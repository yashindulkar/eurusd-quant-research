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
- Trace eligibility decisions to raw timestamp and row, RAW-DQ-001 evidence,
  stable rule ID, coverage configuration, repository version, and dataset
  version.

## Observation handling

Never silently delete, replace, interpolate, or winsorise observations. Report
missingness and anomalies first. Any later exclusion requires a written rule,
reason, affected count, and sensitivity comparison where appropriate.

Every behavioural study must use COVERAGE-001. `DEFAULT_RESEARCH` retains
structurally valid observations even when a coverage warning applies.
Study-specific exclusions are named masks, never destructive transformations,
and must report the excluded count. A study using `STRICT_CONTINUITY` must also
report an appropriate full or sensitivity population so that the exclusion is
reversible and its effect is visible.

Coverage flags are descriptive rather than causal. A weekly-gap boundary,
continuity-impaired month, or affected-period flag identifies Task 02 evidence;
it does not establish a market-calendar event, upstream cause, or invalid
price observation.

## Time integrity

Use timezone-aware timestamps. Storage is UTC, but civil-market definitions
must use IANA timezone databases and account for daylight-saving transitions.
Do not encode a local session as a fixed UTC offset. Define week and trading-day
boundaries explicitly.

## Bias controls

Avoid look-ahead bias, future leakage, survivorship-like source changes, and
post-result definition changes. Define methods before inspecting results.
Separate exploratory findings from confirmatory tests and preserve both labels.

For a preregistered or correctively registered study, every semantic design
field, executable setting, evidence-rating rule, limitation, dependency, and
expected output is locked before production calculation. A deterministic
receipt outside the lifecycle YAML binds that semantic fingerprint to the
executable configuration, complete declared source/dependency closure, exact
Task 03 row membership, an identified Git commit/tree, and the output
inventory. Completion must descend from the anchor object, and registered paths
must remain byte-identical to their anchor blobs. Git does not make local files
undeletable; a replacement scientific design creates a different auditable
commit lineage.

RANGE-WEEKDAY-001 v2.5 does not support same-version post-anchor deviations.
Any scientific, population, threshold, output-contract, or interpretive change
requires a new registration version and new anchor. Its committed
preregistration remains `PREREGISTERED`; completion is represented only by the
receipt-bound lifecycle.

When analysis or results were already developed before an enforceable receipt,
the corrected run is labelled a registered replication, not a pristine
first-look preregistration.

## Statistical discipline

Report denominators, uncertainty, missing-data effects, multiple-comparison
considerations, regime sensitivity, and practical magnitude. Robustness across
years or regimes does not rescue an ambiguously defined metric.

RANGE-WEEKDAY-001 uses Kruskal-Wallis as its primary test and reports all ten
Dunn pairwise comparisons with Holm correction. Parametric tests are
complementary, outliers remain in the primary analysis, and the evidence rating
requires stability and effect magnitude rather than relying on a small p-value.
Registration version 2.5 cannot exceed `MODERATE` while authoritative
candle-open-versus-candle-close timestamp semantics remain unresolved.

Task 04 v2.5 distinguishes candidate evidence from completed evidence.
Candidate generation cannot create a completed registry or lifecycle.
Completion requires individually registered integrity, reconciliation,
determinism, figure, test, typing, lint, coverage, path-safety, and raw-input
immutability gates; missing or false evidence fails closed. Independent
reconciliation is component-level: unchecked components, asserted zero
discrepancies, unsupported claims, or uninspected inventories cannot satisfy a
completion gate.
