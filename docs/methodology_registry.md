# Methodology registry

Research definitions should be registered before results are examined. Add one
entry per material method and preserve superseded entries rather than rewriting
history.

## Entry template

```text
Method ID:
Status: proposed | preregistered | exploratory | validated | superseded
Created (UTC):
Owner:
Research question:
Population and sample window:
Input dataset version(s):
Unit of observation:
Exact variable definitions:
Timezone, calendar, and boundary rules:
Inclusion and exclusion rules:
Missing/invalid observation policy:
Statistical estimand and method:
Confidence level and multiplicity policy:
Robustness checks planned before results:
Outputs:
Known limitations:
Supersedes / superseded by:
Results access status at definition time:
```

## Registered methods

**Method ID:** RAW-DQ-001

**Status:** validated

**Created (UTC):** 2026-07-27

**Owner:** EUR/USD Quant Research

**Research question:** Is the registered raw EUR/USD M15 dataset technically
reliable enough to support later feature engineering and research?

**Population and sample window:** Every source row in registered dataset version
`sha256:b2a41310927aa9a9`; registered bounds 2010-01-03T22:00:00Z through
2026-06-26T20:45:00Z.

**Input dataset version(s):** `sha256:b2a41310927aa9a9` (full SHA-256 retained in
the authoritative manifest and outputs).

**Unit of observation:** One source CSV record; timestamp continuity uses pairs
of consecutive records in source order.

**Exact variable definitions:** Raw schema as defined in
`docs/data_dictionary.md`.
OHLC invariants require finite positive prices, high at least low/open/close,
and low at most open/close. The source-provided count field is tested for
finite, non-negative, integer-like values and empirical bounds without assigning
semantics.

**Timezone, calendar, and boundary rules:** Timestamps must carry an explicit
timezone, normalize to UTC, and align to minutes 00/15/30/45 with zero seconds
and microseconds. A likely weekly-closure gap is at least the configured 1,440
minutes and has a Friday/Saturday endpoint followed by Sunday/Monday. A
`long_nonweekly_gap` is at least the configured 720 minutes outside that rule;
its cause remains unresolved. A non-weekend intraday gap has weekday endpoints
and is below 720 minutes. Other gaps are unclassified. No session, holiday, or
fixed UTC offset is assigned.

**Inclusion and exclusion rules:** All structurally readable source rows are
included. Empty and malformed physical rows are counted explicitly; malformed
rows make the audit fatal. No observation is cleaned, reordered, interpolated,
filled, repaired, or written back.

**Missing/invalid observation policy:** Report every detected issue. Store
detailed gap and violation tables separately; do not remove observations.

**Statistical estimand and method:** Counts, percentages, empirical distributions,
minimum, maximum, mean, median, sample standard deviation, and selected
percentiles. Large ranges use the predeclared 99.9th percentile as a descriptive
flag only. 2023 is called materially different only if its estimated
non-weekend intraday missing bars exceed twice both 2022 and 2024. A
concentrated pattern is bounded using 2023 non-weekend intraday gap durations
that occur at least ten times and remain below 720 minutes.

Absent timestamps are vector-expanded only for positive, cadence-aligned
intervals and allocated to their actual UTC years/months. Gap-begin, gap-end,
gap-touch, and physically missing-timestamp counts are separate. Boundary,
sparse, and continuity-impaired month rules are independent; the continuity
rule is at least 10 non-weekend intraday gaps touching a month.

Count-field masks include immediate rows before/after classified weekly gaps;
immediate endpoints of gaps at least 720 minutes; observed rows on UTC dates
touched by non-weekly continuity defects; and the computed recurring 2023
anomaly bounds. Low count means below the configured empirical 10th percentile.
Subset and comparator sample size, mean, median, standard deviation, bounds,
configured percentiles, and low-count rate are reported without causal claims.

**Confidence level and multiplicity policy:** Not applicable; this is a
deterministic technical audit, not inferential market-behaviour research.

