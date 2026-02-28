"""Context compilation — generates output files from indexed documents."""

from hwcc.compile.base import BaseCompiler
from hwcc.compile.context import (
    CompileContext,
    DocumentSummary,
    ErrataSummary,
    PeripheralSummary,
    TargetInfo,
)
from hwcc.compile.hot_context import HotContextCompiler
from hwcc.compile.output import OutputCompiler
from hwcc.compile.peripheral import PeripheralContextCompiler
from hwcc.compile.templates import TARGET_REGISTRY, TemplateEngine

__all__ = [
    "TARGET_REGISTRY",
    "BaseCompiler",
    "CompileContext",
    "DocumentSummary",
    "ErrataSummary",
    "HotContextCompiler",
    "OutputCompiler",
    "PeripheralContextCompiler",
    "PeripheralSummary",
    "TargetInfo",
    "TemplateEngine",
]
