"""Dataset generator — creates benchmark Q&A pairs from SVD files."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hwcc.bench.types import BenchDataset, BenchQuestion
from hwcc.exceptions import BenchmarkError

if TYPE_CHECKING:
    from pathlib import Path

    from cmsis_svd.model import (
        SVDDevice,
        SVDField,
        SVDPeripheral,
        SVDRegister,
    )

__all__ = ["generate_dataset", "load_dataset", "save_dataset"]

logger = logging.getLogger(__name__)

# Common peripherals to prioritize (sorted by typical relevance for embedded dev)
_PRIORITY_PERIPHERALS = [
    "SPI",
    "USART",
    "UART",
    "TIM",
    "GPIO",
    "RCC",
    "DMA",
    "ADC",
    "I2C",
    "CAN",
    "DAC",
    "IWDG",
    "WWDG",
    "PWR",
    "EXTI",
    "SYSCFG",
    "FLASH",
]

_MAX_REGISTERS_PER_PERIPHERAL = 3
_MAX_FIELDS_PER_REGISTER = 3


def generate_dataset(
    svd_path: Path,
    num_peripherals: int = 10,
    chip: str = "",
) -> BenchDataset:
    """Generate a benchmark dataset from an SVD file.

    Parses the SVD file and generates Q&A pairs across 5 categories:
    base_address, register_offset, bit_field, reset_value, access_type.

    Args:
        svd_path: Path to the .svd file.
        num_peripherals: Maximum number of peripherals to include.
        chip: Chip name override (auto-detected from SVD if empty).

    Returns:
        BenchDataset with generated questions.

    Raises:
        BenchmarkError: If the SVD file cannot be parsed.
    """
    try:
        from cmsis_svd.parser import SVDParser
    except ImportError as e:
        msg = "cmsis-svd library is required: pip install cmsis-svd"
        raise BenchmarkError(msg) from e

    if not svd_path.exists():
        msg = f"SVD file not found: {svd_path}"
        raise BenchmarkError(msg)

    try:
        parser = SVDParser.for_xml_file(str(svd_path))
        device = parser.get_device()
    except Exception as e:
        msg = f"Failed to parse SVD file: {e}"
        raise BenchmarkError(msg) from e

    chip_name = chip or device.name or svd_path.stem
    peripherals = _select_peripherals(device, num_peripherals)

    if not peripherals:
        msg = f"No peripherals found in {svd_path.name}"
        raise BenchmarkError(msg)

    questions: list[BenchQuestion] = []
    for peripheral in peripherals:
        questions.extend(_generate_peripheral_questions(peripheral, chip_name))

    categories = tuple(sorted({q.category for q in questions}))
    dataset = BenchDataset(
        name=f"{chip_name}_RegisterKnowledge",
        chip=chip_name,
        source_svd=str(svd_path),
        question_count=len(questions),
        questions=tuple(questions),
        created=datetime.now(UTC).isoformat(),
        categories=categories,
    )

    logger.info(
        "Generated dataset: %d questions across %d peripherals, %d categories",
        len(questions),
        len(peripherals),
        len(categories),
    )

    return dataset


def _select_peripherals(
    device: SVDDevice,
    max_count: int,
) -> list[SVDPeripheral]:
    """Select peripherals, prioritizing common ones.

    Returns peripherals sorted by priority (common first), then alphabetically.
    Skips peripherals without base_address or registers.
    """
    from cmsis_svd.model import SVDPeripheral, SVDPeripheralArray

    if not device.peripherals:
        return []

    # Flatten peripheral arrays
    all_peripherals: list[SVDPeripheral] = []
    for item in device.peripherals:
        if isinstance(item, SVDPeripheral):
            all_peripherals.append(item)
        elif isinstance(item, SVDPeripheralArray):
            all_peripherals.extend(item.peripherals)

    # Filter: must have base_address and registers
    valid = [p for p in all_peripherals if p.base_address is not None and p.registers]

    # Sort by priority
    def priority_key(p: SVDPeripheral) -> tuple[int, str]:
        name = (p.name or "").upper()
        for i, prefix in enumerate(_PRIORITY_PERIPHERALS):
            if name.startswith(prefix):
                return (i, name)
        return (len(_PRIORITY_PERIPHERALS), name)

    valid.sort(key=priority_key)
    return valid[:max_count]


def _generate_peripheral_questions(
    peripheral: SVDPeripheral,
    chip: str,
) -> list[BenchQuestion]:
    """Generate all question types for a single peripheral."""
    from cmsis_svd.model import (
        SVDRegister,
        SVDRegisterArray,
        SVDRegisterCluster,
    )

    questions: list[BenchQuestion] = []
    name = peripheral.name or "UNKNOWN"

    # 1. Base address question (always)
    if peripheral.base_address is not None:
        questions.append(
            BenchQuestion(
                id=f"{name.lower()}_base_address",
                category="base_address",
                peripheral=name,
                register="",
                field_name="",
                question=f"What is the base address of the {name} peripheral on the {chip}?",
                answer=f"0x{peripheral.base_address:08X}",
                answer_format="hex",
            )
        )

    # Collect registers
    registers: list[SVDRegister] = []
    if peripheral.registers:
        for item in peripheral.registers:
            if isinstance(item, SVDRegister):
                registers.append(item)
            elif isinstance(item, SVDRegisterArray):
                registers.extend(item.registers)
            elif isinstance(item, SVDRegisterCluster) and item.registers:
                for sub in item.registers:
                    if isinstance(sub, SVDRegister):
                        registers.append(sub)

    # Sort by offset for deterministic order
    registers.sort(key=lambda r: r.address_offset if r.address_offset is not None else 0)

    # 2-3. Register-level questions (offset, reset value, access type)
    for reg in registers[:_MAX_REGISTERS_PER_PERIPHERAL]:
        questions.extend(_generate_register_questions(reg, name, chip))

    # 4. Field-level questions (bit_field)
    field_questions: list[BenchQuestion] = []
    for reg in registers:
        if reg.fields:
            field_questions.extend(_generate_field_questions(reg, name, chip))
        if len(field_questions) >= _MAX_FIELDS_PER_REGISTER * _MAX_REGISTERS_PER_PERIPHERAL:
            break
    questions.extend(field_questions[: _MAX_FIELDS_PER_REGISTER * _MAX_REGISTERS_PER_PERIPHERAL])

    return questions


def _generate_register_questions(
    reg: SVDRegister,
    peripheral_name: str,
    chip: str,
) -> list[BenchQuestion]:
    """Generate register-level questions."""
    from cmsis_svd.model import SVDAccessType

    questions: list[BenchQuestion] = []
    reg_name = reg.name or "UNKNOWN"
    qid_base = f"{peripheral_name.lower()}_{reg_name.lower()}"

    # Offset question
    if reg.address_offset is not None:
        questions.append(
            BenchQuestion(
                id=f"{qid_base}_offset",
                category="register_offset",
                peripheral=peripheral_name,
                register=reg_name,
                field_name="",
                question=(
                    f"What is the address offset of the {reg_name} register "
                    f"in the {peripheral_name} peripheral on the {chip}?"
                ),
                answer=f"0x{reg.address_offset:04X}",
                answer_format="hex",
            )
        )

    # Reset value question
    if reg.reset_value is not None:
        questions.append(
            BenchQuestion(
                id=f"{qid_base}_reset",
                category="reset_value",
                peripheral=peripheral_name,
                register=reg_name,
                field_name="",
                question=(
                    f"What is the reset value of the {peripheral_name}_{reg_name} "
                    f"register on the {chip}?"
                ),
                answer=f"0x{reg.reset_value:08X}",
                answer_format="hex",
            )
        )

    # Access type question
    if reg.access is not None and isinstance(reg.access, SVDAccessType):
        access_map = {
            SVDAccessType.READ_ONLY: "RO",
            SVDAccessType.WRITE_ONLY: "WO",
            SVDAccessType.READ_WRITE: "RW",
            SVDAccessType.WRITE_ONCE: "W1",
            SVDAccessType.READ_WRITE_ONCE: "RW1",
        }
        access_str = access_map.get(reg.access)
        if access_str:
            questions.append(
                BenchQuestion(
                    id=f"{qid_base}_access",
                    category="access_type",
                    peripheral=peripheral_name,
                    register=reg_name,
                    field_name="",
                    question=(
                        f"What is the access type of the {peripheral_name}_{reg_name} "
                        f"register on the {chip}?"
                    ),
                    answer=access_str,
                    answer_format="access_code",
                )
            )

    return questions


def _generate_field_questions(
    reg: SVDRegister,
    peripheral_name: str,
    chip: str,
) -> list[BenchQuestion]:
    """Generate field-level bit position questions."""
    from cmsis_svd.model import SVDField

    questions: list[BenchQuestion] = []
    reg_name = reg.name or "UNKNOWN"

    if not reg.fields:
        return questions

    typed_fields: list[SVDField] = [f for f in reg.fields if isinstance(f, SVDField)]
    # Sort by bit position (descending) for consistency
    typed_fields.sort(
        key=lambda f: (f.bit_offset or 0) + (f.bit_width or 1) - 1,
        reverse=True,
    )

    for fld in typed_fields[:_MAX_FIELDS_PER_REGISTER]:
        if fld.bit_offset is None or fld.bit_width is None:
            continue

        field_name = fld.name or "UNKNOWN"
        msb = fld.bit_offset + fld.bit_width - 1
        bit_str = f"[{msb}]" if fld.bit_width == 1 else f"[{msb}:{fld.bit_offset}]"

        qid = f"{peripheral_name.lower()}_{reg_name.lower()}_{field_name.lower()}_bits"
        questions.append(
            BenchQuestion(
                id=qid,
                category="bit_field",
                peripheral=peripheral_name,
                register=reg_name,
                field_name=field_name,
                question=(
                    f"What bit position(s) does the {field_name} field occupy "
                    f"in the {peripheral_name}_{reg_name} register on the {chip}?"
                ),
                answer=bit_str,
                answer_format="bit_range",
            )
        )

    return questions


def save_dataset(dataset: BenchDataset, path: Path) -> None:
    """Save a dataset to JSON file.

    Args:
        dataset: The dataset to save.
        path: Output file path.

    Raises:
        BenchmarkError: If writing fails.
    """
    try:
        data = asdict(dataset)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as e:
        msg = f"Failed to save dataset: {e}"
        raise BenchmarkError(msg) from e

    logger.info("Saved dataset to %s (%d questions)", path, dataset.question_count)


def load_dataset(path: Path) -> BenchDataset:
    """Load a dataset from JSON file.

    Args:
        path: Path to the JSON file.

    Returns:
        Loaded BenchDataset.

    Raises:
        BenchmarkError: If reading or parsing fails.
    """
    if not path.exists():
        msg = f"Dataset file not found: {path}"
        raise BenchmarkError(msg)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        msg = f"Failed to load dataset: {e}"
        raise BenchmarkError(msg) from e

    try:
        questions = tuple(BenchQuestion(**q) for q in data["questions"])
        return BenchDataset(
            name=data["name"],
            chip=data["chip"],
            source_svd=data["source_svd"],
            question_count=data["question_count"],
            questions=questions,
            created=data["created"],
            categories=tuple(data["categories"]),
        )
    except (KeyError, TypeError) as e:
        msg = f"Invalid dataset format: {e}"
        raise BenchmarkError(msg) from e
