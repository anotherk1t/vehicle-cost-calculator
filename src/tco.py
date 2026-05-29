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

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = "public"
DEFAULT_AGGREGATES = os.path.join("data", "aggregates.json")

# --- coefficient constants (mirrored by the page's JS) -----------------------
# Everything here is a default the user can override in the UI. The numbers are
# deliberately conservative PL used-market ballparks, not precise per-model data
# — the calculator is a band, never a false-precision point.

PUMP_PETROL_PLN: float = 6.49  # zł/litre, 95-oct, standard rate (no temp cut)
PCC_RATE: float = 0.02  # podatek od czynności cywilnoprawnych on a private buy
REGISTRATION_PLN_YR: float = 99.0  # przegląd + recurring registration, amortised
SERVICE_AGE_K: float = 0.045  # the wear reserve grows ~4.5% per year of bike age
SERVICE_BAND: float = 0.35  # ± on the maintenance/wear reserve → the cost band

# Per engine-class defaults. Keys MUST match the aggregates `cc_order` buckets so
# a class selection maps straight onto a depreciation curve.
CLASS_DEFAULTS: dict[str, dict] = {
    "<=125": {
        "label": "≤125 cc",
        "tag": "commuter / A1",
        "fuel_per100": 2.8,  # litres / 100 km
        "service_per1000": 50,  # zł reserve per 1000 km, at age 0
        "insurance_yr": 320,  # OC ballpark; user pastes a real quote
        "kind": "scooter",
    },
    "126-300": {
        "label": "126–300 cc",
        "tag": "first big bike",
        "fuel_per100": 3.5,
        "service_per1000": 70,
        "insurance_yr": 480,
        "kind": "light",
    },
    "301-600": {
        "label": "301–600 cc",
        "tag": "middleweight",
        "fuel_per100": 4.2,
        "service_per1000": 95,
        "insurance_yr": 640,
        "kind": "mid",
    },
    "601-900": {
        "label": "601–900 cc",
        "tag": "do-it-all",
        "fuel_per100": 4.9,
        "service_per1000": 120,
        "insurance_yr": 820,
        "kind": "big",
    },
    "900+": {
        "label": "900 cc +",
        "tag": "litre / tourer",
        "fuel_per100": 5.6,
        "service_per1000": 150,
        "insurance_yr": 1050,
        "kind": "litre",
    },
}

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
            "classDefaults": CLASS_DEFAULTS,
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

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_render_html(agg))
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
// Only offer classes whose depreciation curve is trustworthy — an unreliable
// curve (thin/noisy data flagged upstream) would poison the whole calculator.
// reliable===false is the engine's hold signal; missing flag = treat as ok.
const present = (AGG.meta.cc_order||[]).filter(cc => AGG.classes[cc] && AGG.classes[cc].points.length && AGG.classes[cc].reliable !== false);
const held = (AGG.meta.cc_order||[]).filter(cc => AGG.classes[cc] && AGG.classes[cc].points.length && AGG.classes[cc].reliable === false);

const state = {cls: present[0], age:5, hold:3, km:8000, price:null,
  pump:CFG.pumpPetrol, insurance:null, service:null, pcc:true};

