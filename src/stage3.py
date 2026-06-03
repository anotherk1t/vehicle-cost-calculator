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
        "dek": "Gdańsk's own transport budget, pulled from GUS public finance data. The split between road builders and transit passengers, in złoty per resident.",
        "nav_cost": "Personal cost",
        "nav_ledger": "Public-money ledger",
        "nav_depr": "Depreciation curves",
        "nav_practice": "In practice",
        "flip_eye": "The flip",
        "flip_h": "Roads vs transit, per resident",
        "flip_lede": "Road chapters enter the data in 2012. Since then the split inverted — roads slid from most of the transport budget to a quarter of it, while transit + rail climbed. Złoty per resident.",
        "flip_roads": "Roads (build + maintain)",
        "flip_transit": "Transit + rail",
        "flip_share": "roads = {v}% of transport spend",
        "run_eye": "Build vs run",
        "run_h": "Most of it just runs the system",
        "run_lede": "The same budget, split by economic type. Capital = building; current = operating + maintenance, where road repairs like Al. Rzeczypospolitej sit. Current now dwarfs capital — the city mostly runs and patches what exists.",
        "run_current": "Current (run + repair)",
        "run_capital": "Capital (build)",
        "map_eye": "On the ground",
        "map_h": "What the capital actually built, and where",
        "map_lede": "Every road and public-transit investment from the city's own investment map, dropped where it was built. Circle size = total cost; colour = roads vs transit. Click a circle for the cost and how much was city money vs EU. The road megaprojects cluster on the port/airport axis (2012–16); the tram + PKM build-out sits in the southern districts (2008–15).",
        "map_note": "Source · Gdańska Mapa Inwestycji (gdansk.pl). Circle area ∝ total cost. Drag to pan, double-click to zoom.",
        "f_all": "All",
        "f_road": "Roads",
        "f_transit": "Transit",
        "f_from": "From",
        "pop_total": "total",
        "pop_city": "city money",
        "pop_ue": "EU funds",
        "pop_mln": "mln zł",
        "leg_road": "Roads / car",
        "leg_transit": "Public transit",
        "axis_zl_cap": "zł / resident",
        "src": "Sources · GUS Bank Danych Lokalnych, dział 600 (budget series) + Gdańska Mapa Inwestycji (project locations & costs). Derived totals only — no marketplace data.",
    },
    "pl": {
        "kicker": "Gdańsk · budżet transportu · 2004–2024",
        "h1": "Dokąd płynie miejski<br>budżet na transport",
        "dek": "To nie polemika — to budżet transportowy Gdańska, odczytany z danych GUS o finansach publicznych. Kto dostaje pieniądze: budowniczowie dróg czy pasażerowie tramwajów i kolei?",
        "nav_cost": "Koszt osobisty",
        "nav_ledger": "Bilans publiczny",
        "nav_depr": "Krzywe wartości",
        "nav_practice": "W praktyce",
        "flip_eye": "Odwrócenie",
        "flip_h": "Drogi kontra transit, na mieszkańca",
        "flip_lede": "Rozdziały drogowe wchodzą do danych w 2012. Od tego czasu proporcje się odwróciły — drogi spadły z większości budżetu transportu do ćwierci, a transit + kolej wzrosły. Złote na mieszkańca.",
        "flip_roads": "Drogi (budowa + utrzymanie)",
        "flip_transit": "Transit + kolej",
        "flip_share": "drogi = {v}% wydatków na transport",
        "run_eye": "Budowa kontra utrzymanie",
        "run_h": "Większość to samo utrzymanie",
        "run_lede": "Ten sam budżet wg rodzaju. Majątkowe = budowa; bieżące = utrzymanie + eksploatacja, tu mieszczą się remonty dróg jak al. Rzeczypospolitej. Bieżące dziś znacznie przewyższają majątkowe — miasto głównie utrzymuje i łata to, co jest.",
        "run_current": "Bieżące (utrzymanie)",
        "run_capital": "Majątkowe (budowa)",
        "map_eye": "W terenie",
        "map_h": "Co i gdzie zbudowano",
        "map_lede": "Każda inwestycja drogowa i transportu zbiorowego z miejskiej mapy inwestycji, naniesiona tam, gdzie powstała. Wielkość koła = koszt całkowity; kolor = drogi czy transit. Kliknij koło, by zobaczyć koszt i ile to pieniądze miasta, a ile z UE. Drogowe megainwestycje skupiają się na osi port–lotnisko (2012–16); tramwaje i PKM — na południu (2008–15).",
        "map_note": "Źródło · Gdańska Mapa Inwestycji (gdansk.pl). Pole koła ∝ koszt. Przeciągnij, dwuklik przybliża.",
        "f_all": "Wszystko",
        "f_road": "Drogi",
        "f_transit": "Transit",
        "f_from": "Od",
        "pop_total": "całość",
        "pop_city": "pieniądze miasta",
        "pop_ue": "środki UE",
        "pop_mln": "mln zł",
        "leg_road": "Drogi / auto",
        "leg_transit": "Transport zbiorowy",
        "axis_zl_cap": "zł / mieszkańca",
        "src": "Źródła · GUS Bank Danych Lokalnych, dział 600 (szereg budżetowy) + Gdańska Mapa Inwestycji (lokalizacje i koszty). Tylko zagregowane sumy — bez danych z ogłoszeń.",
    },
}

