"""Surface 3 — "In practice": where Gdańsk's transport money actually goes.

The viral hook of the project, and the one surface that is pure *public* data — no
marketplace listings, no scraper. It answers a question the other two surfaces set
up ("the careful buyer pays for a car; what does the city pay around them?") with
Gdańsk's own budget, 2004–2024.

Two honest findings drive the page, both straight from GUS BDL (dział 600, MnPP):

  * **The flip.** Road chapters (60015+60016) only enter BDL in 2012, but inside
    that window roads fall from ~70% of the transport budget (the Euro-2012 spike)
    to ~25% by 2024, while non-road transport (transit + rail = dział-600 total
    minus all road chapters ≈ ZTM bus/tram + SKM/PKM) climbs the other way. Gdańsk
    shifted money *toward* transit — the opposite of the lazy "cars eat everything"
    take, so we tell the true story instead.

  * **Build vs run.** The same budget splits into wydatki majątkowe (capital —
    building) and bieżące (current — operating + maintenance, where road repairs
    like Al. Rzeczypospolitej live). Current spending now dwarfs capital (~1 550 vs
    ~430 zł/cap in 2024): most transport money just *runs and patches* the system,
    it doesn't expand it.

Then a real interactive map (Leaflet + the city's own investment-map dataset) pins
every road and public-transit investment by where it was actually built, sized by
cost — so you can see the capital wave (road megaprojects 2012–16 on the port/airport
axis; the tram + PKM build-out 2008–15 in the southern districts) on the ground.

Static + self-contained for the budget charts (Python embeds the BDL series + the
investment list, vanilla JS draws the charts as hand-rolled SVG). The map is the one
exception: it pulls Leaflet + a basemap from a CDN, which only matters for a literal
geographic map and stays behind the same auth gate as the page.
"""

from __future__ import annotations

import json
import logging
import os

from src import ui

logger = logging.getLogger(__name__)

DEFAULT_BUDGET = os.path.join("data", "stage3_gdansk_transport.json")
DEFAULT_INVEST = os.path.join("data", "stage3_gdansk_investments.json")

MODE_COLOR = {"road": "#f4a31c", "transit": "#34d399"}

