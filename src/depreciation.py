"""Surface 1 (input) — motorcycle depreciation page, rendered from aggregates.

This is the *public* half of the depreciation handoff. The private engine emits
`aggregates.json` (smoothed value-vs-age curves + retention + coverage — derived
facts only, never a listing); this module embeds that JSON and draws the page
client-side in vanilla SVG. No matplotlib, no backend, no marketplace data — so
it deploys as a static file and structurally cannot leak the source rows.

The economics (isotonic smoothing, retention, sweet-spot) all happen upstream in
the engine; here we only present what it computed.
"""

from __future__ import annotations

import json
import logging
import os

from src import ui

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = "public"


def render_depreciation(
    aggregates_path: str,
    *,
    output_dir: str | None = None,
    filename: str = "depreciation.html",
) -> str:
    """Render the depreciation page from an aggregates JSON file."""
    output_dir = output_dir or DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, filename)

    with open(aggregates_path, encoding="utf-8") as f:
        agg = json.load(f)

    with open(out_path, "w", encoding="utf-8") as f:
        car_agg = {"meta": {}, "models": {}}
        _car = os.path.join(os.path.dirname(aggregates_path) or ".", "cars_aggregates.json")
        if os.path.exists(_car):
            with open(_car, encoding="utf-8") as cf:
                car_agg = json.load(cf)
        f.write(_render_html(agg, car_agg))
    logger.info("Rendered depreciation page → %s", out_path)
    return out_path


_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Anton&family=IBM+Plex+Mono:wght@400;500&'
    'family=Newsreader:ital,wght@0,400;1,400&display=swap" rel="stylesheet">'
)

