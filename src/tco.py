"""Surface 1 — the personal total-cost-of-ownership calculator.

The spine of the product. Every other surface orbits this one: "what will this
bike actually cost me per year, and per kilometre, once I stop pretending the
sticker price is the whole story?"

The honest, hard-won half is **depreciation**, and we own it — it is read off
the engine's `aggregates.json` (the same smoothed value-vs-age curves the
depreciation page draws). Capital loss over a hold window is usually 40–60% of
true cost and is the part nobody else localises for the PL used market. The rest
(fuel, the maintenance/wear reserve, fees, the PCC purchase tax) are bolt-on
coefficients — modelled, shown as a band, and fully user-adjustable. Insurance is
the one thing we refuse to model: the user pastes their own quote.

Like Surface 2 this is static and client-side. Python holds the coefficients as
the single source of truth (`compute_tco`, unit-tested) and the rendered page
embeds the same constants for a vanilla-JS calculator that mirrors the function
line-for-line, plus the engine's aggregates JSON for the depreciation lookup.

One panel — the *seasonal* buy/sell timing ("buy in February, sell in May") — is
deliberately stubbed as "coming soon": it is the only piece that needs a full
season of banked data to be honest, and that season is still accumulating.
"""

from __future__ import annotations

import json
import logging
import os

from src import ui

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = "public"
DEFAULT_AGGREGATES = os.path.join("data", "aggregates.json")
DEFAULT_CAR_AGGREGATES = os.path.join("data", "cars_aggregates.json")

# --- coefficient constants (mirrored by the page's JS) -----------------------
# Everything here is a default the user can override in the UI. The numbers are
# deliberately conservative PL used-market ballparks, not precise per-model data
# — the calculator is a band, never a false-precision point.

PUMP_PETROL_PLN: float = 6.49  # zł/litre, 95-oct, standard rate (no temp cut)
PCC_RATE: float = 0.02  # podatek od czynności cywilnoprawnych on a private buy
REGISTRATION_PLN_YR: float = 99.0  # przegląd + recurring registration, amortised
SERVICE_AGE_K: float = 0.045  # the wear reserve grows ~4.5% per year of bike age
SERVICE_BAND: float = 0.35  # ± on the maintenance/wear reserve → the cost band

# Per riding-category defaults (fuel / service / insurance). Keys MUST match the
# engine's `category` taxonomy so a category selection maps onto its curve, and a
# specific model inherits its category's coefficients. All user-adjustable in the UI.
CATEGORY_ORDER: list[str] = [
    "scooter",
    "maxi_scooter",
    "moped",
    "naked",
    "sport",
    "touring",
    "adventure",
    "cruiser",
    "enduro",
]
CATEGORY_DEFAULTS: dict[str, dict] = {
    "moped": {"label": "Moped ≤50", "tag": "city / A", "fuel_per100": 2.5, "service_per1000": 45, "insurance_yr": 300},
    "scooter": {"label": "Scooter", "tag": "commuter", "fuel_per100": 3.0, "service_per1000": 55, "insurance_yr": 350},
    "maxi_scooter": {"label": "Maxi-scooter", "tag": "motorway scooter", "fuel_per100": 4.0, "service_per1000": 90, "insurance_yr": 550},
    "naked": {"label": "Naked", "tag": "roadster / standard", "fuel_per100": 4.5, "service_per1000": 95, "insurance_yr": 650},
    "sport": {"label": "Sport", "tag": "supersport", "fuel_per100": 5.2, "service_per1000": 120, "insurance_yr": 950},
    "touring": {"label": "Touring", "tag": "sport-tourer / GT", "fuel_per100": 5.0, "service_per1000": 110, "insurance_yr": 800},
    "adventure": {"label": "Adventure", "tag": "ADV / GS-style", "fuel_per100": 4.8, "service_per1000": 120, "insurance_yr": 800},
    "cruiser": {"label": "Cruiser", "tag": "cruiser / chopper", "fuel_per100": 5.0, "service_per1000": 100, "insurance_yr": 700},
    "enduro": {"label": "Enduro", "tag": "dual-sport / SM", "fuel_per100": 4.2, "service_per1000": 100, "insurance_yr": 600},
}

# Car running-cost coefficients, keyed by fuel (the dominant car cost driver).
# per100 = litres (or kWh for EV) / 100 km; pump = zł per litre (or per kWh).
CAR_FUEL_DEFAULTS: dict[str, dict] = {
    "petrol": {"label": "Petrol", "per100": 7.0, "pump": 6.49, "unit": "l"},
    "diesel": {"label": "Diesel", "per100": 5.5, "pump": 6.59, "unit": "l"},
    "petrol-lpg": {"label": "LPG", "per100": 9.0, "pump": 2.80, "unit": "l"},
    "hybrid": {"label": "Hybrid", "per100": 4.8, "pump": 6.49, "unit": "l"},
    "plugin-hybrid": {"label": "Plug-in hybrid", "per100": 3.5, "pump": 6.49, "unit": "l"},
    "electric": {"label": "Electric", "per100": 17.0, "pump": 1.10, "unit": "kWh"},
}
CAR_SERVICE_PER1000: float = 130.0  # zł reserve / 1000 km (cars run dearer than bikes)
CAR_INSURANCE_YR: float = 2200.0  # OC/AC ballpark; user pastes a real quote

# Stable colour per cost component (the receipt's ink). Depreciation is the
# dominant, alarming slice; the modelled costs cool down from there.
COMPONENT_ORDER: list[tuple[str, str]] = [
    ("depreciation", "Depreciation"),
    ("fuel", "Fuel"),
    ("service", "Service & wear"),
    ("insurance", "Insurance (OC/AC)"),
    ("fees", "Fees & PCC tax"),
]
COMPONENT_COLORS: dict[str, str] = {
    "depreciation": "#f35b04",
    "fuel": "#f7b801",
    "service": "#4cc9f0",
    "insurance": "#9d7bff",
    "fees": "#6b7280",
}


# --- core computation (mirrored by the page's JS) ----------------------------


def _interp(curve: list[dict], age: float) -> float | None:
    """Linear-interpolate the smoothed value curve at an arbitrary age.

    `curve` is a class's `points` list (each with `age` + `smooth`), sorted by
    age. Ages outside the tracked range clamp to the nearest endpoint — we never
    extrapolate a curve we have no data for.
    """
    if not curve:
        return None
    pts = sorted(curve, key=lambda p: p["age"])
    if age <= pts[0]["age"]:
        return float(pts[0]["smooth"])
    if age >= pts[-1]["age"]:
        return float(pts[-1]["smooth"])
    for i in range(1, len(pts)):
        if age <= pts[i]["age"]:
            x0, y0 = pts[i - 1]["age"], pts[i - 1]["smooth"]
            x1, y1 = pts[i]["age"], pts[i]["smooth"]
            t = (age - x0) / (x1 - x0) if x1 != x0 else 0.0
            return float(y0 + t * (y1 - y0))
    return float(pts[-1]["smooth"])


