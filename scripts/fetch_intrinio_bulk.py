#!/usr/bin/env python3
"""Fetch Intrinio bulk downloads (prices, fundamentals, company metadata).

Replicates the established 2026-09-28 pattern: query the bulk-downloads
links endpoint (paginated), match the three licensed products by Intrinio ID
(falling back to name match), download every file, and write a manifest.json
in the same shape as data/raw/intrinio/2026-09-28/manifest.json.

Auth is handled entirely by the Intrinio skill CLI -- this script never sees
the raw API key. Download URLs are pre-signed S3 links (no auth needed).

Usage:
    python3 scripts/fetch_intrinio_bulk.py [--out data/raw/intrinio/<date>]
    (defaults to today's date)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SKILL_CLI = Path.home() / "workspace" / "skills" / "intrinio" / "bin" / "intrinio_api.py"

# Intrinio product IDs from the 2026-09-28 manifest; matched by ID first,
# then by exact name if IDs ever rotate.
WANT = [
    ("bdt_nzJNzB", "US Stock Prices, 5 years"),
    ("bdt_AXGAyM", "US Fundamentals, 5 years"),
    ("bdt_xgxWyr", "US Company Metadata"),
]


def api(path: str, **params: str) -> dict:
    cmd = [sys.executable, str(SKILL_CLI), path]
    cmd += [f"{k}={v}" for k, v in params.items()]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def list_products() -> list[dict]:
    products: list[dict] = []
    params: dict[str, str] = {}
    while True:
        page = api("/bulk_downloads/links", **params)
        products.extend(page["bulk_downloads"])
        nxt = page.get("next_page")
        if not nxt:
            break
        params = {"next_page": nxt}
    return products


def download(url: str, dest: Path, retries: int = 3) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "borealis/1.0"})
            with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
                expected = r.headers.get("Content-Length")
                expected = int(expected) if expected else None
                total = 0
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)
            if expected is not None and total != expected:
                raise IOError(f"truncated download: got {total} bytes, "
                              f"expected {expected}")
            return total
        except Exception as e:  # noqa: BLE001 - retry then record
            print(f"    attempt {attempt + 1} failed: {e}", flush=True)
            if attempt == retries - 1:
                raise
            time.sleep(5)
    raise RuntimeError("unreachable")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None,
                    help="output dir (default data/raw/intrinio/<today>)")
    args = ap.parse_args()

    today = dt.date.today().isoformat()
    out_dir = Path(args.out) if args.out else Path("data/raw/intrinio") / today
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[fetch] listing bulk products ...", flush=True)
    products = list_products()
    by_id = {p["id"]: p for p in products}

    manifest: dict = {
        "download_started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "datasets": [],
        "failures": [],
    }
    total_bytes = 0

    for want_id, want_name in WANT:
        prod = by_id.get(want_id)
        if prod is None:
            matches = [p for p in products if p["name"] == want_name]
            prod = matches[0] if matches else None
        if prod is None:
            msg = f"product not found: id={want_id} name={want_name!r}"
            print(f"[fetch] ERROR: {msg}", flush=True)
            manifest["failures"].append(msg)
            continue
        if prod["id"] != want_id:
            print(f"[fetch] note: {want_name!r} matched by name "
                  f"(id {prod['id']}, expected {want_id})", flush=True)

        entry: dict = {
            "name": prod["name"],
            "intrinio_id": prod["id"],
            "format": prod.get("format"),
            "intrinio_last_updated": prod.get("last_updated"),
            "intrinio_data_length_bytes": prod.get("data_length_bytes"),
            "files": [],
        }
        print(f"[fetch] {prod['name']} ({len(prod['links'])} files) ...", flush=True)
        for link in prod["links"]:
            fname = link["name"]
            dest = out_dir / fname
            if dest.exists():
                nbytes = dest.stat().st_size
                print(f"    skip {fname} (already present, {nbytes} bytes)", flush=True)
            else:
                print(f"    downloading {fname} ...", flush=True)
                nbytes = download(link["url"], dest)
            entry["files"].append({
                "filename": fname,
                "bytes": nbytes,
                "downloaded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            })
            total_bytes += nbytes
        manifest["datasets"].append(entry)

    manifest["total_bytes"] = total_bytes
    manifest["download_finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"[fetch] done: {total_bytes:,} bytes -> {out_dir}", flush=True)
    if manifest["failures"]:
        print(f"[fetch] FAILURES: {manifest['failures']}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
