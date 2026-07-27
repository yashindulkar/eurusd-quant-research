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
