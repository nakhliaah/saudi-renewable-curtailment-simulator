"""Linear, network-aware renewable-surplus optimization model."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from .case_data import BUSES, DEMAND, DEMAND_SHARES, GENERATORS, LINES
from .saudi_data import build_portfolio_plants


@dataclass(frozen=True)
class Scenario:
    solar_scale: float = 1.0
    wind_scale: float = 1.0
    demand_scale: float = 1.0
    portfolio_year: int = 2025
    selected_projects: tuple[str, ...] = ()
    network_scale: float = 0.25
    operating_day: str = "Spring solar surplus"
    battery_power_mw: float = 150.0
    battery_energy_mwh: float = 600.0
    flexible_power_mw: float = 120.0
    flexible_energy_mwh: float = 720.0
    flexible_bus: int = 15
    strategy: str = "Combined optimization"


class Index:
    def __init__(self, sizes):
        self.slices = {}
        start = 0
        for name, size in sizes:
            self.slices[name] = slice(start, start + size)
            start += size
        self.n = start

    def one(self, name, *coords, shape):
        return self.slices[name].start + np.ravel_multi_index(coords, shape)


def run_simulation(scenario: Scenario) -> dict:
    hours, buses = 24, len(BUSES)
    plants, portfolio = build_portfolio_plants(
        selected_projects=scenario.selected_projects,
        portfolio_year=scenario.portfolio_year,
        network_scale=scenario.network_scale,
        solar_weather=scenario.solar_scale,
        wind_weather=scenario.wind_scale,
    )
    ng, nr, nl = len(GENERATORS), len(plants), len(LINES)
    idx = Index([
        ("gen", ng * hours), ("ren", nr * hours), ("flow", nl * hours),
        ("theta", buses * hours), ("charge", hours), ("discharge", hours),
        ("soc", hours), ("flex", hours),
    ])

    use_battery = scenario.strategy in {"Battery only", "Combined optimization"}
    optimize_flex = scenario.strategy in {"Flexible load only", "Combined optimization"}
    demand = DEMAND * scenario.demand_scale
    fixed_flex = np.full(hours, scenario.flexible_energy_mwh / hours)
    fixed_flex = np.minimum(fixed_flex, scenario.flexible_power_mw)

    c = np.zeros(idx.n)
    bounds = [(None, None)] * idx.n

    for g, (_, _, pmax, cost) in enumerate(GENERATORS):
        for t in range(hours):
            k = idx.one("gen", g, t, shape=(ng, hours))
            c[k], bounds[k] = cost, (0, pmax)
    for r, plant in enumerate(plants):
        for t in range(hours):
            k = idx.one("ren", r, t, shape=(nr, hours))
            # Negative value rewards useful renewable dispatch and is
            # equivalent to penalizing curtailment by $8/MWh.
            c[k], bounds[k] = -8.0, (0, float(plant["available"][t]))
    for l, (_, _, _, _, cap) in enumerate(LINES):
        for t in range(hours):
            bounds[idx.one("flow", l, t, shape=(nl, hours))] = (-cap, cap)
    for b in range(buses):
        for t in range(hours):
            bounds[idx.one("theta", b, t, shape=(buses, hours))] = (-np.pi, np.pi)
    for t in range(hours):
        c[idx.slices["charge"].start + t] = 0.5
        c[idx.slices["discharge"].start + t] = 0.5
        bounds[idx.slices["charge"].start + t] = (0, scenario.battery_power_mw if use_battery else 0)
        bounds[idx.slices["discharge"].start + t] = (0, scenario.battery_power_mw if use_battery else 0)
        bounds[idx.slices["soc"].start + t] = (0, scenario.battery_energy_mwh if use_battery else 0)
        if optimize_flex:
            bounds[idx.slices["flex"].start + t] = (0, scenario.flexible_power_mw)
        else:
            bounds[idx.slices["flex"].start + t] = (fixed_flex[t], fixed_flex[t])

    aeq, beq = [], []
    # DC line-flow equations. Matches the shared model's 250/X base.
    for l, (_, from_bus, to_bus, x, _) in enumerate(LINES):
        for t in range(hours):
            row = np.zeros(idx.n)
            row[idx.one("flow", l, t, shape=(nl, hours))] = 1
            row[idx.one("theta", from_bus - 1, t, shape=(buses, hours))] = -250 / x
            row[idx.one("theta", to_bus - 1, t, shape=(buses, hours))] = 250 / x
            aeq.append(row); beq.append(0)

    # Nodal balance.
    battery_bus = 21
    for b in BUSES:
        for t in range(hours):
            row = np.zeros(idx.n)
            for g, (_, gen_bus, _, _) in enumerate(GENERATORS):
                if gen_bus == b:
                    row[idx.one("gen", g, t, shape=(ng, hours))] += 1
            for r, plant in enumerate(plants):
                if plant["bus"] == b:
                    row[idx.one("ren", r, t, shape=(nr, hours))] += 1
            for l, (_, from_bus, to_bus, _, _) in enumerate(LINES):
                if from_bus == b:
                    row[idx.one("flow", l, t, shape=(nl, hours))] -= 1
                if to_bus == b:
                    row[idx.one("flow", l, t, shape=(nl, hours))] += 1
            if b == battery_bus:
                row[idx.slices["discharge"].start + t] += 1
                row[idx.slices["charge"].start + t] -= 1
            if b == scenario.flexible_bus:
                row[idx.slices["flex"].start + t] -= 1
            aeq.append(row)
            beq.append(demand[t] * DEMAND_SHARES.get(b, 0.0))

    # Reference angle.
    for t in range(hours):
        row = np.zeros(idx.n)
        row[idx.one("theta", 0, t, shape=(buses, hours))] = 1
        aeq.append(row); beq.append(0)

    # Battery state of charge and end-of-day neutrality.
    eta_c, eta_d = 0.95, 0.95
    initial_soc = scenario.battery_energy_mwh * 0.50 if use_battery else 0
    for t in range(hours):
        row = np.zeros(idx.n)
        row[idx.slices["soc"].start + t] = 1
        row[idx.slices["charge"].start + t] = -eta_c
        row[idx.slices["discharge"].start + t] = 1 / eta_d
        if t > 0:
            row[idx.slices["soc"].start + t - 1] = -1
            rhs = 0
        else:
            rhs = initial_soc
        aeq.append(row); beq.append(rhs)
    row = np.zeros(idx.n)
    row[idx.slices["soc"].stop - 1] = 1
    aeq.append(row); beq.append(initial_soc)

    # Flexible service must deliver the same total useful energy in every case.
    row = np.zeros(idx.n)
    row[idx.slices["flex"]] = 1
    aeq.append(row); beq.append(float(fixed_flex.sum()))

    started = perf_counter()
    result = linprog(c, A_eq=np.asarray(aeq), b_eq=np.asarray(beq), bounds=bounds, method="highs")
    solve_seconds = perf_counter() - started
    if not result.success:
        raise RuntimeError(f"Optimization failed: {result.message}")
    x = result.x

    gen = x[idx.slices["gen"]].reshape(ng, hours)
    ren = x[idx.slices["ren"]].reshape(nr, hours)
    flow = x[idx.slices["flow"]].reshape(nl, hours)
    charge, discharge = x[idx.slices["charge"]], x[idx.slices["discharge"]]
    soc, flex = x[idx.slices["soc"]], x[idx.slices["flex"]]
    available = np.vstack([p["available"] for p in plants])
    curtailed = available - ren

    hourly = pd.DataFrame({
        "Hour": np.arange(1, 25), "Base demand (MW)": demand,
        "Renewable available (MW)": available.sum(axis=0),
        "Renewable used (MW)": ren.sum(axis=0),
        "Curtailed (MW)": curtailed.sum(axis=0),
        "Flexible load (MW)": flex, "Battery charge (MW)": charge,
        "Battery discharge (MW)": discharge, "Battery SOC (MWh)": soc,
        "Conventional generation (MW)": gen.sum(axis=0),
    })
    line_loading = np.abs(flow) / np.array([line[4] for line in LINES])[:, None]
    renewable_available = float(available.sum())
    renewable_used = float(ren.sum())
    metrics = {
        "renewable_available_mwh": renewable_available,
        "renewable_used_mwh": renewable_used,
        "curtailment_mwh": renewable_available - renewable_used,
        "curtailment_pct": 100 * (renewable_available - renewable_used) / renewable_available,
        "renewable_utilization_pct": 100 * renewable_used / renewable_available,
        "generation_cost": float(sum(gen[g].sum() * GENERATORS[g][3] for g in range(ng))),
        "max_line_loading_pct": float(100 * line_loading.max()),
        "solve_seconds": solve_seconds,
        "solver_iterations": int(getattr(result, "nit", 0)),
    }
    curtailment_by_plant = pd.DataFrame({
        "Plant": [p["name"] for p in plants], "Type": [p["kind"] for p in plants],
        "Bus": [p["bus"] for p in plants], "Available (MWh)": available.sum(axis=1),
        "Used (MWh)": ren.sum(axis=1), "Curtailed (MWh)": curtailed.sum(axis=1),
    })
    lines = pd.DataFrame({
        "Line": [line[0] for line in LINES], "From": [line[1] for line in LINES],
        "To": [line[2] for line in LINES],
        "Peak loading (%)": 100 * line_loading.max(axis=1),
    }).sort_values("Peak loading (%)", ascending=False)
    return {"metrics": metrics, "hourly": hourly, "plants": curtailment_by_plant,
            "lines": lines, "raw_flow": flow, "scenario": scenario,
            "portfolio": portfolio}


def compare_strategies(base: Scenario) -> pd.DataFrame:
    rows = []
    for strategy in ["No intervention", "Battery only", "Flexible load only", "Combined optimization"]:
        scenario = Scenario(**{**base.__dict__, "strategy": strategy})
        result = run_simulation(scenario)
        m = result["metrics"]
        rows.append({"Strategy": strategy, "Curtailment (MWh)": m["curtailment_mwh"],
                     "Renewable utilization (%)": m["renewable_utilization_pct"],
                     "Generation cost ($)": m["generation_cost"],
                     "Peak line loading (%)": m["max_line_loading_pct"]})
    return pd.DataFrame(rows)

