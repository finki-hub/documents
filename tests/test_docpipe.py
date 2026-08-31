from pathlib import Path

import fitz

from tools.docpipe import chunk, extract_pdf, to_markdown


def test_extract_pdf_preserves_repeated_body_lines_and_numeric_cells(tmp_path: Path) -> None:
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


def test_to_markdown_normalizes_split_article_heading_and_wrapped_word() -> None:
    mode, markdown = to_markdown("Член\n17\nнаучноистражу-\nвачки")

    assert mode == "member"
    assert markdown == "# Член 17\n\nнаучноистражувачки"


def test_to_markdown_dehyphenates_heading_mode_without_flattening_lines() -> None:
    mode, markdown = to_markdown("Наслов\nнаучно-\nистражувачки\nСледен ред")

    assert mode == "heading"
    assert markdown == "Наслов\nнаучноистражувачки\nСледен ред"


def test_chunk_preserves_suffixed_article_identifier() -> None:
    chunks = chunk("# Член 3-а\n\nТекст", "member", len)

    assert chunks == [("Член 3-а", "Текст")]
