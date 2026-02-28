"""Generate sample.pdf test fixture for PdfParser tests.

Creates a 2-page PDF simulating a hardware datasheet with:
- Title page: large heading, body text
- Register table with bordered cells
- Electrical characteristics table
- Multiple heading levels (different font sizes)
- Page headers ("TestVendor — TESTCHIP") and footers ("Page N of 2")

Run: python tests/fixtures/generate_pdf.py
"""

from __future__ import annotations

from pathlib import Path

import pymupdf


def _draw_table(
    page: pymupdf.Page,
    x0: float,
    y_start: float,
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[float],
    *,
    fontsize: float = 9,
) -> float:
    """Draw a bordered table and return the Y position after the table."""
    row_height = 16
    y = y_start

    # Header row
    x = x0
    for i, header in enumerate(headers):
        rect = pymupdf.Rect(x, y, x + col_widths[i], y + row_height)
        page.draw_rect(rect, color=(0, 0, 0), width=0.5)
        page.insert_text(
            pymupdf.Point(x + 3, y + row_height - 4),
            header,
            fontsize=fontsize,
            fontname="hebo",
        )
        x += col_widths[i]
    y += row_height

    # Data rows
    for row in rows:
        x = x0
        for i, cell in enumerate(row):
            rect = pymupdf.Rect(x, y, x + col_widths[i], y + row_height)
            page.draw_rect(rect, color=(0, 0, 0), width=0.5)
            page.insert_text(
                pymupdf.Point(x + 3, y + row_height - 4),
                cell,
                fontsize=fontsize,
                fontname="helv",
            )
            x += col_widths[i]
        y += row_height

    return y


def generate_sample_pdf(output_path: Path) -> None:
    """Generate a 2-page sample hardware datasheet PDF."""
    doc = pymupdf.open()

    # =========== Page 1 ===========
    page1 = doc.new_page(width=595, height=842)  # A4

    # Header (should be stripped by parser)
    page1.insert_text(
        pymupdf.Point(50, 30),
        "TestVendor — TESTCHIP",
        fontsize=8,
        fontname="helv",
    )

    # Title — large bold heading (h1)
    page1.insert_text(
        pymupdf.Point(50, 80),
        "TESTCHIP Datasheet",
        fontsize=24,
        fontname="hebo",
    )

    # Subtitle text
    page1.insert_text(
        pymupdf.Point(50, 110),
        "32-bit ARM Cortex-M4 Microcontroller",
        fontsize=12,
        fontname="helv",
    )

    # Section heading — h2
    page1.insert_text(
        pymupdf.Point(50, 160),
        "1. SPI Peripheral",
        fontsize=18,
        fontname="hebo",
    )

    # Subsection heading — h3
    page1.insert_text(
        pymupdf.Point(50, 195),
        "1.1 Register Map",
        fontsize=14,
        fontname="hebo",
    )

    # Body paragraph
    page1.insert_text(
        pymupdf.Point(50, 225),
        "The SPI peripheral supports full-duplex synchronous serial communication.",
        fontsize=10,
        fontname="helv",
    )
    page1.insert_text(
        pymupdf.Point(50, 240),
        "It provides master and slave modes with configurable clock polarity.",
        fontsize=10,
        fontname="helv",
    )

    # Register table
    reg_headers = ["Register", "Offset", "Size", "Access", "Description"]
    reg_rows = [
        ["CR1", "0x00", "32", "RW", "Control register 1"],
        ["CR2", "0x04", "32", "RW", "Control register 2"],
        ["SR", "0x08", "32", "RO", "Status register"],
        ["DR", "0x0C", "32", "RW", "Data register"],
    ]
    reg_widths = [80, 60, 50, 55, 200]
    table_y_end = _draw_table(page1, 50, 265, reg_headers, reg_rows, reg_widths)

    # Body text after table
    page1.insert_text(
        pymupdf.Point(50, table_y_end + 20),
        "The CR1 register controls the SPI clock phase and polarity settings.",
        fontsize=10,
        fontname="helv",
    )

    # Footer (should be stripped by parser)
    page1.insert_text(
        pymupdf.Point(250, 820),
        "Page 1 of 2",
        fontsize=8,
        fontname="helv",
    )

    # =========== Page 2 ===========
    page2 = doc.new_page(width=595, height=842)

    # Header
    page2.insert_text(
        pymupdf.Point(50, 30),
        "TestVendor — TESTCHIP",
        fontsize=8,
        fontname="helv",
    )

    # Section heading — h2
    page2.insert_text(
        pymupdf.Point(50, 80),
        "2. GPIO Peripheral",
        fontsize=18,
        fontname="hebo",
    )

    # Body text
    page2.insert_text(
        pymupdf.Point(50, 115),
        "Each GPIO port provides 16 individually configurable I/O pins.",
        fontsize=10,
        fontname="helv",
    )

    # Subsection heading — h3
    page2.insert_text(
        pymupdf.Point(50, 150),
        "2.1 Electrical Characteristics",
        fontsize=14,
        fontname="hebo",
    )

    # Electrical table
    elec_headers = ["Parameter", "Min", "Typ", "Max", "Unit"]
    elec_rows = [
        ["VIH", "2.0", "", "3.3", "V"],
        ["VIL", "0", "", "0.8", "V"],
        ["IOH", "", "8", "20", "mA"],
    ]
    elec_widths = [100, 60, 60, 60, 50]
    elec_y_end = _draw_table(page2, 50, 175, elec_headers, elec_rows, elec_widths)

    # Body text after table
    page2.insert_text(
        pymupdf.Point(50, elec_y_end + 20),
        "All GPIO pins are 5V tolerant when configured as inputs.",
        fontsize=10,
        fontname="helv",
    )

    # Footer
    page2.insert_text(
        pymupdf.Point(250, 820),
        "Page 2 of 2",
        fontsize=8,
        fontname="helv",
    )

    # Save with metadata
    doc.set_metadata(
        {
            "title": "TESTCHIP Datasheet",
            "author": "TestVendor",
            "subject": "Hardware Datasheet",
        }
    )
    doc.save(str(output_path))
    doc.close()


if __name__ == "__main__":
    out = Path(__file__).parent / "sample.pdf"
    generate_sample_pdf(out)
    print(f"Generated: {out}")
