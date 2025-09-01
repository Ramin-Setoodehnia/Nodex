#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'

# ==================== UI ====================
ce() { local c="$1"; shift || true; local code=0
  case "$c" in red)code=31;;green)code=32;;yellow)code=33;;blue)code=34;;magenta)code=35;;cyan)code=36;;bold)code=1;; *)code=0;; esac
  echo -e "\033[${code}m$*\033[0m"
}
section(){ ce magenta "\n────────────────────────────────────────────────────"; ce bold " $1"; ce magenta "────────────────────────────────────────────────────\n"; }
ok()  { ce green   "[OK]   $1"; }
warn(){ ce yellow  "[WARN] $1"; }
fatal(){ ce red    "[FATAL] $1"; exit 1; }

need_curl(){
  command -v curl >/dev/null 2>&1 || fatal "curl is required. Install curl and try again."
}

show_menu(){
  section "DDS-Nodex Version Picker"
  ce green "┌──────────────────────────────────────────────────────────┐"
  ce green "│  1 )  v1.3                                              │"
  ce green "│  0 )  Exit                                              │"
  ce green "└──────────────────────────────────────────────────────────┘"
}

# ==================== Main ====================
while true; do
  show_menu
  read -p "Select a version [0-1]: " -r choice
  [[ -z "${choice:-}" ]] && { warn "No input."; continue; }

  if [[ "$choice" == "0" ]]; then
    ce bold "Goodbye!"; exit 0
  fi

  if [[ "$choice" == "1" ]]; then
    section "Downloading installer for v1.3"
    need_curl
    curl -fsSL "https://raw.githubusercontent.com/azavaxhuman/Nodex/refs/heads/main/v1.3/install.sh" -o install.sh \
      && chmod +x install.sh \
      && sudo mv install.sh /opt/dds-nodex/install.sh \
      && sudo chown root:root /opt/dds-nodex/install.sh \
      && ok "Installer downloaded and made executable."
      && /opt/dds-nodex/install.sh
      && exit 0 \
      || fatal "Failed to install v1.3"
  else
    warn "Invalid choice."
  fi
done
