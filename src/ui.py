"""Shared top-bar selectors: language (EN/PL) + vehicle (Moto/Car).

State lives in localStorage (`ui_lang`, `ui_veh`) so it carries across pages. On
change the bar applies translations to `[data-i18n]` / `[data-i18n-html]` elements
(strings come from a page-defined global `window.T = {en:{…}, pl:{…}}`) and fires a
`uichange` CustomEvent so each page can re-render its data for the chosen
language + vehicle.
"""

from __future__ import annotations

LANGS = ("en", "pl")
VEHICLES = ("moto", "car")


def selector_bar() -> str:
    return """
<div class="uibar reveal">
  <div class="seg" id="vehSeg" role="group" aria-label="vehicle">
    <button data-veh="moto">🏍 <span data-i18n="veh_moto">Moto</span></button><button data-veh="car">🚗 <span data-i18n="veh_car">Car</span></button>
  </div>
  <div class="seg" id="langSeg" role="group" aria-label="language">
    <button data-lang="en">EN</button><button data-lang="pl">PL</button>
  </div>
</div>
"""


SELECTOR_CSS = """
.uibar{display:flex; gap:.6rem; justify-content:flex-end; flex-wrap:wrap; margin:0 0 -.4rem; padding-top:1.1rem}
.seg{display:inline-flex; border:1px solid var(--line); border-radius:999px; overflow:hidden;
  background:var(--panel); font-family:"IBM Plex Mono",monospace}
.seg button{appearance:none; border:0; background:transparent; color:var(--muted); cursor:pointer;
  font:inherit; font-size:.74rem; padding:.4rem .8rem; letter-spacing:.04em; transition:.15s}
.seg button:hover{color:var(--ink)}
.seg button[aria-pressed="true"]{background:var(--ink); color:#0b0b0f}
"""


# Plain JS, no f-string. `window.T` (per page) supplies translations.
SELECTOR_JS = r"""
const UI = { lang: localStorage.getItem("ui_lang") || "en", veh: localStorage.getItem("ui_veh") || "moto" };
function _t(key){ return (window.T && T[UI.lang] && T[UI.lang][key]); }
function fmt(t, v){ return (t || "").replace(/\{(\w+)\}/g, (_, k) => (v[k] != null ? v[k] : "")); }
function applyLang(){
  document.querySelectorAll("[data-i18n]").forEach(el => { const t=_t(el.dataset.i18n); if(t!=null) el.textContent=t; });
  document.querySelectorAll("[data-i18n-html]").forEach(el => { const t=_t(el.dataset.i18nHtml); if(t!=null) el.innerHTML=t; });
  document.documentElement.lang = UI.lang;
}
function _sync(){
  document.querySelectorAll("#langSeg button").forEach(b => b.setAttribute("aria-pressed", b.dataset.lang===UI.lang));
  document.querySelectorAll("#vehSeg button").forEach(b => b.setAttribute("aria-pressed", b.dataset.veh===UI.veh));
}
document.addEventListener("click", e => {
  const L = e.target.closest("#langSeg button"), V = e.target.closest("#vehSeg button");
  if(L){ UI.lang=L.dataset.lang; localStorage.setItem("ui_lang",UI.lang); _sync(); applyLang(); window.dispatchEvent(new CustomEvent("uichange")); }
  if(V){ UI.veh=V.dataset.veh; localStorage.setItem("ui_veh",UI.veh); _sync(); window.dispatchEvent(new CustomEvent("uichange")); }
});
_sync(); applyLang();
"""