_STYLE = """
:root{
  --bg:#0c0c0f; --panel:#15151b; --panel-2:#101015; --ink:#ece8e1; --muted:#8f8a80;
  --line:#26262e; --amber:#f7b801; --orange:#f35b04; --red:#d62828; --cyan:#4cc9f0;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0; background:var(--bg); color:var(--ink);
  font-family:"Newsreader",Georgia,serif; font-size:17px; line-height:1.55; -webkit-font-smoothing:antialiased}
body::before{content:""; position:fixed; inset:0; z-index:0; pointer-events:none; opacity:.05;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
body::after{content:""; position:fixed; inset:0; z-index:0; pointer-events:none;
  background:radial-gradient(120% 80% at 50% -10%, rgba(247,184,1,.10), transparent 55%)}
.wrap{position:relative; z-index:1; max-width:1080px; margin:0 auto; padding:0 22px 5rem}
.mono{font-family:"IBM Plex Mono",ui-monospace,monospace; font-variant-numeric:tabular-nums}

.sample{margin:1.4rem 0 0; font-family:"IBM Plex Mono",monospace; font-size:.78rem; color:var(--amber);
  border:1px dashed rgba(247,184,1,.45); border-radius:8px; padding:.6rem .9rem}

header{padding:5rem 0 2rem; border-bottom:1px solid var(--line)}
.kicker{font-family:"IBM Plex Mono",monospace; letter-spacing:.34em; text-transform:uppercase;
  font-size:.7rem; color:var(--amber); margin:0 0 1.1rem}
h1{font-family:"Anton",Impact,sans-serif; font-weight:400; text-transform:uppercase;
  font-size:clamp(2.9rem,8.5vw,6.2rem); line-height:.92; letter-spacing:.01em; margin:0;
  background:linear-gradient(92deg,var(--cyan),var(--amber) 48%,var(--red));
  -webkit-background-clip:text; background-clip:text; color:transparent}
.dek{font-size:1.16rem; color:#cfcabf; max-width:46ch; margin:1.3rem 0 0; font-style:italic}
.redline{height:3px; margin:1.9rem 0 0; border-radius:2px;
  background:linear-gradient(90deg,var(--cyan),var(--amber) 50%,var(--red))}
.nav{display:flex; gap:.4rem 1.2rem; flex-wrap:wrap; margin-top:1.5rem;
  font-family:"IBM Plex Mono",monospace; font-size:.74rem}
.nav a{color:var(--muted); text-decoration:none; border-bottom:1px dotted transparent; padding-bottom:1px}
.nav a:hover{color:var(--amber); border-bottom-color:var(--amber)}
.nav a.here{color:var(--ink)}
.chips{display:flex; flex-wrap:wrap; gap:.5rem 1.6rem; margin-top:1.6rem}
.chip b{display:block; font-size:1.7rem; color:var(--ink); font-family:"IBM Plex Mono",monospace}
.chip span{color:var(--muted); text-transform:uppercase; letter-spacing:.12em; font-size:.66rem;
  font-family:"IBM Plex Mono",monospace}

section{margin-top:3rem}
.eyebrow{font-family:"IBM Plex Mono",monospace; letter-spacing:.28em; text-transform:uppercase;
  font-size:.72rem; color:var(--muted); display:flex; align-items:center; gap:.8rem}
.eyebrow::before{content:""; width:26px; height:2px; background:var(--amber)}
h2{font-family:"Anton",sans-serif; font-weight:400; text-transform:uppercase; letter-spacing:.02em;
  font-size:1.9rem; margin:.5rem 0 .2rem}
.lede{color:var(--muted); margin:.1rem 0 1.2rem; max-width:64ch}
.card{background:linear-gradient(180deg,var(--panel),var(--panel-2)); border:1px solid var(--line);
  border-radius:14px; padding:1.3rem 1.4rem; box-shadow:0 24px 60px -36px rgba(0,0,0,.9)}
svg{width:100%; height:auto; display:block}

.legend{display:flex; flex-wrap:wrap; gap:.4rem 1.2rem; margin-top:.7rem;
  font-family:"IBM Plex Mono",monospace; font-size:.74rem; color:var(--muted)}
.legend i{display:inline-block; width:14px; height:3px; vertical-align:middle; margin-right:.4rem; border-radius:2px}

.grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(330px,1fr)); gap:1.1rem; margin-top:1.1rem}
.cls{border-top:3px solid var(--accent)}
.cls h3{font-family:"Anton",sans-serif; font-weight:400; letter-spacing:.03em; text-transform:uppercase;
  font-size:1.4rem; margin:.1rem 0; color:var(--accent)}
.cls .sub{font-family:"IBM Plex Mono",monospace; font-size:.74rem; color:var(--muted); margin:0 0 .7rem}

table{width:100%; border-collapse:collapse; font-family:"IBM Plex Mono",monospace;
  font-size:.82rem; margin-top:.7rem; font-variant-numeric:tabular-nums}
th,td{padding:6px 9px; text-align:right; border-bottom:1px solid var(--line)}
th{color:var(--muted); font-weight:500; text-transform:uppercase; letter-spacing:.08em; font-size:.66rem}
th:first-child,td:first-child{text-align:left}
tbody tr:hover{background:rgba(247,184,1,.05)}
.spot{color:#0c0c0f; background:var(--amber); padding:1px 8px; border-radius:999px; font-weight:600}
.lowconf{font-family:"IBM Plex Mono",monospace; font-size:.74rem; color:var(--muted); margin:.8rem 0 0}
.lowbadge{font-family:"IBM Plex Mono",monospace; font-size:.58rem; letter-spacing:.12em; text-transform:uppercase;
  color:var(--amber); border:1px dashed rgba(247,184,1,.5); border-radius:999px; padding:1px 7px; vertical-align:middle}
.card.low{opacity:.82}

.note{border-left:3px solid var(--cyan); background:rgba(76,201,240,.05); margin-top:1.1rem;
  padding:1.1rem 1.4rem; border-radius:0 12px 12px 0; color:#cfcabf; font-size:1.02rem}
.note h2{font-size:1.45rem; margin:.1rem 0 .5rem} .note ul{margin:.6rem 0 0; padding-left:1.1rem}
.note li{margin:.5rem 0} .note b{color:var(--ink)}

footer{margin-top:3.4rem; padding-top:1.4rem; border-top:1px solid var(--line);
  font-family:"IBM Plex Mono",monospace; font-size:.74rem; color:var(--muted); line-height:1.7}

@keyframes rise{from{opacity:0; transform:translateY(16px)} to{opacity:1; transform:none}}
.reveal{animation:rise .7s cubic-bezier(.2,.7,.2,1) both}
@media (prefers-reduced-motion:reduce){.reveal{animation:none}}
"""