STRINGS = {
    "en": {
        "kicker": "Gdańsk · public transport budget · 2004–2024",
        "h1": "Where the city's<br>mobility money goes",
        "dek": "Not a polemic — Gdańsk's own transport budget, read off GUS public finance data. Who gets the money: road builders, or the people on trams and trains?",
        "nav_cost": "Personal cost", "nav_ledger": "Public-money ledger",
        "nav_depr": "Depreciation curves", "nav_practice": "In practice",
        "flip_eye": "The flip", "flip_h": "Roads vs transit, per resident",
        "flip_lede": "Road chapters enter the data in 2012. Since then the split inverted — roads slid from most of the transport budget to a quarter of it, while transit + rail climbed. Złoty per resident.",
        "flip_roads": "Roads (build + maintain)", "flip_transit": "Transit + rail",
        "flip_share": "roads = {v}% of transport spend",
        "run_eye": "Build vs run", "run_h": "Most of it just runs the system",
        "run_lede": "The same budget, split by economic type. Capital = building; current = operating + maintenance, where road repairs like Al. Rzeczypospolitej sit. Current now dwarfs capital — the city mostly runs and patches what exists.",
        "run_current": "Current (run + repair)", "run_capital": "Capital (build)",
        "map_eye": "On the ground", "map_h": "What the capital actually built, and where",
        "map_lede": "Every road and public-transit investment from the city's own investment map, dropped where it was built. Circle size = total cost; colour = roads vs transit. Click a circle for the cost and how much was city money vs EU. The road megaprojects cluster on the port/airport axis (2012–16); the tram + PKM build-out sits in the southern districts (2008–15).",
        "map_note": "Source · Gdańska Mapa Inwestycji (gdansk.pl). Circle area ∝ total cost. Drag to pan, double-click to zoom.",
        "f_all": "All", "f_road": "Roads", "f_transit": "Transit", "f_recent": "2018+ only",
        "pop_total": "total", "pop_city": "city money", "pop_ue": "EU funds", "pop_mln": "mln zł",
        "leg_road": "Roads / car", "leg_transit": "Public transit",
        "axis_zl_cap": "zł / resident",
        "src": "Sources · GUS Bank Danych Lokalnych, dział 600 (budget series) + Gdańska Mapa Inwestycji (project locations & costs). Derived totals only — no marketplace data.",
    },
    "pl": {
        "kicker": "Gdańsk · budżet transportu · 2004–2024",
        "h1": "Dokąd płynie miejski<br>budżet na transport",
        "dek": "To nie polemika — to budżet transportowy Gdańska, odczytany z danych GUS o finansach publicznych. Kto dostaje pieniądze: budowniczowie dróg czy pasażerowie tramwajów i kolei?",
        "nav_cost": "Koszt osobisty", "nav_ledger": "Bilans publiczny",
        "nav_depr": "Krzywe wartości", "nav_practice": "W praktyce",
        "flip_eye": "Odwrócenie", "flip_h": "Drogi kontra transit, na mieszkańca",
        "flip_lede": "Rozdziały drogowe wchodzą do danych w 2012. Od tego czasu proporcje się odwróciły — drogi spadły z większości budżetu transportu do ćwierci, a transit + kolej wzrosły. Złote na mieszkańca.",
        "flip_roads": "Drogi (budowa + utrzymanie)", "flip_transit": "Transit + kolej",
        "flip_share": "drogi = {v}% wydatków na transport",
        "run_eye": "Budowa kontra utrzymanie", "run_h": "Większość to samo utrzymanie",
        "run_lede": "Ten sam budżet wg rodzaju. Majątkowe = budowa; bieżące = utrzymanie + eksploatacja, tu mieszczą się remonty dróg jak al. Rzeczypospolitej. Bieżące dziś znacznie przewyższają majątkowe — miasto głównie utrzymuje i łata to, co jest.",
        "run_current": "Bieżące (utrzymanie)", "run_capital": "Majątkowe (budowa)",
        "map_eye": "W terenie", "map_h": "Co i gdzie zbudowano",
        "map_lede": "Każda inwestycja drogowa i transportu zbiorowego z miejskiej mapy inwestycji, naniesiona tam, gdzie powstała. Wielkość koła = koszt całkowity; kolor = drogi czy transit. Kliknij koło, by zobaczyć koszt i ile to pieniądze miasta, a ile z UE. Drogowe megainwestycje skupiają się na osi port–lotnisko (2012–16); tramwaje i PKM — na południu (2008–15).",
        "map_note": "Źródło · Gdańska Mapa Inwestycji (gdansk.pl). Pole koła ∝ koszt. Przeciągnij, dwuklik przybliża.",
        "f_all": "Wszystko", "f_road": "Drogi", "f_transit": "Transit", "f_recent": "tylko 2018+",
        "pop_total": "całość", "pop_city": "pieniądze miasta", "pop_ue": "środki UE", "pop_mln": "mln zł",
        "leg_road": "Drogi / auto", "leg_transit": "Transport zbiorowy",
        "axis_zl_cap": "zł / mieszkańca",
        "src": "Źródła · GUS Bank Danych Lokalnych, dział 600 (szereg budżetowy) + Gdańska Mapa Inwestycji (lokalizacje i koszty). Tylko zagregowane sumy — bez danych z ogłoszeń.",
    },
}

_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Spline+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">'
)
_LEAFLET = (
    '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">'
    '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>'
)

