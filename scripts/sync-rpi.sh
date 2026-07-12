#!/usr/bin/env bash
set -euo pipefail

RPI_HOST="${RPI_HOST:-fra@192.168.1.67}"
RPI_DIR="${RPI_DIR:-/home/fra/pdoa-uwb-rpi}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_PORT="${WEB_PORT:-8080}"
WEB_DEVICE="${WEB_DEVICE:-/dev/ttyACM0}"
STDDEV_WINDOW="${STDDEV_WINDOW:-100}"
START_WEB=0

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --web                    restart the Raspberry Pi web monitor after sync
  --web-host HOST          web bind address on the Raspberry Pi (default: ${WEB_HOST})
  --web-port PORT          web port on the Raspberry Pi (default: ${WEB_PORT})
  --web-device DEVICE      serial device used by pdoa-monitor (default: ${WEB_DEVICE})
  --stddev-window COUNT    range standard deviation sample window (default: ${STDDEV_WINDOW})
  -h, --help               show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --web)
      START_WEB=1
      shift
      ;;
    --web-host)
      WEB_HOST="$2"
      shift 2
      ;;
    --web-port)
      WEB_PORT="$2"
      shift 2
      ;;
    --web-device)
      WEB_DEVICE="$2"
      shift 2
      ;;
    --stddev-window)
      STDDEV_WINDOW="$2"
      shift 2
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

rsync -av --delete \
  --exclude='.git/' \
  --exclude='.codex-project-id' \
  --exclude='__pycache__/' \
  --exclude='backups/' \
  --exclude='pdoa-monitor' \
  --exclude='build/' \
  --exclude='logs/' \
  --exclude='datasets/' \
  "${repo_root}/" "${RPI_HOST}:${RPI_DIR}/"

ssh "${RPI_HOST}" "cd '${RPI_DIR}' && make"

echo "Synced and built on ${RPI_HOST}:${RPI_DIR}"
echo "Run with: ssh ${RPI_HOST} 'cd ${RPI_DIR} && ./pdoa-monitor -d /dev/ttyACM0'"

if [[ "${START_WEB}" -eq 1 ]]; then
  ssh "${RPI_HOST}" "
    set -e
    pkill -f '[p]ython3 ./scripts/pdoa-web.py' 2>/dev/null || true
    pkill -x pdoa-monitor 2>/dev/null || true
    cd '${RPI_DIR}'
    setsid -f ./scripts/pdoa-web.py \
      --host '${WEB_HOST}' \
      --port '${WEB_PORT}' \
      --device '${WEB_DEVICE}' \
      --stddev-window '${STDDEV_WINDOW}' \
      </dev/null >/tmp/pdoa-web.log 2>&1
  "
  echo "Web monitor restarted at http://${RPI_HOST#*@}:${WEB_PORT}"
fi
