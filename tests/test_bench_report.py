"""Tests for hwcc.bench.report — report generation and serialization."""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

if TYPE_CHECKING:
    from pathlib import Path

from hwcc.bench.report import (
    _estimate_cost,
    generate_report,
    generate_report_markdown,
    load_report,
    print_report,
    save_report,
)
from hwcc.bench.types import BenchDataset, BenchQuestion, BenchResponse, BenchRun
from hwcc.exceptions import BenchmarkError


def _make_responses(correct_count: int, total: int) -> tuple[BenchResponse, ...]:
    """Helper to create test responses."""
    responses = []
    for i in range(total):
        is_correct = i < correct_count
        responses.append(
            BenchResponse(
                question_id=f"q{i}_base_address" if i % 2 == 0 else f"q{i}_offset",
                raw_response="0x40013000" if is_correct else "I don't know",
                extracted_answer="0x40013000" if is_correct else "",
                correct=is_correct,
                score=1.0 if is_correct else 0.0,
                latency_ms=100.0 + i * 10,
            )
        )
    return tuple(responses)


def _make_run(
    condition: str,
    correct_count: int,
    total: int = 10,
) -> BenchRun:
    """Helper to create a test run."""
    return BenchRun(
        dataset_name="TESTCHIP_RegisterKnowledge",
        condition=condition,
        model="test-model",
        provider="test",
        temperature=0.0,
        responses=_make_responses(correct_count, total),
        started="2026-03-02T00:00:00+00:00",
        completed="2026-03-02T00:01:00+00:00",
        total_tokens=1000,
    )


class TestGenerateReport:
    """Tests for generate_report()."""

    def test_empty_runs_returns_empty_report(self):
        report = generate_report([], chip="TEST")
        assert report.chip == "TEST"
        assert len(report.runs) == 0
        assert len(report.metrics) == 0

    def test_single_condition(self):
        runs = [_make_run("no_context", correct_count=3, total=10)]
        report = generate_report(runs, chip="TESTCHIP")

        assert report.chip == "TESTCHIP"
        assert len(report.runs) == 1
        assert "no_context" in report.metrics
        assert report.metrics["no_context"].accuracy == 0.3

    def test_two_conditions_compute_comparison(self):
        runs = [
            _make_run("no_context", correct_count=3, total=10),
            _make_run("hwcc_full", correct_count=9, total=10),
        ]
        report = generate_report(runs, chip="TESTCHIP")

        assert len(report.metrics) == 2
        assert report.metrics["no_context"].accuracy == 0.3
        assert report.metrics["hwcc_full"].accuracy == 0.9

        assert report.comparison["accuracy_delta"] == pytest.approx(0.6)
        assert report.comparison["hallucination_reduction"] == pytest.approx(0.6)

    def test_comparison_picks_best_hwcc_condition(self):
        runs = [
            _make_run("no_context", correct_count=3, total=10),
            _make_run("hwcc_hot", correct_count=5, total=10),
            _make_run("hwcc_full", correct_count=9, total=10),
        ]
        report = generate_report(runs, chip="TESTCHIP")

        # Should compare against hwcc_full (best accuracy)
        assert report.comparison["best_accuracy"] == 0.9

    def test_multi_run_same_condition_aggregates_metrics(self):
        """Multiple runs with same condition should pool responses, not overwrite."""
        runs = [
            _make_run("no_context", correct_count=3, total=10),
            _make_run("no_context", correct_count=7, total=10),
        ]
        report = generate_report(runs, chip="TEST")

        # Should have ONE metrics entry (not two), pooling 20 responses
        assert len(report.metrics) == 1
        m = report.metrics["no_context"]
        assert m.total == 20  # pooled: 10 + 10
        assert m.correct == 10  # pooled: 3 + 7
        assert m.accuracy == pytest.approx(0.5)

    def test_multi_run_preserves_all_runs(self):
        """All BenchRun objects should be preserved even when conditions repeat."""
        runs = [
            _make_run("no_context", correct_count=3, total=10),
            _make_run("no_context", correct_count=7, total=10),
        ]
        report = generate_report(runs, chip="TEST")
        assert len(report.runs) == 2


