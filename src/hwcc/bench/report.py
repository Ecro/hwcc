"""Report generator — produces benchmark reports in JSON and Rich table format."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.table import Table

from hwcc.bench.scoring import compute_metrics_with_difficulty
from hwcc.bench.types import (
    BenchDataset,
    BenchMetrics,
    BenchQuestion,
    BenchReport,
    BenchResponse,
    BenchRun,
)
from hwcc.exceptions import BenchmarkError

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["generate_report", "generate_report_markdown", "print_report", "save_report"]

logger = logging.getLogger(__name__)

# Blended cost per 1M tokens (approximate input+output average).
# Last updated: 2026-03. For precise billing, check provider dashboards.
_COST_PER_1M_TOKENS: dict[str, float] = {
    "anthropic": 9.0,  # ~$3 input + $15 output blended
    "openai": 10.0,  # ~$5 input + $15 output blended
    "ollama": 0.0,
    "claude_code": 0.0,  # subscription-based
}


# Categories that belong to Register Knowledge (SVD-derived)
_REGISTER_CATEGORIES = frozenset(
    {
        "base_address",
        "register_offset",
        "bit_field",
        "reset_value",
        "access_type",
    }
)


def _knowledge_group(category: str) -> str:
    """Classify a category into Register Knowledge or Datasheet Knowledge."""
    if category in _REGISTER_CATEGORIES:
        return "Register Knowledge"
    return "Datasheet Knowledge"


def _estimate_cost(provider: str, total_tokens: int) -> float:
    """Estimate cost in USD from provider name and total token count."""
    rate = _COST_PER_1M_TOKENS.get(provider, 0.0)
    return total_tokens * rate / 1_000_000


def generate_report(
    runs: list[BenchRun],
    chip: str = "",
    dataset: BenchDataset | None = None,
) -> BenchReport:
    """Generate a benchmark report from run results.

    Computes per-condition metrics and cross-condition comparisons.

    Args:
        runs: List of benchmark runs (one per condition).
        chip: Chip name for the report header.
        dataset: Optional dataset for per-difficulty breakdown.

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

    # Build difficulty map from dataset (if provided)
    difficulty_map: dict[str, str] | None = None
    if dataset:
        difficulty_map = {q.id: q.difficulty for q in dataset.questions}

    # Group runs by condition (supports num_runs > 1)
    runs_by_condition: dict[str, list[BenchRun]] = {}
    for run in runs:
        runs_by_condition.setdefault(run.condition, []).append(run)

    # Compute per-condition metrics (pooling responses across runs, with Wilson CI)
    metrics: dict[str, BenchMetrics] = {}
    for condition_name, condition_runs in runs_by_condition.items():
        pooled: list[BenchResponse] = []
        for r in condition_runs:
            pooled.extend(r.responses)
        metrics[condition_name] = compute_metrics_with_difficulty(pooled, difficulty_map)

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
    summary.add_column("95% CI", justify="right")
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

        ci_str = f"[{m.ci_lower:.1%}, {m.ci_upper:.1%}]"

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
            ci_str,
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

    # Per-difficulty breakdown
    if any(m.by_difficulty for m in report.metrics.values()):
        console.print()
        diff_table = Table(title="Accuracy by Difficulty", show_lines=True)
        diff_table.add_column("Difficulty", style="bold")

        condition_names = list(report.metrics.keys())
        for name in condition_names:
            diff_table.add_column(name, justify="right")

        all_difficulties: set[str] = set()
        for m in report.metrics.values():
            all_difficulties.update(m.by_difficulty.keys())

        difficulty_order = {"easy": 0, "medium": 1, "hard": 2}
        for diff in sorted(all_difficulties, key=lambda d: difficulty_order.get(d, 99)):
            diff_row: list[str] = [diff]
            for name in condition_names:
                m = report.metrics[name]
                val = m.by_difficulty.get(diff, 0.0)
                val_str = f"{val:.1%}"
                if val >= 0.9:
                    val_str = f"[green]{val_str}[/green]"
                elif val >= 0.5:
                    val_str = f"[yellow]{val_str}[/yellow]"
                else:
                    val_str = f"[red]{val_str}[/red]"
                diff_row.append(val_str)
            diff_table.add_row(*diff_row)

        console.print(diff_table)

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
    has_ece = any(m.expected_calibration_error is not None for m in report.metrics.values())
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

    # Cost estimate
    total_tokens = sum(r.total_tokens for r in report.runs)
    if total_tokens > 0:
        provider_name = report.runs[0].provider
        cost = _estimate_cost(provider_name, total_tokens)
        if cost > 0:
            console.print()
            console.print(f"[dim]Estimated cost: ${cost:.2f}[/dim]")

    console.print()


