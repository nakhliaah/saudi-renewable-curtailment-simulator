from surplusflex.model import Scenario, compare_strategies, run_simulation
from surplusflex.saudi_data import load_project_catalog


def test_energy_and_limits():
    result = run_simulation(Scenario())
    assert result["metrics"]["curtailment_mwh"] >= -1e-5
    assert result["metrics"]["renewable_utilization_pct"] <= 100.0001
    assert result["metrics"]["max_line_loading_pct"] <= 100.0001
    assert abs(result["hourly"]["Flexible load (MW)"].sum() - 720) < 1e-4
    assert abs(result["hourly"]["Battery SOC (MWh)"].iloc[-1] - 300) < 1e-4


def test_combined_not_worse_than_no_intervention():
    comparison = compare_strategies(Scenario())
    curtailment = comparison.set_index("Strategy")["Curtailment (MWh)"]
    assert curtailment["Combined optimization"] <= curtailment["No intervention"] + 1e-5


def test_official_catalog_totals_and_wind_normalization():
    catalog = load_project_catalog()
    assert len(catalog) == 15
    assert abs(catalog["Capacity MW"].sum() - 12313) < 1e-6
    dumat = catalog.set_index("Project").loc["Dumat Al-Jandal"]
    assert dumat["Technology"] == "Wind"

