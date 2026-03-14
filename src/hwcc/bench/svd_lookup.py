"""SVD lookup — direct answer extraction from parsed SVD data (no LLM)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hwcc.bench.types import BenchQuestion

__all__ = ["SVD_CATEGORIES", "SvdLookupResult", "lookup_svd_answer"]

SVD_CATEGORIES = frozenset({
    "base_address",
    "register_offset",
    "bit_field",
    "reset_value",
    "access_type",
})

# Maps cmsis_svd SVDAccessType enum names to standard access codes
_ACCESS_MAP = {
    "READ_ONLY": "RO",
    "WRITE_ONLY": "WO",
    "READ_WRITE": "RW",
    "WRITE_ONCE": "W1",
    "READ_WRITE_ONCE": "RW1",
}


@dataclass(frozen=True)
class SvdLookupResult:
    """Result of an SVD lookup for a single benchmark question."""

    answer: str  # extracted answer string (e.g. "0x40013000")
    answerable: bool  # True if question category is SVD-answerable
    peripheral: str  # peripheral name matched (empty if not found)
    latency_ms: float  # lookup time


def lookup_svd_answer(
    question: BenchQuestion,
    device: object,
) -> SvdLookupResult:
    """Look up the answer to a bench question directly from SVD data.

    Args:
        question: The benchmark question with structured metadata.
        device: Parsed SVDDevice from cmsis_svd.

    Returns:
        SvdLookupResult with the answer or unanswerable status.
    """
    start = time.perf_counter()

    if question.category not in SVD_CATEGORIES:
        elapsed = (time.perf_counter() - start) * 1000
        return SvdLookupResult(
            answer="", answerable=False, peripheral="", latency_ms=elapsed
        )

    # Find peripheral
    periph = _find_peripheral(device, question.peripheral)
    if periph is None:
        return _unanswerable(start)

    periph_name: str = getattr(periph, "name", "") or ""

    # base_address only needs peripheral
    if question.category == "base_address":
        base_addr = getattr(periph, "base_address", None)
        if base_addr is not None:
            return _answerable(f"0x{base_addr:08X}", periph_name, start)
        return _unanswerable(start, periph_name)

    # All other SVD categories need a register
    reg = _find_register(periph, question.register)
    if reg is None:
        return _unanswerable(start, periph_name)

    if question.category == "register_offset":
        offset = getattr(reg, "address_offset", None)
        if offset is not None:
            return _answerable(f"0x{offset:04X}", periph_name, start)
        return _unanswerable(start, periph_name)

    if question.category == "reset_value":
        reset_val = getattr(reg, "reset_value", None)
        if reset_val is not None:
            return _answerable(f"0x{reset_val:08X}", periph_name, start)
        return _unanswerable(start, periph_name)

    if question.category == "access_type":
        access = getattr(reg, "access", None)
        if access is not None:
            access_name: str = getattr(access, "name", str(access))
            access_code = _ACCESS_MAP.get(access_name, "")
            if access_code:
                return _answerable(access_code, periph_name, start)
        return _unanswerable(start, periph_name)

    if question.category == "bit_field":
        field = _find_field(reg, question.field_name)
        bit_offset: int | None = getattr(field, "bit_offset", None) if field else None
        bit_width: int | None = getattr(field, "bit_width", None) if field else None
        if field is not None and bit_offset is not None and bit_width is not None:
            msb = bit_offset + bit_width - 1
            answer = f"[{msb}]" if bit_width == 1 else f"[{msb}:{bit_offset}]"
            return _answerable(answer, periph_name, start)
        return _unanswerable(start, periph_name)

    return _unanswerable(start)


def _answerable(answer: str, peripheral: str, start: float) -> SvdLookupResult:
    """Build an answerable result."""
    return SvdLookupResult(
        answer=answer,
        answerable=True,
        peripheral=peripheral,
        latency_ms=(time.perf_counter() - start) * 1000,
    )


def _unanswerable(start: float, peripheral: str = "") -> SvdLookupResult:
    """Build an unanswerable result."""
    return SvdLookupResult(
        answer="",
        answerable=False,
        peripheral=peripheral,
        latency_ms=(time.perf_counter() - start) * 1000,
    )


def _find_peripheral(device: object, name: str) -> object | None:
    """Find peripheral by case-insensitive exact match, then prefix match."""
    peripherals: list[object] = getattr(device, "peripherals", None) or []
    if not peripherals:
        return None

    name_upper = name.upper()

    # 1. Exact match (case-insensitive)
    for p in peripherals:
        p_name: str = getattr(p, "name", "") or ""
        if p_name.upper() == name_upper:
            return p

    # 2. Prefix match: question "SPI1" matches SVD "SPI1_I2S1ext"
    for p in peripherals:
        p_name = getattr(p, "name", "") or ""
        if p_name.upper().startswith(name_upper):
            return p

    return None


def _find_register(peripheral: object, name: str) -> object | None:
    """Find register by case-insensitive exact match."""
    registers: list[object] = getattr(peripheral, "registers", None) or []
    if not registers:
        return None

    name_upper = name.upper()
    for r in registers:
        r_name: str = getattr(r, "name", "") or ""
        if r_name.upper() == name_upper:
            return r

    return None


def _find_field(register: object, name: str) -> object | None:
    """Find field by case-insensitive exact match."""
    fields: list[object] = getattr(register, "fields", None) or []
    if not fields:
        return None

    name_upper = name.upper()
    for f in fields:
        f_name: str = getattr(f, "name", "") or ""
        if f_name.upper() == name_upper:
            return f

    return None
