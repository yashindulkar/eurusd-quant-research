from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel, ValidationError

from eurusd_research.paths import find_repository_root
from eurusd_research.studies import registry as registry_module
from eurusd_research.studies.configuration import Task04Config, load_task04_config
from eurusd_research.studies.registry import (
    LOCKED_FIELDS,
    Task04Preregistration,
    assert_locked_fields_unchanged,
    assert_registration_matches_config,
    build_registration_receipt,
    executable_configuration_fingerprint,
    locked_design_fingerprint,
    read_preregistration,
)


def _contract() -> tuple[Path, Task04Config, Task04Preregistration]:
    root = find_repository_root()
    config = load_task04_config(root)
    registration, _ = read_preregistration(root / config.preregistration_path)
    return root, config, registration


def _changed(value: Any) -> Any:
    if isinstance(value, str):
        return value + "-changed"
    if isinstance(value, tuple):
        return (*value, "changed")
    if isinstance(value, dict):
        return {**value, "adversarial_change": True}
    raise TypeError(f"Unsupported fixture type: {type(value)}")


def _alter_config(config: Task04Config, path: str, value: object) -> Task04Config:
    parent, separator, child = path.partition(".")
    if not separator:
        return config.model_copy(update={parent: value})
    nested = getattr(config, parent)
    return config.model_copy(update={parent: nested.model_copy(update={child: value})})


def _preregistered(
    registration: Task04Preregistration,
) -> Task04Preregistration:
    return registration.model_copy(update={"status": "PREREGISTERED"})


def test_task04_config_and_registration_contract() -> None:
    root, config, registration = _contract()
    assert registration.status == "PREREGISTERED"
    assert registration.registration_version == config.registration_version == "2.8"
    assert_registration_matches_config(registration, config)
    assert len(locked_design_fingerprint(registration)) == 64
    assert len(executable_configuration_fingerprint(config)) == 64
    assert set(LOCKED_FIELDS) == set(Task04Preregistration.model_fields).difference(
        {"status"}
    )
    assert (root / "studies" / "task04_development_baseline.json").is_file()


def test_v28_preserves_v27_scientific_design_exactly() -> None:
    root = find_repository_root()
    with (root / "studies/task04_daily_range_weekday.v2.7.yaml").open(
        encoding="utf-8"
    ) as handle:
        v27 = yaml.safe_load(handle)
    with (root / "studies/task04_daily_range_weekday.v2.8.yaml").open(
        encoding="utf-8"
    ) as handle:
        v28 = yaml.safe_load(handle)
    scientific_fields = (
        "research_question",
        "primary_null_hypothesis",
        "primary_alternative_hypothesis",
        "secondary_hypotheses",
        "primary_outcome",
        "unit_of_analysis",
        "calendar_definition",
        "weekday_definition",
        "timestamp_semantics",
        "primary_coverage_profile",
        "sensitivity_profiles",
        "daily_completeness_rule",
        "boundary_period_policy",
        "descriptive_statistics",
        "statistical_conventions",
        "primary_statistical_test",
        "post_hoc_test",
        "multiple_testing_correction",
        "effect_size_measures",
        "confidence_interval_method",
        "normality_diagnostic",
        "variance_diagnostic",
        "robustness_analyses",
        "volatility_regime_definition",
        "chronological_stability_design",
        "missing_data_policy",
        "exclusion_policy",
        "deterministic_seed_policy",
        "evidence_rating",
        "known_limitations",
        "prohibited_analyses",
    )
    assert {field: v28[field] for field in scientific_fields} == {
        field: v27[field] for field in scientific_fields
    }
    assert v28["expected_outputs"]["files"] == v27["expected_outputs"]["files"]
    assert v28["expected_outputs"]["figures"] == v27["expected_outputs"]["figures"]
    assert (
        v28["expected_outputs"]["figure_settings"]
        == (v27["expected_outputs"]["figure_settings"])
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("timezone", "Europe/Berlin", "must be UTC"),
        ("weekday_inclusion", ("Friday",) * 5, "Monday through Friday"),
        ("sensitivity_profiles", ("STRICT_CONTINUITY",) * 3, "incomplete"),
        ("regime_quantiles", (0.8, 0.2), "increasing"),
        ("winsorisation_limits", (0.99, 0.01), "increasing"),
        ("output_directory", Path("/tmp/absolute"), "repository-relative"),
        ("registration_receipt_path", Path("../escape.json"), "repository-relative"),
        ("volatility_minimum_history", 2, "cover the lookback"),
        (
            "expected_output_files",
            ("duplicate.csv", "duplicate.csv"),
            "duplicates",
        ),
    ],
)
def test_task04_config_fails_closed(field: str, value: object, message: str) -> None:
    values = load_task04_config().model_dump(mode="python")
    values[field] = value
    with pytest.raises(ValidationError, match=message):
        Task04Config.model_validate(values)


