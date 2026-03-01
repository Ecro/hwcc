"""Tests for the Jinja2 template engine and template rendering."""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from hwcc.compile.context import (
    CompileContext,
    DocumentSummary,
    ErrataSummary,
    PeripheralSummary,
    TargetInfo,
)
from hwcc.compile.templates import TARGET_REGISTRY, TemplateEngine
from hwcc.config import (
    ConventionsConfig,
    HardwareConfig,
    HwccConfig,
    ProjectConfig,
    SoftwareConfig,
)
from hwcc.exceptions import CompileError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> TemplateEngine:
    """TemplateEngine with only built-in templates."""
    return TemplateEngine()


@pytest.fixture
def full_context() -> CompileContext:
    """A CompileContext with all fields populated."""
    return CompileContext(
        project_name="motor-controller",
        project_description="Brushless DC motor controller",
        mcu="STM32F407VGT6",
        mcu_family="STM32F4",
        architecture="Cortex-M4",
        clock_mhz=168,
        flash_kb=1024,
        ram_kb=192,
        rtos="FreeRTOS 10.5.1",
        hal="STM32 HAL v1.27.1",
        language="C",
        build_system="CMake",
        register_access="HAL functions only, no direct register writes",
        error_handling="return HAL_StatusTypeDef",
        naming="snake_case for functions, UPPER_CASE for defines",
        documents=(
            DocumentSummary(
                doc_id="ds_stm32f407",
                title="STM32F407 Datasheet",
                doc_type="datasheet",
                chip="STM32F407",
                chunk_count=847,
            ),
            DocumentSummary(
                doc_id="rm_rm0090",
                title="RM0090 Reference Manual",
                doc_type="reference_manual",
                chip="STM32F407",
                chunk_count=1204,
            ),
        ),
        peripherals=(
            PeripheralSummary(
                name="SPI1",
                description="Serial Peripheral Interface",
                register_count=9,
                chip="STM32F407",
            ),
            PeripheralSummary(
                name="I2C1",
                description="Inter-Integrated Circuit",
                register_count=7,
                chip="STM32F407",
            ),
        ),
        errata=(
            ErrataSummary(
                errata_id="ES0182 §2.1.8",
                title="SPI CRC not reliable in slave mode at frequencies > 18 MHz",
                description="Workaround: disable CRC in slave mode above 18 MHz.",
                affected_peripheral="SPI",
                severity="high",
            ),
        ),
        hwcc_version="0.1.0",
        generated_at="2026-02-28 10:30 UTC",
        mcp_available=True,
        hot_context="# Hardware Context — motor-controller\n\n- MCU: STM32F407VGT6",
    )


@pytest.fixture
def minimal_context() -> CompileContext:
    """A CompileContext with only required/default fields."""
    return CompileContext(
        hwcc_version="0.1.0",
        generated_at="2026-02-28 10:30 UTC",
    )


@pytest.fixture
def peripheral_context() -> CompileContext:
    """A CompileContext for peripheral template rendering."""
    return CompileContext(
        mcu="STM32F407VGT6",
        peripheral_name="SPI1",
        register_map=(
            "| Register | Offset | Description |\n"
            "|----------|--------|-------------|\n"
            "| CR1 | 0x00 | Control register 1 |"
        ),
        peripheral_details="The SPI peripheral supports full-duplex synchronous serial communication.",  # noqa: E501
        errata=(
            ErrataSummary(
                errata_id="ES0182 §2.1.8",
                title="SPI CRC unreliable above 18 MHz in slave mode",
                severity="high",
            ),
        ),
        hwcc_version="0.1.0",
    )


# ---------------------------------------------------------------------------
# TemplateEngine initialization
# ---------------------------------------------------------------------------


class TestTemplateEngineInit:
    def test_loads_builtin_templates(self, engine):
        templates = engine.list_templates()
        assert len(templates) >= 7
        assert "hot_context.md.j2" in templates
        assert "claude.md.j2" in templates
        assert "peripheral.md.j2" in templates

    def test_no_project_root_is_valid(self):
        engine = TemplateEngine()
        assert len(engine.list_templates()) >= 7

    def test_project_root_without_override_dir(self, tmp_path):
        engine = TemplateEngine(project_root=tmp_path)
        # Should still work, just no overrides
        assert len(engine.list_templates()) >= 7

    def test_project_root_with_override_dir(self, tmp_path):
        override_dir = tmp_path / ".rag" / "templates"
        override_dir.mkdir(parents=True)
        (override_dir / "custom.md.j2").write_text("custom template")
        engine = TemplateEngine(project_root=tmp_path)
        templates = engine.list_templates()
        assert "custom.md.j2" in templates


# ---------------------------------------------------------------------------
# Template rendering — hot_context.md.j2
# ---------------------------------------------------------------------------


