"""Scoring engine — extracts and scores answers from LLM responses."""

from __future__ import annotations

import math
import re

from hwcc.bench.types import BenchMetrics, BenchResponse

__all__ = [
    "compute_metrics",
    "compute_metrics_with_difficulty",
    "extract_answer",
    "extract_confidence",
    "mcnemar_test",
    "normalize_access",
    "normalize_bit_range",
    "normalize_hex",
    "normalize_numeric",
    "score_answer",
    "score_answer_partial",
    "wilson_ci",
]

# Regex patterns for answer extraction
_HEX_RE = re.compile(r"0[xX][0-9A-Fa-f]+")
_BIT_RANGE_RE = re.compile(r"\[(\d+)(?::(\d+))?\]")
_BIT_RANGE_ALT_RE = re.compile(
    r"(?:bits?\s+)?(\d+)\s*(?:[-\u2013\u2014]|to\s*(?:bit\s*)?)\s*(\d+)",
    re.IGNORECASE,
)
_BIT_SINGLE_RE = re.compile(r"\bbit\s+(\d{1,2})\b", re.IGNORECASE)
_ACCESS_RE = re.compile(
    r"\b(RO|RW|WO|W1|RW1|read[- ]?only|write[- ]?only|read[- ]?write|"
    r"read/write|write[- ]?once|read[- ]?write[- ]?once)\b",
    re.IGNORECASE,
)
_CONFIDENCE_PCT_RE = re.compile(
    r"(?:confidence|confident|certain)\s*[:=]?\s*(\d{1,3})%",
    re.IGNORECASE,
)
_CONFIDENCE_PHRASE_RE = re.compile(
    r"(\d{1,3})%\s*(?:confidence|confident|certain)",
    re.IGNORECASE,
)
_CONFIDENCE_DECIMAL_RE = re.compile(
    r"(?:confidence|confident|certain)\s*[:=]\s*(0\.\d+|1\.0|0|1)\b",
    re.IGNORECASE,
)

# Numeric extraction: number + optional unit
_NUMERIC_RE = re.compile(
    r"(-?\d+\.?\d*)\s*(MHz|mhz|Mhz|kHz|KHz|GHz|Hz|hz|"
    r"mV|mv|V|v|volt|volts|"
    r"uA|ua|µA|mA|ma|A|amp|amps|"
    r"ns|us|µs|ms|s|sec|"
    r"KB|kB|MB|"
    r"MSPS|Msps|ksps|kSPS|SPS|"
    r"wait\s+states?)(?:\b|$)",
    re.IGNORECASE,
)
_NUMERIC_BARE_RE = re.compile(r"(-?\d+\.?\d*)")

# Numeric range: "X to Y" or "X - Y" with optional units
_RANGE_RE = re.compile(
    r"(-?\d+\.?\d*)\s*([a-zA-Z\u00b0\u00b5]*)\s*(?:to|-|\u2013|\u2014)\s*(-?\d+\.?\d*)\s*([a-zA-Z\u00b0\u00b5]*)",
)

# Unit normalization table
_UNIT_TABLE: dict[str, tuple[str, float]] = {
    "hz": ("Hz", 1.0),
    "khz": ("Hz", 1e3),
    "mhz": ("Hz", 1e6),
    "ghz": ("Hz", 1e9),
    "v": ("V", 1.0),
    "volt": ("V", 1.0),
    "volts": ("V", 1.0),
    "mv": ("V", 1e-3),
    "a": ("A", 1.0),
    "amp": ("A", 1.0),
    "amps": ("A", 1.0),
    "ma": ("A", 1e-3),
    "ua": ("A", 1e-6),
    "µa": ("A", 1e-6),
    "s": ("s", 1.0),
    "sec": ("s", 1.0),
    "ms": ("s", 1e-3),
    "us": ("s", 1e-6),
    "µs": ("s", 1e-6),
    "ns": ("s", 1e-9),
    "kb": ("B", 1024.0),
    "mb": ("B", 1048576.0),
    "msps": ("SPS", 1e6),
    "ksps": ("SPS", 1e3),
    "sps": ("SPS", 1.0),
    "\u00b0c": ("\u00b0C", 1.0),
    "\u00b0f": ("\u00b0F", 1.0),
}