def generate_report_markdown(
    report: BenchReport,
    dataset: BenchDataset | None = None,
) -> str:
    """Generate a markdown-formatted benchmark report.

    Args:
        report: The benchmark report to format.
        dataset: Optional dataset for source_ref display and category grouping.

    Returns:
        Markdown string suitable for saving to .md file.
    """
    if not report.runs:
        return f"# HwBench Report — {report.chip}\n\nNo benchmark results to display.\n"

    lines: list[str] = []
    lines.append(f"# HwBench Report — {report.chip}")
    lines.append("")
    lines.append(f"**Dataset:** {report.dataset_name}")
    lines.append(f"**Model:** {report.runs[0].model} ({report.runs[0].provider})")
    lines.append(f"**Chip:** {report.chip}")

    # Cost estimate
    total_tokens = sum(r.total_tokens for r in report.runs)
    if total_tokens > 0:
        provider_name = report.runs[0].provider
        cost = _estimate_cost(provider_name, total_tokens)
        if cost > 0:
            lines.append(f"**Estimated Cost:** ${cost:.2f}")

    lines.append("")

    # Summary table
    lines.append("## Results")
    lines.append("")
    lines.append("| Condition | Accuracy | 95% CI | Partial | Correct | Total |")
    lines.append("|-----------|----------|--------|---------|---------|-------|")

    for condition_name, m in report.metrics.items():
        ci_str = f"[{m.ci_lower:.1%}, {m.ci_upper:.1%}]"
        lines.append(
            f"| {condition_name} "
            f"| {m.accuracy:.1%} "
            f"| {ci_str} "
            f"| {m.avg_partial_score:.1%} "
            f"| {m.correct} "
            f"| {m.total} |"
        )

    lines.append("")

    # Per-difficulty table
    if any(m.by_difficulty for m in report.metrics.values()):
        lines.append("## Accuracy by Difficulty")
        lines.append("")

        condition_names = list(report.metrics.keys())
        header = "| Difficulty | " + " | ".join(condition_names) + " |"
        sep = "|------------|" + "|".join("-" * (len(n) + 2) for n in condition_names) + "|"
        lines.append(header)
        lines.append(sep)

        all_difficulties: set[str] = set()
        for m in report.metrics.values():
            all_difficulties.update(m.by_difficulty.keys())

        difficulty_order = {"easy": 0, "medium": 1, "hard": 2}
        for diff in sorted(all_difficulties, key=lambda d: difficulty_order.get(d, 99)):
            row_parts = [f"| {diff} "]
            for name in condition_names:
                m = report.metrics[name]
                val = m.by_difficulty.get(diff, 0.0)
                row_parts.append(f"| {val:.1%} ")
            row_parts.append("|")
            lines.append("".join(row_parts))

        lines.append("")

    # Impact summary (comparison)
    if report.comparison:
        baseline_acc = report.comparison.get("baseline_accuracy", 0.0)
        best_acc = report.comparison.get("best_accuracy", 0.0)
        delta = report.comparison.get("accuracy_delta", 0.0)

        lines.append("## Impact Summary")
        lines.append("")
        lines.append(f"- **Accuracy:** {baseline_acc:.1%} → {best_acc:.1%} (+{delta:.1%})")
        lines.append("")

    # Knowledge group breakdown (if dataset has mixed categories)
    question_map: dict[str, BenchQuestion] = {}
    if dataset:
        question_map = {q.id: q for q in dataset.questions}
        # Check if we have both register and datasheet categories
        groups: dict[str, list[str]] = {}
        for q in dataset.questions:
            group = _knowledge_group(q.category)
            groups.setdefault(group, []).append(q.category)
        if len(groups) > 1:
            lines.append("## Accuracy by Knowledge Group")
            lines.append("")
            condition_names = list(report.metrics.keys())
            header = "| Knowledge Group | " + " | ".join(condition_names) + " |"
            sep = (
                "|-----------------|" + "|".join("-" * (len(n) + 2) for n in condition_names) + "|"
            )
            lines.append(header)
            lines.append(sep)
            for group_name in ["Register Knowledge", "Datasheet Knowledge"]:
                if group_name not in groups:
                    continue
                row_parts = [f"| {group_name} "]
                for cond_name in condition_names:
                    m = report.metrics[cond_name]
                    # Sum accuracy for categories in this group
                    group_cats = set(groups[group_name])
                    cat_accs = [m.by_category[c] for c in group_cats if c in m.by_category]
                    if cat_accs:
                        avg = sum(cat_accs) / len(cat_accs)
                        row_parts.append(f"| {avg:.1%} ")
                    else:
                        row_parts.append("| — ")
                row_parts.append("|")
                lines.append("".join(row_parts))
            lines.append("")

    # Per-question detail
    lines.append("## Per-Question Detail")
    lines.append("")

    has_source_ref = any(q.source_ref for q in question_map.values()) if question_map else False
    for run in report.runs:
        lines.append(f"### {run.condition}")
        lines.append("")
        if has_source_ref:
            lines.append("| Question | Correct | Answer | Expected | Source |")
            lines.append("|----------|---------|--------|----------|--------|")
        else:
            lines.append("| Question | Correct | Answer | Expected |")
            lines.append("|----------|---------|--------|----------|")
        for resp in run.responses:
            correct_mark = "Y" if resp.correct else "N"
            if has_source_ref:
                q_info = question_map.get(resp.question_id)
                ref = q_info.source_ref if q_info else ""
                lines.append(
                    f"| {resp.question_id} | {correct_mark} "
                    f"| {resp.extracted_answer} | — | {ref} |"
                )
            else:
                lines.append(
                    f"| {resp.question_id} | {correct_mark} | {resp.extracted_answer} | — |"
                )
        lines.append("")

    return "\n".join(lines)


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
            ci_lower=m_data.get("ci_lower", 0.0),
            ci_upper=m_data.get("ci_upper", 0.0),
            by_difficulty=m_data.get("by_difficulty", {}),
        )

    return BenchReport(
        chip=data["chip"],
        dataset_name=data["dataset_name"],
        runs=tuple(runs),
        metrics=metrics,
        comparison=data.get("comparison", {}),
    )
