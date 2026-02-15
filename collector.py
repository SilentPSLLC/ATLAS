#!/usr/bin/env python3
"""
ATLAS Collector — v2.1.0
Adaptive Telemetry & Live Analytics System
License: GPL v3 
Copyright (C) 2026S SilencePSLLC

Default: CPU, RAM, Disk only.
Enable more in /opt/Atlas/config/atlas.json.
You pay for what you collect.
"""

import os, sys, time, json, socket, platform, argparse, subprocess
from datetime import datetime, timezone

try:
    import psutil
except ImportError:
    print("[ATLAS] ERROR: psutil not found. Run: sudo apt install python3-psutil")
    sys.exit(1)

BASE_DIR    = "/opt/Atlas"
CACHE_FILE  = os.path.join(BASE_DIR, "cache",  "stats.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config", "atlas.json")
DB_FILE     = os.path.join(BASE_DIR, "data",   "atlas.db")

for d in ("cache", "config", "data"):
    os.makedirs(os.path.join(BASE_DIR, d), exist_ok=True)

DEFAULT_CONFIG = {
    # ── On by default ─────────────────────────────────────────────────────────
    "collect_cpu":        True,
    "collect_ram":        True,
    "collect_disk":       True,
    # ── Off by default — enable what you need ─────────────────────────────────
    "collect_network":    False,   # adds ~1s per cycle for speed sampling
    "collect_temp":       False,
    "collect_uptime":     False,
    "collect_os":         False,
    "collect_hardware":   False,   # slow — requires dmidecode
    "collect_processes":  False,   # CPU spike per cycle
    "collect_users":      False,
    "collect_battery":    False,
    "collect_gpu":        False,   # requires nvidia-smi or vcgencmd
    # ── Network sub-option ────────────────────────────────────────────────────
    "net_speed_enabled":  True,    # False = totals only, saves 1s per cycle
    # ── Timing ────────────────────────────────────────────────────────────────
    "interval":           30,
    # ── History ───────────────────────────────────────────────────────────────
    "history_enabled":    False,
    "history_keep_days":  7,
    # ── API (read by api.py) ──────────────────────────────────────────────────
    "api_engine":         "http",  # "http" | "flask" | "off"
    "api_port":           19890,
    "api_key":            "",
    "api_enabled":        True,
}


def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                cfg.update(json.load(f))
        except Exception as e:
            print(f"[ATLAS] Config error: {e} — using defaults")
    return cfg


def init_config():
    if not os.path.exists(CONFIG_FILE):
        import secrets, string
        cfg = DEFAULT_CONFIG.copy()
        cfg["api_key"] = "atl_" + "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(44))
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
        print(f"[ATLAS] Config created: {CONFIG_FILE}")
        print(f"[ATLAS] API Key: {cfg['api_key']}")
    return load_config()


# ── Collectors ────────────────────────────────────────────────────────────────

def collect_cpu():
    try:
        freq = psutil.cpu_freq()
        return {
            "percent":          round(psutil.cpu_percent(interval=1), 1),
            "percent_per_core": [round(x, 1) for x in
                                 psutil.cpu_percent(percpu=True, interval=0)],
            "cores_logical":    psutil.cpu_count(logical=True),
            "cores_physical":   psutil.cpu_count(logical=False),
            "model":            platform.processor() or _cpu_model(),
            "architecture":     platform.machine(),
            "freq_mhz_current": round(freq.current, 1) if freq else None,
            "freq_mhz_max":     round(freq.max,     1) if freq else None,
        }
    except Exception as e:
        return {"error": str(e)}


def _cpu_model():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
                if line.lower().startswith("hardware"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return "Unknown"


def collect_ram():
    try:
        vm   = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            "percent":       round(vm.percent,         1),
            "total_gb":      round(vm.total     / 1e9, 2),
            "used_gb":       round(vm.used      / 1e9, 2),
            "free_gb":       round(vm.available / 1e9, 2),
            "cached_gb":     round(getattr(vm, "cached", 0) / 1e9, 2),
            "swap_total_gb": round(swap.total   / 1e9, 2),
            "swap_used_gb":  round(swap.used    / 1e9, 2),
            "swap_percent":  round(swap.percent,       1),
        }
    except Exception as e:
        return {"error": str(e)}