# Text scoring stopwords
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "of",
        "on",
        "in",
        "to",
        "for",
        "it",
        "and",
        "or",
        "that",
        "this",
        "was",
        "be",
        "at",
        "by",
    }
)

# Answer extraction patterns for text format
_ANSWER_IS_RE = re.compile(r"(?:is|=|:)\s+(.+?)(?:\.|,|\n|$)", re.IGNORECASE)


def extract_answer(raw_response: str, answer_format: str) -> str:
    """Extract the answer value from an LLM response.

    Handles common response patterns like:
    - "The base address is 0x40013000" → "0x40013000"
    - "0x40013000" → "0x40013000"
    - "[5:3]" → "[5:3]"
    - "RO (read-only)" → "RO"

    Args:
        raw_response: Full text response from the LLM.
        answer_format: Expected format: "hex", "bit_range", "access_code".

    Returns:
        Extracted and normalized answer string, or empty string if not found.
    """
    text = raw_response.strip()

    if answer_format == "hex":
        return _extract_hex(text)
    if answer_format == "bit_range":
        return _extract_bit_range(text)
    if answer_format == "access_code":
        return _extract_access(text)
    if answer_format == "text":
        return _extract_text(text)
    if answer_format == "numeric":
        return _extract_numeric(text)
    if answer_format == "numeric_range":
        return _extract_numeric_range(text)
    if answer_format == "list":
        return _extract_list(text)
    return text


def _extract_hex(text: str) -> str:
    """Extract a hex value from text."""
    match = _HEX_RE.search(text)
    if match:
        return normalize_hex(match.group())
    # Try bare hex digits (without 0x prefix) — require exactly 8 chars
    # (full 32-bit address) and at least one digit to avoid matching
    # English words like DEAD, FACE, CAFE, BEEF
    bare_hex = re.search(r"\b([0-9A-Fa-f]{8})\b", text)
    if bare_hex and re.search(r"[0-9]", bare_hex.group()):
        return normalize_hex(bare_hex.group())
    return ""


def _extract_bit_range(text: str) -> str:
    """Extract a bit range from text."""
    # Try [MSB:LSB] format first
    match = _BIT_RANGE_RE.search(text)
    if match:
        msb = match.group(1)
        lsb = match.group(2)
        if lsb is not None:
            return normalize_bit_range(f"[{msb}:{lsb}]")
        return normalize_bit_range(f"[{msb}]")

    # Try "bits N-M" or "bit N to M" format
    alt_match = _BIT_RANGE_ALT_RE.search(text)
    if alt_match:
        a, b = int(alt_match.group(1)), int(alt_match.group(2))
        msb_val, lsb_val = max(a, b), min(a, b)
        if msb_val == lsb_val:
            return f"[{msb_val}]"
        return f"[{msb_val}:{lsb_val}]"

    # Try single "bit N"
    single_match = _BIT_SINGLE_RE.search(text)
    if single_match:
        return f"[{single_match.group(1)}]"

    # Bare number as entire response (e.g. LLM replies "15" for bit position)
    bare = text.strip()
    if bare.isdigit() and len(bare) <= 2:
        return f"[{bare}]"

    return ""


def _extract_access(text: str) -> str:
    """Extract an access type from text."""
    match = _ACCESS_RE.search(text)
    if match:
        return normalize_access(match.group(1))
    return ""


def _extract_text(text: str) -> str:
    """Extract a text answer from a response.

    Short responses (<= 20 words) pass through directly.
    Longer ones use pattern matching: "is X", "answer: X", "= X".
    Fallback: last sentence.
    """
    if not text:
        return ""
    words = text.split()
    if len(words) <= 20:
        # Look for "is X" pattern even in short text
        match = _ANSWER_IS_RE.search(text)
        if match:
            return match.group(1).strip()
        return text

    # Try pattern-based extraction
    match = _ANSWER_IS_RE.search(text)
    if match:
        return match.group(1).strip()

    # Fallback: last sentence
    sentences = [s.strip() for s in re.split(r"[.!?\n]", text) if s.strip()]
    return sentences[-1] if sentences else text


def _extract_numeric(text: str) -> str:
    """Extract a numeric value with unit from text."""
    if not text:
        return ""
    match = _NUMERIC_RE.search(text)
    if match:
        num = match.group(1)
        unit = match.group(2).strip()
        # Normalize "wait states" → "wait states"
        return f"{num} {unit}"

    # Try bare number
    match = _NUMERIC_BARE_RE.search(text)
    if match:
        return match.group(1)
    return ""