class TestPrintReport:
    """Tests for print_report() — verify output content."""

    def _capture_output(self, report) -> str:
        """Print report to a StringIO and return the text."""
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=120)
        print_report(report, console=console)
        return buf.getvalue()

    def test_print_empty_report(self):
        report = generate_report([], chip="TEST")
        output = self._capture_output(report)
        assert "No benchmark results" in output

    def test_print_single_condition_shows_chip(self):
        runs = [_make_run("no_context", correct_count=5, total=10)]
        report = generate_report(runs, chip="TESTCHIP")
        output = self._capture_output(report)
        assert "TESTCHIP" in output
        assert "no_context" in output

    def test_print_single_condition_shows_accuracy(self):
        runs = [_make_run("no_context", correct_count=5, total=10)]
        report = generate_report(runs, chip="TESTCHIP")
        output = self._capture_output(report)
        assert "50.0%" in output

    def test_print_shows_model_name(self):
        runs = [_make_run("no_context", correct_count=5, total=10)]
        report = generate_report(runs, chip="TESTCHIP")
        output = self._capture_output(report)
        assert "test-model" in output

    def test_print_with_comparison_shows_delta(self):
        runs = [
            _make_run("no_context", correct_count=3, total=10),
            _make_run("hwcc_full", correct_count=9, total=10),
        ]
        report = generate_report(runs, chip="TESTCHIP")
        output = self._capture_output(report)
        assert "no_context" in output
        assert "hwcc_full" in output
        assert "Impact Summary" in output
        assert "30.0%" in output  # baseline accuracy
        assert "90.0%" in output  # best accuracy


class TestSaveLoadReport:
    """Tests for report JSON serialization."""

    def test_round_trip_preserves_data(self, tmp_path: Path):
        runs = [
            _make_run("no_context", correct_count=3, total=10),
            _make_run("hwcc_full", correct_count=9, total=10),
        ]
        report = generate_report(runs, chip="TESTCHIP")

        json_path = tmp_path / "report.json"
        save_report(report, json_path)
        loaded = load_report(json_path)

        assert loaded.chip == report.chip
        assert loaded.dataset_name == report.dataset_name
        assert len(loaded.runs) == len(report.runs)
        assert len(loaded.metrics) == len(report.metrics)

    def test_round_trip_preserves_metrics(self, tmp_path: Path):
        runs = [_make_run("no_context", correct_count=5, total=10)]
        report = generate_report(runs, chip="TEST")

        json_path = tmp_path / "report.json"
        save_report(report, json_path)
        loaded = load_report(json_path)

        orig_m = report.metrics["no_context"]
        loaded_m = loaded.metrics["no_context"]
        assert loaded_m.total == orig_m.total
        assert loaded_m.correct == orig_m.correct
        assert loaded_m.accuracy == pytest.approx(orig_m.accuracy)

    def test_round_trip_preserves_responses(self, tmp_path: Path):
        runs = [_make_run("no_context", correct_count=2, total=3)]
        report = generate_report(runs, chip="TEST")

        json_path = tmp_path / "report.json"
        save_report(report, json_path)
        loaded = load_report(json_path)

        orig_responses = report.runs[0].responses
        loaded_responses = loaded.runs[0].responses
        assert len(loaded_responses) == len(orig_responses)
        for orig, loaded_r in zip(orig_responses, loaded_responses, strict=True):
            assert loaded_r.question_id == orig.question_id
            assert loaded_r.correct == orig.correct
            assert loaded_r.score == orig.score

    def test_load_nonexistent_raises_error(self, tmp_path: Path):
        with pytest.raises(BenchmarkError, match="not found"):
            load_report(tmp_path / "nonexistent.json")

    def test_load_invalid_json_raises_error(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        with pytest.raises(BenchmarkError, match="Failed to load"):
            load_report(bad)

    def test_round_trip_preserves_partial_score(self, tmp_path: Path):
        responses = (
            BenchResponse(
                "q0_base_address",
                "0x40013000",
                "0x40013000",
                True,
                1.0,
                100.0,
                1.0,
                0.9,
            ),
            BenchResponse(
                "q1_offset",
                "wrong",
                "",
                False,
                0.0,
                110.0,
                0.5,
                0.3,
            ),
        )
        run = BenchRun(
            dataset_name="TEST_RK",
            condition="no_context",
            model="test",
            provider="test",
            temperature=0.0,
            responses=responses,
            started="2026-03-02T00:00:00+00:00",
            completed="2026-03-02T00:01:00+00:00",
            total_tokens=100,
        )
        report = generate_report([run], chip="TEST")
        json_path = tmp_path / "report.json"
        save_report(report, json_path)
        loaded = load_report(json_path)

        m = loaded.metrics["no_context"]
        assert m.avg_partial_score == pytest.approx(0.75)
        assert m.expected_calibration_error is not None

    def test_round_trip_preserves_confidence_none(self, tmp_path: Path):
        """Old-style responses without confidence still round-trip."""
        runs = [_make_run("no_context", correct_count=3, total=5)]
        report = generate_report(runs, chip="TEST")
        json_path = tmp_path / "report.json"
        save_report(report, json_path)
        loaded = load_report(json_path)

        m = loaded.metrics["no_context"]
        assert m.expected_calibration_error is None


class TestPrintReportCalibration:
    """Tests for print_report() with calibration data."""

    def test_print_with_confidence_data(self):
        responses = (
            BenchResponse(
                "q0_base_address",
                "0x40013000",
                "0x40013000",
                True,
                1.0,
                100.0,
                1.0,
                0.9,
            ),
            BenchResponse(
                "q1_offset",
                "wrong",
                "",
                False,
                0.0,
                110.0,
                0.5,
                0.8,
            ),
        )
        run = BenchRun(
            dataset_name="TEST_RK",
            condition="no_context",
            model="test",
            provider="test",
            temperature=0.0,
            responses=responses,
            started="2026-03-02T00:00:00+00:00",
            completed="2026-03-02T00:01:00+00:00",
            total_tokens=100,
        )
        report = generate_report([run], chip="TEST")
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=120)
        print_report(report, console=console)
        output = buf.getvalue()
        assert "Confidence Calibration" in output
        assert "ECE" in output