function curveOf(cls){ return AGG.classes[cls].points.map(p=>({age:p.age, smooth:p.smooth})); }

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
  const d = CFG.classDefaults[state.cls];
  const curve = curveOf(state.cls);
  const baseNow = interp(curve, state.age);
  const baseLater = interp(curve, state.age + state.hold);
  const paid = state.price!=null ? state.price : baseNow;
  const scale = baseNow ? paid/baseNow : 1;
  const valueEnd = baseLater*scale;
  const deprTotal = Math.max(0, paid - valueEnd);
  const deprYr = state.hold ? deprTotal/state.hold : 0;

  const fuelYr = d.fuel_per100/100 * state.km * state.pump;
  const svcPer1000 = state.service!=null ? state.service : d.service_per1000;
  const avgAge = state.age + state.hold/2;
  const serviceYr = svcPer1000 * (state.km/1000) * (1 + CFG.serviceAgeK*avgAge);
  const pccYr = state.pcc ? paid*CFG.pccRate/(state.hold||1) : 0;
  const feesYr = CFG.registration + pccYr;
  const insurance = state.insurance!=null ? state.insurance : d.insurance_yr;

  const raw = {depreciation:deprYr, fuel:fuelYr, service:serviceYr, insurance, fees:feesYr};
  const items = CFG.componentOrder.map(([k,lbl])=>({key:k, label:lbl, pln:raw[k]}));
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
  $("perkm").innerHTML = r.perKm.toFixed(2).replace(".",",") + `<span class="u">zł / km</span>`;
  $("yrnum").textContent = PLN(r.total);
  $("bandtxt").textContent = `range ${PLN(r.lo)} – ${PLN(r.hi)} /yr`;
  $("life").innerHTML = `Over <b>${state.hold} year${state.hold>1?"s":""}</b> at <b>${state.km.toLocaleString("pl-PL")} km/yr</b> you'll spend about <b>${PLN(r.lifetime)}</b> — of which <b>${r.deprShare}%</b> is value the bike quietly loses while parked.`;

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
  let buy = `You pay <b>${PLN(r.paid)}</b> today; after ${state.hold} year${state.hold>1?"s":""} the curve says it's worth about <b>${PLN(r.valueEnd)}</b>.`;
  const deprItem = r.items.find(i=>i.key==="depreciation");
  if(deprItem && deprItem.pln < 1){
    const anchorScaled = (AGG.classes[state.cls].anchor||0) * r.scale;
    // Flat near the top of the curve on a young bike = the near-new sample is
    // too thin to resolve real decline (honest), NOT a genuine value floor.
    if(state.age <= 4 && anchorScaled && r.valueEnd >= 0.78*anchorScaled)
      buy += ` <span style="color:var(--amber)">⚠ Near-new depreciation for this class isn't resolved yet — too few young listings, so the curve is flat where it shouldn't be. Treat this as a floor; real loss over these years is likely higher.</span>`;
    else
      buy += ` <span style="color:var(--cyan)">The curve is flat here — the bike is near its value floor, so it has already done most of its depreciating. That's when a used bike is cheapest to own.</span>`;
  }
  $("buynote").innerHTML = buy;

  // keep price box in sync if untouched
  if(state.price==null) $("price").placeholder = Math.round(r.baseNow).toLocaleString("pl-PL");
}

function selectClass(cls){
  state.cls=cls; state.price=null; state.insurance=null; state.service=null;
  document.querySelectorAll(".mode-btn").forEach(b=>b.setAttribute("aria-pressed", b.dataset.cls===cls));
  $("price").value=""; $("ins").value=""; $("svc").value="";
  const d=CFG.classDefaults[cls];
  $("ins").placeholder=d.insurance_yr; $("svc").placeholder=d.service_per1000;
  render();
}

