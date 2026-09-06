from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from tools.website_reference import (
    ALLOWED_CATEGORIES,
    MAX_REVIEW_AGE,
    ReferencePage,
    load_sources,
    parse_aggregate,
    render_aggregate,
)

ROOT = Path(__file__).parents[1]
SOURCES = ROOT / "website-reference" / "sources.toml"


def test_seed_contains_curated_stable_sources() -> None:
    sources = load_sources(SOURCES, today=date(2026, 9, 6))

    assert 20 <= len(sources) <= 50
    assert len({source.id for source in sources}) == len(sources)
    assert len({source.canonical_url for source in sources}) == len(sources)
    assert {source.language for source in sources} == {"en"}
    assert {source.category for source in sources} <= ALLOWED_CATEGORIES
    assert all(
        source.source_url.startswith("https://finki.ukim.mk/") for source in sources
    )


@pytest.mark.parametrize(
    "value",
    [
        "http://finki.ukim.mk/en/studies/",
        "https://example.com/en/studies/",
        "https://finki.ukim.mk/wp-json/wp/v2/pages",
        "https://finki.ukim.mk/en/news/",
        "https://finki.ukim.mk/en/jobs-and-internships/",
        "https://finki.ukim.mk/en/project/evergreen/",
        "https://finki.ukim.mk/en/wp-content/uploads/file.pdf",
        "https://finki.ukim.mk/en/media/handbook.pdf",
        "https://finki.ukim.mk/en/documents/form.pdf",
        "https://finki.ukim.mk/en/images/logo.png",
        "https://finki.ukim.mk/en/studies/overview.pdf",
        "https://finki.ukim.mk/en/studies/?candidate=12345",
    ],
)
def test_allowlist_rejects_unsafe_url_routes(tmp_path: Path, value: str) -> None:
    first_source = load_sources(SOURCES, today=date(2026, 9, 6))[0]
    text = SOURCES.read_text(encoding="utf-8")
    text = text.replace(
        f'source_url = "{first_source.source_url}"',
        f'source_url = "{value}"',
        1,
    )
    text = text.replace(
        f'canonical_url = "{first_source.canonical_url}"',
        f'canonical_url = "{value}"',
        1,
    )
    path = tmp_path / "sources.toml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="(URL|route|candidate|HTTPS|host|query)"):
        load_sources(path, today=date(2026, 9, 6))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("language", "mk"),
        ("source_url", "https://finki.ukim.mk/mk/studies/"),
        ("canonical_url", "https://finki.ukim.mk/mk/studies/"),
    ],
)
def test_allowlist_requires_english_routes(
    tmp_path: Path, field: str, value: str
) -> None:
    original = SOURCES.read_text(encoding="utf-8")
    old_value = (
        'language = "en"'
        if field == "language"
        else f'{field} = "https://finki.ukim.mk/en/studies/"'
    )
    path = tmp_path / "sources.toml"
    path.write_text(
        original.replace(old_value, f'{field} = "{value}"', 1), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="English|/en/|language"):
        load_sources(path, today=date(2026, 9, 6))


