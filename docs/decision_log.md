# Decision log

Material decisions are appended with an ISO date, rationale, and implications.

## 2026-07-27 — Use a `src`-layout Python package

**Decision:** Package reusable code under `src/eurusd_research`.

**Rationale:** Prevent accidental imports from the working tree and keep scripts,
tests, and library responsibilities distinct.

## 2026-07-27 — Use `pyproject.toml` and Python 3.11–3.13

**Decision:** Declare runtime and development dependencies in one PEP 621 file;
validate this repository with Python 3.12.

**Rationale:** Python 3.11+ is modern and supported, while an upper bound avoids
claiming compatibility before scientific dependencies support newer runtimes.
Compatible release ranges balance reproducibility with security maintenance.

## 2026-07-27 — Validate YAML configuration with Pydantic

**Decision:** Keep human-readable YAML under `configs/` and validate it into
typed, immutable models.

**Rationale:** Research conventions remain reviewable while malformed or
inconsistent settings fail with useful messages.

## 2026-07-27 — Stream raw-file registration

**Decision:** Read the raw CSV sequentially with the standard library to compute
identity and metadata; do not load or rewrite it with a dataframe library.

**Rationale:** This bounds memory use and minimizes the operations performed on
the immutable source.

## 2026-07-27 — Defer all session times

**Decision:** Configure named placeholders and IANA timezones, but leave local
times disabled and unset.

**Rationale:** Session and FX rollover definitions are methodological choices
that require explicit preregistration and daylight-saving-aware implementation.

## 2026-07-27 — Treat raw quality findings as evidence, not repairs

**Decision:** Implement RAW-DQ-001 as a strictly read-only package workflow with
separate typed results, gap classification, serialization, and CLI concerns.
Retain every detailed gap and violation in diagnostic tables; do not clean,
sort, interpolate, fill, or rewrite the registered input.

**Rationale:** Future research needs reproducible evidence and complete lineage
before any research-specific exclusion rule can be justified.

## 2026-07-27 — Predeclare conservative readiness and gap rules

**Decision:** Classify fatal identity, mandatory-schema, timestamp,
duplicate-primary-timestamp, material OHLC, unreadable-file, and mutation
findings as `NOT_READY`. Coverage gaps, partial periods, and unresolved source
semantics produce `CONDITIONALLY_READY`; `READY` is reserved for the absence of
material issues. Gap labels use only endpoint weekdays and configured duration
thresholds and do not name holidays.

**Rationale:** Predeclared criteria prevent the observed production result from
driving the classification rule and prevent plausible calendar interpretations
from being reported as confirmed facts.

## 2026-07-27 — Keep count-field language neutral

**Decision:** Preserve the raw name `volume_or_tick_count` but refer to it in
research prose only as the source-provided count field until source
documentation establishes its meaning.

**Rationale:** Empirical bounds may support a constituent-M1-count hypothesis
but cannot establish volume, activity, participation, liquidity, or feed
semantics.

## 2026-07-27 — Type-check against the validated Python 3.12 runtime

**Decision:** Set mypy's target to Python 3.12, the repository's recommended and
validated runtime, while retaining the declared runtime support range.
Scientific-library imports without installed third-party stubs are explicitly
ignored; internal annotations remain under strict mypy rules.

**Rationale:** Installed NumPy stubs use Python 3.12 type-alias syntax. This
keeps the quality gate executable in the validated environment without adding
an undeclared network-time dependency.

## 2026-07-27 — Repair RAW-DQ-001 lineage and coverage semantics

**Decision:** Make the typed raw manifest authoritative; keep only logical,
path, schema, and version expectations in configuration; and make every
manifest/config/file disagreement fatal. Identical registration does not
rewrite the manifest solely for a later verification timestamp.

**Rationale:** Immutable registration identity must not be shadowed by
duplicated configuration values or churn from transient verification metadata.

## 2026-07-27 — Allocate missing timestamps to physical UTC periods

