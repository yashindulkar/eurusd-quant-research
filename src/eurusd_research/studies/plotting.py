"""Deterministic publication-quality static figures for Task 04."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from eurusd_research.studies.configuration import Task04Config

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri")
MARKERS = ("o", "s", "^", "D", "P")


def _metadata(
    frame: pd.DataFrame, profile: str, method_id: str, raw_version: str
) -> str:
    return (
        f"n={len(frame):,} | {frame['utc_date'].min()} to "
        f"{frame['utc_date'].max()} | {profile} | {raw_version} | {method_id}"
    )


def _finish(
    figure: Figure,
    axis: Axes,
    *,
    title: str,
    subtitle: str,
    output: Path,
    config: Task04Config,
) -> None:
    figure.suptitle(title, x=0.08, ha="left", fontsize=14, fontweight="bold")
    axis.set_title(subtitle, loc="left", fontsize=9, color="#444444", pad=10)
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis="y", color="#D9DEE3", linewidth=0.7, alpha=0.8)
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        output,
        dpi=config.figure_settings.dpi,
        bbox_inches="tight",
        facecolor="white",
        metadata={"Software": "eurusd_research", "Creation Time": None},
    )
    plt.close(figure)


def _figure(config: Task04Config) -> tuple[Figure, Axes]:
    return plt.subplots(
        figsize=(
            config.figure_settings.width_inches,
            config.figure_settings.height_inches,
        )
    )


def plot_all_figures(
    *,
    primary: pd.DataFrame,
    weekday_stats: pd.DataFrame,
    yearly_stats: pd.DataFrame,
    coverage_comparison: pd.DataFrame,
    period_results: pd.DataFrame,
    regime_stats: pd.DataFrame,
    output_directory: Path,
    config: Task04Config,
    raw_version: str,
) -> list[Path]:
    """Generate the eight preregistered figures in stable order."""
    figures_directory = output_directory / "figures"
    palette = config.figure_settings.palette
    metadata = _metadata(
        primary, config.primary_coverage_profile, config.method_id, raw_version
    )
    arrays = [
        primary.loc[primary["weekday_name"].eq(day), "daily_range_pips"].to_numpy()
        for day in WEEKDAYS
    ]
    paths: list[Path] = []

    path = figures_directory / "01_weekday_boxplot.png"
    figure, axis = _figure(config)
    box = axis.boxplot(
        arrays,
        tick_labels=SHORT,
        patch_artist=True,
        showfliers=True,
        flierprops={"marker": ".", "markersize": 2, "alpha": 0.25},
        medianprops={"color": "black", "linewidth": 1.5},
    )
    for index, patch in enumerate(box["boxes"]):
        patch.set_facecolor(palette[index])
        patch.set_alpha(0.35)
        patch.set_edgecolor("black")
    axis.set_ylabel("Daily high-low range (pips)")
    axis.set_ylim(bottom=0)
    _finish(
        figure,
        axis,
        title="EUR/USD daily range by UTC weekday",
        subtitle=f"Boxplots retain all complete-day observations | {metadata}",
        output=path,
        config=config,
    )
    paths.append(path)

    path = figures_directory / "02_weekday_violin_or_distribution.png"
    figure, axis = _figure(config)
    violins = axis.violinplot(
        arrays,
        showmeans=False,
        showmedians=True,
        showextrema=True,
        bw_method=config.figure_settings.violin_bandwidth_method,
    )
    bodies = cast(list[Any], violins["bodies"])
    for index, body in enumerate(bodies):
        body.set_facecolor(palette[index])
        body.set_edgecolor("black")
        body.set_alpha(0.35)
    for key in ("cbars", "cmins", "cmaxes", "cmedians"):
        violins[key].set_color("black")
        violins[key].set_linewidth(0.8)
    axis.set_xticks(range(1, 6), SHORT)
    axis.set_ylabel("Daily high-low range (pips)")
    axis.set_ylim(bottom=0)
    _finish(
        figure,
        axis,
        title="EUR/USD daily range distributions by UTC weekday",
        subtitle=(
            f"Fixed Scott bandwidth; median and full observed span shown | {metadata}"
        ),
        output=path,
        config=config,
    )
    paths.append(path)

    path = figures_directory / "03_weekday_ecdf.png"
    figure, axis = _figure(config)
    for index, (day, values) in enumerate(zip(WEEKDAYS, arrays, strict=True)):
        ordered = np.sort(values)
        probability = np.arange(1, len(ordered) + 1) / len(ordered)
        axis.step(
            ordered,
            probability,
            where="post",
            label=f"{day} (n={len(values):,})",
            color=palette[index],
            linestyle=("-" if index < 2 else "--" if index < 4 else ":"),
            linewidth=1.5,
        )
    axis.set_xlabel("Daily high-low range (pips)")
    axis.set_ylabel("Empirical cumulative probability")
    axis.set_xlim(left=0)
    axis.legend(frameon=False, ncol=2)
    _finish(
        figure,
        axis,
        title="Empirical distributions of EUR/USD daily range",
        subtitle=(
            f"ECDFs show the complete distribution without histogram bins | {metadata}"
        ),
        output=path,
        config=config,
    )
    paths.append(path)

    path = figures_directory / "04_weekday_mean_median_ci.png"
    figure, axis = _figure(config)
    primary_stats = weekday_stats.loc[
        weekday_stats["profile"].eq(config.primary_coverage_profile)
        & weekday_stats["analysis_scope"].eq("complete_weekday_dates")
    ].set_index("weekday_name")
    x = np.arange(5)
    means = primary_stats.loc[list(WEEKDAYS), "mean"].to_numpy()
    mean_low = primary_stats.loc[list(WEEKDAYS), "mean_ci_lower"].to_numpy()
    mean_high = primary_stats.loc[list(WEEKDAYS), "mean_ci_upper"].to_numpy()
    medians = primary_stats.loc[list(WEEKDAYS), "median"].to_numpy()
    median_low = primary_stats.loc[list(WEEKDAYS), "median_ci_lower"].to_numpy()
    median_high = primary_stats.loc[list(WEEKDAYS), "median_ci_upper"].to_numpy()
    axis.errorbar(
        x - 0.08,
        means,
        yerr=[means - mean_low, mean_high - means],
        fmt="o",
        color=palette[1],
        capsize=4,
        label="Mean (95% bootstrap CI)",
    )
    axis.errorbar(
        x + 0.08,
        medians,
        yerr=[medians - median_low, median_high - medians],
        fmt="s",
        mfc="white",
        color="black",
        capsize=4,
        label="Median (95% bootstrap CI)",
    )
    axis.set_xticks(x, SHORT)
    axis.set_ylabel("Daily high-low range (pips)")
    axis.set_ylim(bottom=0)
    axis.legend(frameon=False)
    _finish(
        figure,
        axis,
        title="Mean and median EUR/USD daily range with uncertainty",
        subtitle=f"Deterministic percentile-bootstrap intervals | {metadata}",
        output=path,
        config=config,
    )
    paths.append(path)

    path = figures_directory / "05_yearly_weekday_medians.png"
    figure, axis = _figure(config)
    pivot = yearly_stats.pivot(
        index="year", columns="weekday_name", values="median"
    ).sort_index()
    for index, day in enumerate(WEEKDAYS):
        axis.plot(
            pivot.index,
            pivot[day],
            label=day,
            color=palette[index],
            marker=MARKERS[index],
            markersize=3.5,
            linestyle=("-" if index < 2 else "--" if index < 4 else ":"),
            linewidth=1.2,
        )
    axis.set_xlabel("UTC calendar year")
    axis.set_ylabel("Median daily range (pips)")
    axis.set_ylim(bottom=0)
    axis.legend(frameon=False, ncol=3)
    _finish(
        figure,
        axis,
        title="Year-by-year median EUR/USD daily range",
        subtitle=f"All years retained; sufficiency is reported separately | {metadata}",
        output=path,
        config=config,
    )
    paths.append(path)

    path = figures_directory / "06_coverage_profile_comparison.png"
    figure, axis = _figure(config)
    profile_stats = weekday_stats.pivot_table(
        index="profile", columns="weekday_name", values="median", observed=True
    ).reindex(coverage_comparison["profile"])
    width = 0.16
    x = np.arange(len(profile_stats))
    for index, day in enumerate(WEEKDAYS):
        axis.bar(
            x + (index - 2) * width,
            profile_stats[day],
            width,
            label=day,
            color=palette[index],
            edgecolor="black",
            linewidth=0.5,
            hatch=("" if index < 2 else "//" if index < 4 else ".."),
            alpha=0.75,
        )
    profile_counts = coverage_comparison.set_index("profile")[
        "eligible_daily_observations"
    ]
    axis.set_xticks(
        x,
        [
            f"{str(value).replace('_', chr(10))}\nn={int(profile_counts[value]):,}"
            for value in profile_stats.index
        ],
    )
    axis.set_ylabel("Median daily range (pips)")
    axis.set_ylim(bottom=0)
    axis.legend(frameon=False, ncol=5)
    _finish(
        figure,
        axis,
        title="Daily range medians across Task 03 coverage profiles",
        subtitle=(
            f"Profiles are row-level populations aggregated separately | {metadata}"
        ),
        output=path,
        config=config,
    )
    paths.append(path)

    path = figures_directory / "07_chronological_stability.png"
    figure, axis = _figure(config)
    median_columns = [f"{day.lower()}_median_pips" for day in WEEKDAYS]
    missing_medians = sorted(set(median_columns).difference(period_results.columns))
    if missing_medians:
        raise ValueError(
            f"Canonical chronological plotting evidence is missing: {missing_medians}"
        )
    period_array = period_results[median_columns].to_numpy(dtype=float)
    x = np.arange(len(period_results))
    for index, day in enumerate(WEEKDAYS):
        axis.plot(
            x,
            period_array[:, index],
            label=day,
            color=palette[index],
            marker=MARKERS[index],
            linestyle=("-" if index < 2 else "--" if index < 4 else ":"),
        )
    axis.set_xticks(
        x,
        [
            f"{value.replace('_', chr(10))}\nn={int(sample_size):,}"
            for value, sample_size in zip(
                period_results["analysis_period"],
                period_results["sample_size"],
                strict=True,
            )
        ],
    )
    axis.set_ylabel("Median daily range (pips)")
    axis.set_ylim(bottom=0)
    axis.legend(frameon=False, ncol=3)
    _finish(
        figure,
        axis,
        title="Chronological stability of weekday daily ranges",
        subtitle=f"Fixed periods and ordered 70/30 split | {metadata}",
        output=path,
        config=config,
    )
    paths.append(path)

    path = figures_directory / "08_volatility_regime_comparison.png"
    figure, axis = _figure(config)
    regime_pivot = regime_stats.pivot_table(
        index="volatility_regime",
        columns="weekday_name",
        values="median",
        observed=True,
    ).reindex(["LOW", "MEDIUM", "HIGH"])
    x = np.arange(3)
    width = 0.16
    for index, day in enumerate(WEEKDAYS):
        axis.bar(
            x + (index - 2) * width,
            regime_pivot[day],
            width,
            label=day,
            color=palette[index],
            edgecolor="black",
            linewidth=0.5,
            hatch=("" if index < 2 else "//" if index < 4 else ".."),
            alpha=0.75,
        )
    regime_counts = regime_stats.groupby("volatility_regime", observed=True)[
        "sample_size"
    ].sum()
    axis.set_xticks(
        x,
        [
            f"{label.title()}\nn={int(regime_counts[label]):,}"
            for label in ("LOW", "MEDIUM", "HIGH")
        ],
    )
    axis.set_xlabel("Past-only volatility regime")
    axis.set_ylabel("Median daily range (pips)")
    axis.set_ylim(bottom=0)
    axis.legend(frameon=False, ncol=5)
    _finish(
        figure,
        axis,
        title="Weekday daily ranges within past-only volatility regimes",
        subtitle=(
            f"Current-day range is excluded from regime classification | {metadata}"
        ),
        output=path,
        config=config,
    )
    paths.append(path)
    return paths
