"""Report generator — produces benchmark reports in JSON and Rich table format."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.table import Table

from hwcc.bench.scoring import compute_metrics
from hwcc.bench.types import BenchMetrics, BenchReport, BenchRun
from hwcc.exceptions import BenchmarkError

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["generate_report", "print_report", "save_report"]

logger = logging.getLogger(__name__)


def generate_report(
    runs: list[BenchRun],
    chip: str = "",
) -> BenchReport:
    """Generate a benchmark report from run results.

    Computes per-condition metrics and cross-condition comparisons.

    Args:
        runs: List of benchmark runs (one per condition).
        chip: Chip name for the report header.

    Returns:
        Complete BenchReport with metrics and comparisons.
    """
    if not runs:
        return BenchReport(
            chip=chip,
            dataset_name="",
            runs=(),
            metrics={},
            comparison={},
        )

    dataset_name = runs[0].dataset_name

    # Compute per-condition metrics
    metrics: dict[str, BenchMetrics] = {}
    for run in runs:
        m = compute_metrics(run.responses)
        metrics[run.condition] = m

    # Compute comparison (delta between no_context and best hwcc condition)
    comparison: dict[str, float] = {}
    baseline = metrics.get("no_context")
    if baseline:
        best_hwcc_accuracy = 0.0
        best_hwcc_condition = ""
        for name, m in metrics.items():
            if name != "no_context" and m.accuracy > best_hwcc_accuracy:
                best_hwcc_accuracy = m.accuracy
                best_hwcc_condition = name

        if best_hwcc_condition:
            best = metrics[best_hwcc_condition]
            comparison["accuracy_delta"] = best.accuracy - baseline.accuracy
            comparison["hallucination_reduction"] = (
                baseline.hallucination_rate - best.hallucination_rate
            )
            comparison["baseline_accuracy"] = baseline.accuracy
            comparison["best_accuracy"] = best.accuracy
            comparison["best_condition"] = 0.0  # Can't store string in float dict

    return BenchReport(
        chip=chip or runs[0].dataset_name.split("_")[0],
        dataset_name=dataset_name,
        runs=tuple(runs),
        metrics=metrics,
        comparison=comparison,
    )


def print_report(report: BenchReport, console: Console | None = None) -> None:
    """Print a benchmark report as a Rich table.

    Args:
        report: The benchmark report to display.
        console: Rich Console instance (creates one if None).
    """
    if console is None:
        console = Console()

    if not report.runs:
        console.print("[yellow]No benchmark results to display.[/yellow]")
        return

    # Header
    console.print()
    console.print(f"[bold]HwBench Report — {report.chip}[/bold]")
    console.print(f"Dataset: {report.dataset_name}")
    console.print(f"Model: {report.runs[0].model} ({report.runs[0].provider})")
    console.print()

    # Summary table
    summary = Table(title="Accuracy by Condition", show_lines=True)
    summary.add_column("Condition", style="bold")
    summary.add_column("Accuracy", justify="right")
    summary.add_column("Partial", justify="right")
    summary.add_column("Correct", justify="right")
    summary.add_column("Total", justify="right")
    summary.add_column("Hallucination Rate", justify="right")
    summary.add_column("Avg Latency", justify="right")

    for condition_name, m in report.metrics.items():
        accuracy_str = f"{m.accuracy:.1%}"
        if m.accuracy >= 0.9:
            accuracy_str = f"[green]{accuracy_str}[/green]"
        elif m.accuracy >= 0.5:
            accuracy_str = f"[yellow]{accuracy_str}[/yellow]"
        else:
            accuracy_str = f"[red]{accuracy_str}[/red]"

        partial_str = f"{m.avg_partial_score:.1%}"

        halluc_str = f"{m.hallucination_rate:.1%}"
        if m.hallucination_rate <= 0.1:
            halluc_str = f"[green]{halluc_str}[/green]"
        elif m.hallucination_rate <= 0.5:
            halluc_str = f"[yellow]{halluc_str}[/yellow]"
        else:
            halluc_str = f"[red]{halluc_str}[/red]"

        summary.add_row(
            condition_name,
            accuracy_str,
            partial_str,
            str(m.correct),
            str(m.total),
            halluc_str,
            f"{m.avg_latency_ms:.0f}ms",
        )

    console.print(summary)

    # Per-category breakdown
    if any(m.by_category for m in report.metrics.values()):
        console.print()
        cat_table = Table(title="Accuracy by Category", show_lines=True)
        cat_table.add_column("Category", style="bold")

        condition_names = list(report.metrics.keys())
        for name in condition_names:
            cat_table.add_column(name, justify="right")

        # Collect all categories
        all_categories: set[str] = set()
        for m in report.metrics.values():
            all_categories.update(m.by_category.keys())

        for cat in sorted(all_categories):
            row = [cat]
            for name in condition_names:
                m = report.metrics[name]
                val = m.by_category.get(cat, 0.0)
                val_str = f"{val:.1%}"
                if val >= 0.9:
                    val_str = f"[green]{val_str}[/green]"
                elif val >= 0.5:
                    val_str = f"[yellow]{val_str}[/yellow]"
                else:
                    val_str = f"[red]{val_str}[/red]"
                row.append(val_str)
            cat_table.add_row(*row)

        console.print(cat_table)

    # Comparison summary
    if report.comparison:
        console.print()
        delta = report.comparison.get("accuracy_delta", 0.0)
        halluc_reduction = report.comparison.get("hallucination_reduction", 0.0)
        baseline_acc = report.comparison.get("baseline_accuracy", 0.0)
        best_acc = report.comparison.get("best_accuracy", 0.0)

        console.print("[bold]Impact Summary[/bold]")
        console.print(
            f"  Accuracy:       {baseline_acc:.1%} → {best_acc:.1%} ([green]+{delta:.1%}[/green])"
        )
        console.print(
            f"  Hallucination:  {1.0 - baseline_acc:.1%} → {1.0 - best_acc:.1%} "
            f"([green]-{halluc_reduction:.1%}[/green])"
        )

    # Calibration summary (if any condition has ECE data)
    has_ece = any(
        m.expected_calibration_error is not None for m in report.metrics.values()
    )
    if has_ece:
        console.print()
        console.print("[bold]Confidence Calibration[/bold]")
        for cond_name, m in report.metrics.items():
            if m.expected_calibration_error is not None:
                ece_val = m.expected_calibration_error
                ece_str = f"{ece_val:.3f}"
                if ece_val <= 0.1:
                    ece_str = f"[green]{ece_str}[/green]"
                elif ece_val <= 0.3:
                    ece_str = f"[yellow]{ece_str}[/yellow]"
                else:
                    ece_str = f"[red]{ece_str}[/red]"
                console.print(f"  {cond_name}: ECE = {ece_str}")

    console.print()


def save_report(report: BenchReport, path: Path) -> None:
    """Save a benchmark report to JSON.

    Args:
        report: The report to save.
        path: Output file path.

    Raises:
        BenchmarkError: If writing fails.
    """
    try:
        data = _report_to_dict(report)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as e:
        msg = f"Failed to save report: {e}"
        raise BenchmarkError(msg) from e

    logger.info("Saved report to %s", path)


def load_report(path: Path) -> BenchReport:
    """Load a benchmark report from JSON.

    Args:
        path: Path to the JSON file.

    Returns:
        Loaded BenchReport.

    Raises:
        BenchmarkError: If reading or parsing fails.
    """
    if not path.exists():
        msg = f"Report file not found: {path}"
        raise BenchmarkError(msg)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        msg = f"Failed to load report: {e}"
        raise BenchmarkError(msg) from e

    try:
        return _dict_to_report(data)
    except (KeyError, TypeError) as e:
        msg = f"Invalid report format: {e}"
        raise BenchmarkError(msg) from e


def _report_to_dict(report: BenchReport) -> dict[str, Any]:
    """Convert a BenchReport to a JSON-serializable dict."""
    return {
        "chip": report.chip,
        "dataset_name": report.dataset_name,
        "runs": [asdict(run) for run in report.runs],
        "metrics": {name: asdict(m) for name, m in report.metrics.items()},
        "comparison": report.comparison,
    }


def _dict_to_report(data: dict[str, Any]) -> BenchReport:
    """Convert a dict back to a BenchReport."""
    from hwcc.bench.types import BenchResponse, BenchRun

    runs = []
    for run_data in data.get("runs", []):
        responses = tuple(BenchResponse(**r) for r in run_data.get("responses", []))
        runs.append(
            BenchRun(
                dataset_name=run_data["dataset_name"],
                condition=run_data["condition"],
                model=run_data["model"],
                provider=run_data["provider"],
                temperature=run_data["temperature"],
                responses=responses,
                started=run_data["started"],
                completed=run_data["completed"],
                total_tokens=run_data["total_tokens"],
            )
        )

    metrics = {}
    for name, m_data in data.get("metrics", {}).items():
        metrics[name] = BenchMetrics(
            total=m_data["total"],
            correct=m_data["correct"],
            accuracy=m_data["accuracy"],
            hallucination_rate=m_data["hallucination_rate"],
            by_category=m_data.get("by_category", {}),
            avg_latency_ms=m_data.get("avg_latency_ms", 0.0),
            total_tokens=m_data.get("total_tokens", 0),
            avg_partial_score=m_data.get("avg_partial_score", 0.0),
            expected_calibration_error=m_data.get("expected_calibration_error"),
        )

    return BenchReport(
        chip=data["chip"],
        dataset_name=data["dataset_name"],
        runs=tuple(runs),
        metrics=metrics,
        comparison=data.get("comparison", {}),
    )