def _extract_numeric_range(text: str) -> str:
    """Extract a numeric range (min-max) from text."""
    if not text:
        return ""
    match = _RANGE_RE.search(text)
    if match:
        lo_val = match.group(1)
        lo_unit = match.group(2)
        hi_val = match.group(3)
        hi_unit = match.group(4) or lo_unit
        return f"{lo_val}{lo_unit} to {hi_val}{hi_unit}"
    return ""


def _extract_list(text: str) -> str:
    """Extract a list of items from text.

    Splits on comma, newline, or bullet points.
    Returns comma-separated normalized list.
    """
    if not text:
        return ""
    # Split on comma, newline, bullet, or numbered list markers
    items = re.split(r"[,\n]|(?:^|\n)\s*[-•*]\s*|(?:^|\n)\s*\d+\.\s*", text)
    cleaned = [re.sub(r"^[-•*]\s*", "", item).strip() for item in items if item.strip()]
    cleaned = [item for item in cleaned if item]
    return ", ".join(cleaned)


def normalize_numeric(value: str) -> tuple[float, str]:
    """Normalize a numeric value with unit to canonical base unit.

    Returns:
        Tuple of (normalized_value, canonical_unit).
        For bare numbers, unit is empty string.
    """
    text = value.strip()
    match = _NUMERIC_RE.search(text)
    if match:
        num = float(match.group(1))
        raw_unit = match.group(2).strip().lower()
        # Handle "wait states" as text unit
        if "wait" in raw_unit:
            return num, "wait_states"
        canonical, multiplier = _UNIT_TABLE.get(raw_unit, ("", 1.0))
        return num * multiplier, canonical

    # Try bare number
    bare = _NUMERIC_BARE_RE.search(text)
    if bare:
        return float(bare.group(1)), ""
    return 0.0, ""


def extract_confidence(raw_response: str) -> float | None:
    """Extract a confidence value from an LLM response.

    Recognizes patterns like:
    - "Confidence: 90%" → 0.9
    - "I am 85% confident" → 0.85
    - "Confidence: 0.95" → 0.95

    Args:
        raw_response: Full text response from the LLM.

    Returns:
        Confidence as a float 0.0-1.0, or None if not found.
    """
    text = raw_response.strip()
    if not text:
        return None

    # Try "Confidence: N%" or "certain: N%"
    match = _CONFIDENCE_PCT_RE.search(text)
    if match:
        return int(match.group(1)) / 100.0

    # Try "N% confident" or "N% certain"
    match = _CONFIDENCE_PHRASE_RE.search(text)
    if match:
        return int(match.group(1)) / 100.0

    # Try "Confidence: 0.95"
    match = _CONFIDENCE_DECIMAL_RE.search(text)
    if match:
        return float(match.group(1))

    return None


def normalize_hex(value: str) -> str:
    """Normalize hex values to consistent format.

    - Ensures 0x prefix (uppercase X not used)
    - Strips leading zeros beyond the minimum width
    - Uses uppercase hex digits

    Examples:
        "40013000" → "0x40013000"
        "0x0040013000" → "0x40013000"
        "0X0000" → "0x0000"
    """
    cleaned = value.strip().upper()
    if cleaned.startswith("0X"):
        cleaned = cleaned[2:]

    # Remove leading zeros but keep at least 1 digit
    cleaned = cleaned.lstrip("0") or "0"

    # Pad to even number of nibbles (min 4 for addresses, min 1 for small values)
    if len(cleaned) <= 4:
        cleaned = cleaned.zfill(4)
    elif len(cleaned) <= 8:
        cleaned = cleaned.zfill(8)

    return f"0x{cleaned}"