def compute_tco(
    *,
    curve: list[dict],
    age: float,
    hold_years: float,
    annual_km: float,
    fuel_per100: float,
    service_per1000: float,
    insurance_yr: float,
    price_paid: float | None = None,
    pump_price: float = PUMP_PETROL_PLN,
    pcc_rate: float = PCC_RATE,
    registration_yr: float = REGISTRATION_PLN_YR,
    service_age_k: float = SERVICE_AGE_K,
    service_band: float = SERVICE_BAND,
) -> dict:
    """Reconcile the real annual cost of owning one bike over a hold window.

    Depreciation comes from the engine's curve (scaled if the user paid a price
    different from the fitted value); the rest are coefficient models. Returns
    per-year line items (PLN), a total with a ± band from the wear reserve, the
    cost per kilometre and the depreciation share. The page's JS recomputes the
    identical thing on every input change.
    """
    base_now = _interp(curve, age)
    base_later = _interp(curve, age + hold_years)
    if base_now is None or base_later is None:
        return {"ok": False}

    paid = float(price_paid) if price_paid is not None else base_now
    scale = paid / base_now if base_now else 1.0
    value_end = base_later * scale
    depreciation_total = max(0.0, paid - value_end)
    depr_yr = depreciation_total / hold_years if hold_years else 0.0

    fuel_yr = fuel_per100 / 100 * annual_km * pump_price

    # The wear reserve grows with the bike's *average* age across the hold.
    avg_age = age + hold_years / 2
    service_yr = service_per1000 * (annual_km / 1000) * (1 + service_age_k * avg_age)

    pcc_yr = paid * pcc_rate / hold_years if hold_years else 0.0
    fees_yr = registration_yr + pcc_yr

    raw = {
        "depreciation": depr_yr,
        "fuel": fuel_yr,
        "service": service_yr,
        "insurance": insurance_yr,
        "fees": fees_yr,
    }
    items = [{"key": k, "label": lbl, "pln": round(raw[k])} for k, lbl in COMPONENT_ORDER]
    total = round(sum(raw.values()))

    # Only the service/wear reserve is genuinely uncertain → it sets the band.
    band = service_yr * service_band
    total_lo = round(total - band)
    total_hi = round(total + band)

    per_km = total / annual_km if annual_km else 0.0
    depr_share = round(100 * raw["depreciation"] / total) if total else 0

    return {
        "ok": True,
        "paid": round(paid),
        "value_end": round(value_end),
        "age": age,
        "hold_years": hold_years,
        "annual_km": annual_km,
        "items": items,
        "total": total,
        "total_lo": total_lo,
        "total_hi": total_hi,
        "lifetime": round(total * hold_years),
        "per_km": round(per_km, 2),
        "depr_share": depr_share,
    }


# --- rendering ---------------------------------------------------------------


def _client_config() -> str:
    """The coefficient source of truth, serialised for the page's JS."""
    return json.dumps(
        {
            "categoryDefaults": CATEGORY_DEFAULTS,
            "categoryOrder": CATEGORY_ORDER,
            "carFuel": CAR_FUEL_DEFAULTS,
            "carService": CAR_SERVICE_PER1000,
            "carInsurance": CAR_INSURANCE_YR,
            "componentOrder": COMPONENT_ORDER,
            "componentColors": COMPONENT_COLORS,
            "pumpPetrol": PUMP_PETROL_PLN,
            "pccRate": PCC_RATE,
            "registration": REGISTRATION_PLN_YR,
            "serviceAgeK": SERVICE_AGE_K,
            "serviceBand": SERVICE_BAND,
        },
        ensure_ascii=False,
    )


def render_tco(
    aggregates_path: str | None = None,
    *,
    car_aggregates_path: str | None = None,
    output_dir: str | None = None,
    filename: str = "cost.html",
) -> str:
    """Render the personal TCO calculator into `output_dir/filename`.

    Reads the engine's `aggregates.json` for the depreciation curves. If it is
    missing or empty the page still renders, with the depreciation engine shown
    as awaiting data (the coefficient costs alone would be a half-truth, so the
    calculator gates on a curve being present).
    """
    output_dir = output_dir or DEFAULT_OUTPUT_DIR
    aggregates_path = aggregates_path or DEFAULT_AGGREGATES
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, filename)

    agg: dict = {"meta": {}, "classes": {}}
    if os.path.exists(aggregates_path):
        with open(aggregates_path, encoding="utf-8") as f:
            agg = json.load(f)
    else:
        logger.warning("%s missing — TCO page will render without curves", aggregates_path)

    car_path = car_aggregates_path or DEFAULT_CAR_AGGREGATES
    car_agg: dict = {"meta": {}, "models": {}, "fuels": {}}
    if os.path.exists(car_path):
        with open(car_path, encoding="utf-8") as f:
            car_agg = json.load(f)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_render_html(agg, car_agg))
    logger.info("Rendered TCO calculator → %s", out_path)
    return out_path


_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Anton&family=IBM+Plex+Mono:wght@400;500;600&'
    'family=Newsreader:ital,wght@0,400;0,500;1,400&display=swap" rel="stylesheet">'
)

