"""Strict v2.5 semantic registration models for Task 04."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, StrictBool, StrictInt, model_validator

from eurusd_research.config import StrictModel

FiniteFloat = Annotated[float, Field(strict=True, allow_inf_nan=False)]
PositiveFiniteFloat = Annotated[float, Field(strict=True, allow_inf_nan=False, gt=0.0)]
Probability = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=1.0)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
GitCommit = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
NonEmpty = Annotated[str, Field(min_length=1)]


class FrozenSection(StrictModel):
    """Unknown-key rejecting immutable semantic section."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PrimaryOutcome(FrozenSection):
    name: Literal["daily_range_pips"]
    definition: NonEmpty
    reporting_unit: Literal["pips"]
    pip_size: PositiveFiniteFloat


class CalendarDefinition(FrozenSection):
    timezone: Literal["UTC"]
    utc_day_start_inclusive: Literal["00:00:00"]
    utc_day_end_inclusive: Literal["23:59:59.999999"]
    local_session_or_rollover_used: StrictBool


class WeekdayDefinition(FrozenSection):
    source: Literal["UTC calendar date"]
    primary_weekdays: tuple[
        Literal["Monday"],
        Literal["Tuesday"],
        Literal["Wednesday"],
        Literal["Thursday"],
        Literal["Friday"],
    ]
    excluded_weekdays: tuple[Literal["Saturday"], Literal["Sunday"]]
    weekend_dates_remain_traceable: StrictBool


class TimestampSemantics(FrozenSection):
    authoritative_status: Literal["UNRESOLVED"]
    operational_assumption: Literal["AS_SUPPLIED_TIMESTAMP_LABEL_DATE"]
    interpretation: NonEmpty
    possible_boundary_consequence: NonEmpty
    evidence_rating_cap: Literal["MODERATE"]
    source_evidence: Literal["reports/audits/raw_data_quality_report.md"]


class SensitivityProfiles(FrozenSection):
    required: tuple[Literal["STRICT_CONTINUITY"]]
    diagnostic: tuple[Literal["SENSITIVITY_FULL"], Literal["SENSITIVITY_2023"]]


class DailyCompletenessRule(FrozenSection):
    row_population_built_before_aggregation: StrictBool
    minimum_coverage_ratio: Probability
    minimum_daily_rows: StrictInt = Field(gt=0)
    require_first_expected_interval: StrictBool
    require_last_expected_interval: StrictBool
    require_all_expected_intervals: StrictBool
    monday_through_thursday_expected_grid: NonEmpty
    friday_expected_grid: NonEmpty
    sunday_expected_grid: NonEmpty
    saturday_policy: NonEmpty
    unresolved_weekly_boundary_policy: NonEmpty
    partial_days_in_primary_analysis: StrictBool
    partial_days_in_sensitivity_analysis: StrictBool
    exclude_dataset_boundary_dates: StrictBool


class BoundaryPeriodPolicy(FrozenSection):
    first_observed_utc_date: NonEmpty
    final_observed_utc_date: NonEmpty
    partial_boundary_years: NonEmpty


class StatisticalConventions(FrozenSection):
    quantile_method: Literal["numpy_linear"]
    variance_convention: Literal["sample_ddof_1"]
    mad_convention: Literal["unscaled_median_absolute_deviation"]


class PrimaryStatisticalTest(FrozenSection):
    name: Literal["Kruskal-Wallis"]
    implementation_id: Literal["kruskal_wallis"]
    groups: tuple[
        Literal["Monday"],
        Literal["Tuesday"],
        Literal["Wednesday"],
        Literal["Thursday"],
        Literal["Friday"],
    ]
    alpha: Probability


class PostHocTest(FrozenSection):
    name: Literal["Dunn pairwise rank comparison"]
    implementation_id: Literal["dunn"]
    comparisons: Literal["all_ten_weekday_pairs"]


class MultipleTestingCorrection(FrozenSection):
    method: Literal["Holm"]
    implementation_id: Literal["holm"]
    family: Literal["ten_weekday_pairwise_comparisons_within_each_analysis_population"]


class MagnitudeConventions(FrozenSection):
    negligible: NonEmpty
    small: NonEmpty
    medium: NonEmpty
    large: NonEmpty