def normalize_bit_range(value: str) -> str:
    """Normalize bit range expressions.

    Examples:
        "[5:3]" → "[5:3]"
        "bits 5-3" → "[5:3]"
        "bit 5 to bit 3" → "[5:3]"
        "[5]" → "[5]"
        "5" → "[5]"
    """
    text = value.strip()

    # Already in [N:M] or [N] format
    match = _BIT_RANGE_RE.search(text)
    if match:
        msb = match.group(1)
        lsb = match.group(2)
        if lsb is not None:
            return f"[{msb}:{lsb}]"
        return f"[{msb}]"

    # "bits N-M" or "N to M"
    alt_match = _BIT_RANGE_ALT_RE.search(text)
    if alt_match:
        a, b = int(alt_match.group(1)), int(alt_match.group(2))
        msb_val, lsb_val = max(a, b), min(a, b)
        if msb_val == lsb_val:
            return f"[{msb_val}]"
        return f"[{msb_val}:{lsb_val}]"

    # Bare number
    bare = re.search(r"(\d+)", text)
    if bare:
        return f"[{bare.group(1)}]"

    return text


def normalize_access(value: str) -> str:
    """Normalize access type strings.

    Examples:
        "read-only" → "RO"
        "Read/Write" → "RW"
        "RO" → "RO"
        "write-once" → "W1"
    """
    text = value.strip().lower().replace("-", "").replace(" ", "").replace("/", "")

    access_map = {
        "ro": "RO",
        "readonly": "RO",
        "rw": "RW",
        "readwrite": "RW",
        "wo": "WO",
        "writeonly": "WO",
        "w1": "W1",
        "writeonce": "W1",
        "rw1": "RW1",
        "readwriteonce": "RW1",
    }

    return access_map.get(text, value.strip().upper())


def score_answer(
    extracted: str,
    ground_truth: str,
    answer_format: str,
) -> float:
    """Score an extracted answer against ground truth.

    Uses exact match after normalization. Returns 1.0 for correct, 0.0 for wrong.

    Args:
        extracted: The extracted/normalized answer from the LLM response.
        ground_truth: The correct answer from the dataset.
        answer_format: The answer format type.

    Returns:
        1.0 if correct, 0.0 if incorrect.
    """
    if not extracted:
        return 0.0

    if answer_format == "hex":
        return 1.0 if normalize_hex(extracted) == normalize_hex(ground_truth) else 0.0
    if answer_format == "bit_range":
        return 1.0 if normalize_bit_range(extracted) == normalize_bit_range(ground_truth) else 0.0
    if answer_format == "access_code":
        return 1.0 if normalize_access(extracted) == normalize_access(ground_truth) else 0.0
    if answer_format == "text":
        return _score_text(extracted, ground_truth)
    if answer_format == "numeric":
        return _score_numeric(extracted, ground_truth)
    if answer_format == "numeric_range":
        return _score_numeric_range(extracted, ground_truth)
    if answer_format == "list":
        return _score_list(extracted, ground_truth)

    return 1.0 if extracted.strip() == ground_truth.strip() else 0.0


def score_answer_partial(
    extracted: str,
    ground_truth: str,
    answer_format: str,
) -> float:
    """Score an extracted answer with partial credit.

    Unlike score_answer() which returns binary 0/1, this returns a graded
    score between 0.0 and 1.0 based on how close the answer is.

    Scoring by format:
    - hex: nibble-level match ratio (matching nibbles / total nibbles)
    - bit_range: Jaccard index of bit position sets (intersection / union)
    - access_code: binary (no meaningful partial credit)

    Args:
        extracted: The extracted/normalized answer from the LLM response.
        ground_truth: The correct answer from the dataset.
        answer_format: The answer format type.

    Returns:
        Score between 0.0 and 1.0.
    """
    if not extracted:
        return 0.0

    if answer_format == "hex":
        return _partial_hex(extracted, ground_truth)
    if answer_format == "bit_range":
        return _partial_bit_range(extracted, ground_truth)
    if answer_format == "access_code":
        return 1.0 if normalize_access(extracted) == normalize_access(ground_truth) else 0.0
    if answer_format == "text":
        return _partial_text(extracted, ground_truth)
    if answer_format == "numeric":
        return _partial_numeric(extracted, ground_truth)
    if answer_format == "numeric_range":
        return _partial_numeric_range(extracted, ground_truth)
    if answer_format == "list":
        return _partial_list(extracted, ground_truth)

    return 1.0 if extracted.strip() == ground_truth.strip() else 0.0


