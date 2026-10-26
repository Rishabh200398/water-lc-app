"""Screenshot helper for the report: drives the local Chrome headlessly over the DevTools protocol.

Dev-only (needs `pip install websocket-client` and Google Chrome). Not used by the app.

    from capture import Browser
    with Browser() as b:
        b.login("Rishabh", "waterlc")
        b.shot("#/admin", "02_dashboard")
"""

from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BASE = "http://localhost:8040/"
OUT = Path(__file__).resolve().parent.parent / "output" / "screenshots"


class Browser:
    def __init__(self, port: int = 9333, width: int = 1280, height: int = 860):
        self.port, self.width, self.height = port, width, height
        self._id = 0

    def __enter__(self) -> "Browser":
        OUT.mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen([
            CHROME, "--headless=new", f"--remote-debugging-port={self.port}", f"--remote-allow-origins=http://127.0.0.1:{self.port}", "--hide-scrollbars",
            f"--user-data-dir={tempfile.mkdtemp(prefix='wlc-chrome-')}", "--no-first-run", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json").read())
                page = next(t for t in tabs if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=60)
        self.size(self.width, self.height)
        return self

    def __exit__(self, *a) -> None:
        self.ws.close()
        self.proc.terminate()

    def cmd(self, method: str, **params):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def size(self, width: int, height: int, mobile: bool = False) -> None:
        self.width, self.height = width, height
        self.cmd("Emulation.setDeviceMetricsOverride", width=width, height=height,
                 deviceScaleFactor=2 if mobile else 1.5, mobile=mobile)

    def js(self, expr: str):
        r = self.cmd("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        return r.get("result", {}).get("value")

    def go(self, hash_path: str, wait: float = 1.8) -> None:
        # Navigating to the same URL is a no-op in Chrome, so go via a blank page to force a fresh load.
        self.cmd("Page.navigate", url="about:blank")
        time.sleep(0.2)
        self.cmd("Page.navigate", url=BASE + hash_path)
        time.sleep(wait)

    def login(self, name: str, password: str) -> None:
        self.go("", 1.0)
        self.js(f"""(async () => {{ const r = await fetch('/api/login', {{method:'POST', headers:{{'content-type':'application/json'}},
            body: JSON.stringify({{name:'{name}', password:'{password}'}})}}); localStorage.setItem('waterlc-session', JSON.stringify(await r.json())); return 1 }})()""")

    def shot(self, hash_path: str | None, name: str, before: str | None = None, full: bool = False,
             clip_selector: str | None = None, max_height: int = 2600) -> Path:
        """Navigate (unless hash_path is None), run optional JS, then save a PNG."""
        if hash_path is not None:
            self.go(hash_path)
        if before:
            self.js(before)
            time.sleep(0.8)
        params: dict = {"format": "png", "captureBeyondViewport": full}
        if clip_selector:
            box = self.js(f"""(() => {{ const r = document.querySelector({json.dumps(clip_selector)}).getBoundingClientRect();
                return {{x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height}} }})()""")
            params["clip"] = {"x": max(box["x"] - 12, 0), "y": max(box["y"] - 12, 0), "width": box["w"] + 24,
                              "height": min(box["h"] + 24, max_height), "scale": 1}
            params["captureBeyondViewport"] = True
        elif full:
            h = min(self.js("document.documentElement.scrollHeight"), max_height)
            params["clip"] = {"x": 0, "y": 0, "width": self.width, "height": h, "scale": 1}
        data = self.cmd("Page.captureScreenshot", **params)["data"]
        path = OUT / f"{name}.png"
        path.write_bytes(base64.b64decode(data))
        return path
