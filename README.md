# EUR/USD Quantitative Behavioural Research

This repository is a reproducible foundation for studying recurring EUR/USD
market behaviour in M15 data from approximately 2010–2026. It preserves source
lineage and separates immutable inputs, reusable transformations, research
definitions, tests, and generated evidence.

This is a behavioural research project. It is **not** a trading strategy,
execution system, parameter-optimisation framework, dashboard, or machine
learning project. No market-behaviour conclusions are included at this stage.

## Repository layout

```text
configs/                 Validated project, data, and session placeholders
data/raw/                Immutable source files (excluded from Git)
data/interim/            Rebuildable intermediate data (excluded from Git)
data/processed/          Rebuildable research-ready data (excluded from Git)
data/external/           Documented third-party supporting data
docs/                    Principles, dictionary, registry, and decision log
notebooks/               Thin, reproducible research interfaces
reports/figures/         Generated figures
reports/tables/          Generated tables
reports/audits/          Machine-readable lineage and audit records
scripts/                 Operational entry points
src/eurusd_research/     Reusable Python package
tests/                   Unit and integration tests
```

## Environment setup

Python 3.11–3.13 is supported; Python 3.12 is recommended.

```bash
make setup
source .venv/bin/activate
make validate-environment
```

`make setup` creates `.venv` with `python3.12` by default. Override it with
`PYTHON_BOOTSTRAP=/path/to/python make setup`.

Dependencies are declared once in `pyproject.toml`. Runtime dependencies support
tabular storage and statistics planned for later research; development
dependencies provide tests, coverage, formatting, linting, and type checking.

## Register the dataset

Place (or safely copy) the original file at
`data/raw/EURUSD_M15_UTC.csv`, then run:

```bash
make register-data
```

Registration streams the file, calculates SHA-256, counts data rows, captures
the header and timestamp bounds, and writes
`reports/audits/raw_dataset_manifest.json`. It does not rewrite the CSV.

Raw files are immutable inputs:

- never edit, sort, clean, truncate, or overwrite them;
- never silently substitute a file with the same name;
- verify the checksum before and after any operation involving raw data;
- keep raw CSV files out of Git (the manifest is designed to be versioned);
- create derived data only under `data/interim` or `data/processed`.

## Development commands

```bash
make format               # apply Ruff formatting
make lint                 # Ruff lint and format checks
make typecheck            # mypy
make test-unit            # unit tests
make test-integration     # integration tests
make test                 # all tests with coverage thresholds
make check                # lint, typecheck, tests, and environment validation
```

## Research workflow

1. Register and verify immutable source data.
2. Define a method in `docs/methodology_registry.md` before examining results.
3. Implement reusable, tested transformations in `src/eurusd_research`.
4. Write derived artifacts outside `data/raw`; document every exclusion.
5. Validate timezone, daylight-saving, leakage, and sample-boundary behaviour.
6. Generate auditable tables and figures from code.
7. Record material decisions and limitations.

Notebooks must remain thin: reusable logic belongs in the package, and notebook
outputs must be reproducible from registered inputs and versioned definitions.

## Current status

Repository infrastructure, configuration, registration, documentation, and test
scaffolding are established. Dataset registration records identity and basic
file metadata only. No complete data-quality audit or behavioural analysis has
been performed.

## Next planned task

Implement a read-only dataset-quality audit covering types, OHLC invariants,
timestamp parsing and ordering, duplicate timestamps, cadence gaps, nulls,
source values, numeric validity, and coverage summaries. The audit must report
issues without cleaning, interpolating, or removing observations.
