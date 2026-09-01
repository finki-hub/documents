from pathlib import Path

import pytest

from tools import preprocess


def _metadata_header(**overrides: str) -> str:
    fields = {
        "title": "Document",
        "source": "document.pdf",
        "authority_url": "https://finki.ukim.mk/official/document.pdf",
        "document_date": "2024-05-16",
        "date_kind": "adopted",
        "date_precision": "day",
        "date_source": "document_text",
        "date_confidence": "high",
        "current_status": "current",
        "last_verified": "2026-09-01",
    }
    fields.update(overrides)
    values = " | ".join(f"{name}: {value}" for name, value in fields.items())
    return f"<!-- {values} | TIER A extraction -->"


def test_audit_rejects_missing_canonical_metadata(tmp_path: Path) -> None:
    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    (out_dir / "document.md").write_text(
        "<!-- title: Document | source: document.pdf | TIER A extraction -->\n\nText",
        encoding="utf-8",
    )

    with pytest.raises(
        preprocess.MetadataError, match="document.md: missing document_date"
    ):
        preprocess.audit_corpus(out_dir)


def test_audit_rejects_missing_authority_url(tmp_path: Path) -> None:
    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    header = _metadata_header().replace(
        " | authority_url: https://finki.ukim.mk/official/document.pdf",
        "",
    )
    (out_dir / "document.md").write_text(header, encoding="utf-8")

    with pytest.raises(
        preprocess.MetadataError, match="document.md: missing authority_url"
    ):
        preprocess.audit_corpus(out_dir)


@pytest.mark.parametrize(
    ("authority_url", "message"),
    [
        ("", "empty authority_url"),
        ("http://finki.ukim.mk/document.pdf", "invalid authority_url"),
        ("https://example.com/document.pdf", "unofficial authority_url"),
        (r"https://evil.example\@finki.ukim.mk/document.pdf", "invalid authority_url"),
        ("https://user@finki.ukim.mk/document.pdf", "invalid authority_url"),
        ("https://finki.ukim.mk:8443/document.pdf", "invalid authority_url"),
        ("https://finki.ukim.mk:notaport/document.pdf", "invalid authority_url"),
        ("https://finki.ukim.mk:99999/document.pdf", "invalid authority_url"),
        ("https://finki.ukim.mk:/document.pdf", "invalid authority_url"),
        ("https://finki.ukim.mk/path with space", "invalid authority_url"),
        ("https://ﬁnki.ukim.mk/document.pdf", "invalid authority_url"),
        ("https://finKi.ukim.mk/document.pdf", "invalid authority_url"),
        ("https://ſlvesnik.com.mk/document.pdf", "invalid authority_url"),
        ("https://finki.ukim.mk/pa\u0080th", "invalid authority_url"),
        ("https://finki.ukim.mk/abc\u202etxt.exe", "invalid authority_url"),
        ("https://finki.ukim.mk/document.pdf?token=secret", "invalid authority_url"),
        ("https://finki.ukim.mk/document.pdf#section", "invalid authority_url"),
        ("https://attacker.finki.ukim.mk/document.pdf", "unofficial authority_url"),
        ("https://finki.ukim.mk.evil.example/document.pdf", "unofficial authority_url"),
    ],
)
def test_audit_rejects_invalid_authority_url(
    tmp_path: Path,
    authority_url: str,
    message: str,
) -> None:
    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    (out_dir / "document.md").write_text(
        _metadata_header(authority_url=authority_url),
        encoding="utf-8",
    )

    with pytest.raises(preprocess.MetadataError, match=message):
        preprocess.audit_corpus(out_dir)


@pytest.mark.parametrize(
    "authority_url",
    [
        "https://finki.ukim.mk/document.pdf",
        "https://ukim.edu.mk/document.pdf",
        "https://portal.mdt.gov.mk/document.pdf",
        "https://azlp.mk/document.pdf",
        "https://slvesnik.com.mk/",
    ],
)
def test_audit_accepts_approved_official_authority_hosts(
    tmp_path: Path,
    authority_url: str,
) -> None:
    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    (out_dir / "document.md").write_text(
        _metadata_header(authority_url=authority_url),
        encoding="utf-8",
    )

    assert preprocess.audit_corpus(out_dir) == {"current": 1}