**Robustness checks planned before results:** Independently enumerate gaps,
summarise them by year/month and duration, compare 2023 with adjacent full
years, use source text plus scaled integers for precision, and verify raw
checksum before and after execution.

**Outputs:** `reports/audits/raw_data_quality_audit.json`,
`raw_data_quality_report.md`, `timestamp_gaps.csv`, `annual_coverage.csv`,
`monthly_coverage.csv`, `ohlc_violations.csv`,
`extreme_price_movements.csv`, and `count_field_distribution.csv`.

**Known limitations:** Timestamp open/close convention, quote convention,
count-field meaning, and upstream-feed continuity are unresolved. Descriptive
gap categories do not confirm a calendar cause.

**Supersedes / superseded by:** None.

**Results access status at definition time:** Criteria were predefined in the
implementation and methodology before their repaired production evaluation.
The current Task 02 worktree is uncommitted, so this is not claimed as
Git-verifiable preregistration. Future research criteria should be committed
before production evaluation whenever practical.

---

**Method ID:** COVERAGE-001

**Status:** validated

**Created (UTC):** 2026-07-27

**Owner:** EUR/USD Quant Research

**Research question:** Which registered observations and UTC periods are
available, structurally eligible, coverage-conditional, or members of a named
sensitivity population for later research?

**Population and sample window:** Every registered source row in
`sha256:b2a41310927aa9a9`, with the RAW-DQ-001 observed bounds.

**Input dataset version(s):** `sha256:b2a41310927aa9a9`; full SHA-256 is
retained in lineage.

**Unit of observation:** One source CSV row. Higher units are observed UTC date,
month, year, and the registered dataset.

**Exact variable definitions:** Stable flags COV-ROW-001 through COV-ROW-010,
COV-PERIOD-001 through COV-PERIOD-004, and COV-ELIG-001/002 are defined in
`docs/data_dictionary.md` and the package rule registry. `eligibility_status`
is `structurally_ineligible` when COV-ELIG-001 fails,
`conditionally_eligible` when structural eligibility passes and COV-ELIG-002
applies, and `fully_eligible` otherwise.

**Timezone, calendar, and boundary rules:** Raw timestamps are normalized to
UTC only after RAW-DQ-001 confirms their validity. Date, month, and year keys
are UTC. No session, holiday, local trading-day, or fixed-offset definition is
introduced. The affected-2023 bounds and continuity-impaired months are
consumed directly from RAW-DQ-001.

**Inclusion and exclusion rules:** `DEFAULT_RESEARCH` requires structural
eligibility and does not exclude coverage-flagged rows. `FULL_DATASET` applies
no filter. `STRICT_CONTINUITY` excludes any COV-ELIG-002 row.
`SENSITIVITY_FULL` selects COV-ELIG-002 rows and `SENSITIVITY_2023` selects
rows inside the audited affected bounds that also satisfy COV-ELIG-001 and
COV-ELIG-002. COV-ELIG-002 includes the affected-period flag, making
`SENSITIVITY_2023` a configuration-provable subset of `SENSITIVITY_FULL`.
Profiles are configuration-driven, reversible masks.

**Missing/invalid observation policy:** Do not insert, delete, repair,
interpolate, or reorder observations. Refuse coverage generation if RAW-DQ-001
has fatal findings or if its JSON, gap table, monthly table, manifest, and raw
identity do not reconcile.

**Statistical estimand and method:** Deterministic boolean classification and
counts/percentages by flag, profile, and coverage level. Structural/all flags
propagate upward with `all`; boundary/sensitivity flags propagate with `any`.
No inferential or market-behaviour statistic is calculated.

**Confidence level and multiplicity policy:** Not applicable; this is
deterministic metadata.

**Robustness checks planned before results:** Reconcile Task 02 artifacts;
verify raw SHA-256 before and after; test flag propagation, profile partitions,
configuration overrides, lineage, deterministic serialization, and raw
immutability.

The configured Task 02 dependency pins its normalized audit-result fingerprint,
gap-table fingerprint, monthly-table fingerprint, and audit method version.
Any drift requires explicit review before COVERAGE-001 can regenerate.