_STYLE = """
:root{
  --bg:#0c0f12; --panel:#13181d; --line:#252c33; --ink:#eef1f3; --muted:#8b97a6;
  --road:#f4a31c; --transit:#34d399; --cap:#f4731c;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0; background:
  radial-gradient(120% 80% at 80% -10%, #16202b 0%, transparent 55%),
  radial-gradient(90% 60% at -10% 10%, #15211a 0%, transparent 50%), var(--bg);
  color:var(--ink); font-family:"Spline Sans",system-ui,sans-serif; line-height:1.55;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1060px; margin:0 auto; padding:2rem 1.4rem 5rem}
.kicker{font-family:"IBM Plex Mono",monospace; font-size:.74rem; letter-spacing:.18em;
  text-transform:uppercase; color:var(--muted)}
h1{font-family:"Archivo Black",sans-serif; font-weight:400; font-size:clamp(2.3rem,6vw,4rem);
  line-height:.98; letter-spacing:-.02em; margin:.5rem 0 .8rem}
.dek{font-size:1.06rem; color:#c7ced6; max-width:62ch; margin:0}
.redline{height:4px; width:84px; margin:1.5rem 0; border-radius:2px;
  background:linear-gradient(90deg,var(--road),var(--transit))}
.nav{display:flex; gap:.4rem 1.3rem; flex-wrap:wrap; margin-top:1.6rem;
  font-family:"IBM Plex Mono",monospace; font-size:.82rem}
.nav a{color:var(--muted); text-decoration:none; padding-bottom:2px; border-bottom:1px solid transparent}
.nav a:hover{color:var(--ink)} .nav a.here{color:var(--ink); border-bottom-color:var(--road)}
section{margin-top:3.4rem}
.eyebrow{font-family:"IBM Plex Mono",monospace; font-size:.72rem; letter-spacing:.16em;
  text-transform:uppercase; color:var(--road)}
h2{font-family:"Archivo Black",sans-serif; font-weight:400; font-size:clamp(1.5rem,3.4vw,2.1rem);
  letter-spacing:-.01em; margin:.3rem 0 .5rem}
.lede{color:#bac2cb; max-width:64ch; margin:0 0 1.3rem}
.card{background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:1.2rem 1.3rem}
svg{display:block; width:100%; height:auto; overflow:visible}
.legend{display:flex; gap:1.1rem; flex-wrap:wrap; font-family:"IBM Plex Mono",monospace;
  font-size:.76rem; color:var(--muted); margin-top:.8rem}
.legend i{display:inline-block; width:11px; height:11px; border-radius:50%; margin-right:.4rem; vertical-align:-1px}
.mapctl{display:flex; gap:1rem; align-items:center; flex-wrap:wrap; margin-bottom:.7rem}
.mapctl .seg{display:inline-flex; border:1px solid var(--line); border-radius:999px; overflow:hidden;
  background:var(--panel); font-family:"IBM Plex Mono",monospace}
.mapctl .seg button{appearance:none; border:0; background:transparent; color:var(--muted); cursor:pointer;
  font:inherit; font-size:.76rem; padding:.42rem .9rem; transition:.15s}
.mapctl .seg button:hover{color:var(--ink)}
.mapctl .seg button.on{background:var(--ink); color:#0b0b0f}
.mapctl .rec{font-family:"IBM Plex Mono",monospace; font-size:.76rem; color:var(--muted); cursor:pointer; user-select:none}
#map{height:600px; border-radius:16px; border:1px solid var(--line); margin:0; background:#0f141a; z-index:0}
.leaflet-popup-content-wrapper,.leaflet-popup-tip{background:#13181d; color:#eef1f3; border:1px solid #252c33}
.leaflet-popup-content{font-family:"Spline Sans",sans-serif; font-size:.84rem; line-height:1.45; margin:.7rem .9rem}
.leaflet-popup-content b{font-size:.9rem}
.leaflet-container a.leaflet-popup-close-button{color:#8b97a6}
.leaflet-bar a{background:#13181d; color:#eef1f3; border-bottom-color:#252c33}
.leaflet-bar a:hover{background:#1c232b}
.note{font-family:"IBM Plex Mono",monospace; font-size:.72rem; color:var(--muted); margin-top:.7rem}
footer{margin-top:3.6rem; padding-top:1.3rem; border-top:1px solid var(--line);
  font-family:"IBM Plex Mono",monospace; font-size:.72rem; color:var(--muted); line-height:1.7}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
.reveal{animation:rise .7s cubic-bezier(.2,.7,.2,1) both}
@media(prefers-reduced-motion:reduce){.reveal{animation:none}}
"""

