from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from eurusd_research.config import DataConfig, load_config
from eurusd_research.data.schemas import expected_raw_columns
from eurusd_research.paths import find_repository_root


def test_load_repository_config() -> None:
    config = load_config()
    assert config.project.instrument == "EURUSD"
    assert config.project.nominal_timeframe == "M15"
    assert config.data.expected_columns == expected_raw_columns()
    assert config.data.immutable_raw_data is True
    assert config.sessions.sessions.london.enabled is False


def test_invalid_data_config_rejected() -> None:
    with pytest.raises(ValidationError, match="timestamp_column"):
        DataConfig.model_validate(
            {
                "raw_dataset_path": "data/raw/file.csv",
                "expected_columns": ["open"],
                "timestamp_column": "timestamp_utc",
                "expected_timezone": "UTC",
                "expected_frequency": "15min",
                "immutable_raw_data": True,
            }
        )


def test_unknown_timezone_rejected() -> None:
    with pytest.raises(ValidationError, match="Unknown IANA timezone"):
        DataConfig.model_validate(
            {
                "raw_dataset_path": "data/raw/file.csv",
                "expected_columns": ["timestamp_utc"],
                "timestamp_column": "timestamp_utc",
                "expected_timezone": "Not/A_Zone",
                "expected_frequency": "15min",
                "immutable_raw_data": True,
            }
        )


def test_load_config_rejects_unknown_key(tmp_path: Path) -> None:
    source = find_repository_root() / "configs"
    target = tmp_path / "configs"
    shutil.copytree(source, target)
    (tmp_path / "pyproject.toml").touch()
    project_path = target / "project.yaml"
    values = yaml.safe_load(project_path.read_text(encoding="utf-8"))
    values["unexpected"] = "rejected"
    project_path.write_text(yaml.safe_dump(values), encoding="utf-8")
    with pytest.raises(ValidationError, match="unexpected"):
        load_config(tmp_path)