STRINGS = {'en': {'veh_moto': 'Moto', 'veh_car': 'Car', 'h1': 'How fast a<br>vehicle bleeds value', 'dek_moto': 'Cross-sectional depreciation curves by engine class, read off private-seller listings and smoothed with weighted isotonic regression.', 'dek_car': 'Per-model depreciation curves for the Polish used-car market — value vs age from private-seller listings.', 'nav_cost': 'Personal cost', 'nav_ledger': 'Public-money ledger', 'nav_depr': 'Depreciation curves', 'car_eye': 'By model', 'car_h': 'Car depreciation by model', 'car_lede': 'Per-model value-vs-age curves from PL private-seller car listings (the most-listed models). Dots are raw medians, the band is P25–P75, the line is the smoothed fit. Read the shape: how much value each model keeps.', 'car_none': 'No car curves yet.'}, 'pl': {'veh_moto': 'Moto', 'veh_car': 'Auto', 'h1': 'Jak szybko<br>pojazd traci wartość', 'dek_moto': 'Przekrojowe krzywe utraty wartości wg klasy silnika, odczytane z ofert prywatnych i wygładzone regresją izotoniczną.', 'dek_car': 'Krzywe utraty wartości per model dla polskiego rynku aut używanych — wartość względem wieku z ofert prywatnych.', 'nav_cost': 'Koszt osobisty', 'nav_ledger': 'Bilans publiczny', 'nav_depr': 'Krzywe wartości', 'car_eye': 'Wg modelu', 'car_h': 'Utrata wartości aut wg modelu', 'car_lede': 'Krzywe wartość-wiek per model z polskich ofert prywatnych (najczęściej wystawiane modele). Kropki to mediany, pasmo to P25–P75, linia to dopasowanie. Patrz na kształt: ile wartości utrzymuje dany model.', 'car_none': 'Brak krzywych dla aut.'}}

