"""Ownership calculation and output contract."""

import json
from pathlib import Path

import pytest

from src.tco import (
    CATEGORY_DEFAULTS,
    CATEGORY_ORDER,
    _interp,
    compute_tco,
    fuel_is_stale,
    render_tco,
    validate_fuel_snapshot,
)

CURVE = [{"age": 2, "smooth": 30000}, {"age": 5, "smooth": 22000}]


def base(**extra):
    args = dict(
        curve=CURVE, age=2, hold_years=3, annual_km=8000, fuel_per100=4.9, service_per1000=120, insurance_yr=820
    )
    args.update(extra)
    return compute_tco(**args)


def test_interpolation_clamps_and_interpolates():
    assert _interp(CURVE, 0) == 30000
    assert _interp(CURVE, 99) == 22000
    assert _interp(CURVE, 3.5) == pytest.approx(26000)


def test_depreciation_and_fuel():
    r = base(pump_price=6)
    assert next(i["pln"] for i in r["items"] if i["key"] == "depreciation") == pytest.approx(2667, abs=2)
    assert next(i["pln"] for i in r["items"] if i["key"] == "fuel") == 2352


def test_private_pcc_only_and_market_basis():
    dealer = base(purchase_path="dealer", pcc_rate=0.02)
    private = base(purchase_path="private", pcc_rate=0.02, market_value=35000)
    assert next(i["pln"] for i in private["items"] if i["key"] == "fees") > next(
        i["pln"] for i in dealer["items"] if i["key"] == "fees"
    )


def test_one_time_costs_are_annualised_and_breakdown_is_100():
    short = base(hold_years=1, registration_cost=160)
    long = base(hold_years=4, registration_cost=160)
    fs = next(i["pln"] for i in short["items"] if i["key"] == "fees")
    fl = next(i["pln"] for i in long["items"] if i["key"] == "fees")
    assert fs > fl
    assert sum(long["shares"].values()) == pytest.approx(100)


def test_inspection_is_a_separate_editable_cost():
    standard = base(inspection_yr=94)
    edited = base(inspection_yr=250)

    def get(result):
        return next(i["pln"] for i in result["items"] if i["key"] == "inspection")

    assert get(standard) == 94 and get(edited) == 250


def test_render_emits_sidecars_and_real_vintage(tmp_path):
    agg = json.loads(Path("data/aggregates.json").read_text())
    p = tmp_path / "aggregates.json"
    p.write_text(json.dumps(agg))
    out = Path(render_tco(str(p), output_dir=str(tmp_path)))
    html = out.read_text()
    assert "const CFG =" in html and "const AGG_MOTO =" in html
    assert (tmp_path / "tco_cars.json").exists() and (tmp_path / "fuel-prices.json").exists()
    assert str(agg["meta"]["current_year"]) in html


def test_render_missing_aggregate_still_has_page(tmp_path):
    out = Path(
        render_tco(
            str(tmp_path / "missing.json"),
            car_aggregates_path=str(tmp_path / "missing-car.json"),
            output_dir=str(tmp_path),
        )
    )
    assert out.exists()


def test_fuel_snapshot_validation_and_fourteen_day_cutoff():
    snapshot = json.loads(Path("data/fuel_prices.json").read_text())
    assert validate_fuel_snapshot(snapshot)
    assert not fuel_is_stale(snapshot, today=__import__("datetime").date(2026, 8, 30))
    fresh = dict(snapshot, stale=False, observed_at="2026-08-25")
    assert not fuel_is_stale(fresh, today=__import__("datetime").date(2026, 8, 30))


def test_frontend_supports_versioned_motorcycle_taxonomy():
    expected = {
        "moped",
        "scooter",
        "maxi_scooter",
        "naked",
        "sport",
        "sport_touring",
        "touring",
        "adventure",
        "adventure_touring",
        "cruiser",
        "enduro",
        "motocross",
        "atv_other",
        "mixed",
    }
    assert set(CATEGORY_ORDER) == expected
    assert set(CATEGORY_DEFAULTS) == expected
    aggregate = json.loads(Path("data/aggregates.json").read_text())
    assert aggregate["meta"]["taxonomy_version"] == "2026-08-31-family-v2"
    assert len(aggregate["models"]) == 461
    assert {model["category"] for model in aggregate["models"].values()} == expected
    assert aggregate["models"]["Honda Forza"]["category"] == "maxi_scooter"
    assert aggregate["models"]["BMW F"]["category_status"] == "variant_required"