def collect_disk():
    try:
        partitions = []
        for part in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(part.mountpoint)
                partitions.append({
                    "device":     part.device,
                    "mountpoint": part.mountpoint,
                    "fstype":     part.fstype,
                    "percent":    round(u.percent, 1),
                    "total_gb":   round(u.total / 1e9, 2),
                    "used_gb":    round(u.used  / 1e9, 2),
                    "free_gb":    round(u.free  / 1e9, 2),
                })
            except PermissionError:
                pass
        io = psutil.disk_io_counters()
        return {
            "partitions":  partitions,
            "io_read_mb":  round(io.read_bytes  / 1e6, 1) if io else None,
            "io_write_mb": round(io.write_bytes / 1e6, 1) if io else None,
        }
    except Exception as e:
        return {"error": str(e)}


def collect_network(speed=True):
    try:
        result = {}
        if speed:
            n1 = psutil.net_io_counters(); time.sleep(1); n2 = psutil.net_io_counters()
            result["speed_up_mbps"] = round((n2.bytes_sent - n1.bytes_sent) * 8 / 1e6, 3)
            result["speed_dn_mbps"] = round((n2.bytes_recv - n1.bytes_recv) * 8 / 1e6, 3)
        else:
            n2 = psutil.net_io_counters()
        result.update({
            "sent_total_mb": round(n2.bytes_sent / 1e6, 1),
            "recv_total_mb": round(n2.bytes_recv / 1e6, 1),
            "packets_sent":  n2.packets_sent,
            "packets_recv":  n2.packets_recv,
            "errors_in":     n2.errin,
            "errors_out":    n2.errout,
        })
        interfaces = []
        st = psutil.net_if_stats()
        for iface, addrs in psutil.net_if_addrs().items():
            info = {"name": iface, "addresses": [], "is_up": False}
            if iface in st:
                info["is_up"]      = st[iface].isup
                info["speed_mbps"] = st[iface].speed or None
                info["mtu"]        = st[iface].mtu
            for a in addrs:
                e = {"family": str(a.family), "address": a.address}
                if a.netmask:   e["netmask"]   = a.netmask
                if a.broadcast: e["broadcast"] = a.broadcast
                info["addresses"].append(e)
            interfaces.append(info)
        result["interfaces"] = interfaces
        return result
    except Exception as e:
        return {"error": str(e)}


def collect_temperature():
    try:
        result = {}
        try:
            s = psutil.sensors_temperatures()
            if s:
                for name, entries in s.items():
                    result[name] = [{"label": e.label or name,
                                     "current": round(e.current, 1),
                                     "high": round(e.high, 1) if e.high else None,
                                     "critical": round(e.critical, 1) if e.critical else None}
                                    for e in entries]
        except AttributeError:
            pass
        if not result and os.path.exists("/sys/class/thermal"):
            zones = []
            for zone in os.listdir("/sys/class/thermal"):
                try:
                    tp = f"/sys/class/thermal/{zone}/temp"
                    tt = f"/sys/class/thermal/{zone}/type"
                    if os.path.exists(tp):
                        with open(tp) as f: temp = int(f.read().strip()) / 1000.0
                        label = open(tt).read().strip() if os.path.exists(tt) else zone
                        zones.append({"label": label, "current": round(temp, 1)})
                except Exception:
                    pass
            if zones: result["thermal_zones"] = zones
        return result or {"note": "No sensors detected"}
    except Exception as e:
        return {"error": str(e)}


def collect_uptime():
    try:
        s = int(time.time() - psutil.boot_time())
        return {
            "uptime_seconds": s,
            "uptime_human":   f"{s//86400}d {(s%86400)//3600:02d}h {(s%3600)//60:02d}m {s%60:02d}s",
            "boot_time":      datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc).isoformat(),
        }
    except Exception as e:
        return {"error": str(e)}


def collect_os():
    try:
        info = {"system": platform.system(), "node": platform.node(),
                "release": platform.release(), "machine": platform.machine(),
                "hostname": socket.gethostname(), "fqdn": socket.getfqdn()}
        if os.path.exists("/etc/os-release"):
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        info["distro_name"] = line.split("=",1)[1].strip().strip('"')
                    if line.startswith("VERSION_ID="):
                        info["distro_version"] = line.split("=",1)[1].strip().strip('"')
        return info
    except Exception as e:
        return {"error": str(e)}


