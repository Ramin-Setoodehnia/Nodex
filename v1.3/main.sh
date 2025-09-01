#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'

# ==================== UI ====================
ce() { local c="$1"; shift || true; local code=0
  case "$c" in red)code=31;;green)code=32;;yellow)code=33;;blue)code=34;;magenta)code=35;;cyan)code=36;;bold)code=1;; *)code=0;; esac
  echo -e "\033[${code}m$*\033[0m"
}
ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { ce "$1" "[$(ts)] $2"; }
section(){ ce magenta "\n────────────────────────────────────────────────────"; ce bold " $1"; ce magenta "────────────────────────────────────────────────────\n"; }
ok()  { log green   "[OK]   $1"; }
warn(){ log yellow  "[WARN] $1"; }
fatal(){ log red    "[FATAL] $1"; exit "${2:-1}"; }
info(){ log cyan    "[INFO] $1"; }

# ==================== Config ====================
RAW_BASE="https://raw.githubusercontent.com/azavaxhuman/Nodex/refs/heads/main"
VERSIONS=( "v1.3" )
INSTALL_ARGS=( "--install" )

# ==================== Helpers ====================
need_curl(){
  command -v curl >/dev/null 2>&1 || fatal "curl is required. Install curl and try again."
}
sudo_cmd(){
  if [[ "$(id -u)" -eq 0 ]]; then echo ""; else echo "sudo"; fi
}

run_install(){
  local ver="$1"
  local url="${RAW_BASE}/${ver}/install.sh"
  section "Run installer for ${ver}"
  info "Fetching: ${url}"
  need_curl

  if ! curl -fsSL "$url" | $(sudo_cmd) bash -s -- "${INSTALL_ARGS[@]}"; then
    fatal "Install failed for ${ver}"
  fi
  ok "Installer finished for ${ver}"
}

show_menu(){
  section "DDS-Nodex Version Picker"
  ce green "┌──────────────────────────────────────────────────────────┐"
  for i in "${!VERSIONS[@]}"; do
    ce green "│  $(printf '%2d' $((i+1))) )  ${VERSIONS[$i]}                                        │"
  done
  ce green "│  0 )  Exit                                              │"
  ce green "└──────────────────────────────────────────────────────────┘"
}

# ==================== Main ====================
while true; do
  show_menu
  read -p "Select a version [0-${#VERSIONS[@]}]: " -r choice
  [[ -z "${choice:-}" ]] && { warn "No input."; continue; }

  if [[ "$choice" == "0" ]]; then
    ce bold "Goodbye!"; exit 0
  fi

  # عدد معتبر؟
  if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#VERSIONS[@]} )); then
    ver="${VERSIONS[$((choice-1))]}"
    run_install "$ver"
    exit 0
  else
    warn "Invalid choice."
  fi
done
