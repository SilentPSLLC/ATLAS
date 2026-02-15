#!/usr/bin/env python3
"""
ATLAS CLI — v2.0.0
Automated Telemetry & Local Administration System
License: GPL v3 
Copyright (C) 2026 SilencePSLLC


Reads the stats cache and displays a clean terminal dashboard.

Usage:
  atlas-stats                    One-shot display
  atlas-stats --watch            Live refresh (default 30s)
  atlas-stats --watch --interval 5
  atlas-stats --section cpu      Show one section only
  atlas-stats --json             Raw JSON dump
  atlas-stats --json --section disk
"""

import os, sys, json, time, argparse
from datetime import datetime, timezone

CACHE_FILE = "/opt/Atlas/cache/stats.json"

# ─── ANSI ─────────────────────────────────────────────────────────────────────
RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
RED   = "\033[91m"
YLW   = "\033[93m"
GRN   = "\033[92m"
CYN   = "\033[96m"
BLU   = "\033[94m"
WHT   = "\033[97m"
MGN   = "\033[95m"

def color_supported():
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def c(col, txt):
    return f"{col}{txt}{RESET}" if color_supported() else txt

def bar(pct, width=24):
    pct    = max(0.0, min(100.0, float(pct or 0)))
    filled = int((pct / 100.0) * width)
    empty  = width - filled
    col    = RED if pct >= 90 else YLW if pct >= 75 else GRN
    inner  = c(col, "█" * filled) + c(DIM, "░" * empty)
    return c(DIM, "[") + inner + c(DIM, "]")

def pct_col(pct):
    pct = float(pct or 0)
    col = RED if pct >= 90 else YLW if pct >= 75 else GRN
    return c(col + BOLD, f"{pct:5.1f}%")

def fmt_bytes(mb):
    if mb is None: return "N/A"
    if mb < 1000:  return f"{mb:.1f} MB"
    return f"{mb/1000:.2f} GB"

def fmt_net(mbps):
    if not mbps: return "0 Kbps"
    if mbps < 1: return f"{mbps*1000:.0f} Kbps"
    return f"{mbps:.2f} Mbps"

def fmt_age(iso):
    try:
        ts  = datetime.fromisoformat(iso)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        diff = int((datetime.now(timezone.utc) - ts).total_seconds())
        if diff <   60: return f"{diff}s ago"
        if diff < 3600: return f"{diff//60}m ago"
        return f"{diff//3600}h ago"
    except Exception:
        return "unknown"

def divider(width=56, char="─"):
    return c(BLU, "  " + char * width)

def section_header(title):
    return c(BLU, "  ┤ ") + c(WHT + BOLD, title) + c(BLU, " ├")