function build(){
  const host=$("modes");
  host.innerHTML = present.map((cc,i)=>{
    const d=CFG.classDefaults[cc];
    return `<button class="mode-btn" data-cls="${cc}" aria-pressed="${i===0}">${d.label}<small>${d.tag}</small></button>`;
  }).join("");
  host.addEventListener("click", e=>{const b=e.target.closest(".mode-btn"); if(b) selectClass(b.dataset.cls);});
  if(held.length){
    const labels = held.map(cc => CFG.classDefaults[cc] ? CFG.classDefaults[cc].label : cc).join(", ");
    $("heldNote").innerHTML = `<b>Gathering data:</b> ${labels} — too few clean listings so far to trust a depreciation curve, so they're held back rather than shown wrong.`;
  }

  $("age").addEventListener("input", e=>{state.age=+e.target.value; $("ageval").textContent=state.age; render();});
  $("hold").addEventListener("input", e=>{state.hold=+e.target.value; $("holdval").textContent=state.hold; render();});
  $("km").addEventListener("input", e=>{state.km=+e.target.value; $("kmval").textContent=state.km.toLocaleString("pl-PL"); render();});
  $("price").addEventListener("input", e=>{state.price = e.target.value? +e.target.value : null; render();});
  $("ins").addEventListener("input", e=>{state.insurance = e.target.value? +e.target.value : null; render();});
  $("svc").addEventListener("input", e=>{state.service = e.target.value? +e.target.value : null; render();});
  $("pump").addEventListener("input", e=>{state.pump = +e.target.value||CFG.pumpPetrol; render();});
  $("pcc").addEventListener("change", e=>{state.pcc = e.target.checked; render();});

  selectClass(present[0]);
}
build();
"""


def _controls() -> str:
    return """
  <div class="controls">
    <div class="field">
      <label>Engine class</label>
      <div class="modes" id="modes"></div>
      <p class="heldnote" id="heldNote"></p>
    </div>
    <div class="row">
      <div class="field">
        <label>Age when you buy</label>
        <div class="sliderline"><b class="mono"><span id="ageval">5</span></b><span>years old</span></div>
        <input type="range" id="age" min="1" max="18" step="1" value="5">
      </div>
      <div class="field">
        <label>How long you'll keep it</label>
        <div class="sliderline"><b class="mono"><span id="holdval">3</span></b><span>years</span></div>
        <input type="range" id="hold" min="1" max="8" step="1" value="3">
      </div>
      <div class="field">
        <label>Distance per year</label>
        <div class="sliderline"><b class="mono" id="kmval">8 000</b><span>km / year</span></div>
        <input type="range" id="km" min="1000" max="25000" step="500" value="8000">
      </div>
    </div>
    <div class="row">
      <div class="field">
        <label>Price you'd pay (blank = market fit)</label>
        <input type="number" id="price" step="500" placeholder="—"
          style="width:100%;font-family:'IBM Plex Mono',monospace;font-size:1rem;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:.55rem .7rem">
      </div>
      <div class="field">
        <label>Your insurance quote · OC/AC (zł/yr)</label>
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
    <div class="head">True cost to ride</div>
    <div class="perkm" id="perkm">—</div>
    <p class="yr">≈ <b id="yrnum">—</b> every year</p>
    <p class="band" id="bandtxt"></p>
    <p class="life" id="life"></p>
  </div>
  <div>
    <div class="head">Where the money goes</div>
    <div class="stack" id="stack" style="margin-top:.7rem"></div>
    <div class="receipt" id="receipt"></div>
    <div class="tot"><span>Total / year</span><span class="v mono" id="rectot">—</span></div>
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


def _render_html(agg: dict) -> str:
    meta = agg.get("meta", {})
    classes = agg.get("classes", {})
    order = meta.get("cc_order", [])
    # Need at least one *reliable* class — an unreliable curve would mislead the
    # whole calculator (reliable defaults True when the flag is absent).
    def _ok(cc: str) -> bool:
        c = classes.get(cc, {})
        return bool(c.get("points")) and c.get("reliable", True) is not False

    has_curves = any(_ok(cc) for cc in order) if order else bool(classes)
    sample = bool(meta.get("sample"))
    year = meta.get("current_year", "—")
    config = _client_config()
    agg_json = json.dumps(agg, ensure_ascii=False)

    sample_banner = (
        '<p class="kicker" style="color:var(--amber)">⚠ sample curves — live page uses real data</p>' if sample else ""
    )

    head = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>What a bike really costs · personal TCO · PL</title>
{_FONTS}
<style>{_STYLE}</style>
</head>
<body>
<div class="wrap">
<header class="reveal">
  <p class="kicker">Poland · used-bike ownership · {year}</p>
  <h1>The sticker is<br>the small print</h1>
  <p class="dek">A motorcycle's real cost isn't its price — it's what it loses,
  burns and bills you every year you keep it. This adds the lot up, per kilometre,
  on top of the depreciation we actually measure.</p>
  <div class="rule"></div>
  {sample_banner}
  <nav class="nav">
    <a href="cost.html" class="here">Personal cost</a>
    <a href="index.html">Public-money ledger</a>
    <a href="depreciation.html">Depreciation curves</a>
  </nav>
"""

    body = _controls() + "</header>\n" + _odometer() + _sections() if has_curves else "</header>\n" + _gate()

    foot = """
<footer>
  <div>METHOD · depreciation read off cross-sectional value-vs-age curves (weighted isotonic regression, private-seller slice), scaled to your price. Fuel/service/fees are coefficient models, user-adjustable.</div>
  <div>DATA · derived aggregate curves only — no listings reproduced. Insurance is never modelled (you paste a quote). Seasonal buy/sell timing arrives once a full tracking season is banked.</div>
</footer>
</div>
"""

    if not has_curves:
        return head + body + foot + "</body>\n</html>\n"
    return (
        head
        + body
        + foot
        + "<script>\nconst CFG = "
        + config
        + ";\nconst AGG = "
        + agg_json
        + ";\n"
        + _JS
        + "</script>\n</body>\n</html>\n"
    )
