# Running on Proxmox

This sets up the WhatsApp bridge and MCP server in a small Proxmox LXC
container. No Docker is needed. `install.sh` installs everything and sets both
services up to start on boot. `update.sh` updates them later.

You end up with:

- the bridge on port `8080` (status page, QR code page, REST API)
- the MCP server on port `3000` (Claude connects to `http://<container-ip>:3000/sse`)

## 1. Create the container

In the Proxmox web UI, click **Create CT**:

| Tab | Setting |
|---|---|
| General | Pick a hostname. Leave **Unprivileged container** ticked. Set a **Password**: this is the container's root password, used to log in on its console. |
| Template | A **Debian 12** standard template. If none is listed, download one first: select your storage, then **CT Templates > Templates**. |
| Disks | 8 GB |
| CPU | 1 to 2 cores |
| Memory | 1024 MB |
| Network | A static IPv4 address on your LAN, e.g. `192.0.2.10/24`, plus the gateway. A fixed address means Claude's URL never changes. |

Finish, then select the container and click **Start**. Under **Options**, set
**Start at boot** to Yes.

If you forgot the password, `install.sh` asks for one when it sees that root
has none.

## 2. Run the installer

Open the container's **Console** in Proxmox, log in as `root`, and run:

```bash
apt-get update && apt-get install -y curl
curl -fsSL https://raw.githubusercontent.com/biovolt/whatsapp-mcp/main/install.sh | bash
```

It takes a few minutes. The installer:

1. asks for a root password if root has none yet
2. installs `git`, a C compiler, `ffmpeg` and `curl` with apt
3. installs Go and `uv` (the versions are pinned in `install.sh`, and the Go
   download is checked against its published checksum)
4. creates a `whatsapp` user and clones this repository to
   `/opt/whatsapp/whatsapp-mcp`
5. writes the settings file `/etc/default/whatsapp-mcp`
6. creates and enables the `whatsapp-bridge` and `whatsapp-mcp` systemd services
7. builds the bridge, starts both services, and prints the URLs

Running it again is safe. Steps that are already done are skipped, and your
settings file is left alone. On a machine where the bridge service was set up
by hand, `install.sh` stops without changing anything; use `update.sh` there.

## 3. Link your phone

Open `http://<container-ip>:8080/qr` in a browser. On the phone, open WhatsApp,
go to **Settings > Linked devices > Link a device**, and scan the code.

The code on the page changes every 20 seconds or so. If nobody scans it for a
few minutes, the bridge stops offering new codes, the page keeps showing the
last one (which no longer works), and a few minutes later the bridge restarts
with fresh codes. So if scanning fails, wait a few minutes and reload the page.

Check that it worked:

```bash
curl -s http://<container-ip>:8080/api/status
```

The output should contain `"connected":true`. The login is kept in
`/opt/whatsapp/whatsapp-mcp/whatsapp-bridge/store/`, so it survives restarts
and reboots.

## 4. Connect Claude

On the computer where you use Claude Code:

```bash
claude mcp add --transport sse --scope user whatsapp http://<container-ip>:3000/sse
```

Check it with `claude mcp list`, or with `/mcp` inside Claude Code.

## 5. Firewall (do not skip)

Neither the bridge nor the MCP server asks for a password. Anyone who can reach
ports `8080` or `3000` can read your messages and send new ones as your number.
Allow only your own network to reach them.

In Proxmox:

1. **Datacenter > Firewall > Options**: set **Firewall** to Yes. Add a rule that
   allows port 8006 from your network first, so you can't lock yourself out of
   the Proxmox UI.
2. On the container, **Network**: edit `net0` and tick **Firewall**.
3. On the container, **Firewall > Add**, once for each port: direction `in`,
   action `ACCEPT`, protocol `tcp`, source your LAN (e.g. `192.0.2.0/24`), and
   destination port `8080` or `3000`. Add a third rule for port `22` if you use
   SSH.
4. On the container, **Firewall > Options**: set **Firewall** to Yes and
   **Input Policy** to `DROP`.

## Updating

Log in to the container as root and run:

```bash
/opt/whatsapp/whatsapp-mcp/update.sh
```

It pulls the latest code, rebuilds the bridge, refreshes the MCP server's Python
packages, restarts both services, and waits until the bridge reports that it is
connected. Restarting the services is not enough: they keep running the old
build until you rebuild.

## Settings

All settings live in `/etc/default/whatsapp-mcp`:

| Setting | Default | What it does |
|---|---|---|
| `WHATSAPP_PUBLIC_URL` | `http://<container-ip>:8080` | The address shown on the QR and status pages |
| `WHATSAPP_BRIDGE_PORT` | `8080` | The bridge's port |
| `WHATSAPP_WEBHOOK_URL` | not set | If set, every incoming message is POSTed to this URL |
| `MCP_TRANSPORT` | `sse` | How Claude talks to the MCP server |
| `MCP_PORT` | `3000` | The MCP server's port |
| `WHATSAPP_API_BASE_URL` | `http://localhost:8080/api` | Where the MCP server finds the bridge |
| `WHATSAPP_BRIDGE_AUTOSTART` | `0` | `0` stops the MCP server from starting its own bridge (systemd runs it) |

After you change something, run
`systemctl restart whatsapp-bridge whatsapp-mcp`. If you change a port, also
change `WHATSAPP_PUBLIC_URL` and `WHATSAPP_API_BASE_URL` to match.

## Troubleshooting

| What you see | What to run |
|---|---|
| Logs | `journalctl -u whatsapp-bridge -n 50` or `journalctl -u whatsapp-mcp -n 50` |
| Whether the services are running | `systemctl status whatsapp-bridge whatsapp-mcp` |
| `Client outdated (405)` in the bridge log | WhatsApp no longer accepts this bridge version. Run `update.sh`. If that doesn't fix it, the whatsmeow library in `whatsapp-bridge/go.mod` needs upgrading. |
| You get asked to scan the QR code again after every restart | The bridge is not running from its own directory. Check that `WorkingDirectory` in `/etc/systemd/system/whatsapp-bridge.service` points at `.../whatsapp-bridge`. |

## Two numbers in one container

Use two checkouts, each with its own ports. For the second one, copy the two
service files under new names. Point them at the second checkout and a second
settings file that sets `WHATSAPP_BRIDGE_PORT=8081`, `MCP_PORT=3001` and
`WHATSAPP_API_BASE_URL=http://localhost:8081/api`. Each checkout keeps its own
login in its own `store/` folder. Two separate containers are simpler, though.
To make a second one, just repeat this guide.
