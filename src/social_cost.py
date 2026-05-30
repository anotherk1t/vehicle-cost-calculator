"""Surface 2 — the "public money on you" calculator.

A personal fiscal balance sheet for a road vehicle: on one side what you *pay*
the Polish state for driving (fuel akcyza + opłata paliwowa + fuel VAT +
registration, minus any purchase subsidy), on the other what you *cost* society
(the EC/CE Delft external-cost coefficients: crashes, congestion, climate, air,
noise, upstream energy, land). The two reconcile into one number — the share of
your own road footprint you actually pay for — personalising the EU-28 ~48%
cost-coverage figure.

Unlike the depreciation page this needs **no tracker data** — it is pure
coefficients. So Python here is the single source of truth for the numbers
(constants + `compute_balance`, both unit-tested) and the rendered page embeds
the same constants for a vanilla-JS calculator that mirrors `compute_balance`
line-for-line. Keeping one spec on each side, tested on the Python side, is how
the economics stay honest.

Two deliberate honesty calls, both from memory/reference notes:
  * **Scooters are NOT a blended motorcycle.** The handbook splits two-wheelers
    only on emissions and applies one blended crash (12.7) + noise (9.0) value
    to everything from a moped to a litre sportbike. We give the 50/125 commuter
    its own profile with the crash term as a *band* (PL KGP death-rate-scaled
    lower bound ≈ 12.7/4 → blended upper bound) — never the blended point.
  * **EVs barely move the externality.** Zeroing the tailpipe leaves crashes +
    congestion (the bulk) untouched, so the cost side falls only ~20%, while the
    contribution side collapses (≈0 fuel tax + a purchase subsidy) → the state
    ends up covering *more* of an EV's footprint, not less. That inversion is
    the page's headline.

All figures are per-km, treating the careful single commuter as riding solo so
vehicle-km ≈ passenger-km (the handbook's unit). Everything is user-adjustable
in the UI — this is a model to argue with, not a verdict to accept.
"""

from __future__ import annotations

import json
import logging
import os

from src import ui
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Default build output directory (Cloudflare Pages serves this folder).
DEFAULT_OUTPUT_DIR = "public"

# --- economic constants ------------------------------------------------------
# External-cost coefficients: €-cent per km, EC/CE Delft "Handbook on the
# external costs of transport" 2019 (EU-28, 2016 prices, Tables 69/70/126).
# Component sums are checked against the published modal totals in the tests.

EUR_PLN_DEFAULT: float = 4.30  # NBP table-A ballpark; user-adjustable

# Order fixes the legend + bar stacking across every mode.
EXTERNAL_COMPONENTS: list[tuple[str, str]] = [
    ("accidents", "Crashes"),
    ("congestion", "Congestion"),
    ("climate", "Climate (CO₂)"),
    ("air", "Air pollution"),
    ("noise", "Noise"),
    ("wtt", "Energy supply"),
    ("habitat", "Land & habitat"),
]

# city congestion presets multiply the *congestion* component only (the single
# most place/time-specific externality — always a band, never a point).
CONGESTION_PRESETS: dict[str, dict] = {
    "rural": {"label": "Rural / off-peak", "factor": 0.12, "hint": "open roads, no jams"},
    "mixed": {"label": "Mixed urban (default)", "factor": 1.0, "hint": "EU-average blend"},
    "core": {"label": "Dense city, peak", "factor": 2.85, "hint": "Gdańsk centre, rush hour"},
}

