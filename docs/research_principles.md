# Research principles

## Scope

The project studies recurring EUR/USD behaviour. It does not assume that a
statistical regularity is tradeable, and it separates description, inference,
and any later economic interpretation.

## Reproducibility and lineage

- Treat registered raw files as immutable.
- Identify inputs by checksum and dataset version, not filename alone.
- Put reusable transformations in the package and test boundary behaviour.
- Make randomness explicit and seed it from validated configuration.
- Keep generated artifacts traceable to code, configuration, and input identity.

## Observation handling

Never silently delete, replace, interpolate, or winsorise observations. Report
missingness and anomalies first. Any later exclusion requires a written rule,
reason, affected count, and sensitivity comparison where appropriate.

## Time integrity

Use timezone-aware timestamps. Storage is UTC, but civil-market definitions
must use IANA timezone databases and account for daylight-saving transitions.
Do not encode a local session as a fixed UTC offset. Define week and trading-day
boundaries explicitly.

## Bias controls

Avoid look-ahead bias, future leakage, survivorship-like source changes, and
post-result definition changes. Define methods before inspecting results.
Separate exploratory findings from confirmatory tests and preserve both labels.

## Statistical discipline

Report denominators, uncertainty, missing-data effects, multiple-comparison
considerations, regime sensitivity, and practical magnitude. Robustness across
years or regimes does not rescue an ambiguously defined metric.