class TestMarkdownReport:
    """Tests for markdown report output."""

    def test_markdown_contains_summary_table(self):
        from hwcc.bench.report import generate_report_markdown

        runs = [_make_run("no_context", correct_count=5, total=10)]
        report = generate_report(runs, chip="TESTCHIP")
        md = generate_report_markdown(report)
        assert "| Condition" in md
        assert "no_context" in md
        assert "TESTCHIP" in md

    def test_markdown_contains_accuracy(self):
        from hwcc.bench.report import generate_report_markdown

        runs = [_make_run("no_context", correct_count=5, total=10)]
        report = generate_report(runs, chip="TESTCHIP")
        md = generate_report_markdown(report)
        assert "50.0%" in md

    def test_markdown_contains_ci(self):
        """Report markdown should include confidence interval values."""
        from hwcc.bench.report import generate_report_markdown

        runs = [_make_run("no_context", correct_count=5, total=10)]
        report = generate_report(runs, chip="TESTCHIP")
        md = generate_report_markdown(report)
        assert "95% CI" in md

    def test_markdown_contains_per_question_detail(self):
        from hwcc.bench.report import generate_report_markdown

        runs = [_make_run("no_context", correct_count=2, total=3)]
        report = generate_report(runs, chip="TEST")
        md = generate_report_markdown(report)
        assert "Per-Question Detail" in md
        assert "q0_base_address" in md

    def test_markdown_contains_comparison(self):
        from hwcc.bench.report import generate_report_markdown

        runs = [
            _make_run("no_context", correct_count=3, total=10),
            _make_run("hwcc_full", correct_count=9, total=10),
        ]
        report = generate_report(runs, chip="TESTCHIP")
        md = generate_report_markdown(report)
        assert "Impact" in md

    def test_markdown_contains_metadata(self):
        from hwcc.bench.report import generate_report_markdown

        runs = [_make_run("no_context", correct_count=5, total=10)]
        report = generate_report(runs, chip="TESTCHIP")
        md = generate_report_markdown(report)
        assert "test-model" in md
        assert "TESTCHIP" in md

    def test_markdown_empty_report(self):
        from hwcc.bench.report import generate_report_markdown

        report = generate_report([], chip="TEST")
        md = generate_report_markdown(report)
        assert "No benchmark results" in md


class TestPrintReportCI:
    """Tests for CI display in Rich print_report."""

    def test_print_shows_ci(self):
        runs = [_make_run("no_context", correct_count=5, total=10)]
        report = generate_report(runs, chip="TESTCHIP")
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=120)
        print_report(report, console=console)
        output = buf.getvalue()
        assert "CI" in output


class TestReportPerQuestionDetail:
    """Tests for per-question detail in report JSON."""

    def test_per_question_in_json_round_trip(self, tmp_path: Path):
        """Per-question details survive JSON round-trip."""
        runs = [_make_run("no_context", correct_count=2, total=3)]
        report = generate_report(runs, chip="TEST")
        json_path = tmp_path / "report.json"
        save_report(report, json_path)
        loaded = load_report(json_path)

        assert len(loaded.runs[0].responses) == 3
        assert loaded.runs[0].responses[0].question_id == "q0_base_address"


