#!/usr/bin/env bash
# DDS-Nodex Version Picker (clean, CRLF-safe, no line-continuations)
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
VERSIONS=( "v1.3" )   # در آینده فقط اضافه کن: ("v1.3" "v1.4" ...)
SUDO_CMD=""

# ==================== Helpers ====================
need_curl(){ command -v curl >/dev/null 2>&1 || fatal "curl is required. Install curl and try again."; }

detect_sudo(){
  if [[ "$(id -u)" -eq 0 ]]; then
    SUDO_CMD=""
  else
    if command -v sudo >/dev/null 2>&1; then
      SUDO_CMD="sudo"
    else
      warn "sudo not found and you are not root. Trying without sudo (may fail)."
      SUDO_CMD=""
    fi
  fi
}

ver_1_3(){

  need_curl
  detect_sudo

sudo mkdir -p /opt/dds-nodex && curl -fsSL https://raw.githubusercontent.com/azavaxhuman/Nodex/refs/heads/main/v1.3/install.sh | sudo tee /opt/dds-nodex/install.sh >/dev/null && sudo chmod +x /opt/dds-nodex/install.sh && sudo bash /opt/dds-nodex/install.sh --install
  if [[ $? -ne 0 ]]; then
    fatal "Installation script for v1.3 failed."
  else
    ok "Installation script for v1.3 completed."
  fi
}

show_menu(){
  section "DDS-Nodex Version Picker"
  ce green "┌──────────────────────────────────────────────────────────┐"
  local i
  for i in "${!VERSIONS[@]}"; do
    ce green "│  $(printf '%2d' $((i+1))) )  ${VERSIONS[$i]}                                        │"
  done
  ce green "│  0 )  Exit                                              │"
  ce green "└──────────────────────────────────────────────────────────┘"
}

# ==================== Main ====================
main(){
  while true; do
    show_menu
    read -r -p "Select a version [0-${#VERSIONS[@]}]: " choice
    [[ -z "${choice:-}" ]] && { warn "No input."; continue; }

    if [[ "$choice" == "0" ]]; then
      ce bold "Goodbye!"
      exit 0
    fi

    if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#VERSIONS[@]} )); then
      local ver="${VERSIONS[$((choice-1))]}"
      ver_1_3 
      exit 0
    else
      warn "Invalid choice."
    fi
  done
}

main "$@"
