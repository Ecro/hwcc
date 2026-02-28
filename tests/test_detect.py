"""Tests for file type detection module."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from hwcc.exceptions import ParseError
from hwcc.ingest.detect import (
    DocType,
    FileFormat,
    FileInfo,
    classify_doc_type,
    detect_file_type,
    get_supported_extensions,
)


class TestFileFormatEnum:
    """FileFormat enum is str-compatible."""

    def test_str_compatibility(self) -> None:
        assert FileFormat.PDF == "pdf"
        assert FileFormat.SVD == "svd"
        assert FileFormat.MARKDOWN == "markdown"
        assert FileFormat.TEXT == "text"
        assert FileFormat.UNKNOWN == "unknown"

    def test_is_string_instance(self) -> None:
        assert isinstance(FileFormat.PDF, str)


class TestDocTypeEnum:
    """DocType enum is str-compatible."""

    def test_str_compatibility(self) -> None:
        assert DocType.DATASHEET == "datasheet"
        assert DocType.REFERENCE_MANUAL == "reference_manual"
        assert DocType.ERRATA == "errata"
        assert DocType.APP_NOTE == "app_note"
        assert DocType.SCHEMATIC == "schematic"
        assert DocType.SVD == "svd"
        assert DocType.DEVICE_TREE == "device_tree"
        assert DocType.CODE == "code"
        assert DocType.DOCUMENTATION == "documentation"
        assert DocType.UNKNOWN == "unknown"

    def test_is_string_instance(self) -> None:
        assert isinstance(DocType.DATASHEET, str)


class TestFileInfoFrozen:
    """FileInfo is a frozen dataclass."""

    def test_frozen(self, tmp_path: Path) -> None:
        info = FileInfo(
            path=tmp_path / "test.pdf",
            format=FileFormat.PDF,
            doc_type=DocType.DATASHEET,
            parser_name="pdf",
            confidence=1.0,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            info.confidence = 0.5  # type: ignore[misc]

    def test_fields(self, tmp_path: Path) -> None:
        p = tmp_path / "test.pdf"
        info = FileInfo(
            path=p,
            format=FileFormat.PDF,
            doc_type=DocType.DATASHEET,
            parser_name="pdf",
            confidence=1.0,
        )
        assert info.path == p
        assert info.format == FileFormat.PDF
        assert info.doc_type == DocType.DATASHEET
        assert info.parser_name == "pdf"
        assert info.confidence == 1.0


class TestExtensionDetection:
    """detect_file_type returns correct format for known extensions."""

    @pytest.mark.parametrize(
        ("ext", "expected_format"),
        [
            (".pdf", FileFormat.PDF),
            (".svd", FileFormat.SVD),
            (".md", FileFormat.MARKDOWN),
            (".markdown", FileFormat.MARKDOWN),
            (".txt", FileFormat.TEXT),
            (".text", FileFormat.TEXT),
            (".dts", FileFormat.DEVICE_TREE),
            (".dtsi", FileFormat.DEVICE_TREE),
            (".h", FileFormat.C_HEADER),
            (".c", FileFormat.C_SOURCE),
            (".rs", FileFormat.RUST),
            (".html", FileFormat.HTML),
            (".htm", FileFormat.HTML),
            (".json", FileFormat.JSON_FORMAT),
            (".yaml", FileFormat.YAML),
            (".yml", FileFormat.YAML),
            (".ioc", FileFormat.CUBEMX),
            (".png", FileFormat.IMAGE),
            (".jpg", FileFormat.IMAGE),
            (".jpeg", FileFormat.IMAGE),
        ],
    )
    def test_known_extensions(self, tmp_path: Path, ext: str, expected_format: FileFormat) -> None:
        f = tmp_path / f"testfile{ext}"
        f.write_text("dummy content", encoding="utf-8")
        info = detect_file_type(f)
        assert info.format == expected_format

    def test_unknown_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "data.xyz"
        f.write_text("dummy", encoding="utf-8")
        info = detect_file_type(f)
        assert info.format == FileFormat.UNKNOWN

    @pytest.mark.parametrize("ext", [".PDF", ".Svd", ".MD", ".TXT"])
    def test_case_insensitive(self, tmp_path: Path, ext: str) -> None:
        f = tmp_path / f"testfile{ext}"
        f.write_text("dummy content", encoding="utf-8")
        info = detect_file_type(f)
        assert info.format != FileFormat.UNKNOWN


class TestParserNameMapping:
    """detect_file_type maps formats to correct parser names."""

    @pytest.mark.parametrize(
        ("ext", "expected_parser"),
        [
            (".pdf", "pdf"),
            (".svd", "svd"),
            (".md", "markdown"),
            (".txt", "text"),
            (".dts", "device_tree"),
            (".dtsi", "device_tree"),
            (".h", "c_header"),
            (".c", "c_source"),
            (".rs", "rust"),
        ],
    )
    def test_parser_mapping(self, tmp_path: Path, ext: str, expected_parser: str) -> None:
        f = tmp_path / f"testfile{ext}"
        f.write_text("dummy content", encoding="utf-8")
        info = detect_file_type(f)
        assert info.parser_name == expected_parser

    def test_unknown_parser_is_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "data.xyz"
        f.write_text("dummy", encoding="utf-8")
        info = detect_file_type(f)
        assert info.parser_name == ""


class TestMagicBytes:
    """Magic byte detection for binary formats."""

    def test_pdf_with_correct_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4 rest of content")
        info = detect_file_type(f)
        assert info.format == FileFormat.PDF
        assert info.confidence == 1.0

    def test_pdf_magic_wrong_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.bin"
        f.write_bytes(b"%PDF-1.4 rest of content")
        info = detect_file_type(f)
        assert info.format == FileFormat.PDF
        assert info.confidence < 1.0

    def test_non_pdf_with_pdf_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "fake.pdf"
        f.write_text("this is not a pdf", encoding="utf-8")
        info = detect_file_type(f)
        # Extension still wins for format detection, but confidence is lower
        assert info.format == FileFormat.PDF
        assert info.confidence < 1.0

    def test_png_magic(self, tmp_path: Path) -> None:
        f = tmp_path / "image.bin"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
        info = detect_file_type(f)
        assert info.format == FileFormat.IMAGE

    def test_jpeg_magic(self, tmp_path: Path) -> None:
        f = tmp_path / "image.bin"
        f.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 20)
        info = detect_file_type(f)
        assert info.format == FileFormat.IMAGE

    def test_svd_xml_disambiguation(self, tmp_path: Path) -> None:
        f = tmp_path / "chip.xml"
        f.write_text(
            '<?xml version="1.0"?>\n<device>\n  <name>STM32F407</name>\n</device>',
            encoding="utf-8",
        )
        info = detect_file_type(f)
        assert info.format == FileFormat.SVD

    def test_plain_xml_not_svd(self, tmp_path: Path) -> None:
        f = tmp_path / "config.xml"
        f.write_text(
            '<?xml version="1.0"?>\n<config>\n  <key>value</key>\n</config>',
            encoding="utf-8",
        )
        info = detect_file_type(f)
        # .xml is not a known extension, and magic bytes don't match SVD
        assert info.format != FileFormat.SVD

    def test_no_extension_with_magic(self, tmp_path: Path) -> None:
        f = tmp_path / "mystery"
        f.write_bytes(b"%PDF-1.7 content")
        info = detect_file_type(f)
        assert info.format == FileFormat.PDF

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        info = detect_file_type(f)
        assert info.format == FileFormat.TEXT


class TestDocTypeClassification:
    """classify_doc_type classifies filenames correctly."""

    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("STM32F407_datasheet.pdf", DocType.DATASHEET),
            ("ds_stm32f407.pdf", DocType.DATASHEET),
            ("RM0090_reference_manual.pdf", DocType.REFERENCE_MANUAL),
            ("rm_rm0090.pdf", DocType.REFERENCE_MANUAL),
            ("ref_manual_stm32.pdf", DocType.REFERENCE_MANUAL),
            ("ES0182_errata.pdf", DocType.ERRATA),
            ("es_stm32f407.pdf", DocType.ERRATA),
            ("erratum_i2c.pdf", DocType.ERRATA),
            ("AN4013_app_note.pdf", DocType.APP_NOTE),
            ("appnote_spi.pdf", DocType.APP_NOTE),
            ("an_timer_config.pdf", DocType.APP_NOTE),
            ("board_schematic.pdf", DocType.SCHEMATIC),
        ],
    )
    def test_filename_heuristics(self, filename: str, expected: DocType) -> None:
        result = classify_doc_type(Path(filename), FileFormat.PDF)
        assert result == expected

    def test_svd_always_svd(self) -> None:
        result = classify_doc_type(Path("random_name.svd"), FileFormat.SVD)
        assert result == DocType.SVD

    def test_dts_always_device_tree(self) -> None:
        result = classify_doc_type(Path("board.dts"), FileFormat.DEVICE_TREE)
        assert result == DocType.DEVICE_TREE

    def test_dtsi_always_device_tree(self) -> None:
        result = classify_doc_type(Path("board.dtsi"), FileFormat.DEVICE_TREE)
        assert result == DocType.DEVICE_TREE

    @pytest.mark.parametrize("ext", [".c", ".h", ".rs"])
    def test_code_formats(self, ext: str) -> None:
        fmt = {".c": FileFormat.C_SOURCE, ".h": FileFormat.C_HEADER, ".rs": FileFormat.RUST}[ext]
        result = classify_doc_type(Path(f"main{ext}"), fmt)
        assert result == DocType.CODE

    def test_markdown_is_documentation(self) -> None:
        result = classify_doc_type(Path("readme.md"), FileFormat.MARKDOWN)
        assert result == DocType.DOCUMENTATION

    def test_no_match_returns_unknown(self) -> None:
        result = classify_doc_type(Path("random_file.pdf"), FileFormat.PDF)
        assert result == DocType.UNKNOWN

    def test_case_insensitive(self) -> None:
        result = classify_doc_type(Path("STM32F407_DATASHEET.PDF"), FileFormat.PDF)
        assert result == DocType.DATASHEET


class TestDetectFileTypeErrors:
    """detect_file_type error handling."""

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        with pytest.raises(ParseError, match="does not exist"):
            detect_file_type(tmp_path / "nonexistent.pdf")

    def test_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ParseError, match="Not a file"):
            detect_file_type(tmp_path)


class TestGetSupportedExtensions:
    """get_supported_extensions returns all known extensions."""

    def test_returns_frozenset(self) -> None:
        exts = get_supported_extensions()
        assert isinstance(exts, frozenset)

    def test_contains_key_extensions(self) -> None:
        exts = get_supported_extensions()
        for ext in (".pdf", ".svd", ".md", ".txt", ".dts", ".h", ".c"):
            assert ext in exts

    def test_all_lowercase(self) -> None:
        exts = get_supported_extensions()
        for ext in exts:
            assert ext == ext.lower()
            assert ext.startswith(".")
