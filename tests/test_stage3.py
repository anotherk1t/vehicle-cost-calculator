"""Surface 3 — Gdańsk transport budget page: data shape, projects, render."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import stage3
from src.stage3 import MODE_COLOR, PROJECTS, STRINGS, render_stage3

BUDGET = Path("data/stage3_gdansk_transport.json")


class TestData:
    def test_budget_file_present_and_shaped(self):
        d = json.loads(BUDGET.read_text(encoding="utf-8"))
        assert "years" in d and d["years"]
        any_year = next(iter(d["years"].values()))
        for k in ("total_pln", "roads_pln", "nonroad_transport_pln", "current_pln", "capital_pln", "pop"):
            assert k in any_year

    def test_roads_chapters_only_from_2012(self):
        # BDL's road-chapter series starts 2012; earlier years carry no roads split.
        d = json.loads(BUDGET.read_text(encoding="utf-8"))["years"]
        assert d["2012"]["roads_pln"] > 0
        assert d.get("2010", {}).get("roads_pln", 0) == 0

    def test_the_flip_direction(self):
        # roads share of the transport budget falls between 2012 and 2024.
        d = json.loads(BUDGET.read_text(encoding="utf-8"))["years"]
        assert d["2012"]["roads_share"] > d["2024"]["roads_share"]


class TestProjects:
    def test_every_project_has_a_known_mode_colour(self):
        for p in PROJECTS:
            assert p["mode"] in MODE_COLOR

    def test_positions_inside_schematic_box(self):
        for p in PROJECTS:
            assert 0 <= p["x"] <= 100 and 0 <= p["y"] <= 100

    def test_costs_are_numeric_or_none(self):
        for p in PROJECTS:
            assert p["cost"] is None or isinstance(p["cost"], (int, float))

    def test_both_languages_on_every_project(self):
        for p in PROJECTS:
            assert p["name"] and p["name_pl"] and p["blurb"] and p["blurb_pl"]


class TestStrings:
    def test_en_and_pl_have_same_keys(self):
        assert set(STRINGS["en"]) == set(STRINGS["pl"])

    def test_nav_practice_label_present(self):
        assert STRINGS["en"]["nav_practice"] and STRINGS["pl"]["nav_practice"]


class TestRender:
    def test_renders_self_contained_page(self, tmp_path):
        out = render_stage3(budget_path=str(BUDGET), output_dir=str(tmp_path), filename="practice.html")
        html = Path(out).read_text(encoding="utf-8")
        assert html.startswith("<!doctype html>")
        # data embedded, no external JS/CDN script tags
        assert "const BUDGET =" in html and "const PROJECTS =" in html
        assert "<script src=" not in html
        # selectors + nav wired
        assert 'id="langSeg"' in html
        assert 'href="practice.html"' in html and 'class="here"' in html
        # the three sections render their mount points
        for mount in ('id="flip"', 'id="run"', 'id="map"', 'id="plist"'):
            assert mount in html

    def test_no_marketplace_rows_leak(self, tmp_path):
        # this surface is public-finance only — never any listing fields.
        out = render_stage3(budget_path=str(BUDGET), output_dir=str(tmp_path))
        html = Path(out).read_text(encoding="utf-8").lower()
        for bad in ("listing_uid", "seller_name", "otomoto", "olx.pl"):
            assert bad not in html
