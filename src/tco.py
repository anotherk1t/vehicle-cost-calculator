"""Ownership-cost calculator: calculations and a static page renderer."""

from __future__ import annotations

import json
import logging
import os
from datetime import date

from src import ui

logger = logging.getLogger(__name__)
DEFAULT_OUTPUT_DIR = "public"
DEFAULT_AGGREGATES = os.path.join("data", "aggregates.json")
DEFAULT_CAR_AGGREGATES = os.path.join("data", "cars_aggregates.json")
DEFAULT_FUEL = os.path.join("data", "fuel_prices.json")
CARS_SIDECAR = "tco_cars.json"
FUEL_SIDECAR = "fuel-prices.json"

PCC_RATE = 0.02
REGISTRATION_PLN = 160.0  # one-time registration, retained plates not assumed
INSPECTION_CAR_PLN = 149.0
INSPECTION_MOTO_PLN = 94.0
SERVICE_AGE_K = 0.045
SERVICE_BAND = 0.35
PUMP_PETROL_PLN = 6.50  # official 2026-08-24 snapshot, displayed with provenance

CATEGORY_ORDER = [
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
]
CATEGORY_DEFAULTS = {
    "moped": {"label": "Moped ≤50", "tag": "city / AM", "fuel_per100": 2.5, "service_per1000": 45, "insurance_yr": 300},
    "scooter": {"label": "Scooter", "tag": "commuter", "fuel_per100": 3.0, "service_per1000": 55, "insurance_yr": 350},
    "maxi_scooter": {
        "label": "Maxi-scooter",
        "tag": "large scooter",
        "fuel_per100": 4.0,
        "service_per1000": 90,
        "insurance_yr": 550,
    },
    "naked": {
        "label": "Naked / roadster",
        "tag": "standard road bike",
        "fuel_per100": 4.5,
        "service_per1000": 95,
        "insurance_yr": 650,
    },
    "sport": {
        "label": "Sport",
        "tag": "performance road bike",
        "fuel_per100": 5.2,
        "service_per1000": 120,
        "insurance_yr": 950,
    },
    "sport_touring": {
        "label": "Sport-touring",
        "tag": "sport and distance",
        "fuel_per100": 5.1,
        "service_per1000": 115,
        "insurance_yr": 875,
    },
    "touring": {
        "label": "Touring / GT",
        "tag": "distance and luggage",
        "fuel_per100": 5.0,
        "service_per1000": 110,
        "insurance_yr": 800,
    },
    "adventure": {
        "label": "Adventure",
        "tag": "mixed-surface",
        "fuel_per100": 4.8,
        "service_per1000": 120,
        "insurance_yr": 800,
    },
    "adventure_touring": {
        "label": "Adventure-touring",
        "tag": "road-focused travel",
        "fuel_per100": 4.9,
        "service_per1000": 115,
        "insurance_yr": 800,
    },
    "cruiser": {
        "label": "Cruiser",
        "tag": "cruiser / chopper",
        "fuel_per100": 5.0,
        "service_per1000": 100,
        "insurance_yr": 700,
    },
    "enduro": {
        "label": "Enduro / trail",
        "tag": "trail / dual-sport / SM",
        "fuel_per100": 4.2,
        "service_per1000": 100,
        "insurance_yr": 600,
    },
    "motocross": {
        "label": "Motocross",
        "tag": "closed-course; adjust costs",
        "fuel_per100": 5.5,
        "service_per1000": 180,
        "insurance_yr": 500,
    },
    "atv_other": {
        "label": "ATV / other",
        "tag": "quad or three-wheeler",
        "fuel_per100": 7.0,
        "service_per1000": 150,
        "insurance_yr": 700,
    },
    "mixed": {
        "label": "Variant required",
        "tag": "family spans several types",
        "fuel_per100": 4.8,
        "service_per1000": 110,
        "insurance_yr": 700,
    },
}
CAR_FUEL_DEFAULTS = {
    "petrol": {"label": "Petrol", "per100": 7.0, "fuel": "petrol95", "unit": "l"},
    "diesel": {"label": "Diesel", "per100": 5.5, "fuel": "diesel", "unit": "l"},
    "lpg": {"label": "LPG", "per100": 9.0, "fuel": "lpg", "unit": "l"},
    "hybrid": {"label": "Hybrid", "per100": 4.8, "fuel": "petrol95", "unit": "l"},
}
CAR_SERVICE_PER1000 = 130.0
CAR_INSURANCE_YR = 2200.0
COMPONENT_ORDER = [
    ("depreciation", "Depreciation"),
    ("fuel", "Fuel"),
    ("service", "Service, tyres & repairs"),
    ("insurance", "Insurance"),
    ("inspection", "Inspection"),
    ("fees", "Registration & PCC"),
]


