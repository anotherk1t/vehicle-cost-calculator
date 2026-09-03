# Vehicle cost calculator

A small model of what a vehicle actually costs in Poland with a focus on a yearly price.
Just a static page at [tco.yanb.dev](https://tco.yanb.dev).

## What is here

    src/                    Python coefficients and renderer
    data/                   derived vehicle curves and dated fuel snapshot
    static/404.html         static not-found page
    public/                 generated deployment output
    build.py                one-command build
    wrangler.jsonc          Cloudflare static-assets deploy config

The calculator covers cars and motorcycles. It runs in the browser and recalculates as inputs change. There is no scraper or marketplace listing data in this repository: `data/` contains derived aggregates only.

## Why?

Everyone needs to move from A to B. Cars are usually regarded as the most convenient and "comfortable" option. They cost more than the alternatives. Depreciation and other running costs are often looked over for a modern-ish economy-ish car at ≈ 50k to 150k PLN that could lose a lot of value after a couple of years. So what is a reasonable amount to spend every year on a cool car? And how much would it cost per year, not just at the point of purchase? I built it to answer my own questions about owning a scooter vs a car vs a bicycle vs just buying a transit pass in Gdańsk.

## Build

Pure Python and one dependency-free browser script. Generated files are written to `public/` and are intentionally ignored by Git.

    python build.py
    python -m pytest
    ruff check . && ruff format --check .
    node --check src/assets/tco.js

Open `public/index.html` locally after building.

## Deploy

Cloudflare Workers Static Assets, configured in `wrangler.jsonc`:

    python build.py
    npx wrangler deploy

Cloudflare serves `public/` from the edge and returns `404.html` for missing routes. The build must run before deployment.

## Data boundary and limits

Vehicle curves are pre-aggregated medians and fitted values produced by a separate private data engine. Fuel prices are a dated, sourced snapshot and remain editable in the calculator; there is no runtime fuel-price API.

Models with thin or noisy data are marked unreliable and hidden from the selector. Where a selected model lacks a dependable curve, the calculator uses its vehicle-category basis and shows that limitation.

Fuel source: [European Commission Weekly Oil Bulletin](https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en), converted with the NBP EUR/PLN rate. Registration, inspection, insurance and running-cost assumptions are editable.
