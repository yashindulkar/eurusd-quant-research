from __future__ import annotations

import inspect
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from eurusd_research.paths import find_repository_root
from eurusd_research.studies import registry as registry_module
from eurusd_research.studies.completion import (
    COMPLETION_BOOLEAN_FIELDS,
    RECONCILIATION_COMPONENTS,
    CompletionGateEvidence,
    ComponentDiscrepancy,
    IndependentReconciliationEvidence,
    LifecycleCompletionRequest,
    OutputDigestEvidence,
    OutputFileHash,
    build_output_digest,
    promote_candidate_outputs,
)
from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.integrity import (
    canonical_digest,
    read_source_dependency_manifest,
    read_task03_row_membership_evidence,
)
from eurusd_research.studies.orchestration import (
    PHASE_B_SEQUENCE,
    PhaseBProgress,
    PhaseBStage,
)
from eurusd_research.studies.registry import (
    RECEIPT_FIELD_INVENTORY,
    LifecycleOutputEvidence,
    RegisteredBlobIdentity,
    Task04RegistrationLifecycle,
    Task04RegistrationReceipt,
    assert_completed_lifecycle_matches,
    assert_registration_receipt_matches,
    build_completed_lifecycle,
    build_registration_receipt,
    executable_configuration_fingerprint,
    locked_design_fingerprint,
    read_preregistration,
    read_registration_receipt,
    write_completed_lifecycle,
    write_registration_receipt,
)
from eurusd_research.studies.task04 import generate_task04_study


def _mapping_field_paths(
    value: object, prefix: tuple[str | int, ...] = ()
) -> list[tuple[str | int, ...]]:
    paths: list[tuple[str | int, ...]] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            path = (*prefix, key)
            paths.append(path)
            paths.extend(_mapping_field_paths(nested, path))
    elif isinstance(value, (list, tuple)) and value:
        paths.extend(_mapping_field_paths(value[0], (*prefix, 0)))
    return paths


def _remove_mapping_field(value: dict[str, Any], path: tuple[str | int, ...]) -> None:
    target: Any = value
    for item in path[:-1]:
        target = target[item]
    target.pop(path[-1])


def _contract() -> tuple[Any, Any]:
    root = find_repository_root()
    config = load_task04_config(root)
    registration, _ = read_preregistration(root / config.preregistration_path)
    return config, registration