# Plain (non-f-string) JS — single braces, no escaping. `AGG` is prepended by
# the renderer. This draws every chart client-side from the embedded aggregates.
_JS = r"""
const M = AGG.meta, HEAT = M.heat, ORDER = M.cc_order;
const present = ORDER.filter(cc => AGG.classes[cc] && AGG.classes[cc].points.length);
// Classes whose curve the engine trusts. Unreliable ones (thin/noisy data) are
// kept out of the headline figures + summary and only shown, badged, per-class.
const reliable = present.filter(cc => AGG.classes[cc].reliable !== false);
const shown = reliable.length ? reliable : present;
document.querySelector("#nclasses b").textContent = reliable.length;

const fmtK = v => v >= 1000 ? (v/1000).toFixed(0)+"k" : v.toFixed(0);
const fmtPct = v => v.toFixed(0)+"%";

// Catmull-Rom → cubic-bezier so the value line reads as a smooth curve instead
// of a sharp polyline. Pixel-space points in, SVG path string out.
function smoothPath(pts){
  if(pts.length < 3) return pts.map((p,i)=>`${i?'L':'M'}${p[0]},${p[1]}`).join(" ");
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for(let i=0;i<pts.length-1;i++){
    const p0=pts[i-1]||pts[i], p1=pts[i], p2=pts[i+1], p3=pts[i+2]||pts[i+1];
    const c1x=p1[0]+(p2[0]-p0[0])/6, c1y=p1[1]+(p2[1]-p0[1])/6;
    const c2x=p2[0]-(p3[0]-p1[0])/6, c2y=p2[1]-(p3[1]-p1[1])/6;
    d += ` C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2[0]},${p2[1]}`;
  }
  return d;
}

// Generic multi-series line chart → SVG string.
// series: [{color, line:[[x,y]], dots:[[x,y]], band:[[x,lo,hi]]}]
function chart(series, {h=380, yfmt=fmtK, xlabel="AGE (YEARS)"} = {}){
  const w = 820, pad = {l:54, r:16, t:14, b:34};
  const xs=[], ys=[];
  series.forEach(s=>{
    (s.line||[]).forEach(p=>{xs.push(p[0]); ys.push(p[1]);});
    (s.dots||[]).forEach(p=>{xs.push(p[0]); ys.push(p[1]);});
    (s.band||[]).forEach(p=>{xs.push(p[0]); ys.push(p[1]); ys.push(p[2]);});
  });
  const xmin=Math.min(...xs), xmax=Math.max(...xs);
  let ymin=Math.min(...ys, 0), ymax=Math.max(...ys);
  if(ymax===ymin) ymax=ymin+1;
  const X = x => pad.l + (x-xmin)/((xmax-xmin)||1) * (w-pad.l-pad.r);
  const Y = y => h-pad.b - (y-ymin)/((ymax-ymin)||1) * (h-pad.t-pad.b);
  let out = `<svg viewBox="0 0 ${w} ${h}" role="img">`;
  for(let i=0;i<=4;i++){
    const yv = ymin + (ymax-ymin)*i/4, py = Y(yv);
    out += `<line x1="${pad.l}" y1="${py}" x2="${w-pad.r}" y2="${py}" stroke="#ffffff" stroke-opacity="0.06"/>`;
    out += `<text x="${pad.l-8}" y="${py+3}" fill="#8f8a80" font-size="10" text-anchor="end" font-family="IBM Plex Mono,monospace">${yfmt(yv)}</text>`;
  }
  for(let a=Math.ceil(xmin); a<=Math.floor(xmax); a++){
    out += `<text x="${X(a)}" y="${h-pad.b+18}" fill="#8f8a80" font-size="10" text-anchor="middle" font-family="IBM Plex Mono,monospace">${a}</text>`;
  }
  out += `<text x="${w/2}" y="${h-2}" fill="#8f8a80" font-size="10" text-anchor="middle" font-family="IBM Plex Mono,monospace" letter-spacing="1">${xlabel}</text>`;
  series.forEach(s=>{
    if(s.band && s.band.length>1){
      const top = s.band.map(p=>`${X(p[0])},${Y(p[2])}`).join(" ");
      const bot = s.band.slice().reverse().map(p=>`${X(p[0])},${Y(p[1])}`).join(" ");
      out += `<polygon points="${top} ${bot}" fill="${s.color}" fill-opacity="0.14"/>`;
    }
    (s.dots||[]).forEach(p=> out += `<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="2.6" fill="${s.color}" fill-opacity="0.4"/>`);
    if(s.line && s.line.length>1){
      const px = s.line.map(p=>[X(p[0]),Y(p[1])]);
      out += `<path d="${smoothPath(px)}" fill="none" stroke="${s.color}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>`;
    }
  });
  return out + `</svg>`;
}

function legend(list){
  return `<div class="legend">` + list.map(cc=>`<span><i style="background:${HEAT[cc]}"></i>${cc}cc</span>`).join("") + `</div>`;
}

// Figure 01 — price vs age (trusted classes only)
const overview = shown.map(cc=>{
  const pts = AGG.classes[cc].points;
  return {color:HEAT[cc], line:pts.map(p=>[p.age,p.smooth]), dots:pts.map(p=>[p.age,p.median])};
});
document.querySelector("#overview").innerHTML = chart(overview);
document.querySelector("#overviewLegend").innerHTML = legend(shown);

// Figure 02 — value retained
const retention = shown.map(cc=>{
  const pts = AGG.classes[cc].points;
  return {color:HEAT[cc], line:pts.map(p=>[p.age,p.retained_pct])};
});
document.querySelector("#retention").innerHTML = chart(retention, {yfmt:fmtPct});
document.querySelector("#retentionLegend").innerHTML = legend(shown);

// Summary table — trusted classes only
function retAt(pts, age){ const p = pts.find(p=>p.age===age); return p? Math.round(p.retained_pct)+"%" : "·"; }
document.querySelector("#summary").innerHTML =
  `<table><thead><tr><th>class</th><th>anchor PLN</th><th>kept 3y</th><th>kept 5y</th><th>kept 10y</th><th>buy from</th></tr></thead><tbody>`
  + shown.map(cc=>{
      const a = AGG.classes[cc];
      const spot = a.sweet_spot_age!=null ? `<span class="spot">${a.sweet_spot_age}y+</span>` : "·";
      return `<tr><td style="color:${HEAT[cc]}">${cc}cc</td><td>${a.anchor.toLocaleString("pl-PL")}</td>`
        + `<td>${retAt(a.points,3)}</td><td>${retAt(a.points,5)}</td><td>${retAt(a.points,10)}</td><td>${spot}</td></tr>`;
    }).join("") + `</tbody></table>`
  + (reliable.length < present.length
      ? `<p class="lowconf">Held back — too few clean listings to trust a curve yet: `
        + present.filter(cc=>AGG.classes[cc].reliable===false).map(cc=>cc+"cc").join(", ") + `.</p>`
      : "");

// Per-class cards — show every class, badge the low-confidence ones
document.querySelector("#classes").innerHTML = present.map((cc,i)=>{
  const a = AGG.classes[cc], pts = a.points, low = a.reliable===false;
  const mini = chart([{color:HEAT[cc],
      band: pts.map(p=>[p.age,p.p25,p.p75]),
      dots: pts.map(p=>[p.age,p.median]),
      line: pts.map(p=>[p.age,p.smooth])}], {h:300});
  const rows = pts.map(p=>{
    const depr = p.annual_depr ? "−"+p.annual_depr.toLocaleString("pl-PL") : "·";
    const km = p.median_km ? p.median_km.toLocaleString("pl-PL") : "·";
    return `<tr><td>${p.age}y</td><td>${p.smooth.toLocaleString("pl-PL")}</td><td>${Math.round(p.retained_pct)}%</td><td>${depr}</td><td>${km}</td><td>${p.n}</td></tr>`;
  }).join("");
  const spot = a.sweet_spot_age!=null ? `buy from ~${a.sweet_spot_age}y` : "early drop unresolved";
  const badge = low ? `<span class="lowbadge">limited data</span>` : "";
  return `<div class="card cls reveal${low?' low':''}" style="--accent:${HEAT[cc]}; animation-delay:${(0.05*i).toFixed(2)}s">
    <h3>${cc}cc ${badge}</h3><p class="sub">anchor ${a.anchor.toLocaleString("pl-PL")} PLN · ${spot}${low?' · curve not yet trustworthy':''}</p>${mini}
    <table><thead><tr><th>age</th><th>fit PLN</th><th>kept</th><th>depr/yr</th><th>med km</th><th>n</th></tr></thead><tbody>${rows}</tbody></table>
  </div>`;
}).join("");

// Per-model gallery — the precise tier (make+model), richest data first.
(function(){
  const host = document.querySelector("#models");
  if(!host) return;
  const VIO = "#9d7bff";
  const entries = Object.entries(AGG.models||{})
    .filter(([n,m]) => m.points && m.points.length)
    .sort((a,b) => (b[1].n_samples||0)-(a[1].n_samples||0));
  if(!entries.length){ host.innerHTML = `<p class="lede">No per-model curves yet — needs more data per model.</p>`; return; }
  const k5 = pts => { const p = pts.find(p=>p.age===5); return p ? Math.round(p.retained_pct)+"%" : "·"; };
  host.innerHTML = entries.map(([name,a],i)=>{
    const pts=a.points, low=a.reliable===false;
    const mini = chart([{color:VIO,
      band: pts.map(p=>[p.age,p.p25,p.p75]),
      dots: pts.map(p=>[p.age,p.median]),
      line: pts.map(p=>[p.age,p.smooth])}], {h:240});
    const badge = low ? `<span class="lowbadge">limited</span>` : "";
    return `<div class="card cls reveal${low?' low':''}" style="--accent:${VIO}; animation-delay:${(0.03*i).toFixed(2)}s">
      <h3 style="font-size:1.15rem">${name} ${badge}</h3>
      <p class="sub">${a.category||"—"} · anchor ${a.anchor.toLocaleString("pl-PL")} PLN · kept 5y ${k5(pts)} · n=${a.n_samples}</p>${mini}
    </div>`;
  }).join("");
})();

// --- car depreciation gallery (self-contained, reuses chart()) ---
(function(){
  const host = document.querySelector("#carmodels");
  if(!host || typeof AGG_CAR === "undefined") return;
  const VIO = "#9d7bff";
  const tc = s => (s||"").replace(/(^|[\s-])\w/g, c => c.toUpperCase());
  const k5 = pts => { const p = pts.find(p=>p.age===5); return p ? Math.round(p.retained_pct)+"%" : "·"; };
  const ms = Object.entries(AGG_CAR.models||{})
    .filter(([n,m]) => m.points && m.points.length)
    .sort((a,b) => (b[1].n_samples||0)-(a[1].n_samples||0));
  host.innerHTML = ms.length ? ms.map(([name,a],i)=>{
    const pts=a.points;
    const mini = chart([{color:VIO, band:pts.map(p=>[p.age,p.p25,p.p75]), dots:pts.map(p=>[p.age,p.median]), line:pts.map(p=>[p.age,p.smooth])}], {h:240});
    return `<div class="card cls reveal" style="--accent:${VIO}; animation-delay:${(0.02*i).toFixed(2)}s"><h3 style="font-size:1.1rem">${tc(name)}</h3><p class="sub">${a.fuel||"—"} · anchor ${a.anchor.toLocaleString("pl-PL")} PLN · kept 5y ${k5(pts)} · n=${a.n_samples}</p>${mini}</div>`;
  }).join("") : `<p class="lede">${_t("car_none")||"No car curves yet."}</p>`;
})();
function applyVeh(){
  const car = (typeof UI!=="undefined") && UI.veh==="car";
  const mo = document.querySelector("#motoSecs"), ca = document.querySelector("#carSecs");
  if(mo) mo.style.display = car ? "none" : "";
  if(ca) ca.style.display = car ? "" : "none";
  const dek = document.querySelector("#dek");
  if(dek) dek.innerHTML = (_t(car?"dek_car":"dek_moto")) || dek.innerHTML;
}
window.addEventListener("uichange", applyVeh);
applyVeh();

"""


