# Decision log

Material decisions are appended with an ISO date, rationale, and implications.

## 2026-09-10 — Bind validated Task 04 candidate bytes before promotion

**Decision:** Version 2.8 establishes a write-once candidate identity only after
candidate schema, inventory, and all twelve independent reconciliation components
are validated. It binds path, length, SHA-256, and canonical aggregate digest;
every later reconciliation, promotion, and lifecycle check compares current bytes
to that prior identity and never silently re-baselines.

**Rationale:** The v2.7 inventory reconciler calculated current hashes but did
not compare them with the already validated candidate. A one-byte figure mutation
therefore produced a different digest while inventory and aggregate checks still
passed. Deterministic regeneration and post-validation identity are distinct
controls. v2.7 remains an abandoned registered attempt; no output was promoted
and no lifecycle was created.

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

## 2026-07-28 — Lock the first behavioural study before outcome calculation

**Decision:** Register RANGE-WEEKDAY-001 in machine-readable YAML before
calculating weekday daily ranges. Lock the null/alternative hypotheses, sole
outcome, UTC calendar, complete-day policy, primary Kruskal-Wallis test, Dunn
post-hoc procedure, Holm correction, effect sizes, deterministic bootstrap,
robustness populations, past-only volatility regime, and evidence-rating logic.
Permit only the `PREREGISTERED` to `COMPLETED` status transition without a
locked-design fingerprint change.

**Rationale:** The first behavioural result must not choose definitions,
exclusions, periods, or tests after inspecting weekday differences.

**Subsequent correction:** Independent adversarial review found that this
development registration had no immutable pre-result receipt, omitted semantic
fields from its lock, and could be rewritten after completion. It is retained
as development history but is not accepted as proven preregistration evidence.
The registered-replication decision below supersedes its lifecycle claim.

## 2026-07-28 — Derive daily completeness from UTC grids and audited boundaries

**Decision:** Require full 00:00-23:45 UTC grids Monday through Thursday. For
Friday, require 00:00 through the applicable RAW-DQ-001
likely-weekly-closure endpoint. Retain Sunday and weekend dates for accounting,
but exclude them from the Monday-Friday comparison. Apply each COVERAGE-001
profile at M15 row level before aggregating its daily observation.

**Rationale:** Assuming 96 observations for Friday would systematically reject
the normal FX weekly close. Reusing audited endpoints avoids a fixed UTC
offset, a New York trading-day boundary, and duplicated Task 02 classification
logic.

## 2026-07-28 — Grade weekday-range evidence conservatively

**Decision:** Assign RANGE-WEEKDAY-001 `MODERATE` evidence. The primary
Kruskal-Wallis result is statistically significant and chronological
validation persists, but epsilon-squared is small, the HIGH past-only
volatility regime is not significant, year ordering is not uniformly stable,
and diagnostic sensitivity-only populations are directionally inconsistent.

**Rationale:** Statistical significance alone does not establish practical
magnitude, temporal stability, coverage robustness, or trading usefulness.

## 2026-07-28 — Track bounded one-row-per-date Task 04 evidence

**Decision:** Version the 5,146-row `daily_observations.csv` requested by the
study contract. Keep it to daily OHLC/range, completeness, profile membership,
contributing-row digests, and lineage fields; do not write a duplicate
row-level M15 dataset.

**Rationale:** The approximately 4.8 MB file is bounded at one record per
observed UTC date and is the direct reproduction bridge between profile masks
and every Task 04 result. The repository has no policy excluding a derived
artifact of this size.

## 2026-07-28 — Correctively register Task 04 replication under receipt v1

**Decision:** Treat the reviewed Task 04 result as development evidence and
create registration version 2.2 as a correctively registered replication.
Before corrected production regeneration, bind every semantic design field,
the complete executable configuration, raw/manifest/Task 02/Task 03 identity,
production-source fingerprint, baseline development record, Git HEAD/dirty
disclosure, and exact output inventory into a deterministic receipt. Pin that
receipt fingerprint in configuration. Persist a separate completion lifecycle
record so a completed registration cannot be reverted to `PREREGISTERED`.