def _receipt() -> Task04RegistrationReceipt:
    config, registration = _contract()
    paths = tuple(registration.repository_lineage.registered_path_inventory)
    inventory = tuple(
        sorted(
            (
                *config.expected_output_files,
                *(f"figures/{x}" for x in config.expected_figure_files),
            )
        )
    )
    figures = tuple(sorted(f"figures/{x}" for x in config.expected_figure_files))
    payload = {
        "identity": {
            "receipt_schema_version": "task04-registration-receipt-v5",
            "study_id": "TASK-04",
            "registration_version": "2.7",
            "method_id": "RANGE-WEEKDAY-001",
            "method_version": "range-weekday-registered-replication-v2.7",
            "registration_file_path": "studies/task04_daily_range_weekday.v2.7.yaml",
            "receipt_file_path": "studies/task04_daily_range_weekday.v2.7.receipt.json",
            "registration_classification": registration.registration_classification,
            "non_first_look_disclosure": registration.registration_disclosure,
            "registration_status_at_anchoring": "PREREGISTERED",
        },
        "git_anchor": {
            "anchor_commit_id": "a" * 40,
            "anchor_tree_id": "b" * 40,
            "anchor_parent_commit_id": "c" * 40,
            "branch_at_registration": "main",
            "anchor_reachability_policy": "ANCHOR_MUST_REMAIN_REACHABLE",
            "descendant_validation_policy": (
                "CURRENT_STATE_MUST_EQUAL_OR_DESCEND_FROM_ANCHOR"
            ),
            "registered_path_tree_fingerprint": "d" * 64,
            "registered_path_inventory": paths,
            "registered_blob_identities": [
                {"path": path, "git_blob_id": "e" * 40, "sha256": "f" * 64}
                for path in paths
            ],
            "repository_dirty_state_policy": (
                registration.repository_lineage.dirty_state_policy
            ),
        },
        "scientific_and_executable_design": {
            "semantic_design_fingerprint": locked_design_fingerprint(registration),
            "executable_configuration_fingerprint": (
                executable_configuration_fingerprint(config)
            ),
            "source_manifest_fingerprint": (
                config.required_source_dependency_manifest_fingerprint
            ),
            "source_tree_fingerprint": "1" * 64,
            "environment_lock_fingerprint": (
                config.required_environment_lock_fingerprint
            ),
            "package_dependency_lock_fingerprint": "2" * 64,
            "timestamp_assumption": "AS_SUPPLIED_TIMESTAMP_LABEL_DATE",
            "unresolved_timestamp_limitation": (
                registration.timestamp_semantics.possible_boundary_consequence
            ),
            "maximum_evidence_rating_cap": "MODERATE",
            "deviation_policy": "NEW_REGISTRATION_VERSION_REQUIRED",
            "expected_production_output_inventory": inventory,
            "expected_figure_inventory": figures,
        },
        "upstream_evidence": {
            "raw_dataset": {
                "path": "data/raw/EURUSD_M15_UTC.csv",
                "dataset_version": "sha256:b2a41310927aa9a9",
                "sha256": config.required_raw_sha256,
                "manifest_fingerprint": config.required_raw_manifest_sha256,
            },
            "task02": {
                "schema_version": "raw-data-quality-audit-v2",
                "audit_fingerprint": config.required_task02_audit_fingerprint,
                "readiness_status": "PASS, CONDITIONALLY_READY",
            },
            "task03": {
                "schema_version": "task03-layered-evidence-v1",
                "method_version": "research-coverage-v1",
                "coverage_stable_artifact_fingerprint": (
                    config.required_coverage_summary_stable_sha256
                ),
                "scientific_membership_fingerprint": (
                    config.required_task03_scientific_membership_fingerprint
                ),
                "stable_artifact_fingerprint": (
                    config.required_task03_stable_artifact_fingerprint
                ),
                "execution_context_fingerprint_at_receipt": "6" * 64,
                "execution_context_variance_policy": (
                    "INFORMATIONAL_IF_SCIENTIFIC_AND_STABLE_ARTIFACT_IDENTITIES_MATCH"
                ),
                "exact_row_membership_fingerprint": "3" * 64,
                "exact_date_membership_fingerprint": "4" * 64,
                "profile_counts": {
                    "default_research_rows": 406945,
                    "strict_continuity_rows": 360477,
                    "sensitivity_full_rows": 46468,
                    "sensitivity_2023_rows": 9258,
                    "observed_dates": 5146,
                    "default_research_dates": 5146,
                    "strict_continuity_dates": 4525,
                    "sensitivity_full_dates": 681,
                    "sensitivity_2023_dates": 156,
                },
                "algebra_fingerprint": "5" * 64,
            },
        },
        "integrity": {
            "canonicalization_version": "task04-canonical-json-v1",
            "field_inventory": RECEIPT_FIELD_INVENTORY,
            "schema_fingerprint": "6" * 64,
            "allowed_mutable_fields_after_anchoring": [],
        },
    }
    return Task04RegistrationReceipt.model_validate(
        {**payload, "receipt_fingerprint": canonical_digest(payload)}
    )


