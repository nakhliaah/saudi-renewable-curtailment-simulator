"""Official Saudi renewable-project catalogue and modeled grid mappings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .case_data import SOLAR_FACTOR, WIND_FACTOR_1, WIND_FACTOR_2


OFFICIAL_CATALOG = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "official"
    / "saudi_renewable_projects_2025.csv"
)
OFFICIAL_URL = "https://www.stats.gov.sa/en/d/renewable-energy-statistics-2025-en-xlsx"

# These are explicitly modeled proxy mappings, not Saudi grid connection data.
REGION_PROXY_BUSES = {
    "Al-Jouf": [5, 7],
    "Makkah": [8, 9, 10, 14],
    "Madinah": [13, 14],
    "Qassim": [15, 16],
    "Hail": [18],
    "Riyadh": [21, 22, 23, 24, 15],
}


@lru_cache(maxsize=1)
def load_project_catalog() -> pd.DataFrame:
    """Load the compact extract derived from the official GASTAT workbook."""
    if not OFFICIAL_CATALOG.exists():
        raise FileNotFoundError(f"Official project catalog not found: {OFFICIAL_CATALOG}")

    catalog = pd.read_csv(OFFICIAL_CATALOG)
    catalog["Operation year"] = catalog["Operation year"].astype(int)
    catalog["Capacity MW"] = catalog["Capacity MW"].astype(float)
    catalog["Proxy bus"] = catalog["Proxy bus"].astype(int)
    return catalog.reset_index(drop=True)


def build_portfolio_plants(
    selected_projects: tuple[str, ...] = (),
    portfolio_year: int = 2025,
    network_scale: float = 0.25,
    solar_weather: float = 1.0,
    wind_weather: float = 1.0,
) -> tuple[list[dict], pd.DataFrame]:
    """Convert official projects into proxy-network renewable plants."""
    catalog = load_project_catalog()
    if selected_projects:
        chosen = catalog[catalog["Project"].isin(selected_projects)].copy()
    else:
        chosen = catalog[catalog["Operation year"] <= portfolio_year].copy()
    wind_profile = (WIND_FACTOR_1 + WIND_FACTOR_2) / 2
    plants = []
    for _, project in chosen.iterrows():
        is_wind = project["Technology"].lower() == "wind"
        profile = wind_profile * wind_weather if is_wind else SOLAR_FACTOR * solar_weather
        plants.append({
            "name": project["Project"], "bus": int(project["Proxy bus"]),
            "kind": project["Technology"],
            "official_capacity_mw": float(project["Capacity MW"]),
            "available": np.maximum(0, float(project["Capacity MW"]) * network_scale * profile),
        })
    return plants, chosen


def portfolio_summary(catalog: pd.DataFrame) -> dict:
    return {
        "projects": int(len(catalog)),
        "capacity_mw": float(catalog["Capacity MW"].sum()),
        "investment_sar_bn": float(catalog["Investment SAR bn"].sum()),
        "households": int(catalog["Estimated households"].sum()),
        "solar_mw": float(catalog.loc[catalog["Technology"] == "Solar", "Capacity MW"].sum()),
        "wind_mw": float(catalog.loc[catalog["Technology"] == "Wind", "Capacity MW"].sum()),
    }

