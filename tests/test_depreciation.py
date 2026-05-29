"""Public depreciation renderer: consumes aggregates JSON, emits a static page."""

from __future__ import annotations

import json
from pathlib import Path

from src.depreciation import render_depreciation

SAMPLE = {
    "meta": {
        "current_year": 2026,
        "sample": True,
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
                    "year": 2024,
                    "n": 8,
                    "median": 30000,
                    "p25": 27000,
                    "p75": 33000,
                    "median_km": 10000,
                    "smooth": 30000,
                    "retained_pct": 100.0,
                    "annual_depr": 3000,
                },
                {
                    "age": 5,
                    "year": 2021,
                    "n": 8,
                    "median": 22000,
                    "p25": 19000,
                    "p75": 25000,
                    "median_km": 40000,
                    "smooth": 22000,
                    "retained_pct": 73.3,
                    "annual_depr": 2000,
                },
            ],
        }
    },
}


def _write(tmp_path, payload):
    p = tmp_path / "aggregates.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


class TestRender:
    def test_writes_page_from_aggregates(self, tmp_path):
        agg = _write(tmp_path, SAMPLE)
        path = render_depreciation(agg, output_dir=str(tmp_path), filename="depreciation.html")
        assert path.endswith("depreciation.html")
        html = Path(path).read_text(encoding="utf-8")
        assert "const AGG =" in html  # data embedded for client-side charts
        assert "function chart(" in html  # SVG charting present
        assert "SAMPLE DATA" in html  # sample flag surfaced
        assert "1,234" in html  # coverage chip rendered

    def test_embedded_payload_is_valid_json(self, tmp_path):
        agg = _write(tmp_path, SAMPLE)
        path = render_depreciation(agg, output_dir=str(tmp_path))
        html = Path(path).read_text(encoding="utf-8")
        line = next(ln for ln in html.splitlines() if ln.startswith("const AGG ="))
        payload = json.loads(line[len("const AGG =") :].rstrip(";").strip())
        assert payload["classes"]["601-900"]["anchor"] == 30000

    def test_no_sample_banner_when_real(self, tmp_path):
        real = json.loads(json.dumps(SAMPLE))
        real["meta"]["sample"] = False
        path = render_depreciation(_write(tmp_path, real), output_dir=str(tmp_path))
        assert "SAMPLE DATA" not in Path(path).read_text(encoding="utf-8")

    def test_empty_classes_placeholder(self, tmp_path):
        empty = {"meta": {"current_year": 2026}, "coverage": {}, "classes": {}}
        path = render_depreciation(_write(tmp_path, empty), output_dir=str(tmp_path))
        assert "No curve yet" in Path(path).read_text(encoding="utf-8")