# Same type system as the other three surfaces (Anton display + Newsreader body +
# IBM Plex Mono) so "In practice" reads as one site, not a sibling.
_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Anton&family=IBM+Plex+Mono:wght@400;500&'
    'family=Newsreader:ital,wght@0,400;0,500;1,400&display=swap" rel="stylesheet">'
)
# Leaflet files (leaflet.min.js + leaflet.min.css) are bundled in public/ and
# loaded as same-origin assets — no CDN, no SRI, no cross-origin issues.

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
  color:var(--ink); font-family:"Newsreader",Georgia,serif; font-size:17px; line-height:1.55;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1060px; margin:0 auto; padding:2rem 1.4rem 5rem}
.kicker{font-family:"IBM Plex Mono",monospace; font-size:.74rem; letter-spacing:.18em;
  text-transform:uppercase; color:var(--muted)}
h1{font-family:"Anton",Impact,sans-serif; font-weight:400; text-transform:uppercase;
  font-size:clamp(2.4rem,6.5vw,4.4rem); line-height:.92; letter-spacing:.01em; margin:.5rem 0 .8rem}
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
h2{font-family:"Anton",sans-serif; font-weight:400; text-transform:uppercase; font-size:clamp(1.5rem,3.4vw,2.1rem);
  letter-spacing:.02em; margin:.3rem 0 .5rem}
