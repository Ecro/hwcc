"""Benchmark runner — executes benchmark questions against LLM providers."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hwcc.bench.scoring import (
    compute_metrics,
    extract_answer,
    extract_confidence,
    score_answer,
    score_answer_partial,
)
from hwcc.bench.types import (
    BenchCondition,
    BenchDataset,
    BenchQuestion,
    BenchResponse,
    BenchRun,
)
from hwcc.exceptions import BenchmarkError

if TYPE_CHECKING:
    from pathlib import Path

    from hwcc.bench.providers import BaseBenchProvider

__all__ = ["prepare_conditions", "run_benchmark"]

logger = logging.getLogger(__name__)

_BASE_SYSTEM_PROMPT = (
    "You are a hardware engineer working with the {chip} microcontroller.\n"
    "{context_block}\n"
    "Answer the following question about {chip} hardware.\n"
    "Reply with ONLY the exact value. No explanation, no units, no surrounding text."
)

ProgressCallback = Callable[[str, int, int], None]


def prepare_conditions(
    context_dir: Path | None,
    chip: str,
    peripheral_names: list[str] | None = None,
) -> list[BenchCondition]:
    """Build benchmark conditions from available context files.

    Args:
        context_dir: Path to .rag/context/ directory (None for no-context only).
        chip: Chip name for prompt interpolation.
        peripheral_names: List of peripheral names to load context for.

    Returns:
        List of BenchCondition objects.
    """
    conditions: list[BenchCondition] = []

    # Condition 1: No context (always)
    conditions.append(
        BenchCondition(
            name="no_context",
            system_prompt=_BASE_SYSTEM_PROMPT.format(chip=chip, context_block=""),
            description="No hardware documentation provided",
        )
    )

    if context_dir is None or not context_dir.is_dir():
        return conditions

    # Condition 2: Hot context only
    hot_path = context_dir / "hot.md"
    if hot_path.exists():
        hot_content = hot_path.read_text(encoding="utf-8")
        context_block = f"Here is the hardware context for this microcontroller:\n\n{hot_content}"
        conditions.append(
            BenchCondition(
                name="hwcc_hot",
                system_prompt=_BASE_SYSTEM_PROMPT.format(chip=chip, context_block=context_block),
                description="hwcc hot context only (~120 lines)",
            )
        )

    # Condition 3: Full context (hot + all relevant peripherals)
    periph_dir = context_dir / "peripherals"
    if periph_dir.is_dir():
        periph_contents: list[str] = []
        if hot_path.exists():
            periph_contents.append(hot_path.read_text(encoding="utf-8"))

        # Load all peripheral files (or filter by names)
        for md_file in sorted(periph_dir.glob("*.md")):
            if peripheral_names:
                stem_upper = md_file.stem.upper()
                if not any(stem_upper.startswith(p.upper()) for p in peripheral_names):
                    continue
            periph_contents.append(md_file.read_text(encoding="utf-8"))

        if periph_contents:
            full_context = "\n\n---\n\n".join(periph_contents)
            context_block = (
                "Here is the complete hardware context for this microcontroller:\n\n"
                f"{full_context}"
            )
            conditions.append(
                BenchCondition(
                    name="hwcc_full",
                    system_prompt=_BASE_SYSTEM_PROMPT.format(
                        chip=chip, context_block=context_block
                    ),
                    description="hwcc hot + peripheral context",
                )
            )

    return conditions


def run_benchmark(
    dataset: BenchDataset,
    provider: BaseBenchProvider,
    conditions: list[BenchCondition],
    delay_seconds: float = 0.5,
    progress_callback: ProgressCallback | None = None,
    num_runs: int = 1,
) -> list[BenchRun]:
    """Execute benchmark: run all questions under each condition.

    Args:
        dataset: The benchmark dataset.
        provider: LLM provider to use.
        conditions: List of context conditions to test.
        delay_seconds: Delay between API calls for rate limiting.
        progress_callback: Optional callback(condition_name, question_index, total).
        num_runs: Number of runs per condition (default 1). Multiple runs enable
            statistical analysis (mean, std, CI).

    Returns:
        List of BenchRun results. With num_runs > 1, multiple runs per condition
        are returned (total = len(conditions) * num_runs).
    """
    runs: list[BenchRun] = []

    for condition in conditions:
        for run_idx in range(num_runs):
            run_label = condition.name
            if num_runs > 1:
                run_label = f"{condition.name} (run {run_idx + 1}/{num_runs})"

            logger.info(
                "Running %s with %d questions on %s/%s",
                run_label,
                dataset.question_count,
                provider.name,
                provider.model_name,
            )

            started = datetime.now(UTC).isoformat()
            responses: list[BenchResponse] = []
            total_tokens = 0

            for i, question in enumerate(dataset.questions):
                if progress_callback:
                    progress_callback(condition.name, i, dataset.question_count)

                response, tokens = _ask_question(question, condition, provider)
                responses.append(response)
                total_tokens += tokens

                # Rate limiting
                if delay_seconds > 0 and i < dataset.question_count - 1:
                    time.sleep(delay_seconds)

            completed = datetime.now(UTC).isoformat()

            run = BenchRun(
                dataset_name=dataset.name,
                condition=condition.name,
                model=provider.model_name,
                provider=provider.name,
                temperature=0.0,
                responses=tuple(responses),
                started=started,
                completed=completed,
                total_tokens=total_tokens,
            )
            runs.append(run)

            metrics = compute_metrics(run.responses)
            logger.info(
                "%s: %d/%d correct (%.1f%% accuracy)",
                run_label,
                metrics.correct,
                metrics.total,
                metrics.accuracy * 100,
            )

    return runs


def _ask_question(
    question: BenchQuestion,
    condition: BenchCondition,
    provider: BaseBenchProvider,
) -> tuple[BenchResponse, int]:
    """Ask a single question and score the response.

    Returns:
        Tuple of (BenchResponse, tokens_used).
    """
    try:
        result = provider.query(
            system_prompt=condition.system_prompt,
            user_prompt=question.question,
        )
    except BenchmarkError:
        # API error — count as incorrect
        return (
            BenchResponse(
                question_id=question.id,
                raw_response="[API_ERROR]",
                extracted_answer="",
                correct=False,
                score=0.0,
                latency_ms=0.0,
            ),
            0,
        )

    extracted = extract_answer(result.text, question.answer_format)
    score = score_answer(extracted, question.answer, question.answer_format)
    partial = score_answer_partial(extracted, question.answer, question.answer_format)
    confidence = extract_confidence(result.text)

    return (
        BenchResponse(
            question_id=question.id,
            raw_response=result.text,
            extracted_answer=extracted,
            correct=score == 1.0,
            score=score,
            latency_ms=result.latency_ms,
            partial_score=partial,
            confidence=confidence,
        ),
        result.tokens_used,
    )