**Outputs:** `reports/coverage/coverage_summary.json`,
`coverage_summary.md`, `row_flag_counts.csv`, `date_flag_counts.csv`,
`month_flag_counts.csv`, and `coverage_profiles.csv`.

**Known limitations:** Coverage metadata cannot establish the cause of a gap or
resolve raw timestamp, quote, count-field, or feed semantics. Higher-level
`any` masks describe whether a child row is flagged; they are not completeness
rates. The framework represents observed rows and periods only.

**Supersedes / superseded by:** None.

**Results access status at definition time:** The rule design was recorded in
the Task 03 worktree before the final production quality-gate run. It is not
claimed as a committed preregistration because the task explicitly forbids a
commit.

---

**Method ID:** RANGE-WEEKDAY-001

**Status:** correctively registered replication, registration version 2.8
prepared; preregistration anchor commit required

**Created (UTC):** 2026-07-28

**Owner:** EUR/USD Quant Research

**Research question:** Does the distribution of EUR/USD daily high-low range
differ across UTC weekdays?

**Population and sample window:** Monday-Friday UTC dates constructed
separately from the `DEFAULT_RESEARCH`, `STRICT_CONTINUITY`,
`SENSITIVITY_FULL`, and `SENSITIVITY_2023` row populations. Primary inference
uses complete `DEFAULT_RESEARCH` dates. The registered dataset bounds are
2010-01-03T22:00:00Z through 2026-06-26T20:45:00Z.

**Input dataset version(s):** `sha256:b2a41310927aa9a9`; full SHA-256
`b2a41310927aa9a9f699ce474bf59c449e99c506bc883cdc73c947286500383c`.
The exact RAW-DQ-001 and COVERAGE-001 dependency fingerprints are locked in
`studies/task04_daily_range_weekday.v2.8.yaml`. Historical v2.2 registration
and control files remain alongside it without being rewritten.

**Unit of observation:** One observed UTC calendar date within one coverage
profile. The sole primary outcome is unrounded daily high-low range divided by
the configured EUR/USD pip size.

**Exact variable definitions:** Daily open and close are the earliest and
latest contributing eligible M15 observations; daily high and low are the
maximum and minimum contributing prices. `daily_range_price = daily_high -
daily_low`; `daily_range_pips = daily_range_price / 0.0001`. No return,
direction, true range, ATR, ADR, signal, or profitability variable is defined.

**Timezone, calendar, and boundary rules:** Dates and weekdays use UTC calendar
boundaries only. Monday through Thursday require the complete 00:00-23:45 M15
grid. Friday's expected grid ends at the applicable audited RAW-DQ-001
likely-weekly-closure endpoint; this avoids assuming 96 Friday candles or a
fixed UTC close. Saturday and Sunday remain traceable but are excluded from the
weekday comparison. The first and final observed dates are retained and
explicitly excluded from inference.

**Inclusion and exclusion rules:** The primary analysis requires Monday-Friday,
complete daily coverage, both expected boundary intervals, no missing expected
interval, and contributing `DEFAULT_RESEARCH` rows. Outliers remain in the
primary population. Partial dates, weekend dates, and boundary dates remain in
daily metadata with reasons. Coverage profiles are applied at row level before
daily aggregation.

**Missing/invalid observation policy:** Do not insert, interpolate, repair,
delete, or silently omit observations. Every observed UTC date is reconciled.
Incomplete profile-date records are excluded only by the registered complete-day
rule and remain reversible in metadata.

**Statistical estimand and method:** Compare Monday-Friday
`daily_range_pips` distributions with a primary Kruskal-Wallis test. Run all
ten Dunn pairwise rank comparisons with Holm family-wise correction. Report
epsilon-squared, Cliff's delta, mean and median differences, deterministic
bootstrap intervals, one-way ANOVA, Welch ANOVA, Brown-Forsythe variance
diagnostics, skewness, excess kurtosis, and Q-Q correlation. Parametric tests
are complementary and cannot replace the primary result.