# Plain JS — single braces, config concatenated by the renderer.
_JS = r"""
const YR = Object.keys(BUDGET.years).map(Number).sort((a,b)=>a-b);
const Y = a => BUDGET.years[a];
const fmt0 = v => Math.round(v).toLocaleString("pl-PL");

function plot(series, opts){
  const W=opts.w||640, H=opts.h||300, mL=46, mR=14, mT=16, mB=34;
  const xs = opts.xkeys, x0=xs[0], x1=xs[xs.length-1];
  const allv = series.flatMap(s=>s.vals.filter(v=>v!=null));
  const ymax = opts.ymax || Math.max(...allv)*1.08, ymin=0;
  const px = x => mL + (x-x0)/((x1-x0)||1)*(W-mL-mR);
  const py = v => H-mB - (v-ymin)/((ymax-ymin)||1)*(H-mT-mB);
  let g = "";
  const ticks=4;
  for(let i=0;i<=ticks;i++){ const v=ymin+(ymax-ymin)*i/ticks; const y=py(v);
    g+=`<line x1="${mL}" y1="${y.toFixed(1)}" x2="${W-mR}" y2="${y.toFixed(1)}" stroke="#1e242b"/>`;
    g+=`<text x="${mL-8}" y="${(y+4).toFixed(1)}" text-anchor="end" font-family="IBM Plex Mono" font-size="10" fill="#8b97a6">${fmt0(v)}</text>`;
  }
  xs.forEach((xx,i)=>{ if(i%2) return; const x=px(xx);
    g+=`<text x="${x.toFixed(1)}" y="${H-mB+18}" text-anchor="middle" font-family="IBM Plex Mono" font-size="10" fill="#8b97a6">${xx}</text>`; });
  series.forEach(s=>{
    const pts = xs.map((xx,i)=>[px(xx),py(s.vals[i]==null?ymin:s.vals[i])]);
    if(s.area){
      let d=`M${px(x0)},${py(ymin)}`; pts.forEach(p=>d+=` L${p[0].toFixed(1)},${p[1].toFixed(1)}`);
      d+=` L${px(x1)},${py(ymin)} Z`;
      g+=`<path d="${d}" fill="${s.color}" opacity="${s.fill||0.16}"/>`;
    }
    let d=""; pts.forEach((p,i)=>d+=`${i?'L':'M'}${p[0].toFixed(1)},${p[1].toFixed(1)} `);
    g+=`<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2.4" stroke-linejoin="round"/>`;
    const last=pts[pts.length-1];
    g+=`<circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="3.5" fill="${s.color}"/>`;
  });
  g+=`<text x="${mL-34}" y="${mT-2}" font-family="IBM Plex Mono" font-size="10" fill="#8b97a6">${opts.ylabel||""}</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img">${g}</svg>`;
}

function drawFlip(){
  const xs = YR.filter(y=>Y(y).roads_per_cap>0);
  const roads = xs.map(y=>Y(y).roads_per_cap);
  const tr = xs.map(y=>Y(y).nonroad_per_cap);
  document.getElementById("flip").innerHTML = plot([
    {vals:tr, color:"#34d399", area:true, fill:0.14},
    {vals:roads, color:"#f4a31c", area:true, fill:0.14},
  ], {xkeys:xs, ylabel:_t("axis_zl_cap")});
  const first=Y(xs[0]), last=Y(xs[xs.length-1]);
  document.getElementById("flipShareA").textContent = fmt(_t("flip_share"),{v:first.roads_share});
  document.getElementById("flipShareB").textContent = fmt(_t("flip_share"),{v:last.roads_share});
  document.getElementById("flipShareA").previousElementSibling.textContent = xs[0];
  document.getElementById("flipShareB").previousElementSibling.textContent = xs[xs.length-1];
}

function drawRun(){
  const xs = YR.filter(y=>Y(y).current_pln>0 || Y(y).capital_pln>0);
  const cur = xs.map(y=>Math.round(Y(y).current_pln/Y(y).pop));
  const cap = xs.map(y=>Math.round(Y(y).capital_pln/Y(y).pop));
  const stack = xs.map((y,i)=>cur[i]+cap[i]);
  document.getElementById("run").innerHTML = plot([
    {vals:stack, color:"#f4731c", area:true, fill:0.16},
    {vals:cur, color:"#9fb0c0", area:true, fill:0.16},
  ], {xkeys:xs, ymax:Math.max(...stack)*1.08, ylabel:_t("axis_zl_cap")});
}

// --- interactive investment map (Leaflet) ---
let _map=null, _layer=null, _mode="all";
function popupHtml(p){
  const mln=_t("pop_mln");
  let s=`<b>${p.n}</b><br>${p.yr} · ${p.tot.toLocaleString("pl-PL")} ${mln}`;
  s+=`<br>${_t("pop_city")}: ${p.city.toLocaleString("pl-PL")} ${mln}`;
  if(p.ue>0) s+=` · ${_t("pop_ue")}: ${p.ue.toLocaleString("pl-PL")} ${mln}`;
  return s;
}
function drawMarkers(){
  if(!_layer) return;
  _layer.clearLayers();
  const rec = document.getElementById("recOnly").checked;
  (INVEST.projects||[]).forEach(p=>{
    if(_mode!=="all" && p.mode!==_mode) return;
    if(rec && p.yr<2018) return;
    const col=MODE_COLOR[p.mode]||"#999";
    L.circleMarker([p.lat,p.lon], {
      radius: Math.max(4, Math.min(34, Math.sqrt(p.tot)*3.3)),
      color:col, weight:1.3, fillColor:col, fillOpacity:0.42
    }).bindPopup(popupHtml(p)).addTo(_layer);
  });
}
function initMap(){
  if(typeof L==="undefined") return;
  _map = L.map("map", {scrollWheelZoom:false}).setView([54.372,18.62], 11);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution:'© OpenStreetMap, © CARTO', subdomains:"abcd", maxZoom:18
  }).addTo(_map);
  _layer = L.layerGroup().addTo(_map);
  drawMarkers();
  document.querySelectorAll("#modeFilter button").forEach(b=>b.addEventListener("click",()=>{
    _mode=b.dataset.m;
    document.querySelectorAll("#modeFilter button").forEach(x=>x.classList.toggle("on", x===b));
    drawMarkers();
  }));
  document.getElementById("recOnly").addEventListener("change", drawMarkers);
}
function drawLegend(){
  document.getElementById("mlegend").innerHTML =
    `<span><i style="background:${MODE_COLOR.road}"></i>${_t("leg_road")}</span>`+
    `<span><i style="background:${MODE_COLOR.transit}"></i>${_t("leg_transit")}</span>`;
}

function renderCharts(){ drawFlip(); drawRun(); drawLegend(); if(_map) drawMarkers(); }
renderCharts();
initMap();
window.addEventListener("uichange", renderCharts);
"""


