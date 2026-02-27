"""Tests for hwcc.manifest module."""

from __future__ import annotations

from pathlib import Path

import pytest

from hwcc.exceptions import ManifestError
from hwcc.manifest import (
    DocumentEntry,
    Manifest,
    compute_hash,
    load_manifest,
    make_doc_id,
    save_manifest,
)


class TestComputeHash:
    def test_consistent_hash(self, sample_file: Path):
        h1 = compute_hash(sample_file)
        h2 = compute_hash(sample_file)
        assert h1 == h2

    def test_hash_starts_with_sha256(self, sample_file: Path):
        h = compute_hash(sample_file)
        assert h.startswith("sha256:")

    def test_different_content_different_hash(self, tmp_path: Path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("content A", encoding="utf-8")
        f2.write_text("content B", encoding="utf-8")
        assert compute_hash(f1) != compute_hash(f2)

    def test_nonexistent_file_raises_error(self, tmp_path: Path):
        with pytest.raises(ManifestError, match="Failed to hash"):
            compute_hash(tmp_path / "nonexistent.txt")


class TestManifestCRUD:
    def test_empty_manifest(self):
        m = Manifest()
        assert len(m.documents) == 0
        assert m.schema_version == "1"

    def test_add_document(self):
        m = Manifest()
        entry = DocumentEntry(
            id="ds_stm32f407",
            path="docs/STM32F407.pdf",
            doc_type="datasheet",
            hash="sha256:abc123",
            added="2026-02-27T10:00:00Z",
            chunks=100,
            chip="STM32F407",
        )
        m.add_document(entry)
        assert len(m.documents) == 1
        assert m.documents[0].id == "ds_stm32f407"

    def test_add_document_replaces_existing(self):
        m = Manifest()
        entry1 = DocumentEntry(
            id="test",
            path="a.pdf",
            doc_type="datasheet",
            hash="sha256:old",
            added="2026-01-01T00:00:00Z",
        )
        entry2 = DocumentEntry(
            id="test",
            path="a.pdf",
            doc_type="datasheet",
            hash="sha256:new",
            added="2026-02-01T00:00:00Z",
        )
        m.add_document(entry1)
        m.add_document(entry2)
        assert len(m.documents) == 1
        assert m.documents[0].hash == "sha256:new"

    def test_remove_document(self):
        m = Manifest()
        entry = DocumentEntry(
            id="test",
            path="a.pdf",
            doc_type="datasheet",
            hash="sha256:abc",
            added="2026-01-01T00:00:00Z",
        )
        m.add_document(entry)
        assert m.remove_document("test") is True
        assert len(m.documents) == 0

    def test_remove_nonexistent_returns_false(self):
        m = Manifest()
        assert m.remove_document("nonexistent") is False

    def test_get_document(self):
        m = Manifest()
        entry = DocumentEntry(
            id="test",
            path="a.pdf",
            doc_type="datasheet",
            hash="sha256:abc",
            added="2026-01-01T00:00:00Z",
            chip="STM32F407",
        )
        m.add_document(entry)
        result = m.get_document("test")
        assert result is not None
        assert result.chip == "STM32F407"

    def test_get_nonexistent_returns_none(self):
        m = Manifest()
        assert m.get_document("nonexistent") is None

    def test_is_changed_new_document(self):
        m = Manifest()
        assert m.is_changed("new_doc", "sha256:abc") is True

    def test_is_changed_same_hash(self):
        m = Manifest()
        entry = DocumentEntry(
            id="test",
            path="a.pdf",
            doc_type="datasheet",
            hash="sha256:abc",
            added="2026-01-01T00:00:00Z",
        )
        m.add_document(entry)
        assert m.is_changed("test", "sha256:abc") is False

    def test_is_changed_different_hash(self):
        m = Manifest()
        entry = DocumentEntry(
            id="test",
            path="a.pdf",
            doc_type="datasheet",
            hash="sha256:abc",
            added="2026-01-01T00:00:00Z",
        )
        m.add_document(entry)
        assert m.is_changed("test", "sha256:xyz") is True


class TestManifestRoundTrip:
    def test_save_and_load_empty(self, tmp_path: Path):
        path = tmp_path / "manifest.json"
        m = Manifest()
        save_manifest(m, path)
        loaded = load_manifest(path)
        assert len(loaded.documents) == 0
        assert loaded.schema_version == "1"

    def test_save_and_load_with_documents(self, tmp_path: Path):
        path = tmp_path / "manifest.json"
        m = Manifest()
        m.add_document(
            DocumentEntry(
                id="ds_stm32f407",
                path="docs/STM32F407.pdf",
                doc_type="datasheet",
                hash="sha256:abc123",
                added="2026-02-27T10:00:00Z",
                chunks=847,
                chip="STM32F407",
            )
        )
        m.last_compiled = "2026-02-27T10:30:00Z"

        save_manifest(m, path)
        loaded = load_manifest(path)

        assert len(loaded.documents) == 1
        doc = loaded.documents[0]
        assert doc.id == "ds_stm32f407"
        assert doc.doc_type == "datasheet"
        assert doc.hash == "sha256:abc123"
        assert doc.chunks == 847
        assert doc.chip == "STM32F407"
        assert loaded.last_compiled == "2026-02-27T10:30:00Z"

    def test_load_nonexistent_raises_error(self, tmp_path: Path):
        with pytest.raises(ManifestError, match="not found"):
            load_manifest(tmp_path / "nonexistent.json")

    def test_load_invalid_json_raises_error(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("{invalid json", encoding="utf-8")
        with pytest.raises(ManifestError):
            load_manifest(path)

    def test_load_missing_required_fields_raises_error(self, tmp_path: Path):
        path = tmp_path / "bad_entry.json"
        path.write_text(
            '{"schema_version": "1", "documents": [{"id": "x"}], "last_compiled": ""}',
            encoding="utf-8",
        )
        with pytest.raises(ManifestError, match="missing required fields"):
            load_manifest(path)


class TestMakeDocId:
    def test_includes_extension(self):
        assert make_doc_id(Path("STM32F407.svd")) == "stm32f407_svd"

    def test_pdf_extension(self):
        assert make_doc_id(Path("STM32F407.pdf")) == "stm32f407_pdf"

    def test_no_collision_between_types(self):
        """SVD and PDF of same name produce different IDs."""
        svd_id = make_doc_id(Path("STM32F407.svd"))
        pdf_id = make_doc_id(Path("STM32F407.pdf"))
        assert svd_id != pdf_id

    def test_spaces_replaced(self):
        assert make_doc_id(Path("STM32 F407 datasheet.pdf")) == "stm32_f407_datasheet_pdf"

    def test_hyphens_replaced(self):
        assert make_doc_id(Path("reference-manual-rm0090.pdf")) == "reference_manual_rm0090_pdf"

    def test_no_extension(self):
        assert make_doc_id(Path("README")) == "readme"
