#!/usr/bin/env bash
set -euo pipefail

ROOT="${GROSTER_ROOT:-/opt/groster}"
SRC="${ROOT}/source"
TMP_SRC="${ROOT}/source.new"
DATA="${ROOT}/data"
CONFIG="${ROOT}/config"
SYSTEMD_DIR="/etc/systemd/system"

sudo mkdir -p "${ROOT}" "${DATA}" "${CONFIG}"

# Copy the current source tree into /opt/groster/source.
# Run this script from the repository root after unpacking the zip.
sudo rm -rf "${TMP_SRC}"
sudo mkdir -p "${TMP_SRC}"
tar \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  -cf - . | sudo tar -C "${TMP_SRC}" -xf -
sudo rm -rf "${SRC}"
sudo mv "${TMP_SRC}" "${SRC}"

if [[ ! -f "${CONFIG}/game-roster.env" ]]; then
  sudo cp "${SRC}/deploy/systemd/game-roster.env" "${CONFIG}/game-roster.env"
fi

sudo chown -R 10001:10001 "${DATA}"
sudo cp "${SRC}/deploy/systemd/game-roster.service" "${SYSTEMD_DIR}/game-roster.service"
sudo systemctl daemon-reload
sudo systemctl enable game-roster.service

echo "Installed game-roster.service."
echo "Traefik was not modified. Existing Traefik file-provider config is left untouched."
echo "Review ${CONFIG}/game-roster.env, then run:"
echo "  sudo systemctl restart game-roster.service"
echo "  sudo journalctl -u game-roster -f"
