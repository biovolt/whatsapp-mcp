#!/usr/bin/env bash
# Update a systemd-managed bridge host (e.g. the Proxmox box): pull the latest
# code, rebuild the bridge binary, restart the service, and wait until the
# bridge reports it is connected to WhatsApp.
#
# A git pull alone is not enough: the service runs the compiled binary, so a
# whatsmeow upgrade only takes effect after a rebuild.
#
# Usage (as root, from anywhere):  /opt/whatsapp/whatsapp-mcp/update.sh
# Override the service name or status URL with SERVICE= / STATUS_URL=.
set -euo pipefail
cd "$(dirname "$0")"

SERVICE="${SERVICE:-whatsapp-bridge}"
STATUS_URL="${STATUS_URL:-http://127.0.0.1:8080/api/status}"

echo "update: pulling latest code"
git pull --ff-only
echo "update: now at $(git log -1 --oneline)"

echo "update: building whatsapp-bridge"
cd whatsapp-bridge
# Build to a temp file and swap it in, so the running binary is never
# half-written.
go build -o whatsapp-bridge.new .
mv whatsapp-bridge.new whatsapp-bridge

echo "update: restarting $SERVICE"
systemctl restart "$SERVICE"

echo "update: waiting for the bridge to connect to WhatsApp"
for _ in $(seq 1 30); do
  if curl -s -m 2 "$STATUS_URL" | grep -q '"connected":true'; then
    echo "update: OK, bridge is connected"
    exit 0
  fi
  sleep 2
done

echo "update: FAILED, bridge not connected after 60s. Recent log:"
journalctl -u "$SERVICE" -n 30 --no-pager
exit 1