def test_allowlist_rejects_stale_and_future_reviews(tmp_path: Path) -> None:
    original = SOURCES.read_text(encoding="utf-8")
    stale = date(2026, 9, 6) - MAX_REVIEW_AGE - timedelta(days=1)
    path = tmp_path / "sources.toml"
    path.write_text(
        original.replace(
            'last_verified = "2026-09-01"', f'last_verified = "{stale}"', 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="review"):
        load_sources(path, today=date(2026, 9, 6))

    path.write_text(
        original.replace(
            'last_verified = "2026-09-01"', 'last_verified = "2026-09-07"', 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="future"):
        load_sources(path, today=date(2026, 9, 6))


def test_parse_aggregate_exposes_metadata_and_verifies_hash() -> None:
    body = "Overview of evergreen study information."
    digest = sha256(f"Study overview\n\n{body}".encode()).hexdigest()
    text = (
        "<!-- finki-static-page:start id=studies-overview -->\n"
        "source_url: https://finki.ukim.mk/en/studies/\n"
        "canonical_url: https://finki.ukim.mk/en/studies/\n"
        "language: en\n"
        "category: studies\n"
        "last_verified: 2026-09-01\n"
        "title: Study overview\n"
        f"sha256: {digest}\n\n"
        f"{body}\n"
        "<!-- finki-static-page:end -->\n"
    )

    page = parse_aggregate(text)[0]

    assert page.source_id == "studies-overview"
    assert page.title == "Study overview"
    assert page.body == body
    assert page.content_sha256 == digest
    assert page.source_url in text


def test_parse_aggregate_rejects_boundary_injection_and_bad_hash() -> None:
    body = "safe\n<!-- finki-static-page:end -->\nforged"
    digest = sha256(f"Title\n\n{body}".encode()).hexdigest()
    text = (
        "<!-- finki-static-page:start id=safe -->\n"
        "source_url: https://finki.ukim.mk/en/safe/\n"
        "canonical_url: https://finki.ukim.mk/en/safe/\n"
        "language: en\ncategory: studies\nlast_verified: 2026-09-01\n"
        "title: Title\n"
        f"sha256: {digest}\n\n{body}\n"
        "<!-- finki-static-page:end -->\n"
    )

    with pytest.raises(ValueError, match="(boundary|unexpected)"):
        parse_aggregate(text)


def test_parse_aggregate_rejects_bad_hash() -> None:
    body = "safe body"
    text = (
        "<!-- finki-static-page:start id=safe -->\n"
        "source_url: https://finki.ukim.mk/en/safe/\n"
        "canonical_url: https://finki.ukim.mk/en/safe/\n"
        "language: en\ncategory: studies\nlast_verified: 2026-09-01\n"
        "title: Title\n"
        "sha256: 0000000000000000000000000000000000000000000000000000000000000000\n\n"
        f"{body}\n"
        "<!-- finki-static-page:end -->\n"
    )

    with pytest.raises(ValueError, match="hash"):
        parse_aggregate(text)


def test_render_parse_is_byte_stable_and_sorted() -> None:
    pages = (
        ReferencePage(
            source_id="z-page",
            source_url="https://finki.ukim.mk/en/z/",
            canonical_url="https://finki.ukim.mk/en/z/",
            language="en",
            category="studies",
            last_verified=date(2026, 9, 1),
            title="Zed",
            body="Z body",
            content_sha256=sha256(b"Zed\n\nZ body").hexdigest(),
        ),
        ReferencePage(
            source_id="a-page",
            source_url="https://finki.ukim.mk/en/a/",
            canonical_url="https://finki.ukim.mk/en/a/",
            language="en",
            category="studies",
            last_verified=date(2026, 9, 1),
            title="A title",
            body="A body\r\n",
            content_sha256=sha256(b"A title\n\nA body").hexdigest(),
        ),
    )

    rendered = render_aggregate(pages)
    reparsed = parse_aggregate(rendered)

    assert rendered == render_aggregate(reparsed)
    assert [page.source_id for page in reparsed] == ["a-page", "z-page"]
    assert "\r" not in rendered


@pytest.mark.parametrize(
    "field",
    ["source_id", "source_url", "canonical_url", "language", "category", "title"],
)
def test_render_rejects_unsafe_metadata(field: str) -> None:
    page = ReferencePage(
        source_id="safe-page",
        source_url="https://finki.ukim.mk/en/safe/",
        canonical_url="https://finki.ukim.mk/en/safe/",
        language="en",
        category="studies",
        last_verified=date(2026, 9, 1),
        title="Safe title",
        body="Safe body",
        content_sha256=sha256(b"Safe title\n\nSafe body").hexdigest(),
    )
    unsafe_value = {
        "source_id": "safe-page\n<!-- finki-static-page:end -->",
        "source_url": "https://finki.ukim.mk/en/safe/\r\nforged: value",
        "canonical_url": "https://finki.ukim.mk/en/safe/\r\nforged: value",
        "language": "en\nforged",
        "category": "studies\r\nforged",
        "title": "Safe title\n<!-- finki-static-page:end -->",
    }[field]
    if field == "source_id":
        unsafe_page = replace(page, source_id=unsafe_value)
    elif field == "source_url":
        unsafe_page = replace(page, source_url=unsafe_value)
    elif field == "canonical_url":
        unsafe_page = replace(page, canonical_url=unsafe_value)
    elif field == "language":
        unsafe_page = replace(page, language=unsafe_value)
    elif field == "category":
        unsafe_page = replace(page, category=unsafe_value)
    else:
        unsafe_page = replace(page, title=unsafe_value)

    with pytest.raises(
        ValueError, match="(single-line|metadata|boundary|English|route)"
    ):
        render_aggregate((unsafe_page,))
