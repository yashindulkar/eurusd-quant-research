# Data dictionary

## Raw dataset: `eurusd_m15_utc`

Canonical path: `data/raw/EURUSD_M15_UTC.csv`

The registration manifest is authoritative for file identity and observed
bounds. The definitions below are expected schema, not a completed quality
assessment.

| Column | Expected meaning | Expected representation |
|---|---|---|
| `timestamp_utc` | Source timestamp for the M15 record; open/close convention unresolved | ISO 8601, UTC-aware |
| `open` | First observed EUR/USD price in the bar | Positive decimal |
| `high` | Maximum observed EUR/USD price in the bar | Positive decimal |
| `low` | Minimum observed EUR/USD price in the bar | Positive decimal |
| `close` | Last observed EUR/USD price in the bar | Positive decimal |
| `volume_or_tick_count` | Source-provided count field; semantics unresolved | Non-negative integer-like value |
| `source` | Data provenance label | Non-empty string |

The price quote convention remains unresolved pending source documentation; it
is not inferred from the column values. The timestamp is not asserted to be
candle open or candle close time. `volume_or_tick_count` must not be described
as trading volume, tick volume, liquidity, participation, or market activity.
Its possible interpretation as the count of constituent M1 observations is an
evidence-supported hypothesis only until source documentation confirms it.

## Raw quality audit outputs

`make audit-raw-data` generates a bounded JSON result and Markdown report plus
detailed CSV tables under `reports/audits/`. Every artifact records or inherits
lineage to the registered raw SHA-256. `timestamp_gaps.csv` preserves every
observed interval above 15 minutes; no missing timestamp is inserted. Empty
diagnostic tables retain canonical headers.

The manifest, not duplicated configuration values, is authoritative for
registered SHA-256, size, row count, schema, and timestamp bounds. Annual and
monthly `estimated_missing_m15_timestamps_in_period` allocate every absent
grid timestamp to its physical UTC period. `gaps_beginning_in_period`,
`gaps_ending_in_period`, and `gaps_touching_period` describe gap events and are
not missing-timestamp counts.

Monthly flags are separate: `boundary_month` marks the first or final observed
month; `sparse_month` marks bar counts below 75% of the within-year median; and
`continuity_impaired_month` marks at least 10 non-weekend intraday gaps touching
the month. `partial_observed_month` is their union, and
`classification_reasons` records every applicable rule.

## Confirmed RAW-DQ-001 limitations

For registered version `sha256:b2a41310927aa9a9`, the audit confirms 1,587
intervals above 15 minutes. The conservative categories contain 855 likely
weekly-closure gaps, 22 long non-weekly gaps with unresolved cause, 681
non-weekend intraday gaps, and 29 unclassified gaps. Estimated absent
grid timestamps are descriptive: 164,846 fall inside likely weekly closures,
2,730 in long non-weekly gaps, 3,086 in non-weekend intraday
gaps, and 117 in unclassified gaps.

The 2023 concern was tested rather than assumed. The year contains 658
non-weekend intraday gaps with an estimated 2,983 absent M15 timestamps, versus
none detected under that rule in 2022 and 5 gaps/22 estimated timestamps in
2024. A recurring 75/135-minute subset contains 655 gaps and 2,956 estimated
absent timestamps from 2023-01-27T10:45:00Z through
2023-07-28T20:00:00Z. This is a continuity finding, not an explanation of
source cause. February through July 2023 satisfy the general continuity rule;
April also satisfies the independent sparse-month rule.

The first and final years are partial at the registered boundaries. In
particular, 2026 ends at the observed registered timestamp
2026-06-26T20:45:00Z; the audit does not assume that later observations should
exist.

## Derived data policy

Future derived datasets must document input dataset version, code/configuration
version, column definitions, exclusions, time conventions, and creation time.

## Research coverage metadata

COVERAGE-001 consumes, rather than redefines, RAW-DQ-001. The package builds
row metadata on demand and writes bounded aggregate counts under
`reports/coverage/`.

| Flag | Meaning |
|---|---|
| `raw_available` | The registered source row is present. |
| `schema_valid` | RAW-DQ-001 schema and row-count reconciliation pass. |
| `timestamp_valid` | RAW-DQ-001 timestamp parsing, UTC, order, and grid checks pass. |
| `ohlc_valid` | RAW-DQ-001 reports no OHLC invariant violation. |
| `duplicate_free` | RAW-DQ-001 reports no duplicate primary timestamp. |
| `cadence_valid` | The incoming observed interval is exactly M15; true for the first row. |
| `weekly_gap_boundary` | Row is either `timestamp_before` or `timestamp_after` for an audited likely-weekly-closure gap. |
| `long_nonweekly_gap_boundary` | Row is either boundary endpoint of an audited long non-weekly gap. |
| `nonweekend_gap_boundary` | Row is either boundary endpoint of an audited non-weekend intraday gap. |
| `unclassified_gap_boundary` | Row is either boundary endpoint of an audited unclassified gap. |
| `continuity_impaired_period` | Row belongs anywhere within an audited continuity-impaired UTC month; it need not be a gap endpoint. |
| `affected_period_2023` | Row lies within the inclusive audited concentrated-2023 bounds. |
| `partial_boundary_year` | Row belongs to the audited incomplete first or final UTC year. |
| `partial_boundary_month` | Row belongs to the audited first or final UTC month. |
| `research_eligible_default` | All structural flags pass; coverage warnings remain included. |
| `requires_sensitivity_analysis` | A partial boundary, impaired month, audited affected period, or non-weekly gap-boundary condition applies. |

`eligibility_status` is derived from the two eligibility flags:

- `fully_eligible`: `research_eligible_default` is true and
  `requires_sensitivity_analysis` is false;
