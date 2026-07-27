"""Validated configuration loading for project-wide research conventions."""

from __future__ import annotations

from datetime import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from eurusd_research.paths import find_repository_root


class StrictModel(BaseModel):
    """Immutable base model that rejects unknown configuration keys."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ReportDirectories(StrictModel):
    """Repository-relative destinations for generated report artifacts."""

    figures: Path
    tables: Path
    audits: Path


class ProjectConfig(StrictModel):
    """Top-level project identity and reproducibility defaults."""

    project_name: str = Field(min_length=1)
    instrument: str = Field(min_length=1)
    nominal_timeframe: str = Field(min_length=1)
    storage_timezone: str
    random_seed: int = Field(ge=0)
    report_directories: ReportDirectories
    default_confidence_level: float = Field(gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def validate_timezone(self) -> ProjectConfig:
        _validate_iana_timezone(self.storage_timezone)
        return self


class DataConfig(StrictModel):
    """Expected raw-file schema and immutable-data policy."""

    raw_dataset_path: Path
    expected_columns: tuple[str, ...] = Field(min_length=1)
    timestamp_column: str
    expected_timezone: str
    expected_frequency: str = Field(pattern=r"^\d+(min|h|s)$")
    immutable_raw_data: bool

    @model_validator(mode="after")
    def validate_data_rules(self) -> DataConfig:
        if self.timestamp_column not in self.expected_columns:
            raise ValueError("timestamp_column must appear in expected_columns")
        if len(set(self.expected_columns)) != len(self.expected_columns):
            raise ValueError("expected_columns must not contain duplicates")
        if not self.immutable_raw_data:
            raise ValueError("immutable_raw_data must be true")
        _validate_iana_timezone(self.expected_timezone)
        return self


class SessionPlaceholder(StrictModel):
    """Disabled placeholder for a future local-time session definition."""

    enabled: bool
    timezone: str
    start_local: time | None
    end_local: time | None

    @model_validator(mode="after")
    def validate_placeholder(self) -> SessionPlaceholder:
        _validate_iana_timezone(self.timezone)
        if self.enabled and (self.start_local is None or self.end_local is None):
            raise ValueError("enabled sessions require start_local and end_local")
        return self


class SessionSet(StrictModel):
    """Named future session placeholders."""

    asia: SessionPlaceholder
    london: SessionPlaceholder
    new_york: SessionPlaceholder
    london_new_york_overlap: SessionPlaceholder


class RolloverPlaceholder(StrictModel):
    """Disabled placeholder for the future FX trading-day boundary."""

    enabled: bool
    timezone: str
    local_time: time | None

    @model_validator(mode="after")
    def validate_placeholder(self) -> RolloverPlaceholder:
        _validate_iana_timezone(self.timezone)
        if self.enabled and self.local_time is None:
            raise ValueError("enabled rollover requires local_time")
        return self


class SessionsConfig(StrictModel):
    """Session configuration structure without methodological definitions."""

    sessions: SessionSet
    fx_trading_day_rollover: RolloverPlaceholder
    warning: str = Field(min_length=1)


class ResearchConfig(StrictModel):
    """Complete validated repository configuration."""

    project: ProjectConfig
    data: DataConfig
    sessions: SessionsConfig


def _validate_iana_timezone(name: str) -> None:
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown IANA timezone: {name}") from error


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"Configuration must be a mapping: {path}")
    return loaded


def load_config(root: Path | None = None) -> ResearchConfig:
    """Load and validate all configuration files from a repository root."""
    repository_root = (root or find_repository_root()).resolve()
    config_directory = repository_root / "configs"
    return ResearchConfig(
        project=ProjectConfig.model_validate(
            _load_yaml(config_directory / "project.yaml")
        ),
        data=DataConfig.model_validate(_load_yaml(config_directory / "data.yaml")),
        sessions=SessionsConfig.model_validate(
            _load_yaml(config_directory / "sessions.yaml")
        ),
    )
