# SurplusFlex prototype

SurplusFlex is a network-aware renewable-curtailment simulator built from the
electrical portion of the shared IEEE 24-bus power-gas model. It reads a compact
project-level extract from the official GASTAT Renewable Energy Statistics 2025
workbook and lets users build
portfolios from all 15 commissioned Saudi projects. Official capacities are
scaled onto a representative test network; the app never presents that proxy
mapping as the real Saudi transmission grid. The original MILP/MISOCP files
remain unchanged in the Downloads folder.

## Install and run

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Run the model checks

```bash
python -c "from tests.test_model import test_energy_and_limits, test_combined_not_worse_than_no_intervention, test_official_catalog_totals_and_wind_normalization; test_energy_and_limits(); test_combined_not_worse_than_no_intervention(); test_official_catalog_totals_and_wind_normalization(); print('Model checks passed')"
```

The prototype uses public/synthetic test-system inputs. It is intended to test
the product concept before student distribution, not to represent live Saudi
National Grid operations.

Official source: https://www.stats.gov.sa/en/d/renewable-energy-statistics-2025-en-xlsx

