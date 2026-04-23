#!/usr/bin/env python3
"""
Serve both Gal Travels pages from one port AND open an HTTPS tunnel.

  /gilbon    → galtravels-gilbon/index.html
  /hashofet  → galtravels-hashofet/index.html
  /          → links to both

Usage:
  python3 serve_gal.py                # port 8080, tunnel on
  python3 serve_gal.py 9000           # custom port, tunnel on
  python3 serve_gal.py 9000 --no-tunnel   # skip the ssh tunnel
"""

import http.server
import sys
import os
import socket
import subprocess
import threading
import re
import atexit
import signal
import urllib.request
import urllib.parse
import ipaddress

args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = {a for a in sys.argv[1:] if a.startswith("--")}
PORT = int(args[0]) if args else 8080
TUNNEL = "--no-tunnel" not in flags
BASE = os.path.dirname(os.path.abspath(__file__))

PAGE_DIRS = {
    "gilbon":   os.path.join(BASE, "galtravels-gilbon"),
    "hashofet": os.path.join(BASE, "galtravels-hashofet"),
}

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css":  "text/css; charset=utf-8",
    ".js":   "application/javascript; charset=utf-8",
    ".jpg":  "image/jpeg", ".jpeg": "image/jpeg",
    ".png":  "image/png",  ".gif":  "image/gif",
    ".webp": "image/webp", ".svg":  "image/svg+xml",
    ".ico":  "image/x-icon",
}

INDEX_HTML = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gal Travels</title>
<style>body{font-family:system-ui,sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;gap:1.5rem;background:#f5f3f7;}
a{display:block;padding:1.2rem 2.5rem;background:#513f83;color:#fff;border-radius:12px;text-decoration:none;font-size:1.2rem;font-weight:700;text-align:center;transition:transform .2s;}
a:hover{transform:scale(1.05);}
h1{font-size:1.5rem;color:#333;}</style></head>
<body>
<h1>Gal Travels - Landing Pages</h1>
<a href="/gilbon">נחל גילבון (25-35)</a>
<a href="/hashofet">נחל השופט (45-55)</a>
<a href="/builder" style="background:#b33">Landing Page Builder →</a>
</body></html>"""

ROOT_FILES = {
    "/builder":       os.path.join(BASE, "builder.html"),
    "/builder.html":  os.path.join(BASE, "builder.html"),
    "/template.html": os.path.join(BASE, "template.html"),
}


class Handler(http.server.BaseHTTPRequestHandler):
    def _send_file(self, abs_path):
        ext = os.path.splitext(abs_path)[1].lower()
        ctype = MIME.get(ext, "application/octet-stream")
        try:
            with open(abs_path, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # Aggressive no-cache so edits show up on refresh without restarting
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def _proxy_fetch(self):
        """Fetch an arbitrary public URL and return its body (for the builder).
        Blocks private/loopback addresses to keep SSRF risk low even though we run on localhost.
        """
        qs = urllib.parse.urlparse(self.path).query
        target = urllib.parse.parse_qs(qs).get("url", [""])[0].strip()
        if not target.startswith(("http://", "https://")):
            self.send_response(400); self.end_headers()
            self.wfile.write(b"bad url"); return
        try:
            host = urllib.parse.urlparse(target).hostname or ""
            # Block localhost / private ranges
            try:
                ip = ipaddress.ip_address(socket.gethostbyname(host))
                if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                    self.send_response(403); self.end_headers()
                    self.wfile.write(b"blocked: private host"); return
            except (ValueError, socket.gaierror):
                pass
            req = urllib.request.Request(
                target,
                headers={"User-Agent": "Mozilla/5.0 GalTravelsBuilder/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read()
                ctype = resp.headers.get("Content-Type", "text/html; charset=utf-8")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(502); self.end_headers()
            self.wfile.write(f"fetch failed: {e}".encode())

    def do_GET(self):
        raw = self.path.split("?")[0]
        # Root index
        if raw in ("", "/"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode())
            return
        # Root-level builder assets
        if raw in ROOT_FILES:
            self._send_file(ROOT_FILES[raw]); return
        # URL-fetch proxy for the builder: /api/fetch?url=https://...
        if raw == "/api/fetch":
            self._proxy_fetch(); return
        parts = [p for p in raw.split("/") if p != ""]
        if not parts or parts[0] not in PAGE_DIRS:
            self.send_response(404); self.end_headers(); return
        page_dir = PAGE_DIRS[parts[0]]
        # /<page>  -> redirect to /<page>/  so relative paths resolve properly
        if len(parts) == 1 and not raw.endswith("/"):
            self._redirect("/" + parts[0] + "/"); return
        # /<page>/  -> index.html
        if len(parts) == 1 and raw.endswith("/"):
            self._send_file(os.path.join(page_dir, "index.html")); return
        # /<page>/<subpath>  -> static file inside the page dir (sandboxed)
        sub = "/".join(parts[1:])
        target = os.path.normpath(os.path.join(page_dir, sub))
        if not target.startswith(page_dir + os.sep):
            self.send_response(403); self.end_headers(); return
        self._send_file(target)

    def log_message(self, fmt, *args):
        pass  # quiet


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def start_tunnel(port):
    """Spawn `ssh -R 80:localhost:<port> nokey@localhost.run` and print the public URL."""
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=60",
        "-R", f"80:localhost:{port}",
        "nokey@localhost.run",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        print("  [tunnel] ssh not found — skipping tunnel")
        return None

    url_re = re.compile(r"https://[a-z0-9-]+\.lhr\.life")

    def reader():
        printed = False
        for line in proc.stdout:
            if not printed:
                m = url_re.search(line)
                if m:
                    print(f"\n  Public:  {m.group(0)}")
                    print(f"           {m.group(0)}/gilbon")
                    print(f"           {m.group(0)}/hashofet\n")
                    printed = True

    threading.Thread(target=reader, daemon=True).start()

    def cleanup():
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
    atexit.register(cleanup)
    return proc


if __name__ == "__main__":
    ip = get_local_ip()
    # allow_reuse_address so restarting after a crash doesn't hit "address in use"
    http.server.HTTPServer.allow_reuse_address = True
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"\n  Gal Travels server running!\n")
    print(f"  Local:   http://localhost:{PORT}")
    print(f"  Network: http://{ip}:{PORT}")
    print(f"")
    print(f"  /gilbon    → נחל גילבון (25-35)")
    print(f"  /hashofet  → נחל השופט (45-55)")
    if TUNNEL:
        print(f"\n  Opening HTTPS tunnel (localhost.run)...")
        start_tunnel(PORT)
    else:
        print(f"\n  Tunnel disabled (--no-tunnel).")
    print(f"\n  Press Ctrl+C to stop.\n")

    # Shut down cleanly: the signal handler runs on the main thread, but
    # server.shutdown() must be called from a DIFFERENT thread than
    # serve_forever(), so dispatch it to a worker thread.
    shutting_down = threading.Event()
    def handle_stop(sig, frame):
        if shutting_down.is_set():
            return
        shutting_down.set()
        print("\n  Shutting down...")
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    try:
        server.serve_forever()
    finally:
        server.server_close()