def test_audit_accepts_unresolved_and_non_calendar_dates(tmp_path: Path) -> None:
    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    (out_dir / "unresolved.md").write_text(
        _metadata_header(
            title="Unresolved",
            source="unresolved.pdf",
            document_date="unresolved",
            date_kind="unresolved",
            date_precision="none",
            date_source="unresolved",
            date_confidence="none",
            current_status="authority_unresolved",
        ),
        encoding="utf-8",
    )
    (out_dir / "gazette.md").write_text(
        _metadata_header(
            title="Gazette",
            source="gazette.pdf",
            document_date="111/2026",
            date_kind="published",
            date_precision="gazette_issue",
            date_source="official_gazette",
            current_status="presumed_current",
        ),
        encoding="utf-8",
    )

    assert preprocess.audit_corpus(out_dir) == {
        "authority_unresolved": 1,
        "presumed_current": 1,
    }


def test_audit_does_not_read_metadata_from_document_body(tmp_path: Path) -> None:
    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    body_fields = _metadata_header().removeprefix("<!-- ").removesuffix(" -->")
    (out_dir / "document.md").write_text(
        f"<!-- title: Document | source: document.pdf | TIER A extraction -->\n\n| {body_fields}",
        encoding="utf-8",
    )

    with pytest.raises(
        preprocess.MetadataError, match="document.md: missing document_date"
    ):
        preprocess.audit_corpus(out_dir)


def test_audit_rejects_duplicate_header_fields(tmp_path: Path) -> None:
    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    header = _metadata_header().replace(
        " | TIER A extraction -->",
        " | current_status: historical | TIER A extraction -->",
    )
    (out_dir / "document.md").write_text(header, encoding="utf-8")

    with pytest.raises(
        preprocess.MetadataError, match="document.md: duplicate current_status"
    ):
        preprocess.audit_corpus(out_dir)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"document_date": "2024-99", "date_precision": "month"},
            "invalid document_date",
        ),
        ({"document_date": "20240516"}, "invalid document_date"),
        ({"document_date": "2021-W01-1"}, "invalid document_date"),
        ({"document_date": "0000", "date_precision": "year"}, "invalid document_date"),
        (
            {"document_date": "2023/9999", "date_precision": "academic_year"},
            "invalid document_date",
        ),
        (
            {"document_date": "unresolved", "date_precision": "none"},
            "unresolved metadata",
        ),
        ({"date_kind": "unresolved"}, "resolved metadata"),
        ({"amended_through": "2025-99-99"}, "invalid amended_through"),
        ({"issued": ""}, "invalid issued"),
    ],
)
def test_audit_rejects_invalid_date_metadata(
    tmp_path: Path,
    overrides: dict[str, str],
    message: str,
) -> None:
    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    (out_dir / "document.md").write_text(
        _metadata_header(**overrides),
        encoding="utf-8",
    )

    with pytest.raises(preprocess.MetadataError, match=message):
        preprocess.audit_corpus(out_dir)


@pytest.mark.parametrize("field", ["title", "source"])
def test_audit_rejects_empty_required_metadata(tmp_path: Path, field: str) -> None:
    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    (out_dir / "document.md").write_text(
        _metadata_header(**{field: ""}),
        encoding="utf-8",
    )

    with pytest.raises(preprocess.MetadataError, match=f"document.md: empty {field}"):
        preprocess.audit_corpus(out_dir)


def test_reviewed_corpus_satisfies_canonical_metadata_contract() -> None:
    repo_root = Path(__file__).parents[1]

    statuses = preprocess.audit_corpus(repo_root / "processed", repo_root / "raw")

    assert sum(statuses.values()) == 34