class TestHotContextTemplate:
    def test_renders_full_context(self, engine, full_context):
        result = engine.render("hot_context.md.j2", full_context)
        assert "motor-controller" in result
        assert "STM32F407VGT6" in result
        assert "Cortex-M4" in result
        assert "168MHz" in result
        assert "1024KB" in result
        assert "192KB" in result
        assert "FreeRTOS" in result
        assert "SPI1" in result
        assert "I2C1" in result
        assert "ES0182" in result
        assert "HAL functions only" in result

    def test_renders_minimal_context(self, engine, minimal_context):
        result = engine.render("hot_context.md.j2", minimal_context)
        # Should not crash, just have minimal content
        assert "Hardware Context" in result
        # Empty sections should be omitted
        assert "Target Hardware" not in result
        assert "Software Stack" not in result
        assert "Indexed Documents" not in result
        assert "Peripherals" not in result
        assert "Errata" not in result

    def test_documents_table(self, engine, full_context):
        result = engine.render("hot_context.md.j2", full_context)
        assert "STM32F407 Datasheet" in result
        assert "datasheet" in result
        assert "847" in result

    def test_errata_severity_tag(self, engine, full_context):
        result = engine.render("hot_context.md.j2", full_context)
        assert "[HIGH]" in result


# ---------------------------------------------------------------------------
# Template rendering — peripheral.md.j2
# ---------------------------------------------------------------------------


class TestPeripheralTemplate:
    def test_renders_peripheral(self, engine, peripheral_context):
        result = engine.render("peripheral.md.j2", peripheral_context)
        assert "SPI1" in result
        assert "STM32F407VGT6" in result
        assert "CR1" in result
        assert "Control register 1" in result
        assert "full-duplex" in result

    def test_errata_in_peripheral(self, engine, peripheral_context):
        result = engine.render("peripheral.md.j2", peripheral_context)
        assert "ES0182" in result
        assert "Known Errata" in result


# ---------------------------------------------------------------------------
# Template rendering — target templates
# ---------------------------------------------------------------------------


class TestTargetTemplates:
    @pytest.mark.parametrize("target", ["claude", "codex", "cursor", "gemini", "copilot"])
    def test_renders_target(self, engine, full_context, target):
        result = engine.render_target(target, full_context)
        assert len(result) > 0

    @pytest.mark.parametrize("target", ["claude", "codex", "cursor", "gemini", "copilot"])
    def test_target_contains_markers(self, engine, full_context, target):
        info = TemplateEngine.get_target_info(target)
        result = engine.render_target(target, full_context)
        assert info.begin_marker in result
        assert info.end_marker in result

    @pytest.mark.parametrize("target", ["claude", "codex", "cursor", "gemini", "copilot"])
    def test_target_contains_version(self, engine, full_context, target):
        result = engine.render_target(target, full_context)
        assert "0.1.0" in result

    def test_claude_contains_mcp_hints(self, engine, full_context):
        result = engine.render_target("claude", full_context)
        assert "hw_search" in result
        assert "hw_registers" in result

    def test_claude_no_mcp_when_unavailable(self, engine, minimal_context):
        result = engine.render_target("claude", minimal_context)
        assert "hw_search" not in result

    @pytest.mark.parametrize("target", ["claude", "codex", "cursor", "gemini", "copilot"])
    def test_target_renders_minimal_context(self, engine, minimal_context, target):
        result = engine.render_target(target, minimal_context)
        # Should render without errors even with minimal data
        assert "BEGIN HWCC CONTEXT" in result
        assert "END HWCC CONTEXT" in result

    def test_cursor_has_mdc_frontmatter(self, engine, full_context):
        result = engine.render_target("cursor", full_context)
        assert "---" in result
        assert "globs:" in result

    def test_codex_contains_hot_context(self, engine, full_context):
        result = engine.render_target("codex", full_context)
        assert full_context.hot_context in result

    def test_each_target_renders_differently(self, engine, full_context):
        """Each target template should produce distinct output."""
        targets = ["claude", "codex", "cursor", "gemini", "copilot"]
        outputs = {t: engine.render_target(t, full_context) for t in targets}
        unique_outputs = set(outputs.values())
        assert len(unique_outputs) == len(outputs), (
            "Some target templates produce identical output"
        )


# ---------------------------------------------------------------------------
# render_target and target registry
# ---------------------------------------------------------------------------


class TestTargetRegistry:
    def test_unknown_target_raises(self, engine, full_context):
        with pytest.raises(CompileError, match="Unknown output target"):
            engine.render_target("unknown_tool", full_context)

    def test_get_target_info_returns_target_info(self):
        info = TemplateEngine.get_target_info("claude")
        assert isinstance(info, TargetInfo)
        assert info.template == "claude.md.j2"
        assert info.output_path == PurePosixPath("CLAUDE.md")

    def test_get_target_info_unknown_raises(self):
        with pytest.raises(CompileError, match="Unknown output target"):
            TemplateEngine.get_target_info("nonexistent")

    def test_supported_targets(self):
        targets = TemplateEngine.supported_targets()
        assert "claude" in targets
        assert "codex" in targets
        assert "cursor" in targets
        assert "gemini" in targets
        assert "copilot" in targets
        assert len(targets) == 5

    def test_all_targets_have_templates(self, engine):
        templates = engine.list_templates()
        for target_info in TARGET_REGISTRY.values():
            assert target_info.template in templates, (
                f"Template {target_info.template} missing for target"
            )