# Per-mode profile. `external` is the baseline €-cent/km breakdown; `fuel` drives
# the contribution side; `crash_band`/`notes` carry the honesty caveats.
MODES: dict[str, dict] = {
    "car_petrol": {
        "label": "Car · petrol",
        "kind": "car",
        "external": {
            "accidents": 4.5,
            "congestion": 4.2,
            "climate": 1.2,
            "air": 0.3,
            "noise": 0.6,
            "wtt": 0.4,
            "habitat": 0.5,
        },
        "fuel": {"type": "petrol", "per100": 6.5},
        "notes": "Average EU petrol car. Air figure is petrol-specific (¼ of a diesel's).",
    },
    "car_diesel": {
        "label": "Car · diesel",
        "kind": "car",
        "external": {
            "accidents": 4.5,
            "congestion": 4.2,
            "climate": 1.2,
            "air": 1.2,
            "noise": 0.6,
            "wtt": 0.4,
            "habitat": 0.5,
        },
        "fuel": {"type": "diesel", "per100": 5.2},
        "notes": "Diesel air pollution is ~4× a petrol car's (NOx + fine particulates).",
    },
    "car_ev": {
        "label": "Car · electric",
        "kind": "car",
        "external": {
            "accidents": 4.5,
            "congestion": 4.2,
            "climate": 0.3,
            "air": 0.1,
            "noise": 0.2,
            "wtt": 0.2,
            "habitat": 0.5,
        },
        "fuel": {"type": "electric", "per100": 18.0},
        "subsidy_default": 18750,  # NaszEauto base grant, PLN
        "notes": "Tailpipe gone, but crashes + congestion (the bulk) are untouched "
        "— and an EV is heavier, so tyre/road particulates and crash energy "
        "partly persist. On Poland's coal-leaning grid climate isn't zero.",
    },
    "motorcycle": {
        "label": "Motorcycle · 125 cc+",
        "kind": "moto",
        "external": {
            "accidents": 12.7,
            "congestion": 0.0,
            "climate": 0.9,
            "air": 1.1,
            "noise": 9.0,
            "wtt": 0.5,
            "habitat": 0.3,
        },
        "fuel": {"type": "petrol", "per100": 4.5},
        "notes": "Filters traffic → zero congestion cost, but the blended PTW "
        "crash + noise terms dominate. Much of the crash cost is the rider's own risk.",
    },
    "scooter": {
        "label": "Scooter · 50–125 cc",
        "kind": "moto",
        "external": {
            "accidents": 7.0,
            "congestion": 0.0,
            "climate": 0.6,
            "air": 1.2,
            "noise": 4.5,
            "wtt": 0.4,
            "habitat": 0.2,
        },
        # KGP: moped severity 5.6 vs moto 10.1, ~4x lower death rate per vehicle.
        # Lower bound = blended 12.7 / 4; upper bound = the blended PTW figure.
        "crash_band": [3.2, 12.7],
        "fuel": {"type": "petrol", "per100": 3.0},
        "notes": "Given its own profile, NOT a blended motorbike. Crash cost shown as a "
        "band (PL death-rate-scaled → EU blend). Counterintuitively a small 2-stroke "
        "can out-pollute a bigger 4-stroke bike on local air.",
    },
}

# PL fuel-specific taxes, 2026 (zł per litre / per kWh). Adjustable in the UI.
FUEL_TAX: dict[str, dict] = {
    # specific = akcyza + opłata paliwowa; pump = typical gross price (for VAT).
    "petrol": {"specific": 1.529 + 0.18, "pump": 6.49},
    "diesel": {"specific": 1.145 + 0.38, "pump": 6.59},
    "electric": {"specific": 0.005, "pump": 1.05},  # akcyza on energy ≈ 5 zł/MWh
}
FUEL_VAT: float = 0.23
REGISTRATION_PLN_YR: int = 99  # przegląd + recurring fees, amortised
EV_SUBSIDY_HOLD_YEARS: int = 8  # NaszEauto grant amortised over assumed ownership

# Current-date caveat surfaced on the page.
FUEL_CUT_NOTE = (
    "Poland's temporary fuel VAT/akcyza reduction is scheduled to lapse 31 May 2026 "
    "— fuel-tax figures here use the standard rates."
)


# --- core computation (mirrored by the page's JS) ----------------------------


def _fuel_tax_per_unit(fuel_type: str, *, include_vat: bool) -> float:
    """zł of tax per litre (or per kWh) of the given fuel."""
    rates = FUEL_TAX[fuel_type]
    tax = rates["specific"]
    if include_vat:
        tax += rates["pump"] * FUEL_VAT / (1 + FUEL_VAT)
    return tax


def compute_balance(
    mode_key: str,
    annual_km: float,
    *,
    congestion: str = "mixed",
    eur_pln: float = EUR_PLN_DEFAULT,
    include_vat: bool = True,
    ev_subsidy: int | None = None,
    crash_bound: str = "point",
) -> dict:
    """Reconcile what you pay the state against what you cost it, per year.

    Returns external + contribution line-item breakdowns (PLN/yr), the coverage
    ratio (contribution / external) and the residual net public burden. The
    page's JS recomputes the same thing on every input change.
    """
    mode = MODES[mode_key]
    factor = CONGESTION_PRESETS[congestion]["factor"]

    # --- what you cost society (external) ---
    ext_items: list[dict] = []
    for key, label in EXTERNAL_COMPONENTS:
        cents = mode["external"][key]
        if key == "congestion":
            cents *= factor
        if key == "accidents" and "crash_band" in mode and crash_bound != "point":
            lo, hi = mode["crash_band"]
            cents = lo if crash_bound == "low" else hi
        pln = cents / 100 * eur_pln * annual_km
        if pln:
            ext_items.append({"key": key, "label": label, "pln": round(pln)})
    external_total = round(sum(i["pln"] for i in ext_items))

    # --- what you pay the state (contribution) ---
    fuel = mode["fuel"]
    tax_per_unit = _fuel_tax_per_unit(fuel["type"], include_vat=include_vat)
    fuel_tax_yr = tax_per_unit * fuel["per100"] / 100 * annual_km

    contrib_items: list[dict] = [
        {"key": "fuel_tax", "label": "Fuel tax", "pln": round(fuel_tax_yr)},
        {"key": "registration", "label": "Registration & przegląd", "pln": REGISTRATION_PLN_YR},
    ]
    if fuel["type"] == "electric":
        grant = mode.get("subsidy_default", 0) if ev_subsidy is None else ev_subsidy
        if grant:
            contrib_items.append(
                {
                    "key": "subsidy",
                    "label": "Purchase subsidy (amortised)",
                    "pln": -round(grant / EV_SUBSIDY_HOLD_YEARS),
                }
            )
    contribution_total = round(sum(i["pln"] for i in contrib_items))

    coverage_pct = round(100 * contribution_total / external_total, 1) if external_total else None
    net_burden = round(external_total - contribution_total)

    return {
        "mode": mode_key,
        "annual_km": annual_km,
        "external_items": ext_items,
        "external_total": external_total,
        "contribution_items": contrib_items,
        "contribution_total": contribution_total,
        "coverage_pct": coverage_pct,
        "net_burden": net_burden,
    }