class EffectSizeMeasures(FrozenSection):
    implementation_ids: tuple[
        Literal["epsilon_squared"],
        Literal["eta_squared"],
        Literal["omega_squared"],
        Literal["cliffs_delta"],
    ]
    omnibus_nonparametric: Literal["epsilon_squared"]
    omnibus_parametric: tuple[Literal["eta_squared"], Literal["omega_squared"]]
    pairwise: Literal["cliffs_delta"]
    magnitude_conventions: MagnitudeConventions
    interpretation_note: NonEmpty


class ConfidenceIntervalMethod(FrozenSection):
    mean: Literal["deterministic percentile bootstrap"]
    median: Literal["deterministic percentile bootstrap"]
    pairwise_median_difference: Literal["deterministic percentile bootstrap"]
    confidence_level: Probability
    seed: StrictInt = Field(ge=0)
    resamples: StrictInt = Field(ge=100)
    dependence_limitation: NonEmpty


class NormalityDiagnostic(FrozenSection):
    methods: tuple[
        Literal["skewness"],
        Literal["excess_kurtosis"],
        Literal["qq_plot_correlation"],
    ]
    mechanical_pass_fail_gate: StrictBool


class VarianceDiagnostic(FrozenSection):
    method: Literal["Brown-Forsythe Levene test centered on median"]
    complementary_tests: tuple[Literal["one_way_anova"], Literal["welch_anova"]]


class VolatilityRegimeDefinition(FrozenSection):
    base_measure: Literal["trailing median daily_range_pips"]
    lookback_eligible_weekdays: StrictInt = Field(gt=1)
    current_date_excluded: StrictBool
    future_information_used: StrictBool
    threshold_history: NonEmpty
    minimum_prior_regime_measures: StrictInt = Field(gt=1)
    low_quantile: Probability
    high_quantile: Probability
    labels: tuple[Literal["LOW"], Literal["MEDIUM"], Literal["HIGH"]]
    warmup_label: Literal["UNCLASSIFIED"]

    @model_validator(mode="after")
    def validate_quantiles(self) -> VolatilityRegimeDefinition:
        if not 0.0 < self.low_quantile < self.high_quantile < 1.0:
            raise ValueError("Registered regime quantiles must be increasing")
        return self


class ChronologicalPeriods(FrozenSection):
    full_eligible_sample: NonEmpty
    pre_2020: NonEmpty
    covid_era: NonEmpty
    post_2021: NonEmpty


class PeriodBoundaries(FrozenSection):
    pre_2020_end_exclusive: Literal["2020-01-01"]
    covid_start_inclusive: Literal["2020-01-01"]
    covid_end_inclusive: Literal["2021-12-31"]
    post_2021_start_inclusive: Literal["2022-01-01"]


class ChronologicalStabilityDesign(FrozenSection):
    periods: ChronologicalPeriods
    period_boundaries: PeriodBoundaries
    development_fraction: Probability
    split_basis: Literal["ordered eligible UTC dates"]
    shuffle: StrictBool
    validation_may_change_design: StrictBool
    minimum_per_weekday_per_year: StrictInt = Field(gt=0)


class ExclusionPolicy(FrozenSection):
    primary: tuple[str, ...] = Field(min_length=4, max_length=4)
    outliers: Literal["retained in primary analysis"]
    reversible_sensitivity_only: tuple[
        Literal["winsorisation"], Literal["largest_one_percent_exclusion"]
    ]
    winsorisation_limits: tuple[Probability, Probability]
    largest_tail_exclusion_fraction: Probability

    @model_validator(mode="after")
    def validate_limits(self) -> ExclusionPolicy:
        low, high = self.winsorisation_limits
        if not 0.0 < low < high < 1.0:
            raise ValueError("Registered winsorisation limits must be increasing")
        if not 0.0 < self.largest_tail_exclusion_fraction < 0.5:
            raise ValueError("Registered tail exclusion must be inside (0, 0.5)")
        return self


class DeterministicSeedPolicy(FrozenSection):
    seed: StrictInt = Field(ge=0)
    algorithm: Literal["numpy Generator PCG64"]
    parallel_random_resampling: StrictBool


