#!/usr/bin/env bash
# Single-instance launcher for the WhatsApp bridge.
#
# Only one bridge process can run at a time: WhatsApp allows a single active
# socket per linked device, and the REST API binds :8080. Starting a second
# instance kicks the first off the WhatsApp session (StreamReplaced) and the
# kicked one never reconnects. This script guarantees a clean single instance
# by stopping whatever currently owns :8080 before starting a fresh bridge.
#
# Point your launcher at this script instead of ./whatsapp-bridge.
set -euo pipefail
cd "$(dirname "$0")"

listeners() { lsof -ti tcp:8080 -sTCP:LISTEN 2>/dev/null || true; }

pids="$(listeners)"
if [ -n "$pids" ]; then
  echo "run-bridge: stopping existing instance on :8080 (PID ${pids//$'\n'/ })"
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true
  for _ in $(seq 1 20); do
    [ -z "$(listeners)" ] && break
    sleep 0.25
  done
  pids="$(listeners)"
  if [ -n "$pids" ]; then
    echo "run-bridge: force-killing stubborn instance (PID ${pids//$'\n'/ })"
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
    sleep 0.5
  fi
fi

# Hook: forward every inbound (watched-chat) message to the wa-agent webhook.
# The bridge reads this ONLY from the environment at startup (getWebhookURL), so
# default it here — a plain ./run-bridge.sh then always wires the agent. Override
# by exporting WHATSAPP_WEBHOOK_URL before calling this script.
: "${WHATSAPP_WEBHOOK_URL:=http://127.0.0.1:9100/webhook}"
export WHATSAPP_WEBHOOK_URL

echo "run-bridge: starting whatsapp-bridge (webhook → $WHATSAPP_WEBHOOK_URL)"
exec ./whatsapp-bridge