def _independent() -> IndependentReconciliationEvidence:
    components = {
        name: ComponentDiscrepancy(
            component=name,
            status="PASS",
            checked_row_count=1,
            checked_field_count=1,
            absolute_discrepancy_by_field={"value": 1e-12},
            relative_discrepancy_by_field={"value": 1e-12},
            maximum_absolute_discrepancy=1e-12,
            maximum_relative_discrepancy=1e-12,
            categorical_mismatch_count=0,
            membership_mismatch_count=0,
            inventory_mismatch_count=0,
            mismatch_examples=(),
            missing_evidence=(),
            unsupported_claims=(),
            passed=True,
        )
        for name in RECONCILIATION_COMPONENTS
    }
    payload = {
        "schema_version": "task04-independent-reconciliation-v2",
        "implementation_id": "task04-independent-full-reproduction-v2",
        "study_id": "TASK-04",
        "registration_version": "2.7",
        "method_version": "range-weekday-registered-replication-v2.7",
        "anchor_commit": "a" * 40,
        "receipt_fingerprint": "b" * 64,
        "raw_sha256": "a" * 64,
        "task03_evidence_fingerprint": "b" * 64,
        "production_output_digest": "c" * 64,
        "tolerance_policy": ("ABSOLUTE_AND_RELATIVE_WITH_ZERO_CATEGORICAL_TOLERANCE"),
        "checked_components": list(RECONCILIATION_COMPONENTS),
        **{name: value.model_dump(mode="json") for name, value in components.items()},
        "independent_rating_decisions": [
            {
                "dimension": "primary_significance",
                "registered_threshold": "0.05",
                "independent_input": "0.01",
                "passed": True,
                "effect_on_rating": "required for MODERATE",
                "missing_evidence_rule": "INSUFFICIENT",
            }
        ],
        "primary_population": 50,
        "checked_row_count": len(components),
        "checked_field_count": len(components),
        "categorical_mismatch_count": 0,
        "membership_mismatch_count": 0,
        "inventory_mismatch_count": 0,
        "missing_evidence": [],
        "unsupported_claims": [],
        "absolute_tolerance": 1e-10,
        "relative_tolerance": 1e-10,
        "maximum_numerical_discrepancy": 1e-12,
        "passed": True,
    }
    return IndependentReconciliationEvidence.model_validate(
        {**payload, "artifact_fingerprint": canonical_digest(payload)}
    )


def _gates(**updates: object) -> CompletionGateEvidence:
    values: dict[str, object] = {name: True for name in COMPLETION_BOOLEAN_FIELDS}
    values.update(
        {
            "maximum_numerical_discrepancy": 1e-12,
            "registered_numerical_tolerance": 1e-10,
            "branch_coverage_percent": 91.0,
            "minimum_branch_coverage_percent": 90.0,
        }
    )
    values.update(updates)
    return CompletionGateEvidence.model_validate(values)


def _outputs(receipt: Task04RegistrationReceipt) -> LifecycleOutputEvidence:
    paths = (
        receipt.scientific_and_executable_design.expected_production_output_inventory
    )
    figures = receipt.scientific_and_executable_design.expected_figure_inventory
    records = tuple(
        OutputFileHash(
            relative_path=path,
            size_bytes=1,
            sha256="a" * 64,
            category="FIGURE" if path in figures else "TABLE_OR_REPORT",
        )
        for path in paths
    )
    digest = OutputDigestEvidence(
        digest_algorithm="task04-path-length-bytes-sha256-v1",
        files=records,
        inventory_fingerprint=canonical_digest(list(paths)),
        path_plus_bytes_digest="b" * 64,
    )
    return LifecycleOutputEvidence(
        production_output_inventory=paths,
        exact_output_paths=paths,
        output_digest=digest,
        figure_inventory=figures,
        no_extra_output_validation_passed=True,
        output_containment_validation_passed=True,
    )


@pytest.mark.parametrize(
    "path",
    [
        ("identity", "registration_file_path"),
        ("identity", "receipt_file_path"),
        ("identity", "registration_classification"),
        ("identity", "non_first_look_disclosure"),
        ("git_anchor", "anchor_parent_commit_id"),
        ("git_anchor", "branch_at_registration"),
        ("git_anchor", "anchor_tree_id"),
        ("git_anchor", "registered_path_inventory"),
        ("scientific_and_executable_design", "unresolved_timestamp_limitation"),
        ("scientific_and_executable_design", "source_manifest_fingerprint"),
        ("scientific_and_executable_design", "environment_lock_fingerprint"),
        ("scientific_and_executable_design", "expected_production_output_inventory"),
        ("upstream_evidence", "task03"),
        ("integrity", "schema_fingerprint"),
    ],
)
def test_receipt_missing_mandatory_fields_fail(path: tuple[str, str]) -> None:
    values = _receipt().model_dump(mode="python")
    values[path[0]].pop(path[1])
    with pytest.raises(ValidationError):
        Task04RegistrationReceipt.model_validate(values)