def _render_html(budget: dict, invest: dict) -> str:
    cfg = json.dumps(budget, ensure_ascii=False)
    inv = json.dumps(invest, ensure_ascii=False)
    colors = json.dumps(MODE_COLOR, ensure_ascii=False)
    strings = json.dumps(STRINGS, ensure_ascii=False)
    lang_bar = (
        '<div class="uibar reveal"><div class="seg" id="langSeg" role="group" aria-label="language">'
        '<button data-lang="en">EN</button><button data-lang="pl">PL</button></div></div>'
    )
    head = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gdańsk transport budget · roads vs transit</title>
{_FONTS}
{_LEAFLET}
<style>{_STYLE}{ui.SELECTOR_CSS}</style>
</head>
<body>
<div class="wrap">
<header class="reveal">
  {lang_bar}
  <p class="kicker" data-i18n="kicker">Gdańsk · public transport budget · 2004–2024</p>
  <h1 data-i18n-html="h1">Where the city's<br>mobility money goes</h1>
  <p class="dek" data-i18n="dek">Not a polemic — Gdańsk's own transport budget.</p>
  <div class="redline"></div>
  <nav class="nav">
    <a href="cost.html" data-i18n="nav_cost">Personal cost</a>
    <a href="index.html" data-i18n="nav_ledger">Public-money ledger</a>
    <a href="depreciation.html" data-i18n="nav_depr">Depreciation curves</a>
    <a href="practice.html" class="here" data-i18n="nav_practice">In practice</a>
  </nav>
