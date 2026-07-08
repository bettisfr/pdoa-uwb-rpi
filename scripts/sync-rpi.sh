#!/usr/bin/env bash
set -euo pipefail

RPI_HOST="${RPI_HOST:-fra@192.168.1.67}"
RPI_DIR="${RPI_DIR:-/home/fra/pdoa-uwb-rpi}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rsync -av --delete \
  --exclude='.git/' \
  --exclude='.codex-project-id' \
  --exclude='backups/' \
  --exclude='pdoa-monitor' \
  --exclude='build/' \
  "${repo_root}/" "${RPI_HOST}:${RPI_DIR}/"

ssh "${RPI_HOST}" "cd '${RPI_DIR}' && make"

echo "Synced and built on ${RPI_HOST}:${RPI_DIR}"
echo "Run with: ssh ${RPI_HOST} 'cd ${RPI_DIR} && ./pdoa-monitor -d /dev/ttyACM0'"
