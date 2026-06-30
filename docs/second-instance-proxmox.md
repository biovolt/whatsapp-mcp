# How-To: Run a Second WhatsApp-MCP Instance on Proxmox

Set up an independent whatsapp-mcp stack (e.g. a billing WhatsApp number) on a
native Proxmox LXC — no Docker — without touching the existing personal bridge.

This guide assumes:

- LXC IP: `192.168.10.123`
- Default ports: bridge REST API `8080`, MCP SSE server `3000`

Adjust the IP/ports to your environment.

> **Why a separate host?** The bridge binds `:8080` and the MCP server reaches it at
> `localhost:8080`. Both are configurable via env vars (`WHATSAPP_BRIDGE_PORT`,
> `WHATSAPP_API_BASE_URL`) for same-host multi-instance, but a separate LXC keeps the
> default ports free and is the simplest, lowest-risk path.

---

## 1. Create the LXC

In the Proxmox UI (or `pct create`): **Debian 12** unprivileged container,
1–2 vCPU, 1 GB RAM, 8 GB disk. Assign the static IP `192.168.10.123` on your
LAN/VLAN. Start it and open the console (or SSH in).

### Optional: enable root SSH access

If you want to SSH into the container instead of using the Proxmox console, run the
following from the console (or via `pct enter <ctid>` on the Proxmox host).

Set the root password:

```bash
passwd root
```

Allow root + password login over SSH:

```bash
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
systemctl restart ssh
```

> **Watch for drop-in overrides.** Debian 12 / cloud images often set
> `PasswordAuthentication no` in a file under `/etc/ssh/sshd_config.d/`, which wins over
> the main config. Check, and if needed add a last-word-wins override:
>
> ```bash
> grep -R -E 'PasswordAuthentication|PermitRootLogin' /etc/ssh/sshd_config.d/ 2>/dev/null
> printf 'PermitRootLogin yes\nPasswordAuthentication yes\n' > /etc/ssh/sshd_config.d/99-root-pw.conf
> systemctl restart ssh
> ```

Verify the effective settings:

```bash
sshd -T | grep -E 'permitrootlogin|passwordauthentication'
```

> ⚠️ Root-with-password over SSH is the weakest config — acceptable on a firewalled
> LAN/VLAN for setup, but afterward prefer SSH keys (`ssh-copy-id`) and set
> `PermitRootLogin prohibit-password` again, especially since this box also runs the
> no-auth WhatsApp bridge.

## 2. Install dependencies

```bash
apt update
apt install -y git build-essential ffmpeg curl
```

