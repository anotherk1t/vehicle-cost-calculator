# mobility-cost-pl

A small, honest model of what a vehicle costs in Poland — to you, and to everyone
else on the road. Static site, no backend, no tracking.

> **Working name.** Rename the repo/folder freely (it'll live under a portfolio
> domain). This is the **public, presentation-only** half of the project.

## What's here (and what isn't)

This repo holds the **rendered product** and the **economic coefficients** — the
single source of truth lives in `src/`, in Python, and is unit-tested. It contains:

- **no scraper** and **no marketplace listings**;
- surfaces that need market data (depreciation curves, seasonality) consume a
  pre-aggregated `aggregates.json` of **derived facts only** (medians, curves),
  produced out-of-band by the private data engine — never raw rows.

That boundary is deliberate: it's structurally impossible for this repo to leak
scraping code or listing data, because it has neither.

## Surfaces

| Surface | Status | Source |
|---|---|---|
| **Public-money-on-you calculator** — what you pay the state vs. what you cost it, per km | ✅ built | `src/social_cost.py` (pure coefficients) |
| Personal cost (depreciation/TCO) | planned | renders from `aggregates.json` |
| "In practice" research/map page | planned | static + public datasets |

### The public-cost calculator

Reconciles, per year and per vehicle, what you hand the Polish state (fuel akcyza
+ opłata paliwowa + VAT + registration, minus any EV purchase grant) against what
you cost society (EC/CE Delft external-cost coefficients: crashes, congestion,
climate, air, noise, energy supply, land). The verdict is one number — the share
of your own road footprint you actually pay for — personalising the EU-28 ~48%
cost-coverage figure. Everything is user-adjustable: it's a model to argue with.

Two honesty calls are baked in: scooters get their **own** profile (crash cost as
a band, not the blended motorcycle figure), and going electric is shown to cut the
*cost* side only modestly while collapsing the *payment* side — so the public ends
up covering **more** of an EV's footprint, not less.

## Build & develop

Pure standard library — no runtime dependencies.

```bash
python build.py                 # renders all surfaces into ./public/
python -m pytest                # coefficient sanity + balance math + render
ruff check . && ruff format --check .
```

Open `public/index.html` in a browser.

## Deploy (Cloudflare Pages)

- **Build command:** `python build.py`
- **Output directory:** `public`

No origin server, no database — the whole site is static, served from the edge
and entirely off the data engine's infrastructure.

## Sources

- EC / CE Delft, *Handbook on the external costs of transport* (2019; EU-28, 2016 €).
- *Transport taxes and charges in Europe* (2019) — the ~48% car cost-coverage figure.
- KGP / ITS Polish road-crash statistics — moped vs. motorcycle severity split.
- PL 2026 fuel excise (akcyza), opłata paliwowa, VAT.

No marketplace data is used anywhere in this repo.