**Confidence level and multiplicity policy:** Alpha 0.05; 95% deterministic
percentile-bootstrap intervals with 2,000 resamples and seed 20260727. Holm
correction applies to the ten pairwise comparisons within each analysis
population.

**Robustness checks planned before results:** Required coverage profiles;
pre-2020, 2020-2021, and post-2021 periods; ordered 70/30
development-validation split; year-by-year summaries with at least 20
observations per weekday for inferential interpretation; past-only lagged
60-day volatility regimes with 120 prior regime measures; 1st/99th percentile
winsorisation; and exclusion of the largest 1% of daily ranges.

**Outputs:** After the separately authorized anchor commit, deterministic
machine-readable study artifacts, date-level
volatility-regime lineage, and eight static figures under
`reports/research/task04_daily_range_weekday_v2.8/`, as enumerated in the
machine-readable registration and immutable receipt.

**Known limitations:** UTC dates are not local trading sessions; timestamp
open/close semantics remain unresolved; serial dependence, volatility
clustering, unequal variance, changing regimes, and calendar imbalance can
affect inference; sensitivity-only profiles are diagnostic populations; daily
range does not establish direction, profitability, or a trading rule.

**Supersedes / superseded by:** v2.8 supersedes the stopped v2.7 attempt without
changing the registered numerical methodology.

**Results access status at definition time:** The original Task 04 analysis had
already been developed, generated, and independently reviewed before
registration version 2.8 was prepared. The original mutable completion record
is preserved in `task04_development_baseline.json` but is not accepted as
proven preregistration evidence. Version 2.8 is therefore a correctively
registered replication, not a pristine first-look preregistration.

**Registration version 2.4 control:** The exact registered design, executable
configuration, complete declared source/script closure, environment lock, Task
02 evidence, Task 03 row/date membership digests, expected output inventory,
and registered path inventory are prepared before anchoring. A receipt may be
created only after these files are committed in a dedicated preregistration
anchor. Validation accepts the anchor and descendants, rejects non-descendants
or missing objects, and requires every registered worktree path to match its
anchor blob. Design B rebuilds Task 03 masks but requires exact row- and
date-membership digests before Task 04 aggregation. Same-version deviations are
forbidden; any post-anchor scientific change requires v2.5 or later.

Version 2.4 preregisters a strict fourteen-stage production sequence, including
an explicit final-output promotion stage before lifecycle construction.
Generation writes only to `reports/research/.task04_v2.4_candidate/` and never
creates a completed lifecycle. Exact inventory and containment, independent
population and statistical reproduction, two isolated deterministic
regenerations, figure validation, and every enumerated quality gate must pass
before atomic promotion to the final directory and construction of a terminal
lifecycle. The canonical digest `task04-path-length-bytes-sha256-v1` streams,
for each sorted registered relative path, UTF-8 path bytes, NUL, ASCII decimal
file length, NUL, file bytes, and NUL into SHA-256. The registered absolute
numerical tolerance is `1e-10`; branch-aware coverage must be at least 90%.

**Historical v2.3 attempt:** v2.3 established a valid pre-result Git anchor at
`d409938b6b528a7acd17404320255a71f9729b6c`. Its anchored production-governance
schema was incomplete, so Phase B stopped before receipt creation, lifecycle
creation, or calculation. It is an abandoned preregistration attempt, not a
completed study and not altered history.

**Historical registration version 2.2 control:** Before corrected production
regeneration,
the `PREREGISTERED` semantic design, executable configuration, raw/manifest/
Task 02/Task 03 fingerprints, production source, Git HEAD/dirty disclosure,
development baseline, and exact output inventory are bound by
`task04_daily_range_weekday.v2.2.receipt.json`. Completion is bound by the
sibling lifecycle record. A later adversarial review demonstrated that
current-HEAD equality, replaceable local control files, incomplete live-source
coverage, and a non-operational deviation ledger prevented v2.2 from being the
final institutional anchor. Its files remain historical control evidence and
are not overwritten. The preserved
`task04_daily_range_weekday.v2.0.failed.receipt.json` anchored an aborted
attempt: live dependency validation rejected a Task 03 artifact whose volatile
repository-state field had been regenerated. No Task 04 aggregation or
weekday-level result was calculated in that attempt. The authoritative tracked
Task 02 and Task 03 outputs were restored byte-for-byte before v2.1 anchoring,
and receipt construction now validates live dependencies before writing.
The completed v2.1 run is preserved in
`task04_v2.1_completed_baseline.json`; its scientific results were correct, but
the exported `method_version` lineage field contained the implementation
version. Version 2.2 corrects only that lineage mapping before a new receipt.