def test_every_receipt_mapping_field_is_mandatory() -> None:
    original = _receipt().model_dump(mode="python")
    paths = _mapping_field_paths(original)
    assert len(paths) >= len(RECEIPT_FIELD_INVENTORY)
    for path in paths:
        values = deepcopy(original)
        _remove_mapping_field(values, path)
        with pytest.raises(ValidationError):
            Task04RegistrationReceipt.model_validate(values)


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf")])
def test_receipt_unknown_null_and_non_finite_fail(bad: object) -> None:
    values = _receipt().model_dump(mode="python")
    values["unknown_alias"] = "x"
    with pytest.raises(ValidationError):
        Task04RegistrationReceipt.model_validate(values)
    values = _receipt().model_dump(mode="python")
    values["identity"]["non_first_look_disclosure"] = bad
    with pytest.raises(ValidationError):
        Task04RegistrationReceipt.model_validate(values)


def test_receipt_mutation_and_replacement_are_detected(tmp_path: Path) -> None:
    config, registration = _contract()
    receipt = _receipt()
    path = tmp_path / "receipt.json"
    write_registration_receipt(receipt, path)
    with pytest.raises(FileExistsError):
        write_registration_receipt(receipt, path)
    values = receipt.model_dump(mode="python")
    values["git_anchor"]["branch_at_registration"] = "other"
    values.pop("receipt_fingerprint")
    replacement = Task04RegistrationReceipt.model_validate(
        {**values, "receipt_fingerprint": canonical_digest(values)}
    )
    with pytest.raises(ValueError, match="validation failed"):
        assert_registration_receipt_matches(
            replacement,
            receipt,
            registration=registration,
            config=config,
        )
    path.write_text(path.read_text().replace("main", "evil"), encoding="utf-8")
    with pytest.raises(ValueError):
        read_registration_receipt(path)


def test_receipt_builder_populates_every_v24_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = find_repository_root()
    config, registration = _contract()
    source = read_source_dependency_manifest(
        root / "studies/task04_v2.7_source_manifest.json"
    )
    task03 = read_task03_row_membership_evidence(
        root / "studies/task03_task04_v2.7_evidence.json"
    )
    monkeypatch.setattr(
        registry_module, "validate_task04_dependencies", lambda *_: None
    )
    monkeypatch.setattr(
        registry_module,
        "validate_source_dependency_manifest",
        lambda *_: source,
    )
    monkeypatch.setattr(
        registry_module, "read_task03_row_membership_evidence", lambda *_: task03
    )
    monkeypatch.setattr(
        registry_module,
        "_sha256_file",
        lambda path: (
            config.required_environment_lock_fingerprint
            if path.name.endswith("environment_lock.json")
            else "7" * 64
        ),
    )
    monkeypatch.setattr(registry_module, "commit_tree_id", lambda *_: "b" * 40)
    monkeypatch.setattr(
        registry_module, "registered_path_tree_fingerprint", lambda *_: "d" * 64
    )
    monkeypatch.setattr(registry_module, "assert_anchor_lineage", lambda *_, **__: None)
    monkeypatch.setattr(
        registry_module,
        "resolve_commit",
        lambda _root, reference="HEAD": "c" * 40,
    )
    monkeypatch.setattr(registry_module, "_git", lambda *_: "main")
    monkeypatch.setattr(
        registry_module,
        "_registered_blob_identities",
        lambda _root, _anchor, paths: tuple(
            RegisteredBlobIdentity(path=path, git_blob_id="e" * 40, sha256="f" * 64)
            for path in paths
        ),
    )
    receipt = build_registration_receipt(
        registration,
        config,
        root=root,
        anchor_commit="a" * 40,
    )
    assert receipt.identity.registration_file_path.endswith("v2.7.yaml")
    assert receipt.git_anchor.anchor_parent_commit_id == "c" * 40
    assert receipt.git_anchor.registered_blob_identities
    assert receipt.upstream_evidence.task03.scientific_membership_fingerprint == (
        task03.scientific_membership_fingerprint
    )
    assert receipt.scientific_and_executable_design.maximum_evidence_rating_cap == (
        "MODERATE"
    )
    assert receipt.integrity.allowed_mutable_fields_after_anchoring == ()


def test_v24_historical_control_records_reconciliation_failure() -> None:
    root = find_repository_root()
    record = json.loads(
        (root / "studies/task04_v2.4_stopped_attempt.json").read_text(encoding="utf-8")
    )
    assert record["classification"] == "ABANDONED_REGISTERED_ATTEMPT"
    assert record["lifecycle_existed"] is False
    assert record["final_output_existed"] is False
    assert set(record["defective_fields"]) == {
        "robustness_population_maximum_absolute_discrepancy",
        "regime_maximum_absolute_discrepancy",
        "output_inventory_reconciled",
    }


