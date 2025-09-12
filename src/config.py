# src/config.py
import os
import json
import logging

def _parse_bool(val, default=False):
    if val is None:
        return default
    v = str(val).strip().lower()
    return v in ("1", "true", "yes", "on")

def _parse_int(val, default):
    if val is None:
        return default
    try:
        return int(str(val).strip())
    except Exception:
        return default

class ConfigManager:
    # Used by main.py: config_file is passed in as an argument
    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self.config = self.load_config()

    def load_config(self):
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                if not config.get('central_server') or not config.get('nodes'):
                    raise ValueError("Missing central_server or nodes in config")

                # --- Set default values if missing ---
                config.setdefault('sync_interval_minutes', 1)
                config.setdefault('net', {})
                config.setdefault('db', {})
                config['net'].setdefault('parallel_node_calls', True)
                config['net'].setdefault('max_workers', 8)
                config['net'].setdefault('request_timeout', 10)
                config['net'].setdefault('connect_pool_size', 50)
                # NEW: TTL for session validation
                config['net'].setdefault('validate_ttl_seconds', 60)

                config['db'].setdefault('wal', True)
                config['db'].setdefault('synchronous', 'NORMAL')  # Options: FULL/NORMAL/OFF
                config['db'].setdefault('cache_size_mb', 20)

                # --- Override config values with environment variables ---
                # sync interval
                config['sync_interval_minutes'] = _parse_int(
                    os.getenv("SYNC_INTERVAL_MINUTES"),
                    config['sync_interval_minutes']
                )

                # network settings
                config['net']['parallel_node_calls'] = _parse_bool(
                    os.getenv("NET_PARALLEL_NODE_CALLS"),
                    config['net']['parallel_node_calls']
                )
                config['net']['max_workers'] = _parse_int(
                    os.getenv("NET_MAX_WORKERS"),
                    config['net']['max_workers']
                )
                config['net']['request_timeout'] = _parse_int(
                    os.getenv("NET_REQUEST_TIMEOUT"),
                    config['net']['request_timeout']
                )
                config['net']['connect_pool_size'] = _parse_int(
                    os.getenv("NET_CONNECT_POOL_SIZE"),
                    config['net']['connect_pool_size']
                )
                # NEW: TTL override from ENV
                config['net']['validate_ttl_seconds'] = _parse_int(
                    os.getenv("NET_VALIDATE_TTL_SECONDS"),
                    config['net']['validate_ttl_seconds']
                )

                # database settings
                db_wal_env = os.getenv("DB_WAL")
                if db_wal_env is not None:
                    config['db']['wal'] = _parse_bool(db_wal_env, config['db']['wal'])

                db_sync_env = os.getenv("DB_SYNCHRONOUS")
                if db_sync_env is not None:
                    sync_mode = str(db_sync_env).strip().upper()
                    if sync_mode in ("FULL", "NORMAL", "OFF"):
                        config['db']['synchronous'] = sync_mode
                    else:
                        logging.warning(f"Invalid DB_SYNCHRONOUS='{db_sync_env}', keeping '{config['db']['synchronous']}'")

                config['db']['cache_size_mb'] = _parse_int(
                    os.getenv("DB_CACHE_SIZE_MB"),
                    config['db']['cache_size_mb']
                )

                return config

        except FileNotFoundError:
            logging.error(f"Config file {self.config_file} not found")
            raise
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in {self.config_file}")
            raise
        except ValueError as e:
            logging.error(f"Config error: {e}")
            raise

    def get_central_server(self):
        return self.config.get('central_server', {})

    def get_nodes(self):
        return self.config.get('nodes', [])

    def get_interval(self):
        return self.config.get('sync_interval_minutes', 1)

    def net(self):
        return self.config.get('net', {})

    def db(self):
        return self.config.get('db', {})