def fuel_is_stale(snapshot, *, today=None):
    """Return True when a snapshot is explicitly stale or older than 14 days."""
    if snapshot.get("stale"):
        return True
    try:
        observed = date.fromisoformat(snapshot["observed_at"])
        current = today or date.today()
        return (current - observed).days > int(snapshot.get("stale_after_days", 14))
    except (KeyError, TypeError, ValueError):
        return True


def validate_fuel_snapshot(snapshot):
    required = {"country", "observed_at", "published_at", "source", "source_url", "unit", "prices"}
    missing = required - set(snapshot)
    if missing:
        raise ValueError(f"fuel snapshot missing: {', '.join(sorted(missing))}")
    for key in ("petrol95", "diesel", "lpg"):
        if not isinstance(snapshot["prices"].get(key), (int, float)) or snapshot["prices"][key] <= 0:
            raise ValueError(f"fuel snapshot has no positive {key} price")
    return True


def _interp(curve, age):
    if not curve:
        return None
    points = sorted(curve, key=lambda p: p["age"])
    if age <= points[0]["age"]:
        return float(points[0]["smooth"])
    if age >= points[-1]["age"]:
        return float(points[-1]["smooth"])
    for left, right in zip(points, points[1:], strict=False):
        if age <= right["age"]:
            t = (age - left["age"]) / (right["age"] - left["age"] or 1)
            return float(left["smooth"] + t * (right["smooth"] - left["smooth"]))
    return float(points[-1]["smooth"])


def compute_tco(
    *,
    curve,
    age,
    hold_years,
    annual_km,
    fuel_per100,
    service_per1000,
    insurance_yr,
    price_paid=None,
    pump_price=PUMP_PETROL_PLN,
    pcc_rate=PCC_RATE,
    purchase_path="dealer",
    market_value=None,
    registration_cost=REGISTRATION_PLN,
    inspection_yr=INSPECTION_MOTO_PLN,
    inspection_due=True,
    service_age_k=SERVICE_AGE_K,
    service_band=SERVICE_BAND,
    registration_yr=None,
):
    """Return annualised costs; PCC is only charged for a private-seller purchase."""
    now = _interp(curve, float(age))
    later = _interp(curve, float(age) + float(hold_years))
    if now is None or later is None or hold_years <= 0:
        return {"ok": False}
    paid = float(price_paid) if price_paid is not None else now
    basis = float(market_value if market_value is not None else paid)
    scale = paid / now if now else 1
    depreciation = max(0.0, paid - later * scale) / hold_years
    fuel = float(fuel_per100) / 100 * float(annual_km) * float(pump_price)
    service = float(service_per1000) * float(annual_km) / 1000 * (1 + service_age_k * (float(age) + hold_years / 2))
    pcc = basis * pcc_rate / hold_years if purchase_path == "private" else 0.0
    registration = float(registration_cost if registration_yr is None else registration_yr) / hold_years
    inspection = float(inspection_yr) if inspection_due else 0.0
    raw = {
        "depreciation": depreciation,
        "fuel": fuel,
        "service": service,
        "insurance": float(insurance_yr),
        "inspection": inspection,
        "fees": registration + pcc,
    }
    total = round(sum(raw.values()))
    items = [{"key": key, "label": label, "pln": round(raw[key])} for key, label in COMPONENT_ORDER]
    shares = {key: round(100 * value / total, 2) if total else 0 for key, value in raw.items()}
    if total:
        shares["fees"] += round(100 - sum(shares.values()), 2)
    band = service * service_band
    return {
        "ok": True,
        "paid": round(paid),
        "value_end": round(later * scale),
        "age": age,
        "hold_years": hold_years,
        "annual_km": annual_km,
        "items": items,
        "shares": shares,
        "total": total,
        "total_lo": round(total - band),
        "total_hi": round(total + band),
        "lifetime": round(total * hold_years),
        "per_km": round(total / annual_km, 2) if annual_km else 0,
        "depr_share": round(shares["depreciation"]),
    }