def test_every_completion_gate_is_mandatory_and_finite() -> None:
    for field in COMPLETION_BOOLEAN_FIELDS:
        with pytest.raises(ValidationError, match="Completion gates failed"):
            _gates(**{field: False})
    with pytest.raises(ValidationError):
        _gates(maximum_numerical_discrepancy=float("nan"))
    with pytest.raises(ValidationError, match="exceeds"):
        _gates(maximum_numerical_discrepancy=1.0)


def test_lifecycle_requires_complete_evidence_and_is_terminal(tmp_path: Path) -> None:
    config, registration = _contract()
    receipt = _receipt()
    lifecycle = build_completed_lifecycle(
        registration,
        config,
        receipt,
        production_state_identifier="working-tree:descendant",
        descendant_commit_or_working_state="working-tree:descendant",
        output_evidence=_outputs(receipt),
        independent_reconciliation=_independent(),
        completion_gates=_gates(),
        primary_population=50,
        primary_statistic=5.0,
        primary_p_value=0.1,
        primary_effect_size=0.01,
        final_evidence_rating="MODERATE",
        task03_execution_context_fingerprint="7" * 64,
        task03_execution_context_variance_observed=False,
        limitations=registration.known_limitations,
    )
    original = lifecycle.model_dump(mode="python")
    for field_path in _mapping_field_paths(original):
        values = deepcopy(original)
        _remove_mapping_field(values, field_path)
        with pytest.raises(ValidationError):
            Task04RegistrationLifecycle.model_validate(values)
    path = tmp_path / "lifecycle.json"
    write_completed_lifecycle(lifecycle, path)
    with pytest.raises(FileExistsError):
        write_completed_lifecycle(lifecycle, path)
    for section, field in (
        ("identity", "method_version"),
        ("identity", "anchor_tree_id"),
        ("production_state", "production_state_identifier"),
        ("output_evidence", "output_digest"),
        ("scientific_completion", "final_evidence_rating"),
        ("scientific_completion", "independent_reconciliation"),
        ("governance", "limitations"),
        ("governance", "completion_gates"),
    ):
        values = lifecycle.model_dump(mode="python")
        values[section].pop(field)
        with pytest.raises(ValidationError):
            Task04RegistrationLifecycle.model_validate(values)
    values = lifecycle.model_dump(mode="python")
    values["identity"]["status"] = "PREREGISTERED"
    with pytest.raises(ValidationError):
        Task04RegistrationLifecycle.model_validate(values)
    for section, field, replacement in (
        ("identity", "receipt_fingerprint", "9" * 64),
        ("identity", "anchor_commit_id", "8" * 40),
        ("governance", "limitations", ("altered",)),
    ):
        values = lifecycle.model_dump(mode="python")
        values[section][field] = replacement
        values.pop("lifecycle_fingerprint")
        altered = Task04RegistrationLifecycle.model_validate(
            {**values, "lifecycle_fingerprint": canonical_digest(values)}
        )
        with pytest.raises(ValueError, match="does not match"):
            assert_completed_lifecycle_matches(
                altered,
                registration=registration,
                config=config,
                receipt=receipt,
            )


def test_phase_b_sequence_cannot_skip_to_completion() -> None:
    progress = PhaseBProgress()
    with pytest.raises(ValueError, match="expected validate_anchor"):
        progress.advance(PHASE_B_SEQUENCE[-2])
    for stage in PHASE_B_SEQUENCE[:11]:
        progress = progress.advance(stage)
    assert progress.final_outputs_may_be_promoted
    assert not progress.lifecycle_may_be_created
    progress = progress.advance(PhaseBStage.PROMOTE_FINAL_OUTPUTS)
    assert progress.lifecycle_may_be_created
    progress = progress.advance(PHASE_B_SEQUENCE[12])
    progress = progress.advance(PHASE_B_SEQUENCE[13])
    assert progress.completed


