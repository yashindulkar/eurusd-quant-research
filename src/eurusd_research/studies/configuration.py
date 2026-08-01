"""Strict configuration for Task 04."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import Field, StrictBool, model_validator

from eurusd_research.config import StrictModel
from eurusd_research.paths import find_repository_root


def _reject_ambiguous_numeric_values(
    value: Any,
    *,
    integer_fields: tuple[str, ...] = (),
    numeric_fields: tuple[str, ...] = (),
) -> Any:
    if not isinstance(value, dict):
        return value
    for field in integer_fields:
        item = value.get(field)
        if item is not None and (isinstance(item, bool) or not isinstance(item, int)):
            raise ValueError(f"{field} must be represented as an integer")
    for field in numeric_fields:
        item = value.get(field)
        if item is not None and (
            isinstance(item, bool) or not isinstance(item, (int, float))
        ):
            raise ValueError(f"{field} must be represented as a number")
    return value


class DailyCompletenessConfig(StrictModel):
    """Rules for deciding whether a profile-date is complete."""

    minimum_coverage_ratio: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)
    minimum_daily_rows: int = Field(gt=0)
    require_first_expected_interval: StrictBool
    require_last_expected_interval: StrictBool
    exclude_partial_days: StrictBool
    exclude_dataset_boundary_dates: StrictBool

    @model_validator(mode="before")
    @classmethod
    def reject_numeric_coercion(cls, value: Any) -> Any:
        return _reject_ambiguous_numeric_values(
            value,
            integer_fields=("minimum_daily_rows",),
            numeric_fields=("minimum_coverage_ratio",),
        )


class PeriodBoundariesConfig(StrictModel):
    """Fixed chronological robustness boundaries."""

    pre_2020_end_exclusive: str
    covid_start_inclusive: str
    covid_end_inclusive: str
    post_2021_start_inclusive: str


class FigureSettingsConfig(StrictModel):
    """Deterministic static-figure settings."""

    dpi: int = Field(ge=72, le=600)
    width_inches: float = Field(gt=0.0, allow_inf_nan=False)
    height_inches: float = Field(gt=0.0, allow_inf_nan=False)
    palette: tuple[str, ...] = Field(min_length=5)
    violin_bandwidth_method: Literal["scott", "silverman"]

    @model_validator(mode="before")
    @classmethod
    def reject_numeric_coercion(cls, value: Any) -> Any:
        return _reject_ambiguous_numeric_values(
            value,
            integer_fields=("dpi",),
            numeric_fields=("width_inches", "height_inches"),
        )


class EvidenceRatingConfig(StrictModel):
    """Result-independent thresholds governing the evidence classification."""

    moderate_minimum_epsilon_squared: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    strong_minimum_epsilon_squared: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    minimum_rank_correlation: float = Field(ge=-1.0, le=1.0, allow_inf_nan=False)
    strong_minimum_stable_year_fraction: float = Field(
        ge=0.0, le=1.0, allow_inf_nan=False
    )
    moderate_maximum_median_ci_relative_width: float = Field(
        gt=0.0, allow_inf_nan=False
    )
    strong_maximum_median_ci_relative_width: float = Field(gt=0.0, allow_inf_nan=False)
    minimum_primary_weekday_sample: int = Field(gt=0)
    minimum_regime_sample: int = Field(gt=0)
    diagnostic_profile_disagreement_blocks_strong: StrictBool
    high_regime_significance_role: Literal["contextual_only"]
    unresolved_timestamp_semantics_maximum_rating: Literal[
        "INSUFFICIENT", "WEAK", "MODERATE", "STRONG"
    ]

    @model_validator(mode="before")
    @classmethod
    def reject_numeric_coercion(cls, value: Any) -> Any:
        return _reject_ambiguous_numeric_values(
            value,
            integer_fields=(
                "minimum_primary_weekday_sample",
                "minimum_regime_sample",
            ),
            numeric_fields=(
                "moderate_minimum_epsilon_squared",
                "strong_minimum_epsilon_squared",
                "minimum_rank_correlation",
                "strong_minimum_stable_year_fraction",
                "moderate_maximum_median_ci_relative_width",
                "strong_maximum_median_ci_relative_width",
            ),
        )


class Task04Config(StrictModel):
    """Complete fail-closed configuration for the weekday-range study."""

    study_id: Literal["TASK-04"]
    registration_version: Literal["2.4"]
    method_id: Literal["RANGE-WEEKDAY-001"]
    method_version: Literal["range-weekday-registered-replication-v2.4"]
    implementation_version: str = Field(min_length=1)
    receipt_schema_version: Literal["task04-registration-receipt-v3"]
    lifecycle_schema_version: Literal["task04-registration-lifecycle-v3"]
    timezone: str
    pip_size: float = Field(gt=0.0, allow_inf_nan=False)
    weekday_inclusion: tuple[str, ...] = Field(min_length=5, max_length=5)
    primary_coverage_profile: Literal["DEFAULT_RESEARCH"]
    sensitivity_profiles: tuple[str, ...] = Field(min_length=3)
    daily_completeness: DailyCompletenessConfig
    minimum_yearly_weekday_sample: int = Field(gt=0)
    alpha: float = Field(gt=0.0, lt=1.0, allow_inf_nan=False)
    multiple_testing_method: Literal["holm"]
    primary_omnibus_test: Literal["kruskal_wallis"]
    post_hoc_test: Literal["dunn"]
    effect_size_methods: tuple[str, ...] = Field(min_length=4)
    confidence_level: float = Field(gt=0.0, lt=1.0, allow_inf_nan=False)
    bootstrap_seed: int = Field(ge=0)
    bootstrap_resamples: int = Field(ge=100)
    chronological_split_fraction: float = Field(gt=0.0, lt=1.0, allow_inf_nan=False)
    period_boundaries: PeriodBoundariesConfig
    volatility_lookback: int = Field(gt=1)
    volatility_minimum_history: int = Field(gt=1)
    regime_quantiles: tuple[float, float]
    winsorisation_limits: tuple[float, float]
    largest_tail_exclusion_fraction: float = Field(gt=0.0, lt=0.5, allow_inf_nan=False)
    quantile_method: Literal["numpy_linear"]
    variance_convention: Literal["sample_ddof_1"]
    mad_convention: Literal["unscaled_median_absolute_deviation"]
    timestamp_semantics_status: Literal["UNRESOLVED"]
    timestamp_operational_assumption: Literal["AS_SUPPLIED_TIMESTAMP_LABEL_DATE"]
    preregistration_path: Path
    registration_receipt_path: Path
    registration_lifecycle_path: Path
    source_dependency_manifest_path: Path
    environment_lock_path: Path
    task03_row_membership_evidence_path: Path
    coverage_summary_path: Path
    output_directory: Path
    candidate_output_directory: Path
    completion_sequence: tuple[str, ...] = Field(min_length=14, max_length=14)
    candidate_outputs_are_completed_evidence: Literal[False]
    output_digest_algorithm: Literal["task04-path-length-bytes-sha256-v1"]
    independent_reconciliation_implementation: Literal[
        "task04-independent-csv-reproduction-v1"
    ]
    maximum_numerical_discrepancy_tolerance: float = Field(ge=0.0, allow_inf_nan=False)
    minimum_branch_coverage_percent: float = Field(
        ge=90.0, le=100.0, allow_inf_nan=False
    )
    candidate_failure_policy: Literal[
        "FAILED_CANDIDATES_NEVER_CREATE_A_COMPLETED_LIFECYCLE"
    ]
    promotion_policy: Literal[
        "VALIDATE_CANDIDATE_THEN_ATOMICALLY_PROMOTE_ON_ONE_FILESYSTEM"
    ]
    required_completion_gates: tuple[str, ...] = Field(min_length=25)
    anchor_ancestry_policy: Literal[
        "COMPLETION_STATE_MUST_EQUAL_OR_DESCEND_FROM_ANCHOR"
    ]
    required_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_raw_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_task02_audit_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_coverage_summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_source_dependency_manifest_fingerprint: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    required_environment_lock_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_task03_row_membership_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_output_files: tuple[str, ...] = Field(min_length=1)
    expected_figure_files: tuple[str, ...] = Field(min_length=1)
    evidence_rating: EvidenceRatingConfig
    figure_settings: FigureSettingsConfig

    @model_validator(mode="before")
    @classmethod
    def reject_numeric_coercion(cls, value: Any) -> Any:
        checked = _reject_ambiguous_numeric_values(
            value,
            integer_fields=(
                "minimum_yearly_weekday_sample",
                "bootstrap_seed",
                "bootstrap_resamples",
                "volatility_lookback",
                "volatility_minimum_history",
            ),
            numeric_fields=(
                "pip_size",
                "alpha",
                "confidence_level",
                "chronological_split_fraction",
                "largest_tail_exclusion_fraction",
                "maximum_numerical_discrepancy_tolerance",
                "minimum_branch_coverage_percent",
            ),
        )
        if isinstance(checked, dict):
            for field in ("regime_quantiles", "winsorisation_limits"):
                items = checked.get(field)
                if items is not None and any(
                    isinstance(item, bool) or not isinstance(item, (int, float))
                    for item in items
                ):
                    raise ValueError(
                        f"{field} must contain only explicitly numeric values"
                    )
        return checked

    @model_validator(mode="after")
    def validate_design(self) -> Task04Config:
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Unknown IANA timezone: {self.timezone}") from error
        if self.timezone != "UTC":
            raise ValueError("Task 04 timezone must be UTC")
        expected_weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
        if self.weekday_inclusion != expected_weekdays:
            raise ValueError("Task 04 weekday order must be Monday through Friday")
        required_profiles = {
            "STRICT_CONTINUITY",
            "SENSITIVITY_FULL",
            "SENSITIVITY_2023",
        }
        if set(self.sensitivity_profiles) != required_profiles:
            raise ValueError("Task 04 sensitivity profiles are incomplete")
        if not 0.0 < self.regime_quantiles[0] < self.regime_quantiles[1] < 1.0:
            raise ValueError("regime_quantiles must be increasing inside (0, 1)")
        if not (
            0.0 < self.winsorisation_limits[0] < self.winsorisation_limits[1] < 1.0
        ):
            raise ValueError("winsorisation_limits must be increasing inside (0, 1)")
        paths = (
            self.preregistration_path,
            self.registration_receipt_path,
            self.registration_lifecycle_path,
            self.source_dependency_manifest_path,
            self.environment_lock_path,
            self.task03_row_membership_evidence_path,
            self.coverage_summary_path,
            self.output_directory,
            self.candidate_output_directory,
        )
        if any(path.is_absolute() or ".." in path.parts for path in paths):
            raise ValueError("Task 04 paths must be repository-relative")
        if self.candidate_output_directory == self.output_directory:
            raise ValueError("Candidate and final output directories must differ")
        if len(self.required_completion_gates) != len(
            set(self.required_completion_gates)
        ):
            raise ValueError("Task 04 completion gates contain duplicates")
        if self.volatility_minimum_history < self.volatility_lookback:
            raise ValueError("volatility minimum history must cover the lookback")
        if len(set(self.expected_output_files)) != len(self.expected_output_files):
            raise ValueError("Task 04 expected output files contain duplicates")
        if len(set(self.expected_figure_files)) != len(self.expected_figure_files):
            raise ValueError("Task 04 expected figure files contain duplicates")
        inventory = (*self.expected_output_files, *self.expected_figure_files)
        if any(
            Path(value).is_absolute() or ".." in Path(value).parts
            for value in inventory
        ):
            raise ValueError("Task 04 output inventory must be repository-relative")
        if any(Path(value).parent != Path(".") for value in inventory):
            raise ValueError(
                "Task 04 output inventory filenames must not add directories"
            )
        if self.evidence_rating.strong_minimum_epsilon_squared < (
            self.evidence_rating.moderate_minimum_epsilon_squared
        ):
            raise ValueError("Strong effect threshold must not be below moderate")
        if self.evidence_rating.strong_maximum_median_ci_relative_width > (
            self.evidence_rating.moderate_maximum_median_ci_relative_width
        ):
            raise ValueError("Strong CI threshold must not be wider than moderate")
        return self


def load_task04_config(root: Path | None = None) -> Task04Config:
    """Load the dedicated Task 04 YAML configuration."""
    repository_root = (root or find_repository_root()).resolve()
    path = repository_root / "configs" / "task04_daily_range_weekday.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Task 04 configuration not found: {path}")
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError("Task 04 configuration must be a mapping")
    return Task04Config.model_validate(value)
