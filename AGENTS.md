# Instructions for coding agents

## Before changing code

- Read `README.md` and the relevant files under `docs/`.
- Inspect existing package utilities and tests before creating new ones.
- Keep changes within the requested scope and avoid unrelated refactors.
- Prefer readable, deterministic, type-hinted code over clever abstractions.

## Data and research integrity

- Never modify, overwrite, reformat, sort, or clean files under `data/raw/`.
- Never silently remove observations. Document every exclusion and its count.
- Preserve lineage from every derived artifact to a registered raw checksum.
- Inspect reusable feature utilities before adding calculations; do not
  duplicate feature engineering.
- Avoid look-ahead bias and all forms of future leakage.
- Use timezone-aware timestamps throughout research code.
- Use IANA timezone names and daylight-saving-aware conversions.
- Never define sessions with fixed UTC offsets.
- Record research definitions in `docs/methodology_registry.md` before examining
  results when practical.

## Quality and handoff

- Add or update meaningful tests when behaviour changes.
- Run relevant tests, Ruff, and mypy before claiming completion.
- Update documentation when interfaces, assumptions, or behaviour change.
- Record material technical or methodological decisions in
  `docs/decision_log.md`.
- Report limitations, unresolved questions, and any checks not run.