_STYLE = """
:root{
  --bg:#0b0b0f; --panel:#15151d; --panel-2:#0f0f15; --ink:#ece8e1; --muted:#8d8a83;
  --line:#24242e; --violet:#9d7bff; --violet-dim:#5b46a8; --orange:#f35b04;
  --amber:#f7b801; --cyan:#4cc9f0; --red:#d62828; --paper:#191921;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0; background:var(--bg); color:var(--ink);
  font-family:"Newsreader",Georgia,serif; font-size:17px; line-height:1.55; -webkit-font-smoothing:antialiased}
body::before{content:""; position:fixed; inset:0; z-index:0; pointer-events:none; opacity:.05;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.82' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
body::after{content:""; position:fixed; inset:0; z-index:0; pointer-events:none;
  background:radial-gradient(120% 75% at 85% -10%, rgba(157,123,255,.10), transparent 55%),
             radial-gradient(110% 70% at -5% 110%, rgba(243,91,4,.07), transparent 55%)}
.wrap{position:relative; z-index:1; max-width:1120px; margin:0 auto; padding:0 22px 5rem}
.mono{font-family:"IBM Plex Mono",ui-monospace,monospace; font-variant-numeric:tabular-nums}

/* hero */
header{padding:5rem 0 2rem; border-bottom:1px solid var(--line)}
.kicker{font-family:"IBM Plex Mono",monospace; letter-spacing:.34em; text-transform:uppercase;
  font-size:.7rem; color:var(--violet); margin:0 0 1.1rem}
h1{font-family:"Anton",Impact,sans-serif; font-weight:400; text-transform:uppercase;
  font-size:clamp(2.8rem,8.5vw,6rem); line-height:.9; letter-spacing:.01em; margin:0;
  background:linear-gradient(95deg,var(--violet),var(--amber) 55%,var(--orange));
  -webkit-background-clip:text; background-clip:text; color:transparent}
.dek{font-size:1.16rem; color:#cfcabf; max-width:50ch; margin:1.3rem 0 0; font-style:italic}
.rule{height:3px; margin:1.9rem 0 0; border-radius:2px;
  background:linear-gradient(90deg,var(--violet),var(--amber) 55%,var(--orange))}
.nav{display:flex; gap:.4rem 1.2rem; flex-wrap:wrap; margin-top:1.5rem;
  font-family:"IBM Plex Mono",monospace; font-size:.74rem}
.nav a{color:var(--muted); text-decoration:none; border-bottom:1px dotted transparent; padding-bottom:1px}
.nav a:hover{color:var(--violet); border-bottom-color:var(--violet)}
.nav a.here{color:var(--ink)}

/* controls */
.controls{margin-top:2.4rem; display:grid; gap:1.5rem}
.field label{font-family:"IBM Plex Mono",monospace; letter-spacing:.2em; text-transform:uppercase;
  font-size:.66rem; color:var(--muted); display:block; margin:0 0 .6rem}
.modes{display:flex; flex-wrap:wrap; gap:.5rem}
.mode-btn{font-family:"IBM Plex Mono",monospace; font-size:.82rem; color:var(--ink); text-align:left;
  background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:.55rem .9rem;
  cursor:pointer; transition:.18s; line-height:1.2}
.mode-btn small{display:block; color:var(--muted); font-size:.66rem; margin-top:2px}
.mode-btn:hover{border-color:var(--violet)}
.mode-btn[aria-pressed="true"]{background:var(--ink); color:#0b0b0f; border-color:var(--ink)}
.mode-btn[aria-pressed="true"] small{color:#3a3a3a}
.heldnote{font-family:"IBM Plex Mono",monospace; font-size:.72rem; color:var(--muted); margin:.7rem 0 0}
.heldnote b{color:var(--amber)}
.modelsel{width:100%; max-width:420px; font-family:"IBM Plex Mono",monospace; font-size:.9rem;
  background:var(--panel); color:var(--ink); border:1px solid var(--line); border-radius:8px; padding:.55rem .7rem}
.modelsel:disabled{opacity:.5}
.row{display:flex; gap:1.4rem; flex-wrap:wrap}
.row .field{flex:1; min-width:210px}
input[type=range]{width:100%; accent-color:var(--violet); cursor:pointer}
.sliderline{display:flex; align-items:baseline; gap:.55rem; margin-bottom:.4rem}
.sliderline b{font-family:"IBM Plex Mono",monospace; font-size:1.4rem; color:var(--ink)}
.sliderline span{font-family:"IBM Plex Mono",monospace; font-size:.72rem; color:var(--muted)}

/* odometer hero */
.odo{margin-top:2.6rem; background:linear-gradient(180deg,var(--panel),var(--panel-2));
  border:1px solid var(--line); border-radius:18px; padding:1.9rem; overflow:hidden;
  box-shadow:0 34px 80px -44px rgba(0,0,0,.95); display:grid; grid-template-columns:1.1fr 1fr; gap:1.6rem}
@media(max-width:760px){.odo{grid-template-columns:1fr}}
.odo .head{font-family:"IBM Plex Mono",monospace; letter-spacing:.24em; text-transform:uppercase;
  font-size:.68rem; color:var(--muted)}
.perkm{font-family:"Anton",sans-serif; font-weight:400; line-height:.9; margin:.35rem 0 0;
  font-size:clamp(3.4rem,13vw,7rem); color:var(--violet); letter-spacing:.005em;
  text-shadow:0 0 40px rgba(157,123,255,.25)}
.perkm .u{font-family:"IBM Plex Mono",monospace; font-size:1.1rem; color:var(--muted);
  -webkit-text-fill-color:var(--muted); text-shadow:none; margin-left:.4rem}
.odo .yr{font-family:"IBM Plex Mono",monospace; font-size:1.05rem; color:#d7d2c7; margin:.8rem 0 0}
.odo .yr b{color:var(--ink); font-size:1.5rem}
.odo .band{font-family:"IBM Plex Mono",monospace; font-size:.78rem; color:var(--muted); margin:.35rem 0 0}
.odo .life{margin:1.1rem 0 0; padding-top:1rem; border-top:1px solid var(--line);
  font-size:1.04rem; color:#cfcabf}
.odo .life b{color:var(--ink)}

/* stacked receipt bar */
.stack{height:34px; border-radius:9px; overflow:hidden; display:flex; border:1px solid var(--line);
  background:#0a0a0d}
.stack i{display:block; height:100%; transition:width .55s cubic-bezier(.2,.7,.2,1)}
.receipt{margin-top:1rem}
.line{display:flex; align-items:center; gap:.7rem; padding:.42rem 0;
  font-family:"IBM Plex Mono",monospace; font-size:.86rem; border-bottom:1px dashed var(--line)}
.line .sw{width:11px; height:11px; border-radius:3px; flex:none}
.line .nm{flex:1; color:#d7d2c7}
.line .pc{color:var(--muted); font-size:.74rem; width:3.2em; text-align:right}
.line .v{color:var(--ink); width:7em; text-align:right; font-variant-numeric:tabular-nums}
.line.user .nm{color:var(--violet)}
.tot{display:flex; justify-content:space-between; align-items:baseline; margin-top:.9rem;
  font-family:"IBM Plex Mono",monospace; font-weight:600}
.tot .v{font-size:1.25rem; color:var(--violet)}

/* sections */
section{margin-top:3.2rem}
.eyebrow{font-family:"IBM Plex Mono",monospace; letter-spacing:.28em; text-transform:uppercase;
  font-size:.72rem; color:var(--muted); display:flex; align-items:center; gap:.8rem}
.eyebrow::before{content:""; width:26px; height:2px; background:var(--violet)}
h2{font-family:"Anton",sans-serif; font-weight:400; text-transform:uppercase; letter-spacing:.02em;
  font-size:1.85rem; margin:.5rem 0 .3rem}
.lede{color:var(--muted); margin:.1rem 0 1.2rem; max-width:64ch}
.card{background:linear-gradient(180deg,var(--panel),var(--panel-2)); border:1px solid var(--line);
  border-radius:14px; padding:1.3rem 1.4rem; box-shadow:0 24px 60px -36px rgba(0,0,0,.9)}
svg{width:100%; height:auto; display:block}
.legend{display:flex; flex-wrap:wrap; gap:.4rem 1.2rem; margin-top:.7rem;
  font-family:"IBM Plex Mono",monospace; font-size:.74rem; color:var(--muted)}
.legend i{display:inline-block; width:14px; height:3px; vertical-align:middle; margin-right:.4rem; border-radius:2px}
.legend .sh{width:14px; height:9px; opacity:.5; border-radius:2px}

/* advanced */
details.adv{margin-top:1.6rem; border:1px solid var(--line); border-radius:12px; background:var(--panel-2)}
details.adv summary{cursor:pointer; padding:.9rem 1.2rem; font-family:"IBM Plex Mono",monospace;
  letter-spacing:.18em; text-transform:uppercase; font-size:.72rem; color:var(--muted)}
details.adv[open] summary{color:var(--ink); border-bottom:1px solid var(--line)}
.advgrid{padding:1.2rem; display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:1.1rem}
.advgrid .field input[type=number]{width:100%; font-family:"IBM Plex Mono",monospace; font-size:.9rem;
  background:var(--panel); color:var(--ink); border:1px solid var(--line); border-radius:8px; padding:.5rem .6rem}

/* coming-soon seasonal panel */
.soon{margin-top:1.4rem; position:relative; border:1px dashed rgba(247,184,1,.4); border-radius:14px;
  padding:1.4rem 1.5rem; background:repeating-linear-gradient(135deg,rgba(247,184,1,.03),rgba(247,184,1,.03) 12px,transparent 12px,transparent 24px)}
.soon .tag{position:absolute; top:-.7rem; left:1.2rem; background:var(--amber); color:#0b0b0f;
  font-family:"IBM Plex Mono",monospace; font-size:.64rem; letter-spacing:.18em; text-transform:uppercase;
  padding:.2rem .6rem; border-radius:999px; font-weight:600}
.soon h3{font-family:"Anton",sans-serif; font-weight:400; text-transform:uppercase; letter-spacing:.02em;
  font-size:1.4rem; margin:.3rem 0 .3rem; color:var(--amber)}
.soon p{color:#cfcabf; margin:.2rem 0 0; max-width:62ch}
.soon .ghost{display:flex; gap:1.4rem; margin-top:1.1rem; flex-wrap:wrap;
  font-family:"IBM Plex Mono",monospace; font-size:.78rem; color:var(--muted)}
.soon .ghost b{display:block; font-size:1.5rem; color:#5a5852; filter:blur(.5px)}

.note{border-left:3px solid var(--violet); background:rgba(157,123,255,.05); margin-top:1.2rem;
  padding:1.1rem 1.4rem; border-radius:0 12px 12px 0; color:#cfcabf; font-size:1.02rem}
.note h2{font-size:1.45rem; margin:.1rem 0 .5rem} .note ul{margin:.6rem 0 0; padding-left:1.1rem}
.note li{margin:.5rem 0} .note b{color:var(--ink)}
.gate{text-align:center; padding:3rem 1rem; color:var(--muted)}

footer{margin-top:3.4rem; padding-top:1.4rem; border-top:1px solid var(--line);
  font-family:"IBM Plex Mono",monospace; font-size:.74rem; color:var(--muted); line-height:1.7}

@keyframes rise{from{opacity:0; transform:translateY(16px)} to{opacity:1; transform:none}}
.reveal{animation:rise .7s cubic-bezier(.2,.7,.2,1) both}
@media (prefers-reduced-motion:reduce){.reveal{animation:none} .stack i{transition:none}}
"""