</header>

<section class="reveal">
  <p class="eyebrow" data-i18n="flip_eye">The flip</p>
  <h2 data-i18n="flip_h">Roads vs transit, per resident</h2>
  <p class="lede" data-i18n="flip_lede">Road chapters enter the data in 2012.</p>
  <div class="card"><div id="flip"></div>
    <div class="legend">
      <span><i style="background:var(--road)"></i><span data-i18n="flip_roads">Roads</span></span>
      <span><i style="background:var(--transit)"></i><span data-i18n="flip_transit">Transit + rail</span></span>
      <span>· <b></b> <span id="flipShareA"></span></span>
      <span>→ <b></b> <span id="flipShareB"></span></span>
    </div>
  </div>
</section>

<section class="reveal">
  <p class="eyebrow" data-i18n="run_eye">Build vs run</p>
  <h2 data-i18n="run_h">Most of it just runs the system</h2>
  <p class="lede" data-i18n="run_lede">The same budget, split by economic type.</p>
  <div class="card"><div id="run"></div>
    <div class="legend">
      <span><i style="background:var(--cap)"></i><span data-i18n="run_capital">Capital</span></span>
      <span><i style="background:#9fb0c0"></i><span data-i18n="run_current">Current</span></span>
    </div>
  </div>
</section>

<section class="reveal">
  <p class="eyebrow" data-i18n="map_eye">On the ground</p>
  <h2 data-i18n="map_h">What the capital actually built, and where</h2>
  <p class="lede" data-i18n="map_lede">Named investments by mode.</p>
  <div class="mapctl">
    <div class="seg" id="modeFilter" role="group">
      <button data-m="all" class="on" data-i18n="f_all">All</button>
      <button data-m="road" data-i18n="f_road">Roads</button>
      <button data-m="transit" data-i18n="f_transit">Transit</button>
    </div>
    <label class="rec"><input type="checkbox" id="recOnly"> <span data-i18n="f_recent">2018+ only</span></label>
  </div>
  <div id="map"></div>
  <div class="legend" id="mlegend"></div>
  <p class="note" data-i18n="map_note">Source · Gdańska Mapa Inwestycji.</p>
</section>

<footer><div data-i18n="src">Source · GUS BDL + Gdańska Mapa Inwestycji.</div></footer>
</div>
"""
    return (
        head
        + "<script>\nconst BUDGET = " + cfg + ";\nconst INVEST = " + inv
        + ";\nconst MODE_COLOR = " + colors + ";\nwindow.T = " + strings + ";\n"
        + ui.SELECTOR_JS + "\n" + _JS + "</script>\n</body>\n</html>\n"
    )


def render_stage3(*, budget_path: str = DEFAULT_BUDGET, invest_path: str = DEFAULT_INVEST,
                  output_dir: str = "public", filename: str = "practice.html") -> str:
    with open(budget_path, encoding="utf-8") as f:
        budget = json.load(f)
    invest = {"projects": []}
    if os.path.exists(invest_path):
        with open(invest_path, encoding="utf-8") as f:
            invest = json.load(f)
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_render_html(budget, invest))
    logger.info("Rendered Stage 3 (Gdańsk transport) → %s", out_path)
    return out_path