**Rationale:** A mutable `COMPLETED` YAML and freshly calculated fingerprint do
not prove what was fixed before results. Receipt and lifecycle validation make
post-anchor changes fail closed without pretending the already reviewed
analysis is a pristine first look.

The first corrective receipt, registration version 2.0, is retained as
`task04_daily_range_weekday.v2.0.failed.receipt.json`. Its first generation
attempt stopped in dependency validation before Task 04 aggregation because a
fresh Task 03 run had changed only the coverage artifact's repository-state
field. The authoritative tracked Task 02 and Task 03 artifacts were restored
byte-for-byte. Version 2.1 was then required rather than replacing the v2.0
receipt. Receipt construction now validates the live raw, manifest, Task 02,
and Task 03 dependencies before it can persist a new anchor.

The completed v2.1 gate subsequently exposed a lineage-only defect:
`method_version` output columns carried `implementation_version`. Preserve its
receipt, lifecycle, and all output hashes in
`task04_v2.1_completed_baseline.json`. Correct the mapping without changing any
scientific definition or known result, and require a new v2.2 receipt before
regeneration.

## 2026-07-28 — Preserve unresolved timestamp semantics as an assumption

**Decision:** Do not infer candle-open or candle-close semantics from market
custom. Aggregate by the UTC timestamp label exactly as supplied, disclose that
a close-time convention could move one M15 interval at date/weekly boundaries,
and cap evidence at `MODERATE` while the convention remains unresolved.

**Rationale:** Source evidence does not resolve the convention. A transparent
label-date assumption is narrower than claiming certainty or selecting the
interpretation that best preserves the known result.

## 2026-07-28 — Close Task 04 reconciliation and reporting control gaps

**Decision:** Represent all 5,146 observed raw dates in every coverage profile,
using nullable OHLC and explicit zero-contribution reasons. Export date-level
past-only regime lineage. Derive chronological figures from the canonical
period table, report numerator and denominator degrees of freedom, propagate
the registered deviation ledger, and enforce the exact output inventory.

**Rationale:** Exclusions, robustness labels, and figures must be independently
auditable rather than inferred from absent rows or reconstructed by plotting
code.

## 2026-07-29 — Prepare Git-anchored Task 04 registration version 2.3

**Decision:** Retain v2.2 as historical control evidence and prepare v2.3
without generating v2.3 results. Replace current-HEAD equality with a dedicated
Git commit/tree anchor whose registered blobs must remain unchanged in every
completion descendant. Bind the complete declared source closure and exact
environment lock. Rebuild Task 03 masks only under Design B: row- and
date-membership digests, row order, boundary classifications, profile algebra,
and coverage-output fingerprints must match pinned evidence before Task 04
aggregation.

Use strict nested registration models with finite standards-compliant numbers.
Treat every required evidence artifact as unavailable when missing, empty,
malformed, non-finite, contradictory, or sample-insufficient; the rating is
then `INSUFFICIENT`. HIGH-regime significance is contextual rather than a tier
gate, but its finite omnibus evidence is required. Reject linked or non-regular
outputs. Report zero-contribution and nonzero-partial dates separately.

**Deviation policy:** v2.3 has no same-version append-only deviation ledger.
Any post-anchor scientific or interpretive change requires a new registration
version and new anchor.

**Rationale:** A Git object supplies durable, auditable identity and ancestry,
while path/tree and dependency reconciliation detect scientific replacement.
It does not make local files undeletable. Keeping the preregistration file
unchanged and recording completion only in a descendant lifecycle preserves
the anchor semantics.

## 2026-08-01 — Supersede incomplete v2.3 production governance with v2.4

**Decision:** Preserve commit
`d409938b6b528a7acd17404320255a71f9729b6c` as the genuine pre-result v2.3
Git anchor, but abandon that registration attempt before receipt creation or
calculation. Version 2.3 established a valid pre-result Git anchor, but the
anchored production-governance schema was incomplete. Its receipt and lifecycle
could not bind every mandatory anchor, production, output, reconciliation,
determinism, rating, limitation, and quality-gate field, and generation itself
would have completed the lifecycle too early. No v2.3 receipt, lifecycle, or
production result was created.

