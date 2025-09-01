import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

class SyncManager:
    def __init__(self, api_manager, config_manager, traffic_state_manager):
        self.api_manager = api_manager
        self.config_manager = config_manager
        self.traffic_state_manager = traffic_state_manager

    @staticmethod
    def _to_int(val, default=0):
        try:
            if val is None:
                return default
            return int(val)
        except Exception:
            try:
                return int(str(val).strip())
            except Exception:
                return default

    @staticmethod
    def _now_ms():
        return int(time.time() * 1000)

    # --- Client identity helpers (protocol-aware) ---
    def _client_key(self, c, protocol: str):
        p = (protocol or "").lower()
        if not isinstance(c, dict):
            return None
        if p == "trojan":
            # Trojan: password is the unique identifier
            return c.get("password") or c.get("email") or c.get("id")
        elif p == "shadowsocks":
            # Shadowsocks: clientId is email
            return c.get("email")
        else:
            # vmess/vless: id or email
            return c.get("id") or c.get("email")

    def _client_id_for_api(self, c, protocol: str):
        p = (protocol or "").lower()
        if not isinstance(c, dict):
            return None
        if p == "trojan":
            return c.get("password")
        elif p == "shadowsocks":
            return c.get("email")
        else:
            return c.get("id")

    def _is_safu_fresh(self, c):
        """
        A fresh SAFU client is waiting for first use: startAfterFirstUse=True and expiryTime<=0
        """
        if not isinstance(c, dict):
            return False
        safu = bool(c.get('startAfterFirstUse'))
        exp = self._to_int(c.get('expiryTime'), 0)
        return safu and exp <= 0

    def _is_active_started(self, c, now_ms):
        """Client is active if expiryTime is in the future."""
        exp = self._to_int(c.get('expiryTime'), 0)
        return exp > now_ms

    def _is_ended(self, c, now_ms):
        """Client has ended if expiryTime is in the past or negative."""
        exp = self._to_int(c.get('expiryTime'), 0)
        return (exp > 0 and exp <= now_ms) or exp < 0

    def sync_inbounds_and_clients(self):
        central = self.config_manager.get_central_server()
        nodes = self.config_manager.get_nodes()

        try:
            central_session = self.api_manager.login(central)
            central_inbounds = self.api_manager.get_inbounds(central, central_session)
            if not central_inbounds:
                logging.error("No inbounds retrieved from central server, skipping sync")
                return
        except Exception as e:
            logging.error(f"Failed to connect to central server: {e}")
            return

        # Parse central inbounds and extract client lists
        parsed_central = []
        for ib in central_inbounds:
            settings = {}
            try:
                settings = json.loads(ib.get('settings') or '{}') or {}
            except Exception:
                pass
            parsed_central.append((ib, settings.get('clients', [])))

        for node in nodes:
            try:
                node_session = self.api_manager.login(node)
                node_inbounds = self.api_manager.get_inbounds(node, node_session)
                node_inbound_map = {inbound['id']: inbound for inbound in node_inbounds}

                # Synchronize inbounds (central -> node)
                for central_inbound, _ in parsed_central:
                    cid = central_inbound['id']
                    if cid not in node_inbound_map:
                        self.api_manager.add_inbound(node, node_session, central_inbound)
                    else:
                        self.api_manager.update_inbound(node, node_session, cid, central_inbound)
                        node_inbound_map.pop(cid, None)

                # Remove inbounds that are not present on the central server
                for inbound_id in list(node_inbound_map.keys()):
                    self.api_manager.delete_inbound(node, node_session, inbound_id)

                # Synchronize clients with SAFU-aware policy
                now_ms = self._now_ms()

                for central_inbound, c_clients in parsed_central:
                    cid = central_inbound['id']

                    # Get clients from node
                    node_inbound = next((ni for ni in node_inbounds if ni['id'] == cid), None)
                    n_clients = []
                    if node_inbound:
                        try:
                            n_clients = (json.loads(node_inbound.get('settings') or '{}') or {}).get('clients', [])
                        except Exception:
                            n_clients = []

                    protocol = (central_inbound.get('protocol') or '').lower()

                    # Build protocol-aware client maps
                    n_client_map = { self._client_key(cl, protocol): cl for cl in n_clients if self._client_key(cl, protocol) }
                    c_client_map = { self._client_key(cl, protocol): cl for cl in c_clients if self._client_key(cl, protocol) }

                    # --- 1) If central has fresh SAFU clients: push them directly to node, skip merging
                    if any(self._is_safu_fresh(ccl) for ccl in c_clients):
                        for k, ccl in c_client_map.items():
                            if not self._is_safu_fresh(ccl):
                                continue  # Only process fresh SAFU clients
                            # Push to node (restore from Ended to SAFU)
                            if k in n_client_map:
                                nid = self._client_id_for_api(n_client_map[k], protocol)
                                # If exists on node, update
                                if nid is not None:
                                    try:
                                        self.api_manager.update_client(node, node_session, nid, cid, ccl)
                                    except Exception as _e:
                                        logging.error(f"Failed to push SAFU from central to node for client {k}: {_e}")
                            else:
                                # If not on node, add
                                try:
                                    self.api_manager.add_client(node, node_session, cid, ccl)
                                except Exception as _e:
                                    logging.error(f"Failed to add SAFU client {k} to node: {_e}")

                        # Continue to general PUSH phase (central -> node)
                        # (In this case, merging from node to central is intentionally skipped)

                    else:
                        # --- 2) If central does not have fresh SAFU: only promote active start time from node to central if needed
                        for k, ccl in c_client_map.items():
                            ncl = n_client_map.get(k)
                            if not ncl:
                                continue

                            central_exp = self._to_int(ccl.get('expiryTime'), 0)
                            node_exp    = self._to_int(ncl.get('expiryTime'), 0)

                            central_started_active = central_exp > now_ms
                            node_started_active    = node_exp > now_ms

                            should_promote = (not central_started_active) and node_started_active
                            if should_promote:
                                # Promote start time from node to central (minimum of positive values)
                                merged = node_exp if central_exp <= 0 else min(central_exp, node_exp)
                                if merged != central_exp and merged > now_ms:
                                    ccl['expiryTime'] = merged
                                    if 'startAfterFirstUse' in ccl and ccl.get('startAfterFirstUse') is True:
                                        ccl['startAfterFirstUse'] = False
                                    try:
                                        client_id = self._client_id_for_api(ccl, protocol) or self._client_id_for_api(ncl, protocol)
                                        if client_id is None:
                                            logging.warning(f"[SAFU-MERGE] Missing clientId for protocol={protocol} key={k} on inbound {cid}; central update skipped.")
                                        else:
                                            self.api_manager.update_client(central, central_session, client_id, cid, ccl)
                                            logging.info(f"[SAFU-MERGE] expiryTime merged to central for client {k} (inbound {cid}): {central_exp} -> {merged}")
                                    except Exception as _e:
                                        logging.error(f"Failed to update central client {k} after SAFU merge: {_e}")
                            # If node is Ended, do not promote to central

                    # --- 3) Final PUSH: central version (after above policy) to node
                    # Add or update clients
                    for ccl in c_clients:
                        k = self._client_key(ccl, protocol)
                        if k in n_client_map:
                            nid = self._client_id_for_api(n_client_map[k], protocol)
                            try:
                                self.api_manager.update_client(node, node_session, nid, cid, ccl)
                            except Exception as _e:
                                logging.error(f"Failed to update client {k} on node: {_e}")
                            # Remove from deletion candidates
                            n_client_map.pop(k, None)
                        else:
                            try:
                                self.api_manager.add_client(node, node_session, cid, ccl)
                            except Exception as _e:
                                logging.error(f"Failed to add client {k} on node: {_e}")

                    # Remove clients that are not present on central
                    for k, ncl in list(n_client_map.items()):
                        n_clid = self._client_id_for_api(ncl, protocol)
                        if n_clid is not None:
                            try:
                                self.api_manager.delete_client(node, node_session, cid, n_clid)
                            except Exception as _e:
                                logging.error(f"Failed to delete extra client {k} on node: {_e}")

            except Exception as e:
                logging.error(f"Error syncing with node {node['url']}: {e}")

    def _fetch_node_traffic_parallel(self, nodes_by_url, node_sessions, email):
        """Parallelize traffic reads (I/O-bound only). Writes remain serial."""
        currents_by_server = {}
        futures = {}
        max_workers = min(len(node_sessions), self.config_manager.net().get('max_workers', 8))
        if max_workers <= 0:
            max_workers = 1

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for srv_url, sess in node_sessions.items():
                node = nodes_by_url.get(srv_url)
                if not node or not sess:
                    continue
                futures[ex.submit(self.api_manager.get_client_traffic, node, sess, email)] = srv_url

            for fut in as_completed(futures):
                srv_url = futures[fut]
                try:
                    n_up, n_down = fut.result()
                except Exception as e:
                    logging.error(f"Traffic fetch failed for {email} on {srv_url}: {e}")
                    n_up, n_down = 0, 0
                currents_by_server[srv_url] = (n_up, n_down)

        return currents_by_server

    def sync_traffic(self):
        central = self.config_manager.get_central_server()
        nodes = self.config_manager.get_nodes()
        net_opts = self.config_manager.net()

        # Login to central server
        try:
            central_sess = self.api_manager.login(central)
        except Exception as e:
            logging.error(f"Failed to connect to central server: {e}")
            return

        # Get client list from central server
        try:
            central_inbounds = self.api_manager.get_inbounds(central, central_sess)
            if not central_inbounds:
                logging.error("No inbounds retrieved from central server, skipping traffic sync")
                return
        except Exception as e:
            logging.error(f"Failed to get inbounds from central server: {e}")
            return

        # Collect client emails from central server (including settings)
        client_emails = set()
        for inbound in central_inbounds:
            for client in inbound.get('clientStats') or []:
                if client and 'email' in client:
                    client_emails.add(client['email'])
            try:
                s = json.loads(inbound.get('settings') or '{}') or {}
                for c in s.get('clients', []):
                    e = c.get('email')
                    if e:
                        client_emails.add(e)
            except Exception:
                pass

        # Login to nodes (optional)
        node_sessions = {}
        for node in nodes:
            try:
                node_sessions[node['url']] = self.api_manager.login(node)
            except Exception as e:
                logging.error(f"Failed to login node {node['url']}: {e}")

        nodes_by_url = {node['url']: node for node in nodes}
        parallel_reads = net_opts.get('parallel_node_calls', True)

        for email in client_emails:
            try:
                # 1) Read current traffic from all servers
                currents_by_server = {}
                c_up, c_down = self.api_manager.get_client_traffic(central, central_sess, email)
                currents_by_server[central['url']] = (c_up, c_down)

                if parallel_reads and node_sessions:
                    currents_by_server.update(
                        self._fetch_node_traffic_parallel(nodes_by_url, node_sessions, email)
                    )
                else:
                    for srv_url, sess in node_sessions.items():
                        node = nodes_by_url.get(srv_url)
                        if not node or not sess:
                            continue
                        n_up, n_down = self.api_manager.get_client_traffic(node, sess, email)
                        currents_by_server[srv_url] = (n_up, n_down)

                # 2) Detect first time or central reset
                last_central = self.traffic_state_manager.get_last_counter(email, central['url'])
                if last_central is None:
                    # First observation of this user -> start cycle at central snapshot
                    self.traffic_state_manager.reset_cycle(email, currents_by_server, central['url'])
                    total_up, total_down = currents_by_server[central['url']]

                    # Write total to all servers and set baseline = written value
                    self.api_manager.update_client_traffic(central, central_sess, email, total_up, total_down)
                    self.traffic_state_manager.set_last_counter(email, central['url'], total_up, total_down)

                    batch_items = []
                    for srv_url, sess in node_sessions.items():
                        node = nodes_by_url.get(srv_url)
                        if node and sess:
                            self.api_manager.update_client_traffic(node, sess, email, total_up, total_down)
                            batch_items.append((srv_url, total_up, total_down))
                    if batch_items:
                        self.traffic_state_manager.set_last_counters_batch(email, batch_items)

                    logging.info(f"[INIT] {email}: total set to central current ({total_up},{total_down}); baselines initialized & aligned; node_totals cleared.")
                    continue

                last_cu, last_cd = last_central
                central_reset = (c_up < last_cu) or (c_down < last_cd)
                if central_reset:
                    # Start a new cycle (central reset)
                    self.traffic_state_manager.reset_cycle(email, currents_by_server, central['url'])
                    total_up, total_down = currents_by_server[central['url']]

                    # Write total to all servers and set baseline = written value
                    self.api_manager.update_client_traffic(central, central_sess, email, total_up, total_down)
                    self.traffic_state_manager.set_last_counter(email, central['url'], total_up, total_down)

                    batch_items = []
                    for srv_url, sess in node_sessions.items():
                        node = nodes_by_url.get(srv_url)
                        if node and sess:
                            self.api_manager.update_client_traffic(node, sess, email, total_up, total_down)
                            batch_items.append((srv_url, total_up, total_down))
                    if batch_items:
                        self.traffic_state_manager.set_last_counters_batch(email, batch_items)

                    logging.warning(
                        f"[CENTRAL RESET] {email}: total reset to central current ({total_up},{total_down}); all servers aligned; node_totals cleared."
                    )
                    continue

                # 3) If no central reset: calculate per-server deltas
                total_up, total_down = self.traffic_state_manager.get_total(email)
                added_up, added_down = 0, 0

                for srv_url, (cur_up, cur_down) in currents_by_server.items():
                    last = self.traffic_state_manager.get_last_counter(email, srv_url)
                    if last is None:
                        # First observation from this server: baseline = current (delta 0)
                        self.traffic_state_manager.set_last_counter(email, srv_url, cur_up, cur_down)
                        continue

                    last_up, last_down = last
                    if cur_up >= last_up and cur_down >= last_down:
                        du = cur_up - last_up
                        dd = cur_down - last_down
                    else:
                        # Reset or manipulation on this server: delta = current value
                        du = cur_up
                        dd = cur_down
                        logging.warning(
                            f"[NODE RESET] {email} @ {srv_url}: last=({last_up},{last_down}) -> cur=({cur_up},{cur_down}); delta=cur."
                        )

                    if du > 0 or dd > 0:
                        added_up += du
                        added_down += dd
                        # <<< جدید: ثبت دلتا برای per-node >>>
                        self.traffic_state_manager.add_node_delta(email, srv_url, du, dd)

                # 4) Add deltas and save new total (only if changed)
                if added_up != 0 or added_down != 0:
                    total_up += added_up
                    total_down += added_down
                    changed = self.traffic_state_manager.set_total(email, total_up, total_down)
                else:
                    changed = False

                # 5) Write total to central and all nodes + update baseline only if changed
                if changed:
                    # Central server
                    self.api_manager.update_client_traffic(central, central_sess, email, total_up, total_down)
                    # Update central baseline
                    self.traffic_state_manager.set_last_counter(email, central['url'], total_up, total_down)

                    # Nodes (batch baseline)
                    batch_items = []
                    for srv_url, sess in node_sessions.items():
                        node = nodes_by_url.get(srv_url)
                        if node and sess:
                            self.api_manager.update_client_traffic(node, sess, email, total_up, total_down)
                            batch_items.append((srv_url, total_up, total_down))
                    if batch_items:
                        self.traffic_state_manager.set_last_counters_batch(email, batch_items)

                    logging.debug(f"[DELTA ADD] {email}: +({added_up},{added_down}) -> total=({total_up},{total_down})")

            except Exception as e:
                logging.error(f"Error syncing traffic for {email}: {e}")
