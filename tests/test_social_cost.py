"""Surface 2 public-cost calculator: coefficient sanity, balance math, render."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import social_cost as sc
from src.social_cost import (
    MODES,
    compute_balance,
    render_social_cost,
)


class TestCoefficients:
    @pytest.mark.parametrize(
        ("mode", "expected_total"),
        [
            ("car_petrol", 11.6),  # handbook petrol car
            ("car_diesel", 12.4),  # handbook diesel car
            ("motorcycle", 24.5),  # handbook motorcycle
        ],
    )
    def test_external_totals_match_handbook(self, mode, expected_total):
        total = sum(MODES[mode]["external"].values())
        assert total == pytest.approx(expected_total, abs=0.3)

    def test_ev_is_only_modestly_cheaper_than_petrol(self):
        petrol = sum(MODES["car_petrol"]["external"].values())
        ev = sum(MODES["car_ev"]["external"].values())
        # The whole point: not near-zero — within ~25% of a petrol car.
        assert 0.70 < ev / petrol < 0.95

    def test_ev_keeps_crashes_and_congestion(self):
        assert MODES["car_ev"]["external"]["accidents"] == MODES["car_petrol"]["external"]["accidents"]
        assert MODES["car_ev"]["external"]["congestion"] == MODES["car_petrol"]["external"]["congestion"]

    def test_motorcycle_has_zero_congestion(self):
        assert MODES["motorcycle"]["external"]["congestion"] == 0.0
        assert MODES["scooter"]["external"]["congestion"] == 0.0

    def test_scooter_crash_is_a_band_below_blended_moto(self):
        lo, hi = MODES["scooter"]["crash_band"]
        assert lo < hi
        assert hi == MODES["motorcycle"]["external"]["accidents"]  # blended = upper bound
        assert MODES["scooter"]["external"]["accidents"] < hi  # default sits below blended


class TestComputeBalance:
    def test_petrol_partial_coverage(self):
        r = compute_balance("car_petrol", 12000)
        assert r["external_total"] > 0
        assert r["contribution_total"] > 0
        # Drivers cover a real-but-minority share of their footprint.
        assert 20 < r["coverage_pct"] < 60
        assert r["net_burden"] == r["external_total"] - r["contribution_total"]

    def test_ev_is_net_subsidised(self):
        ev = compute_balance("car_ev", 12000)
        # Subsidy line is negative and present.
        subsidy = next(i for i in ev["contribution_items"] if i["key"] == "subsidy")
        assert subsidy["pln"] < 0
        # After the grant the driver is a net recipient → negative coverage.
        assert ev["coverage_pct"] < 0

    def test_ev_costs_society_nearly_as_much_as_petrol(self):
        petrol = compute_balance("car_petrol", 12000)
        ev = compute_balance("car_ev", 12000)
        assert ev["external_total"] > 0.70 * petrol["external_total"]

    def test_congestion_band_lifts_car_cost_but_not_scooter(self):
        car_rural = compute_balance("car_petrol", 12000, congestion="rural")
        car_core = compute_balance("car_petrol", 12000, congestion="core")
        assert car_core["external_total"] > car_rural["external_total"]

        scoot_rural = compute_balance("scooter", 12000, congestion="rural")
        scoot_core = compute_balance("scooter", 12000, congestion="core")
        assert scoot_core["external_total"] == scoot_rural["external_total"]

    def test_scooter_crash_bound_changes_cost(self):
        low = compute_balance("scooter", 12000, crash_bound="low")
        high = compute_balance("scooter", 12000, crash_bound="high")
        assert high["external_total"] > low["external_total"]

    def test_vat_toggle_raises_contribution(self):
        without = compute_balance("car_petrol", 12000, include_vat=False)
        with_vat = compute_balance("car_petrol", 12000, include_vat=True)
        assert with_vat["contribution_total"] > without["contribution_total"]

    def test_scales_with_distance(self):
        low = compute_balance("car_petrol", 5000)
        high = compute_balance("car_petrol", 20000)
        assert high["external_total"] > low["external_total"]

    def test_custom_eur_rate_moves_external(self):
        cheap = compute_balance("car_petrol", 12000, eur_pln=4.0)
        dear = compute_balance("car_petrol", 12000, eur_pln=5.0)
        assert dear["external_total"] > cheap["external_total"]


class TestRender:
    def test_writes_page(self, tmp_path):
        path = render_social_cost(output_dir=str(tmp_path), now=1_780_000_000)
        assert path.endswith("index.html")
        html = Path(path).read_text(encoding="utf-8")
        # Every mode is selectable.
        for m in MODES.values():
            assert m["label"] in html
        # The interactive config and the JS calculator are embedded.
        assert "const CFG =" in html
        assert "function compute()" in html
        # Honesty hooks present.
        assert "CE Delft" in html
        assert "KGP" in html

    def test_embedded_config_is_valid_json(self, tmp_path):
        path = render_social_cost(output_dir=str(tmp_path))
        html = Path(path).read_text(encoding="utf-8")
        line = next(ln for ln in html.splitlines() if ln.startswith("const CFG ="))
        payload = line[len("const CFG =") :].rstrip(";").strip()
        cfg = json.loads(payload)
        assert set(cfg["modes"]) == set(MODES)
        assert cfg["eurPlnDefault"] == sc.EUR_PLN_DEFAULT