def test_every_semantic_registration_field_changes_fingerprint() -> None:
    _, _, registration = _contract()
    baseline = locked_design_fingerprint(registration)
    values = registration.model_dump(mode="python")
    for field in LOCKED_FIELDS:
        changed = registration.model_copy(update={field: _changed(values[field])})
        assert locked_design_fingerprint(changed) != baseline, field
    assert (
        locked_design_fingerprint(
            registration.model_copy(update={"status": "PREREGISTERED"})
        )
        == baseline
    )
    values = registration.model_dump(mode="python")
    values["preregistration_deviations"] = [{"deviation_id": "forbidden"}]
    with pytest.raises(ValidationError):
        Task04Preregistration.model_validate(values)


def test_canonical_ordering_semantics_and_unknown_fields() -> None:
    _, _, registration = _contract()
    outputs = dict(registration.expected_outputs)
    outputs["files"] = tuple(reversed(outputs["files"]))
    outputs["figures"] = tuple(reversed(outputs["figures"]))
    reordered_inventory = registration.model_copy(update={"expected_outputs": outputs})
    assert locked_design_fingerprint(reordered_inventory) == locked_design_fingerprint(
        registration
    )
    reordered_hypotheses = registration.model_copy(
        update={
            "secondary_hypotheses": tuple(reversed(registration.secondary_hypotheses))
        }
    )
    assert locked_design_fingerprint(reordered_hypotheses) != (
        locked_design_fingerprint(registration)
    )
    values = registration.model_dump(mode="python")
    values["unknown_field"] = True
    with pytest.raises(ValidationError, match="Extra inputs"):
        Task04Preregistration.model_validate(values)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("study_id", "OTHER"),
        ("registration_version", "9.0"),
        ("method_id", "OTHER"),
        ("method_version", "other-version"),
        ("implementation_version", "other-implementation"),
        ("required_raw_sha256", "b" * 64),
        ("required_raw_manifest_sha256", "b" * 64),
        ("required_task02_audit_fingerprint", "b" * 64),
        ("required_coverage_summary_stable_sha256", "b" * 64),
        ("timezone", "Europe/Berlin"),
        ("pip_size", 0.001),
        (
            "weekday_inclusion",
            ("Tuesday", "Monday", "Wednesday", "Thursday", "Friday"),
        ),
        ("timestamp_semantics_status", "RESOLVED"),
        ("timestamp_operational_assumption", "OTHER"),
        ("primary_coverage_profile", "STRICT_CONTINUITY"),
        (
            "sensitivity_profiles",
            ("STRICT_CONTINUITY", "SENSITIVITY_FULL", "OTHER"),
        ),
        ("daily_completeness.minimum_coverage_ratio", 0.99),
        ("daily_completeness.minimum_daily_rows", 2),
        ("daily_completeness.require_first_expected_interval", False),
        ("daily_completeness.require_last_expected_interval", False),
        ("daily_completeness.exclude_partial_days", False),
        ("daily_completeness.exclude_dataset_boundary_dates", False),
        ("minimum_yearly_weekday_sample", 30),
        ("alpha", 0.99),
        ("multiple_testing_method", "none"),
        ("primary_omnibus_test", "anova"),
        ("post_hoc_test", "tukey"),
        ("effect_size_methods", ("epsilon_squared",)),
        ("confidence_level", 0.90),
        ("bootstrap_seed", 1),
        ("bootstrap_resamples", 100),
        ("quantile_method", "other"),
        ("variance_convention", "other"),
        ("mad_convention", "other"),
        ("chronological_split_fraction", 0.60),
        ("period_boundaries.pre_2020_end_exclusive", "2019-01-01"),
        ("period_boundaries.covid_start_inclusive", "2019-01-01"),
        ("period_boundaries.covid_end_inclusive", "2020-01-01"),
        ("period_boundaries.post_2021_start_inclusive", "2020-01-02"),
        ("volatility_lookback", 30),
        ("volatility_minimum_history", 60),
        ("regime_quantiles", (0.25, 0.75)),
        ("winsorisation_limits", (0.02, 0.98)),
        ("largest_tail_exclusion_fraction", 0.02),
        ("evidence_rating.moderate_minimum_epsilon_squared", 0.02),
        ("evidence_rating.strong_minimum_epsilon_squared", 0.07),
        ("evidence_rating.minimum_rank_correlation", 0.70),
        ("evidence_rating.strong_minimum_stable_year_fraction", 0.80),
        ("evidence_rating.moderate_maximum_median_ci_relative_width", 0.30),
        ("evidence_rating.strong_maximum_median_ci_relative_width", 0.10),
        ("evidence_rating.minimum_primary_weekday_sample", 101),
        ("evidence_rating.diagnostic_profile_disagreement_blocks_strong", True),
        ("evidence_rating.unresolved_timestamp_semantics_maximum_rating", "WEAK"),
        ("output_directory", Path("reports/research/other")),
        ("expected_output_files", ("only.csv",)),
        ("expected_figure_files", ("only.png",)),
        ("figure_settings.dpi", 199),
        ("figure_settings.width_inches", 13.0),
        ("figure_settings.height_inches", 9.0),
        ("figure_settings.palette", ("#000000",) * 5),
        ("figure_settings.violin_bandwidth_method", "silverman"),
    ],
)
def test_each_executable_setting_contradiction_fails(path: str, value: object) -> None:
    _, config, registration = _contract()
    altered = _alter_config(config, path, value)
    with pytest.raises(ValueError, match="configuration disagree"):
        assert_registration_matches_config(registration, altered)


