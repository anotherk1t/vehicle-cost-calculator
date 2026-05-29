"""Surface 1 — personal TCO: compute math (source of truth) + static render."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.tco import (
    CLASS_DEFAULTS,
    PUMP_PETROL_PLN,
    _interp,
    compute_tco,
    render_tco,
)

# A two-point curve: 30k at age 2, 22k at age 5 (≈2667 zł/yr straight-line).
CURVE = [
    {"age": 2, "smooth": 30000},
    {"age": 5, "smooth": 22000},
]

SAMPLE = {
    "meta": {
        "current_year": 2026,
        "sample": False,
        "cc_order": ["<=125", "126-300", "301-600", "601-900", "900+"],
        "heat": {"601-900": "#f35b04"},
    },
    "coverage": {"n_total": 1234, "pct_year": 88.0, "pct_cc": 91.0, "pct_km": 70.0},
    "classes": {
        "601-900": {
            "anchor": 30000,
            "sweet_spot_age": 3,
            "points": [
                {
                    "age": 2,
                    "smooth": 30000,
                    "median": 30000,
                    "p25": 27000,
                    "p75": 33000,
                    "median_km": 10000,
                    "retained_pct": 100.0,
                    "annual_depr": 3000,
                    "n": 8,
                    "year": 2024,
                },
                {
                    "age": 5,
                    "smooth": 22000,
                    "median": 22000,
                    "p25": 19000,
                    "p75": 25000,
                    "median_km": 40000,
                    "retained_pct": 73.3,
                    "annual_depr": 2000,
                    "n": 8,
                    "year": 2021,
                },
            ],
        }
    },
}


class TestInterp:
    def test_clamps_below_range(self):
        assert _interp(CURVE, 0) == 30000

    def test_clamps_above_range(self):
        assert _interp(CURVE, 99) == 22000

    def test_linear_midpoint(self):
        # halfway in age (3.5) → halfway in value (26000)
        assert _interp(CURVE, 3.5) == pytest.approx(26000)

    def test_empty_curve_is_none(self):
        assert _interp([], 3) is None


class TestComputeTco:
    def _run(self, **kw):
        base = dict(
            curve=CURVE,
            age=2,
            hold_years=3,
            annual_km=8000,
            fuel_per100=4.9,
            service_per1000=120,
            insurance_yr=820,
        )
        base.update(kw)
        return compute_tco(**base)

    def test_depreciation_from_curve(self):
        r = self._run()
        # buy at age 2 (30k), sell at age 5 (22k) → 8000 lost over 3y ≈ 2667/yr
        depr = next(i["pln"] for i in r["items"] if i["key"] == "depreciation")
        assert depr == pytest.approx(2667, abs=2)

    def test_price_override_scales_curve(self):
        # Pay 15k for a bike the curve fits at 30k → everything halves.
        r = self._run(price_paid=15000)
        depr = next(i["pln"] for i in r["items"] if i["key"] == "depreciation")
        assert depr == pytest.approx(1333, abs=2)
        assert r["value_end"] == pytest.approx(11000, abs=2)

    def test_fuel_scales_with_distance_and_price(self):
        r = self._run(annual_km=10000, fuel_per100=5.0, pump_price=6.0)
        fuel = next(i["pln"] for i in r["items"] if i["key"] == "fuel")
        assert fuel == pytest.approx(5.0 / 100 * 10000 * 6.0)  # 3000

    def test_band_brackets_total(self):
        r = self._run()
        assert r["total_lo"] < r["total"] < r["total_hi"]

    def test_per_km_and_lifetime(self):
        r = self._run()
        assert r["per_km"] == pytest.approx(r["total"] / 8000, abs=0.01)
        assert r["lifetime"] == pytest.approx(r["total"] * 3, abs=2)

    def test_depr_share_is_a_percentage(self):
        r = self._run()
        assert 0 <= r["depr_share"] <= 100

    def test_pcc_toggle_changes_fees(self):
        with_pcc = self._run(pcc_rate=0.02)
        without = self._run(pcc_rate=0.0)
        f_with = next(i["pln"] for i in with_pcc["items"] if i["key"] == "fees")
        f_without = next(i["pln"] for i in without["items"] if i["key"] == "fees")
        assert f_with > f_without

    def test_insurance_passed_through_untouched(self):
        r = self._run(insurance_yr=1234)
        ins = next(i["pln"] for i in r["items"] if i["key"] == "insurance")
        assert ins == 1234

    def test_no_negative_depreciation(self):
        # A rising "curve" (older worth more) must not produce negative depr.
        rising = [{"age": 2, "smooth": 20000}, {"age": 5, "smooth": 30000}]
        r = compute_tco(
            curve=rising, age=2, hold_years=3, annual_km=8000, fuel_per100=4.0, service_per1000=100, insurance_yr=500
        )
        depr = next(i["pln"] for i in r["items"] if i["key"] == "depreciation")
        assert depr == 0


class TestRender:
    def _write(self, tmp_path, payload):
        p = tmp_path / "aggregates.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        return str(p)

    def test_writes_calculator_with_curves(self, tmp_path):
        path = render_tco(self._write(tmp_path, SAMPLE), output_dir=str(tmp_path), filename="cost.html")
        assert path.endswith("cost.html")
        html = Path(path).read_text(encoding="utf-8")
        assert "const CFG =" in html  # coefficient source-of-truth embedded
        assert "const AGG =" in html  # depreciation curves embedded
        assert "function compute()" in html  # JS mirror present
        assert "Coming soon" in html  # seasonal panel stubbed
        assert "zł / km" in html  # odometer hero

    def test_embedded_config_is_valid_json(self, tmp_path):
        path = render_tco(self._write(tmp_path, SAMPLE), output_dir=str(tmp_path))
        html = Path(path).read_text(encoding="utf-8")
        line = next(ln for ln in html.splitlines() if ln.startswith("const CFG ="))
        cfg = json.loads(line[len("const CFG =") :].rstrip(";").strip())
        assert cfg["pumpPetrol"] == PUMP_PETROL_PLN
        assert set(cfg["classDefaults"]) == set(CLASS_DEFAULTS)

    def test_no_listing_fields_leak(self, tmp_path):
        # The page embeds aggregates — assert it stays curves-only.
        path = render_tco(self._write(tmp_path, SAMPLE), output_dir=str(tmp_path))
        html = Path(path).read_text(encoding="utf-8")
        line = next(ln for ln in html.splitlines() if ln.startswith("const AGG ="))
        blob = line[len("const AGG =") :]
        for leak in ('"url"', '"title"', '"listing_uid"', '"seller_name"'):
            assert leak not in blob

    def test_gate_when_no_curves(self, tmp_path):
        empty = {"meta": {"current_year": 2026, "cc_order": []}, "classes": {}}
        path = render_tco(self._write(tmp_path, empty), output_dir=str(tmp_path))
        html = Path(path).read_text(encoding="utf-8")
        assert "warming up" in html
        assert "const CFG =" not in html  # no calculator when there's nothing to compute

    def test_missing_aggregates_file_renders_gate(self, tmp_path):
        path = render_tco(str(tmp_path / "nope.json"), output_dir=str(tmp_path))
        assert "warming up" in Path(path).read_text(encoding="utf-8")