**Timestamp assumption:** Authoritative candle-open-versus-candle-close
semantics remain unresolved. Version 2.4 assigns each timestamp label to its
supplied UTC date, discloses the possible one-bar boundary consequence, and
caps evidence at `MODERATE`.

**Historical v2.4 completion record:** None. v2.4 reached an anchor, receipt,
dependency gate, and candidate generation, then stopped at independent
reconciliation. Candidate artifacts were never promoted and no lifecycle was
created. Historical v2.2 reference values remain regression evidence rather
than v2.5 registration inputs.

### Registration version 2.5 governance amendment

The scientific definitions above remain unchanged. v2.4 is now classified as
an abandoned registered attempt: its anchor, receipt, dependency gate, and
candidate generation succeeded, but Phase B stopped before deterministic
regeneration, promotion, lifecycle completion, or final acceptance. The
anchored independent module had asserted zero robustness/regime discrepancies
and output-inventory success without calculating them. Its exact stopped state
is recorded in `studies/task04_v2.4_stopped_attempt.json`.

Version 2.5 preregisters
`task04-independent-full-reproduction-v2`. It independently validates raw and
Task 03 identities, rebuilds all four profile-date populations before daily
aggregation, and checks every profile/date field through the registered
`daily_profile_observations.csv`. It independently calculates the full
descriptive set, bootstrap intervals, omnibus/effect tests, all pairwise rows,
chronological split, fixed periods, all calendar years, date-level past-only
regimes, extreme-event sensitivities, and every evidence-rating dimension. It
also inspects the filesystem inventory, file types, links, containment,
per-file SHA-256, and the registered path-length-bytes digest without calling
the production inventory implementation.

The required component inventory is `source_population`, `daily_aggregation`,
`descriptive_statistics`, `primary_inference`, `pairwise_analysis`,
`chronological_analysis`, `fixed_period_analysis`, `annual_analysis`,
`volatility_regime_analysis`, `extreme_event_analysis`, `evidence_rating`, and
`output_inventory`. Each component records checked row/field counts,
field-level absolute and relative discrepancies, categorical/membership/
inventory mismatch counts, missing evidence, unsupported claims, and pass/fail
status. Categorical, membership, and inventory tolerances are zero. An absent
or `NOT_CHECKED` component, a non-finite discrepancy, an unsupported assertion,
or any component failure prevents lifecycle completion.

Task 03 remains Design B because the authoritative artifact provides exact
row/date membership digests rather than a row-addressable mask file. The
independent path may invoke the upstream COVERAGE-001 builder only to obtain
masks; it must reconcile every row/date membership digest, profile count,
boundary classification, and subset/disjointness rule before reading an outcome
into Task 04 aggregation. No Task 04 production aggregation, statistics,
robustness, rating, or inventory function is a permitted dependency.

For v2.6 reconciliation, candidate CSVs are loaded by explicit schema. The
registered volatility-regime comparison is projected to exactly these fields,
in order: `utc_date`, `profile`, `daily_range_pips`,
`lagged_trailing_median_range_pips`, `prior_regime_measure_count`,
`past_only_low_threshold`, `past_only_high_threshold`, `volatility_regime`,
`regime_warmup`, `regime_classification_reason`, `volatility_lookback`, and
`volatility_minimum_history`. Wider independent working fields are not output
evidence. Output paths are production-root-relative forward-slash paths;
figures must retain the `figures/` prefix. Categorical, membership, and
inventory mismatches remain fail-closed at zero tolerance.