def _make_dataset(questions: list[BenchQuestion] | None = None) -> BenchDataset:
    """Helper to create a test dataset with difficulty data."""
    if questions is None:
        questions = [
            BenchQuestion(
                id=f"q{i}_base_address" if i % 2 == 0 else f"q{i}_offset",
                category="base_address" if i % 2 == 0 else "register_offset",
                peripheral="SPI1",
                register="" if i % 2 == 0 else "CR1",
                field_name="",
                question=f"Question {i}",
                answer="0x40013000",
                answer_format="hex",
                difficulty=["easy", "medium", "hard"][i % 3],
            )
            for i in range(10)
        ]
    return BenchDataset(
        name="TEST_RK",
        chip="TESTCHIP",
        source_svd="test.svd",
        question_count=len(questions),
        questions=tuple(questions),
        created="2026-03-02T00:00:00+00:00",
        categories=("base_address", "register_offset"),
    )


class TestPerDifficulty:
    """Tests for per-difficulty metrics in report."""

    def test_generate_report_with_dataset_populates_difficulty(self):
        dataset = _make_dataset()
        runs = [_make_run("no_context", correct_count=5, total=10)]
        report = generate_report(runs, chip="TEST", dataset=dataset)

        m = report.metrics["no_context"]
        assert len(m.by_difficulty) > 0
        assert all(d in ("easy", "medium", "hard") for d in m.by_difficulty)

    def test_generate_report_without_dataset_has_empty_difficulty(self):
        runs = [_make_run("no_context", correct_count=5, total=10)]
        report = generate_report(runs, chip="TEST")

        m = report.metrics["no_context"]
        assert m.by_difficulty == {}

    def test_print_report_shows_difficulty_table(self):
        dataset = _make_dataset()
        runs = [_make_run("no_context", correct_count=5, total=10)]
        report = generate_report(runs, chip="TEST", dataset=dataset)

        buf = StringIO()
        c = Console(file=buf, force_terminal=False, width=120)
        print_report(report, console=c)
        output = buf.getvalue()
        assert "Accuracy by Difficulty" in output

    def test_markdown_contains_difficulty_table(self):
        dataset = _make_dataset()
        runs = [_make_run("no_context", correct_count=5, total=10)]
        report = generate_report(runs, chip="TEST", dataset=dataset)

        md = generate_report_markdown(report)
        assert "Accuracy by Difficulty" in md

    def test_difficulty_round_trips_through_json(self, tmp_path: Path):
        dataset = _make_dataset()
        runs = [_make_run("no_context", correct_count=5, total=10)]
        report = generate_report(runs, chip="TEST", dataset=dataset)

        json_path = tmp_path / "report.json"
        save_report(report, json_path)
        loaded = load_report(json_path)

        orig_diff = report.metrics["no_context"].by_difficulty
        loaded_diff = loaded.metrics["no_context"].by_difficulty
        assert set(loaded_diff.keys()) == set(orig_diff.keys())
        for k in orig_diff:
            assert loaded_diff[k] == pytest.approx(orig_diff[k])