# --- rendering ---------------------------------------------------------------


def _client_config() -> str:
    """The single source of truth, serialised for the page's JS."""
    return json.dumps(
        {
            "modes": MODES,
            "externalComponents": EXTERNAL_COMPONENTS,
            "congestionPresets": CONGESTION_PRESETS,
            "fuelTax": FUEL_TAX,
            "fuelVat": FUEL_VAT,
            "registration": REGISTRATION_PLN_YR,
            "evSubsidyHoldYears": EV_SUBSIDY_HOLD_YEARS,
            "eurPlnDefault": EUR_PLN_DEFAULT,
        },
        ensure_ascii=False,
    )


def render_social_cost(*, output_dir: str | None = None, filename: str = "index.html", now: int | None = None) -> str:
    """Build the public-cost calculator into `output_dir/filename`."""
    output_dir = output_dir or DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, filename)

    ts = now if now is not None else int(datetime.now(tz=UTC).timestamp())
    year = datetime.fromtimestamp(ts, tz=UTC).year

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_render_html(year=year))
    logger.info("Rendered public-cost calculator → %s", out_path)
    return out_path


_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Anton&family=IBM+Plex+Mono:wght@400;500;600&'
    'family=Newsreader:ital,wght@0,400;0,500;1,400&display=swap" rel="stylesheet">'
)

