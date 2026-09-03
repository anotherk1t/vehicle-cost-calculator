"""Shared shell for the one shipped ownership-cost page."""

from __future__ import annotations

import html
from pathlib import Path

FONT = 'ui-monospace, "SF Mono", Menlo, Consolas, monospace'
DARK_TOKENS = {
    "bg": "#111110",
    "ink": "#f0efe9",
    "body": "#b8b7b0",
    "muted": "#9a9a93",
    "rule": "#2d2d29",
    "accent": "#6fc3ca",
    "data": "#79aeb2",
    "input": "#1b1b19",
    "selection": "#363630",
    "control_border": "#74746d",
    "control_selected": "#292925",
}
LIGHT_TOKENS = {
    "bg": "#faf9f6",
    "ink": "#181815",
    "body": "#494943",
    "muted": "#62625c",
    "rule": "#e1dfd7",
    "accent": "#1f6570",
    "data": "#3f747b",
    "input": "#f3f1eb",
    "selection": "#e6e3db",
    "control_border": "#77766f",
    "control_selected": "#e4e1d8",
}


def _vars(values):
    return "".join(f"--{key}:{value};" for key, value in values.items())


# Approved "plain portfolio A" visual contract.
BASE_CSS = f"""
*{{box-sizing:border-box}}:root{{color-scheme:light dark;{_vars(DARK_TOKENS)}}}@media(prefers-color-scheme:light){{:root{{{_vars(LIGHT_TOKENS)}}}}}
html{{scrollbar-width:none}}html::-webkit-scrollbar{{display:none}}body{{margin:0;min-height:100vh;background:var(--bg);color:var(--body);font:16px/1.65 {FONT};-webkit-font-smoothing:antialiased}}::selection{{background:var(--selection);color:var(--ink)}}a{{color:inherit}}a:hover,a:focus-visible{{color:var(--ink)}}button,input,select{{font:inherit}}button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible,summary:focus-visible{{outline:2px solid var(--accent);outline-offset:3px}}
.page{{width:100%;max-width:840px;margin:0 auto;padding:60px 40px 90px}}.skip{{position:absolute;top:-80px;left:12px;padding:7px 10px;background:var(--ink);color:var(--bg);font-size:12px;z-index:2}}.skip:focus{{top:12px}}.top{{display:flex;justify-content:space-between;align-items:baseline;gap:24px;margin-bottom:60px}}.top h1{{margin:0;color:var(--ink);font-size:22px;font-weight:600;letter-spacing:-.03em}}.top nav{{font-size:13px;color:var(--muted)}}.top nav button{{border:0;background:none;padding:0;color:inherit;cursor:pointer}}.top nav button[aria-pressed=true]{{color:var(--ink)}}.top nav button+button:before{{content:" / ";color:var(--rule);margin:0 5px}}
.intro{{max-width:680px;margin:0 0 54px;line-height:1.8}}.section{{margin-top:50px}}.section:first-of-type{{margin-top:0}}.section-title{{margin:0 0 18px;color:var(--muted);font-size:13px;font-weight:400;letter-spacing:.1em}}.section-title:before{{content:"# ";color:var(--accent)}}.calculator{{display:grid;grid-template-columns:270px 1fr;gap:66px;border-top:1px solid var(--rule);padding-top:24px}}.form,.result{{min-width:0}}.field{{padding:0;margin:0 0 22px;border:0}}.field label,.field legend,.kind-label{{display:block;margin:0 0 7px;padding:0;color:var(--muted);font-size:12px;line-height:1.4}}.field select,.field input[type=number],.field input[type=search]{{width:100%;min-height:42px;padding:9px 38px 9px 12px;border:1px solid var(--control_border);border-radius:8px;background:var(--input);color:var(--ink)}}.field input[type=number],.field input[type=search]{{padding-right:12px}}.field input[type=number]{{appearance:textfield}}.field input[type=number]::-webkit-inner-spin-button,.field input[type=number]::-webkit-outer-spin-button{{appearance:none}}.select-control{{position:relative;display:block}}.select-control:after{{content:"";position:absolute;right:14px;top:50%;width:7px;height:7px;border-right:1px solid var(--muted);border-bottom:1px solid var(--muted);transform:translateY(-70%) rotate(45deg);pointer-events:none}}.select-control select{{appearance:none;background-image:none}}.hint{{display:block;margin-top:6px;color:var(--muted);font-size:12px;line-height:1.5}}
.kind-options,.purchase-options{{display:grid;grid-template-columns:1fr 1fr;gap:3px;padding:3px;border:1px solid var(--control_border);border-radius:10px;background:var(--input)}}.kind-options button,.purchase-options button{{min-height:36px;border:0;border-radius:7px;background:transparent;color:var(--muted);font:13px {FONT};cursor:pointer}}.kind-options button[aria-pressed=true],.purchase-options button[aria-pressed=true]{{background:var(--control_selected);color:var(--ink);box-shadow:inset 0 0 0 1px var(--accent)}}
.range-line{{display:flex;align-items:baseline;justify-content:space-between;gap:10px}}.range-line input.exact{{width:112px;min-height:36px;flex:0 0 112px;padding:6px 9px;color:var(--ink);font-size:18px;font-weight:600;font-variant-numeric:tabular-nums}}.range-line span{{color:var(--muted);font-size:12px;white-space:nowrap}}input[type=range]{{display:block;width:100%;height:20px;margin:10px 0 0;appearance:none;background:transparent;cursor:pointer}}input[type=range]::-webkit-slider-runnable-track{{height:5px;border-radius:999px;background:var(--control_border)}}input[type=range]::-webkit-slider-thumb{{width:17px;height:17px;margin-top:-6px;border:0;border-radius:50%;appearance:none;background:var(--accent)}}input[type=range]::-moz-range-track{{height:5px;border-radius:999px;background:var(--control_border)}}input[type=range]::-moz-range-progress{{height:5px;border-radius:999px;background:var(--accent)}}input[type=range]::-moz-range-thumb{{width:17px;height:17px;border:0;border-radius:50%;background:var(--accent)}}
.model-picker{{position:relative}}.profile-results{{position:absolute;z-index:5;top:calc(100% + 3px);left:0;right:0;max-height:286px;overflow:auto;scrollbar-width:none;border:1px solid var(--control_border);border-radius:10px;background:var(--bg);box-shadow:0 10px 24px rgb(0 0 0/.22)}}.profile-results::-webkit-scrollbar{{display:none}}.profile-option{{display:grid;grid-template-columns:1fr auto;gap:10px;padding:9px 11px;border-bottom:1px solid var(--rule);color:var(--body);font-size:12px;cursor:pointer}}.profile-option:last-child{{border-bottom:0}}.profile-option small{{color:var(--muted);font-size:10px}}.profile-option[aria-selected=true],.profile-option:hover{{background:var(--control_selected);color:var(--ink)}}.profile-empty,.profile-more{{padding:11px;color:var(--muted);font-size:11px}}.profile-more{{border-top:1px solid var(--rule)}}.model-meta{{margin:7px 0 0;color:var(--muted);font-size:11px;line-height:1.55}}.model-meta strong{{color:var(--body);font-weight:400}}.model-warning,.model-note{{display:block;margin-top:6px;padding-left:9px;border-left:1px solid var(--rule);color:var(--body)}}.model-note-label{{color:var(--accent)}}.filter-panel,.adjust{{margin-top:22px}}.filter-panel summary,.adjust summary{{width:fit-content;padding:7px 10px;border:1px solid var(--rule);border-radius:8px;color:var(--muted);font-size:12px;cursor:pointer}}.filter-panel[open] summary,.adjust[open] summary{{color:var(--ink)}}.filter-fields,.advanced-fields{{margin-top:20px}}.filter-fields{{padding:16px 0 1px;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}}.filter-fields .field{{margin-bottom:14px}}.filter-reset{{margin:0 0 15px;padding:5px 8px;border:1px solid var(--rule);border-radius:7px;background:transparent;color:var(--muted);font-size:11px;cursor:pointer}}.filter-reset:hover{{color:var(--ink)}}.check{{display:flex!important;align-items:flex-start;gap:8px;color:var(--body)!important}}.check input{{margin-top:4px;accent-color:var(--accent)}}[hidden]{{display:none!important}}
.result-heading{{border-top:1px solid var(--ink);padding:12px 0 20px;color:var(--muted);font-size:12px}}.result-number{{display:flex;align-items:baseline;gap:10px;padding-bottom:21px;border-bottom:1px solid var(--ink);color:var(--accent);font-size:46px;line-height:1.05;letter-spacing:-.07em;font-variant-numeric:tabular-nums;white-space:nowrap}}.result-number small{{color:var(--muted);font-size:13px;letter-spacing:0}}.result-summary{{margin:18px 0 31px;max-width:54ch;color:var(--body);font-size:14px;line-height:1.75}}.result-summary strong{{color:var(--ink);font-weight:400}}.breakdown-heading{{display:flex;justify-content:space-between;gap:15px;padding-bottom:8px;border-bottom:1px solid var(--ink);color:var(--muted);font-size:12px}}.cost-row{{display:grid;grid-template-columns:120px 1fr 82px;gap:14px;align-items:center;padding:10px 0;border-bottom:1px solid var(--rule);font-size:12px}}.row-name{{color:var(--body)}}.bar{{height:5px;background:var(--rule)}}.bar i{{display:block;width:var(--width);height:100%;background:var(--data);border-radius:999px}}.row-value{{text-align:right;color:var(--body);font-variant-numeric:tabular-nums}}.cost-row.total{{padding-top:13px;border-bottom:1px solid var(--ink)}}.cost-row.total .row-name,.cost-row.total .row-value{{color:var(--ink)}}.cost-row.total .row-value{{font-size:14px}}.row-share{{display:block;visibility:hidden;color:var(--muted);font-size:10px;line-height:1.5}}.cost-row:hover .row-share,.cost-row:focus-visible .row-share{{visibility:visible}}.cost-row:focus-visible{{outline:2px solid var(--accent);outline-offset:3px}}
.curve{{margin-top:52px;border-top:1px solid var(--rule);padding-top:15px}}.curve h2,.details h2{{margin:0;color:var(--muted);font-size:12px;font-weight:400}}.curve-wrap{{position:relative;margin-top:15px;border-bottom:1px solid var(--rule);padding:0 0 7px;cursor:crosshair;touch-action:pan-y}}.curve svg{{display:block;width:100%;height:auto}}.curve-wrap:focus-visible{{outline:2px solid var(--accent);outline-offset:3px}}.chart-tip{{position:absolute;z-index:2;max-width:calc(100% - 12px);padding:4px 9px;border-radius:6px;background:var(--ink);color:var(--bg);font-size:11px;line-height:1.4;white-space:normal;transform:translate(-50%,-135%);pointer-events:none}}.chart-year-line{{stroke:var(--rule);stroke-width:1;vector-effect:non-scaling-stroke}}.chart-years{{position:relative;height:18px;margin-top:2px;color:var(--muted);font-size:10px;line-height:16px;pointer-events:none}}.chart-year{{position:absolute;white-space:nowrap;transform:translateX(-50%)}}.chart-year.first{{transform:none}}.chart-year.last{{transform:translateX(-100%)}}.chart-line{{stroke:var(--ink);stroke-width:2;stroke-linecap:round;vector-effect:non-scaling-stroke}}.chart-line.interpolated{{stroke-dasharray:5 5;opacity:.65}}.chart-observation{{fill:var(--ink);stroke:var(--bg);stroke-width:1;vector-effect:non-scaling-stroke}}.chart-guide{{stroke:var(--accent);stroke-width:1.5;stroke-dasharray:3 3;opacity:.9;vector-effect:non-scaling-stroke}}.chart-dot{{fill:var(--accent);stroke:var(--bg);stroke-width:1.5}}.chart-key{{display:flex;flex-wrap:wrap;gap:8px 18px;margin-top:8px;color:var(--muted);font-size:10px}}.chart-key>span{{display:inline-flex;align-items:center;gap:6px}}.key-dot{{width:6px;height:6px;border-radius:50%;background:var(--ink)}}.key-dash{{width:18px;border-top:1px dashed var(--ink);opacity:.65}}.curve-note{{display:flex;justify-content:space-between;gap:14px;margin-top:9px;color:var(--muted);font-size:12px}}.curve-note b{{color:var(--accent);font-weight:400}}.details{{margin-top:72px;border-top:1px solid var(--rule);padding-top:15px}}.details-grid{{display:grid;grid-template-columns:1fr 1fr;gap:45px}}.details p{{margin:16px 0 0;color:var(--body);font-size:13px;line-height:1.75}}footer{{display:flex;justify-content:space-between;gap:25px;margin-top:70px;border-top:1px solid var(--rule);padding-top:14px;color:var(--muted);font-size:12px;line-height:1.6}}footer p{{margin:0;max-width:56ch}}
@media(max-width:700px){{.page{{padding:36px 24px 64px}}.top{{margin-bottom:38px}}.calculator{{grid-template-columns:1fr;gap:47px}}.intro{{margin-bottom:45px}}.result-number{{font-size:42px}}.details-grid{{grid-template-columns:1fr;gap:27px}}.curve{{margin-top:50px}}footer{{display:block}}footer p+p{{margin-top:12px}}}}@media(max-width:390px){{.page{{padding-left:19px;padding-right:19px}}.cost-row{{grid-template-columns:106px 1fr 75px;gap:9px}}.result-number{{font-size:39px}}}}@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}}}
 .chart-tip{{width:max-content;max-width:none;white-space:nowrap}}.chart-tip.edge-left{{transform:translate(0,-135%)}}.chart-tip.edge-right{{transform:translate(-100%,-135%)}}
"""


