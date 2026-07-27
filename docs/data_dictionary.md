# Data dictionary

## Raw dataset: `eurusd_m15_utc`

Canonical path: `data/raw/EURUSD_M15_UTC.csv`

The registration manifest is authoritative for file identity and observed
bounds. The definitions below are expected schema, not a completed quality
assessment.

| Column | Expected meaning | Expected representation |
|---|---|---|
| `timestamp_utc` | Start timestamp of the M15 bar | ISO 8601, UTC-aware |
| `open` | First observed EUR/USD price in the bar | Positive decimal |
| `high` | Maximum observed EUR/USD price in the bar | Positive decimal |
| `low` | Minimum observed EUR/USD price in the bar | Positive decimal |
| `close` | Last observed EUR/USD price in the bar | Positive decimal |
| `volume_or_tick_count` | Source-provided activity count | Non-negative integer-like value |
| `source` | Data provenance label | Non-empty string |

The price quote convention is assumed to be USD per EUR but must be confirmed
against source documentation. Counts are not assumed to be exchange volume.

## Derived data policy

Future derived datasets must document input dataset version, code/configuration
version, column definitions, exclusions, time conventions, and creation time.
No derived field is defined in this infrastructure task.