_STYLE = """
:root{
  --bg:#0b0c0e; --panel:#14161b; --panel-2:#0f1116; --ink:#ece8e1; --muted:#8b8a83;
  --line:#23252d; --credit:#28d6a3; --credit-dim:#15795e; --debit:#f35b04;
  --debit-2:#d62828; --gold:#f7b801; --paper:#1a1d23;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:"Newsreader",Georgia,serif; font-size:17px; line-height:1.55;
  -webkit-font-smoothing:antialiased;
}
body::before{
  content:""; position:fixed; inset:0; z-index:0; pointer-events:none; opacity:.045;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}
body::after{
  content:""; position:fixed; inset:0; z-index:0; pointer-events:none;
  background:radial-gradient(120% 70% at 80% -10%, rgba(40,214,163,.09), transparent 55%),
             radial-gradient(110% 70% at 0% 110%, rgba(243,91,4,.08), transparent 55%);
}
.wrap{position:relative; z-index:1; max-width:1120px; margin:0 auto; padding:0 22px 5rem}
.mono{font-family:"IBM Plex Mono",ui-monospace,monospace; font-variant-numeric:tabular-nums}

/* hero */
header{padding:5rem 0 2rem; border-bottom:1px solid var(--line)}
.kicker{font-family:"IBM Plex Mono",monospace; letter-spacing:.34em; text-transform:uppercase;
  font-size:.7rem; color:var(--credit); margin:0 0 1.1rem}
h1{font-family:"Anton",Impact,sans-serif; font-weight:400; text-transform:uppercase;
  font-size:clamp(2.7rem,8vw,5.8rem); line-height:.9; letter-spacing:.01em; margin:0;
  background:linear-gradient(95deg,var(--credit),var(--gold) 52%,var(--debit));
  -webkit-background-clip:text; background-clip:text; color:transparent;}
.dek{font-size:1.16rem; color:#cfcabf; max-width:50ch; margin:1.3rem 0 0; font-style:italic}
.rule{height:3px; margin:1.9rem 0 0; border-radius:2px;
  background:linear-gradient(90deg,var(--credit),var(--gold) 50%,var(--debit))}
.nav{display:flex; gap:.4rem 1.2rem; flex-wrap:wrap; margin-top:1.5rem;
  font-family:"IBM Plex Mono",monospace; font-size:.74rem}
.nav a{color:var(--muted); text-decoration:none; border-bottom:1px dotted transparent; padding-bottom:1px}
.nav a:hover{color:var(--credit); border-bottom-color:var(--credit)}
.nav a.here{color:var(--ink)}

/* controls */
.controls{margin-top:2.2rem; display:grid; grid-template-columns:1fr; gap:1.4rem}
.field label{font-family:"IBM Plex Mono",monospace; letter-spacing:.2em; text-transform:uppercase;
  font-size:.66rem; color:var(--muted); display:block; margin:0 0 .6rem}
.modes{display:flex; flex-wrap:wrap; gap:.5rem}
.mode-btn{font-family:"IBM Plex Mono",monospace; font-size:.82rem; color:var(--ink);
  background:var(--panel); border:1px solid var(--line); border-radius:999px;
  padding:.5rem 1rem; cursor:pointer; transition:.18s; letter-spacing:.02em}
.mode-btn:hover{border-color:var(--credit)}
.mode-btn[aria-pressed="true"]{background:var(--ink); color:#0b0c0e; border-color:var(--ink); font-weight:600}
.row{display:flex; gap:1.4rem; flex-wrap:wrap}
.row .field{flex:1; min-width:240px}
input[type=range]{width:100%; accent-color:var(--gold); cursor:pointer}
.kmline{display:flex; align-items:baseline; gap:.6rem; margin-bottom:.4rem}
.kmline b{font-family:"IBM Plex Mono",monospace; font-size:1.5rem; color:var(--ink)}
.kmline span{font-family:"IBM Plex Mono",monospace; font-size:.72rem; color:var(--muted)}
select{font-family:"IBM Plex Mono",monospace; font-size:.82rem; background:var(--panel);
  color:var(--ink); border:1px solid var(--line); border-radius:8px; padding:.5rem .7rem; width:100%}

/* verdict */
.verdict{margin-top:2.6rem; background:linear-gradient(180deg,var(--panel),var(--panel-2));
  border:1px solid var(--line); border-radius:16px; padding:1.8rem; overflow:hidden;
  box-shadow:0 30px 70px -40px rgba(0,0,0,.9)}
.verdict .head{font-family:"IBM Plex Mono",monospace; letter-spacing:.24em; text-transform:uppercase;
  font-size:.7rem; color:var(--muted)}
.bignum{font-family:"Anton",sans-serif; font-weight:400; line-height:.95; margin:.4rem 0 .2rem;
  font-size:clamp(3rem,11vw,6.4rem); letter-spacing:.01em}
.bignum.good{color:var(--credit)} .bignum.mid{color:var(--gold)} .bignum.bad{color:var(--debit)}
.verdict .say{font-size:1.18rem; color:#d7d2c7; max-width:60ch; margin:.2rem 0 0}
.verdict .say b{color:var(--ink)}

/* scale bar */
.scale{margin-top:1.6rem; height:30px; border-radius:8px; overflow:hidden; display:flex;
  border:1px solid var(--line); background:#0a0b0d}
.scale .paid{background:linear-gradient(90deg,var(--credit-dim),var(--credit)); transition:width .6s cubic-bezier(.2,.7,.2,1)}
.scale .owed{background:repeating-linear-gradient(45deg,rgba(243,91,4,.85),rgba(243,91,4,.85) 9px,rgba(214,40,40,.85) 9px,rgba(214,40,40,.85) 18px); transition:width .6s cubic-bezier(.2,.7,.2,1)}
.scalekey{display:flex; justify-content:space-between; margin-top:.5rem;
  font-family:"IBM Plex Mono",monospace; font-size:.72rem; color:var(--muted)}
.scalekey .c{color:var(--credit)} .scalekey .d{color:var(--debit)}

/* ledger */
.ledger{margin-top:1.8rem; display:grid; grid-template-columns:1fr 1fr; gap:1.1rem}
@media(max-width:720px){.ledger{grid-template-columns:1fr}}
.col{background:var(--paper); border:1px solid var(--line); border-radius:14px; padding:1.2rem 1.3rem}
.col.credit{border-top:3px solid var(--credit)}
.col.debit{border-top:3px solid var(--debit)}
.col h3{font-family:"Anton",sans-serif; font-weight:400; text-transform:uppercase; letter-spacing:.03em;
  font-size:1.25rem; margin:.1rem 0 .1rem}
.col.credit h3{color:var(--credit)} .col.debit h3{color:var(--debit)}
.col .csub{font-family:"IBM Plex Mono",monospace; font-size:.72rem; color:var(--muted); margin:0 0 1rem}
.item{margin:.5rem 0}
.item .top{display:flex; justify-content:space-between; align-items:baseline; gap:1rem;
  font-family:"IBM Plex Mono",monospace; font-size:.84rem}
.item .top .v{color:var(--ink); font-variant-numeric:tabular-nums}
.item .top .v.neg{color:var(--credit)}
.item .meter{height:7px; border-radius:5px; margin-top:.35rem; background:#0a0b0d; overflow:hidden}
.item .meter i{display:block; height:100%; border-radius:5px; transition:width .5s ease}
.col.credit .meter i{background:var(--credit)}
.col.debit .meter i{background:linear-gradient(90deg,var(--gold),var(--debit))}
.col .sum{display:flex; justify-content:space-between; margin-top:1.1rem; padding-top:.8rem;
  border-top:1px solid var(--line); font-family:"IBM Plex Mono",monospace; font-weight:600}
.col .sum .v{font-size:1.15rem}
.col.credit .sum .v{color:var(--credit)} .col.debit .sum .v{color:var(--debit)}

/* sections + notes */
section{margin-top:3rem}
.eyebrow{font-family:"IBM Plex Mono",monospace; letter-spacing:.28em; text-transform:uppercase;
  font-size:.72rem; color:var(--muted); display:flex; align-items:center; gap:.8rem}
.eyebrow::before{content:""; width:26px; height:2px; background:var(--credit)}
h2{font-family:"Anton",sans-serif; font-weight:400; text-transform:uppercase; letter-spacing:.02em;
  font-size:1.8rem; margin:.5rem 0 .4rem}
.lede{color:var(--muted); margin:.1rem 0 1.1rem; max-width:66ch}
.modenote{font-style:italic; color:#cfcabf; border-left:3px solid var(--gold);
  padding:.4rem 0 .4rem 1rem; margin:.2rem 0 0; font-size:1.02rem}

details.adv{margin-top:1.6rem; border:1px solid var(--line); border-radius:12px; background:var(--panel-2)}
details.adv summary{cursor:pointer; padding:.9rem 1.2rem; font-family:"IBM Plex Mono",monospace;
  letter-spacing:.18em; text-transform:uppercase; font-size:.72rem; color:var(--muted)}
details.adv[open] summary{color:var(--ink); border-bottom:1px solid var(--line)}
.advgrid{padding:1.2rem; display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:1.1rem}
.advgrid .field input[type=number]{width:100%; font-family:"IBM Plex Mono",monospace; font-size:.9rem;
  background:var(--panel); color:var(--ink); border:1px solid var(--line); border-radius:8px; padding:.5rem .6rem}
.advgrid .chk{display:flex; align-items:center; gap:.55rem; font-family:"IBM Plex Mono",monospace; font-size:.8rem; color:var(--ink)}
.advgrid .chk input{accent-color:var(--credit); width:16px; height:16px}

.note{border-left:3px solid var(--credit); background:rgba(40,214,163,.05);
  padding:1.1rem 1.4rem; border-radius:0 12px 12px 0; color:#cfcabf; font-size:1.02rem}
.note h2{font-size:1.45rem; margin:.1rem 0 .5rem}
.note ul{margin:.6rem 0 0; padding-left:1.1rem} .note li{margin:.5rem 0} .note b{color:var(--ink)}
.flag{font-family:"IBM Plex Mono",monospace; font-size:.78rem; color:var(--gold);
  border:1px dashed rgba(247,184,1,.4); border-radius:8px; padding:.6rem .9rem; margin-top:1.2rem}

footer{margin-top:3.4rem; padding-top:1.4rem; border-top:1px solid var(--line);
  font-family:"IBM Plex Mono",monospace; font-size:.74rem; color:var(--muted); line-height:1.7}

@keyframes rise{from{opacity:0; transform:translateY(16px)} to{opacity:1; transform:none}}
.reveal{animation:rise .7s cubic-bezier(.2,.7,.2,1) both}
@media (prefers-reduced-motion:reduce){.reveal{animation:none} .scale i,.scale div,.item .meter i{transition:none}}
"""


STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "veh_moto": "Moto", "veh_car": "Car",
        "h1": "Who pays<br>for your ride?",
        "dek": "Every kilometre you drive, you hand the state some tax and impose some cost on everyone else. This reconciles the two — and shows the share of your own footprint you actually cover.",
        "nav_cost": "Personal cost", "nav_ledger": "Public-money ledger", "nav_depr": "Depreciation curves",
        "lbl_vehicle": "Vehicle", "lbl_km": "Distance per year", "km_year": "km / year",
        "lbl_congestion": "Where you drive (congestion)", "assumptions": "Assumptions — adjust the model",
        "verdict_head": "The verdict — share of your road footprint you pay for",
        "credit_h": "What you pay the state", "debit_h": "What you cost society",
        "ext_accidents": "Crashes", "ext_congestion": "Congestion", "ext_climate": "Climate (CO₂)",
        "ext_air": "Air pollution", "ext_noise": "Noise", "ext_wtt": "Energy supply", "ext_habitat": "Land & habitat",
        "cr_fuel": "Fuel tax", "cr_reg": "Registration & przegląd", "cr_sub": "Purchase subsidy (amortised)",
        "say_none": "No measurable footprint.",
        "say_recipient": "The state spends more <b>on</b> you than you cost it — a net <b>recipient</b> of public money, while your footprint stays {ext}/yr.",
        "say_cover": "You cover <b>{cov}%</b> of the <b>{ext}/yr</b> you cost everyone else. The remaining <b>{net}/yr</b> is carried by the public across {km} km.",
    },
    "pl": {
        "veh_moto": "Moto", "veh_car": "Auto",
        "h1": "Kto płaci<br>za Twoją jazdę?",
        "dek": "Za każdy przejechany kilometr płacisz państwu podatek i nakładasz koszt na resztę. To zestawia jedno z drugim — i pokazuje, jaką część własnego śladu faktycznie pokrywasz.",
        "nav_cost": "Koszt osobisty", "nav_ledger": "Bilans publiczny", "nav_depr": "Krzywe wartości",
        "lbl_vehicle": "Pojazd", "lbl_km": "Dystans rocznie", "km_year": "km / rok",
        "lbl_congestion": "Gdzie jeździsz (zatłoczenie)", "assumptions": "Założenia — dostosuj model",
        "verdict_head": "Werdykt — jaką część swojego śladu drogowego pokrywasz",
        "credit_h": "Ile płacisz państwu", "debit_h": "Ile kosztujesz społeczeństwo",
        "ext_accidents": "Wypadki", "ext_congestion": "Zatłoczenie", "ext_climate": "Klimat (CO₂)",
        "ext_air": "Zanieczyszczenie powietrza", "ext_noise": "Hałas", "ext_wtt": "Dostawa energii", "ext_habitat": "Ziemia i środowisko",
        "cr_fuel": "Podatek paliwowy", "cr_reg": "Rejestracja i przegląd", "cr_sub": "Dopłata do zakupu (amortyzowana)",
        "say_none": "Brak mierzalnego śladu.",
        "say_recipient": "Państwo wydaje na Ciebie więcej niż Ty kosztujesz — jesteś netto <b>beneficjentem</b> publicznych pieniędzy, a Twój ślad to {ext}/rok.",
        "say_cover": "Pokrywasz <b>{cov}%</b> z <b>{ext}/rok</b>, które kosztujesz innych. Pozostałe <b>{net}/rok</b> ponosi ogół na {km} km.",
    },
}

