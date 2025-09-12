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
VERSIONS=( "v1.4" )
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

install_version(){
  local ver="$1"
  need_curl
  detect_sudo

  # آدرس صحیح raw گیت‌هاب (بدون refs/heads)
  local url="https://raw.githubusercontent.com/azavaxhuman/Nodex/main/${ver}/install.sh"
  local dst="/opt/dds-nodex/install.sh"

  info "Fetching installer for ${ver} from: ${url}"
  ${SUDO_CMD} mkdir -p /opt/dds-nodex
  # اگر tee نیاز به sudo داشته باشد، قبلش SUDO_CMD را می‌گذاریم
  curl -fsSL "$url" | ${SUDO_CMD} tee "$dst" >/dev/null || fatal "Download failed for ${ver}."
  ${SUDO_CMD} chmod +x "$dst"
  ${SUDO_CMD} bash "$dst" --install || fatal "Installation script for ${ver} failed."
  ok "Installation script for ${ver} completed."
}

show_menu(){
  section "DDS-Nodex Version Picker"
  ce magenta "@DailyDigitalSkills"
  ce bold " "
  ce magenta "Select a version to install:"
  ce green "┌──────────────────────────────────────────────────────────┐"
  local i
  for i in "${!VERSIONS[@]}"; do
    ce green "│  $(printf '%2d' $((i+1))) )  ${VERSIONS[$i]}                                              │"
  done
  ce green "│   0 )  Exit                                              │"
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
      install_version "$ver"
      exit 0
    else
      warn "Invalid choice."
    fi
  done
}

main "$@"
