# ATLAS
### Adaptive Telemetry & Live Analytics System
> "Everyone else is a commercial kitchen. ATLAS is a good chef's knife."

ATLAS is a lightweight, zero-dependency system telemetry agent for Linux. Install it on any machine and instantly get a complete, structured snapshot of everything about that machine — queryable by CLI, `curl`, or any HTTP client.

No server required. No account. No cloud. No pipeline to configure. Just a machine that knows everything about itself and will tell anyone who asks.

---

## Why ATLAS

Tools like Prometheus, OpenTelemetry, and Telegraf are powerful — but they assume you have somewhere to send data. A collector pipeline. A metrics backend. A Grafana instance. They're built for infrastructure teams running full observability stacks.

ATLAS is built for everyone else.

- A sysadmin who wants to `curl` a remote machine and get its full hardware inventory
- A developer who wants structured system data without writing their own psutil wrappers
- An MSP tech who needs CPU, RAM, disk, and serial numbers from a client machine right now
- Anyone who wants a machine to be observable by anything — a script, an RMM, a cron job, a dashboard they haven't built yet

ATLAS collects. You decide what to do with the data.

---

## Quick Start
```bash
# 1. Create the directory structure
sudo mkdir -p /opt/Atlas/{cache,config,data}

# 2. Clone the repo into /opt/Atlas
sudo git clone https://github.com/SilencePSLLC/atlas.git /opt/Atlas

# 3. Set ownership
sudo chown -R $USER:$USER /opt/Atlas

# 4. Install dependency
sudo apt install -y python3-psutil

# 5. Run the collector once to generate config and API key
python3 /opt/Atlas/collector.py --once

# 6. Install CLI command
sudo ln -sf /opt/Atlas/cli.py /usr/local/bin/atlas-stats
sudo chmod +x /usr/local/bin/atlas-stats
```

Your API key is displayed on first run and saved to `/opt/Atlas/config/atlas.json`.

To start the API:
```bash
python3 /opt/Atlas/api.py &
```

## Install as Services (auto-start on boot)
```bash
sudo python3 /opt/Atlas/collector.py --install-service --user YOUR_USERNAME
sudo python3 /opt/Atlas/api.py --install-service --user YOUR_USERNAME
```

Check status:
```bash
systemctl status atlas-collector
systemctl status atlas-api
```

---

## CLI Usage
```bash
atlas-stats                          # Full dashboard
atlas-stats --watch                  # Live refresh (default: 30s)
atlas-stats --watch --interval 5     # Refresh every 5s
atlas-stats --section cpu            # CPU only
atlas-stats --section ram            # Memory only
atlas-stats --section disk           # Disk partitions
atlas-stats --section network        # Network interfaces + speed
atlas-stats --section hardware       # Manufacturer, serials, BIOS
atlas-stats --section processes      # Top processes by CPU and RAM
atlas-stats --section temperature    # All temperature sensors
atlas-stats --section users          # Logged in users
atlas-stats --section battery        # Battery status
atlas-stats --section gpu            # GPU (NVIDIA or RPi VideoCore)
atlas-stats --json                   # Full raw JSON
atlas-stats --json --section cpu     # Single section as JSON
atlas-stats --json | python3 -m json.tool  # Pretty-printed JSON
```

---

## API Usage

ATLAS runs a minimal HTTP API on port `19890` (configurable).
All endpoints except `/api/ping` require the API key generated at first run.

**Auth:** `X-ATLAS-Key` header or `?key=` query param.

| Endpoint | Auth | Description |
|---|---|---|
| `GET /api/ping` | No | Health check |
| `GET /api/stats` | Yes | Full snapshot |
| `GET /api/stats/<section>` | Yes | Single section |
| `GET /api/history` | Yes | Historical snapshots (if enabled) |
```bash
# Health check
curl http://192.168.1.100:19890/api/ping

# Full snapshot
curl -H "X-ATLAS-Key: atl_yourkey" http://192.168.1.100:19890/api/stats

# Single section
curl -H "X-ATLAS-Key: atl_yourkey" http://192.168.1.100:19890/api/stats/cpu

# Pretty print
curl -s -H "X-ATLAS-Key: atl_yourkey" http://192.168.1.100:19890/api/stats \
  | python3 -m json.tool

# Query param alternative
curl "http://192.168.1.100:19890/api/stats?key=atl_yourkey"
```

Your API key is auto-generated on first run and saved to:
```
/opt/Atlas/config/atlas.json
```

---

## Configuration