def _partial_hex(extracted: str, ground_truth: str) -> float:
    """Compute nibble-level match ratio for hex values."""
    e = normalize_hex(extracted)
    g = normalize_hex(ground_truth)
    if e == g:
        return 1.0

    e_digits = e[2:]  # strip "0x"
    g_digits = g[2:]
    max_len = max(len(e_digits), len(g_digits))
    e_digits = e_digits.zfill(max_len)
    g_digits = g_digits.zfill(max_len)

    matches = sum(a == b for a, b in zip(e_digits, g_digits, strict=True))
    return matches / max_len


def _partial_bit_range(extracted: str, ground_truth: str) -> float:
    """Compute Jaccard index of bit position sets."""
    e = normalize_bit_range(extracted)
    g = normalize_bit_range(ground_truth)
    if e == g:
        return 1.0

    e_bits = _range_to_bit_set(e)
    g_bits = _range_to_bit_set(g)
    if not e_bits or not g_bits:
        return 0.0

    intersection = e_bits & g_bits
    union = e_bits | g_bits
    return len(intersection) / len(union) if union else 0.0


def _range_to_bit_set(normalized: str) -> set[int]:
    """Convert a normalized bit range like '[5:3]' or '[6]' to a set of bit positions."""
    match = _BIT_RANGE_RE.search(normalized)
    if not match:
        return set()

    msb = int(match.group(1))
    lsb_str = match.group(2)
    if lsb_str is not None:
        lsb = int(lsb_str)
        return set(range(lsb, msb + 1))
    return {msb}


def _normalize_text(text: str) -> str:
    """Lowercase, strip, remove articles."""
    t = text.strip().lower()
    words = t.split()
    return " ".join(w for w in words if w not in {"a", "an", "the"})


def _tokenize(text: str) -> set[str]:
    """Split into tokens, remove stopwords, lowercase, strip punctuation."""
    words = re.split(r"[\s,;:()]+", text.lower())
    return {
        w.strip(".,;:()[]") for w in words if w.strip(".,;:()[]") and w.lower() not in _STOPWORDS
    }


def _score_text(extracted: str, ground_truth: str) -> float:
    """Binary text scoring: 1.0 if normalized ground_truth is substring of extracted."""
    if not extracted:
        return 0.0
    gt_norm = _normalize_text(ground_truth)
    ext_norm = _normalize_text(extracted)
    return 1.0 if gt_norm in ext_norm else 0.0


def _partial_text(extracted: str, ground_truth: str) -> float:
    """Partial text scoring: token Jaccard coefficient."""
    if not extracted:
        return 0.0
    gt_tokens = _tokenize(ground_truth)
    ext_tokens = _tokenize(extracted)
    if not gt_tokens and not ext_tokens:
        return 1.0
    if not gt_tokens or not ext_tokens:
        return 0.0
    intersection = gt_tokens & ext_tokens
    union = gt_tokens | ext_tokens
    return len(intersection) / len(union) if union else 0.0


def _score_numeric(extracted: str, ground_truth: str) -> float:
    """Binary numeric scoring: exact match after unit normalization."""
    if not extracted:
        return 0.0
    ext_val, ext_unit = normalize_numeric(extracted)
    gt_val, gt_unit = normalize_numeric(ground_truth)
    if ext_unit == gt_unit:
        if gt_val == 0:
            return 1.0 if ext_val == 0 else 0.0
        return 1.0 if abs(ext_val - gt_val) / abs(gt_val) < 1e-6 else 0.0
    # Unit mismatch — try two fallbacks:
    # 1. Compare normalized values directly (handles "16000000" vs "16 MHz")
    if ext_val != 0 and gt_val != 0 and abs(ext_val - gt_val) / abs(gt_val) < 1e-6:
        return 1.0
    # 2. Compare raw numeric parts (handles "1024" vs "1024 KB")
    if ext_unit == "" or gt_unit == "":
        raw_ext = _NUMERIC_BARE_RE.search(extracted)
        raw_gt = _NUMERIC_BARE_RE.search(ground_truth)
        if raw_ext and raw_gt:
            re_val, rg_val = float(raw_ext.group(1)), float(raw_gt.group(1))
            if rg_val == 0:
                return 1.0 if re_val == 0 else 0.0
            if abs(re_val - rg_val) / abs(rg_val) < 1e-6:
                return 1.0
    return 0.0


