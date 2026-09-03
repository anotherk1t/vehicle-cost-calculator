#!/usr/bin/env python3
"""Static build for Cloudflare Pages.

Renders the ownership calculator and static 404 into ./public/ — a
self-contained bundle with no runtime dependencies. Cloudflare Pages config:
    Build command:    python build.py
    Output directory: public

This repo is presentation-only: it holds the rendered product and the economic
coefficients (a single source of truth, unit-tested). It contains no scraper and
no marketplace listings; depreciation consumes pre-aggregated derived facts.
"""

from __future__ import annotations

import logging
import os
import shutil

from src.tco import render_tco

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

OUTPUT_DIR = "public"
AGGREGATES = os.path.join("data", "aggregates.json")


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for old in ("ledger.html", "depreciation.html", "practice.html"):
        path = os.path.join(OUTPUT_DIR, old)
        if os.path.exists(path):
            os.unlink(path)
    render_tco(AGGREGATES, output_dir=OUTPUT_DIR, filename="index.html")
    shutil.copyfile(os.path.join("static", "404.html"), os.path.join(OUTPUT_DIR, "404.html"))


if __name__ == "__main__":
    main()