Install **Go 1.25+** (Debian's package is older, so pull upstream):

```bash
curl -LO https://go.dev/dl/go1.25.0.linux-amd64.tar.gz
rm -rf /usr/local/go && tar -C /usr/local -xzf go1.25.0.linux-amd64.tar.gz
echo 'export PATH=$PATH:/usr/local/go/bin' >> /etc/profile.d/go.sh && . /etc/profile.d/go.sh
go version    # confirm 1.25+
```

Install **uv** (Python runner; needs Python 3.11+, which Debian 12 has):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

> `ffmpeg` is only needed for sending voice notes — keep it if unsure.

## 3. Service account, clone, and build

```bash
useradd -r -m -d /opt/whatsapp whatsapp
git clone https://github.com/biovolt/whatsapp-mcp.git /opt/whatsapp/whatsapp-mcp
cd /opt/whatsapp/whatsapp-mcp/whatsapp-bridge
CGO_ENABLED=1 go build -buildvcs=false -o whatsapp-bridge .
chown -R whatsapp:whatsapp /opt/whatsapp
```

> `CGO_ENABLED=1` is required — the bridge uses the `mattn/go-sqlite3` driver, which
> needs cgo (hence `build-essential`). `libsqlite3-dev` is **not** needed; the driver
> bundles its own SQLite C source.
>
> `-buildvcs=false` disables git VCS stamping. When the build user differs from the
> `.git` owner (e.g. cloned as root, then chowned to `whatsapp`), git refuses with
> "dubious ownership" and the build fails with `error obtaining VCS status: exit
> status 128` — **producing no new binary**. The flag sidesteps it. Always include it
> when rebuilding after pulling/copying new source, e.g.:
>
> ```bash
> cd /opt/whatsapp/whatsapp-mcp/whatsapp-bridge
> CGO_ENABLED=1 go build -buildvcs=false -o whatsapp-bridge .
> chown whatsapp:whatsapp whatsapp-bridge
> systemctl restart whatsapp-bridge
> ```

## 4. Link the WhatsApp number (one-time, interactive)

```bash
cd /opt/whatsapp/whatsapp-mcp/whatsapp-bridge
sudo -u whatsapp ./whatsapp-bridge
```

- In a browser open **`http://192.168.10.123:8080/qr`** and scan it with the phone →
  *Settings → Linked Devices → Link a Device*. (The QR also prints to the terminal;
  the web page is more reliable over SSH.)
- Confirm linked:

  ```bash
  curl -s http://192.168.10.123:8080/api/status      # should report authenticated
  ```

- Smoke-test a send to your own number:

  ```bash
  curl -s -X POST http://192.168.10.123:8080/api/send \
    -H 'Content-Type: application/json' \
    -d '{"recipient":"<your-number>","message":"bridge test"}'
  ```

- Press `Ctrl-C`. Credentials now persist in `whatsapp-bridge/store/whatsapp.db`.

## 5. systemd units (survive reboots)

`/etc/systemd/system/whatsapp-bridge.service`:

```ini
[Unit]
Description=WhatsApp Bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=whatsapp
WorkingDirectory=/opt/whatsapp/whatsapp-mcp/whatsapp-bridge
# Make the QR/status URLs report the container's reachable address instead of
# localhost. Set this to the LXC IP (and the bridge port). Optional but
# recommended on a remote host.
Environment=WHATSAPP_PUBLIC_URL=http://192.168.10.123:8080
ExecStart=/opt/whatsapp/whatsapp-mcp/whatsapp-bridge/whatsapp-bridge
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/whatsapp-mcp.service`:

```ini
[Unit]
Description=WhatsApp MCP server
After=whatsapp-bridge.service
Wants=whatsapp-bridge.service

[Service]
Type=simple
User=whatsapp
WorkingDirectory=/opt/whatsapp/whatsapp-mcp/whatsapp-mcp-server
Environment=MCP_TRANSPORT=sse
Environment=MCP_PORT=3000
ExecStart=/home/whatsapp/.local/bin/uv run main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

> ⚠️ The `WorkingDirectory` lines are **not optional**. The bridge stores its session in
> a `store/` folder relative to its working directory — without this, a restart begins in
> `/`, creates a fresh empty `store/`, and you'd have to re-scan the QR every reboot.

Enable and start:

```bash
systemctl daemon-reload
systemctl enable --now whatsapp-bridge whatsapp-mcp
journalctl -u whatsapp-bridge -n 20    # expect "Connected", REST server on :8080
```

If `ExecStart` fails, confirm uv's path: `sudo -u whatsapp which uv` and adjust.

## 6. Firewall — mandatory (the API has no auth)

The bridge binds all interfaces with **zero authentication**: anyone who can reach
`:8080` can send messages as this number and read local media. Restrict `8080` and
`3000` to your trusted subnet — via **Proxmox Datacenter → Firewall** rules on the
container, or inside the LXC:

```bash
apt install -y ufw
ufw allow from 192.168.10.0/24 to any port 8080 proto tcp
ufw allow from 192.168.10.0/24 to any port 3000 proto tcp
ufw enable
```

Adjust the source subnet to wherever your Claude host lives.

## 7. Add it to Claude Code

The MCP server speaks SSE on port `3000` at path `/sse`:

```bash
claude mcp add --transport sse --scope user whatsapp-billing http://192.168.10.123:3000/sse
```

- `--scope user` makes it available in every project (drop it to scope to the current
  directory; default scope is `local`).
- Verify: `claude mcp list` (or `/mcp` inside a session).
- Remove later: `claude mcp remove whatsapp-billing`.

**Result:**

- Bridge REST base: `http://192.168.10.123:8080`
- MCP SSE endpoint (for Claude): `http://192.168.10.123:3000/sse`

---

## Appendix: Two instances on a single host

If you ever want two bridges on the **same** box, use two separate checkouts and set
these env vars on the second instance's systemd units (defaults shown for the first):

| | Instance 1 | Instance 2 |
|---|---|---|
| Bridge port | `8080` (default) | `WHATSAPP_BRIDGE_PORT=8081` |
| MCP port | `MCP_PORT=3000` | `MCP_PORT=3001` |
| MCP → bridge URL | default | `WHATSAPP_API_BASE_URL=http://localhost:8081/api` |

The session store is per-working-directory, so two checkouts stay isolated
automatically. Firewall all four ports.
