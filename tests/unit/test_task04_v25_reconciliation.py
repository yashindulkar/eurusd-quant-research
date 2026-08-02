from __future__ import annotations

import inspect

from eurusd_research.studies import independent_reconciliation
from eurusd_research.studies.completion import IndependentReconciliationEvidence


def test_v24_asserted_reconciliation_pass_values_are_forbidden() -> None:
    source = inspect.getsource(
        independent_reconciliation.build_independent_reconciliation
    )
    assert '"robustness_population_maximum_absolute_discrepancy": 0.0' not in source
    assert '"regime_maximum_absolute_discrepancy": 0.0' not in source
    assert '"output_inventory_reconciled": True' not in source


def test_reconciliation_schema_requires_component_level_evidence() -> None:
    required = {
        "daily_aggregation",
        "descriptive_statistics",
        "primary_inference",
        "pairwise_analysis",
        "chronological_analysis",
        "fixed_period_analysis",
        "annual_analysis",
        "volatility_regime_analysis",
        "extreme_event_analysis",
        "evidence_rating",
        "output_inventory",
    }
    assert required.issubset(IndependentReconciliationEvidence.model_fields)
