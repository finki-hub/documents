import hashlib
import re
from pathlib import Path

import pytest

from tools import document_metadata

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    ("stem", "digest", "article_count", "source_pages", "adopted", "published"),
    [
        (
            "pravilnik-studii-prv-vtor-ciklus-ukim-417-2019",
            "9852f353799149f039fa7e6c58a76bc79641d9f211eec99728cb091c6e4b5bc2",
            101,
            "1-22",
            "2018-11-27",
            "2019-01-29",
        ),
        (
            "dopolnuvanje-pravilnik-studii-ukim-607-2022",
            "1f4d8a427f53d7d41dc8056defb196d1ce8510dc6c16b662e9370688f4234827",
            2,
            "1-2",
            "2022-03-31",
            "2022-04-06",
        ),
    ],
)
def test_ukim_original_identity_and_complete_article_sequence(
    stem: str,
    digest: str,
    article_count: int,
    source_pages: str,
    adopted: str,
    published: str,
) -> None:
    path = ROOT / "processed" / f"{stem}.md"
    content = path.read_text(encoding="utf-8")
    fields = document_metadata.header_fields(content)
    assert document_metadata.validate_document(path) == "currentness_unresolved"
    assert set(fields) <= set(document_metadata.REQUIRED_FIELDS) | set(
        document_metadata.INGEST_FIELDS
    )
    assert fields["document_date"] == adopted
    assert fields["date_kind"] == "adopted"
    assert fields["published"] == fields["effective_from"] == published
    assert fields["source_pages"] == source_pages
    assert fields["source"] == f"{stem}.pdf"
    assert (
        hashlib.sha256((ROOT / "raw" / fields["source"]).read_bytes()).hexdigest()
        == digest
    )
    assert re.findall(r"^# Член (\d+)$", content, re.MULTILINE) == [
        str(number) for number in range(1, article_count + 1)
    ]
    assert "\ufffd" not in content


def test_base_retains_priority_transition_and_repeat_without_consolidation() -> None:
    content = (
        ROOT / "processed/pravilnik-studii-prv-vtor-ciklus-ukim-417-2019.md"
    ).read_text(encoding="utf-8")
    assert "Во случај на спротивност, се применува овој Правилник." in content
    assert "доколку се поповолни за нив." in content
    assert "во период од најмногу четири месеци од полагањето." in content
    assert "најмалку 60 %" in content
    assert "вонредна, кризна или воена" not in content
    assert "Проф. д-р Никола Јанкуловски, с.р." in content
    assert re.findall(r"<!-- PDF page (\d+);", content) == [
        str(number) for number in range(1, 23)
    ]


def test_amendment_contains_only_the_study_rule_act() -> None:
    content = (
        ROOT / "processed/dopolnuvanje-pravilnik-studii-ukim-607-2022.md"
    ).read_text(encoding="utf-8")
    assert "по став 3 се додава нов став 4" in content
    assert "вонредна, кризна или воена состојба" in content
    assert "помалку од 60 %" in content
    assert "Проф. д-р Анета Баракоска, с.р." in content
    assert "Поликлиника" not in content
    assert "Елена Шукарова" not in content
    assert "Наташа Матева" not in content
