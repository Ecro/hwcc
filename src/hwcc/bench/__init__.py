"""HwBench — Hardware Context Benchmark Suite.

Quantitatively measures the impact of hwcc-compiled context on LLM accuracy
for hardware register questions. Generates Q&A datasets from SVD files,
runs benchmarks against LLM APIs, and produces scored reports.
"""

from hwcc.bench.types import (
    BenchCondition,
    BenchDataset,
    BenchMetrics,
    BenchQuestion,
    BenchReport,
    BenchResponse,
    BenchRun,
)

__all__ = [
    "BenchCondition",
    "BenchDataset",
    "BenchMetrics",
    "BenchQuestion",
    "BenchReport",
    "BenchResponse",
    "BenchRun",
]
