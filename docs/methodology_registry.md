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