class Task02Dependency(FrozenSection):
    method_version: Literal["raw-data-quality-audit-v2"]
    normalized_result_fingerprint: Sha256
    gap_table_fingerprint: Sha256
    monthly_table_fingerprint: Sha256


class Task03Dependency(FrozenSection):
    architecture: Literal["DESIGN_B_REBUILD_AND_RECONCILE_EXACTLY"]
    method_id: Literal["COVERAGE-001"]
    method_version: Literal["research-coverage-v1"]
    coverage_config_fingerprint: Sha256
    coverage_summary_file_fingerprint: Sha256
    row_membership_evidence_path: Literal[
        "studies/task03_task04_v2.5_mask_evidence.json"
    ]
    row_membership_evidence_fingerprint: Sha256


class FigureSettings(FrozenSection):
    dpi: StrictInt = Field(ge=72, le=600)
    width_inches: PositiveFiniteFloat
    height_inches: PositiveFiniteFloat
    palette: tuple[str, ...] = Field(min_length=5, max_length=5)
    violin_bandwidth_method: Literal["scott"]


class ExpectedOutputs(FrozenSection):
    directory: Literal["reports/research/task04_daily_range_weekday_v2.5"]
    files: tuple[str, ...] = Field(min_length=20, max_length=20)
    figures: tuple[str, ...] = Field(min_length=8, max_length=8)
    figure_settings: FigureSettings

    @model_validator(mode="after")
    def validate_inventory(self) -> ExpectedOutputs:
        inventory = (*self.files, *self.figures)
        if len(inventory) != len(set(inventory)):
            raise ValueError("Registered output inventory contains duplicates")
        return self


class EvidenceThresholds(FrozenSection):
    moderate_minimum_epsilon_squared: Probability
    strong_minimum_epsilon_squared: Probability
    minimum_rank_correlation: FiniteFloat = Field(ge=-1.0, le=1.0)
    strong_minimum_stable_year_fraction: Probability
    moderate_maximum_median_ci_relative_width: PositiveFiniteFloat
    strong_maximum_median_ci_relative_width: PositiveFiniteFloat
    minimum_primary_weekday_sample: StrictInt = Field(gt=0)
    minimum_regime_sample: StrictInt = Field(gt=0)
    diagnostic_profile_disagreement_blocks_strong: StrictBool
    unresolved_timestamp_semantics_maximum_rating: Literal["MODERATE"]
    high_regime_significance_role: Literal["contextual_only"]


class EvidenceRating(FrozenSection):
    scale: tuple[
        Literal["INSUFFICIENT"],
        Literal["WEAK"],
        Literal["MODERATE"],
        Literal["STRONG"],
    ]
    dimensions: tuple[str, ...] = Field(min_length=8, max_length=8)
    thresholds: EvidenceThresholds
    required_profiles: tuple[Literal["DEFAULT_RESEARCH"], Literal["STRICT_CONTINUITY"]]
    diagnostic_profiles: tuple[Literal["SENSITIVITY_FULL"], Literal["SENSITIVITY_2023"]]
    required_periods: tuple[
        Literal["full_eligible_sample"],
        Literal["pre_2020"],
        Literal["covid_era"],
        Literal["post_2021"],
        Literal["development_70"],
        Literal["validation_30"],
    ]
    required_regimes: tuple[Literal["LOW"], Literal["MEDIUM"], Literal["HIGH"]]
    required_evidence_artifacts: tuple[str, ...] = Field(min_length=7)
    contradictory_evidence_policy: NonEmpty
    missing_evidence_policy: Literal[
        "Any missing, empty, malformed, non-finite, contradictory, or "
        "sample-insufficient required evidence produces INSUFFICIENT."
    ]
    logic: NonEmpty