Prepare v2.4 with the scientific design unchanged. Candidate generation is not
completion. A separately constructed terminal lifecycle requires every strict
completion gate, independent CSV-based reproduction evidence, and the
documented `task04-path-length-bytes-sha256-v1` digest before final promotion.

**Rationale:** A valid Git anchor proves which design preceded calculation, but
cannot compensate for an incomplete production-completion contract. A new
version preserves the honest history without rewriting v2.3.

## 2026-08-02 — Stop v2.4 and require full independent reconciliation in v2.5

**Decision:** Preserve the v2.4 anchor, receipt, and candidate identities as an
abandoned registered attempt. v2.4 successfully completed its Git anchor,
receipt, dependency validation, and candidate generation. Phase B stopped
before determinism, promotion, lifecycle completion, or final evidence
acceptance because the anchored independent-reconciliation module assigned
zero discrepancies to robustness/regime checks and asserted output-inventory
success without calculating those claims. No final v2.4 output or lifecycle
exists. The stopped-attempt identity is recorded in
`studies/task04_v2.4_stopped_attempt.json`; the original untracked receipt and
candidate directory remain historical runtime evidence.

Prepare v2.5 with unchanged scientific definitions. The independent path must
rebuild profile-date OHLC/ranges from raw rows after exact Task 03 membership
reconciliation, calculate every descriptive, inferential, pairwise,
chronological, fixed-period, annual, past-only regime, extreme-event, and
rating component without importing Task 04 production implementations, and
inspect the output inventory directly. Every component carries calculated
absolute/relative discrepancies, mismatch counts, missing/unsupported claims,
and a pass state. `NOT_CHECKED`, any mismatch, or any unsupported assertion
prevents lifecycle completion.

**Rationale:** A second implementation is useful only when it can expose the
same categories of defects that the production path could contain. Hard-coded
zero discrepancies and asserted booleans are governance claims, not evidence.

## 2026-08-02 — Stop v2.5 after three reconciliation execution defects

**Decision:** Preserve the v2.5 anchor, validated receipt, candidate digest,
and stopped reconciliation identity as an abandoned registered attempt. v2.5
did not promote outputs or create a lifecycle. Its independent architecture
calculated all twelve components, but default CSV NA conversion changed empty
`exclusion_reasons` to null, the wider independent regime frame was compared
without projection to the registered 12-field lineage, and figure basenames
were compared with registered `figures/` paths. These caused false categorical,
membership, and inventory mismatches. The compact identity is recorded in
`studies/task04_v2.5_stopped_attempt.json`.

Prepare v2.6 without changing any scientific definition or numerical
tolerance. Register schema-driven empty-string handling only for
`exclusion_reasons`, the exact regime-lineage field inventory, and canonical
production-root-relative output paths with nested figure prefixes. Retain zero
tolerance for categorical, membership, and inventory mismatches.

**Rationale:** The fail-closed thresholds worked: false comparison mismatches
prevented completion. Correcting the representation contracts is narrower and
more defensible than weakening those thresholds or changing the study.

## 2026-08-02 — Stop v2.6 on lifecycle-state test and layer Task 03 identity

**Decision:** Preserve the v2.6 anchor, receipt, candidate digest, successful
twelve-component reconciliation, deterministic regeneration, and figure
validation as an abandoned registered attempt. No output was promoted and no
lifecycle was created. The quality gate failed because an anchor-registered
integration test required receipt absence even after the registered workflow
had legitimately created the receipt. The production receipt workflow was not
invalidated by that assertion.

Prepare v2.7 with unchanged scientific definitions and unchanged reconciliation
thresholds. Replace the global receipt-absence assumption with five explicit,
isolated lifecycle-state tests. Separate Task 03 scientific membership identity
and stable canonical artifact identity from repository/execution context.
Scientific or stable-artifact differences remain fatal before aggregation;
explicitly registered context-only variance remains auditable and informational.

**Rationale:** Receipt existence is state-dependent, while row/date population
identity is not equivalent to a regenerated artifact's repository-state
metadata. Separating those contracts prevents false governance failures without
relaxing exact membership validation.