# Plain (non-f-string) JS — single braces, no escaping. `CFG` and `AGG` are
# prepended by the renderer. Mirrors compute_tco line-for-line.
_JS = r"""
const PLN = n => (n<0?"−":"") + Math.abs(Math.round(n)).toLocaleString("pl-PL") + " zł";
const $ = id => document.getElementById(id);
const COL = CFG.componentColors;
const CARS = (typeof AGG_CAR !== "undefined") ? AGG_CAR : {models:{}, fuels:{}};
const MOTO = (typeof AGG_MOTO !== "undefined") ? AGG_MOTO : {categories:{}, models:{}};
const isCar = () => UI.veh === "car";
const A = () => isCar() ? CARS : MOTO;
const fmt = (t, v) => (t || "").replace(/\{(\w+)\}/g, (_, k) => (v[k] != null ? v[k] : ""));
const titlecase = s => (s || "").replace(/(^|[\s-])\w/g, c => c.toUpperCase());

const state = {grp:null, model:null, age:5, hold:3, km:8000, price:null,
  pump:null, insurance:null, service:null, pcc:true};

// models in a group: a moto category, or (for cars) a make
function modelsInGroup(g){
  const models = A().models || {};
  return Object.entries(models)
    .filter(([n,m]) => m.points && m.points.length && (isCar() ? n.split(" ")[0]===g : m.category===g))
    .sort((a,b) => (b[1].n_samples||0)-(a[1].n_samples||0));
}
// selectable groups: moto = riding categories with a curve/models; car = makes
function groups(){
  if(isCar()){
    const mk = new Set();
    for(const k in (CARS.models||{})){ const m=CARS.models[k]; if(m.points && m.points.length) mk.add(k.split(" ")[0]); }
    return [...mk].sort();
  }
  const cats = MOTO.categories || {};
  return (CFG.categoryOrder||[]).filter(c => CFG.categoryDefaults[c] &&
    ((cats[c] && cats[c].points && cats[c].points.length) || modelsInGroup(c).length));
}
function groupCurve(g){ return isCar() ? null : (MOTO.categories||{})[g]; }  // moto has category curves; cars don't
function groupLabel(g){ return isCar() ? titlecase(g) : ((CFG.categoryDefaults[g]||{}).label || g); }
function groupTag(g){ return isCar()
  ? (modelsInGroup(g).length + " " + (_t("models_word")||"models"))
  : ((CFG.categoryDefaults[g]||{}).tag || ""); }

// the curve in effect — a specific model when picked, else the group (moto category) curve
function chosen(){
  const models = A().models || {};
  if(state.model && models[state.model]) return models[state.model];
  return groupCurve(state.grp);
}
function curveOf(){ const c=chosen(); return (c && c.points) ? c.points.map(p=>({age:p.age, smooth:p.smooth})) : []; }

// running-cost coefficients: car = by fuel; moto = by category
function coeffs(){
  if(isCar()){
    const m = state.model && CARS.models[state.model];
    const fuel = (m && m.fuel) || "petrol";
    const f = (CFG.carFuel||{})[fuel] || (CFG.carFuel||{}).petrol || {per100:7, pump:6.49, label:"Petrol"};
    return {fuel_per100:f.per100, pump:(state.pump!=null?state.pump:f.pump),
      service:(state.service!=null?state.service:CFG.carService),
      insurance:(state.insurance!=null?state.insurance:CFG.carInsurance), fuel, fuelLabel:f.label};
  }
  const d = CFG.categoryDefaults[state.grp] || {fuel_per100:4, service_per1000:90, insurance_yr:600};
  return {fuel_per100:d.fuel_per100, pump:(state.pump!=null?state.pump:CFG.pumpPetrol),
    service:(state.service!=null?state.service:d.service_per1000),
    insurance:(state.insurance!=null?state.insurance:d.insurance_yr), fuel:"petrol", fuelLabel:"Petrol"};
}

function interp(curve, age){
  if(!curve.length) return null;
  const pts = curve.slice().sort((a,b)=>a.age-b.age);
  if(age<=pts[0].age) return pts[0].smooth;
  if(age>=pts[pts.length-1].age) return pts[pts.length-1].smooth;
  for(let i=1;i<pts.length;i++){
    if(age<=pts[i].age){
      const t=(age-pts[i-1].age)/((pts[i].age-pts[i-1].age)||1);
      return pts[i-1].smooth + t*(pts[i].smooth-pts[i-1].smooth);
    }
  }
  return pts[pts.length-1].smooth;
}

function compute(){
  const co = coeffs();
  const curve = curveOf();
  const baseNow = interp(curve, state.age);
  const baseLater = interp(curve, state.age + state.hold);
  const paid = state.price!=null ? state.price : baseNow;
  const scale = baseNow ? paid/baseNow : 1;
  const valueEnd = baseLater*scale;
  const deprTotal = Math.max(0, paid - valueEnd);
  const deprYr = state.hold ? deprTotal/state.hold : 0;

  const fuelYr = co.fuel_per100/100 * state.km * co.pump;
  const avgAge = state.age + state.hold/2;
  const serviceYr = co.service * (state.km/1000) * (1 + CFG.serviceAgeK*avgAge);
  const pccYr = state.pcc ? paid*CFG.pccRate/(state.hold||1) : 0;
  const feesYr = CFG.registration + pccYr;
  const insurance = co.insurance;

  const raw = {depreciation:deprYr, fuel:fuelYr, service:serviceYr, insurance, fees:feesYr};
  const items = CFG.componentOrder.map(([k,lbl])=>({key:k, label:(_t("comp_"+k)||lbl), pln:raw[k]}));
  const total = items.reduce((a,i)=>a+i.pln,0);
  const band = serviceYr*CFG.serviceBand;

  return {ok:true, paid, valueEnd, baseNow, items, total,
    lo:total-band, hi:total+band, lifetime:total*state.hold,
    perKm: state.km? total/state.km : 0,
    deprShare: total? Math.round(100*deprYr/total) : 0,
    curve, scale};
}

// --- depreciation curve with the hold window shaded (signature moment) ---
function holdChart(r){
  const w=820, h=340, pad={l:58,r:16,t:16,b:34};
  const pts = r.curve.map(p=>({age:p.age, val:p.smooth*r.scale}));
  const xs=pts.map(p=>p.age), ys=pts.map(p=>p.val);
  const xmin=Math.min(...xs), xmax=Math.max(...xs);
  let ymin=Math.min(...ys,0), ymax=Math.max(...ys); if(ymax===ymin) ymax+=1;
  const X=x=>pad.l+(x-xmin)/((xmax-xmin)||1)*(w-pad.l-pad.r);
  const Y=y=>h-pad.b-(y-ymin)/((ymax-ymin)||1)*(h-pad.t-pad.b);
  let s=`<svg viewBox="0 0 ${w} ${h}" role="img">`;
  for(let i=0;i<=4;i++){
    const yv=ymin+(ymax-ymin)*i/4, py=Y(yv);
    s+=`<line x1="${pad.l}" y1="${py}" x2="${w-pad.r}" y2="${py}" stroke="#fff" stroke-opacity="0.06"/>`;
    s+=`<text x="${pad.l-8}" y="${py+3}" fill="#8d8a83" font-size="10" text-anchor="end" font-family="IBM Plex Mono,monospace">${(yv/1000).toFixed(0)}k</text>`;
  }
  for(let a=Math.ceil(xmin); a<=Math.floor(xmax); a++)
    s+=`<text x="${X(a)}" y="${h-pad.b+18}" fill="#8d8a83" font-size="10" text-anchor="middle" font-family="IBM Plex Mono,monospace">${a}</text>`;
  s+=`<text x="${w/2}" y="${h-2}" fill="#8d8a83" font-size="10" text-anchor="middle" font-family="IBM Plex Mono,monospace" letter-spacing="1">AGE (YEARS)</text>`;

  // shaded hold window between buy age and sell age
  const a0=state.age, a1=Math.min(state.age+state.hold, xmax);
  const vx0=X(a0), vx1=X(a1);
  s+=`<rect x="${vx0}" y="${pad.t}" width="${Math.max(0,vx1-vx0)}" height="${h-pad.t-pad.b}" fill="#9d7bff" fill-opacity="0.12"/>`;
  s+=`<line x1="${vx0}" y1="${pad.t}" x2="${vx0}" y2="${h-pad.b}" stroke="#9d7bff" stroke-width="1.4" stroke-dasharray="3 3"/>`;
  s+=`<line x1="${vx1}" y1="${pad.t}" x2="${vx1}" y2="${h-pad.b}" stroke="#9d7bff" stroke-width="1.4" stroke-dasharray="3 3"/>`;

  // value curve
  const d = pts.map((p,i)=>`${i?'L':'M'}${X(p.age)},${Y(p.val)}`).join(" ");
  s+=`<path d="${d}" fill="none" stroke="#f35b04" stroke-width="2.6" stroke-linejoin="round"/>`;

  // buy + sell markers
  const buyV=interp(r.curve,state.age)*r.scale, sellV=interp(r.curve,state.age+state.hold)*r.scale;
  s+=`<circle cx="${X(a0)}" cy="${Y(buyV)}" r="5" fill="#9d7bff"/>`;
  s+=`<circle cx="${vx1}" cy="${Y(sellV)}" r="5" fill="#9d7bff" fill-opacity="0.6" stroke="#9d7bff"/>`;
  // bled-value bracket label
  const midx=(vx0+vx1)/2;
  s+=`<text x="${midx}" y="${pad.t+16}" fill="#9d7bff" font-size="12" text-anchor="middle" font-family="IBM Plex Mono,monospace">−${Math.round(buyV-sellV).toLocaleString("pl-PL")} zł</text>`;
  return s+`</svg>`;
}

function render(){
  const r = compute();
  // odometer
  const yrW = state.hold>1 ? (_t("years")||"years") : (_t("year")||"year");
  $("perkm").innerHTML = r.perKm.toFixed(2).replace(".",",") + `<span class="u">${_t("per_km")||"zł / km"}</span>`;
  $("yrnum").textContent = PLN(r.total);
  $("bandtxt").textContent = fmt(_t("range_fmt")||"range {lo} – {hi} /yr", {lo:PLN(r.lo), hi:PLN(r.hi)});
  $("life").innerHTML = fmt(_t("life")||"Over <b>{hold} {yr}</b> at <b>{km} km/yr</b> you'll spend about <b>{life}</b> — of which <b>{share}%</b> is value it loses while parked.",
    {hold:state.hold, yr:yrW, km:state.km.toLocaleString("pl-PL"), life:PLN(r.lifetime), share:r.deprShare});

  // stacked bar + receipt
  const peak = r.total||1;
  $("stack").innerHTML = r.items.filter(i=>i.pln>0).map(i=>
    `<i style="width:${i.pln/peak*100}%;background:${COL[i.key]}" title="${i.label}"></i>`).join("");
  $("receipt").innerHTML = r.items.map(i=>{
    const pc = r.total? Math.round(100*i.pln/r.total):0;
    const user = (i.key==="insurance");
    return `<div class="line ${user?'user':''}"><span class="sw" style="background:${COL[i.key]}"></span>
      <span class="nm">${i.label}${user?' ·':''}</span><span class="pc">${pc}%</span>
      <span class="v">${PLN(i.pln)}</span></div>`;
  }).join("");
  $("rectot").textContent = PLN(r.total)+" /yr";

  // hold-window chart
  $("holdchart").innerHTML = holdChart(r);
  let buy = fmt(_t("buy_pay")||"You pay <b>{paid}</b> today; after {hold} {yr} the curve says it's worth about <b>{end}</b>.",
    {paid:PLN(r.paid), hold:state.hold, yr:yrW, end:PLN(r.valueEnd)});
  const deprItem = r.items.find(i=>i.key==="depreciation");
  if(deprItem && deprItem.pln < 1){
    const ch = chosen();
    const anchorScaled = ((ch && ch.anchor) || 0) * r.scale;
    if(state.age <= 4 && anchorScaled && r.valueEnd >= 0.78*anchorScaled)
      buy += ` <span style="color:var(--amber)">${_t("flat_young")||"⚠ Near-new depreciation here isn't resolved yet — treat this as a floor; real loss is likely higher."}</span>`;
    else
      buy += ` <span style="color:var(--cyan)">${_t("flat_floor")||"The curve is flat here — it's near its value floor, having done most of its depreciating already."}</span>`;
  }
  $("buynote").innerHTML = buy;

  const ch = chosen();
  $("confnote").innerHTML = (ch && ch.reliable===false)
    ? fmt(_t("conf_limited")||"⚠ limited data for this {what} — read the curve's <b>shape</b>, not its exact złoty.",
        {what: state.model ? (_t("model_word")||"model") : (_t("category_word")||"category")})
    : "";

  // keep price box in sync if untouched
  if(state.price==null) $("price").placeholder = Math.round(r.baseNow).toLocaleString("pl-PL");
}

function prettyModel(n){ return isCar() ? titlecase(n) : n; }

function fillModels(){
  const ms = modelsInGroup(state.grp);
  let opts = [];
  if(!isCar()) opts.push(`<option value="">${(_t("any_word")||"Any")} ${groupLabel(state.grp)} — ${(_t("category_curve")||"category curve")}</option>`);
  opts = opts.concat(ms.map(([name,m]) => `<option value="${name}">${prettyModel(name)} · n=${m.n_samples}</option>`));
  $("model").innerHTML = opts.join("");
  $("model").value = state.model || "";
  $("model").disabled = ms.length===0;
  $("modelhint").textContent = ms.length ? `${ms.length} ${(_t("models_word")||"models")}` : (_t("no_models")||"no per-model data");
}

function refreshAdv(){
  const co = coeffs();
  $("ins").placeholder = Math.round(co.insurance);
  $("svc").placeholder = Math.round(co.service);
  if($("pump")) $("pump").placeholder = co.pump;
}

function selectGroup(g){
  state.grp=g; state.price=null; state.insurance=null; state.service=null; state.pump=null;
  const ms = modelsInGroup(g).map(x=>x[0]);
  state.model = isCar() ? (ms[0]||null) : null;  // car has no group curve → auto-pick top model
  $("price").value=""; $("ins").value=""; $("svc").value="";
  document.querySelectorAll(".mode-btn").forEach(b=>b.setAttribute("aria-pressed", b.dataset.grp===g));
  fillModels(); refreshAdv(); render();
}

function build(){
  const gs = groups();
  if(!gs.includes(state.grp)){ state.grp = gs[0]; state.model = null; }
  if($("grpLabel")) $("grpLabel").textContent = isCar() ? (_t("make")||"Make") : (_t("category")||"Category");
  $("modes").innerHTML = gs.map(g =>
    `<button class="mode-btn" data-grp="${g}" aria-pressed="${g===state.grp}"><span>${groupLabel(g)}</span><small>${groupTag(g)}</small></button>`).join("");
  const ms = modelsInGroup(state.grp).map(x=>x[0]);
  if(isCar() && (!state.model || !ms.includes(state.model))) state.model = ms[0]||null;
  if(!isCar() && state.model && !ms.includes(state.model)) state.model = null;
  const heldEl = $("heldNote");
  if(heldEl){
    const held = isCar() ? [] : (CFG.categoryOrder||[]).filter(c => CFG.categoryDefaults[c] && !gs.includes(c));
    heldEl.innerHTML = held.length
      ? fmt(_t("gathering")||"<b>Gathering data:</b> {list} — not enough clean listings yet.",
          {list: held.map(c => (CFG.categoryDefaults[c]||{}).label || c).join(", ")})
      : "";
  }
  fillModels(); refreshAdv(); render();
}

function init(){
  document.addEventListener("click", e=>{ const b=e.target.closest(".mode-btn"); if(b) selectGroup(b.dataset.grp); });
  $("model").addEventListener("change", e=>{ state.model = e.target.value || null; state.price=null; $("price").value=""; refreshAdv(); render(); });
  $("age").addEventListener("input", e=>{state.age=+e.target.value; $("ageval").textContent=state.age; render();});
  $("hold").addEventListener("input", e=>{state.hold=+e.target.value; $("holdval").textContent=state.hold; render();});
  $("km").addEventListener("input", e=>{state.km=+e.target.value; $("kmval").textContent=state.km.toLocaleString("pl-PL"); render();});
  $("price").addEventListener("input", e=>{state.price = e.target.value? +e.target.value : null; render();});
  $("ins").addEventListener("input", e=>{state.insurance = e.target.value? +e.target.value : null; render();});
  $("svc").addEventListener("input", e=>{state.service = e.target.value? +e.target.value : null; render();});
  $("pump").addEventListener("input", e=>{state.pump = e.target.value? +e.target.value : null; render();});
  $("pcc").addEventListener("change", e=>{state.pcc = e.target.checked; render();});
  window.addEventListener("uichange", build);  // language or vehicle switched
  build();
}
init();
"""


