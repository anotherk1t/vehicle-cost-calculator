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
    it doesn't expand it. That answers "are repairs in the data?" — emphatically yes.

A schematic map pins the named investments (Trasa Słowackiego, the Martwa Wisła
tunnel, PKM, the southern trams, the cycle network) by mode so you can see what the
capital half actually bought.

Like the other surfaces this is a static, self-contained page: Python embeds the
BDL series (data/stage3_gdansk_transport.json, derived totals only) plus a curated
projects list, and vanilla JS draws every chart as hand-rolled SVG. No CDN, no deps.
"""

from __future__ import annotations

import json
import logging
import os

from src import ui

logger = logging.getLogger(__name__)

DEFAULT_BUDGET = os.path.join("data", "stage3_gdansk_transport.json")

# Curated marquee investments. Costs are reported headline figures (rounded, mln
# zł); many are EU/state co-funded so they are NOT all city money — the page says
# so. `cost` is None where a clean figure isn't public (shown as "—"). x/y are
# schematic positions in a 0–100 box (x = west→east, y = coast→south), not survey
# coordinates. mode drives the colour + the legend.
PROJECTS = [
    {"key": "tunnel", "mode": "tunnel", "year": 2016, "cost": 885, "x": 80, "y": 24,
     "name": "Tunnel under the Martwa Wisła", "name_pl": "Tunel pod Martwą Wisłą",
     "blurb": "The marquee road project — stage IV of Trasa Słowackiego, mostly EU-funded.",
     "blurb_pl": "Sztandarowa inwestycja drogowa — IV etap Trasy Słowackiego, w większości z UE."},
    {"key": "slowackiego", "mode": "road", "year": 2016, "cost": 1400, "x": 47, "y": 31,
     "name": "Trasa Słowackiego", "name_pl": "Trasa Słowackiego",
     "blurb": "Cross-city road corridor, airport → port, built in four stages.",
     "blurb_pl": "Drogowy korytarz przez miasto, lotnisko → port, w czterech etapach."},
    {"key": "pkm1", "mode": "rail", "year": 2015, "cost": 1100, "x": 28, "y": 39,
     "name": "PKM (stage I)", "name_pl": "PKM (etap I)",
     "blurb": "Pomorska Kolej Metropolitalna — new commuter rail, Wrzeszcz → airport → Kashubia.",
     "blurb_pl": "Pomorska Kolej Metropolitalna — nowa kolej, Wrzeszcz → lotnisko → Kaszuby."},
    {"key": "pkms", "mode": "rail", "year": 2027, "cost": 221, "x": 53, "y": 83,
     "name": "PKM Południe (planned)", "name_pl": "PKM Południe (plan.)",
     "blurb": "Southern rail spur; Gdańsk's share ~221 mln of a ~2.3 bn programme.",
     "blurb_pl": "Południowa odnoga kolei; udział Gdańska ~221 mln z ~2,3 mld."},
    {"key": "bulonska", "mode": "tram", "year": 2019, "cost": None, "x": 46, "y": 66,
     "name": "Nowa Bulońska tram", "name_pl": "Tramwaj Nowa Bulońska",
     "blurb": "Tram extension into the dense southern districts (Jasień / Morena).",
     "blurb_pl": "Tramwaj w gęste dzielnice południa (Jasień / Morena)."},
    {"key": "gpw", "mode": "tram", "year": 2026, "cost": None, "x": 51, "y": 75,
     "name": "GPW tram (building)", "name_pl": "Tramwaj GPW (w budowie)",
     "blurb": "Gdańsk Południe ↔ Wrzeszcz tram, knitting the southern districts to the centre.",
     "blurb_pl": "Tramwaj Gdańsk Południe ↔ Wrzeszcz, spinający południe z centrum."},
    {"key": "bike", "mode": "bike", "year": 2016, "cost": 35, "x": 38, "y": 52,
     "name": "Cycle network (EU)", "name_pl": "Sieć rowerowa (UE)",
     "blurb": "EU-funded cycle routes; the city now counts ~883 km of paths.",
     "blurb_pl": "Trasy rowerowe z UE; miasto liczy dziś ~883 km dróg rowerowych."},
    {"key": "forum", "mode": "hub", "year": 2018, "cost": None, "x": 66, "y": 41,
     "name": "Forum Gdańsk hub", "name_pl": "Węzeł Forum Gdańsk",
     "blurb": "Multimodal interchange stitched over the main railway cut.",
     "blurb_pl": "Węzeł przesiadkowy nad wykopem kolejowym."},
    {"key": "siennicki", "mode": "bridge", "year": 2022, "cost": None, "x": 73, "y": 49,
     "name": "Most Siennicki", "name_pl": "Most Siennicki",
     "blurb": "Reconstruction of the historic bascule bridge over the Motława.",
     "blurb_pl": "Przebudowa zabytkowego mostu zwodzonego nad Motławą."},
    {"key": "rzeczy", "mode": "maintenance", "year": 2024, "cost": None, "x": 57, "y": 16,
     "name": "Al. Rzeczypospolitej repaving", "name_pl": "Remont al. Rzeczypospolitej",
     "blurb": "Routine repaving in Przymorze — the 'current' bucket, not an expansion.",
     "blurb_pl": "Bieżący remont w Przymorzu — koszt utrzymania, nie rozbudowa."},
]

MODE_COLOR = {
    "road": "#f4a31c", "tunnel": "#f4731c", "bridge": "#f4731c",
    "rail": "#3aa0ff", "tram": "#34d399", "bike": "#f062c0",
    "hub": "#b08cff", "maintenance": "#8b97a6",
}

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
        "map_eye": "On the ground", "map_h": "What the capital half bought",
        "map_lede": "Named investments by mode. Costs are reported headline figures (rounded, mln zł) — several are EU- or state-co-funded, so not all of it is city money. Positions are schematic.",
        "map_note": "Schematic — positions approximate, not to scale.",
        "axis_zl_cap": "zł / resident", "year": "year", "reported": "reported", "planned": "planned",
        "src": "Source · GUS Bank Danych Lokalnych, dział 600 (Transport i łączność), Gdańsk. Transit + rail = dział-600 total minus all road chapters (≈ ZTM bus/tram + SKM/PKM + misc). Derived totals only.",
        "modes": {"road": "Road", "tunnel": "Tunnel", "bridge": "Bridge", "rail": "Rail",
                  "tram": "Tram", "bike": "Cycle", "hub": "Interchange", "maintenance": "Maintenance"},
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
        "map_eye": "W terenie", "map_h": "Co kupiła część inwestycyjna",
        "map_lede": "Nazwane inwestycje wg środka transportu. Koszty to podawane kwoty (zaokrąglone, mln zł) — część współfinansowana z UE lub budżetu państwa, więc nie wszystko to pieniądze miasta. Pozycje schematyczne.",
        "map_note": "Schemat — pozycje przybliżone, nie w skali.",
        "axis_zl_cap": "zł / mieszkańca", "year": "rok", "reported": "podano", "planned": "plan.",
        "src": "Źródło · GUS Bank Danych Lokalnych, dział 600 (Transport i łączność), Gdańsk. Transit + kolej = suma działu 600 minus rozdziały drogowe (≈ ZTM autobus/tramwaj + SKM/PKM + inne). Tylko zagregowane sumy.",
        "modes": {"road": "Droga", "tunnel": "Tunel", "bridge": "Most", "rail": "Kolej",
                  "tram": "Tramwaj", "bike": "Rower", "hub": "Węzeł", "maintenance": "Utrzymanie"},
    },
}

_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Spline+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">'
)

_STYLE = """
:root{
  --bg:#0c0f12; --panel:#13181d; --line:#252c33; --ink:#eef1f3; --muted:#8b97a6;
  --road:#f4a31c; --transit:#34d399; --rail:#3aa0ff; --cap:#f4731c;
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
.legend i{display:inline-block; width:11px; height:11px; border-radius:3px; margin-right:.4rem; vertical-align:-1px}
.grid{display:grid; grid-template-columns:1.25fr .9fr; gap:1.2rem}
@media(max-width:760px){.grid{grid-template-columns:1fr}}
.plist{display:flex; flex-direction:column; gap:.5rem; max-height:520px; overflow:auto; padding-right:.3rem}
.pitem{display:grid; grid-template-columns:auto 1fr auto; gap:.7rem; align-items:baseline;
  padding:.6rem .2rem; border-bottom:1px solid var(--line)}
.pitem .dot{width:10px; height:10px; border-radius:50%; align-self:center}
.pitem .nm{font-weight:600; font-size:.92rem}
.pitem .bl{grid-column:2; color:var(--muted); font-size:.8rem; margin-top:.15rem}
.pitem .meta{font-family:"IBM Plex Mono",monospace; font-size:.78rem; color:var(--muted); white-space:nowrap}
.pitem .cost{color:var(--ink)}
.pin{cursor:pointer; transition:.15s} .pin:hover{filter:brightness(1.25)}
.maphint{font-family:"IBM Plex Mono",monospace; font-size:.7rem; fill:var(--muted)}
.note{font-family:"IBM Plex Mono",monospace; font-size:.72rem; color:var(--muted); margin-top:.6rem}
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
const mlnLabel = p => p.cost==null ? "—" : (p.cost>=1000 ? (p.cost/1000).toFixed(p.cost%1000?1:0)+" bn" : p.cost+" mln");

// generic line/area plotter into an SVG string
function plot(series, opts){
  const W=opts.w||640, H=opts.h||300, mL=46, mR=14, mT=16, mB=34;
  const xs = opts.xkeys, x0=xs[0], x1=xs[xs.length-1];
  const allv = series.flatMap(s=>s.vals.filter(v=>v!=null));
  const ymax = opts.ymax || Math.max(...allv)*1.08, ymin=0;
  const px = x => mL + (x-x0)/((x1-x0)||1)*(W-mL-mR);
  const py = v => H-mB - (v-ymin)/((ymax-ymin)||1)*(H-mT-mB);
  let g = "";
  // y gridlines
  const ticks=4;
  for(let i=0;i<=ticks;i++){ const v=ymin+(ymax-ymin)*i/ticks; const y=py(v);
    g+=`<line x1="${mL}" y1="${y.toFixed(1)}" x2="${W-mR}" y2="${y.toFixed(1)}" stroke="#1e242b"/>`;
    g+=`<text x="${mL-8}" y="${(y+4).toFixed(1)}" text-anchor="end" font-family="IBM Plex Mono" font-size="10" fill="#8b97a6">${fmt0(v)}</text>`;
  }
  // x labels (every other year)
  xs.forEach((xx,i)=>{ if(i%2) return; const x=px(xx);
    g+=`<text x="${x.toFixed(1)}" y="${H-mB+18}" text-anchor="middle" font-family="IBM Plex Mono" font-size="10" fill="#8b97a6">${xx}</text>`; });
  // series
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
  const xs = YR.filter(y=>Y(y).roads_per_cap>0);   // 2012+
  const roads = xs.map(y=>Y(y).roads_per_cap);
  const tr = xs.map(y=>Y(y).nonroad_per_cap);
  const svg = plot([
    {vals:tr, color:"#34d399", area:true, fill:0.14},
    {vals:roads, color:"#f4a31c", area:true, fill:0.14},
  ], {xkeys:xs, ylabel:_t("axis_zl_cap")});
  document.getElementById("flip").innerHTML = svg;
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
  // stacked: capital on top of current
  const stack = xs.map((y,i)=>cur[i]+cap[i]);
  const ymax=Math.max(...stack)*1.08;
  const svg = plot([
    {vals:stack, color:"#f4731c", area:true, fill:0.16},
    {vals:cur, color:"#9fb0c0", area:true, fill:0.16},
  ], {xkeys:xs, ymax, ylabel:_t("axis_zl_cap")});
  document.getElementById("run").innerHTML = svg;
}

function drawMap(){
  const W=560,H=460;
  let g="";
  // bay (top-right arc) + water tint
  g+=`<path d="M${W},0 L${W},${H} L${W*0.62},${H} Q${W*0.74},${H*0.5} ${W*0.9},${H*0.28} Q${W},${H*0.16} ${W},0 Z" fill="#0f1a24"/>`;
  g+=`<text x="${W*0.86}" y="${H*0.2}" class="maphint" text-anchor="middle">Zatoka Gdańska</text>`;
  // motlawa hint
  g+=`<path d="M${W*0.7},${H*0.3} C${W*0.66},${H*0.5} ${W*0.7},${H*0.68} ${W*0.66},${H*0.86}" stroke="#19384d" stroke-width="6" fill="none" opacity="0.7"/>`;
  // district hints
  [["Wrzeszcz",0.42,0.33],["Śródmieście",0.6,0.55],["Przymorze",0.5,0.14],["Południe",0.5,0.8],["lotnisko",0.12,0.46]].forEach(d=>{
    g+=`<text x="${(d[1]*W).toFixed(0)}" y="${(d[2]*H).toFixed(0)}" class="maphint" text-anchor="middle" opacity="0.55">${d[0]}</text>`;
  });
  // pins
  const rad = c => c==null ? 7 : Math.max(7, Math.min(26, Math.sqrt(c)*0.65));
  PROJECTS.forEach(p=>{
    const cx=p.x/100*W, cy=p.y/100*H, col=MODE_COLOR[p.mode]||"#999";
    g+=`<circle class="pin" cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${rad(p.cost).toFixed(1)}" fill="${col}" fill-opacity="0.22" stroke="${col}" stroke-width="1.6" data-k="${p.key}"><title></title></circle>`;
    g+=`<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="2.5" fill="${col}"/>`;
  });
  document.getElementById("map").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img">${g}</svg>`;
}

function renderProjects(){
  const lang = UI.lang;
  const rep=_t("reported"), pl=_t("planned"), modes=(window.T[lang]||{}).modes||{};
  document.getElementById("plist").innerHTML = PROJECTS.map(p=>{
    const col=MODE_COLOR[p.mode]||"#999";
    const nm = lang==="pl"? p.name_pl : p.name;
    const bl = lang==="pl"? p.blurb_pl : p.blurb;
    const cost = p.cost==null ? "—" : `${mlnLabel(p)} zł`;
    const yr = p.year>=2026 ? `${p.year} · ${pl}` : `${p.year}`;
    return `<div class="pitem"><span class="dot" style="background:${col}"></span>`+
      `<span class="nm">${nm}</span>`+
      `<span class="meta">${yr}<br><span class="cost">${cost}</span></span>`+
      `<span class="bl">${bl} · ${modes[p.mode]||p.mode}</span></div>`;
  }).join("");
  // map tooltips
  document.querySelectorAll("#map .pin title").forEach((t,i)=>{});
  document.querySelectorAll("#map .pin").forEach(c=>{
    const p=PROJECTS.find(x=>x.key===c.dataset.k); if(!p) return;
    const nm = lang==="pl"? p.name_pl : p.name;
    c.querySelector("title").textContent = `${nm} — ${p.cost==null?"—":mlnLabel(p)+" zł"} (${p.year})`;
  });
  // legend
  const order=["road","tunnel","rail","tram","bike","hub","maintenance"];
  document.getElementById("mlegend").innerHTML = order.map(m=>
    `<span><i style="background:${MODE_COLOR[m]}"></i>${modes[m]||m}</span>`).join("");
}

function renderAll(){ drawFlip(); drawRun(); drawMap(); renderProjects(); }
renderAll();
window.addEventListener("uichange", renderAll);
"""


def _render_html(budget: dict) -> str:
    cfg = json.dumps(budget, ensure_ascii=False)
    proj = json.dumps(PROJECTS, ensure_ascii=False)
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
  <h2 data-i18n="map_h">What the capital half bought</h2>
  <p class="lede" data-i18n="map_lede">Named investments by mode.</p>
  <div class="grid">
    <div class="card"><div id="map"></div>
      <div class="legend" id="mlegend"></div>
      <p class="note" data-i18n="map_note">Schematic — positions approximate.</p>
    </div>
    <div class="plist" id="plist"></div>
  </div>
</section>

<footer><div data-i18n="src">Source · GUS BDL.</div></footer>
</div>
"""
    return (
        head
        + "<script>\nconst BUDGET = " + cfg + ";\nconst PROJECTS = " + proj
        + ";\nconst MODE_COLOR = " + colors + ";\nwindow.T = " + strings + ";\n"
        + ui.SELECTOR_JS + "\n" + _JS + "</script>\n</body>\n</html>\n"
    )


def render_stage3(*, budget_path: str = DEFAULT_BUDGET, output_dir: str = "public",
                  filename: str = "practice.html") -> str:
    with open(budget_path, encoding="utf-8") as f:
        budget = json.load(f)
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_render_html(budget))
    logger.info("Rendered Stage 3 (Gdańsk transport) → %s", out_path)
    return out_path
