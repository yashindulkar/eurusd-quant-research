# Research Coverage and Eligibility Framework

## Scope

This framework assigns reversible descriptive eligibility metadata. It does not clean, repair, delete, or reorder raw observations and does not perform market-behaviour analysis.

## Lineage

- Dataset version: `sha256:b2a41310927aa9a9`
- Raw SHA-256: `b2a41310927aa9a9f699ce474bf59c449e99c506bc883cdc73c947286500383c`
- Task 02 audit method: `raw-data-quality-audit-v2`
- Normalized Task 02 result fingerprint: `670968cbfcf018abc59bbb64a4b2b3912bae9df44988542765748328caf9c61f`
- Task 02 gap-table fingerprint: `60b48e06c107b5c676f200392db6002ca4f678ed4a6c31bb3f0439ebbf6e06c9`
- Task 02 monthly-table fingerprint: `16a7bcc38addf98892b532b4386f59cc5833bd6cf4ecc423e7b9e286027c495a`
- Coverage method: `COVERAGE-001` (`research-coverage-v1`)
- Repository version: `git:c21113da7f91f64804704a2a7c9ccc1b50df0edd+dirty`

## Eligibility summary

- `conditionally_eligible`: 46,468 rows
- `fully_eligible`: 360,477 rows

Coverage warnings do not make an otherwise valid row ineligible under `DEFAULT_RESEARCH`; they mark it for sensitivity analysis.

## Task 02 continuity evidence

- Continuity-impaired UTC months: 2023-02, 2023-03, 2023-04, 2023-05, 2023-06, 2023-07
- Audited concentrated-2023 inclusive bounds: 2023-01-27T10:45:00Z through 2023-07-28T20:00:00Z.

## Sensitivity population

The sensitivity population is the union of the following rules; counts overlap and therefore do not add arithmetically:

- `long_nonweekly_gap_boundary` (COV-ROW-008): 44 rows; 41 rows have only this condition
- `nonweekend_gap_boundary` (COV-ROW-009): 1,362 rows; 34 rows have only this condition
- `unclassified_gap_boundary` (COV-ROW-010): 58 rows; 14 rows have only this condition
- `continuity_impaired_period` (COV-PERIOD-001): 9,128 rows; 111 rows have only this condition
- `affected_period_2023` (COV-PERIOD-002): 9,258 rows; 239 rows have only this condition
- `partial_boundary_year` (COV-PERIOD-003): 37,010 rows; 33,156 rows have only this condition
- `partial_boundary_month` (COV-PERIOD-004): 3,837 rows; 0 rows have only this condition

Mutually exclusive rule combinations and the union total are retained in `coverage_summary.json` for exact reconciliation.

## Coverage profiles

| Profile | Included rows | Excluded rows | Included % |
|---|---:|---:|---:|
| FULL_DATASET | 406,945 | 0 | 100.000000 |
| DEFAULT_RESEARCH | 406,945 | 0 | 100.000000 |
| STRICT_CONTINUITY | 360,477 | 46,468 | 88.581258 |
| SENSITIVITY_FULL | 46,468 | 360,477 | 11.418742 |
| SENSITIVITY_2023 | 9,258 | 397,687 | 2.275000 |

Profile exclusions are masks, not deletions. The same registered rows remain available through `FULL_DATASET` and sensitivity profiles.

## Level semantics

- **row:** one observed raw CSV row; physical row number is retained
- **date:** one UTC date with observations; all-rules require every row and any-rules require at least one row
- **month:** one UTC month with observations; propagated from its observed rows
- **year:** one UTC year with observations; propagated from its observed rows
- **dataset:** the registered dataset; all-rules require every row and any-rules require at least one row

The CSV outputs contain aggregate flag and profile counts only; the package API builds the row/date/month/year/dataset masks on demand.