STRINGS = {
    "en": {
        "title": "Vehicle cost calculator",
        "intro": "Estimate the yearly cost of owning a used vehicle. Choose a vehicle, set a few basic assumptions, and adjust the prices if you know them.",
        "calculator": "calculator",
        "vehicle_type": "Vehicle type",
        "car": "car",
        "motorcycle": "motorcycle",
        "vehicle": "Vehicle model",
        "make": "Vehicle make",
        "loading": "Loading vehicles…",
        "model_search": "Search models",
        "model_filter": "Filter motorcycle models",
        "category": "Category",
        "any_category": "Any category",
        "no_matches": "No matching models",
        "more_matches": "Showing {shown} of {total} — type to narrow",
        "listings": "listings",
        "reset_filter": "Reset filter",
        "variant_required": "Variant required",
        "variant_warning": "Choose an exact variant; engine size and licence class affect running costs.",
        "alias_notice": "Similar listing names are grouped.",
        "curve_coverage": "Model data: ages {min}–{max}, {samples} listings",
        "curve_basis": "Curve",
        "curve_category": "Uses the {category} category trend",
        "curve_sparse": "Few model age groups; treat the trend as approximate",
        "curve_interpolated": "Missing ages are estimated between observed ages",
        "curve_uncertain": "The model trend is less certain",
        "observed_ages": "observed ages",
        "interpolated_gap": "interpolated data gap",
        "interpolated_value": "interpolated across a data gap",
        "age": "Vehicle age at purchase",
        "sell": "Vehicle age when sold",
        "buy_value": "Buy",
        "sell_value": "Sell",
        "at_age": "at age",
        "distance": "Distance driven per year",
        "km_year": "km / year",
        "adjust": "Costs and purchase details",
        "fuel_type": "Fuel type",
        "price": "Purchase price (zł)",
        "price_hint": "Blank uses the typical value from the market curve.",
        "insurance": "Insurance per year (zł)",
        "insurance_hint": "Blank uses a broad vehicle estimate.",
        "fuel": "Fuel price (zł / litre)",
        "service": "Service and repairs (zł / 1,000 km)",
        "purchase": "Purchase route",
        "dealer": "Dealer",
        "private": "Private seller",
        "market": "PCC market-value basis (zł)",
        "registration": "Registration, one-time (zł)",
        "registration_hint": "Blank uses the standard 160 zł.",
        "inspection": "Technical inspection per year (zł)",
        "pcc": "Include PCC at 2%",
        "result": "Estimated yearly cost",
        "year": "zł / year",
        "cost_year": "Cost per year",
        "total": "Total",
        "depreciation": "Depreciation",
        "fuel_cost": "Fuel",
        "service_label": "Service and repairs",
        "insurance_cost": "Insurance",
        "inspection_label": "Inspection",
        "fees": "Purchase fees",
        "chart": "Estimated value over time",
        "no_curve": "No aggregate curve is available for this vehicle.",
        "includes_heading": "What is included",
        "includes": "Value loss, fuel, service and wear, insurance, inspection, and purchase fees.",
        "method_heading": "About the estimate",
        "method_text": "Value loss follows aggregated asking-price curves. Running costs are typical assumptions and can be changed above. An asking price is not a completed sale price.",
        "source": "Fuel data",
        "stale": "Older than 14 days; check a current price before relying on it.",
        "fresh": "Checked within the last 14 days.",
    },
    "pl": {
        "title": "Kalkulator kosztów pojazdu",
        "intro": "Oszacuj roczny koszt posiadania używanego pojazdu. Wybierz pojazd, ustaw podstawowe założenia i zmień ceny, jeśli je znasz.",
        "calculator": "kalkulator",
        "vehicle_type": "Rodzaj pojazdu",
        "car": "samochód",
        "motorcycle": "motocykl",
        "vehicle": "Model pojazdu",
        "make": "Marka pojazdu",
        "loading": "Ładowanie pojazdów…",
        "model_search": "Szukaj modelu",
        "model_filter": "Filtruj modele motocykli",
        "category": "Kategoria",
        "any_category": "Wszystkie kategorie",
        "no_matches": "Brak pasujących modeli",
        "more_matches": "Wyświetlono {shown} z {total} — wpisz więcej, aby zawęzić",
        "listings": "ogłoszeń",
        "reset_filter": "Wyczyść filtr",
        "variant_required": "Wymagany dokładny wariant",
        "variant_warning": "Wybierz dokładny wariant; pojemność i kategoria prawa jazdy wpływają na koszty.",
        "alias_notice": "Podobne nazwy w ogłoszeniach są grupowane.",
        "curve_coverage": "Dane modelu: wiek {min}–{max}, {samples} ogłoszeń",
        "curve_basis": "Krzywa",
        "curve_category": "Korzysta z trendu kategorii {category}",
        "curve_sparse": "Mało grup wiekowych modelu; trend jest orientacyjny",
        "curve_interpolated": "Brakujące roczniki są szacowane między obserwacjami",
        "curve_uncertain": "Trend modelu jest mniej pewny",
        "observed_ages": "obserwowane roczniki",
        "interpolated_gap": "interpolowana luka w danych",
        "interpolated_value": "interpolacja przez lukę w danych",
        "age": "Wiek pojazdu przy zakupie",
        "sell": "Wiek pojazdu przy sprzedaży",
        "buy_value": "Kupno",
        "sell_value": "Sprzedaż",
        "at_age": "w wieku",
        "distance": "Roczny przebieg",
        "km_year": "km / rok",
        "adjust": "Koszty i szczegóły zakupu",
        "fuel_type": "Rodzaj paliwa",
        "price": "Cena zakupu (zł)",
        "price_hint": "Puste pole używa typowej wartości z krzywej rynkowej.",
        "insurance": "Ubezpieczenie roczne (zł)",
        "insurance_hint": "Puste pole używa ogólnego szacunku dla pojazdu.",
        "fuel": "Cena paliwa (zł / litr)",
        "service": "Serwis i naprawy (zł / 1000 km)",
        "purchase": "Sposób zakupu",
        "dealer": "Dealer",
        "private": "Sprzedawca prywatny",
        "market": "Wartość rynkowa do PCC (zł)",
        "registration": "Rejestracja, jednorazowo (zł)",
        "registration_hint": "Puste pole używa standardowej kwoty 160 zł.",
        "inspection": "Badanie techniczne rocznie (zł)",
        "pcc": "Uwzględnij PCC 2%",
        "result": "Szacowany koszt roczny",
        "year": "zł / rok",
        "cost_year": "Koszt roczny",
        "total": "Razem",
        "depreciation": "Utrata wartości",
        "fuel_cost": "Paliwo",
        "service_label": "Serwis i naprawy",
        "insurance_cost": "Ubezpieczenie",
        "inspection_label": "Badanie",
        "fees": "Opłaty zakupu",
        "chart": "Szacowana wartość w czasie",
        "no_curve": "Brak zagregowanej krzywej dla tego pojazdu.",
        "includes_heading": "Co obejmuje szacunek",
        "includes": "Utratę wartości, paliwo, serwis i zużycie, ubezpieczenie, badanie oraz opłaty przy zakupie.",
        "method_heading": "O szacunku",
        "method_text": "Utrata wartości korzysta z zagregowanych krzywych cen ofertowych. Koszty bieżące są typowymi założeniami i można je zmienić powyżej. Cena ofertowa nie jest ceną zawartej transakcji.",
        "source": "Dane o paliwie",
        "stale": "Dane mają ponad 14 dni; przed użyciem sprawdź aktualną cenę.",
        "fresh": "Dane sprawdzono w ciągu ostatnich 14 dni.",
    },
}