def _render_html(agg: dict, car_agg: dict | None = None) -> str:
    car_agg = car_agg or {"meta": {}, "models": {}}
    meta = agg.get("meta", {})
    cov = agg.get("coverage", {})
    has_data = bool(agg.get("classes")) or bool(car_agg.get("models"))
    sample = bool(meta.get("sample"))
    sample_banner = (
        '<p class="sample">⚠ SAMPLE DATA — generated for layout preview. The live page '
        "renders the same shape from the engine's real <code>aggregates.json</code>.</p>"
        if sample
        else ""
    )
    year = meta.get("current_year", "—")
    config = json.dumps(agg, ensure_ascii=False)
    car_config = json.dumps(car_agg, ensure_ascii=False)

    body = (
        _data_sections()
        if has_data
        else '<section class="reveal"><div class="card"><h2>No curve yet</h2>'
        '<p class="lede">The aggregates file holds no classes with enough data to draw curves.</p>'
        "</div></section>"
    )

    head = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Motorcycle depreciation · PL used market</title>
{_FONTS}
<style>{_STYLE}{ui.SELECTOR_CSS}</style>
</head>
<body>
<div class="wrap">
<header class="reveal">
  {ui.selector_bar()}
  <p class="kicker">Polish used market · reference year {year}</p>
  <h1 data-i18n-html="h1">How fast a<br>bike bleeds value</h1>
  <p class="dek" id="dek" data-i18n="dek_moto">Cross-sectional depreciation curves by engine class, read off
  private-seller listings and smoothed with weighted isotonic regression.</p>
  <div class="redline"></div>
  <div class="chips">
    <div class="chip"><b>{cov.get("n_total", 0):,}</b><span>valid bikes</span></div>
    <div class="chip"><b>{cov.get("pct_year", 0):.0f}%</b><span>have model year</span></div>
    <div class="chip"><b>{cov.get("pct_cc", 0):.0f}%</b><span>engine size</span></div>
    <div class="chip" id="nclasses"><b>—</b><span>engine classes</span></div>
  </div>
  {sample_banner}
  <nav class="nav">
    <a href="cost.html" data-i18n="nav_cost">Personal cost</a>
    <a href="index.html" data-i18n="nav_ledger">Public-money ledger</a>
    <a href="depreciation.html" class="here" data-i18n="nav_depr">Depreciation curves</a>
  </nav>
