#!/usr/bin/env python3
"""Capture a thumbnail of every viewer and dashboard the portal links to.

The catalogue comes from the "Direct access to viewers and tables" page, which
lists each application with the box it belongs to. Each one is rendered in
headless Chrome and downscaled to a thumbnail for the gallery page.

Nothing here talks to the portal's CMS — it only opens the applications
themselves, which live on Tableau Public and discomap.

Usage::

    python scripts/capture_thumbnails.py [--only ID ...] [--jobs 4]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CATALOGUE_PAGE = Path("docs/pages/direct-access-to-viewers-and-tablesviewers-direct-access.md")
CATALOGUE_JSON = Path("docs/_data/applications.json")
SHOTS_DIR = Path("build/shots")
THUMBS_DIR = Path("docs/_static/thumbnails")

# Tableau needs the longest to draw; give every app the same generous budget so
# a slow dashboard is not silently captured mid-render.
VIRTUAL_TIME_BUDGET_MS = 25000
WINDOW = "1280,900"
THUMB_WIDTH = 640
THUMB_QUALITY = 70


def parse_catalogue() -> list[dict]:
    """Read the viewer catalogue out of the exported Markdown table."""
    rows: list[dict] = []
    box = ""
    for line in CATALOGUE_PAGE.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or cells[0] in ("Serial number",) or set(cells[0]) <= set("- "):
            continue
        num, raw_box, name, previously, url_cell = cells[:5]
        raw_box = raw_box.replace("**", "").strip()
        if raw_box:
            box = raw_box
        match = re.search(r"\]\((https?://[^)\s]+)\)|<(https?://[^>\s]+)>", url_cell)
        if not match:
            continue
        name = name.replace("**", "").strip()
        rows.append({
            "id": num,
            "box": box,
            "name": re.sub(r"\s+", " ", name),
            "discontinued": "discontinued" in name.lower(),
            "previously": previously.replace("**", "").strip(),
            "url": match.group(1) or match.group(2),
        })
    return rows


def capture(app: dict) -> tuple[str, bool, str]:
    """Render one application to a PNG. Returns (id, ok, message)."""
    out = SHOTS_DIR / f"{app['id']}.png"
    cmd = [
        CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--no-first-run", "--no-default-browser-check",
        f"--window-size={WINDOW}",
        f"--virtual-time-budget={VIRTUAL_TIME_BUDGET_MS}",
        f"--screenshot={out}", app["url"],
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=False)
    except subprocess.TimeoutExpired:
        return app["id"], False, "timed out"
    if not out.exists() or out.stat().st_size < 5000:
        return app["id"], False, "no image produced"
    return app["id"], True, f"{out.stat().st_size // 1024} KB"


def make_thumbnail(app_id: str) -> bool:
    """Downscale a capture into the gallery thumbnail."""
    src = SHOTS_DIR / f"{app_id}.png"
    dst = THUMBS_DIR / f"{app_id}.jpg"
    if not src.exists():
        return False
    result = subprocess.run(
        ["sips", "-s", "format", "jpeg", "-Z", str(THUMB_WIDTH),
         "--setProperty", "formatOptions", str(THUMB_QUALITY),
         str(src), "--out", str(dst)],
        capture_output=True,
    )
    return result.returncode == 0 and dst.exists()


def is_blank(app_id: str) -> bool:
    """Flag captures that came out essentially uniform (blank or error page).

    A viewer that failed to load usually renders as a single flat colour, and
    a flat image compresses far smaller than a real screenshot.
    """
    dst = THUMBS_DIR / f"{app_id}.jpg"
    return dst.exists() and dst.stat().st_size < 12000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="capture just these catalogue ids")
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()

    if not Path(CHROME).exists():
        print(f"Google Chrome not found at {CHROME}", file=sys.stderr)
        return 1

    apps = parse_catalogue()
    CATALOGUE_JSON.parent.mkdir(parents=True, exist_ok=True)
    CATALOGUE_JSON.write_text(json.dumps(apps, indent=1) + "\n", encoding="utf-8")
    print(f"Catalogue: {len(apps)} applications in "
          f"{len({a['box'] for a in apps})} groups -> {CATALOGUE_JSON}")

    targets = [a for a in apps if not args.only or a["id"] in args.only]
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Capturing {len(targets)} applications with {args.jobs} parallel browsers...")
    failures, blanks = [], []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for app_id, ok, message in pool.map(capture, targets):
            name = next(a["name"] for a in targets if a["id"] == app_id)
            if not ok:
                failures.append((app_id, name, message))
                print(f"  FAIL {app_id}  {name[:44]:<44} {message}")
                continue
            make_thumbnail(app_id)
            flag = ""
            if is_blank(app_id):
                blanks.append((app_id, name))
                flag = "  <- looks blank, check"
            print(f"  ok   {app_id}  {name[:44]:<44} {message}{flag}")

    print(f"\nCaptured {len(targets) - len(failures)}/{len(targets)}")
    if failures:
        print("Failed:")
        for app_id, name, message in failures:
            print(f"  - {app_id} {name}: {message}")
    if blanks:
        print("Suspiciously uniform (verify before publishing):")
        for app_id, name in blanks:
            print(f"  - {app_id} {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
