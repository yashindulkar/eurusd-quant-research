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