</header>
{body}
<footer>
  <div>METHOD · cross-sectional medians, private-seller slice; smoothing = weighted isotonic regression (PAVA) on log-price, computed upstream.</div>
  <div>SOURCE · derived aggregate curves only — no listings reproduced. Registration overlay (CEPiK) planned.</div>
</footer>
</div>
"""
    if not has_data:
        return head + "</body>\n</html>\n"
    return (
        head
        + "<script>\nconst AGG = " + config + ";\nconst AGG_CAR = " + car_config
        + ";\nwindow.T = " + json.dumps(STRINGS, ensure_ascii=False) + ";\n"
        + ui.SELECTOR_JS + "\n" + _JS + "</script>\n</body>\n</html>\n"
    )


def _data_sections() -> str:
    return """
<div id="motoSecs">
<section class="reveal" style="animation-delay:.08s">
  <p class="eyebrow">Figure 01</p>
  <h2>Price against age</h2>
  <p class="lede">Faint dots are raw medians per (class, age) cell; the solid line
  is the monotone isotonic fit. Bigger engines sit higher and shed more value.</p>
  <div class="card"><div id="overview"></div><div id="overviewLegend"></div></div>
</section>

<section class="reveal" style="animation-delay:.12s">
  <p class="eyebrow">Figure 02</p>
  <h2>Value retained</h2>
  <p class="lede">Each class indexed to 100% at its youngest tracked cohort — the
  lower a line falls, the faster that class hands value to the next owner.</p>
  <div class="card"><div id="retention"></div><div id="retentionLegend"></div></div>
