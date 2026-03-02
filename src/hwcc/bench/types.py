"""Benchmark data contracts — frozen dataclasses for the HwBench pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "BenchCondition",
    "BenchDataset",
    "BenchMetrics",
    "BenchQuestion",
    "BenchReport",
    "BenchResponse",
    "BenchRun",
]


@dataclass(frozen=True)
class BenchQuestion:
    """A single benchmark question with ground truth answer."""

    id: str
    category: str  # base_address | register_offset | bit_field | reset_value | access_type
    peripheral: str
    register: str  # empty for base_address questions
    field_name: str  # empty for register-level questions
    question: str
    answer: str  # ground truth value
    answer_format: str  # hex | bit_range | access_code


@dataclass(frozen=True)
class BenchDataset:
    """Collection of benchmark questions from a single SVD source."""

    name: str
    chip: str
    source_svd: str
    question_count: int
    questions: tuple[BenchQuestion, ...]
    created: str  # ISO timestamp
    categories: tuple[str, ...]  # unique categories present


@dataclass(frozen=True)
class BenchResponse:
    """Result of asking one question to one LLM."""

    question_id: str
    raw_response: str
    extracted_answer: str
    correct: bool
    score: float  # 0.0 or 1.0 (exact match)
    latency_ms: float
    partial_score: float = 0.0  # 0.0-1.0 graded (nibble match, bit overlap)
    confidence: float | None = None  # 0.0-1.0 if model stated confidence


@dataclass(frozen=True)
class BenchCondition:
    """A test condition (context variation)."""

    name: str  # no_context | hwcc_hot | hwcc_peripheral | hwcc_full
    system_prompt: str
    description: str


@dataclass(frozen=True)
class BenchRun:
    """Complete benchmark run results for one condition."""

    dataset_name: str
    condition: str
    model: str
    provider: str
    temperature: float
    responses: tuple[BenchResponse, ...]
    started: str  # ISO timestamp
    completed: str
    total_tokens: int


@dataclass(frozen=True)
class BenchMetrics:
    """Aggregated metrics for a benchmark run."""

    total: int
    correct: int
    accuracy: float
    hallucination_rate: float
    by_category: dict[str, float] = field(default_factory=dict)
    avg_latency_ms: float = 0.0
    total_tokens: int = 0
    avg_partial_score: float = 0.0  # mean of all partial scores
    expected_calibration_error: float | None = None  # ECE if confidence data available


@dataclass(frozen=True)
class BenchReport:
    """Complete benchmark report across all conditions."""

    chip: str
    dataset_name: str
    runs: tuple[BenchRun, ...]
    metrics: dict[str, BenchMetrics] = field(default_factory=dict)
    comparison: dict[str, float] = field(default_factory=dict)
