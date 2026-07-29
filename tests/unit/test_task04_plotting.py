from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from eurusd_research.paths import find_repository_root
from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.plotting import plot_all_figures


def _historical_table(name: str) -> pd.DataFrame:
    root = find_repository_root()
    return pd.read_csv(
        root / "reports" / "research" / "task04_daily_range_weekday" / name
    )


def test_all_figures_render_from_historical_canonical_tables(tmp_path: Path) -> None:
    """Exercise plotting with verified v2.2 evidence, never v2.3 production data."""
    daily = _historical_table("daily_observations.csv")
    primary = daily.loc[daily["primary_profile_eligible"]].copy()
    paths = plot_all_figures(
        primary=primary,
        weekday_stats=_historical_table("weekday_statistics.csv"),
        yearly_stats=_historical_table("yearly_statistics.csv"),
        coverage_comparison=_historical_table("coverage_profile_comparison.csv"),
        period_results=_historical_table("period_robustness.csv"),
        regime_stats=_historical_table("volatility_regime_statistics.csv"),
        output_directory=tmp_path,
        config=load_task04_config(),
        raw_version="historical-v2.2-test-fixture",
    )
    assert len(paths) == 8
    assert all(path.is_file() and path.stat().st_size > 10_000 for path in paths)


def test_chronological_figure_requires_canonical_medians(tmp_path: Path) -> None:
    daily = _historical_table("daily_observations.csv")
    with pytest.raises(ValueError, match="missing"):
        plot_all_figures(
            primary=daily.loc[daily["primary_profile_eligible"]],
            weekday_stats=_historical_table("weekday_statistics.csv"),
            yearly_stats=_historical_table("yearly_statistics.csv"),
            coverage_comparison=_historical_table("coverage_profile_comparison.csv"),
            period_results=_historical_table("period_robustness.csv").drop(
                columns="monday_median_pips"
            ),
            regime_stats=_historical_table("volatility_regime_statistics.csv"),
            output_directory=tmp_path,
            config=load_task04_config(),
            raw_version="historical-v2.2-test-fixture",
        )