def _client_config(fuel):
    labels_pl = {
        "moped": "Motorower ≤50",
        "scooter": "Skuter",
        "maxi_scooter": "Maxiskuter",
        "naked": "Naked / roadster",
        "sport": "Sportowy",
        "sport_touring": "Sportowo-turystyczny",
        "touring": "Turystyczny / GT",
        "adventure": "Adventure",
        "adventure_touring": "Adventure-touring",
        "cruiser": "Cruiser",
        "enduro": "Enduro / terenowy",
        "motocross": "Motocross",
        "atv_other": "Quad / inne",
        "mixed": "Wymaga wariantu",
    }
    return {
        "categories": CATEGORY_DEFAULTS,
        "categoryOrder": CATEGORY_ORDER,
        "categoryLabels": {"en": {k: v["label"] for k, v in CATEGORY_DEFAULTS.items()}, "pl": labels_pl},
        "carFuel": CAR_FUEL_DEFAULTS,
        "carFuelLabels": {
            "en": {k: v["label"] for k, v in CAR_FUEL_DEFAULTS.items()},
            "pl": {"petrol": "Benzyna", "diesel": "Diesel", "lpg": "LPG", "hybrid": "Hybryda"},
        },
        "carService": CAR_SERVICE_PER1000,
        "carInsurance": CAR_INSURANCE_YR,
        "pccRate": PCC_RATE,
        "registration": REGISTRATION_PLN,
        "inspectionMoto": INSPECTION_MOTO_PLN,
        "inspectionCar": INSPECTION_CAR_PLN,
        "serviceAgeK": SERVICE_AGE_K,
        "serviceBand": SERVICE_BAND,
        "fuel": fuel,
        "components": COMPONENT_ORDER,
    }