def _partial_numeric(extracted: str, ground_truth: str) -> float:
    """Partial numeric scoring: ratio-based."""
    if not extracted:
        return 0.0
    ext_val, ext_unit = normalize_numeric(extracted)
    gt_val, gt_unit = normalize_numeric(ground_truth)

    def _ratio(a: float, b: float) -> float:
        if b == 0:
            return 1.0 if a == 0 else 0.0
        return max(0.0, 1.0 - min(1.0, abs(a - b) / abs(b)))

    if ext_unit == gt_unit:
        return _ratio(ext_val, gt_val)
    # Unit mismatch — try normalized values directly (handles "16000000" vs "16 MHz")
    if ext_val != 0 and gt_val != 0:
        ratio = _ratio(ext_val, gt_val)
        if ratio > 0:
            return ratio
    # Fallback: compare raw numeric parts (handles "1024" vs "1024 KB")
    if ext_unit == "" or gt_unit == "":
        raw_ext = _NUMERIC_BARE_RE.search(extracted)
        raw_gt = _NUMERIC_BARE_RE.search(ground_truth)
        if raw_ext and raw_gt:
            return _ratio(float(raw_ext.group(1)), float(raw_gt.group(1)))
    return 0.0


def _score_numeric_range(extracted: str, ground_truth: str) -> float:
    """Binary numeric range scoring: both bounds must match after normalization."""
    if not extracted:
        return 0.0
    ext_lo, ext_hi, ext_unit = _parse_range(extracted)
    gt_lo, gt_hi, gt_unit = _parse_range(ground_truth)
    if ext_unit != gt_unit and ext_unit != "" and gt_unit != "":
        return 0.0
    lo_ok = abs(ext_lo - gt_lo) < 1e-6 * max(1, abs(gt_lo)) if gt_lo != 0 else ext_lo == 0
    hi_ok = abs(ext_hi - gt_hi) < 1e-6 * max(1, abs(gt_hi)) if gt_hi != 0 else ext_hi == 0
    return 1.0 if lo_ok and hi_ok else 0.0


def _partial_numeric_range(extracted: str, ground_truth: str) -> float:
    """Partial numeric range scoring: 0.5 per matching bound."""
    if not extracted:
        return 0.0
    ext_lo, ext_hi, ext_unit = _parse_range(extracted)
    gt_lo, gt_hi, gt_unit = _parse_range(ground_truth)
    if ext_unit != gt_unit and ext_unit != "" and gt_unit != "":
        return 0.0
    score = 0.0
    if abs(ext_lo - gt_lo) < 1e-6 * max(1, abs(gt_lo)):
        score += 0.5
    if abs(ext_hi - gt_hi) < 1e-6 * max(1, abs(gt_hi)):
        score += 0.5
    return score


def _parse_range(text: str) -> tuple[float, float, str]:
    """Parse a numeric range string into (lo, hi, canonical_unit)."""
    match = _RANGE_RE.search(text)
    if not match:
        return 0.0, 0.0, ""
    lo_raw = match.group(1)
    lo_unit_raw = match.group(2) or ""
    hi_raw = match.group(3)
    hi_unit_raw = match.group(4) or ""

    # Inherit unit: if one side lacks a unit, take it from the other
    if not lo_unit_raw and hi_unit_raw:
        lo_unit_raw = hi_unit_raw
    elif lo_unit_raw and not hi_unit_raw:
        hi_unit_raw = lo_unit_raw

    lo_val = float(lo_raw)
    hi_val = float(hi_raw)

    # Normalize units
    lo_unit_key = lo_unit_raw.lower()
    hi_unit_key = hi_unit_raw.lower()
    if lo_unit_key in _UNIT_TABLE:
        canonical, mult = _UNIT_TABLE[lo_unit_key]
        lo_val *= mult
    else:
        canonical = lo_unit_raw

    if hi_unit_key in _UNIT_TABLE:
        _, mult = _UNIT_TABLE[hi_unit_key]
        hi_val *= mult

    return lo_val, hi_val, canonical


def _score_list(extracted: str, ground_truth: str) -> float:
    """Binary list scoring: Jaccard >= 0.75 → 1.0, else 0.0."""
    if not extracted:
        return 0.0
    ext_set = _list_to_set(extracted)
    gt_set = _list_to_set(ground_truth)
    if not gt_set:
        return 1.0 if not ext_set else 0.0
    jaccard = _set_jaccard(ext_set, gt_set)
    return 1.0 if jaccard >= 0.75 else 0.0


