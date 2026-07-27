from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from eurusd_research.data.quality_models import json_safe


def test_json_safe_converts_scientific_values() -> None:
    converted = json_safe(
        {
            "timestamp": pd.Timestamp("2024-01-01T00:00:00Z"),
            "datetime": datetime(2024, 1, 1, tzinfo=UTC),
            "path": Path("reports/a.csv"),
            "integer": np.int64(4),
            "tuple": (1, 2),
            "infinity": math.inf,
        }
    )
    assert converted["timestamp"] == "2024-01-01T00:00:00Z"
    assert converted["datetime"] == "2024-01-01T00:00:00Z"
    assert converted["path"] == "reports/a.csv"
    assert converted["integer"] == 4
    assert converted["tuple"] == [1, 2]
    assert converted["infinity"] is None
