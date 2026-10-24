"""Generate the fictional Nova Systems sample documents into test-data/.

All content is fictional demonstration data and does not describe any real company or product.
Run:  python -m app.scripts.make_test_data
"""
from pathlib import Path

import pymupdf

TEST_DATA = Path(__file__).resolve().parents[3] / "test-data"

DISCLAIMER = "Fictional demonstration data for Nova Systems. Not a real company or product."

PDF_PAGES = [
    (
        "Nova Systems - Nova Laptop Product Specification\n\n"
        f"{DISCLAIMER}\n\n"
        "Document version 3.2. Effective from the 2026 autumn release.\n\n"
        "1. Product overview\n"
        "Product name: Nova. The exact approved product name is Nova. Do not abbreviate it or add a prefix.\n"
        "Nova is a 14 inch lightweight laptop for everyday professional work."
    ),
    (
        "2. Battery and power\n\n"
        "Battery life: up to 18 hours under specified test conditions.\n"
        "Specified test conditions: 1080p local video playback, 50 percent screen brightness, "
        "wireless networking enabled, and factory default power settings.\n"
        "Real-world battery life varies with usage and settings.\n\n"
        "Charging: 65 W USB-C adapter included in the box."
    ),
    (
        "3. Performance\n\n"
        "Performance improvement: 25 percent faster multi-core processing than the previous generation "
        "Nova, under the approved comparison methodology.\n"
        "The approved comparison methodology is Benchmark Method NS-BM-4, run on production units with "
        "identical memory and storage.\n\n"
        "4. Warranty\n"
        "Limited warranty: 2 years from the date of purchase. See the warranty terms for exclusions."
    ),
]

TERMINOLOGY_TXT = f"""Nova Systems Terminology Guide

{DISCLAIMER}

Approved terms
Always write the product name as Nova, with a capital N and no article before it.
Say lightweight laptop, not ultrabook, when describing the product category.

Terms to avoid
Do not use the words fastest, best ever or unbeatable in any claim about Nova.
Do not describe battery life without the phrase under specified test conditions.

Contact
Questions about this guide go to the Nova brand team.
"""

SPEC_CSV = """Specification,Value,Unit,Notes
Weight,1.24,kg,Measured without charger
Display size,14,inch,Diagonal
Memory,16,GB,Soldered
Storage,512,GB,NVMe SSD
Charger,65,W,USB-C
"""


def build_pdf(path: Path) -> None:
    doc = pymupdf.open()
    for text in PDF_PAGES:
        page = doc.new_page()
        rc = page.insert_textbox(pymupdf.Rect(54, 54, 540, 780), text, fontsize=11, fontname="helv")
        assert rc >= 0, "text overflowed the page"
    doc.set_metadata({"title": "Nova Product Specification (fictional)", "author": "Nova Systems (fictional)"})
    doc.save(path)
    doc.close()


def main() -> None:
    TEST_DATA.mkdir(parents=True, exist_ok=True)
    build_pdf(TEST_DATA / "nova_product_specification.pdf")
    (TEST_DATA / "nova_terminology_guide.txt").write_text(TERMINOLOGY_TXT, encoding="utf-8")
    (TEST_DATA / "nova_spec_table.csv").write_text(SPEC_CSV, encoding="utf-8")
    # Deliberately bad samples for manual and automated testing of failure handling.
    (TEST_DATA / "corrupt.pdf").write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\ntruncated garbage without xref")
    (TEST_DATA / "unsupported.exe").write_bytes(b"MZ\x90\x00\x03\x00\x00\x00 not a real executable")
    (TEST_DATA / "README.md").write_text(
        "# Test data\n\nFictional Nova Systems samples used by the seed script, tests and manual checks.\n\n"
        "- nova_product_specification.pdf: 3-page PDF with battery, performance and warranty statements\n"
        "- nova_terminology_guide.txt: plain-text terminology guide\n"
        "- nova_spec_table.csv: specification table with headers\n"
        "- corrupt.pdf: has a PDF header but cannot be parsed (expects processing_status=failed)\n"
        "- unsupported.exe: rejected at upload (unsupported type)\n\n"
        "Regenerate with `python -m app.scripts.make_test_data` from the backend directory.\n",
        encoding="utf-8",
    )
    print(f"Wrote sample files to {TEST_DATA}")


if __name__ == "__main__":
    main()
