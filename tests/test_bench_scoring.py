"""Tests for hwcc.bench.scoring — answer extraction, normalization, and scoring."""

from __future__ import annotations

import pytest

from hwcc.bench.scoring import (
    compute_metrics,
    extract_answer,
    extract_confidence,
    normalize_access,
    normalize_bit_range,
    normalize_hex,
    score_answer,
    score_answer_partial,
)
from hwcc.bench.types import BenchResponse
from hwcc.exceptions import BenchmarkError


class TestNormalizeHex:
    """Tests for normalize_hex()."""

    def test_bare_hex_digits(self):
        assert normalize_hex("40013000") == "0x40013000"

    def test_with_0x_prefix(self):
        assert normalize_hex("0x40013000") == "0x40013000"

    def test_uppercase_prefix(self):
        assert normalize_hex("0X40013000") == "0x40013000"

    def test_leading_zeros_stripped(self):
        assert normalize_hex("0x0040013000") == "0x40013000"

    def test_short_offset_padded(self):
        assert normalize_hex("0x0000") == "0x0000"

    def test_short_value_padded(self):
        assert normalize_hex("0x8") == "0x0008"

    def test_zero_value(self):
        assert normalize_hex("0x0") == "0x0000"

    def test_full_32bit_value(self):
        assert normalize_hex("0xFFFFFFFF") == "0xFFFFFFFF"

    def test_lowercase_converted(self):
        assert normalize_hex("0x4001a000") == "0x4001A000"

    def test_whitespace_stripped(self):
        assert normalize_hex("  0x40013000  ") == "0x40013000"

    def test_two_value(self):
        # Leading zeros are stripped, padded to 4 nibbles minimum
        assert normalize_hex("0x00000002") == "0x0002"


class TestNormalizeBitRange:
    """Tests for normalize_bit_range()."""

    def test_standard_range(self):
        assert normalize_bit_range("[5:3]") == "[5:3]"

    def test_single_bit(self):
        assert normalize_bit_range("[5]") == "[5]"

    def test_bits_n_to_m(self):
        assert normalize_bit_range("bits 5-3") == "[5:3]"

    def test_bit_to_bit(self):
        assert normalize_bit_range("bit 5 to bit 3") == "[5:3]"

    def test_reversed_range(self):
        assert normalize_bit_range("bits 3-5") == "[5:3]"

    def test_bare_number(self):
        assert normalize_bit_range("5") == "[5]"

    def test_zero_bit(self):
        assert normalize_bit_range("[0]") == "[0]"

    def test_wide_range(self):
        assert normalize_bit_range("[31:0]") == "[31:0]"


class TestNormalizeAccess:
    """Tests for normalize_access()."""

    def test_ro_passthrough(self):
        assert normalize_access("RO") == "RO"

    def test_rw_passthrough(self):
        assert normalize_access("RW") == "RW"

    def test_wo_passthrough(self):
        assert normalize_access("WO") == "WO"

    def test_read_only(self):
        assert normalize_access("read-only") == "RO"

    def test_read_write(self):
        assert normalize_access("read-write") == "RW"

    def test_read_write_slash(self):
        assert normalize_access("read/write") == "RW"

    def test_write_only(self):
        assert normalize_access("write-only") == "WO"

    def test_write_once(self):
        assert normalize_access("write-once") == "W1"

    def test_w1(self):
        assert normalize_access("W1") == "W1"

    def test_case_insensitive(self):
        assert normalize_access("Read-Only") == "RO"

    def test_rw1(self):
        assert normalize_access("RW1") == "RW1"


class TestExtractAnswer:
    """Tests for extract_answer()."""

    def test_extract_hex_from_sentence(self):
        result = extract_answer("The base address is 0x40013000", "hex")
        assert result == "0x40013000"

    def test_extract_bare_hex(self):
        result = extract_answer("0x40013000", "hex")
        assert result == "0x40013000"

    def test_extract_hex_with_explanation(self):
        result = extract_answer(
            "The SPI1 base address on STM32F407 is 0x40013000.",
            "hex",
        )
        assert result == "0x40013000"

    def test_extract_bit_range_brackets(self):
        result = extract_answer("[5:3]", "bit_range")
        assert result == "[5:3]"

    def test_extract_bit_range_from_sentence(self):
        result = extract_answer("The BR field occupies bits [5:3]", "bit_range")
        assert result == "[5:3]"

    def test_extract_single_bit(self):
        result = extract_answer("[6]", "bit_range")
        assert result == "[6]"

    def test_extract_access_code(self):
        result = extract_answer("RO", "access_code")
        assert result == "RO"

    def test_extract_access_from_description(self):
        result = extract_answer("The register is read-only (RO)", "access_code")
        assert result == "RO"

    def test_extract_hex_empty_response(self):
        result = extract_answer("", "hex")
        assert result == ""

    def test_extract_hex_no_match(self):
        result = extract_answer("I don't know", "hex")
        assert result == ""