def render_tco(
    aggregates_path=None, *, car_aggregates_path=None, fuel_path=DEFAULT_FUEL, output_dir=None, filename="index.html"
):
    output_dir = output_dir or DEFAULT_OUTPUT_DIR
    aggregates_path = aggregates_path or DEFAULT_AGGREGATES
    os.makedirs(output_dir, exist_ok=True)
    if os.path.exists(aggregates_path):
        with open(aggregates_path, encoding="utf-8") as f:
            agg = json.load(f)
    else:
        logger.warning("%s missing; rendering without aggregate curves", aggregates_path)
        agg = {"meta": {}, "categories": {}, "models": {}, "classes": {}}
    car_path = car_aggregates_path or DEFAULT_CAR_AGGREGATES
    if os.path.exists(car_path):
        with open(car_path, encoding="utf-8") as f:
            car = json.load(f)
    else:
        car = {"meta": {}, "models": {}}
    if os.path.exists(fuel_path):
        with open(fuel_path, encoding="utf-8") as f:
            fuel = json.load(f)
    else:
        fuel = {"prices": {}, "stale": True}
    if fuel.get("prices"):
        validate_fuel_snapshot(fuel)
    fuel["stale"] = fuel_is_stale(fuel)
    with open(os.path.join(output_dir, CARS_SIDECAR), "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in car.items() if k != "fuels"}, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(output_dir, FUEL_SIDECAR), "w", encoding="utf-8") as f:
        json.dump(fuel, f, ensure_ascii=False, separators=(",", ":"))
    body = """
<p class="intro" data-i18n="intro">Estimate the yearly cost of owning a used vehicle. Choose a vehicle, set a few basic assumptions, and adjust the prices if you know them.</p>
<section class="section" id="calculator"><h2 class="section-title" data-i18n="calculator">calculator</h2><div class="calculator">
<form class="form" onsubmit="return false">
<div class="field"><span class="kind-label" data-i18n="vehicle_type">Vehicle type</span><div class="kind-options" role="group" aria-label="Vehicle type" data-i18n-aria-label="vehicle_type"><button type="button" data-veh="car" aria-pressed="true" data-i18n="car">car</button><button type="button" data-veh="moto" aria-pressed="false" data-i18n="motorcycle">motorcycle</button></div></div>
<div class="field" id="carMakeField"><label for="carMake" data-i18n="make">Vehicle make</label><span class="select-control"><select id="carMake"></select></span></div>
<div class="field" id="profileField"><label for="profileSearch" data-i18n="vehicle">Vehicle model</label><div class="model-picker"><input id="profileSearch" type="search" role="combobox" aria-autocomplete="list" aria-controls="profileResults" aria-expanded="false" aria-describedby="modelMeta" autocomplete="off" placeholder="Search models" data-i18n-placeholder="model_search"><div id="profileResults" class="profile-results" role="listbox" hidden></div></div><p class="model-meta" id="modelMeta" aria-live="polite"></p>
<details class="filter-panel" id="modelFilters" hidden><summary data-i18n="model_filter">Filter motorcycle models</summary><div class="filter-fields"><div class="field"><label for="categoryFilter" data-i18n="category">Category</label><span class="select-control"><select id="categoryFilter"></select></span></div><button class="filter-reset" id="resetModelFilter" type="button" data-i18n="reset_filter">Reset filter</button></div></details></div>
<div class="field"><label for="age" data-i18n="age">Vehicle age at purchase</label><div class="range-line"><input class="exact" id="ageNumber" type="number" min="0" max="18" step="1" value="5" aria-label="Vehicle age at purchase" data-i18n-aria-label="age"><span id="ageUnit">years old</span></div><input id="age" type="range" min="0" max="18" step="1" value="5" aria-label="Vehicle age at purchase" data-i18n-aria-label="age"></div>
<div class="field"><label for="sell" data-i18n="sell">Vehicle age when sold</label><div class="range-line"><input class="exact" id="sellNumber" type="number" min="2" max="19" step="1" value="8" aria-label="Vehicle age when sold" data-i18n-aria-label="sell"><span id="sellUnit">years old</span></div><input id="sell" type="range" min="2" max="19" step="1" value="8" aria-label="Vehicle age when sold" data-i18n-aria-label="sell"></div>
<div class="field"><label for="km" data-i18n="distance">Distance driven per year</label><div class="range-line"><input class="exact" id="kmNumber" type="number" min="1000" max="50000" step="100" value="8000" aria-label="Distance driven per year" data-i18n-aria-label="distance"><span data-i18n="km_year">km / year</span></div><input id="km" type="range" min="1000" max="50000" step="100" value="8000" aria-label="Distance driven per year" data-i18n-aria-label="distance"></div>
<details class="adjust"><summary data-i18n="adjust">Costs and purchase details</summary><div class="advanced-fields">
<div class="field" id="fuelTypeField"><label for="fuelType" data-i18n="fuel_type">Fuel type</label><span class="select-control"><select id="fuelType"></select></span></div>
<div class="field"><label for="price" data-i18n="price">Purchase price (zł)</label><input id="price" type="number" min="0" step="100"><span class="hint" data-i18n="price_hint">Blank uses the typical value from the market curve.</span></div>
<div class="field"><label for="ins" data-i18n="insurance">Insurance per year (zł)</label><input id="ins" type="number" min="0" step="50"><span class="hint" data-i18n="insurance_hint">Blank uses a broad vehicle estimate.</span></div>
<div class="field"><label for="pump" data-i18n="fuel">Fuel price (zł / litre)</label><input id="pump" type="number" min="0" step=".01"><span class="hint" id="fuelnote"></span></div>
<div class="field"><label for="svc" data-i18n="service">Service and repairs (zł / 1,000 km)</label><input id="svc" type="number" min="0" step="5"></div>
<fieldset class="field"><legend data-i18n="purchase">Purchase route</legend><div class="purchase-options"><button type="button" data-route="dealer" aria-pressed="true" data-i18n="dealer">dealer</button><button type="button" data-route="private" aria-pressed="false" data-i18n="private">private</button></div></fieldset>
<div class="field"><label for="market" data-i18n="market">PCC market-value basis (zł)</label><input id="market" type="number" min="0" step="100" disabled></div>
<div class="field"><label for="registration" data-i18n="registration">Registration, one-time (zł)</label><input id="registration" type="number" min="0" value="160" step="1"><span class="hint" data-i18n="registration_hint">Blank uses the standard 160 zł.</span></div>
<div class="field"><label for="inspection" data-i18n="inspection">Technical inspection per year (zł)</label><input id="inspection" type="number" min="0" step="1"></div>
<label class="field check"><input id="pcc" type="checkbox" disabled><span data-i18n="pcc">Include PCC at 2%</span></label>
</div></details></form>
<section class="result" aria-live="polite"><div class="result-heading" data-i18n="result">Estimated yearly cost</div><div class="result-number"><span id="annual">—</span><small data-i18n="year">zł / year</small></div><p class="result-summary" id="summary">—</p><div class="breakdown-heading"><span data-i18n="cost_year">Cost per year</span><span>zł</span></div><div id="rows"></div></section>
</div></section>
<section class="curve"><h2 data-i18n="chart">Estimated value over time</h2><div class="curve-wrap" id="chart"></div><div class="chart-key"><span><i class="key-dot"></i><span data-i18n="observed_ages">observed ages</span></span><span class="key-gap"><i class="key-dash"></i><span data-i18n="interpolated_gap">interpolated data gap</span></span></div><div class="curve-note"><span id="chartStart">—</span><b id="chartLoss">—</b><span id="chartEnd">—</span></div></section>
<section class="details"><div class="details-grid"><div><h2 data-i18n="includes_heading">What is included</h2><p data-i18n="includes">Value loss, fuel, service and wear, insurance, inspection, and purchase fees.</p></div><div><h2 data-i18n="method_heading">About the estimate</h2><p data-i18n="method_text">Value loss follows aggregated asking-price curves. Running costs are typical assumptions and can be changed above. An asking price is not a completed sale price.</p></div></div></section>"""
    foot = ""
    script = f"const CFG = {json.dumps(_client_config(fuel), ensure_ascii=False)};\nconst AGG_MOTO = {json.dumps(agg, ensure_ascii=False)};\nconst AGG_CAR = {json.dumps(car, ensure_ascii=False)};\nconst T = {json.dumps(STRINGS, ensure_ascii=False)};\n{ui.asset('tco.js')}"
    return _write_page(
        ui.page_shell(
            title=STRINGS["en"]["title"],
            description=STRINGS["en"]["intro"],
            body=body,
            foot=foot,
            script=script,
            page_id="tco",
        ),
        output_dir,
        filename,
    )


def _write_page(content, output_dir, filename):
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
