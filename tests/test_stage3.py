"""Surface 3 — Gdańsk transport budget + investment map: data, render."""

from __future__ import annotations

import json
from pathlib import Path

from src.stage3 import MODE_COLOR, STRINGS, render_stage3

BUDGET = Path("data/stage3_gdansk_transport.json")
INVEST = Path("data/stage3_gdansk_investments.json")


class TestBudget:
    def test_shaped(self):
        d = json.loads(BUDGET.read_text(encoding="utf-8"))
        any_year = next(iter(d["years"].values()))
        for k in ("total_pln", "roads_pln", "nonroad_transport_pln", "current_pln", "capital_pln", "pop"):
            assert k in any_year

    def test_roads_chapters_only_from_2012(self):
        d = json.loads(BUDGET.read_text(encoding="utf-8"))["years"]
        assert d["2012"]["roads_pln"] > 0
        assert d.get("2010", {}).get("roads_pln", 0) == 0

    def test_the_flip_direction(self):
        d = json.loads(BUDGET.read_text(encoding="utf-8"))["years"]
        assert d["2012"]["roads_share"] > d["2024"]["roads_share"]


class TestInvestments:
    def test_present_and_modes_known(self):
        d = json.loads(INVEST.read_text(encoding="utf-8"))
        assert d["projects"]
        for p in d["projects"]:
            assert p["mode"] in MODE_COLOR

    def test_coords_inside_gdansk_bbox(self):
        d = json.loads(INVEST.read_text(encoding="utf-8"))["projects"]
        for p in d:
            assert 54.2 <= p["lat"] <= 54.5 and 18.3 <= p["lon"] <= 19.05

    def test_costs_present_and_positive(self):
        d = json.loads(INVEST.read_text(encoding="utf-8"))["projects"]
        for p in d:
            assert p["tot"] > 0 and p["city"] >= 0 and p["ue"] >= 0
            assert 2000 <= p["yr"] <= 2030

    def test_both_modes_represented(self):
        d = json.loads(INVEST.read_text(encoding="utf-8"))["projects"]
        modes = {p["mode"] for p in d}
        assert {"road", "transit"} <= modes


class TestStrings:
    def test_en_and_pl_have_same_keys(self):
        assert set(STRINGS["en"]) == set(STRINGS["pl"])

    def test_nav_and_map_labels_present(self):
        for lang in ("en", "pl"):
            for k in ("nav_practice", "f_road", "f_transit", "pop_city", "leg_transit"):
                assert STRINGS[lang][k]


class TestRender:
    def test_renders_with_embedded_data_and_map(self, tmp_path):
        out = render_stage3(budget_path=str(BUDGET), invest_path=str(INVEST),
                            output_dir=str(tmp_path), filename="practice.html")
        html = Path(out).read_text(encoding="utf-8")
        assert html.startswith("<!doctype html>")
        # data embedded inline (no fetch at runtime for our own data)
        assert "const BUDGET =" in html and "const INVEST =" in html
        # Leaflet loaded from same-origin bundle
        assert "leaflet.min.js" in html and "leaflet.min.css" in html
        for mount in ('id="flip"', 'id="run"', 'id="map"', 'id="modeFilter"', 'id="yrSlider"'):
            assert mount in html
        # nav cross-links + active page
        assert 'href="practice.html"' in html and 'class="here"' in html

    def test_handles_missing_investments_file(self, tmp_path):
        out = render_stage3(budget_path=str(BUDGET), invest_path=str(tmp_path / "nope.json"),
                            output_dir=str(tmp_path))
        assert "const INVEST =" in Path(out).read_text(encoding="utf-8")

    def test_no_marketplace_rows_leak(self, tmp_path):
        out = render_stage3(budget_path=str(BUDGET), invest_path=str(INVEST), output_dir=str(tmp_path))
        html = Path(out).read_text(encoding="utf-8").lower()
        for bad in ("listing_uid", "seller_name", "otomoto", "olx.pl"):
            assert bad not in html