</section>

<section class="reveal" style="animation-delay:.16s">
  <p class="eyebrow">The read</p>
  <h2>Summary &amp; buy timing</h2>
  <p class="lede">"Buy from" marks the first age where yearly value loss drops below
  8% of the near-new price — past the cliff the first owner already paid.</p>
  <div class="card"><div id="summary"></div></div>
  <div class="note">
    <h2>Where registration data plugs in</h2>
    <ul>
      <li><b>Survivorship.</b> Old bikes still listed are the well-kept survivors;
      CEPiK de-registrations per cohort give a survival fraction to discount the tail.</li>
      <li><b>Sample bias.</b> Sellers over-list newer bikes; CEPiK first-registration
      volumes re-weight the medians toward true cohort sizes.</li>
    </ul>
  </div>
</section>

<section class="reveal">
  <p class="eyebrow">By engine class</p>
  <h2>Class breakdowns</h2>
  <div class="grid" id="classes"></div>
</section>

<section class="reveal">
  <p class="eyebrow">By model</p>
  <h2>Model-level curves</h2>
  <p class="lede">The precise tier — depreciation for a single make + model, where there's
  enough data. Includes dealer listings for coverage, so read the <b>shape</b> (how much
  value it keeps), not the absolute złoty.</p>
  <div class="grid" id="models"></div>
</section>
</div>
<div id="carSecs" style="display:none">
<section class="reveal">
  <p class="eyebrow" data-i18n="car_eye">By model</p>
  <h2 data-i18n="car_h">Car depreciation by model</h2>
  <p class="lede" data-i18n="car_lede">Per-model value-vs-age curves from PL private-seller car listings — read the shape: how much value each keeps.</p>
  <div class="grid" id="carmodels"></div>
</section>
</div>
"""