def collect_hardware():
    try:
        info = {}
        for dmi, key in [("system-manufacturer","manufacturer"),
                         ("system-product-name","product_name"),
                         ("system-serial-number","serial_number"),
                         ("system-uuid","uuid"),
                         ("bios-vendor","bios_vendor"),
                         ("bios-version","bios_version"),
                         ("chassis-type","chassis_type")]:
            try:
                r = subprocess.run(["dmidecode","-s",dmi], capture_output=True, text=True, timeout=3)
                v = r.stdout.strip()
                if v and "not present" not in v.lower(): info[key] = v
            except Exception: pass
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    for k,v in [("Model","rpi_model"),("Serial","rpi_serial"),("Revision","rpi_revision")]:
                        if line.startswith(k):
                            info[v] = line.split(":",1)[1].strip()
        except Exception: pass
        return info or {"note": "Limited — dmidecode may need sudo"}
    except Exception as e:
        return {"error": str(e)}


def collect_processes():
    try:
        procs = []
        for p in psutil.process_iter(["pid","name","username","cpu_percent","memory_percent","status"]):
            try: procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied): pass
        fmt = lambda p: {"pid": p.get("pid"), "name": p.get("name"),
                         "user": p.get("username"),
                         "cpu_pct": round(p.get("cpu_percent") or 0, 2),
                         "mem_pct": round(p.get("memory_percent") or 0, 2),
                         "status": p.get("status")}
        return {
            "total":   len(procs),
            "running": sum(1 for p in procs if p.get("status") == "running"),
            "top_cpu": [fmt(p) for p in sorted(procs, key=lambda x: x.get("cpu_percent") or 0, reverse=True)[:5]],
            "top_mem": [fmt(p) for p in sorted(procs, key=lambda x: x.get("memory_percent") or 0, reverse=True)[:5]],
        }
    except Exception as e:
        return {"error": str(e)}


def collect_users():
    try:
        return {"logged_in": [{"name": u.name, "terminal": u.terminal, "host": u.host,
                "started": datetime.fromtimestamp(u.started, tz=timezone.utc).isoformat()}
                for u in psutil.users()], "count": len(psutil.users())}
    except Exception as e:
        return {"error": str(e)}


def collect_battery():
    try:
        b = psutil.sensors_battery()
        if not b: return {"present": False}
        return {"present": True, "percent": round(b.percent, 1),
                "plugged_in": b.power_plugged,
                "time_left_sec": b.secsleft if b.secsleft != psutil.POWER_TIME_UNLIMITED else None}
    except Exception as e:
        return {"error": str(e)}


