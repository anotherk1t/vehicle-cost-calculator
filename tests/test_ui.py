"""Shipped-page contract and static data checks."""

import json
import shutil
import subprocess
from pathlib import Path

from src import ui
from src.tco import STRINGS


def test_tokens_and_layout_match_approved_plain_portfolio_concept():
    assert "#111110" in ui.BASE_CSS and "#faf9f6" in ui.BASE_CSS
    assert "#6fc3ca" in ui.BASE_CSS and "#1f6570" in ui.BASE_CSS
    assert "grid-template-columns:270px 1fr" in ui.BASE_CSS
    assert "max-width:840px" in ui.BASE_CSS


def test_en_pl_keys_match():
    assert set(STRINGS["en"]) == set(STRINGS["pl"])


def test_build_only_publishes_one_page_and_404(tmp_path):
    subprocess.run(["python", "build.py"], check=True)
    assert Path("public/index.html").exists() and Path("public/404.html").exists()
    assert not any(Path("public", p).exists() for p in ("ledger.html", "depreciation.html", "practice.html"))


def test_404_is_static_noindex_and_links_root():
    page = Path("static/404.html").read_text()
    assert 'name="robots" content="noindex"' in page
    assert 'href="/"' in page and "<script" not in page


def test_fuel_schema_is_dated_and_provenanced():
    fuel = json.loads(Path("data/fuel_prices.json").read_text())
    for key in ("country", "observed_at", "published_at", "source", "source_url", "unit", "prices"):
        assert key in fuel
    assert {"petrol95", "diesel", "lpg"} <= set(fuel["prices"])
    assert fuel["stale"] is False
    assert fuel["conversion"]["pln_per_eur"] == 4.3124
    assert fuel["original_eur_per_l"]["diesel"] == 1.728178662
    assert fuel["prices"] == {"petrol95": 6.50, "diesel": 7.45, "lpg": 2.94}
    assert "electric" not in fuel["prices"]
    assert fuel["source_url"].startswith("https://energy.ec.europa.eu/")
    assert fuel["conversion"]["source_url"].startswith("https://api.nbp.pl/")


def test_wrangler_uses_static_404():
    assert '"not_found_handling": "404-page"' in Path("wrangler.jsonc").read_text()


def test_only_one_runtime_asset_and_it_is_valid_js():
    assets = sorted(Path("src/assets").glob("*.js"))
    assert [p.name for p in assets] == ["tco.js"]
    if shutil.which("node"):
        assert subprocess.run(["node", "--check", str(assets[0])]).returncode == 0
    script = Path("src/assets/tco.js").read_text()
    assert "state.inspection ?? d.inspection" in script
    assert 'state.pcc = state.route === "private"' in script
    assert "function buildMotoCatalog(models)" in script
    assert "}).filter(profile => profile.reliable).sort" in script
    assert "const carMakes =" in script
    assert "profile.make === state.make" in script
    assert '$("carMake").addEventListener("change"' in script
    assert "profile.aliases.includes(state.model)" in script
    assert 'profile.status === "variant_required"' in script
    assert "function constrainTimeline(changed)" in script
    assert "Math.max(ageMin + 1, Math.floor(dataMax))" in script
    assert 'changed === "age"' in script
    assert 'changed === "sell"' in script
    assert "Math.round(number)" in script
    assert "range.min = String(ageMin); range.max = String(maxAge)" in script
    assert "number.min = String(min); number.max = String(max)" in script
    assert "quality.maxGap > 1" in script
    assert "!profile.reliable" in script
    assert 'template("curve_category"' in script
    assert "state.registration !== null" in script
    assert "endAge: Number(state.sell), scale" in script
    assert "function chartInspect(" in script
    assert 'chart.addEventListener("pointerdown"' in script
    assert 'mount.setAttribute("aria-label", text("chart"))' in script
    assert 'mount.setAttribute("aria-valuetext", tip.textContent)' in script
    assert 'mount.setAttribute("role", "slider")' in script
    assert "const ySpan = maxY - minY" in script
    assert "function curveQuality(" in script and "function curveContext(" in script
    assert "const rawPoints = context.modelPoints.length ? context.modelPoints : context.points" in script
    assert "const sparseModel = context.modelPoints.length && context.quality.points < 6" in script
    assert "const segments = points.slice(1).map" in script
    assert 'class="chart-line${interpolated' in script
    assert 'class="chart-observation"' in script
    assert "function chartYearTicks(" in script
    assert 'class="chart-year-line"' in script
    assert 'class="chart-years"' in script
    assert "function chartCrossesGap(" in script
    assert 'class="row-share"' in script
    assert 'class="chart-hover"' in script
    assert 'classList.toggle("edge-right"' in script
    assert ".chart-tip.edge-left" in ui.BASE_CSS