.lede{color:#bac2cb; max-width:64ch; margin:0 0 1.3rem}
.card{position:relative; background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:1.2rem 1.3rem}
.exp{position:absolute; top:.7rem; right:.7rem; z-index:3; appearance:none; cursor:pointer;
  width:30px; height:30px; border-radius:9px; border:1px solid var(--line);
  background:rgba(13,18,23,.72); color:var(--muted); font-size:1rem; line-height:1;
  display:inline-flex; align-items:center; justify-content:center; transition:.15s}
.exp:hover{color:var(--ink); border-color:var(--road); background:rgba(13,18,23,.96)}
.xhair{pointer-events:none}
.xhair line{stroke:var(--ink); stroke-opacity:.4; stroke-width:1; stroke-dasharray:4 3}
.xtip rect{fill:rgba(8,12,16,.92); stroke:var(--line); stroke-width:.5}
.xtip text{font-family:"IBM Plex Mono",monospace}
.lb{position:fixed; inset:0; z-index:60; background:rgba(6,9,12,.86); backdrop-filter:blur(5px);
  display:flex; align-items:center; justify-content:center; padding:4vmin; animation:rise .25s ease both}
.lb[hidden]{display:none}
.lb-card{position:relative; background:var(--panel); border:1px solid var(--line); border-radius:18px;
  padding:2.4rem 1.7rem 1.5rem; width:min(1120px,95vw); box-shadow:0 50px 140px -50px #000}
.lb-x{position:absolute; top:.8rem; right:.9rem; appearance:none; cursor:pointer; background:transparent;
  border:0; color:var(--muted); font-size:1.15rem; line-height:1}
.lb-x:hover{color:var(--ink)}
.lb-body svg{width:100%; height:auto}
/* Scope to our chart containers only — a bare `svg{}` rule also matches Leaflet's
   internal vector overlay pane and collapses the circle markers (tiles are <img>,
   so the basemap shows but the overlay disappears). */
#flip svg,#run svg{display:block; width:100%; height:auto; overflow:visible}
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
.mapctl .yrf{display:inline-flex; align-items:center; gap:.55rem; font-family:"IBM Plex Mono",monospace; font-size:.76rem; color:var(--muted)}
.mapctl .yrf input[type=range]{width:130px; accent-color:var(--road); cursor:pointer}
.mapctl .yrf b{min-width:2.6rem; color:var(--ink)}
#map{height:600px; border-radius:16px; border:1px solid var(--line); margin:0; background:#0f141a; z-index:0}
.leaflet-popup-content-wrapper,.leaflet-popup-tip{background:#13181d; color:#eef1f3; border:1px solid #252c33}
.leaflet-popup-content{font-family:"Newsreader",Georgia,serif; font-size:.86rem; line-height:1.45; margin:.7rem .9rem}
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
  // ylabel inside the chart area (top-left) so it never overlaps the left-margin tick values
  if(opts.ylabel) g+=`<text x="${mL+4}" y="${mT+12}" font-family="IBM Plex Mono" font-size="10" fill="#8b97a6" text-anchor="start">${opts.ylabel}</text>`;
  // transparent capture rect for hover, plus data-meta for wireHoverS
  g+=`<rect x="0" y="0" width="${W}" height="${H}" fill="transparent" pointer-events="all"/>`;
  const _ls = series.map(s=>({color:s.color,name:s.name||"",pts:xs.map((xx,j)=>[xx,s.vals[j]]).filter(p=>p[1]!=null)}));
  const _m = JSON.stringify({w:W,h:H,pad:{l:mL,r:mR,t:mT,b:mB},xmin:x0,xmax:x1,ymin,ymax,fmt:"",series:_ls}).replace(/'/g,"&#39;");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" data-meta='${_m}'>${g}</svg>`;
}

function drawFlip(){
  const xs = YR.filter(y=>Y(y).roads_per_cap>0);
  const roads = xs.map(y=>Y(y).roads_per_cap);
  const tr = xs.map(y=>Y(y).nonroad_per_cap);
  document.getElementById("flip").innerHTML = plot([
    {vals:tr, color:"#34d399", area:true, fill:0.14, name:_t("flip_transit")||"Transit"},
    {vals:roads, color:"#f4a31c", area:true, fill:0.14, name:_t("flip_roads")||"Roads"},
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
    {vals:stack, color:"#f4731c", area:true, fill:0.16, name:"Total"},
    {vals:cur, color:"#9fb0c0", area:true, fill:0.16, name:_t("run_current")||"Current"},
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
  const sl = document.getElementById("yrSlider");
  const yrFrom = sl ? +sl.value : 0;
  (INVEST.projects||[]).forEach(p=>{
    if(_mode!=="all" && p.mode!==_mode) return;
    if(p.yr < yrFrom) return;
    const col=MODE_COLOR[p.mode]||"#999";
    L.circleMarker([p.lat,p.lon], {
      radius: Math.max(4, Math.min(34, Math.sqrt(p.tot)*3.3)),
      color:col, weight:1.3, fillColor:col, fillOpacity:0.42
    }).bindPopup(popupHtml(p)).addTo(_layer);
  });
}
let _leafletLoaded = false;
function initMap(){
  const mapDiv = document.getElementById("map");
  if(!mapDiv) return;
  if(_leafletLoaded){ _startMap(); return; }
  const js = document.createElement("script");
  js.src = "/leaflet.min.js";
  js.onerror = () => { mapDiv.innerHTML = '<p style="color:var(--muted);padding:2rem;font-family:IBM Plex Mono,monospace;font-size:.8rem">Map script failed to load.</p>'; };
  js.onload = () => { _leafletLoaded = true; _startMap(); };
  document.head.appendChild(js);
}
function _startMap(){
  _map = L.map("map", {scrollWheelZoom:false}).setView([54.372,18.62], 11);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution:'© OpenStreetMap, © CARTO', subdomains:"abcd", maxZoom:18
  }).addTo(_map);
  _layer = L.layerGroup().addTo(_map);
  const yrs = (INVEST.projects||[]).map(p=>p.yr).filter(Boolean);
  if(yrs.length){
    const ymin=Math.min(...yrs), ymax=Math.max(...yrs);
    const sl=document.getElementById("yrSlider");
    sl.min=ymin; sl.max=ymax; sl.value=ymin;
    document.getElementById("yrVal").textContent=ymin;
  }
  drawMarkers();
  document.querySelectorAll("#modeFilter button").forEach(b=>b.addEventListener("click",()=>{
    _mode=b.dataset.m;
    document.querySelectorAll("#modeFilter button").forEach(x=>x.classList.toggle("on", x===b));
    drawMarkers();
  }));
  document.getElementById("yrSlider").addEventListener("input", e=>{
    document.getElementById("yrVal").textContent=e.target.value;
    drawMarkers();
  });
}
function drawLegend(){
  document.getElementById("mlegend").innerHTML =
    `<span><i style="background:${MODE_COLOR.road}"></i>${_t("leg_road")}</span>`+
    `<span><i style="background:${MODE_COLOR.transit}"></i>${_t("leg_transit")}</span>`;
}

function renderCharts(){ drawFlip(); drawRun(); drawLegend(); if(_map) drawMarkers(); enhanceChartsS(); }
renderCharts();
initMap();
window.addEventListener("uichange", renderCharts);

// --- hover crosshair + expand-to-lightbox for the two budget charts ---
const _NSS = "http://www.w3.org/2000/svg";
function _valAtS(pts, x){
  if(!pts.length) return null;
  if(x<=pts[0][0]) return pts[0][1];
  if(x>=pts[pts.length-1][0]) return pts[pts.length-1][1];
  for(let i=0;i<pts.length-1;i++){
    const a=pts[i], b=pts[i+1];
    if(x>=a[0] && x<=b[0]) return a[1]+(b[1]-a[1])*((x-a[0])/((b[0]-a[0])||1));
  }
  return null;
}
function wireHoverS(svg){
  if(svg.__wired) return; svg.__wired=true;
  const m=JSON.parse(svg.getAttribute("data-meta"));
  const {w,h,pad,xmin,xmax,ymin,ymax,series}=m;
  const X=x=>pad.l+(x-xmin)/((xmax-xmin)||1)*(w-pad.l-pad.r);
  const Y=y=>h-pad.b-(y-ymin)/((ymax-ymin)||1)*(h-pad.t-pad.b);
  const g=document.createElementNS(_NSS,"g"); g.setAttribute("class","xhair"); g.style.display="none";
  const vl=document.createElementNS(_NSS,"line"); g.appendChild(vl);
  const dots=document.createElementNS(_NSS,"g"); g.appendChild(dots);
  const tip=document.createElementNS(_NSS,"g"); tip.setAttribute("class","xtip");
  const tr=document.createElementNS(_NSS,"rect"); tr.setAttribute("rx","5"); tip.appendChild(tr);
  const tt=document.createElementNS(_NSS,"text"); tip.appendChild(tt);
  g.appendChild(tip); svg.appendChild(g);
  function move(e){
    const r=svg.getBoundingClientRect(); if(!r.width) return;
    const vbx=(e.clientX-r.left)/r.width*w;
    let xv=Math.round((vbx-pad.l)/((w-pad.l-pad.r)||1)*(xmax-xmin)+xmin);
    xv=Math.max(xmin,Math.min(xmax,xv));
    const cx=X(xv);
    g.style.display="";
    vl.setAttribute("x1",cx); vl.setAttribute("x2",cx);
    vl.setAttribute("y1",pad.t); vl.setAttribute("y2",h-pad.b);
    while(dots.firstChild) dots.removeChild(dots.firstChild);
    while(tt.firstChild) tt.removeChild(tt.firstChild);
    const lines=[{t:xv.toString(),c:"#eef1f3"}]; let maxlen=4;
    series.forEach(s=>{
      const v=_valAtS(s.pts,xv); if(v==null) return;
      const d=document.createElementNS(_NSS,"circle");
      d.setAttribute("cx",cx); d.setAttribute("cy",Y(v)); d.setAttribute("r","3.4");
      d.setAttribute("fill",s.color); d.setAttribute("stroke","#0c0f12"); d.setAttribute("stroke-width","1");
      dots.appendChild(d);
      const t=(s.name?s.name+"  ":"")+Math.round(v).toLocaleString("pl-PL");
      lines.push({t,c:s.color}); maxlen=Math.max(maxlen,t.length);
    });
    const lh=15,px2=9,py2=7;
    lines.forEach((ln,i)=>{
      const ts=document.createElementNS(_NSS,"tspan");
      ts.setAttribute("x",px2); ts.setAttribute("dy",i?lh:0);
      ts.setAttribute("fill",ln.c); ts.setAttribute("font-size","11");
      ts.textContent=ln.t; tt.appendChild(ts);
    });
    const tw=maxlen*6.7+px2*2,th=lines.length*lh+py2*2;
    let tx=cx+12; if(tx+tw>w-pad.r) tx=cx-12-tw; if(tx<pad.l) tx=pad.l;
    tip.setAttribute("transform","translate("+tx+","+(pad.t+6)+")");
    tr.setAttribute("width",tw); tr.setAttribute("height",th);
    tt.setAttribute("y",py2+11);
  }
  svg.addEventListener("mousemove",move);
  svg.addEventListener("mouseleave",()=>{ g.style.display="none"; });
}
let _lbS;
function openLBS(svg){
  if(!_lbS){
    _lbS=document.createElement("div"); _lbS.className="lb"; _lbS.hidden=true;
    _lbS.innerHTML='<div class="lb-card"><button class="lb-x" aria-label="close">&#10005;</button><div class="lb-body"></div></div>';
    document.body.appendChild(_lbS);
    _lbS.addEventListener("click",e=>{ if(e.target===_lbS||e.target.closest(".lb-x")) _lbS.hidden=true; });
    document.addEventListener("keydown",e=>{ if(e.key==="Escape") _lbS.hidden=true; });
  }
  const body=_lbS.querySelector(".lb-body"); body.innerHTML="";
  const clone=svg.cloneNode(true);
  clone.querySelectorAll(".xhair").forEach(n=>n.remove());
  clone.__wired=false;
  body.appendChild(clone); wireHoverS(clone);
  _lbS.hidden=false;
}
function addExpandS(card){
  if(card.__exp) return;
  if(!card.querySelector("svg[data-meta]")) return;
  card.__exp=true;
  const b=document.createElement("button");
  b.className="exp"; b.type="button"; b.title="Expand"; b.innerHTML="&#10530;";
  b.addEventListener("click",()=>{ const svg=card.querySelector("svg[data-meta]"); if(svg) openLBS(svg); });
  card.appendChild(b);
}
function enhanceChartsS(){
  document.querySelectorAll("svg[data-meta]").forEach(wireHoverS);
  document.querySelectorAll(".card").forEach(addExpandS);
}
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
<link rel="stylesheet" href="/leaflet.min.css">
<style>{_STYLE}{ui.SELECTOR_CSS}</style>
</head>
<body>
<div class="wrap">
<header class="reveal">
  {lang_bar}
  <p class="kicker" data-i18n="kicker">Gdańsk · public transport budget · 2004–2024</p>
  <h1 data-i18n-html="h1">Where the city's<br>mobility money goes</h1>
  <p class="dek" data-i18n="dek">Gdańsk's own transport budget, pulled from GUS public finance data.</p>
  <div class="redline"></div>
  <nav class="nav">
    <a href="index.html" data-i18n="nav_cost">Personal cost</a>
    <a href="ledger.html" data-i18n="nav_ledger">Public-money ledger</a>
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
    <div class="yrf">
      <span data-i18n="f_from">From</span>
      <input type="range" id="yrSlider" min="2000" max="2023" step="1" value="2000">
      <b id="yrVal">2000</b>
    </div>
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
        + "<script>\nconst BUDGET = "
        + cfg
        + ";\nconst INVEST = "
        + inv
        + ";\nconst MODE_COLOR = "
        + colors
        + ";\nwindow.T = "
        + strings
        + ";\n"
        + ui.SELECTOR_JS
        + "\n"
        + _JS
        + "</script>\n</body>\n</html>\n"
    )


def render_stage3(
    *,
    budget_path: str = DEFAULT_BUDGET,
    invest_path: str = DEFAULT_INVEST,
    output_dir: str = "public",
    filename: str = "practice.html",
) -> str:
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
