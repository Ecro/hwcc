"""Tests for hwcc.bench.runner — benchmark orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hwcc.bench.providers import BaseBenchProvider, ProviderResponse
from hwcc.bench.runner import _ask_question, prepare_conditions, run_benchmark
from hwcc.bench.types import BenchCondition, BenchDataset, BenchQuestion
from hwcc.exceptions import BenchmarkError

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_dataset(questions: tuple[BenchQuestion, ...] | None = None) -> BenchDataset:
    """Create a minimal dataset for testing."""
    if questions is None:
        questions = (
            BenchQuestion(
                id="spi1_base_address",
                category="base_address",
                peripheral="SPI1",
                register="",
                field_name="",
                question="What is the base address of SPI1?",
                answer="0x40013000",
                answer_format="hex",
            ),
            BenchQuestion(
                id="spi1_cr1_offset",
                category="register_offset",
                peripheral="SPI1",
                register="CR1",
                field_name="",
                question="What is the offset of SPI1_CR1?",
                answer="0x0000",
                answer_format="hex",
            ),
        )
    return BenchDataset(
        name="TEST_RegisterKnowledge",
        chip="TESTCHIP",
        source_svd="/tmp/test.svd",
        question_count=len(questions),
        questions=questions,
        created="2026-03-02T00:00:00+00:00",
        categories=("base_address", "register_offset"),
    )


class _MockProvider(BaseBenchProvider):
    """Mock provider that returns a fixed answer."""

    def __init__(self, answer: str = "0x40013000") -> None:
        self._answer = answer
        self._call_count = 0

    def query(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        self._call_count += 1
        return ProviderResponse(text=self._answer, tokens_used=10, latency_ms=50.0)

    @property
    def name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-v1"


class _ErrorProvider(BaseBenchProvider):
    """Mock provider that always raises BenchmarkError."""

    def query(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        msg = "API call failed"
        raise BenchmarkError(msg)

    @property
    def name(self) -> str:
        return "error_mock"

    @property
    def model_name(self) -> str:
        return "error-v1"


# ---------------------------------------------------------------------------
# TestPrepareConditions
# ---------------------------------------------------------------------------


class TestPrepareConditions:
    """Tests for prepare_conditions()."""

    def test_no_context_dir_returns_only_no_context(self):
        conditions = prepare_conditions(None, chip="TESTCHIP")
        assert len(conditions) == 1
        assert conditions[0].name == "no_context"
        assert "TESTCHIP" in conditions[0].system_prompt

    def test_nonexistent_context_dir_returns_only_no_context(self, tmp_path: Path):
        conditions = prepare_conditions(tmp_path / "nonexistent", chip="TESTCHIP")
        assert len(conditions) == 1
        assert conditions[0].name == "no_context"

    def test_with_hot_md(self, tmp_path: Path):
        context_dir = tmp_path / "context"
        context_dir.mkdir()
        (context_dir / "hot.md").write_text("# SPI1\nBase: 0x40013000\n", encoding="utf-8")

        conditions = prepare_conditions(context_dir, chip="TESTCHIP")
        assert len(conditions) == 2
        assert conditions[0].name == "no_context"
        assert conditions[1].name == "hwcc_hot"
        assert "0x40013000" in conditions[1].system_prompt

    def test_with_peripherals_dir(self, tmp_path: Path):
        context_dir = tmp_path / "context"
        context_dir.mkdir()
        (context_dir / "hot.md").write_text("# Hot context\n", encoding="utf-8")
        periph_dir = context_dir / "peripherals"
        periph_dir.mkdir()
        (periph_dir / "SPI1.md").write_text("# SPI1 details\n", encoding="utf-8")

        conditions = prepare_conditions(context_dir, chip="TESTCHIP")
        assert len(conditions) == 3
        names = [c.name for c in conditions]
        assert names == ["no_context", "hwcc_hot", "hwcc_full"]
        assert "SPI1 details" in conditions[2].system_prompt

    def test_peripheral_filter(self, tmp_path: Path):
        context_dir = tmp_path / "context"
        context_dir.mkdir()
        periph_dir = context_dir / "peripherals"
        periph_dir.mkdir()
        (periph_dir / "SPI1.md").write_text("SPI1 data", encoding="utf-8")
        (periph_dir / "USART1.md").write_text("USART1 data", encoding="utf-8")
        (periph_dir / "TIM2.md").write_text("TIM2 data", encoding="utf-8")

        conditions = prepare_conditions(
            context_dir,
            chip="TESTCHIP",
            peripheral_names=["SPI1"],
        )
        # no_context + hwcc_full (filtered)
        assert len(conditions) == 2
        full_cond = conditions[1]
        assert "SPI1 data" in full_cond.system_prompt
        assert "USART1 data" not in full_cond.system_prompt
        assert "TIM2 data" not in full_cond.system_prompt

    def test_empty_peripherals_dir_no_full_condition(self, tmp_path: Path):
        context_dir = tmp_path / "context"
        context_dir.mkdir()
        periph_dir = context_dir / "peripherals"
        periph_dir.mkdir()
        # Empty peripherals directory

        conditions = prepare_conditions(context_dir, chip="TESTCHIP")
        assert len(conditions) == 1  # Only no_context
        assert conditions[0].name == "no_context"


# ---------------------------------------------------------------------------
# TestRunBenchmark
# ---------------------------------------------------------------------------


class TestRunBenchmark:
    """Tests for run_benchmark()."""

    def test_single_condition_correct_answers(self):
        dataset = _make_dataset()
        provider = _MockProvider(answer="0x40013000")
        conditions = [
            BenchCondition(
                name="no_context",
                system_prompt="You are a hardware engineer.",
                description="Test condition",
            ),
        ]

        runs = run_benchmark(
            dataset,
            provider,
            conditions,
            delay_seconds=0,
        )

        assert len(runs) == 1
        run = runs[0]
        assert run.condition == "no_context"
        assert run.model == "mock-v1"
        assert run.provider == "mock"
        assert run.dataset_name == "TEST_RegisterKnowledge"
        assert len(run.responses) == 2
        # First question (base_address) should be correct
        assert run.responses[0].correct is True
        assert run.responses[0].extracted_answer == "0x40013000"

    def test_multiple_conditions(self):
        dataset = _make_dataset()
        provider = _MockProvider(answer="0x40013000")
        conditions = [
            BenchCondition("no_context", "prompt1", "No context"),
            BenchCondition("hwcc_full", "prompt2", "Full context"),
        ]

        runs = run_benchmark(
            dataset,
            provider,
            conditions,
            delay_seconds=0,
        )

        assert len(runs) == 2
        assert runs[0].condition == "no_context"
        assert runs[1].condition == "hwcc_full"

    def test_api_error_counted_as_incorrect(self):
        dataset = _make_dataset()
        provider = _ErrorProvider()
        conditions = [
            BenchCondition("no_context", "prompt", "Test"),
        ]

        runs = run_benchmark(
            dataset,
            provider,
            conditions,
            delay_seconds=0,
        )

        assert len(runs) == 1
        for resp in runs[0].responses:
            assert resp.correct is False
            assert resp.raw_response == "[API_ERROR]"
            assert resp.extracted_answer == ""

    def test_progress_callback_called(self):
        dataset = _make_dataset()
        provider = _MockProvider(answer="0x40013000")
        conditions = [
            BenchCondition("no_context", "prompt", "Test"),
        ]

        callback_calls: list[tuple[str, int, int]] = []

        def on_progress(cond_name: str, idx: int, total: int) -> None:
            callback_calls.append((cond_name, idx, total))

        run_benchmark(
            dataset,
            provider,
            conditions,
            delay_seconds=0,
            progress_callback=on_progress,
        )

        assert len(callback_calls) == 2
        assert callback_calls[0] == ("no_context", 0, 2)
        assert callback_calls[1] == ("no_context", 1, 2)

    def test_tokens_accumulated(self):
        dataset = _make_dataset()
        provider = _MockProvider(answer="0x40013000")
        conditions = [
            BenchCondition("no_context", "prompt", "Test"),
        ]

        runs = run_benchmark(
            dataset,
            provider,
            conditions,
            delay_seconds=0,
        )

        assert runs[0].total_tokens == 20  # 10 per question * 2 questions


# ---------------------------------------------------------------------------
# TestAskQuestion
# ---------------------------------------------------------------------------


class TestAskQuestion:
    """Tests for _ask_question()."""

    def test_correct_hex_answer(self):
        question = BenchQuestion(
            id="spi1_base_address",
            category="base_address",
            peripheral="SPI1",
            register="",
            field_name="",
            question="What is the base address of SPI1?",
            answer="0x40013000",
            answer_format="hex",
        )
        condition = BenchCondition("test", "system prompt", "desc")
        provider = _MockProvider(answer="0x40013000")

        response, tokens = _ask_question(question, condition, provider)

        assert response.correct is True
        assert response.score == 1.0
        assert response.extracted_answer == "0x40013000"
        assert response.latency_ms == 50.0
        assert tokens == 10

    def test_wrong_hex_answer(self):
        question = BenchQuestion(
            id="spi1_base_address",
            category="base_address",
            peripheral="SPI1",
            register="",
            field_name="",
            question="What is the base address of SPI1?",
            answer="0x40013000",
            answer_format="hex",
        )
        condition = BenchCondition("test", "system prompt", "desc")
        provider = _MockProvider(answer="0xDEADBEEF")

        response, tokens = _ask_question(question, condition, provider)

        assert response.correct is False
        assert response.score == 0.0
        assert response.partial_score < 1.0

    def test_api_error_returns_error_response(self):
        question = BenchQuestion(
            id="spi1_base_address",
            category="base_address",
            peripheral="SPI1",
            register="",
            field_name="",
            question="What is the base address of SPI1?",
            answer="0x40013000",
            answer_format="hex",
        )
        condition = BenchCondition("test", "system prompt", "desc")
        provider = _ErrorProvider()

        response, tokens = _ask_question(question, condition, provider)

        assert response.correct is False
        assert response.raw_response == "[API_ERROR]"
        assert tokens == 0

    def test_bit_range_extraction_and_scoring(self):
        question = BenchQuestion(
            id="spi1_cr1_br_bits",
            category="bit_field",
            peripheral="SPI1",
            register="CR1",
            field_name="BR",
            question="What bits does BR occupy?",
            answer="[5:3]",
            answer_format="bit_range",
        )
        condition = BenchCondition("test", "system prompt", "desc")
        provider = _MockProvider(answer="[5:3]")

        response, tokens = _ask_question(question, condition, provider)

        assert response.correct is True
        assert response.extracted_answer == "[5:3]"

    def test_access_code_extraction_and_scoring(self):
        question = BenchQuestion(
            id="spi1_cr1_access",
            category="access_type",
            peripheral="SPI1",
            register="CR1",
            field_name="",
            question="What is the access type of SPI1_CR1?",
            answer="RW",
            answer_format="access_code",
        )
        condition = BenchCondition("test", "system prompt", "desc")
        provider = _MockProvider(answer="read-write")

        response, tokens = _ask_question(question, condition, provider)

        assert response.correct is True
        assert response.extracted_answer == "RW"

    def test_confidence_extracted(self):
        question = BenchQuestion(
            id="spi1_base_address",
            category="base_address",
            peripheral="SPI1",
            register="",
            field_name="",
            question="What is the base address of SPI1?",
            answer="0x40013000",
            answer_format="hex",
        )
        condition = BenchCondition("test", "system prompt", "desc")
        provider = _MockProvider(answer="0x40013000\nConfidence: 90%")

        response, tokens = _ask_question(question, condition, provider)

        assert response.correct is True
        assert response.confidence == 0.9


# ---------------------------------------------------------------------------
# TestRunBenchmarkMultiRun
# ---------------------------------------------------------------------------


class TestPrepareConditionsRawPdf:
    """Tests for raw_pdf condition in prepare_conditions()."""

    def test_raw_pdf_condition_created(self, tmp_path: Path):
        context_dir = tmp_path / "context"
        context_dir.mkdir()
        (context_dir / "raw_pdf.md").write_text("# SPI chapter\nSome content.\n", encoding="utf-8")

        conditions = prepare_conditions(context_dir, chip="TESTCHIP")
        names = [c.name for c in conditions]
        assert "raw_pdf" in names

    def test_raw_pdf_content_in_prompt(self, tmp_path: Path):
        context_dir = tmp_path / "context"
        context_dir.mkdir()
        (context_dir / "raw_pdf.md").write_text("VDD range is 1.8V to 3.6V", encoding="utf-8")

        conditions = prepare_conditions(context_dir, chip="TESTCHIP")
        raw_pdf_cond = next(c for c in conditions if c.name == "raw_pdf")
        assert "1.8V to 3.6V" in raw_pdf_cond.system_prompt

    def test_raw_pdf_truncation(self, tmp_path: Path):
        context_dir = tmp_path / "context"
        context_dir.mkdir()
        # Write a file larger than 400K chars
        big_content = "A" * 500_000
        (context_dir / "raw_pdf.md").write_text(big_content, encoding="utf-8")

        conditions = prepare_conditions(context_dir, chip="TESTCHIP")
        raw_pdf_cond = next(c for c in conditions if c.name == "raw_pdf")
        # System prompt should contain truncated content
        assert len(raw_pdf_cond.system_prompt) < 500_000

    def test_no_raw_pdf_without_file(self, tmp_path: Path):
        context_dir = tmp_path / "context"
        context_dir.mkdir()

        conditions = prepare_conditions(context_dir, chip="TESTCHIP")
        names = [c.name for c in conditions]
        assert "raw_pdf" not in names


class TestBuildRagCondition:
    """Tests for _build_rag_condition_from_engine()."""

    def test_builds_condition_from_search_engine(self):
        from hwcc.bench.runner import _build_rag_condition_from_engine
        from hwcc.bench.types import BenchQuestion
        from hwcc.types import Chunk, ChunkMetadata, SearchResult

        question = BenchQuestion(
            id="usart2_apb_bus",
            category="clock_config",
            peripheral="USART2",
            register="",
            field_name="",
            question="What APB bus is USART2 connected to?",
            answer="APB1",
            answer_format="text",
        )

        class MockSearchEngine:
            def search(
                self, query: str, k: int = 5, chip: str = "", **kwargs: str
            ) -> tuple[list[SearchResult], float]:
                meta = ChunkMetadata(doc_id="test", doc_type="reference_manual")
                c1 = Chunk(
                    chunk_id="c1",
                    content="USART2 is on APB1 bus",
                    token_count=6,
                    metadata=meta,
                )
                c2 = Chunk(
                    chunk_id="c2",
                    content="APB1 runs at 42 MHz",
                    token_count=5,
                    metadata=meta,
                )
                return [
                    SearchResult(chunk=c1, score=0.9),
                    SearchResult(chunk=c2, score=0.8),
                ], 0.01

        condition = _build_rag_condition_from_engine(question, MockSearchEngine(), "TESTCHIP")  # type: ignore[arg-type]
        assert condition.name == "hwcc_rag"
        assert "USART2 is on APB1 bus" in condition.system_prompt
        assert "APB1 runs at 42 MHz" in condition.system_prompt

    def test_rag_respects_char_budget(self):
        from hwcc.bench.runner import _build_rag_condition_from_engine
        from hwcc.bench.types import BenchQuestion
        from hwcc.types import Chunk, ChunkMetadata, SearchResult

        question = BenchQuestion(
            id="test_q",
            category="clock_config",
            peripheral="SPI1",
            register="",
            field_name="",
            question="Test?",
            answer="test",
            answer_format="text",
        )

        class MockSearchEngine:
            def search(
                self, query: str, k: int = 5, chip: str = "", **kwargs: str
            ) -> tuple[list[SearchResult], float]:
                meta = ChunkMetadata(doc_id="test", doc_type="reference_manual")
                c1 = Chunk(
                    chunk_id="c1",
                    content="A" * 20_000,
                    token_count=5000,
                    metadata=meta,
                )
                c2 = Chunk(
                    chunk_id="c2",
                    content="B" * 20_000,
                    token_count=5000,
                    metadata=meta,
                )
                return [
                    SearchResult(chunk=c1, score=0.9),
                    SearchResult(chunk=c2, score=0.8),
                ], 0.01

        condition = _build_rag_condition_from_engine(
            question, MockSearchEngine(), "TESTCHIP", max_chars=32_000  # type: ignore[arg-type]
        )
        # Only first chunk should fit
        assert "A" * 20_000 in condition.system_prompt
        assert "B" * 20_000 not in condition.system_prompt


class TestRunBenchmarkWithRag:
    """Tests for run_benchmark() with hwcc_rag condition using search_engine."""

    def test_rag_condition_uses_search_engine(self):
        """When hwcc_rag condition is present and search_engine provided,
        each question gets per-question RAG context."""
        from hwcc.types import Chunk, ChunkMetadata, SearchResult

        dataset = _make_dataset()
        provider = _MockProvider(answer="0x40013000")
        conditions = [
            BenchCondition("hwcc_rag", "", "RAG condition placeholder"),
        ]

        class MockSearchEngine:
            def __init__(self):
                self.queries: list[str] = []

            def search(
                self, query: str, k: int = 5, chip: str = "", **kwargs: str
            ) -> tuple[list[SearchResult], float]:
                self.queries.append(query)
                meta = ChunkMetadata(doc_id="test", doc_type="svd")
                chunk = Chunk(
                    chunk_id="c1",
                    content=f"Context for: {query}",
                    token_count=10,
                    metadata=meta,
                )
                return [SearchResult(chunk=chunk, score=0.9)], 0.01

        engine = MockSearchEngine()
        runs = run_benchmark(
            dataset,
            provider,
            conditions,
            delay_seconds=0,
            search_engine=engine,
        )

        assert len(runs) == 1
        assert runs[0].condition == "hwcc_rag"
        # Search should have been called once per question
        assert len(engine.queries) == 2
        assert engine.queries[0] == "What is the base address of SPI1?"
        assert engine.queries[1] == "What is the offset of SPI1_CR1?"

    def test_rag_condition_without_engine_skipped(self):
        """hwcc_rag condition without search_engine is skipped."""
        dataset = _make_dataset()
        provider = _MockProvider(answer="0x40013000")
        conditions = [
            BenchCondition("no_context", "prompt", "No context"),
            BenchCondition("hwcc_rag", "", "RAG placeholder"),
        ]

        runs = run_benchmark(
            dataset,
            provider,
            conditions,
            delay_seconds=0,
        )

        # Only no_context should run, hwcc_rag skipped
        assert len(runs) == 1
        assert runs[0].condition == "no_context"

    def test_rag_top_k_passed_to_search(self):
        """rag_top_k parameter controls k in search calls."""
        from hwcc.types import Chunk, ChunkMetadata, SearchResult

        dataset = _make_dataset(
            questions=(
                BenchQuestion(
                    id="q1",
                    category="base_address",
                    peripheral="SPI1",
                    register="",
                    field_name="",
                    question="Test?",
                    answer="0x40013000",
                    answer_format="hex",
                ),
            )
        )
        provider = _MockProvider(answer="0x40013000")
        conditions = [
            BenchCondition("hwcc_rag", "", "RAG placeholder"),
        ]

        class MockSearchEngine:
            def __init__(self):
                self.k_values: list[int] = []

            def search(
                self, query: str, k: int = 5, chip: str = "", **kwargs: str
            ) -> tuple[list[SearchResult], float]:
                self.k_values.append(k)
                meta = ChunkMetadata(doc_id="test", doc_type="svd")
                chunk = Chunk(
                    chunk_id="c1",
                    content="context",
                    token_count=10,
                    metadata=meta,
                )
                return [SearchResult(chunk=chunk, score=0.9)], 0.01

        engine = MockSearchEngine()
        run_benchmark(
            dataset,
            provider,
            conditions,
            delay_seconds=0,
            search_engine=engine,
            rag_top_k=10,
        )

        assert engine.k_values == [10]


class TestRunBenchmarkMultiRun:
    """Tests for run_benchmark() with --runs N support."""

    def test_single_run_default(self):
        """Default num_runs=1 produces same result as before."""
        dataset = _make_dataset()
        provider = _MockProvider(answer="0x40013000")
        conditions = [
            BenchCondition("no_context", "prompt", "Test"),
        ]

        runs = run_benchmark(
            dataset,
            provider,
            conditions,
            delay_seconds=0,
            num_runs=1,
        )

        assert len(runs) == 1

    def test_multiple_runs(self):
        """num_runs=3 produces 3 runs per condition."""
        dataset = _make_dataset()
        provider = _MockProvider(answer="0x40013000")
        conditions = [
            BenchCondition("no_context", "prompt", "Test"),
        ]

        runs = run_benchmark(
            dataset,
            provider,
            conditions,
            delay_seconds=0,
            num_runs=3,
        )

        assert len(runs) == 3
        for run in runs:
            assert run.condition == "no_context"

    def test_multiple_conditions_multiple_runs(self):
        """2 conditions x 3 runs = 6 total runs."""
        dataset = _make_dataset()
        provider = _MockProvider(answer="0x40013000")
        conditions = [
            BenchCondition("no_context", "prompt1", "No ctx"),
            BenchCondition("hwcc_full", "prompt2", "Full ctx"),
        ]

        runs = run_benchmark(
            dataset,
            provider,
            conditions,
            delay_seconds=0,
            num_runs=3,
        )

        assert len(runs) == 6
        no_ctx_runs = [r for r in runs if r.condition == "no_context"]
        full_runs = [r for r in runs if r.condition == "hwcc_full"]
        assert len(no_ctx_runs) == 3
        assert len(full_runs) == 3

    def test_provider_called_correct_times(self):
        """With 2 questions, 1 condition, 3 runs → 6 queries."""
        dataset = _make_dataset()
        provider = _MockProvider(answer="0x40013000")
        conditions = [
            BenchCondition("no_context", "prompt", "Test"),
        ]

        run_benchmark(
            dataset,
            provider,
            conditions,
            delay_seconds=0,
            num_runs=3,
        )

        assert provider._call_count == 6  # 2 questions x 3 runs