class TestScoreAnswer:
    """Tests for score_answer()."""

    def test_correct_hex(self):
        assert score_answer("0x40013000", "0x40013000", "hex") == 1.0

    def test_wrong_hex(self):
        assert score_answer("0x40013001", "0x40013000", "hex") == 0.0

    def test_hex_normalization_match(self):
        # Both normalize to the same value
        assert score_answer("40013000", "0x40013000", "hex") == 1.0

    def test_correct_bit_range(self):
        assert score_answer("[5:3]", "[5:3]", "bit_range") == 1.0

    def test_wrong_bit_range(self):
        assert score_answer("[6:4]", "[5:3]", "bit_range") == 0.0

    def test_correct_access(self):
        assert score_answer("RO", "RO", "access_code") == 1.0

    def test_access_normalization_match(self):
        assert score_answer("read-only", "RO", "access_code") == 1.0

    def test_wrong_access(self):
        assert score_answer("RW", "RO", "access_code") == 0.0

    def test_empty_extracted_scores_zero(self):
        assert score_answer("", "0x40013000", "hex") == 0.0


class TestComputeMetrics:
    """Tests for compute_metrics()."""

    def test_all_correct(self):
        responses = [
            BenchResponse("q1_base_address", "0x40013000", "0x40013000", True, 1.0, 100.0),
            BenchResponse("q2_offset", "0x0008", "0x0008", True, 1.0, 120.0),
        ]
        metrics = compute_metrics(responses)
        assert metrics.total == 2
        assert metrics.correct == 2
        assert metrics.accuracy == 1.0
        assert metrics.hallucination_rate == 0.0

    def test_mixed_results(self):
        responses = [
            BenchResponse("q1_base_address", "0x40013000", "0x40013000", True, 1.0, 100.0),
            BenchResponse("q2_offset", "wrong", "wrong", False, 0.0, 120.0),
            BenchResponse("q3_base_address", "0x40011000", "0x40011000", True, 1.0, 110.0),
        ]
        metrics = compute_metrics(responses)
        assert metrics.total == 3
        assert metrics.correct == 2
        assert abs(metrics.accuracy - 2 / 3) < 0.001
        assert abs(metrics.hallucination_rate - 1 / 3) < 0.001

    def test_all_wrong(self):
        responses = [
            BenchResponse("q1_base_address", "wrong", "", False, 0.0, 100.0),
            BenchResponse("q2_offset", "wrong", "", False, 0.0, 120.0),
        ]
        metrics = compute_metrics(responses)
        assert metrics.accuracy == 0.0
        assert metrics.hallucination_rate == 1.0

    def test_empty_responses(self):
        metrics = compute_metrics([])
        assert metrics.total == 0
        assert metrics.accuracy == 0.0

    def test_per_category_accuracy(self):
        responses = [
            BenchResponse("spi1_base_address", "...", "0x40013000", True, 1.0, 100.0),
            BenchResponse("usart1_base_address", "...", "0x40011000", True, 1.0, 100.0),
            BenchResponse("spi1_cr1_offset", "...", "0x0000", True, 1.0, 100.0),
            BenchResponse("spi1_sr_offset", "...", "wrong", False, 0.0, 100.0),
        ]
        metrics = compute_metrics(responses)
        assert metrics.by_category["base_address"] == 1.0
        assert metrics.by_category["register_offset"] == 0.5

    def test_avg_latency(self):
        responses = [
            BenchResponse("q1_base_address", "...", "...", True, 1.0, 100.0),
            BenchResponse("q2_offset", "...", "...", True, 1.0, 200.0),
        ]
        metrics = compute_metrics(responses)
        assert metrics.avg_latency_ms == 150.0


