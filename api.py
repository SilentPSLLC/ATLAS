#!/usr/bin/env python3
"""
ATLAS API — v2.1.0
Adaptive Telemetry & Live Analytics System
License: GPL v3 — https://www.gnu.org/licenses/gpl-3.0.txt
Copyright (C) 2026 SilencePSLLC

Engines:
  "http"  — Python built-in. Zero deps. ~2MB. Default. Recommended for Pi Zero.
  "flask" — Flask. ~15MB. Recommended for servers.
  "off"   — No API. Cache file only.

Endpoints:
  GET /api/ping              Health check — no auth
  GET /api/stats             Full snapshot
  GET /api/stats/<section>   Single section
  GET /api/history           SQLite history (if enabled)

Auth: X-ATLAS-Key header or ?key= query param

"""

import os, sys, json, sqlite3, argparse, subprocess
from datetime import datetime, timezone

BASE_DIR    = "/opt/Atlas"
CACHE_FILE  = os.path.join(BASE_DIR, "cache",  "stats.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config", "atlas.json")
DB_FILE     = os.path.join(BASE_DIR, "data",   "atlas.db")

DEFAULT_CONFIG = {
    "api_engine":  "http",
    "api_port":    19890,
    "api_key":     "",
    "api_enabled": True,
}


def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def load_cache():
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def check_key(provided, cfg):
    key = cfg.get("api_key", "")
    if not key:
        return True
    return provided == key


def get_key_from_request(headers, params):
    return (headers.get("X-ATLAS-Key") or
            headers.get("x-atlas-key") or
            params.get("key", ""))


def make_stats_response(section=None):
    data = load_cache()
    if data is None:
        return 503, {"error": "Cache not found — is collector running?"}
    if section:
        available = [k for k in data if k not in
                     ("atlas_version", "collected_at", "hostname")]
        if section not in data:
            return 404, {"error": f"Section '{section}' not found",
                         "available": available}
        return 200, {"section": section,
                     "hostname":     data.get("hostname"),
                     "collected_at": data.get("collected_at"),
                     "data":         data[section]}
    return 200, data


def make_history_response(limit=100):
    if not os.path.exists(DB_FILE):
        return 404, {"error": "History not enabled or no data yet"}
    try:
        limit = min(int(limit), 1000)
        conn  = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        rows  = conn.execute(
            "SELECT collected_at,hostname,cpu_percent,ram_percent,disk_percent "
            "FROM snapshots ORDER BY collected_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return 200, {"count": len(rows), "limit": limit,
                     "snapshots": [dict(r) for r in rows]}
    except Exception as e:
        return 500, {"error": str(e)}


def make_ping_response():
    return 200, {"status": "ok", "service": "ATLAS", "version": "2.1.0",
                 "time":  datetime.now(timezone.utc).isoformat(),
                 "cache": os.path.exists(CACHE_FILE)}


def run_http_server(cfg, port):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlparse, parse_qs

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                  f"{self.address_string()} {fmt % args}")

        def send_json(self, code, data):
            body = json.dumps(data, indent=2).encode()
            self.send_response(code)
            self.send_header("Content-Type",   "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            path   = parsed.path.rstrip("/")
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            key    = get_key_from_request(dict(self.headers), params)

            if path == "/api/ping":
                code, data = make_ping_response()
                return self.send_json(code, data)

            if not check_key(key, cfg):
                return self.send_json(401, {
                    "error": "Unauthorized — provide X-ATLAS-Key header"})

            if path == "/api/stats":
                code, data = make_stats_response()
                return self.send_json(code, data)

            if path.startswith("/api/stats/"):
                section    = path[len("/api/stats/"):]
                code, data = make_stats_response(section)
                return self.send_json(code, data)

            if path == "/api/history":
                limit      = params.get("limit", 100)
                code, data = make_history_response(limit)
                return self.send_json(code, data)

            self.send_json(404, {"error": "Not found"})

    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"[ATLAS] API running — engine: http  port: {port}")
    server.serve_forever()


def run_flask_server(cfg, port):
    try:
        from flask import Flask, jsonify, request, abort
    except ImportError:
        print("[ATLAS] ERROR: Flask not found.")
        print("  Run: sudo pip3 install flask --break-system-packages")
        print("  Or set api_engine to 'http' in atlas.json")
        sys.exit(1)

    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    def auth():
        key = get_key_from_request(dict(request.headers), request.args)
        return check_key(key, cfg)

    @app.route("/api/ping")
    def ping():
        _, data = make_ping_response()
        return jsonify(data)

    @app.route("/api/stats")
    def stats():
        if not auth(): abort(401)
        code, data = make_stats_response()
        return jsonify(data), code

    @app.route("/api/stats/<string:section>")
    def stats_section(section):
        if not auth(): abort(401)
        code, data = make_stats_response(section)
        return jsonify(data), code

    @app.route("/api/history")
    def history():
        if not auth(): abort(401)
        limit      = request.args.get("limit", 100)
        code, data = make_history_response(limit)
        return jsonify(data), code

    @app.errorhandler(401)
    def unauth(e):
        return jsonify({"error": "Unauthorized — provide X-ATLAS-Key header"}), 401

    @app.errorhandler(404)
    def notfound(e):
        return jsonify({"error": "Not found"}), 404

    print(f"[ATLAS] API running — engine: flask  port: {port}")
    app.run(host="0.0.0.0", port=port, debug=False)


def install_service(user):
    script = os.path.abspath(__file__)
    svc = f"""[Unit]
Description=ATLAS API — Adaptive Telemetry & Live Analytics System
After=network.target atlas-collector.service
Wants=atlas-collector.service

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
        with open("/etc/systemd/system/atlas-api.service", "w") as f:
            f.write(svc)
        subprocess.run(["systemctl","daemon-reload"],      check=True)
        subprocess.run(["systemctl","enable","atlas-api"], check=True)
        subprocess.run(["systemctl","start","atlas-api"],  check=True)
        print(f"\n  ✓ atlas-api service installed\n")
    except PermissionError:
        print("\n  ✗ Run with sudo\n")
    except Exception as e:
        print(f"\n  ✗ {e}\n")


def main():
    parser = argparse.ArgumentParser(description="ATLAS API v2.1.0")
    parser.add_argument("--install-service", action="store_true")
    parser.add_argument("--user",   default="pi")
    parser.add_argument("--port",   type=int)
    parser.add_argument("--engine", choices=["http","flask","off"])
    args = parser.parse_args()

    if args.install_service:
        install_service(args.user)
        sys.exit(0)

    cfg    = load_config()
    port   = args.port   or cfg.get("api_port",   19890)
    engine = args.engine or cfg.get("api_engine", "http")
    key    = cfg.get("api_key", "")

    if engine == "off":
        print("[ATLAS] API disabled (api_engine=off)")
        sys.exit(0)

    print(f"[ATLAS] API v2.1.0 — {engine} engine  port {port}")
    if not key:
        print("[ATLAS] WARNING: No api_key set — API is open to anyone on the network")
    else:
        print(f"[ATLAS] Auth enabled  (key: {key[:16]}...)")

    if engine == "flask":
        run_flask_server(cfg, port)
    else:
        run_http_server(cfg, port)


if __name__ == "__main__":
    main()