def _controls() -> str:
    return """
  <div class="controls">
    <div class="field">
      <label id="grpLabel" data-i18n="category">Category</label>
      <div class="modes" id="modes"></div>
      <p class="heldnote" id="heldNote"></p>
    </div>
    <div class="field">
      <label><span data-i18n="model_label">Model</span> · <span id="modelhint" style="text-transform:none;letter-spacing:0;color:var(--violet)">optional</span></label>
      <select id="model" class="modelsel"></select>
      <p class="heldnote" id="confnote" style="color:var(--amber)"></p>
    </div>
    <div class="row">
      <div class="field">
        <label data-i18n="lbl_age">Age when you buy</label>
        <div class="sliderline"><b class="mono"><span id="ageval">5</span></b><span data-i18n="yrs_old">years old</span></div>
        <input type="range" id="age" min="1" max="18" step="1" value="5">
      </div>
      <div class="field">
        <label data-i18n="lbl_hold">How long you'll keep it</label>
        <div class="sliderline"><b class="mono"><span id="holdval">3</span></b><span data-i18n="lbl_years">years</span></div>
        <input type="range" id="hold" min="1" max="8" step="1" value="3">
      </div>
      <div class="field">
        <label data-i18n="lbl_km">Distance per year</label>
        <div class="sliderline"><b class="mono" id="kmval">8 000</b><span data-i18n="km_year">km / year</span></div>
        <input type="range" id="km" min="1000" max="25000" step="500" value="8000">
      </div>
    </div>
    <div class="row">
      <div class="field">
        <label data-i18n="lbl_price">Price you'd pay (blank = market fit)</label>
        <input type="number" id="price" step="500" placeholder="—"
          style="width:100%;font-family:'IBM Plex Mono',monospace;font-size:1rem;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:.55rem .7rem">
      </div>
      <div class="field">
        <label data-i18n="lbl_ins">Your insurance quote · OC/AC (zł/yr)</label>
        <input type="number" id="ins" step="50" placeholder="—"
          style="width:100%;font-family:'IBM Plex Mono',monospace;font-size:1rem;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:.55rem .7rem">
      </div>
    </div>
  </div>
"""