`/opt/Atlas/config/atlas.json` — auto-generated on first run.
```json
{
  "collect_cpu":        true,
  "collect_ram":        true,
  "collect_disk":       true,
  "collect_network":    false,
  "collect_temp":       false,
  "collect_uptime":     false,
  "collect_os":         false,
  "collect_hardware":   false,
  "collect_processes":  false,
  "collect_users":      false,
  "collect_battery":    false,
  "collect_gpu":        false,

  "net_speed_enabled":  true,

  "interval":           30,

  "history_enabled":    false,
  "history_keep_days":  7,

  "api_engine":         "http",
  "api_port":           19890,
  "api_key":            "atl_auto_generated",
  "api_enabled":        true
}
```

**You pay for what you collect.** Only CPU, RAM, and Disk are on by default.
Enable any section by setting it to `true`. Restart the collector after changes:
```bash
sudo systemctl restart atlas-collector
```

---

## API Engines

Three options — set `api_engine` in `atlas.json`:

| Engine | Memory | Requirement | Best for |
|---|---|---|---|
| `"http"` | ~2MB | None (built-in) | Pi Zero, low-resource machines |
| `"flask"` | ~15MB | `pip install flask` | Servers, easier to extend |
| `"off"` | 0MB | — | Cache file only, no HTTP |

To use Flask engine:
```bash
sudo pip3 install flask --break-system-packages
```
Then set `"api_engine": "flask"` in `atlas.json` and restart `atlas-api`.

---

## What Gets Collected

| Section | Data | Default |
|---|---|---|
| `cpu` | percent, per-core, model, cores, frequency | ✓ On |
| `ram` | percent, used/total/free GB, swap | ✓ On |
| `disk` | per partition — percent, sizes, fstype, I/O | ✓ On |
| `network` | speed up/down, totals, per-interface IPs/MACs | Off |
| `temperature` | all sensor readings, RPi thermal zones | Off |
| `uptime` | seconds, human readable, boot time | Off |
| `os` | distro, kernel, hostname, architecture | Off |
| `hardware` | manufacturer, serial, UUID, BIOS, RPi model/serial | Off |
| `processes` | total count, top 5 CPU, top 5 memory | Off |
| `users` | currently logged in sessions | Off |
| `battery` | percent, plugged/unplugged, time remaining | Off |
| `gpu` | NVIDIA via nvidia-smi, RPi VideoCore via vcgencmd | Off |

---

## File Structure
```
/opt/Atlas/
├── collector.py        ← Collects stats, writes cache
├── api.py              ← HTTP API server
├── cli.py              ← Terminal dashboard (atlas-stats command)
├── config/
│   └── atlas.json      ← Configuration + API key
├── cache/
│   └── stats.json      ← Live snapshot (updated every N seconds)
└── data/
    └── atlas.db        ← SQLite history (if enabled)
```

---

## Services
```bash
# Status
systemctl status atlas-collector
systemctl status atlas-api

# Restart
sudo systemctl restart atlas-collector
sudo systemctl restart atlas-api

# Logs
journalctl -u atlas-collector -f
journalctl -u atlas-api -f

# Stop
sudo systemctl stop atlas-collector
sudo systemctl stop atlas-api
```

---

## Requirements

- Linux (Debian / Ubuntu / Raspberry Pi OS)
- Python 3.9+
- `python3-psutil`
- `flask` — optional, only needed for `api_engine: "flask"`

Optional for extended collection:
- `dmidecode` — hardware serials, BIOS info (needs sudo)
- `nvidia-smi` — NVIDIA GPU stats
- `vcgencmd` — Raspberry Pi GPU / throttle status

---

## History (SQLite)

Off by default. Enable in `atlas.json`:
```json
{
  "history_enabled":   true,
  "history_keep_days": 7
}
```

Query via API:
```bash
curl -H "X-ATLAS-Key: atl_yourkey" http://localhost:19890/api/history
curl -H "X-ATLAS-Key: atl_yourkey" "http://localhost:19890/api/history?limit=50"
```

---

## Tested On

- Raspberry Pi Zero 2W — Raspberry Pi OS Lite 64-bit
- Raspberry Pi 4 — Raspberry Pi OS Lite 64-bit
- Debian 12 (Trixie) — arm64

---

## Roadmap

- [ ] Windows support
- [ ] macOS support
- [ ] `curl | bash` one-liner installer

---

## Contributing

Issues and pull requests welcome at [github.com/SilencePSLLC/atlas](https://github.com/SilencePSLLC/atlas).

---

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).

ATLAS is free software. Modifications must remain open source under GPL v3.

---

*Copyright (C) 2026 SilencePSLLC*
