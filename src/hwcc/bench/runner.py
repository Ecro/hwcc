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
from hwcc.bench.svd_lookup import SVD_CATEGORIES, SvdLookupResult, lookup_svd_answer
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
    from hwcc.search import SearchEngine

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

    # Condition: raw_pdf (relevant datasheet chapters as plain text)
    raw_pdf_path = context_dir / "raw_pdf.md"
    if raw_pdf_path.exists():
        raw_content = raw_pdf_path.read_text(encoding="utf-8")
        max_raw_pdf_chars = 400_000
        if len(raw_content) > max_raw_pdf_chars:
            logger.warning(
                "raw_pdf.md truncated from %d to %d chars",
                len(raw_content),
                max_raw_pdf_chars,
            )
            raw_content = raw_content[:max_raw_pdf_chars]
        conditions.append(
            BenchCondition(
                name="raw_pdf",
                system_prompt=_BASE_SYSTEM_PROMPT.format(
                    chip=chip,
                    context_block=f"Here is the raw datasheet text:\n\n{raw_content}",
                ),
                description=f"Raw PDF chapter text ({len(raw_content)} chars, no hwcc processing)",
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
    search_engine: SearchEngine | None = None,
    rag_top_k: int = 5,
    svd_device: object | None = None,
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
        search_engine: Optional SearchEngine for hwcc_rag condition. When provided
            and a condition named "hwcc_rag" is in the list, each question gets
            per-question context via vector search.
        rag_top_k: Number of chunks to retrieve per question for RAG (default 5).
        svd_device: Optional parsed SVDDevice for svd_lookup and hybrid conditions.

    Returns:
        List of BenchRun results. With num_runs > 1, multiple runs per condition
        are returned (total = len(conditions) * num_runs).
    """
    runs: list[BenchRun] = []

    # Resolve LLM fallback condition for hybrid routing (hwcc_full > hwcc_hot > no_context)
    llm_fallback = _resolve_llm_fallback(conditions)

    for condition in conditions:
        # Skip conditions that require unavailable dependencies
        if condition.name == "hwcc_rag" and search_engine is None:
            logger.warning("Skipping hwcc_rag condition: no search engine provided")
            continue
        if condition.name == "svd_lookup" and svd_device is None:
            logger.warning("Skipping svd_lookup condition: no SVD device provided")
            continue
        if condition.name == "hybrid" and svd_device is None:
            logger.warning("Skipping hybrid condition: no SVD device provided")
            continue

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

                if condition.name == "svd_lookup":
                    response, tokens = _handle_svd_lookup(question, svd_device)
                elif condition.name == "hybrid":
                    response, tokens = _handle_hybrid(
                        question,
                        svd_device,
                        provider,
                        search_engine,
                        llm_fallback,
                        dataset.chip,
                        rag_top_k,
                    )
                else:
                    # Standard LLM path
                    effective_condition = condition
                    if condition.name == "hwcc_rag" and search_engine is not None:
                        effective_condition = _build_rag_condition_from_engine(
                            question,
                            search_engine,
                            dataset.chip,
                            top_k=rag_top_k,
                        )
                    response, tokens = _ask_question(
                        question, effective_condition, provider
                    )

                responses.append(response)
                total_tokens += tokens

                # Rate limiting (skip for pure SVD lookup — no API call)
                needs_delay = condition.name != "svd_lookup"
                if condition.name == "hybrid":
                    needs_delay = question.category not in SVD_CATEGORIES
                if needs_delay and delay_seconds > 0 and i < dataset.question_count - 1:
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


def _resolve_llm_fallback(conditions: list[BenchCondition]) -> BenchCondition | None:
    """Find the best LLM fallback condition for hybrid routing.

    Priority: hwcc_full > hwcc_hot > no_context.
    """
    by_name = {c.name: c for c in conditions}
    for name in ("hwcc_full", "hwcc_hot", "no_context"):
        if name in by_name:
            return by_name[name]
    return None


def _handle_svd_lookup(
    question: BenchQuestion,
    svd_device: object | None,
) -> tuple[BenchResponse, int]:
    """Answer a question via direct SVD lookup (no LLM)."""
    if svd_device is None:
        return _svd_unanswerable_response(question, 0.0), 0

    result = lookup_svd_answer(question, svd_device)
    return _svd_result_to_response(question, result), 0


def _handle_hybrid(
    question: BenchQuestion,
    svd_device: object | None,
    provider: BaseBenchProvider,
    search_engine: SearchEngine | None,
    llm_fallback: BenchCondition | None,
    chip: str,
    rag_top_k: int,
) -> tuple[BenchResponse, int]:
    """Route a question to the best condition via hybrid routing."""
    route = _route_question(question)

    if route == "svd_lookup" and svd_device is not None:
        result = lookup_svd_answer(question, svd_device)
        return _svd_result_to_response(question, result), 0

    # Non-SVD question: use RAG if available, else LLM fallback
    if route == "hwcc_rag" and search_engine is not None:
        effective = _build_rag_condition_from_engine(
            question, search_engine, chip, top_k=rag_top_k
        )
        return _ask_question(question, effective, provider)

    # Fallback to best available LLM condition
    if llm_fallback is not None:
        return _ask_question(question, llm_fallback, provider)

    # No fallback available — build a minimal no_context condition
    fallback = BenchCondition(
        name="no_context",
        system_prompt=_BASE_SYSTEM_PROMPT.format(chip=chip, context_block=""),
        description="No context fallback",
    )
    return _ask_question(question, fallback, provider)


def _route_question(question: BenchQuestion) -> str:
    """Route a question to the best condition name."""
    if question.category in SVD_CATEGORIES:
        return "svd_lookup"
    if question.peripheral:
        return "hwcc_rag"
    return "hwcc_full"


def _svd_result_to_response(
    question: BenchQuestion,
    result: SvdLookupResult,
) -> BenchResponse:
    """Convert an SvdLookupResult to a BenchResponse with scoring."""
    if not result.answerable:
        return _svd_unanswerable_response(question, result.latency_ms)

    sc = score_answer(result.answer, question.answer, question.answer_format)
    partial = score_answer_partial(result.answer, question.answer, question.answer_format)

    return BenchResponse(
        question_id=question.id,
        raw_response=result.answer,
        extracted_answer=result.answer,
        correct=sc == 1.0,
        score=sc,
        latency_ms=result.latency_ms,
        partial_score=partial,
        confidence=1.0,
    )


def _svd_unanswerable_response(
    question: BenchQuestion,
    latency_ms: float,
) -> BenchResponse:
    """Build a BenchResponse for an unanswerable SVD lookup."""
    return BenchResponse(
        question_id=question.id,
        raw_response="[SVD_UNANSWERABLE]",
        extracted_answer="",
        correct=False,
        score=0.0,
        latency_ms=latency_ms,
        partial_score=0.0,
        confidence=None,
    )


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


def _build_rag_condition_from_engine(
    question: BenchQuestion,
    search_engine: SearchEngine,
    chip: str,
    top_k: int = 5,
    max_chars: int = 32_000,
) -> BenchCondition:
    """Build a per-question RAG condition using a SearchEngine.

    Args:
        question: The benchmark question to build context for.
        search_engine: SearchEngine instance for vector search.
        chip: Chip name for prompt interpolation.
        top_k: Number of chunks to retrieve.
        max_chars: Maximum characters for assembled context.

    Returns:
        BenchCondition with retrieved chunks as context.
    """
    results, _elapsed = search_engine.search(query=question.question, k=top_k, chip=chip)
    chunks: list[str] = []
    total_chars = 0
    for result in results:
        text = result.chunk.content
        if total_chars + len(text) > max_chars:
            break
        chunks.append(text)
        total_chars += len(text)
    context = "\n\n---\n\n".join(chunks)
    return BenchCondition(
        name="hwcc_rag",
        system_prompt=_BASE_SYSTEM_PROMPT.format(
            chip=chip,
            context_block=f"Here are relevant documentation excerpts:\n\n{context}",
        ),
        description=f"hwcc RAG: top-{top_k} chunks ({total_chars} chars)",
    )