def _odometer() -> str:
    return """
<div class="odo reveal" style="animation-delay:.06s">
  <div>
    <div class="head" data-i18n="odo_head">True cost to ride</div>
    <div class="perkm" id="perkm">—</div>
    <p class="yr">≈ <b id="yrnum">—</b> <span data-i18n="odo_yr">every year</span></p>
    <p class="band" id="bandtxt"></p>
    <p class="life" id="life"></p>
  </div>
  <div>
    <div class="head" data-i18n="odo_where">Where the money goes</div>
    <div class="stack" id="stack" style="margin-top:.7rem"></div>
    <div class="receipt" id="receipt"></div>
    <div class="tot"><span data-i18n="tot_year">Total / year</span><span class="v mono" id="rectot">—</span></div>
  </div>
</div>
"""


def _sections() -> str:
    return f"""
<details class="adv reveal" style="animation-delay:.1s">
  <summary>Assumptions — adjust the model</summary>
  <div class="advgrid">
    <div class="field"><label>Petrol price (zł/l)</label>
      <input type="number" id="pump" step="0.01" value="{PUMP_PETROL_PLN}"></div>
    <div class="field"><label>Service reserve (zł / 1000 km)</label>
      <input type="number" id="svc" step="5" placeholder="—"></div>
    <div class="field"><label class="mono" style="display:flex;align-items:center;gap:.55rem;color:var(--ink);font-size:.8rem;text-transform:none;letter-spacing:0">
      <input type="checkbox" id="pcc" checked style="accent-color:var(--violet);width:16px;height:16px"> charge 2% PCC purchase tax</label></div>
  </div>
</details>

<section class="reveal" style="animation-delay:.14s">
  <p class="eyebrow">The big one</p>
  <h2>What it bleeds while you own it</h2>
  <p class="lede">The orange line is the real value curve for this class (smoothed
  from PL private-seller listings). The shaded band is your hold window — buy on
  the left dot, sell on the right. The gap between them is depreciation: usually
  the largest single cost of owning a bike, and the one no dealer prints on the
  tag.</p>
  <div class="card"><div id="holdchart"></div>
    <p class="lede" id="buynote" style="margin:.9rem 0 0"></p>
    <div class="legend">
      <span><i style="background:#f35b04"></i>fitted value</span>
      <span><i class="sh" style="background:#9d7bff"></i>your hold window</span>
    </div>
  </div>

  <div class="soon">
    <span class="tag">Coming soon</span>
    <h3>Buy in February, sell in May</h3>
    <p>Two-wheeler prices swing with the season — a bike costs more in spring than
    in the dead of winter. Once a full year of tracking is banked, this panel will
    show the cheapest month to buy, the dearest to sell, and the złoty that timing
    alone saves on top of the curve above.</p>
    <div class="ghost">
      <span>cheapest to buy<b>Feb?</b></span>
      <span>dearest to sell<b>May?</b></span>
      <span>timing swing<b>± ? zł</b></span>
    </div>
  </div>
</section>

<section class="reveal">
  <p class="eyebrow">How to read this</p>
  <h2>It's a band, not a verdict</h2>
  <div class="note">
    <h2>Three honest caveats</h2>
    <ul>
      <li><b>Depreciation is ours; the rest is modelled.</b> The value curve is
      real data. Fuel, the service/wear reserve and fees are coefficient estimates
      — that's why the yearly figure is shown as a <b>range</b>, swung by the wear
      reserve.</li>
      <li><b>Insurance is yours.</b> We refuse to guess it — paste a real OC/AC
      quote and the receipt updates. The default is only a placeholder.</li>
      <li><b>Resale assumes an average example.</b> Your bike's condition, mileage
      and history move the sell value off the curve. Treat the end value as the
      midpoint of a fleet, not a promise.</li>
    </ul>
  </div>
</section>
"""


