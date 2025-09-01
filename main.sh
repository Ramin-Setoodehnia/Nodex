#!/usr/bin/env bash
# DDS-Nodex Version Picker (clean, CRLF-safe)
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
VERSIONS=( "v1.3" )
INSTALL_URL_V13="https://raw.githubusercontent.com/azavaxhuman/Nodex/refs/heads/main/v1.3/install.sh"
TARGET_DIR="/opt/dds-nodex"
TARGET_FILE="${TARGET_DIR}/install.sh"
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

ensure_target_dir(){
  ${SUDO_CMD} mkdir -p "${TARGET_DIR}" || fatal "Failed to create ${TARGET_DIR}"
  ${SUDO_CMD} chmod 755 "${TARGET_DIR}" || true
}

ver_1_3(){
  need_curl
  detect_sudo
  ensure_target_dir

  section "Downloading installer for v1.3 → ${TARGET_FILE}"
  # نوشتن امن در مسیر روت با sudo + tee
  if curl -fsSL "${INSTALL_URL_V13}" | ${SUDO_CMD} tee "${TARGET_FILE}" >/dev/null; then
    ${SUDO_CMD} chmod +x "${TARGET_FILE}"
    ok "Installer saved to ${TARGET_FILE} and made executable."
  else
    fatal "Failed to download installer (curl)."
  fi

  section "Running installer"
  if ${SUDO_CMD} bash "${TARGET_FILE}" --install; then
    ok "Installation completed successfully."
  else
    fatal "Installation failed."
  fi
}

show_menu(){
  section "DDS-Nodex Version Picker"
  ce green "┌──────────────────────────────────────────────────────────┐"
  ce green "│  1 )  v1.3                                              │"
  ce green "│  0 )  Exit                                              │"
  ce green "└──────────────────────────────────────────────────────────┘"
}

# ==================== Main ====================
main(){
  while true; do
    show_menu
    read -r -p "Select a version [0-${#VERSIONS[@]}]: " choice
    [[ -z "${choice:-}" ]] && { warn "No input."; continue; }

    case "$choice" in
      0) ce bold "Goodbye!"; exit 0 ;;
      1) ver_1_3; exit 0 ;;
      *) warn "Invalid choice." ;;
    esac
  done
}

main "$@"