**Decision:** Expand cadence-aligned missing grid points and allocate them to
their actual UTC year/month. Report gap starts, ends, touches, and missing
timestamps separately. Classify months independently as boundary, sparse, and
continuity-impaired; the latter requires at least 10 non-weekend intraday gaps
touching the month.

**Rationale:** Assigning an entire cross-period gap to its ending period
misstates coverage, while total bar count alone cannot detect systematic
intramonth discontinuity.

## 2026-07-27 — Use neutral gap and count-relationship diagnostics

**Decision:** Replace holiday-like language with `long_nonweekly_gap`. Apply the
configured weekly threshold consistently. Compare the source-provided count
field at immediate weekly boundaries, immediate endpoints of gaps at least 720
minutes, continuity-impaired UTC dates, and computed affected-period bounds,
with explicit comparator statistics.

**Rationale:** Duration and weekday evidence do not establish a holiday,
source cause, liquidity, participation, or count-field semantics.

## 2026-07-27 — Define warnings and deterministic serialization

**Decision:** Emit ordered coverage, data-value, and semantic warnings
separately from fatal failures. Stable analytical JSON, CSVs, and Markdown are
deterministic; execution timestamp, elapsed time, and raw modification time are
normalized out of deterministic comparisons. Serialized artifact paths are
repository-relative so outputs do not embed a local workstation path.

**Rationale:** Conditional readiness must expose its nonfatal limitations, and
reviewers need a reproducible analytical-content contract without pretending
execution metadata is invariant.

## 2026-07-27 — Retain coverage warnings in the default population

**Decision:** Define `DEFAULT_RESEARCH` from structural validity only.
Continuity-impaired periods, partial boundaries, and non-weekly gap endpoints
remain included but set `requires_sensitivity_analysis`. Put actual exclusions
in named configuration-driven profiles.

**Rationale:** Task 02 findings justify visible robustness checks, not silent
deletion or a universal claim that affected prices are invalid.

## 2026-07-27 — Consume Task 02 artifacts as the coverage source of truth

**Decision:** Build COVERAGE-001 from the registered audit JSON,
`timestamp_gaps.csv`, and `monthly_coverage.csv`; do not reclassify gaps or
repeat schema, timestamp, duplicate, and OHLC validation. Refuse generation
when the evidence does not reconcile.

**Rationale:** One audited definition prevents methodological drift and
preserves direct lineage from later research masks to RAW-DQ-001.

## 2026-07-27 — Propagate flags with explicit any/all semantics

**Decision:** At UTC date, month, year, and dataset levels, structural flags use
`all`; boundary, impairment, affected-period, and sensitivity flags use `any`.
Represent observed periods only.

**Rationale:** Higher-level masks need deterministic meaning without inventing
missing rows. Explicit propagation makes study exclusions reversible and
testable.

## 2026-07-28 — Include the audited affected period in sensitivity eligibility

**Decision:** Add `affected_period_2023` to COV-ELIG-002 and require
COV-ELIG-002 explicitly in `SENSITIVITY_2023`.

**Rationale:** Independent verification found 239 affected-period rows outside
the original six-condition sensitivity union. The original 46,229-row
population therefore failed the required
`SENSITIVITY_2023 ⊆ SENSITIVITY_FULL` relationship. The corrected union is
46,468 rows, and the profile algebra is now verified over every truth
assignment of its referenced flags rather than only the production dataset.

## 2026-07-28 — Pin exact Task 02 evidence and report dirty lineage

**Decision:** Pin the normalized audit-result, gap-table, and monthly-table
fingerprints in coverage configuration. Persist exact consumed artifact
fingerprints and append `+clean` or `+dirty` to the Git HEAD lineage. Exclude
only the configured generated coverage-output directory from the worktree
state check so an artifact refresh does not change its own lineage.

**Rationale:** Dataset identity and aggregate counts alone cannot detect every
stale table substitution, and a dirty Task 03 worktree must not be represented
as the clean committed HEAD. Generated outputs are consequences of that state,
not source inputs, and including them would make clean-lineage regeneration
self-referential and non-deterministic.
