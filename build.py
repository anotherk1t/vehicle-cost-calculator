#!/usr/bin/env python3
"""Static build for Cloudflare Pages.

Renders every surface of the site into ./public/ — a self-contained static
bundle with no runtime dependencies. Cloudflare Pages config:
    Build command:    python build.py
    Output directory: public

This repo is presentation-only: it holds the rendered product and the economic
coefficients (a single source of truth, unit-tested). It contains no scraper and
no marketplace listings — surfaces that need market data consume a separate,
pre-aggregated `aggregates.json` (derived facts only), never raw rows.
"""

from __future__ import annotations

import logging
import os

from src.depreciation import render_depreciation
from src.social_cost import render_social_cost
from src.stage3 import render_stage3
from src.tco import render_tco

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

OUTPUT_DIR = "public"
AGGREGATES = os.path.join("data", "aggregates.json")
STAGE3_BUDGET = os.path.join("data", "stage3_gdansk_transport.json")


def main() -> None:
    # Surface 2 — public-money-on-you calculator (the landing page). Pure
    # coefficients, no data dependency.
    render_social_cost(output_dir=OUTPUT_DIR, filename="index.html")

    # Surface 1 — the personal TCO calculator (the spine). Reads the engine's
    # aggregates for the depreciation curve; renders a data-gate if it's absent.
    render_tco(AGGREGATES, output_dir=OUTPUT_DIR, filename="cost.html")

    # Surface 1 (input) — the standalone depreciation page, rendered from the same
    # engine aggregates. The private pipeline drops data/aggregates.json (derived
    # curves, no rows); if it's absent the build simply skips the page.
    if os.path.exists(AGGREGATES):
        render_depreciation(AGGREGATES, output_dir=OUTPUT_DIR, filename="depreciation.html")
    else:
        logging.warning("%s missing — skipping depreciation page", AGGREGATES)

    # Surface 3 — "In practice": Gdańsk transport budget (roads vs transit) + the
    # named-projects map. Pure public-finance data (GUS BDL), no marketplace rows.
    if os.path.exists(STAGE3_BUDGET):
        render_stage3(budget_path=STAGE3_BUDGET, output_dir=OUTPUT_DIR, filename="practice.html")
    else:
        logging.warning("%s missing — skipping Stage 3 page", STAGE3_BUDGET)


if __name__ == "__main__":
    main()
