#!/usr/bin/env bash
# Install the WhatsApp bridge and MCP server on a fresh Debian/Ubuntu machine,
# e.g. a Proxmox LXC container. Safe to run again: it skips what is already
# done and keeps your settings in /etc/default/whatsapp-mcp.
#
# Usage (as root inside the container):
#   curl -fsSL https://raw.githubusercontent.com/biovolt/whatsapp-mcp/main/install.sh | bash
# or, from a checkout:
#   ./install.sh
#
# Override with REPO_URL= / INSTALL_DIR= / BRIDGE_PORT= / MCP_PORT= if needed.
set -euo pipefail

# Everything runs inside main, so that with "curl ... | bash" bash has read the
# whole script before any command can read from stdin.
main() {

REPO_URL="${REPO_URL:-https://github.com/biovolt/whatsapp-mcp.git}"
SERVICE_USER=whatsapp
SERVICE_HOME=/opt/whatsapp
INSTALL_DIR="${INSTALL_DIR:-$SERVICE_HOME/whatsapp-mcp}"
BRIDGE_PORT="${BRIDGE_PORT:-8080}"
MCP_PORT="${MCP_PORT:-3000}"
ENV_FILE=/etc/default/whatsapp-mcp
BRIDGE_UNIT=/etc/systemd/system/whatsapp-bridge.service
MCP_UNIT=/etc/systemd/system/whatsapp-mcp.service
MARKER="# Written by whatsapp-mcp install.sh"

# Pinned versions. go.mod needs Go 1.26+; bump these (and the checksums, from
# https://go.dev/dl/?mode=json) when go.mod moves to a newer Go.
GO_VERSION=1.26.9
GO_SHA256_amd64=42d158b4d8f7b61ac0a830567c940a86098fb7aac52e467a5ebec03ef5cc2f8d
GO_SHA256_arm64=4a97373d49fcacdcf3694fea368a500b00ee3e963974f3e7514132717632f052
UV_VERSION=0.13.1

say() { echo "install: $*"; }
# The service user cannot read root's home; git refuses to run from there.
cd /

if [ "$(id -u)" -ne 0 ]; then
  echo "install: run this as root" >&2
  exit 1
fi
if ! command -v apt-get >/dev/null; then
  echo "install: this script supports Debian/Ubuntu (apt-get) only" >&2
  exit 1
fi

# A bridge service that install.sh did not write means this machine was set up
# by hand. Stop before touching anything; update.sh is the tool for that case.
existing="$(systemctl show -p FragmentPath --value whatsapp-bridge 2>/dev/null || true)"
if [ -n "$existing" ] && ! grep -qxF "$MARKER" "$existing"; then
  echo "install: $existing was not written by install.sh, so this machine was" >&2
  echo "install: set up by hand. Nothing was changed. To update it, run:" >&2
  echo "install:   $INSTALL_DIR/update.sh" >&2
  exit 1
fi

# 1. Root password. A Proxmox container created without one cannot be logged
# into on its console. Only asked when there is a terminal to type into.
if [ "$(passwd -S root | awk '{print $2}')" != P ]; then
  if (exec </dev/tty) 2>/dev/null; then
    say "root has no password yet; set one now (used for the Proxmox console)"
    passwd root </dev/tty
  else
    say "WARNING: root has no password; run 'passwd root' to set one"
  fi
fi

# 2. System packages. build-essential: the SQLite driver needs cgo.
# ffmpeg: converts audio to voice notes when sending.
say "installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q git build-essential ffmpeg curl ca-certificates

# 3. Go (Debian's own package is too old for go.mod).
case "$(dpkg --print-architecture)" in
  amd64) GO_ARCH=amd64; GO_SHA256=$GO_SHA256_amd64 ;;
  arm64) GO_ARCH=arm64; GO_SHA256=$GO_SHA256_arm64 ;;
  *) echo "install: unsupported CPU architecture $(dpkg --print-architecture)" >&2; exit 1 ;;
esac
if [ "$(/usr/local/go/bin/go env GOVERSION 2>/dev/null || true)" != "go$GO_VERSION" ]; then
  say "installing Go $GO_VERSION"
  tarball="$(mktemp)"
  curl -fsSL -o "$tarball" "https://go.dev/dl/go$GO_VERSION.linux-$GO_ARCH.tar.gz"
  echo "$GO_SHA256  $tarball" | sha256sum -c --quiet
  rm -rf /usr/local/go
  tar -C /usr/local -xzf "$tarball"
  rm -f "$tarball"
fi
cat >/etc/profile.d/go.sh <<'EOF'
export PATH=$PATH:/usr/local/go/bin
EOF

