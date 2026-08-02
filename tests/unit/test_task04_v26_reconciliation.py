from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest

from eurusd_research.studies import independent_reconciliation
from eurusd_research.studies.independent_inventory import inspect_output_inventory
from eurusd_research.studies.reconciliation_schema import (
    REGIME_LINEAGE_COMPARISON_COLUMNS,
    CandidateCsvSchema,
    canonical_exclusion_reasons,
    canonical_registered_output_paths,
    load_candidate_csv,
    project_registered_regime_lineage,
)


def test_v26_uses_schema_driven_candidate_csv_loading() -> None:
    source = inspect.getsource(
        independent_reconciliation.build_independent_reconciliation
    )
    assert "load_candidate_csv" in source


def test_v26_projects_registered_regime_lineage_schema() -> None:
    source = inspect.getsource(
        independent_reconciliation.build_independent_reconciliation
    )
    assert "project_registered_regime_lineage" in source


def test_v26_uses_canonical_registered_output_paths() -> None:
    source = inspect.getsource(
        independent_reconciliation.build_independent_reconciliation
    )
    assert "canonical_registered_output_paths" in source


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("", True),
        ("weekend_utc_date", True),
        ("weekend_utc_date|dataset_boundary_date", True),
        (None, False),
        (" ", False),
        ("weekend_utc_date ", False),
        ("dataset_boundary_date|weekend_utc_date", False),
        ("weekend_utc_date||dataset_boundary_date", False),
        ("unknown", False),
    ],
)
def test_exclusion_reason_canonical_form(value: object, valid: bool) -> None:
    if valid:
        assert canonical_exclusion_reasons(value) == value
    else:
        with pytest.raises(ValueError):
            canonical_exclusion_reasons(value)


def test_schema_loader_preserves_empty_exclusion_reason_only(tmp_path: Path) -> None:
    path = tmp_path / "candidate.csv"
    path.write_text('utc_date,exclusion_reasons,value,note\n2020-01-06,"",1,\n')
    schema = CandidateCsvSchema(
        required_columns=("utc_date", "exclusion_reasons", "value", "note"),
        empty_string_columns=("exclusion_reasons",),
        nullable_columns=("note",),
        numeric_columns=("value",),
        date_columns=("utc_date",),
    )
    loaded = load_candidate_csv(path, schema)
    assert loaded.loc[0, "exclusion_reasons"] == ""
    assert pd.isna(loaded.loc[0, "note"])


def test_schema_loader_rejects_missing_reordered_and_extra_columns(
    tmp_path: Path,
) -> None:
    schema = CandidateCsvSchema(required_columns=("a", "b"))
    for text in ("a\n1\n", "b,a\n2,1\n", "a,b,c\n1,2,3\n"):
        path = tmp_path / "candidate.csv"
        path.write_text(text)
        with pytest.raises(ValueError):
            load_candidate_csv(path, schema)


def _lineage_row() -> dict[str, object]:
    return {
        "utc_date": "2020-01-06",
        "profile": "DEFAULT_RESEARCH",
        "daily_range_pips": 10.0,
        "lagged_trailing_median_range_pips": None,
        "prior_regime_measure_count": 0,
        "past_only_low_threshold": None,
        "past_only_high_threshold": None,
        "volatility_regime": "WARMUP",
        "regime_warmup": True,
        "regime_classification_reason": "insufficient_history",
        "volatility_lookback": 180,
        "volatility_minimum_history": 180,
    }


def test_regime_projection_accepts_wider_frame_and_orders_contract() -> None:
    row = _lineage_row()
    frame = pd.DataFrame([{**row, "independent_working_value": 1}])
    projected = project_registered_regime_lineage(frame)
    assert tuple(projected.columns) == REGIME_LINEAGE_COMPARISON_COLUMNS


def test_regime_projection_rejects_missing_field_and_duplicate_key() -> None:
    row = _lineage_row()
    with pytest.raises(ValueError, match="missing registered fields"):
        project_registered_regime_lineage(
            pd.DataFrame([{k: v for k, v in row.items() if k != "volatility_regime"}])
        )
    with pytest.raises(ValueError, match="duplicate"):
        project_registered_regime_lineage(pd.DataFrame([row, row]))


def test_regime_projection_exposes_label_threshold_history_and_warmup_defects() -> None:
    expected = project_registered_regime_lineage(pd.DataFrame([_lineage_row()]))
    for field, value in (
        ("volatility_regime", "LOW"),
        ("past_only_low_threshold", 5.0),
        ("prior_regime_measure_count", 1),
        ("regime_warmup", False),
    ):
        changed = _lineage_row()
        changed[field] = value
        comparison = independent_reconciliation.compare_frames(
            expected,
            project_registered_regime_lineage(pd.DataFrame([changed])),
            keys=("utc_date", "profile"),
            label="regime_lineage",
        )
        assert (
            comparison.categorical_mismatches > 0
            or max(comparison.absolute.values(), default=0.0) > 0.0
        )


def test_registered_output_paths_require_nested_figure_prefix() -> None:
    assert canonical_registered_output_paths(
        ("study_summary.json",), ("01_weekday_boxplot.png",)
    ) == ("figures/01_weekday_boxplot.png", "study_summary.json")
    for roots, figures in (
        (("01_weekday_boxplot.png",), ()),
        (("../study_summary.json",), ()),
        (("nested/file.csv",), ()),
        (("A.csv", "a.csv"), ()),
        (("a\\b.csv",), ()),
        ((), ("figures/01.png",)),
    ):
        with pytest.raises(ValueError):
            canonical_registered_output_paths(roots, figures)


def test_inventory_detects_missing_extra_and_changed_figure(tmp_path: Path) -> None:
    figures = tmp_path / "figures"
    figures.mkdir()
    figure = figures / "01.png"
    figure.write_bytes(b"first")
    expected = ("figures/01.png", "summary.json")
    missing = inspect_output_inventory(tmp_path, expected)
    assert missing.missing_paths == ("summary.json",)
    (tmp_path / "summary.json").write_text("{}")
    baseline = inspect_output_inventory(tmp_path, expected)
    assert baseline.reconciled
    figure.write_bytes(b"second")
    changed = inspect_output_inventory(tmp_path, expected)
    assert changed.reconciled
    assert changed.path_plus_bytes_digest != baseline.path_plus_bytes_digest
    (tmp_path / "extra.csv").write_text("x")
    assert inspect_output_inventory(tmp_path, expected).extra_paths == ("extra.csv",)