def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def asset(name):
    return (Path(__file__).parent / "assets" / name).read_text(encoding="utf-8")


def boot_js(_shared, page_js):
    return page_js


def page_shell(
    *,
    title,
    body,
    active="index.html",
    hero="",
    foot="",
    style="",
    script="",
    veh=True,
    description="",
    page_id="",
    **_kwargs,
):
    del active, hero, veh
    footer = f"<footer>{foot}</footer>" if foot else ""
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><meta name="description" content="{esc(description)}"><meta name="theme-color" content="{LIGHT_TOKENS["bg"]}" media="(prefers-color-scheme:light)"><meta name="theme-color" content="{DARK_TOKENS["bg"]}" media="(prefers-color-scheme:dark)"><style>{BASE_CSS}{style}</style></head>
<body id="{esc(page_id)}"><a class="skip" href="#calculator">Skip to calculator</a><div class="page"><header class="top"><h1 data-i18n="title">Vehicle cost calculator</h1><nav aria-label="Language"><button data-lang="en" aria-pressed="true">en</button><button data-lang="pl" aria-pressed="false">pl</button></nav></header><main>{body}</main>{footer}</div><script>{script}</script></body></html>'''


SHARED_FULL: tuple[str, ...] = ()
SHARED_LITE: tuple[str, ...] = ()
SELECTOR_CSS = ""
SELECTOR_JS = ""


def selector_bar():
    return '<div><button data-lang="en">en</button><button data-lang="pl">pl</button></div>'