class RepositoryLineage(FrozenSection):
    baseline_head: GitCommit
    development_baseline_path: Literal["studies/task04_development_baseline.json"]
    registration_receipt_path: Literal[
        "studies/task04_daily_range_weekday.v2.5.receipt.json"
    ]
    registration_lifecycle_path: Literal[
        "studies/task04_daily_range_weekday.v2.5.lifecycle.json"
    ]
    source_manifest_path: Literal["studies/task04_v2.5_source_manifest.json"]
    environment_lock_path: Literal["studies/task04_v2.5_environment_lock.json"]
    raw_path: Literal["data/raw/EURUSD_M15_UTC.csv"]
    manifest_path: Literal["reports/audits/raw_dataset_manifest.json"]
    task_02_result_path: Literal["reports/audits/raw_data_quality_audit.json"]
    task_03_result_path: Literal["reports/coverage/coverage_summary.json"]
    registered_path_inventory: tuple[str, ...] = Field(min_length=1)
    dirty_state_policy: NonEmpty


class DeviationPolicy(FrozenSection):
    model: Literal["NEW_REGISTRATION_VERSION_REQUIRED"]
    post_anchor_scientific_changes_permitted: StrictBool
    same_version_append_only_ledger_supported: StrictBool
    rule: NonEmpty


class ProductionGovernance(FrozenSection):
    """Pre-result v2.5 orchestration and completion contract."""

    receipt_schema_version: Literal["task04-registration-receipt-v4"]
    lifecycle_schema_version: Literal["task04-registration-lifecycle-v4"]
    completion_sequence: tuple[
        Literal["validate_anchor"],
        Literal["create_receipt"],
        Literal["validate_receipt"],
        Literal["validate_pre_generation_dependencies"],
        Literal["generate_candidate_outputs"],
        Literal["validate_candidate_outputs"],
        Literal["independent_population_reconciliation"],
        Literal["independent_statistical_reproduction"],
        Literal["deterministic_regeneration"],
        Literal["figure_validation"],
        Literal["run_required_quality_gates"],
        Literal["promote_final_outputs"],
        Literal["create_completed_lifecycle"],
        Literal["validate_completed_lifecycle"],
    ]
    candidate_output_directory: Literal["reports/research/.task04_v2.5_candidate"]
    final_output_directory: Literal["reports/research/task04_daily_range_weekday_v2.5"]
    candidate_outputs_are_completed_evidence: Literal[False]
    output_digest_algorithm: Literal["task04-path-length-bytes-sha256-v1"]
    independent_reconciliation_implementation: Literal[
        "task04-independent-full-reproduction-v2"
    ]
    independent_reconciliation_components: tuple[str, ...] = Field(
        min_length=12, max_length=12
    )
    required_checked_statistics: tuple[str, ...] = Field(min_length=4)
    required_checked_robustness: tuple[str, ...] = Field(min_length=5)
    required_checked_output_evidence: tuple[str, ...] = Field(min_length=4)
    categorical_mismatch_tolerance: Literal[0]
    membership_mismatch_tolerance: Literal[0]
    inventory_mismatch_tolerance: Literal[0]
    unchecked_component_policy: Literal["NOT_CHECKED_CAUSES_OVERALL_FAILURE"]
    independent_rating_reconstruction_required: Literal[True]
    lifecycle_requires_component_level_reconciliation: Literal[True]
    defect_detection_requirement: Literal[
        "EACH_REGISTERED_COMPONENT_MUST_FAIL_ON_TARGETED_MUTATION"
    ]
    maximum_numerical_discrepancy_tolerance: FiniteFloat = Field(ge=0.0)
    minimum_branch_coverage_percent: FiniteFloat = Field(ge=90.0, le=100.0)
    required_completion_gates: tuple[str, ...] = Field(min_length=25)
    promotion_policy: Literal[
        "VALIDATE_CANDIDATE_THEN_ATOMICALLY_PROMOTE_ON_ONE_FILESYSTEM"
    ]
    failure_policy: Literal["FAILED_CANDIDATES_NEVER_CREATE_A_COMPLETED_LIFECYCLE"]
    anchor_ancestry_policy: Literal[
        "COMPLETION_STATE_MUST_EQUAL_OR_DESCEND_FROM_ANCHOR"
    ]

    @model_validator(mode="after")
    def validate_gates(self) -> ProductionGovernance:
        if len(self.required_completion_gates) != len(
            set(self.required_completion_gates)
        ):
            raise ValueError("Completion gate inventory contains duplicates")
        return self