def test_timeline_controls_preserve_the_other_endpoint():
    if not shutil.which("node"):
        return
    subprocess.run(["python", "build.py"], check=True)
    script = r"""
const fs = require("fs"), vm = require("vm");
const html = fs.readFileSync("public/index.html", "utf8");
const source = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]).join("\n");
const elements = {};
const document = {
  documentElement: { lang: "en" },
  getElementById(id) { return elements[id] ||= {}; },
  querySelectorAll() { return []; },
  addEventListener() {}
};
const context = { console, document };
vm.createContext(context);
vm.runInContext(source, context);
context.state.vehicle = "car";
context.state.model = "volkswagen golf";
context.state.age = 5;
context.state.sell = 8;
context.constrainTimeline();
context.state.age = 0;
context.state.sell = 1;
context.constrainTimeline("age");
if (context.state.age !== 0 || context.state.sell !== 1) throw new Error("new vehicle age zero is unavailable");
context.state.sell = 8;
context.state.age = 10;
context.constrainTimeline("age");
if (context.state.age !== 7 || context.state.sell !== 8) throw new Error("purchase age moved sale age");
if (elements.ageNumber.max !== "7") throw new Error("purchase-age maximum does not preserve sale age");
if (elements.age.min !== "0" || elements.sell.min !== "0" || elements.sell.max !== elements.age.max) throw new Error("range tracks do not share a common scale");
context.state.age = 5;
context.state.sell = 2;
context.constrainTimeline("sell");
if (context.state.age !== 5 || context.state.sell !== 6) throw new Error("sale age moved purchase age");
if (elements.sellNumber.min !== "6") throw new Error("sale-age minimum does not follow purchase age");
context.state.age = 5.6;
context.state.sell = 8.4;
context.constrainTimeline("age");
if (context.state.age !== 6 || context.state.sell !== 8) throw new Error("fractional ages were not normalized");
context.state.age = 8;
context.state.sell = 8;
context.constrainTimeline("age");
if (context.state.age !== 7 || context.state.sell !== 8) throw new Error("purchase age crossed sale age");
context.state.age = 5;
context.state.sell = 99;
context.constrainTimeline("sell");
if (context.state.age !== 5 || context.state.sell !== Number(elements.sell.max)) throw new Error("sale age exceeded data range");
"""
    subprocess.run(["node", "-e", script], check=True)


def test_render_has_no_secondary_navigation():
    html = Path("public/index.html").read_text()
    assert "ledger.html" not in html and "depreciation.html" not in html and "practice.html" not in html
    assert 'data-veh="car"' in html and 'data-lang="pl"' in html
    assert 'data-i18n="title"' in html
    assert 'id="profileSearch"' in html and 'role="combobox"' in html
    assert 'id="categoryFilter"' in html and 'id="modelMeta"' in html
    assert "scrollbar-width:none" in html
    assert ".profile-results::-webkit-scrollbar" in html
    assert 'class="model-note"' in html
    assert 'id="carMake"' in html and 'data-i18n="make"' in html
    assert 'data-i18n-aria-label="age"' in html
    assert 'id="age" type="range" min="0"' in html
    assert 'id="ageNumber" type="number" min="0"' in html
    assert 'id="sell"' in html and 'id="sellNumber"' in html and 'data-i18n="sell"' in html
    assert 'id="hold"' not in html and "Ownership period" not in html
    assert "Poland · ownership ·" not in html
    assert '"electric"' not in html
    assert 'class="intro"' in html
    assert 'class="calculator"' in html
    assert 'class="result-number"' in html
    assert 'id="rows"' in html and 'id="chart"' in html
    assert "This is an estimate, not a quote" not in html
    assert "Data: aggregate asking-price curves" not in html
    assert "<footer>" not in html
    assert "const AGG_CAR =" in html
    assert '"Honda CB"' in html and '"BMW GS"' in html


def test_controls_follow_rounded_segmented_direction():
    css = ui.BASE_CSS
    assert ".kind-options,.purchase-options" in css
    assert "border-radius:10px" in css
    assert "border-radius:8px" in css
    assert "border-radius:7px" in css
    assert "border-radius:999px" in css
    assert "border-radius:50%" in css
    assert ".profile-results" in css and ".profile-option" in css
