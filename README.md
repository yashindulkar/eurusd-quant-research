# EUR/USD Quantitative Behavioural Research

This repository is a reproducible foundation for studying recurring EUR/USD
market behaviour in M15 data from approximately 2010–2026. It preserves source
lineage and separates immutable inputs, reusable transformations, research
definitions, tests, and generated evidence.

This is a behavioural research project. It is **not** a trading strategy,
execution system, parameter-optimisation framework, dashboard, or machine
learning project. Behavioural conclusions appear only in completed,
preregistered study reports with their lineage, uncertainty, and limitations.

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
reports/coverage/        Reproducible eligibility metadata and profile counts
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
make audit-raw-data       # read-only registered raw-data quality audit
make generate-coverage    # Task 02-backed research eligibility metadata
make prepare-task04-v28-integrity
make prepare-task04-v28-registration
make validate-task04-preregistration  # Phase A; no v2.8 results
make create-task04-registration-receipt  # Phase B, after anchor commit
make validate-task04-registration-receipt
make generate-task04-candidate  # Phase B candidate generation; never completion
make reconcile-task04-v28       # establish and verify candidate byte identity
```

`make audit-raw-data` verifies the registered identity, loads the CSV once for
the main calculations, performs schema, timestamp, cadence, OHLC, precision,
count-field, source, coverage, weekly-boundary, and discontinuity diagnostics,
then writes the computed JSON, Markdown, and diagnostic CSVs under
`reports/audits/`. The command returns exit code 1 only for fatal identity,
mandatory-schema, timestamp, duplicate-primary-key, OHLC, unreadable-file, or
raw-mutation findings. Warnings and `CONDITIONALLY_READY` findings return 0.

The audit does not clean, interpolate, sort, exclude, or rewrite raw
observations. Its gap and calendar summaries are coverage diagnostics only.

The JSON manifest at `reports/audits/raw_dataset_manifest.json` is the
authoritative immutable identity record. The audit fatally reconciles its
logical identifier, version, relative path, SHA-256, size, row count, schema,
and timestamp bounds against configuration expectations and the actual file.
Re-registering identical identity leaves manifest bytes unchanged.

Absent grid timestamps are allocated to the UTC year and month in which each
timestamp physically falls. Coverage tables separately report gaps beginning,
ending, and touching each period. A boundary month is the first or last
observed month; a sparse month is below 75% of its within-year monthly
bar-count median; a continuity-impaired month has at least 10 non-weekend
intraday gaps touching it. These flags are independent and may overlap.

The configured weekly threshold is 1,440 minutes. Gaps outside that rule are
described neutrally as `long_nonweekly_gap`, `non_weekend_intraday`, or
`unclassified`; no holiday cause is assigned. Count-field relationship subsets
use immediate weekly endpoints, immediate endpoints of gaps at least 720
minutes, observations on continuity-impaired UTC dates, and computed recurring
anomaly bounds, each with an explicit comparator.

Analytical JSON content, warning/failure order, CSV row order, and Markdown are
deterministic. Execution timestamp, elapsed time, and raw modification time are
documented volatile JSON fields; serialized paths are repository-relative.
Exit code 1 is reserved for fatal validation failures; warnings and conditional
readiness return 0.

## Research coverage and eligibility

`make generate-coverage` consumes the registered Task 02 audit JSON,
`timestamp_gaps.csv`, and `monthly_coverage.csv`. It verifies their lineage,
reads only raw timestamps, and builds descriptive masks at row, UTC-date,
UTC-month, UTC-year, and dataset levels. It does not repeat the audit's gap,
schema, timestamp, duplicate, or OHLC rules.

Coverage warnings remain included under `DEFAULT_RESEARCH`. The
`STRICT_CONTINUITY` profile applies a reversible exclusion mask, while
`SENSITIVITY_FULL` and `SENSITIVITY_2023` expose comparison populations.
`FULL_DATASET` always preserves the registered population. Profile definitions
are validated from `configs/coverage.yaml`.

The bounded outputs under `reports/coverage/` contain deterministic flag and
profile counts. The package API builds the full masks on demand; no row is
deleted and no row-level copy of the raw dataset is written.

## Daily range by UTC weekday

Task 04 remains a correctively registered replication of the reviewed
development analysis. Version 2.2 is retained as historical control evidence;
the corrected pre-anchor design is version 2.8 at
`studies/task04_daily_range_weekday.v2.8.yaml`, method
`RANGE-WEEKDAY-001`. It asks whether the distribution of unrounded EUR/USD
daily high-low range in pips differs across Monday-Friday UTC calendar dates.

The primary analysis uses complete `DEFAULT_RESEARCH` dates. Task 03 profile
masks are applied to M15 rows before each profile is aggregated; the study does
not recreate audit or coverage classifications. Monday-Thursday completeness
requires the full UTC M15 grid. Friday completeness ends at the applicable
audited RAW-DQ-001 weekly-boundary endpoint rather than assuming 96 candles or
a fixed UTC market close.

Kruskal-Wallis is the primary omnibus test. Dunn pairwise comparisons use Holm
correction; one-way and Welch ANOVA are complementary. The outputs include
effect sizes, deterministic bootstrap intervals, chronological and yearly
stability, past-only volatility regimes, coverage-profile comparisons, and
reversible extreme-event sensitivities under
`reports/research/task04_daily_range_weekday_v2.8/` only after the separately
authorized anchor commit. The existing unversioned directory remains
historical v2.2 output.

Versions 2.4, 2.5, and 2.6 are abandoned registered attempts. v2.6 reached
receipt, candidate generation, all twelve reconciliation components,
deterministic regeneration, and figure validation, but its quality gate exposed
an integration test that incorrectly required receipt absence after legitimate
receipt creation. No v2.6 output was promoted and no lifecycle was completed.
Version 2.7 separates lifecycle-state tests and Task 03 scientific/stable/context
identity layers, but stopped when a one-byte post-validation figure mutation was
not compared with a prior trusted candidate identity. Version 2.8 binds a
write-once validated candidate identity to reconciliation, promotion, and
lifecycle completion. The earlier v2.5 attempt had stopped on three false comparison
mismatches involving empty strings, regime-lineage projection, and nested
figure paths. Historical estimates remain regression controls, not v2.8 evidence.

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

Repository infrastructure, registration, RAW-DQ-001, COVERAGE-001, and the
registered-replication RANGE-WEEKDAY-001 study are established. All 406,945 rows are
structurally eligible under `DEFAULT_RESEARCH`; coverage limitations remain
explicit and 46,468 rows carry at least one sensitivity condition.

## Next planned task

Design a separately preregistered follow-up that tests one bounded mechanism or
external calendar explanation. Do not convert Task 04 into a trading strategy
or extend its locked hypotheses retrospectively.