# Vehicle-aware + i18n ledger JS (raw, single braces). CFG/UI/_t/fmt supplied.
_LEDGER_JS = r"""
const PLN = n => (n<0?"−":"") + Math.abs(Math.round(n)).toLocaleString("pl-PL") + " zł";
const $ = id => document.getElementById(id);
const modesForVeh = () => Object.entries(CFG.modes).filter(([k,m]) => UI.veh==="car" ? m.kind==="car" : m.kind!=="car");

const state = {mode:null, km:12000, congestion:"mixed", eur:CFG.eurPlnDefault, vat:true, subsidy:18750, crash:"point"};

function fuelTaxPerUnit(type, vat){ const r = CFG.fuelTax[type]; let t = r.specific; if(vat) t += r.pump * CFG.fuelVat/(1+CFG.fuelVat); return t; }

function compute(){
  const m = CFG.modes[state.mode];
  const factor = CFG.congestionPresets[state.congestion].factor;
  const ext = [];
  for(const [key,label] of CFG.externalComponents){
    let cents = m.external[key];
    if(key==="congestion") cents *= factor;
    if(key==="accidents" && m.crash_band && state.crash!=="point") cents = state.crash==="low" ? m.crash_band[0] : m.crash_band[1];
    const pln = cents/100 * state.eur * state.km;
    if(pln) ext.push({key, label:(_t("ext_"+key)||label), pln});
  }
  const extTotal = ext.reduce((a,i)=>a+i.pln,0);
  const f = m.fuel;
  const taxUnit = fuelTaxPerUnit(f.type, state.vat);
  const cred = [
    {key:"fuel_tax", label:(_t("cr_fuel")||"Fuel tax"), pln: taxUnit*f.per100/100*state.km},
    {key:"reg", label:(_t("cr_reg")||"Registration & przegląd"), pln: CFG.registration},
  ];
  if(f.type==="electric" && state.subsidy)
    cred.push({key:"subsidy", label:(_t("cr_sub")||"Purchase subsidy (amortised)"), pln: -(state.subsidy/CFG.evSubsidyHoldYears)});
  const credTotal = cred.reduce((a,i)=>a+i.pln,0);
  return {ext, extTotal, cred, credTotal, coverage: extTotal ? 100*credTotal/extTotal : null, net: extTotal - credTotal};
}

function bars(items, total, el){
  const peak = Math.max(...items.map(i=>Math.abs(i.pln)), 1);
  el.innerHTML = items.map(i=>{
    const neg = i.pln<0;
    return `<div class="item"><div class="top"><span>${i.label}</span><span class="v ${neg?'neg':''}">${PLN(i.pln)}</span></div><div class="meter"><i style="width:${Math.abs(i.pln)/peak*100}%"></i></div></div>`;
  }).join("");
}

function render(){
  const r = compute();
  bars(r.ext, r.extTotal, $("debitItems"));
  bars(r.cred, r.credTotal, $("creditItems"));
  $("debitTotal").textContent = PLN(r.extTotal) + " /yr";
  $("creditTotal").textContent = PLN(r.credTotal) + " /yr";
  const cov = r.coverage, covEl = $("coverage"), say = $("verdictSay");
  covEl.className = "bignum mono " + (cov===null?"mid":cov<0?"bad":cov<60?"bad":cov<100?"mid":"good");
  covEl.textContent = cov===null ? "—" : Math.round(cov)+"%";
  const paid = Math.max(0, Math.min(100, cov===null?0:cov));
  $("scalePaid").style.width = paid+"%"; $("scaleOwed").style.width = (100-paid)+"%";
  const km = state.km.toLocaleString("pl-PL");
  if(cov===null) say.innerHTML = _t("say_none")||"No measurable footprint.";
  else if(cov<0) say.innerHTML = fmt(_t("say_recipient")||"The state spends more <b>on</b> you than you cost it — a net <b>recipient</b> of public money, while your footprint stays {ext}/yr.", {ext:PLN(r.extTotal)});
  else say.innerHTML = fmt(_t("say_cover")||"You cover <b>{cov}%</b> of the <b>{ext}/yr</b> you cost everyone else. The remaining <b>{net}/yr</b> is carried by the public across {km} km.", {cov:Math.round(cov), ext:PLN(r.extTotal), net:PLN(r.net), km});
  $("modeNote").textContent = CFG.modes[state.mode].notes;
}

function buildModes(){
  const ms = modesForVeh();
  if(!ms.find(([k])=>k===state.mode)) state.mode = ms[0][0];
  $("modes").innerHTML = ms.map(([k,m])=>`<button class="mode-btn" data-mode="${k}" aria-pressed="${k===state.mode}">${m.label}</button>`).join("");
  render();
}

$("modes").addEventListener("click", e=>{ const b=e.target.closest(".mode-btn"); if(!b) return; state.mode=b.dataset.mode; document.querySelectorAll(".mode-btn").forEach(x=>x.setAttribute("aria-pressed", x===b)); render(); });
$("km").addEventListener("input", e=>{ state.km=+e.target.value; $("kmval").textContent = state.km.toLocaleString("pl-PL"); render(); });
$("congestion").addEventListener("change", e=>{ state.congestion=e.target.value; render(); });
$("eur").addEventListener("input", e=>{ state.eur=+e.target.value||CFG.eurPlnDefault; render(); });
$("subsidy").addEventListener("input", e=>{ state.subsidy=+e.target.value||0; render(); });
$("crash").addEventListener("change", e=>{ state.crash=e.target.value; render(); });
$("vat").addEventListener("change", e=>{ state.vat=e.target.checked; render(); });
window.addEventListener("uichange", buildModes);
buildModes();
"""