- `conditionally_eligible`: both flags are true;
- `structurally_ineligible`: `research_eligible_default` is false, regardless
  of sensitivity flags.

For gap-boundary flags, both the last observed row before the gap and the first
observed row after it are flagged. By contrast, `cadence_valid` is false only
on the after-gap row because it describes that row's incoming interval.
`continuity_impaired_period` is a period-membership flag applied to every
observed row in the affected month, not a gap-endpoint flag.

At date, month, year, and dataset levels, structural and default-eligibility
flags require all observed child rows to pass. Boundary, affected-period, and
sensitivity flags are true when any observed child row is flagged. Only UTC
periods containing an observed row are represented; absent timestamps remain
Task 02 audit evidence, not inserted observations.

Profiles are masks over those flags:

- `FULL_DATASET`: every registered observation;
- `DEFAULT_RESEARCH`: structurally eligible observations, with coverage
  warnings retained;
- `STRICT_CONTINUITY`: default-eligible observations without a sensitivity
  condition;
- `SENSITIVITY_FULL`: default-eligible observations with any sensitivity
  condition;
- `SENSITIVITY_2023`: default-eligible observations inside the audited
  concentrated-2023 bounds.

Every flag is registered to a stable rule ID in
`eurusd_research.research.registry`. Row lineage retains the physical CSV row
number and raw timestamp; all levels retain raw checksum, dataset version,
normalized Task 02 result fingerprint, coverage-config fingerprint,
COVERAGE-001 version, exact gap/month artifact fingerprints, and Git repository
version plus clean/dirty source-worktree state. The configured generated
coverage-output directory is excluded from that state check so refreshing the
reports cannot make its own lineage dirty; every other tracked or untracked
path remains part of the check.

`configs/coverage.yaml` pins the normalized RAW-DQ-001 result fingerprint and
the exact Task 02 gap/month table fingerprints. Missing artifacts, mismatched
dataset identity, changed audit rules, incompatible schemas, cross-artifact
disagreement, or fingerprint drift stop generation. Refreshing these pins
requires an explicit review of a newly generated Task 02 audit.

## Task 04 daily observations

The historical v2.2 file
`reports/research/task04_daily_range_weekday/daily_observations.csv` contains
one row per observed UTC date. It is a daily lineage and eligibility table, not
a duplicate M15 dataset. After the authorized v2.3 anchor, the same registered
schema will be generated under
`reports/research/task04_daily_range_weekday_v2.3/`.

| Field | Definition |
|---|---|
| `utc_date` | UTC calendar date, `00:00:00` through `23:59:59.999999`. |
| `weekday_number` / `weekday_name` | UTC weekday; Monday is 0. |
| `daily_open` | Open of the earliest contributing `DEFAULT_RESEARCH` M15 row. |
| `daily_high` | Maximum high among contributing primary-profile rows. |
| `daily_low` | Minimum low among contributing primary-profile rows. |
| `daily_close` | Close of the latest contributing primary-profile row. |
| `daily_range_price` | `daily_high - daily_low`, without pre-analysis rounding. |
| `daily_range_pips` | `daily_range_price / 0.0001`; the Task 04 primary outcome. |
| `expected_m15_rows` | Expected grid size under the registered UTC/Task 02 boundary rule. |
| `observed_coverage_ratio` | Contributing rows divided by expected rows. |
| `is_partial_daily_observation` | At least one registered completeness condition fails. |
| `primary_profile_eligible` | Complete non-boundary Monday-Friday date under `DEFAULT_RESEARCH`. |
| `*_analysis_eligible` | Equivalent separately aggregated membership for a named Task 03 profile. |
| `*_observed_m15_rows` | Profile contribution count; zero is explicit rather than an absent date. |
| `*_daily_range_pips` | Nullable for a zero-contribution profile-date; no artificial range is created. |
| `contributing_rows_sha256` | Digest of contributing physical CSV row numbers. |
| lineage fields | Dataset, audit, coverage, Task 04 configuration, preregistration, method, and Git identities. |

Monday-Thursday expected grids contain 96 M15 timestamps. Friday grids end at
the applicable `timestamp_before` from an audited RAW-DQ-001
`likely_weekly_closure`; Sunday grids begin at the corresponding
`timestamp_after` but remain excluded from Monday-Friday inference. Saturday
and all other weekend observations remain traceable. Profile-prefixed fields
come from row-level profile selection before aggregation.
Floating-point fields are serialized with 17 significant digits so CSV
round-tripping preserves the unrounded analysis values and test statistics.

Every profile reconciles to all 5,146 raw-observed UTC dates. A
zero-contribution date has nullable OHLC/range, zero contributing rows, and
explicit `zero_profile_contribution` and `task03_profile_ineligible_date`
reasons in the internal long-form per-profile aggregation. The public wide
daily CSV exports primary OHLC plus profile-prefixed contribution, range,
eligibility, and digest fields; it does not export secondary-profile OHLC.

The v2.3 population reconciliation reports `zero_contribution_dates`,
`nonzero_partial_dates`, `complete_dates`, `incomplete_dates`, and
`dates_included_in_analysis`. For every profile:

`incomplete_dates = zero_contribution_dates + nonzero_partial_dates`.

The historical v2.2 label `partial_daily_observations` meant total incomplete
dates, including zero contribution; it remains historical output only.

## Task 04 volatility-regime lineage

`volatility_regime_lineage.csv` contains one row per primary eligible UTC date.
It reports the lagged 60-date trailing median, number of earlier regime
measures, past-only 0.33/0.67 thresholds, regime label, warm-up flag/reason,
lookback/minimum-history settings, and complete Task 04 lineage. Current-day
range is shifted out before the trailing statistic, and thresholds use only
earlier trailing measures.