def _partial_list(extracted: str, ground_truth: str) -> float:
    """Partial list scoring: raw Jaccard coefficient."""
    if not extracted:
        return 0.0
    ext_set = _list_to_set(extracted)
    gt_set = _list_to_set(ground_truth)
    if not gt_set and not ext_set:
        return 1.0
    return _set_jaccard(ext_set, gt_set)


def _list_to_set(text: str) -> set[str]:
    """Convert a comma/newline separated list to a normalized set."""
    items = re.split(r"[,\n]|(?:^|\n)\s*[-•*]\s*|(?:^|\n)\s*\d+\.\s*", text)
    return {item.strip().lower() for item in items if item.strip()}


def _set_jaccard(a: set[str], b: set[str]) -> float:
    """Compute Jaccard index of two sets."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def compute_metrics(responses: tuple[BenchResponse, ...] | list[BenchResponse]) -> BenchMetrics:
    """Compute aggregated metrics from benchmark responses.

    Args:
        responses: Collection of benchmark responses.

    Returns:
        Aggregated BenchMetrics.
    """
    if not responses:
        return BenchMetrics(
            total=0,
            correct=0,
            accuracy=0.0,
            hallucination_rate=0.0,
        )

    total = len(responses)
    correct = sum(1 for r in responses if r.correct)
    accuracy = correct / total if total > 0 else 0.0

    # Per-category accuracy
    categories: dict[str, list[bool]] = {}
    for r in responses:
        # Extract category from question_id pattern: peripheral_register_field_category
        # We track by the response's correctness
        cat = _infer_category(r.question_id)
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r.correct)

    by_category = {
        cat: sum(results) / len(results) for cat, results in categories.items() if results
    }

    avg_latency = sum(r.latency_ms for r in responses) / total if total > 0 else 0.0
    avg_partial = sum(r.partial_score for r in responses) / total if total > 0 else 0.0

    # Expected Calibration Error (ECE) — only if confidence data is available
    ece = _compute_ece(responses)

    return BenchMetrics(
        total=total,
        correct=correct,
        accuracy=accuracy,
        hallucination_rate=1.0 - accuracy,
        by_category=by_category,
        avg_latency_ms=avg_latency,
        avg_partial_score=avg_partial,
        expected_calibration_error=ece,
    )


def _infer_category(question_id: str) -> str:
    """Infer the category from a question ID.

    Question IDs follow patterns like:
    - spi1_base_address → base_address
    - spi1_cr1_offset → register_offset
    - spi1_cr1_br_bits → bit_field
    - spi1_cr1_reset → reset_value
    - spi1_cr1_access → access_type
    """
    parts = question_id.split("_")
    if not parts:
        return "unknown"

    suffix = parts[-1]
    if suffix == "address" and len(parts) >= 2 and parts[-2] == "base":
        return "base_address"
    if suffix == "offset":
        return "register_offset"
    if suffix == "bits":
        return "bit_field"
    if suffix == "reset":
        return "reset_value"
    if suffix == "access":
        return "access_type"

    return "unknown"


def _compute_ece(
    responses: tuple[BenchResponse, ...] | list[BenchResponse],
    num_bins: int = 10,
) -> float | None:
    """Compute Expected Calibration Error.

    Groups responses by confidence into bins, then measures the weighted
    average absolute difference between confidence and accuracy per bin.

    Returns None if no responses have confidence data.
    """
    with_conf = [(r.correct, r.confidence) for r in responses if r.confidence is not None]
    if not with_conf:
        return None

    total = len(with_conf)
    bin_size = 1.0 / num_bins
    ece = 0.0

    for i in range(num_bins):
        lo = i * bin_size
        hi = lo + bin_size
        in_bin = [
            (c, conf)
            for c, conf in with_conf
            if lo <= conf < hi or (i == num_bins - 1 and conf == 1.0)
        ]
        if not in_bin:
            continue

        bin_acc = sum(1 for c, _ in in_bin if c) / len(in_bin)
        bin_conf = sum(conf for _, conf in in_bin) / len(in_bin)
        ece += abs(bin_acc - bin_conf) * len(in_bin) / total

    return ece


def wilson_ci(
    successes: int,
    trials: int,
    z: float = 1.96,
) -> tuple[float, float]:
    """Compute Wilson score confidence interval for a proportion.

    The Wilson score interval provides better coverage than the normal
    approximation, especially for small samples and extreme proportions.

    Args:
        successes: Number of successes (correct answers).
        trials: Total number of trials (questions).
        z: Z-score for confidence level (1.96 for 95%, 1.645 for 90%).

    Returns:
        Tuple of (lower_bound, upper_bound) as proportions [0.0, 1.0].
    """
    if trials == 0:
        return 0.0, 0.0

    n = trials
    p = successes / n
    z2 = z * z

    denominator = 1 + z2 / n
    center = p + z2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))

    lower = max(0.0, (center - margin) / denominator)
    upper = min(1.0, (center + margin) / denominator)

    return lower, upper


def mcnemar_test(
    a_results: list[bool],
    b_results: list[bool],
) -> tuple[float, float]:
    """Compute McNemar's test for paired binary outcomes.

    Uses Edwards' continuity correction (|b-c| - 1)^2 / (b+c), which is
    the standard form recommended for small sample sizes (< 25 discordant
    pairs). Tests whether the accuracy difference between two conditions
    (e.g., no_context vs hwcc_full) is statistically significant.

    Args:
        a_results: Per-question correctness for condition A.
        b_results: Per-question correctness for condition B (same questions).

    Returns:
        Tuple of (test_statistic, p_value). p_value < 0.05 means significant.
    """
    if not a_results or not b_results:
        return 0.0, 1.0

    # Count discordant pairs
    b_count = 0  # A wrong, B correct
    c_count = 0  # A correct, B wrong

    for a, b in zip(a_results, b_results, strict=True):
        if not a and b:
            b_count += 1
        elif a and not b:
            c_count += 1

    total_discordant = b_count + c_count
    if total_discordant == 0:
        return 0.0, 1.0

    # McNemar's chi-squared statistic with Edwards' continuity correction
    chi2 = max(0, abs(b_count - c_count) - 1) ** 2 / total_discordant

    # p-value from chi-squared distribution with df=1
    p_value = _chi2_sf(chi2, df=1)

    return chi2, p_value


def _chi2_sf(x: float, df: int = 1) -> float:
    """Survival function (1-CDF) for chi-squared distribution with df=1.

    Only supports df=1 (used by McNemar's test).
    For df=1: P(X > x) = erfc(sqrt(x/2))
    """
    if df != 1:
        msg = f"_chi2_sf only supports df=1, got df={df}"
        raise ValueError(msg)
    if x <= 0:
        return 1.0
    return math.erfc(math.sqrt(x / 2))


def compute_metrics_with_difficulty(
    responses: tuple[BenchResponse, ...] | list[BenchResponse],
    difficulty_map: dict[str, str] | None = None,
) -> BenchMetrics:
    """Compute metrics including per-difficulty and CI breakdown.

    Like compute_metrics but also computes:
    - Wilson CI for overall accuracy
    - Per-difficulty accuracy breakdown

    Args:
        responses: Collection of benchmark responses.
        difficulty_map: Maps question_id → difficulty level (easy/medium/hard).

    Returns:
        BenchMetrics with CI and difficulty fields populated.
    """
    base = compute_metrics(responses)

    if not responses:
        return base

    # Wilson CI
    ci_lower, ci_upper = wilson_ci(base.correct, base.total)

    # Per-difficulty accuracy
    by_difficulty: dict[str, list[bool]] = {}
    if difficulty_map:
        for r in responses:
            diff = difficulty_map.get(r.question_id, "medium")
            if diff not in by_difficulty:
                by_difficulty[diff] = []
            by_difficulty[diff].append(r.correct)

    diff_accuracy = {
        diff: sum(results) / len(results) for diff, results in by_difficulty.items() if results
    }

    return BenchMetrics(
        total=base.total,
        correct=base.correct,
        accuracy=base.accuracy,
        hallucination_rate=base.hallucination_rate,
        by_category=base.by_category,
        avg_latency_ms=base.avg_latency_ms,
        total_tokens=base.total_tokens,
        avg_partial_score=base.avg_partial_score,
        expected_calibration_error=base.expected_calibration_error,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        by_difficulty=diff_accuracy,
    )