def test_unordered_output_inventory_order_does_not_contradict_registration() -> None:
    _, config, registration = _contract()
    altered = config.model_copy(
        update={
            "expected_output_files": tuple(reversed(config.expected_output_files)),
            "expected_figure_files": tuple(reversed(config.expected_figure_files)),
        }
    )
    assert_registration_matches_config(registration, altered)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("alpha", "0.05"),
        ("bootstrap_resamples", 10_000.0),
        ("regime_quantiles", ("0.33", 0.67)),
        ("daily_completeness.minimum_coverage_ratio", "1.0"),
        ("figure_settings.dpi", 200.0),
        ("evidence_rating.minimum_primary_weekday_sample", "100"),
    ],
)
def test_ambiguous_numeric_coercion_is_rejected(path: str, value: object) -> None:
    values = load_task04_config().model_dump(mode="python")
    parent, separator, child = path.partition(".")
    if separator:
        values[parent][child] = value
    else:
        values[parent] = value
    with pytest.raises(ValidationError, match=r"represented|explicitly numeric"):
        Task04Config.model_validate(values)


def test_receipt_creation_validates_live_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, config, registration = _contract()

    def fail_dependency_validation(*_args: object, **_kwargs: object) -> None:
        raise ValueError("Task 03 stable coverage-summary fingerprint is stale")

    monkeypatch.setattr(
        registry_module,
        "validate_task04_dependencies",
        fail_dependency_validation,
    )
    with pytest.raises(ValueError, match="stable coverage-summary fingerprint"):
        build_registration_receipt(_preregistered(registration), config, root=root)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_registration_numbers_fail(bad: float) -> None:
    _, _, registration = _contract()
    values = registration.model_dump(mode="python")
    values["primary_outcome"]["pip_size"] = bad
    with pytest.raises(ValidationError):
        Task04Preregistration.model_validate(values)


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("primary_outcome", "significance_level"),
        ("calendar_definition", "time_zone"),
        ("primary_statistical_test", "significance_level"),
        ("confidence_interval_method", "bootstrap_samples"),
        ("volatility_regime_definition", "lookback"),
        ("evidence_rating", "result_specific_override"),
        ("repository_lineage", "mutable_anchor_file"),
        ("deviation_policy", "appendable"),
    ],
)
def test_unknown_nested_registration_keys_fail(section: str, field: str) -> None:
    _, _, registration = _contract()
    values = registration.model_dump(mode="python")
    values[section][field] = "forbidden"
    with pytest.raises(ValidationError, match="Extra inputs"):
        Task04Preregistration.model_validate(values)