# ---------------------------------------------------------------------------
# User template overrides
# ---------------------------------------------------------------------------


class TestTemplateOverrides:
    def test_override_takes_precedence(self, tmp_path, full_context):
        override_dir = tmp_path / ".rag" / "templates"
        override_dir.mkdir(parents=True)
        (override_dir / "claude.md.j2").write_text(
            "CUSTOM: {{ project_name }} v{{ hwcc_version }}"
        )
        engine = TemplateEngine(project_root=tmp_path)
        result = engine.render_target("claude", full_context)
        assert result == "CUSTOM: motor-controller v0.1.0"

    def test_is_overridden_true(self, tmp_path):
        override_dir = tmp_path / ".rag" / "templates"
        override_dir.mkdir(parents=True)
        (override_dir / "claude.md.j2").write_text("custom")
        engine = TemplateEngine(project_root=tmp_path)
        assert engine.is_overridden("claude.md.j2") is True

    def test_is_overridden_false(self, tmp_path):
        override_dir = tmp_path / ".rag" / "templates"
        override_dir.mkdir(parents=True)
        engine = TemplateEngine(project_root=tmp_path)
        assert engine.is_overridden("claude.md.j2") is False

    def test_is_overridden_no_project_root(self, engine):
        assert engine.is_overridden("claude.md.j2") is False

    def test_non_overridden_templates_still_work(self, tmp_path, full_context):
        override_dir = tmp_path / ".rag" / "templates"
        override_dir.mkdir(parents=True)
        (override_dir / "claude.md.j2").write_text("CUSTOM")
        engine = TemplateEngine(project_root=tmp_path)
        # Non-overridden templates should fall through to built-in
        result = engine.render("hot_context.md.j2", full_context)
        assert "Hardware Context" in result


# ---------------------------------------------------------------------------
# CompileContext
# ---------------------------------------------------------------------------


class TestCompileContext:
    def test_from_config(self):
        config = HwccConfig(
            project=ProjectConfig(name="test-project"),
            hardware=HardwareConfig(mcu="STM32F407", architecture="Cortex-M4", clock_mhz=168),
            software=SoftwareConfig(rtos="FreeRTOS"),
            conventions=ConventionsConfig(register_access="HAL only"),
        )

        ctx = CompileContext.from_config(config)

        assert ctx.project_name == "test-project"
        assert ctx.mcu == "STM32F407"
        assert ctx.architecture == "Cortex-M4"
        assert ctx.clock_mhz == 168
        assert ctx.rtos == "FreeRTOS"
        assert ctx.register_access == "HAL only"
        assert ctx.hwcc_version == "0.1.0"
        assert ctx.generated_at  # Should have a timestamp

    def test_from_config_bsp_fields(self):
        config = HwccConfig(
            hardware=HardwareConfig(
                soc="i.MX8M Plus",
                soc_family="i.MX8",
                board="Custom Board",
            ),
            software=SoftwareConfig(
                kernel="linux-6.6",
                bootloader="U-Boot 2024.01",
                distro="Yocto kirkstone",
            ),
        )
        ctx = CompileContext.from_config(config)
        assert ctx.soc == "i.MX8M Plus"
        assert ctx.soc_family == "i.MX8"
        assert ctx.board == "Custom Board"
        assert ctx.kernel == "linux-6.6"
        assert ctx.bootloader == "U-Boot 2024.01"
        assert ctx.distro == "Yocto kirkstone"

    def test_from_config_defaults(self):
        ctx = CompileContext.from_config(HwccConfig())
        assert ctx.project_name == ""
        assert ctx.mcu == ""
        assert ctx.soc == ""
        assert ctx.kernel == ""
        assert ctx.documents == ()
        assert ctx.peripherals == ()
        assert ctx.errata == ()

    def test_frozen(self):
        ctx = CompileContext()
        with pytest.raises(AttributeError):
            ctx.mcu = "should fail"  # type: ignore[misc]

    def test_document_summary_frozen(self):
        doc = DocumentSummary(doc_id="test", title="Test", doc_type="datasheet")
        with pytest.raises(AttributeError):
            doc.title = "should fail"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_missing_template_raises(self, engine, full_context):
        with pytest.raises(CompileError, match="Template not found"):
            engine.render("nonexistent.j2", full_context)

    def test_broken_template_raises(self, tmp_path, full_context):
        override_dir = tmp_path / ".rag" / "templates"
        override_dir.mkdir(parents=True)
        (override_dir / "broken.md.j2").write_text("{{ totally_undefined_variable }}")
        engine = TemplateEngine(project_root=tmp_path)
        with pytest.raises(CompileError, match="Failed to render"):
            engine.render("broken.md.j2", full_context)

    @pytest.mark.parametrize("target", ["claude", "codex", "cursor", "gemini", "copilot"])
    def test_target_markers_in_correct_order(self, engine, full_context, target):
        info = TemplateEngine.get_target_info(target)
        result = engine.render_target(target, full_context)
        begin_pos = result.index(info.begin_marker)
        end_pos = result.index(info.end_marker)
        assert begin_pos < end_pos
