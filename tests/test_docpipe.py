from pathlib import Path

import fitz
import pytest

from tools.docpipe import USAGE, chunk, extract_pdf, to_markdown


def test_usage_documents_directory_mode() -> None:
    assert "<pdf-or-markdown-path-or-directory>" in USAGE
    assert "*.pdf" in USAGE


def test_extract_pdf_preserves_repeated_body_lines_and_numeric_cells(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "repeated-content.pdf"
    document = fitz.open()
    for page_number in range(1, 4):
        page = document.new_page()
        page.insert_text((72, 36), "OFFICIAL DOCUMENT HEADER")
        page.insert_text((72, 72), f"Page introduction {page_number}")
        page.insert_text((72, 120), "Repeated operative legal provision")
        page.insert_text((72, 144), "729")
        page.insert_text((72, 760), f"Page conclusion {page_number}")
        page.insert_text((72, 806), str(page_number))
    document.save(pdf_path)
    document.close()

    extracted = extract_pdf(str(pdf_path))

    assert "OFFICIAL DOCUMENT HEADER" not in extracted
    assert extracted.count("Repeated operative legal provision") == 3
    assert extracted.count("729") == 3
    assert not any(line in {"1", "2", "3"} for line in extracted.splitlines())


def test_to_markdown_preserves_ambiguous_hard_hyphen_at_line_break() -> None:
    mode, markdown = to_markdown("Член\n17\nнаучноистражу-\nвачки")

    assert mode == "member"
    assert markdown == "# Член 17\n\nнаучноистражу- вачки"


def test_to_markdown_removes_explicit_soft_hyphen() -> None:
    mode, markdown = to_markdown("Член 17\nнаучноистражу\u00ad\nвачки")

    assert mode == "member"
    assert markdown == "# Член 17\n\nнаучноистражувачки"


@pytest.mark.parametrize("article", ["3-а", "16 А", "42 A", "4.1"])
def test_chunk_preserves_supported_article_identifier(article: str) -> None:
    chunks = chunk(f"# Член {article}\n\nТекст", "member", len)

    assert chunks == [(f"Член {article}", "Текст")]
