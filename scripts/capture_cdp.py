#!/usr/bin/env python3
"""Capture heavy map applications that defeat Chrome's --screenshot flag.

``--virtual-time-budget`` never expires on pages that keep a timer running
forever, which is exactly what the ArcGIS and Air Quality Index map viewers do:
headless Chrome hangs instead of producing an image. This script drives Chrome
over the DevTools Protocol instead, waits a fixed number of real seconds, and
then asks for the screenshot.

Usage::

    python scripts/capture_cdp.py <id>=<url> [<id>=<url> ...] [--wait 30]
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9222
SHOTS_DIR = Path("build/shots")


def start_chrome(profile: Path, webgl: bool = False) -> subprocess.Popen:
    # Map viewers (ArcGIS, the Air Quality Index) draw into a WebGL canvas,
    # which --disable-gpu leaves blank. SwiftShader renders it in software.
    gpu_flags = (["--enable-unsafe-swiftshader", "--use-gl=angle",
                  "--use-angle=swiftshader"] if webgl else ["--disable-gpu"])
    return subprocess.Popen(
        [CHROME, "--headless=new", *gpu_flags, "--hide-scrollbars",
         "--no-first-run", "--no-default-browser-check",
         f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
         "--remote-allow-origins=*",
         "--window-size=1280,900", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def wait_for_devtools(attempts: int = 40) -> str:
    """Block until Chrome's DevTools endpoint answers, then return the WS URL."""
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2) as r:
                return json.load(r)["webSocketDebuggerUrl"]
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Chrome DevTools endpoint never came up")


class CDP:
    """Minimal DevTools Protocol client."""

    def __init__(self, url: str):
        self.ws = websocket.create_connection(url, timeout=120)
        self.seq = 0

    def send(self, method: str, **params):
        self.seq += 1
        self.ws.send(json.dumps({"id": self.seq, "method": method, "params": params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == self.seq:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})

    def close(self):
        self.ws.close()


def capture(browser: CDP, app_id: str, url: str, wait: int) -> bool:
    target = browser.send("Target.createTarget", url="about:blank")["targetId"]
    session = CDP(f"ws://127.0.0.1:{PORT}/devtools/page/{target}")
    try:
        session.send("Page.enable")
        session.send("Emulation.setDeviceMetricsOverride",
                     width=1280, height=900, deviceScaleFactor=1, mobile=False)
        session.send("Page.navigate", url=url)
        # A real wall-clock wait: the point of this script.
        time.sleep(wait)
        data = session.send("Page.captureScreenshot", format="png")["data"]
    finally:
        session.close()
        browser.send("Target.closeTarget", targetId=target)

    out = SHOTS_DIR / f"{app_id}.png"
    out.write_bytes(base64.b64decode(data))
    return out.stat().st_size > 5000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="+", metavar="ID=URL")
    parser.add_argument("--wait", type=int, default=30,
                        help="real seconds to let the app draw before capturing")
    parser.add_argument("--webgl", action="store_true",
                        help="render WebGL in software (needed by map viewers)")
    args = parser.parse_args()

    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    profile = Path("build/cdp-profile")
    profile.mkdir(parents=True, exist_ok=True)

    chrome = start_chrome(profile, webgl=args.webgl)
    try:
        browser = CDP(wait_for_devtools())
        failed = []
        for target in args.targets:
            app_id, _, url = target.partition("=")
            print(f"  capturing {app_id} (waiting {args.wait}s) ...", flush=True)
            try:
                if capture(browser, app_id, url, args.wait):
                    size = (SHOTS_DIR / f"{app_id}.png").stat().st_size // 1024
                    print(f"    ok: {size} KB")
                else:
                    failed.append(app_id)
                    print("    too small")
            except Exception as exc:  # noqa: BLE001
                failed.append(app_id)
                print(f"    failed: {exc}")
        browser.close()
        if failed:
            print("failed:", ", ".join(failed))
            return 1
        return 0
    finally:
        chrome.terminate()
        try:
            chrome.wait(timeout=10)
        except subprocess.TimeoutExpired:
            chrome.kill()


if __name__ == "__main__":
    sys.exit(main())