def test_completion_request_requires_exact_pre_promotion_sequence() -> None:
    progress = PhaseBProgress()
    for stage in PHASE_B_SEQUENCE[:11]:
        progress = progress.advance(stage)
    values = {
        "schema_version": "task04-lifecycle-completion-request-v1",
        "phase_b_progress": progress,
        "production_state_identifier": "candidate-state",
        "descendant_commit_or_working_state": "anchor-plus-results",
        "deterministic_regeneration_digest": "a" * 64,
        "independent_reconciliation": _independent(),
        "completion_gates": _gates(),
        "primary_population": 50,
        "primary_statistic": 1.0,
        "primary_p_value": 0.5,
        "primary_effect_size": 0.01,
        "final_evidence_rating": "MODERATE",
        "limitations": ("Timestamp semantics remain unresolved.",),
    }
    LifecycleCompletionRequest.model_validate(values)
    values["phase_b_progress"] = PhaseBProgress()
    with pytest.raises(ValidationError, match="pre-promotion"):
        LifecycleCompletionRequest.model_validate(values)


@pytest.mark.parametrize("component", RECONCILIATION_COMPONENTS)
def test_lifecycle_rejects_each_missing_reconciliation_component(
    component: str,
) -> None:
    values = _independent().model_dump(mode="python")
    values.pop(component)
    with pytest.raises(ValidationError):
        IndependentReconciliationEvidence.model_validate(values)


@pytest.mark.parametrize("component", RECONCILIATION_COMPONENTS)
def test_lifecycle_rejects_each_failed_reconciliation_component(
    component: str,
) -> None:
    evidence_values = _independent().model_dump(mode="python")
    evidence_values[component]["status"] = "FAIL"
    evidence_values[component]["passed"] = False
    evidence_values["passed"] = False
    evidence_values.pop("artifact_fingerprint")
    evidence = IndependentReconciliationEvidence.model_validate(
        {
            **evidence_values,
            "artifact_fingerprint": canonical_digest(evidence_values),
        }
    )
    config, registration = _contract()
    receipt = _receipt()
    with pytest.raises(ValueError, match="reconciliation"):
        build_completed_lifecycle(
            registration,
            config,
            receipt,
            production_state_identifier="candidate",
            descendant_commit_or_working_state="descendant",
            output_evidence=_outputs(receipt),
            independent_reconciliation=evidence,
            completion_gates=_gates(),
            primary_population=50,
            primary_statistic=1.0,
            primary_p_value=0.5,
            primary_effect_size=0.01,
            final_evidence_rating="MODERATE",
            task03_execution_context_fingerprint="7" * 64,
            task03_execution_context_variance_observed=False,
            limitations=registration.known_limitations,
        )


def test_candidate_generator_has_no_completion_transition() -> None:
    source = inspect.getsource(generate_task04_study)
    assert "transition_to_completed" not in source
    assert "write_completed_lifecycle" not in source
    assert '"status": "CANDIDATE"' in source


def test_digest_algorithm_and_candidate_promotion_are_exact(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "a.txt").write_bytes(b"alpha")
    (candidate / "b.txt").write_bytes(b"beta")
    first = build_output_digest(candidate, ("a.txt", "b.txt"))
    second = build_output_digest(candidate, ("b.txt", "a.txt"))
    assert first == second
    final = tmp_path / "final"
    promote_candidate_outputs(candidate, final, ("a.txt", "b.txt"))
    assert final.is_dir() and not candidate.exists()
    with pytest.raises(FileExistsError):
        promote_candidate_outputs(final, final, ("a.txt", "b.txt"))
    with pytest.raises(ValidationError):
        OutputFileHash(
            relative_path="figures\\figure.png",
            size_bytes=1,
            sha256="a" * 64,
            category="FIGURE",
        )


def test_digest_rejects_extra_symlink_and_hardlink(tmp_path: Path) -> None:
    root = tmp_path / "outputs"
    root.mkdir()
    target = root / "a.txt"
    target.write_text("a", encoding="utf-8")
    (root / "extra.txt").write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError, match="inventory mismatch"):
        build_output_digest(root, ("a.txt",))
    (root / "extra.txt").unlink()
    link = root / "link.txt"
    link.symlink_to(target)
    with pytest.raises(RuntimeError):
        build_output_digest(root, ("a.txt", "link.txt"))
    link.unlink()
    hardlink = root / "hard.txt"
    os.link(target, hardlink)
    with pytest.raises(RuntimeError, match="hard links"):
        build_output_digest(root, ("a.txt", "hard.txt"))