def load_cache(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


# ═════════════════════════════════════════════════════════════════════════════
# Section printers
# ═════════════════════════════════════════════════════════════════════════════

def print_header(stats):
    hostname  = stats.get("hostname", "unknown")
    age       = fmt_age(stats.get("collected_at", ""))
    version   = stats.get("atlas_version", "?")
    os_data   = stats.get("os", {})
    os_str    = f"{os_data.get('distro_name', os_data.get('system',''))} {os_data.get('release','')}"

    print()
    print(divider(56, "═"))
    print(c(BLU, "  ║ ") + c(CYN + BOLD, " ⬡  ATLAS") +
          c(DIM, f" v{version}") +
          c(BLU, "  ─  ") +
          c(WHT + BOLD, hostname.upper()))
    if os_str.strip():
        print(c(BLU, "  ║ ") + c(DIM, f"    {os_str.strip()}"))
    print(c(BLU, "  ║ ") + c(DIM, f"    Cache: {age}  |  SilencePSLLC"))
    print(divider(56, "═"))


def print_cpu(cpu):
    if not cpu or cpu.get("enabled") is False: return
    print()
    print(section_header("CPU"))
    pct   = cpu.get("percent", 0)
    cores = cpu.get("cores_logical", "?")
    model = cpu.get("model", "Unknown")[:40]
    freq  = cpu.get("freq_mhz_current")
    print(f"  {bar(pct)} {pct_col(pct)}" +
          c(DIM, f"  {cores} cores" + (f"  {freq:.0f} MHz" if freq else "")))
    print(c(DIM, f"    {model}"))

    per_core = cpu.get("percent_per_core", [])
    if per_core and len(per_core) > 1:
        row = "    "
        for i, p in enumerate(per_core):
            col = RED if p >= 90 else YLW if p >= 75 else GRN
            row += c(col, f"C{i}:{p:.0f}%") + "  "
        print(row)


def print_ram(ram):
    if not ram or ram.get("enabled") is False: return
    print()
    print(section_header("MEMORY"))
    pct   = ram.get("percent", 0)
    used  = ram.get("used_gb", 0)
    total = ram.get("total_gb", 0)
    free  = ram.get("free_gb", 0)
    print(f"  {bar(pct)} {pct_col(pct)}" +
          c(DIM, f"  {used:.2f} / {total:.2f} GB  (free: {free:.2f} GB)"))

    swap_pct  = ram.get("swap_percent", 0)
    swap_used = ram.get("swap_used_gb", 0)
    swap_tot  = ram.get("swap_total_gb", 0)
    if swap_tot > 0:
        print(f"  {bar(swap_pct)} {pct_col(swap_pct)}" +
              c(DIM, f"  SWAP  {swap_used:.2f} / {swap_tot:.2f} GB"))


def print_disk(disk):
    if not disk or disk.get("enabled") is False: return
    print()
    print(section_header("DISK"))
    for part in disk.get("partitions", []):
        pct   = part.get("percent", 0)
        used  = part.get("used_gb", 0)
        total = part.get("total_gb", 0)
        mnt   = part.get("mountpoint", "?")
        fs    = part.get("fstype", "")
        dev   = part.get("device", "")
        print(f"  {bar(pct)} {pct_col(pct)}" +
              c(DIM, f"  {used:.1f}/{total:.1f}GB") +
              c(WHT, f"  {mnt}") +
              c(DIM, f"  {fs}"))

    io_r = disk.get("io_read_mb")
    io_w = disk.get("io_write_mb")
    if io_r is not None:
        print(c(DIM, f"    I/O — Read: {fmt_bytes(io_r)}  Write: {fmt_bytes(io_w)}"))


def print_network(net):
    if not net or net.get("enabled") is False: return
    print()
    print(section_header("NETWORK"))
    up  = net.get("speed_up_mbps", 0)
    dn  = net.get("speed_dn_mbps", 0)
    print(f"  {c(GRN+BOLD,'↑')} {c(GRN, fmt_net(up)):<16}"
          f"  {c(CYN+BOLD,'↓')} {c(CYN, fmt_net(dn))}")
    sent = net.get("sent_total_mb", 0)
    recv = net.get("recv_total_mb", 0)
    erri = net.get("errors_in",  0)
    erro = net.get("errors_out", 0)
    print(c(DIM, f"    Total sent: {fmt_bytes(sent)}  recv: {fmt_bytes(recv)}"
           f"  errors: {erri}/{erro}"))
    for iface in net.get("interfaces", []):
        if not iface.get("is_up"): continue
        addrs = [a["address"] for a in iface.get("addresses", [])
                 if ":" not in a["address"] and not a["address"].startswith("127")]
        if addrs:
            speed = iface.get("speed_mbps")
            print(c(DIM, f"    {iface['name']:<12}") +
                  c(WHT, "  ".join(addrs[:2])) +
                  c(DIM, f"  {speed}Mbps" if speed else ""))


def print_temperature(temp):
    if not temp or temp.get("enabled") is False: return
    readings = []
    for key, val in temp.items():
        if key in ("enabled", "note", "error"): continue
        if isinstance(val, list):
            for entry in val:
                readings.append((entry.get("label", key), entry.get("current", 0)))
        elif isinstance(val, dict) and "current" in val:
            readings.append((val.get("label", key), val["current"]))
    if not readings: return
    print()
    print(section_header("TEMPERATURE"))
    for label, deg in readings:
        col = RED if deg > 75 else YLW if deg > 60 else GRN
        bar_pct = min(100, (deg / 85.0) * 100)
        print(f"  {bar(bar_pct)} " +
              c(col + BOLD, f"{deg:5.1f}°C") +
              c(DIM, f"  {label}"))


def print_uptime(uptime):
    if not uptime or uptime.get("enabled") is False: return
    print()
    print(section_header("UPTIME"))
    print(c(DIM, f"    {uptime.get('uptime_human','?')}") +
          c(DIM, f"   (boot: {uptime.get('boot_time','?')[:19].replace('T',' ')})"))


def print_os(os_data):
    if not os_data or os_data.get("enabled") is False: return
    print()
    print(section_header("OS"))
    fields = [
        ("Hostname",     os_data.get("hostname")),
        ("OS",           os_data.get("distro_name") or os_data.get("system")),
        ("Kernel",       os_data.get("release")),
        ("Architecture", os_data.get("machine")),
        ("Python",       os_data.get("python")),
    ]
    for label, val in fields:
        if val:
            print(c(DIM, f"    {label:<14}") + c(WHT, str(val)))


def print_hardware(hw):
    if not hw or hw.get("enabled") is False: return
    skip = {"enabled", "note", "error", "mac_addresses"}
    items = {k: v for k, v in hw.items() if k not in skip and v}
    if not items and not hw.get("mac_addresses"): return
    print()
    print(section_header("HARDWARE"))
    labels = {
        "manufacturer":    "Manufacturer",
        "product_name":    "Product",
        "serial_number":   "Serial",
        "uuid":            "UUID",
        "board_product":   "Board",
        "board_serial":    "Board Serial",
        "bios_vendor":     "BIOS",
        "bios_version":    "BIOS Ver",
        "bios_date":       "BIOS Date",
        "chassis_type":    "Chassis",
        "rpi_model":       "RPi Model",
        "rpi_serial":      "RPi Serial",
        "rpi_revision":    "RPi Revision",
    }
    for key, label in labels.items():
        val = hw.get(key)
        if val:
            print(c(DIM, f"    {label:<16}") + c(WHT, str(val)))
    macs = hw.get("mac_addresses", {})
    for iface, mac in macs.items():
        print(c(DIM, f"    MAC {iface:<12}") + c(WHT, mac))


def print_processes(procs):
    if not procs or procs.get("enabled") is False: return
    print()
    print(section_header("PROCESSES"))
    total   = procs.get("total",   0)
    running = procs.get("running", 0)
    print(c(DIM, f"    Total: ") + c(WHT, str(total)) +
          c(DIM, "   Running: ") + c(WHT, str(running)))

    top_cpu = procs.get("top_cpu", [])
    if top_cpu:
        print(c(DIM, "\n    Top CPU:"))
        for p in top_cpu:
            print(c(DIM, f"      {p.get('pid',0):>6}  ") +
                  c(YLW, f"{p.get('cpu_pct',0):5.1f}%  ") +
                  c(WHT, f"{p.get('name','?'):<24}") +
                  c(DIM, f"  {p.get('user','?')}"))

    top_mem = procs.get("top_mem", [])
    if top_mem:
        print(c(DIM, "\n    Top Memory:"))
        for p in top_mem:
            print(c(DIM, f"      {p.get('pid',0):>6}  ") +
                  c(CYN, f"{p.get('mem_pct',0):5.1f}%  ") +
                  c(WHT, f"{p.get('name','?'):<24}") +
                  c(DIM, f"  {p.get('user','?')}"))


def print_users(users):
    if not users or users.get("enabled") is False: return
    logged = users.get("logged_in", [])
    if not logged: return
    print()
    print(section_header("USERS"))
    for u in logged:
        print(c(WHT, f"    {u.get('name','?'):<16}") +
              c(DIM, f"  {u.get('terminal','?'):<8}  {u.get('host','local'):<16}  {u.get('started','?')[:19]}"))


def print_battery(batt):
    if not batt or batt.get("enabled") is False: return
    if not batt.get("present"): return
    print()
    print(section_header("BATTERY"))
    pct     = batt.get("percent", 0)
    plugged = "Plugged in" if batt.get("plugged_in") else "On battery"
    secs    = batt.get("time_left_sec")
    time_str = ""
    if secs:
        h = secs // 3600; m = (secs % 3600) // 60
        time_str = f"  {h}h {m:02d}m remaining"
    print(f"  {bar(pct)} {pct_col(pct)}" + c(DIM, f"  {plugged}{time_str}"))


def print_gpu(gpu):
    if not gpu or gpu.get("enabled") is False: return
    gpus = gpu.get("gpus", [])
    if not gpus: return
    print()
    print(section_header("GPU"))
    for g in gpus:
        name = g.get("name", "Unknown GPU")
        util = g.get("util_percent")
        temp = g.get("temp_celsius")
        mem_u = g.get("mem_used_mb")
        mem_t = g.get("mem_total_mb")
        # RPi VideoCore
        gpu_mem   = g.get("gpu_mem")
        throttled = g.get("throttled")
        if util is not None:
            print(f"  {bar(util or 0)} {pct_col(util or 0)}" +
                  c(DIM, f"  {name}"))
            if temp:
                print(c(DIM, f"    Temp: {temp}°C") +
                      (c(DIM, f"  VRAM: {mem_u}/{mem_t} MB") if mem_u else ""))
        else:
            print(c(WHT, f"    {name}"))
            if gpu_mem:   print(c(DIM, f"    GPU Memory: {gpu_mem}"))
            if throttled: print(c(DIM, f"    Throttle:   {throttled}"))


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

SECTION_PRINTERS = {
    "cpu":         print_cpu,
    "ram":         print_ram,
    "disk":        print_disk,
    "network":     print_network,
    "temperature": print_temperature,
    "uptime":      print_uptime,
    "os":          print_os,
    "hardware":    print_hardware,
    "processes":   print_processes,
    "users":       print_users,
    "battery":     print_battery,
    "gpu":         print_gpu,
}


def print_all(stats):
    print_header(stats)
    for key, fn in SECTION_PRINTERS.items():
        data = stats.get(key)
        if data:
            fn(data)
    print()
    print(divider())
    print(c(DIM, " SilencePSLLC |  ATLAS v2.0.0"))
    print(divider())
    print()


def main():
    parser = argparse.ArgumentParser(description="ATLAS CLI v2.0.0")
    parser.add_argument("--watch",    action="store_true", help="Live refresh mode")
    parser.add_argument("--interval", type=int, default=30, help="Refresh interval (seconds)")
    parser.add_argument("--section",  help="Show one section only (cpu/ram/disk/network/etc)")
    parser.add_argument("--json",     action="store_true", help="Raw JSON output")
    parser.add_argument("--cache",    default=CACHE_FILE,  help="Path to cache file")
    args = parser.parse_args()

    try:
        while True:
            stats = load_cache(args.cache)

            if stats is None:
                print(f"\n  {c(RED,'✗')} No cache found at {args.cache}")
                print(f"  Start the collector:")
                print(f"  {c(CYN,'python3 /opt/Atlas/collector.py &')}\n")
                if not args.watch:
                    sys.exit(1)
                time.sleep(args.interval)
                continue

            if args.json:
                if args.section:
                    data = stats.get(args.section, {"error": "section not found"})
                    print(json.dumps(data, indent=2))
                else:
                    print(json.dumps(stats, indent=2))
            else:
                if args.watch:
                    print("\033[2J\033[H", end="")
                if args.section:
                    fn = SECTION_PRINTERS.get(args.section)
                    if fn:
                        print_header(stats)
                        fn(stats.get(args.section, {}))
                        print()
                    else:
                        print(f"Unknown section. Available: {', '.join(SECTION_PRINTERS)}")
                else:
                    print_all(stats)

            if not args.watch:
                break
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