class TestScoreAnswerPartial:
    """Tests for score_answer_partial() — graded scoring."""

    # --- Hex partial credit (nibble-level match) ---

    def test_exact_hex_match_is_1(self):
        assert score_answer_partial("0x40013000", "0x40013000", "hex") == 1.0

    def test_empty_extracted_is_0(self):
        assert score_answer_partial("", "0x40013000", "hex") == 0.0

    def test_hex_one_nibble_off(self):
        # 0x40013000 vs 0x40014000 — 7/8 nibbles match
        score = score_answer_partial("0x40014000", "0x40013000", "hex")
        assert abs(score - 7 / 8) < 0.01

    def test_hex_completely_wrong(self):
        # No nibbles match
        score = score_answer_partial("0xDEADBEEF", "0x40013000", "hex")
        assert score < 0.2

    def test_hex_right_peripheral_region(self):
        # 0x40013000 vs 0x40013008 — 7/8 nibbles match
        score = score_answer_partial("0x40013008", "0x40013000", "hex")
        assert abs(score - 7 / 8) < 0.01

    def test_hex_short_values(self):
        # 0x0008 vs 0x000C — 3/4 nibbles match
        score = score_answer_partial("0x000C", "0x0008", "hex")
        assert abs(score - 3 / 4) < 0.01

    def test_hex_normalization_applied(self):
        # Both normalize to same → 1.0
        assert score_answer_partial("40013000", "0x40013000", "hex") == 1.0

    # --- Bit range partial credit (Jaccard index of bit sets) ---

    def test_exact_bit_range_match_is_1(self):
        assert score_answer_partial("[5:3]", "[5:3]", "bit_range") == 1.0

    def test_bit_range_one_bit_off(self):
        # [5:3] = {3,4,5}, [6:3] = {3,4,5,6} → intersection=3, union=4 → 0.75
        score = score_answer_partial("[6:3]", "[5:3]", "bit_range")
        assert abs(score - 3 / 4) < 0.01

    def test_bit_range_shifted(self):
        # [5:3] = {3,4,5}, [7:5] = {5,6,7} → intersection={5}, union={3,4,5,6,7} → 1/5
        score = score_answer_partial("[7:5]", "[5:3]", "bit_range")
        assert abs(score - 1 / 5) < 0.01

    def test_bit_range_no_overlap(self):
        # [1:0] = {0,1}, [5:3] = {3,4,5} → no overlap → 0.0
        assert score_answer_partial("[1:0]", "[5:3]", "bit_range") == 0.0

    def test_single_bit_exact_match(self):
        assert score_answer_partial("[6]", "[6]", "bit_range") == 1.0

    def test_single_bit_wrong(self):
        # [5] = {5}, [6] = {6} → no overlap → 0.0
        assert score_answer_partial("[5]", "[6]", "bit_range") == 0.0

    def test_bit_range_empty_extracted(self):
        assert score_answer_partial("", "[5:3]", "bit_range") == 0.0

    # --- Access code partial credit (binary — no partial credit) ---

    def test_access_exact_match_is_1(self):
        assert score_answer_partial("RO", "RO", "access_code") == 1.0

    def test_access_wrong_is_0(self):
        assert score_answer_partial("RW", "RO", "access_code") == 0.0

    def test_access_normalization_applied(self):
        assert score_answer_partial("read-only", "RO", "access_code") == 1.0


class TestExtractConfidence:
    """Tests for extract_confidence() — confidence value extraction."""

    def test_percentage_at_end(self):
        assert extract_confidence("0x40013000\nConfidence: 90%") == 0.9

    def test_confidence_colon_pattern(self):
        assert extract_confidence("Confidence: 75%") == 0.75

    def test_confident_phrase(self):
        assert extract_confidence("I am 85% confident the answer is 0x40013000") == 0.85

    def test_decimal_confidence(self):
        assert extract_confidence("Confidence: 0.95") == 0.95

    def test_no_confidence_returns_none(self):
        assert extract_confidence("0x40013000") is None

    def test_empty_string_returns_none(self):
        assert extract_confidence("") is None

    def test_100_percent(self):
        assert extract_confidence("Confidence: 100%") == 1.0

    def test_zero_percent(self):
        assert extract_confidence("Confidence: 0%") == 0.0

    def test_confidence_with_word_certain(self):
        assert extract_confidence("I'm 50% certain") == 0.5


