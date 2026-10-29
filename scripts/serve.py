#!/usr/bin/env python3
"""
Live preview — builds the site, opens it in your browser and rebuilds + reloads
every time you save the letter, story.toml, a clip, or the page code.

    python scripts/serve.py              http://localhost:8000
    python scripts/serve.py --port 9000

Tip: add ?nogate to the URL to skip the "Open it" screen while you're editing.
Stop with Ctrl+C.
"""
from __future__ import annotations

import argparse
import http.server
import importlib
import re
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

WATCH = (build.CONTENT, build.MEDIA, build.SRC, build.HERE)
STATE = {"version": str(time.time())}

# Injected only by this dev server — never part of the published site.
RELOAD_JS = b"""<script>/* dev live-reload */(()=>{const K='__devscroll';const s=sessionStorage.getItem(K);
if(s!==null){sessionStorage.removeItem(K);addEventListener('load',()=>setTimeout(()=>scrollTo(0,+s),80));}
let v=null;setInterval(async()=>{try{const t=await(await fetch('/__version',{cache:'no-store'})).text();
if(v&&t!==v){sessionStorage.setItem(K,String(scrollY));location.reload();}v=t;}catch(e){}},900);})();</script>"""


def snapshot() -> int:
    sig = []
    for base in WATCH:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if (p.is_file() and not p.name.startswith(".") and ".tmp." not in p.name
                    and "__pycache__" not in p.parts):
                try:
                    st = p.stat()
                except FileNotFoundError:
                    continue
                sig.append((str(p), st.st_size, st.st_mtime_ns))
    return hash(tuple(sorted(sig)))


def safe_build() -> bool:
    try:
        # pick up edits to the build scripts themselves, not just the content
        for name in ("media", "render"):
            if name in sys.modules:
                importlib.reload(sys.modules[name])
        importlib.reload(build)
        build.build()
        return True
    except build.BuildError as e:
        print(f"✗ {e}")
    except Exception:
        traceback.print_exc()
    return False


def watch_loop() -> None:
    last = snapshot()
    while True:
        time.sleep(1)
        now = snapshot()
        if now == last:
            continue
        while True:  # wait until files stop changing (big clips take a moment to copy)
            time.sleep(0.6)
            settled = snapshot()
            if settled == now:
                break
            now = settled
        last = now
        print("\n↻ change detected — rebuilding…")
        if safe_build():
            STATE["version"] = str(time.time())
            print("✓ page reloaded")


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript", ".css": "text/css", ".html": "text/html",
        ".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm",
        ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac",
        ".ogg": "audio/ogg", ".opus": "audio/ogg", ".wav": "audio/wav", ".jpg": "image/jpeg",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(build.OUT), **kwargs)

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path == "/__version":
            body = STATE["version"].encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        fs = Path(self.translate_path(self.path))
        if fs.is_dir():
            if not path.endswith("/"):
                return super().do_GET()  # redirect to add the slash
            fs = fs / "index.html"

        if fs.suffix == ".html" and fs.is_file():
            data = fs.read_bytes().replace(b"</body>", RELOAD_JS + b"</body>", 1)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        rng = self.headers.get("Range")
        if rng and fs.is_file():
            return self.send_range(fs, rng)
        return super().do_GET()

    def send_range(self, fs: Path, rng: str):
        """Videos need byte-range requests to loop and seek smoothly (Safari insists on it)."""
        size = fs.stat().st_size
        m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
        if not m or (m.group(1) == "" and m.group(2) == ""):
            return super().do_GET()
        a, b = m.groups()
        if a == "":
            start, end = max(0, size - int(b)), size - 1
        else:
            start = int(a)
            end = min(int(b), size - 1) if b else size - 1
        if start >= size or start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return
        length = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(fs)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        with open(fs, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    break
                remaining -= len(chunk)


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return  # the browser cancelled a video request — normal
        super().handle_error(request, client_address)


def main() -> None:
    ap = argparse.ArgumentParser(description="Live preview of the birthday page")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-open", action="store_true", help="don't open a browser tab")
    args = ap.parse_args()

    print("Building…")
    safe_build()

    server = None
    for port in range(args.port, args.port + 20):
        try:
            server = Server(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if not server:
        sys.exit("No free port found.")

    url = f"http://localhost:{server.server_address[1]}/"
    print(f"\n★ Preview: {url}")
    print(f"  Editing mode (skips the opening screen): {url}?nogate")
    print("  Save any file in content/, media/ or site_src/ and the page reloads.  Ctrl+C to stop.\n")
    threading.Thread(target=watch_loop, daemon=True).start()
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye 👋")


if __name__ == "__main__":
    main()