def collect_gpu():
    try:
        r = subprocess.run(["nvidia-smi","--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu","--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            gpus = []
            for line in r.stdout.strip().splitlines():
                p = [x.strip() for x in line.split(",")]
                if len(p) >= 5:
                    gpus.append({"name": p[0], "util_percent": float(p[1]) if p[1] else None,
                                 "mem_used_mb": float(p[2]) if p[2] else None,
                                 "mem_total_mb": float(p[3]) if p[3] else None,
                                 "temp_celsius": float(p[4]) if p[4] else None, "driver": "nvidia"})
            return {"gpus": gpus}
        r = subprocess.run(["vcgencmd","get_mem","gpu"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            th = subprocess.run(["vcgencmd","get_throttled"], capture_output=True, text=True, timeout=3)
            return {"gpus": [{"name": "VideoCore (RPi)", "gpu_mem": r.stdout.strip(),
                               "throttled": th.stdout.strip() if th.returncode == 0 else None,
                               "driver": "videocore"}]}
        return {"gpus": [], "note": "No GPU detected"}
    except FileNotFoundError:
        return {"gpus": [], "note": "No GPU tools found"}
    except Exception as e:
        return {"error": str(e)}


# ── Collection orchestrator ───────────────────────────────────────────────────

def collect_all(cfg):
    stats = {"atlas_version": "2.1.0",
             "collected_at":  datetime.now(timezone.utc).isoformat(),
             "hostname":      socket.gethostname()}
    if cfg.get("collect_cpu",       True):  stats["cpu"]         = collect_cpu()
    if cfg.get("collect_ram",       True):  stats["ram"]         = collect_ram()
    if cfg.get("collect_disk",      True):  stats["disk"]        = collect_disk()
    if cfg.get("collect_network",   False): stats["network"]     = collect_network(cfg.get("net_speed_enabled", True))
    if cfg.get("collect_temp",      False): stats["temperature"] = collect_temperature()
    if cfg.get("collect_uptime",    False): stats["uptime"]      = collect_uptime()
    if cfg.get("collect_os",        False): stats["os"]          = collect_os()
    if cfg.get("collect_hardware",  False): stats["hardware"]    = collect_hardware()
    if cfg.get("collect_processes", False): stats["processes"]   = collect_processes()
    if cfg.get("collect_users",     False): stats["users"]       = collect_users()
    if cfg.get("collect_battery",   False): stats["battery"]     = collect_battery()
    if cfg.get("collect_gpu",       False): stats["gpu"]         = collect_gpu()
    return stats


def write_cache(stats):
    tmp = CACHE_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(stats, f, indent=2)
        os.replace(tmp, CACHE_FILE)
    except Exception as e:
        print(f"[ATLAS] Cache write error: {e}")


def write_history(stats, keep_days):
    import sqlite3
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("""CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT, collected_at TEXT NOT NULL,
            hostname TEXT, cpu_percent REAL, ram_percent REAL,
            disk_percent REAL, raw_json TEXT)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON snapshots(collected_at)")
        parts    = stats.get("disk", {}).get("partitions", [{}])
        disk_pct = parts[0].get("percent") if parts else None
        conn.execute("INSERT INTO snapshots (collected_at,hostname,cpu_percent,ram_percent,disk_percent,raw_json) VALUES (?,?,?,?,?,?)",
                     (stats.get("collected_at"), stats.get("hostname"),
                      stats.get("cpu",{}).get("percent"), stats.get("ram",{}).get("percent"),
                      disk_pct, json.dumps(stats)))
        conn.execute("DELETE FROM snapshots WHERE collected_at < datetime('now', ?)", (f"-{keep_days} days",))
        conn.commit(); conn.close()
    except Exception as e:
        print(f"[ATLAS] History error: {e}")


def install_service(user):
    script = os.path.abspath(__file__)
    svc = f"""[Unit]
Description=ATLAS Collector — Adaptive Telemetry & Live Analytics System
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory=/home/{user}
ExecStart=/usr/bin/python3 {script}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
    try:
        with open("/etc/systemd/system/atlas-collector.service", "w") as f: f.write(svc)
        subprocess.run(["systemctl","daemon-reload"], check=True)
        subprocess.run(["systemctl","enable","atlas-collector"], check=True)
        subprocess.run(["systemctl","start","atlas-collector"], check=True)
        print(f"\n  ✓ atlas-collector service installed\n")
    except PermissionError:
        print("\n  ✗ Run with sudo\n")
    except Exception as e:
        print(f"\n  ✗ {e}\n")


def main():
    parser = argparse.ArgumentParser(description="ATLAS Collector v2.1.0")
    parser.add_argument("--once",            action="store_true")
    parser.add_argument("--install-service", action="store_true")
    parser.add_argument("--user",   default="pi")
    parser.add_argument("--interval", type=int)
    args = parser.parse_args()

    if args.install_service:
        install_service(args.user)
        sys.exit(0)

    cfg = init_config()
    if args.interval: cfg["interval"] = args.interval

    enabled = [k.replace("collect_","") for k,v in cfg.items() if k.startswith("collect_") and v]
    print(f"[ATLAS] Collector v2.1.0")
    print(f"[ATLAS] Collecting: {', '.join(enabled)}")
    print(f"[ATLAS] Interval:   {cfg['interval']}s  |  History: {'on' if cfg.get('history_enabled') else 'off'}")

    while True:
        start = time.time()
        try:
            stats = collect_all(cfg)
            write_cache(stats)
            if cfg.get("history_enabled"):
                write_history(stats, cfg.get("history_keep_days", 7))
            cpu = stats.get("cpu",{}).get("percent","-")
            ram = stats.get("ram",{}).get("percent","-")
            dsk = (stats.get("disk",{}).get("partitions") or [{}])[0].get("percent","-")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] CPU:{cpu}%  RAM:{ram}%  DISK:{dsk}%")
        except Exception as e:
            print(f"[ATLAS] Error: {e}")
        if args.once: break
        time.sleep(max(0, cfg["interval"] - (time.time() - start)))


if __name__ == "__main__":
    main()