class TestComputeMetricsPartial:
    """Tests for compute_metrics() with partial scores and confidence."""

    def test_avg_partial_score(self):
        responses = [
            BenchResponse("q1_base_address", "...", "0x40013000", True, 1.0, 100.0, 1.0),
            BenchResponse("q2_offset", "...", "wrong", False, 0.0, 100.0, 0.5),
        ]
        metrics = compute_metrics(responses)
        assert metrics.avg_partial_score == 0.75

    def test_avg_partial_score_all_zero(self):
        responses = [
            BenchResponse("q1_base_address", "...", "", False, 0.0, 100.0, 0.0),
            BenchResponse("q2_offset", "...", "", False, 0.0, 100.0, 0.0),
        ]
        metrics = compute_metrics(responses)
        assert metrics.avg_partial_score == 0.0

    def test_ece_with_confidence_data(self):
        # Perfect calibration: confidence matches accuracy
        responses = [
            BenchResponse("q1_base_address", "...", "0x40013000", True, 1.0, 100.0, 1.0, 1.0),
            BenchResponse("q2_offset", "...", "wrong", False, 0.0, 100.0, 0.0, 0.0),
        ]
        metrics = compute_metrics(responses)
        assert metrics.expected_calibration_error is not None
        assert metrics.expected_calibration_error < 0.1

    def test_ece_miscalibrated(self):
        # Overconfident: says 90% confidence but all wrong
        responses = [
            BenchResponse("q1_base_address", "...", "", False, 0.0, 100.0, 0.0, 0.9),
            BenchResponse("q2_offset", "...", "", False, 0.0, 100.0, 0.0, 0.9),
            BenchResponse("q3_bits", "...", "", False, 0.0, 100.0, 0.0, 0.9),
        ]
        metrics = compute_metrics(responses)
        assert metrics.expected_calibration_error is not None
        assert metrics.expected_calibration_error > 0.8

    def test_ece_none_when_no_confidence(self):
        responses = [
            BenchResponse("q1_base_address", "...", "0x40013000", True, 1.0, 100.0),
        ]
        metrics = compute_metrics(responses)
        assert metrics.expected_calibration_error is None

    def test_backward_compat_no_partial_fields(self):
        # Old-style construction without partial_score/confidence still works
        r = BenchResponse("q1", "raw", "ext", True, 1.0, 100.0)
        assert r.partial_score == 0.0
        assert r.confidence is None


class TestCriticalFixRegressions:
    """Regression tests for critical fixes from v1.1 review."""

    def test_bit_single_requires_bit_keyword(self):
        """Bare numbers in text must NOT match as single-bit answers."""
        assert extract_answer("register 12 holds the value", "bit_range") == ""

    def test_bit_single_with_keyword_still_works(self):
        assert extract_answer("bit 5 is the enable flag", "bit_range") == "[5]"

    def test_bare_hex_rejects_english_words(self):
        """Words like DEADBEEF/CAFEBABE must NOT match as hex addresses."""
        assert extract_answer("DEADBEEF", "hex") == ""
        assert extract_answer("CAFEBABE", "hex") == ""
        assert extract_answer("FACEFEED", "hex") == ""

    def test_bare_hex_accepts_valid_address(self):
        """Valid 8-char bare hex with digits should still match."""
        assert extract_answer("40013000", "hex") == "0x40013000"
        assert extract_answer("4001A000", "hex") == "0x4001A000"

    def test_bare_hex_rejects_short_values(self):
        """Short bare hex (< 8 chars) should not match without 0x prefix."""
        assert extract_answer("ABCD", "hex") == ""

    def test_prefixed_hex_still_works(self):
        """0x-prefixed hex is unaffected by the bare-hex fix."""
        assert extract_answer("0xDEADBEEF", "hex") == "0xDEADBEEF"
        assert extract_answer("0xCAFE", "hex") == "0xCAFE"


class TestBenchmarkErrorInHierarchy:
    """Test that BenchmarkError is in the exception hierarchy."""

    def test_benchmark_error_is_hwcc_error(self):
        from hwcc.exceptions import HwccError

        assert issubclass(BenchmarkError, HwccError)

    def test_can_raise_and_catch(self):
        with pytest.raises(BenchmarkError, match="test error"):
            raise BenchmarkError("test error")