def _gate() -> str:
    return """
<section class="reveal" style="animation-delay:.1s">
  <div class="card gate">
    <h2>Depreciation engine warming up</h2>
    <p class="lede" style="margin:.6rem auto 0">The calculator runs on real
    value-vs-age curves, and none are banked yet. Once the tracker has enough
    listings per engine class, this page fills in automatically.</p>
  </div>
</section>
"""


# UI translations. `{x}` are fmt() placeholders filled in JS.
STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "veh_moto": "Moto", "veh_car": "Car",
        "h1": "The sticker is<br>the small print",
        "dek": "A vehicle's real cost isn't its price — it's what it loses, burns and bills you every year. This adds it all up, per kilometre, on top of the depreciation we actually measure.",
        "nav_cost": "Personal cost", "nav_ledger": "Public-money ledger", "nav_depr": "Depreciation curves",
        "foot1": "METHOD · depreciation read off cross-sectional value-vs-age curves, scaled to your price. Fuel/service/fees are coefficient models, user-adjustable.",
        "foot2": "DATA · derived aggregate curves only — no listings reproduced. Insurance is never modelled (you paste a quote).",
        "category": "Category", "make": "Make", "model_label": "Model", "optional": "optional",
        "lbl_age": "Age when you buy", "yrs_old": "years old", "lbl_hold": "How long you'll keep it",
        "lbl_years": "years", "lbl_km": "Distance per year", "km_year": "km / year",
        "lbl_price": "Price you'd pay (blank = market fit)", "lbl_ins": "Your insurance quote · OC/AC (zł/yr)",
        "odo_head": "True cost to ride", "odo_yr": "every year", "odo_where": "Where the money goes",
        "tot_year": "Total / year", "assumptions": "Assumptions — adjust the model",
        "lbl_fuel_price": "Fuel price (zł/l or zł/kWh)", "lbl_service": "Service reserve (zł / 1000 km)",
        "lbl_pcc": "charge 2% PCC purchase tax",
        "sec_big_eye": "The big one", "sec_big_h": "What it bleeds while you own it",
        "any_word": "Any", "category_curve": "category curve", "models_word": "models", "no_models": "no per-model data",
        "model_word": "model", "category_word": "category",
        "comp_depreciation": "Depreciation", "comp_fuel": "Fuel", "comp_service": "Service & wear",
        "comp_insurance": "Insurance (OC/AC)", "comp_fees": "Fees & PCC tax",
        "per_km": "zł / km", "range_fmt": "range {lo} – {hi} /yr", "year": "year", "years": "years",
        "life": "Over <b>{hold} {yr}</b> at <b>{km} km/yr</b> you'll spend about <b>{life}</b> — of which <b>{share}%</b> is value it loses while parked.",
        "buy_pay": "You pay <b>{paid}</b> today; after {hold} {yr} the curve says it's worth about <b>{end}</b>.",
        "flat_young": "⚠ Near-new depreciation here isn't resolved yet — too few young listings, so the curve is flat where it shouldn't be. Treat this as a floor; real loss is likely higher.",
        "flat_floor": "The curve is flat here — it's near its value floor, having done most of its depreciating already. That's when a used vehicle is cheapest to own.",
        "conf_limited": "⚠ limited data for this {what} — read the curve's <b>shape</b>, not its exact złoty.",
        "gathering": "<b>Gathering data:</b> {list} — not enough clean listings yet.",
    },
    "pl": {
        "veh_moto": "Moto", "veh_car": "Auto",
        "h1": "Cena to<br>tylko nagłówek",
        "dek": "Prawdziwy koszt pojazdu to nie cena — to ile traci, spala i kosztuje co roku. To podlicza całość, na kilometr, na bazie zmierzonej utraty wartości.",
        "nav_cost": "Koszt osobisty", "nav_ledger": "Bilans publiczny", "nav_depr": "Krzywe wartości",
        "foot1": "METODA · utrata wartości odczytana z przekrojowych krzywych wartość-wiek, skalowana do Twojej ceny. Paliwo/serwis/opłaty to modele współczynnikowe, edytowalne.",
        "foot2": "DANE · tylko pochodne krzywe zbiorcze — żadne ogłoszenia nie są kopiowane. Ubezpieczenia nie modelujemy (wklejasz wycenę).",
        "category": "Kategoria", "make": "Marka", "model_label": "Model", "optional": "opcjonalnie",
        "lbl_age": "Wiek przy zakupie", "yrs_old": "lat", "lbl_hold": "Jak długo go zatrzymasz",
        "lbl_years": "lat", "lbl_km": "Dystans rocznie", "km_year": "km / rok",
        "lbl_price": "Cena, którą zapłacisz (puste = wg rynku)", "lbl_ins": "Twoja wycena ubezpieczenia · OC/AC (zł/rok)",
        "odo_head": "Prawdziwy koszt jazdy", "odo_yr": "rocznie", "odo_where": "Gdzie idą pieniądze",
        "tot_year": "Razem / rok", "assumptions": "Założenia — dostosuj model",
        "lbl_fuel_price": "Cena paliwa (zł/l lub zł/kWh)", "lbl_service": "Rezerwa serwisowa (zł / 1000 km)",
        "lbl_pcc": "nalicz 2% PCC od zakupu",
        "sec_big_eye": "Najważniejsze", "sec_big_h": "Ile traci, gdy go masz",
        "any_word": "Dowolny", "category_curve": "krzywa kategorii", "models_word": "modeli", "no_models": "brak danych per model",
        "model_word": "modelu", "category_word": "kategorii",
        "comp_depreciation": "Utrata wartości", "comp_fuel": "Paliwo", "comp_service": "Serwis i zużycie",
        "comp_insurance": "Ubezpieczenie (OC/AC)", "comp_fees": "Opłaty i PCC",
        "per_km": "zł / km", "range_fmt": "zakres {lo} – {hi} /rok", "year": "rok", "years": "lat",
        "life": "Przez <b>{hold} {yr}</b> przy <b>{km} km/rok</b> wydasz około <b>{life}</b> — z czego <b>{share}%</b> to wartość tracona podczas postoju.",
        "buy_pay": "Płacisz dziś <b>{paid}</b>; po {hold} {yr} krzywa wskazuje wartość około <b>{end}</b>.",
        "flat_young": "⚠ Utrata wartości tuż po zakupie nie jest tu jeszcze rozstrzygnięta — za mało młodych ofert, więc krzywa jest płaska. Traktuj to jako dolną granicę; realna strata jest większa.",
        "flat_floor": "Krzywa jest tu płaska — pojazd jest blisko wartości minimalnej, większość utraty już za nim. Wtedy używany pojazd jest najtańszy w utrzymaniu.",
        "conf_limited": "⚠ mało danych dla tego {what} — patrz na <b>kształt</b> krzywej, nie dokładne złotówki.",
        "gathering": "<b>Zbieramy dane:</b> {list} — za mało czystych ofert na krzywą.",
    },
}


