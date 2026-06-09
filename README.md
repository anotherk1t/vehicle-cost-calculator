# Vehicle cost calculator

A small, honest model of what a vehicle actually costs in Poland — to you, and to everyone else on the road. Static site, no backend, no tracking. Live at [yanb.dev](https://yanb.dev).

## Why?

Everyone has an opinion on whether a car is "worth it", but the numbers people argue with are usually wrong in both directions. The sticker price hides depreciation, which is the biggest cost by far and the one nobody puts on a spreadsheet. And the public side is invisible: fuel tax, registration, the EV grant on one side; crashes, congestion, climate, air, noise on the other. You pay for some of your footprint and society covers the rest, and almost no one can say what that split is.

This is a model you can argue with. Every coefficient is exposed, every input is adjustable, and the whole thing runs in your browser with nothing phoning home. I built it to answer my own questions about owning a motorcycle vs. a car vs. just buying a transit pass in Gdańsk — so it leans toward the choices someone living here actually makes.

## The privacy boundary (read this first)

This repo is the **public, presentation-only** half of a two-part project. It holds the **rendered product** and the **economic coefficients** — the single source of truth lives in `src/`, in plain Python, and is unit-tested.

It contains **no scraper and no marketplace listings.** Surfaces that need market data (depreciation curves, resale seasonality) read a pre-aggregated `data/aggregates.json` of **derived facts only** — medians, fitted curves, never raw rows — produced out-of-band by a separate private data engine. If those aggregates are absent, the affected page simply doesn't build.

That split is deliberate: it's structurally impossible for this repo to leak scraping code or listing data, because it has neither.

## Surfaces

The site is four standalone pages sharing one top bar (language EN/PL, vehicle Moto/Car):

| Page | What it does | Source |
|---|---|---|
| **TCO calculator** (`index.html`) | The spine and landing page — personal total cost of ownership, with depreciation read from the engine's value-vs-age curves | `src/tco.py` |
| **Public-money ledger** (`ledger.html`) | What you hand the Polish state per year vs. what you cost society — the share of your own road footprint you actually pay for | `src/social_cost.py` |
| **Depreciation** (`depreciation.html`) | Value-retention curves rendered from the pre-aggregated market data | `src/depreciation.py` |
| **In practice** (`practice.html`) | Where Gdańsk's transport money actually goes — roads vs. transit, with a named-projects map | `src/stage3.py` |

### The public-money ledger

Reconciles, per year and per vehicle, what you pay the state (fuel akcyza + opłata paliwowa + VAT + registration, minus any EV purchase grant) against what you cost society, using EC/CE Delft external-cost coefficients (crashes, congestion, climate, air, noise, energy supply, land). The verdict is one number — the share of your footprint you cover yourself — which personalises the EU ~48% car cost-coverage figure.

Two honesty calls are baked in: scooters get their **own** crash profile (a band, not the blended motorcycle figure), and going electric is shown to cut the *cost* side only modestly while collapsing the *payment* side — so the public ends up covering **more** of an EV's footprint, not less.

## Architecture

```
src/*.py  (coefficients + renderers, pure stdlib)
   │  python build.py
   ▼
public/*.html  (self-contained static pages)  ──►  Cloudflare Workers Static Assets
   ▲                                                        │
   │ derived facts only                          GET /api/fuel → worker/index.js
data/aggregates.json                                        │
(dropped by the private engine)                   live PL pump prices (paliwo.today)
```

- **Build** is a single `build.py` that imports each surface's renderer and writes `public/`. No templating framework — the HTML is generated in Python.
- **Coefficients** (taxes, external costs, fuel economy, TCO math) live in `src/` and are the single source of truth, mirrored client-side in the page's JS so the calculators recompute live as you change inputs.
- **The Worker** does exactly one thing: `GET /api/fuel` returns current PL pump prices (zł/l, zł/kWh) from [paliwo.today](https://paliwo.today), cached at the edge. The calculators fetch it on load to seed defaults; if it fails they fall back to a static ballpark, so the page is never blocked on it. Every other path is a static asset served straight from the edge without invoking the Worker.

## Build & develop

Pure standard library — no runtime dependencies.

```bash
python build.py                      # render every surface into ./public/
python -m pytest                     # coefficient sanity + balance math + render checks
ruff check . && ruff format --check .
```

Then open `public/index.html` in a browser.

## Deploy

Hosted on Cloudflare as Workers Static Assets (config in `wrangler.jsonc`):

```bash
python build.py
wrangler deploy
```

No origin server and no database — the whole site is static, served from the edge and entirely off the data engine's infrastructure. The only dynamic piece is the live-fuel Worker.

## Sources

- EC / CE Delft, *Handbook on the External Costs of Transport* (2019; EU-28, 2016 €).
- *Transport Taxes and Charges in Europe* (2019) — the ~48% car cost-coverage figure.
- KGP / ITS Polish road-crash statistics — moped vs. motorcycle severity split.
- GUS BDL — Gdańsk transport-budget figures for the "In practice" page.
- PL 2026 fuel excise (akcyza), opłata paliwowa, VAT, registration fees.
- [paliwo.today](https://paliwo.today) — live pump prices.

No marketplace data is used anywhere in this repo.