# 4. uv (runs the Python MCP server), installed for all users.
if [ "$(uv --version 2>/dev/null | awk '{print $2}')" != "$UV_VERSION" ]; then
  say "installing uv $UV_VERSION"
  curl -fsSL "https://astral.sh/uv/$UV_VERSION/install.sh" |
    env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi

# 5. Service user and code.
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  say "creating user $SERVICE_USER"
  useradd --system --create-home --home-dir "$SERVICE_HOME" --shell /usr/sbin/nologin "$SERVICE_USER"
fi
if [ ! -d "$INSTALL_DIR/.git" ]; then
  say "cloning $REPO_URL into $INSTALL_DIR"
  install -d -o "$SERVICE_USER" -g "$SERVICE_USER" "$(dirname "$INSTALL_DIR")"
  runuser -u "$SERVICE_USER" -- git clone "$REPO_URL" "$INSTALL_DIR"
fi
# The services run as $SERVICE_USER, so it must own the code. A checkout cloned
# as root leaves the MCP service unable to create its Python environment, and
# it restarts forever.
if [ -n "$(find "$INSTALL_DIR" ! -user "$SERVICE_USER" -print -quit)" ]; then
  say "giving $SERVICE_USER ownership of $INSTALL_DIR"
  chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
fi

# 6. Settings, kept across re-runs so your edits survive.
if [ ! -f "$ENV_FILE" ]; then
  ip="$(hostname -I | awk '{print $1}')"
  say "writing $ENV_FILE"
  cat >"$ENV_FILE" <<EOF
# Settings for the whatsapp-bridge and whatsapp-mcp services.
# After editing: systemctl restart whatsapp-bridge whatsapp-mcp

# Address other machines use to reach the bridge (shown on the QR/status pages).
WHATSAPP_PUBLIC_URL=http://$ip:$BRIDGE_PORT
WHATSAPP_BRIDGE_PORT=$BRIDGE_PORT

# Optional: POST every incoming message to this URL.
#WHATSAPP_WEBHOOK_URL=http://192.0.2.10:9100/webhook

# MCP server: SSE transport so Claude on another machine can connect.
MCP_TRANSPORT=sse
MCP_PORT=$MCP_PORT
WHATSAPP_API_BASE_URL=http://localhost:$BRIDGE_PORT/api
# systemd runs the bridge; the MCP server must not start a second one.
WHATSAPP_BRIDGE_AUTOSTART=0
EOF
fi

# 7. systemd services. Restart=always: the bridge exits when no QR code is
# scanned in time, and must come back with a fresh code. A service file that
# install.sh did not write (no marker line) is left alone, so hand-made
# settings on an existing host are never lost.
writable_unit() {
  [ ! -e "$1" ] || grep -qxF "$MARKER" "$1" || {
    say "WARNING: leaving $1 alone (not written by install.sh)"
    return 1
  }
}
say "writing systemd services"
if writable_unit "$BRIDGE_UNIT"; then cat >"$BRIDGE_UNIT" <<EOF
$MARKER
[Unit]
Description=WhatsApp bridge
After=network-online.target
Wants=network-online.target

[Service]
User=$SERVICE_USER
# The bridge keeps its login and messages in store/ under this directory.
WorkingDirectory=$INSTALL_DIR/whatsapp-bridge
EnvironmentFile=$ENV_FILE
ExecStart=$INSTALL_DIR/whatsapp-bridge/whatsapp-bridge
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
fi
if writable_unit "$MCP_UNIT"; then cat >"$MCP_UNIT" <<EOF
$MARKER
[Unit]
Description=WhatsApp MCP server
After=whatsapp-bridge.service
Wants=whatsapp-bridge.service

[Service]
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR/whatsapp-mcp-server
EnvironmentFile=$ENV_FILE
ExecStart=/usr/local/bin/uv run --frozen main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
fi
systemctl daemon-reload
systemctl enable whatsapp-bridge whatsapp-mcp

# 8. Build, start and wait (shared with later updates).
STATUS_URL="http://127.0.0.1:$BRIDGE_PORT/api/status" "$INSTALL_DIR/update.sh"

ip="$(hostname -I | awk '{print $1}')"
cat <<EOF

install: done.
  Bridge status page:  http://$ip:$BRIDGE_PORT/status
  Link a phone (QR):   http://$ip:$BRIDGE_PORT/qr
  MCP endpoint:        http://$ip:$MCP_PORT/sse
  Add it to Claude Code on your computer:
    claude mcp add --transport sse --scope user whatsapp http://$ip:$MCP_PORT/sse
  Settings: $ENV_FILE    Update later: $INSTALL_DIR/update.sh

  WARNING: the bridge and MCP server have no password. Only allow your own
  network to reach ports $BRIDGE_PORT and $MCP_PORT (see the README).
EOF
}

main "$@"