@pytest.mark.parametrize(
    ("section", "field", "bad"),
    [
        ("primary_statistical_test", "alpha", "0.05"),
        ("confidence_interval_method", "resamples", 2000.0),
        ("confidence_interval_method", "seed", "20260727"),
        ("calendar_definition", "local_session_or_rollover_used", 0),
        ("daily_completeness_rule", "minimum_daily_rows", 1.0),
        ("daily_completeness_rule", "require_all_expected_intervals", "true"),
        ("evidence_rating", "thresholds", None),
    ],
)
def test_registration_rejects_coercion_null_and_numeric_strings(
    section: str, field: str, bad: object
) -> None:
    _, _, registration = _contract()
    values = registration.model_dump(mode="python")
    values[section][field] = bad
    with pytest.raises(ValidationError):
        Task04Preregistration.model_validate(values)


def test_same_version_deviations_are_forbidden() -> None:
    _, _, registration = _contract()
    values = registration.model_dump(mode="python")
    values["preregistration_deviations"] = [{"affected_field": "alpha"}]
    with pytest.raises(ValidationError):
        Task04Preregistration.model_validate(values)


def _nested_model_paths(
    model: BaseModel, prefix: tuple[str, ...] = ()
) -> list[tuple[str, ...]]:
    paths: list[tuple[str, ...]] = []
    for field in model.__class__.model_fields:
        value = getattr(model, field)
        if isinstance(value, BaseModel):
            path = (*prefix, field)
            paths.append(path)
            paths.extend(_nested_model_paths(value, path))
    return paths


def _mapping_at(values: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    current = values
    for part in path:
        current = current[part]
    return current


def test_every_nested_semantic_model_rejects_unknown_missing_and_null() -> None:
    _, _, registration = _contract()
    paths = _nested_model_paths(registration)
    assert len(paths) >= 25
    for path in paths:
        base = registration.model_dump(mode="python")
        target = _mapping_at(base, path)
        target["unknown_semantic_alias"] = "forbidden"
        with pytest.raises(ValidationError):
            Task04Preregistration.model_validate(base)

        missing = registration.model_dump(mode="python")
        missing_target = _mapping_at(missing, path)
        required_field = next(iter(missing_target))
        missing_target.pop(required_field)
        with pytest.raises(ValidationError):
            Task04Preregistration.model_validate(missing)

        null = registration.model_dump(mode="python")
        null_target = _mapping_at(null, path)
        null_target[required_field] = None
        with pytest.raises(ValidationError):
            Task04Preregistration.model_validate(null)


def test_nested_numeric_collections_reject_strings_and_non_finite_values() -> None:
    _, _, registration = _contract()
    cases = [
        (
            ("exclusion_policy", "winsorisation_limits"),
            ["0.01", 0.99],
        ),
        (
            ("volatility_regime_definition", "low_quantile"),
            float("nan"),
        ),
        (
            ("evidence_rating", "thresholds", "minimum_rank_correlation"),
            float("inf"),
        ),
        (
            ("expected_outputs", "figure_settings", "width_inches"),
            float("-inf"),
        ),
    ]
    for path, bad in cases:
        values = deepcopy(registration.model_dump(mode="python"))
        parent = values
        for part in path[:-1]:
            parent = parent[part]
        parent[path[-1]] = bad
        with pytest.raises(ValidationError):
            Task04Preregistration.model_validate(values)


def test_locked_field_assertion() -> None:
    _, _, registration = _contract()
    changed = registration.model_copy(
        update={"research_question": "A changed post-result question"}
    )
    with pytest.raises(ValueError, match="Locked preregistration fields changed"):
        assert_locked_fields_unchanged(registration, changed)