### Registration version 2.7 governance amendment

The scientific definitions and all v2.6 reconciliation controls above remain
unchanged. v2.6 completed its anchor, receipt, dependency gate, candidate
generation, twelve-component reconciliation, deterministic regeneration, and
figure validation. It stopped before promotion or lifecycle creation because
an integration test incorrectly treated receipt absence as a global invariant
after legitimate receipt creation.

Version 2.7 registers five explicit filesystem lifecycle states:
`PRE_RECEIPT`, `POST_RECEIPT_PRE_CANDIDATE`, `CANDIDATE`,
`POST_PROMOTION_PRE_LIFECYCLE`, and `COMPLETED`. Tests use isolated paths and
require receipt absence only in `PRE_RECEIPT`; later states require the receipt.

Task 03 evidence is separated into scientific membership, stable artifact, and
execution-context identities. Exact row/date memberships, counts, algebra,
boundaries, schema, and raw identity comprise the scientific fingerprint.
Canonical Task 03 output content after excluding only registered repository
context comprises the stable-artifact fingerprint. Repository HEAD, dirty
state, and raw artifact hashes remain in a separate execution-context
fingerprint. Context variance is informational only when both scientific and
stable identities match; either material identity mismatch fails before Task 04
aggregation. The receipt binds scientific and stable identities plus the
context observed at receipt creation; the lifecycle records the Phase B context
and whether allowed variance occurred.

No v2.7 receipt, lifecycle, candidate output, production output, or observed
v2.7 result may exist before the separately authorized v2.7 Git anchor.

### Registration version 2.8 candidate byte-identity amendment

The scientific design, Task 03 identity layers, output inventory, statistical
methods, and tolerances remain unchanged from v2.7. The v2.7 attempt stopped
before promotion and lifecycle creation after a one-byte mutation to
`figures/01_weekday_boxplot.png` changed the file hash and canonical digest but
was not compared with any prior trusted candidate identity.

After schema, inventory, and all twelve reconciliation components succeed,
v2.8 creates one immutable `task04-validated-candidate-identity-v1` record. It
binds the anchor, receipt, method, exact path inventory, per-file sizes and
SHA-256 hashes, and `task04-path-length-bytes-sha256-v1` digest. Subsequent
reconciliation, pre-promotion validation, final-output validation, and lifecycle
construction must compare their current bytes with that same baseline. Missing,
replaced, cross-anchor, cross-receipt, cross-version, or automatically regenerated
baseline identities fail closed. Deterministic regeneration remains a separate
repeatability control.

No v2.8 receipt, lifecycle, candidate output, production output, candidate
identity, or observed v2.8 result may exist before the separately authorized
v2.8 Git anchor.

### Registration version 2.9 standalone completion-evidence amendment

Version 2.9 preserves every v2.8 scientific definition and the exact 28-file
scientific output inventory. It changes governance only. A completed lifecycle
is valid only when validation reopens both standalone evidence files, validates
their strict schemas and canonical fingerprints, matches anchor, receipt,
registration and method context, and proves the standalone candidate inventory
equals final production bytes. Embedded lifecycle copies cannot substitute for
missing, truncated, or different standalone evidence.

The independent evidence-rating path also reconstructs and compares every
nested rating-summary dimension field by field; the registered thresholds and
rating algorithm are unchanged. PRE_RECEIPT integration tests use temporary
repository state and never infer lifecycle state from a developer checkout.

### Registration version 2.10 lifecycle-fixture isolation amendment

Version 2.10 preserves the complete v2.9 scientific design, standalone-evidence
binding, Task 03 identities, and 28-file output inventory. Its PRE_RECEIPT
fixture is constructed only from registered anchor paths and the registered raw
CSV. It explicitly excludes all ambient receipt, candidate, validated identity,
reconciliation, final-output, lifecycle, historical runtime, cache, coverage,
and temporary mutation state. Every other lifecycle-state test likewise builds
its own state rather than inheriting the live repository state.