def _render_html(agg: dict, car_agg: dict | None = None) -> str:
    car_agg = car_agg or {"meta": {}, "models": {}, "fuels": {}}
    meta = agg.get("meta", {})
    moto_curves = any(c.get("points") for c in agg.get("categories", {}).values()) or any(
        m.get("points") for m in agg.get("models", {}).values()
    )
    car_curves = any(m.get("points") for m in car_agg.get("models", {}).values())
    has_curves = moto_curves or car_curves
    year = meta.get("current_year", "—")
    config = _client_config()
    moto_json = json.dumps(agg, ensure_ascii=False)
    car_json = json.dumps(car_agg, ensure_ascii=False)

    head = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>What a vehicle really costs · personal TCO · PL</title>
{_FONTS}
<style>{_STYLE}{ui.SELECTOR_CSS}</style>
</head>
<body>
<div class="wrap">
<header class="reveal">
  {ui.selector_bar()}
  <p class="kicker">Poland · used-vehicle ownership · {year}</p>
  <h1 data-i18n-html="h1">The sticker is<br>the small print</h1>
  <p class="dek" data-i18n="dek">A vehicle's real cost isn't its price — it's what it
  loses, burns and bills you every year. This adds it all up, per kilometre, on top
  of the depreciation we actually measure.</p>
  <div class="rule"></div>
  <nav class="nav">
    <a href="cost.html" class="here" data-i18n="nav_cost">Personal cost</a>
    <a href="index.html" data-i18n="nav_ledger">Public-money ledger</a>
    <a href="depreciation.html" data-i18n="nav_depr">Depreciation curves</a>
  </nav>
"""

    body = _controls() + "</header>\n" + _odometer() + _sections() if has_curves else "</header>\n" + _gate()

    foot = """
<footer>
  <div data-i18n="foot1">METHOD · depreciation read off cross-sectional value-vs-age curves, scaled to your price. Fuel/service/fees are coefficient models, user-adjustable.</div>
  <div data-i18n="foot2">DATA · derived aggregate curves only — no listings reproduced. Insurance is never modelled (you paste a quote).</div>
</footer>
</div>
"""

    if not has_curves:
        return head + body + foot + "</body>\n</html>\n"
    return (
        head + body + foot
        + "<script>\nconst CFG = " + config
        + ";\nconst AGG_MOTO = " + moto_json
        + ";\nconst AGG_CAR = " + car_json
        + ";\nwindow.T = " + json.dumps(STRINGS, ensure_ascii=False) + ";\n"
        + ui.SELECTOR_JS + "\n" + _JS + "</script>\n</body>\n</html>\n"
    )