class TestKnowledgeGrouping:
    """Tests for Register Knowledge vs Datasheet Knowledge category grouping."""

    def test_markdown_shows_knowledge_groups(self):
        """Markdown report should show separate groups for register vs datasheet categories."""
        from hwcc.bench.report import generate_report_markdown

        # Mix of register and datasheet question IDs
        responses = (
            BenchResponse("spi1_base_address", "0x40013000", "0x40013000", True, 1.0, 100.0),
            BenchResponse("spi1_cr1_offset", "0x0000", "0x0000", True, 1.0, 100.0),
            BenchResponse("usart2_apb_bus", "APB1", "APB1", True, 1.0, 100.0),
            BenchResponse("vdd_range", "1.8V to 3.6V", "1.8V to 3.6V", True, 1.0, 100.0),
        )
        run = BenchRun(
            dataset_name="TEST_Mixed",
            condition="no_context",
            model="test",
            provider="test",
            temperature=0.0,
            responses=responses,
            started="2026-03-02T00:00:00+00:00",
            completed="2026-03-02T00:01:00+00:00",
            total_tokens=100,
        )

        # Create dataset with mixed categories for grouping
        questions = [
            BenchQuestion(
                id="spi1_base_address",
                category="base_address",
                peripheral="SPI1",
                register="",
                field_name="",
                question="Base address?",
                answer="0x40013000",
                answer_format="hex",
            ),
            BenchQuestion(
                id="spi1_cr1_offset",
                category="register_offset",
                peripheral="SPI1",
                register="CR1",
                field_name="",
                question="Offset?",
                answer="0x0000",
                answer_format="hex",
            ),
            BenchQuestion(
                id="usart2_apb_bus",
                category="clock_config",
                peripheral="USART2",
                register="",
                field_name="",
                question="APB bus?",
                answer="APB1",
                answer_format="text",
            ),
            BenchQuestion(
                id="vdd_range",
                category="electrical",
                peripheral="",
                register="",
                field_name="",
                question="VDD range?",
                answer="1.8V to 3.6V",
                answer_format="numeric_range",
            ),
        ]
        dataset = BenchDataset(
            name="TEST_Mixed",
            chip="TEST",
            source_svd="",
            question_count=4,
            questions=tuple(questions),
            created="2026-03-14T00:00:00+00:00",
            categories=("base_address", "register_offset", "clock_config", "electrical"),
        )

        report = generate_report([run], chip="TEST", dataset=dataset)
        md = generate_report_markdown(report, dataset=dataset)

        # Should group into Register Knowledge and Datasheet Knowledge
        assert "Register Knowledge" in md
        assert "Datasheet Knowledge" in md

    def test_markdown_source_ref_in_detail(self):
        """Per-question detail should show source_ref when available."""
        from hwcc.bench.report import generate_report_markdown

        responses = (BenchResponse("usart2_apb_bus", "APB1", "APB1", True, 1.0, 100.0),)
        run = BenchRun(
            dataset_name="TEST_DS",
            condition="no_context",
            model="test",
            provider="test",
            temperature=0.0,
            responses=responses,
            started="2026-03-02T00:00:00+00:00",
            completed="2026-03-02T00:01:00+00:00",
            total_tokens=100,
        )

        questions = [
            BenchQuestion(
                id="usart2_apb_bus",
                category="clock_config",
                peripheral="USART2",
                register="",
                field_name="",
                question="APB bus?",
                answer="APB1",
                answer_format="text",
                source_ref="RM0090 Table 1",
            ),
        ]
        dataset = BenchDataset(
            name="TEST_DS",
            chip="TEST",
            source_svd="",
            question_count=1,
            questions=tuple(questions),
            created="2026-03-14T00:00:00+00:00",
            categories=("clock_config",),
        )

        report = generate_report([run], chip="TEST", dataset=dataset)
        md = generate_report_markdown(report, dataset=dataset)
        assert "RM0090 Table 1" in md


class TestCostTracking:
    """Tests for cost estimation."""

    def test_estimate_cost_anthropic(self):
        cost = _estimate_cost("anthropic", 1_000_000)
        assert cost == pytest.approx(9.0)

    def test_estimate_cost_ollama_is_free(self):
        cost = _estimate_cost("ollama", 1_000_000)
        assert cost == 0.0

    def test_estimate_cost_unknown_provider(self):
        cost = _estimate_cost("unknown_provider", 1_000_000)
        assert cost == 0.0

    def test_estimate_cost_zero_tokens(self):
        cost = _estimate_cost("anthropic", 0)
        assert cost == 0.0

    def test_print_report_shows_cost_for_anthropic(self):
        """Cost should appear when provider has a cost rate and tokens > 0."""
        responses = (
            BenchResponse(
                "q0_base_address",
                "0x40013000",
                "0x40013000",
                True,
                1.0,
                100.0,
            ),
        )
        run = BenchRun(
            dataset_name="TEST_RK",
            condition="no_context",
            model="test",
            provider="anthropic",
            temperature=0.0,
            responses=responses,
            started="2026-03-02T00:00:00+00:00",
            completed="2026-03-02T00:01:00+00:00",
            total_tokens=100_000,
        )
        report = generate_report([run], chip="TEST")
        buf = StringIO()
        c = Console(file=buf, force_terminal=False, width=120)
        print_report(report, console=c)
        output = buf.getvalue()
        assert "Estimated cost" in output

    def test_print_report_no_cost_for_ollama(self):
        """Cost should not appear for free providers."""
        runs = [_make_run("no_context", correct_count=5, total=10)]
        # _make_run uses provider="test" which has $0 rate
        report = generate_report(runs, chip="TEST")
        buf = StringIO()
        c = Console(file=buf, force_terminal=False, width=120)
        print_report(report, console=c)
        output = buf.getvalue()
        assert "Estimated cost" not in output

    def test_markdown_shows_cost_for_anthropic(self):
        responses = (
            BenchResponse(
                "q0_base_address",
                "0x40013000",
                "0x40013000",
                True,
                1.0,
                100.0,
            ),
        )
        run = BenchRun(
            dataset_name="TEST_RK",
            condition="no_context",
            model="test",
            provider="anthropic",
            temperature=0.0,
            responses=responses,
            started="2026-03-02T00:00:00+00:00",
            completed="2026-03-02T00:01:00+00:00",
            total_tokens=100_000,
        )
        report = generate_report([run], chip="TEST")
        md = generate_report_markdown(report)
        assert "Estimated Cost" in md
