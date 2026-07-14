#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit_name="pdoa-web.service"

sudo install -m 0644 "${repo_root}/systemd/${unit_name}" "/etc/systemd/system/${unit_name}"
sudo systemctl daemon-reload
sudo systemctl enable --now "${unit_name}"

systemctl --no-pager --full status "${unit_name}"
