#!/usr/bin/env bash
set -euo pipefail

RPI_HOST="${RPI_HOST:-fra@rpi5-01.local}"
RPI_DIR="${RPI_DIR:-/opt/pdoa-uwb-rpi}"
START_WEB=0

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --web                    restart pdoa-web.service after sync
  -h, --help               show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --web)
      START_WEB=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rsync -rltO --delete --no-owner --no-group --no-perms \
  --exclude='.git/' \
  --exclude='.codex-project-id' \
  --exclude='__pycache__/' \
  --exclude='backups/' \
  --exclude='pdoa-monitor' \
  --exclude='build/' \
  --exclude='logs/' \
  --exclude='datasets/' \
  "${repo_root}/" "${RPI_HOST}:${RPI_DIR}/"

ssh "${RPI_HOST}" "cd '${RPI_DIR}' && sudo -u rpi make"

echo "Synced and built on ${RPI_HOST}:${RPI_DIR}"
echo "Run with: ssh ${RPI_HOST} 'cd ${RPI_DIR} && sudo -u rpi ./pdoa-monitor -d /dev/ttyACM0'"

if [[ "${START_WEB}" -eq 1 ]]; then
  ssh "${RPI_HOST}" "sudo systemctl restart pdoa-web.service"
  echo "Web service restarted at http://${RPI_HOST#*@}:8080"
fi
