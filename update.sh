#!/usr/bin/env bash
# Update a systemd-managed bridge host (e.g. a Proxmox LXC set up by install.sh):
# pull the latest code, rebuild the bridge binary, refresh the MCP server's
# Python environment, restart the services, and wait until the bridge is either
# connected to WhatsApp or showing a QR code to link a phone.
#
# A git pull alone is not enough: the service runs the compiled binary, so a
# whatsmeow upgrade only takes effect after a rebuild.
#
# Usage (as root, from anywhere):  /opt/whatsapp/whatsapp-mcp/update.sh
# Override with SERVICE= / MCP_SERVICE= / STATUS_URL= if you changed them.
set -euo pipefail
cd "$(dirname "$0")"

SERVICE="${SERVICE:-whatsapp-bridge}"
MCP_SERVICE="${MCP_SERVICE:-whatsapp-mcp}"
STATUS_URL="${STATUS_URL:-http://127.0.0.1:8080/api/status}"

if [ "$(id -u)" -ne 0 ]; then
  echo "update: run this as root (it restarts systemd services)" >&2
  exit 1
fi

# Run git, go and uv as the user that owns the checkout. Running git as root on
# a checkout owned by another user fails with "dubious ownership", and building
# as root would leave root-owned files the service user cannot update.
OWNER="$(stat -c %U .)"
as_owner() {
  if [ "$OWNER" = root ]; then "$@"; else runuser -u "$OWNER" -- "$@"; fi
}

GO="$(command -v go || true)"
[ -x /usr/local/go/bin/go ] && GO=/usr/local/go/bin/go
if [ -z "$GO" ]; then
  echo "update: go not found; run install.sh first" >&2
  exit 1
fi

echo "update: pulling latest code"
as_owner git pull --ff-only
echo "update: now at $(as_owner git log -1 --oneline)"

echo "update: building whatsapp-bridge with $("$GO" version)"
cd whatsapp-bridge
# Build to a temp file and swap it in, so the running binary is never
# half-written. -buildvcs=false: the binary does not need git metadata, and
# stamping it fails if any part of the checkout has a different owner.
as_owner env CGO_ENABLED=1 "$GO" build -buildvcs=false -o whatsapp-bridge.new .
mv whatsapp-bridge.new whatsapp-bridge
cd ..

has_mcp=false
if systemctl cat "$MCP_SERVICE" >/dev/null 2>&1; then
  has_mcp=true
  UV="$(command -v uv || true)"
  # install.sh puts uv in /usr/local/bin, which a `pct exec` PATH may lack (like go above).
  [ -x /usr/local/bin/uv ] && UV=/usr/local/bin/uv
  if [ -n "$UV" ]; then
    echo "update: syncing the MCP server's Python environment"
    (cd whatsapp-mcp-server && as_owner "$UV" sync --frozen)
  else
    echo "update: WARNING: uv not on PATH, skipping the Python sync" \
      "(uv run syncs it when the service starts)"
  fi
fi

echo "update: restarting $SERVICE"
systemctl restart "$SERVICE"
if $has_mcp; then
  echo "update: restarting $MCP_SERVICE"
  systemctl restart "$MCP_SERVICE"
fi

echo "update: waiting for the bridge to connect to WhatsApp"
for _ in $(seq 1 30); do
  status="$(curl -s -m 2 "$STATUS_URL" || true)"
  if grep -q '"connected":true' <<<"$status"; then
    echo "update: OK, bridge is connected"
    exit 0
  fi
  if grep -q '"has_qr_code":true' <<<"$status"; then
    qr_url="$(sed -n 's/.*"qr_url":"\([^"]*\)".*/\1/p' <<<"$status")"
    echo "update: OK, bridge is running but no phone is linked yet."
    echo "update: open $qr_url and scan it in WhatsApp > Settings > Linked devices > Link a device"
    exit 0
  fi
  sleep 2
done

echo "update: FAILED, bridge not connected after 60s. Recent log:"
journalctl -u "$SERVICE" -n 30 --no-pager
exit 1