def _render_html(*, year: int) -> str:
    config = _client_config()
    selector_bar = ui.selector_bar()
    strings_json = json.dumps(STRINGS, ensure_ascii=False)
    congestion_opts = "".join(
        f'<option value="{k}"{" selected" if k == "mixed" else ""}>{p["label"]} · {p["hint"]}</option>'
        for k, p in CONGESTION_PRESETS.items()
    )

    return (
        f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>What the road costs · your public ledger · PL</title>
{_FONTS}
<style>{_STYLE}{ui.SELECTOR_CSS}</style>
</head>
<body>
<div class="wrap">
<header class="reveal">
  {selector_bar}
  <p class="kicker">Poland · personal road ledger · {year}</p>
  <h1 data-i18n-html="h1">Who pays<br>for your ride?</h1>
  <p class="dek" data-i18n="dek">Every kilometre you drive, you hand the state some tax and impose
  some cost on everyone else. This reconciles the two — and shows the share of
  your own footprint you actually cover.</p>
  <div class="rule"></div>
  <nav class="nav">
    <a href="cost.html" data-i18n="nav_cost">Personal cost</a>
    <a href="index.html" class="here" data-i18n="nav_ledger">Public-money ledger</a>
    <a href="depreciation.html" data-i18n="nav_depr">Depreciation curves</a>
  </nav>

  <div class="controls">
    <div class="field">
      <label data-i18n="lbl_vehicle">Vehicle</label>
      <div class="modes" id="modes"></div>
    </div>
    <div class="row">
      <div class="field">
        <label data-i18n="lbl_km">Distance per year</label>
        <div class="kmline"><b class="mono" id="kmval">12 000</b><span data-i18n="km_year">km / year</span></div>
        <input type="range" id="km" min="1000" max="40000" step="500" value="12000">
      </div>
      <div class="field">
        <label data-i18n="lbl_congestion">Where you drive (congestion)</label>
        <select id="congestion">{congestion_opts}</select>
      </div>
    </div>
  </div>
</header>

<div class="verdict reveal" style="animation-delay:.08s">
  <div class="head" data-i18n="verdict_head">The verdict — share of your road footprint you pay for</div>
  <div class="bignum mono mid" id="coverage">—</div>
  <p class="say" id="verdictSay"></p>
  <div class="scale" id="scale">
    <div class="paid" id="scalePaid" style="width:0%"></div>
    <div class="owed" id="scaleOwed" style="width:100%"></div>
  </div>
  <div class="scalekey">
    <span class="c">▰ you pay</span>
    <span class="d">everyone else covers ▱</span>
  </div>
  <p class="modenote" id="modeNote"></p>
</div>

<div class="ledger reveal" style="animation-delay:.12s">
  <div class="col credit">
    <h3 data-i18n="credit_h">What you pay the state</h3>
    <p class="csub">akcyza · opłata paliwowa · VAT · fees − subsidy</p>
    <div id="creditItems"></div>
    <div class="sum"><span>Per year</span><span class="v mono" id="creditTotal">—</span></div>
  </div>
  <div class="col debit">
    <h3 data-i18n="debit_h">What you cost society</h3>
    <p class="csub">EC/CE Delft external-cost coefficients</p>
    <div id="debitItems"></div>
    <div class="sum"><span>Per year</span><span class="v mono" id="debitTotal">—</span></div>
  </div>
</div>

<details class="adv reveal" style="animation-delay:.16s">
  <summary data-i18n="assumptions">Assumptions — adjust the model</summary>
  <div class="advgrid">
    <div class="field"><label>EUR → PLN rate</label>
      <input type="number" id="eur" step="0.01" value="4.30"></div>
    <div class="field"><label>EV purchase subsidy (PLN)</label>
      <input type="number" id="subsidy" step="250" value="18750"></div>
    <div class="field"><label>Scooter crash estimate</label>
      <select id="crash">
        <option value="point" selected>Mid (PL-scaled)</option>
        <option value="low">Low · death-rate floor</option>
        <option value="high">High · EU blended</option>
      </select></div>
    <div class="field"><label class="chk"><input type="checkbox" id="vat" checked> count fuel VAT</label>
      <span class="csub" style="display:block;margin-top:.5rem">Off = fuel-specific taxes only</span></div>
  </div>
</details>

<section class="reveal">
  <p class="eyebrow">The twist</p>
  <h2>Going electric covers <em>less</em>, not more</h2>
  <p class="lede">Switch the vehicle to <b>electric</b>. The cost side barely
  moves — crashes and congestion are most of it and an EV imposes both — yet
  the payment side collapses: almost no fuel tax, plus a purchase grant. The
  result inverts the intuition: the public covers a <em>bigger</em> share of an
  EV's footprint than a petrol car's. That is a deliberate decarbonisation
  subsidy, not a free lunch — worth seeing plainly.</p>
  <div class="note">
    <h2>How to read this</h2>
    <ul>
      <li><b>Per kilometre, solo.</b> Costs are the handbook's per-passenger-km
      figures treated as per-km for a single rider — your real footprint if you
      drive alone. Carpooling lowers the per-person cost.</li>
      <li><b>Congestion is a band, never a point.</b> It's the most place- and
      time-specific cost; the selector swings it from open road to rush-hour core.
      Two-wheelers filter traffic, so theirs stays zero — which is where a
      scooter quietly wins a dense city.</li>
      <li><b>A scooter isn't a free angel.</b> Given its own profile it still
      carries real crash cost — but much of that risk is the rider's own, and
      most of the rest is imposed <em>by</em> car drivers.</li>
      <li><b>This is a model to argue with.</b> Every rate above is editable.</li>
    </ul>
  </div>
  <div class="flag">⚠ {FUEL_CUT_NOTE}</div>
</section>

<footer>
  <div>METHOD · external costs: EC/CE Delft Handbook on the external costs of transport 2019 (EU-28, 2016 €), per-km, solo occupancy. Congestion scaled by a city band.</div>
  <div>CONTRIBUTION · PL 2026 akcyza + opłata paliwowa + (optional) fuel VAT + recurring registration; EV purchase grant amortised over {EV_SUBSIDY_HOLD_YEARS} years.</div>
  <div>SCOOTER SPLIT · KGP/ITS PL crash data (moped vs motorcycle severity) rescales the blended PTW crash term. Coverage % personalises the EU-28 ~48% figure (Transport taxes &amp; charges in Europe 2019).</div>
  <div>No marketplace data used · public coefficients only.</div>
</footer>
</div>
"""
        + "<script>\nconst CFG = " + config + ";\nwindow.T = " + strings_json + ";\n"
        + ui.SELECTOR_JS + "\n" + _LEDGER_JS + "</script>\n</body>\n</html>\n"
    )
