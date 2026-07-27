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
No derived field is defined in this infrastructure task.