class Task04PreregistrationV25(FrozenSection):
    """Complete v2.5 registration; lifecycle status remains external."""

    study_id: Literal["TASK-04"]
    registration_version: Literal["2.5"]
    method_id: Literal["RANGE-WEEKDAY-001"]
    method_version: Literal["range-weekday-registered-replication-v2.5"]
    title: Literal["Daily Range Behaviour by Weekday"]
    status: Literal["PREREGISTERED"]
    registration_classification: Literal[
        "correctively registered replication of the developed Task 04 analysis"
    ]
    registration_disclosure: NonEmpty
    research_question: NonEmpty
    primary_null_hypothesis: NonEmpty
    primary_alternative_hypothesis: NonEmpty
    secondary_hypotheses: tuple[str, ...] = Field(min_length=3, max_length=3)
    primary_outcome: PrimaryOutcome
    unit_of_analysis: NonEmpty
    calendar_definition: CalendarDefinition
    weekday_definition: WeekdayDefinition
    timestamp_semantics: TimestampSemantics
    primary_coverage_profile: Literal["DEFAULT_RESEARCH"]
    sensitivity_profiles: SensitivityProfiles
    daily_completeness_rule: DailyCompletenessRule
    boundary_period_policy: BoundaryPeriodPolicy
    descriptive_statistics: tuple[str, ...] = Field(min_length=20)
    statistical_conventions: StatisticalConventions
    primary_statistical_test: PrimaryStatisticalTest
    post_hoc_test: PostHocTest
    multiple_testing_correction: MultipleTestingCorrection
    effect_size_measures: EffectSizeMeasures
    confidence_interval_method: ConfidenceIntervalMethod
    normality_diagnostic: NormalityDiagnostic
    variance_diagnostic: VarianceDiagnostic
    robustness_analyses: tuple[str, ...] = Field(min_length=8)
    volatility_regime_definition: VolatilityRegimeDefinition
    chronological_stability_design: ChronologicalStabilityDesign
    missing_data_policy: NonEmpty
    exclusion_policy: ExclusionPolicy
    deterministic_seed_policy: DeterministicSeedPolicy
    dataset_version: Literal["sha256:b2a41310927aa9a9"]
    raw_checksum: Sha256
    raw_manifest_sha256: Sha256
    task_02_dependency: Task02Dependency
    task_03_dependency: Task03Dependency
    implementation_version: Literal["task04-daily-range-weekday-v2.5"]
    source_dependency_manifest_fingerprint: Sha256
    environment_lock_fingerprint: Sha256
    expected_outputs: ExpectedOutputs
    evidence_rating: EvidenceRating
    known_limitations: tuple[str, ...] = Field(min_length=1)
    prohibited_analyses: tuple[str, ...] = Field(min_length=1)
    repository_lineage: RepositoryLineage
    deviation_policy: DeviationPolicy
    production_governance: ProductionGovernance
    preregistration_deviations: tuple[Any, ...] = Field(max_length=0)

    @model_validator(mode="after")
    def validate_design(self) -> Task04PreregistrationV25:
        if len(set(self.descriptive_statistics)) != len(self.descriptive_statistics):
            raise ValueError("Descriptive method identifiers contain duplicates")
        if len(set(self.prohibited_analyses)) != len(self.prohibited_analyses):
            raise ValueError("Prohibited analyses contain duplicates")
        if self.registration_disclosure != (
            "The study design was locked before the corrected production "
            "regeneration. However, the underlying analysis had already been "
            "developed and its results reviewed. The corrected production run is "
            "therefore treated as a registered replication of the development "
            "analysis, not as a pristine first-look preregistration."
        ):
            raise ValueError("The corrective-registration disclosure is locked")
        if self.deviation_policy.post_anchor_scientific_changes_permitted:
            raise ValueError("v2.5 post-anchor scientific changes are forbidden")
        if self.deviation_policy.same_version_append_only_ledger_supported:
            raise ValueError("v2.5 has no same-version append-only deviation ledger")
        try:
            json.dumps(
                self.model_dump(mode="json"),
                allow_nan=False,
                sort_keys=True,
            )
        except (TypeError, ValueError) as error:
            raise ValueError("Registration must be standards-compliant JSON") from error
        return self
