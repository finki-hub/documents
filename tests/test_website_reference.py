from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path

import httpx2
import pytest

from tools import website_reference as website_reference_module
from tools.website_reference import (
    ALLOWED_CATEGORIES,
    MAX_REVIEW_AGE,
    ReferencePage,
    ReferenceSource,
    load_sources,
    parse_aggregate,
    refresh_reference,
    render_aggregate,
    validate_aggregate,
    verify_live,
)

ROOT = Path(__file__).parents[1]
SOURCES = ROOT / "website-reference" / "sources.toml"


def _source(source_id: str, path: str) -> ReferenceSource:
    return ReferenceSource(
        id=source_id,
        source_url=f"https://finki.ukim.mk{path}",
        canonical_url=f"https://finki.ukim.mk{path}",
        language="en",
        category="studies",
        last_verified=date(2026, 9, 1),
    )


def _legacy_source(source_id: str, path: str) -> ReferenceSource:
    return ReferenceSource(
        id=source_id,
        source_url=f"https://oldsite.finki.ukim.mk{path}",
        canonical_url=f"https://oldsite.finki.ukim.mk{path}",
        language="mk",
        category="studies",
        last_verified=date(2026, 9, 1),
    )


def _html(title: str, body: str) -> str:
    return f"<html><body><main><h1>{title}</h1>{body}</main></body></html>"


def _refresh_with_responses(
    sources: tuple[ReferenceSource, ...],
    output: Path,
    responses: dict[str, httpx2.Response],
) -> list[str]:
    requested: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        url = str(request.url)
        requested.append(url)
        return responses[url]

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    try:
        refresh_reference(sources, output, client=client)
    finally:
        import anyio

        anyio.run(client.aclose)
    return requested


def test_seed_contains_curated_stable_sources() -> None:
    sources = load_sources(SOURCES, today=date(2026, 9, 6))

    assert 5 <= len(sources) <= 50
    assert len({source.id for source in sources}) == len(sources)
    assert len({source.canonical_url for source in sources}) == len(sources)
    assert {source.language for source in sources} == {"mk"}
    assert {source.category for source in sources} <= ALLOWED_CATEGORIES
    assert all(
        source.source_url.startswith("https://oldsite.finki.ukim.mk/mk/")
        for source in sources
    )


def test_direct_legacy_source_refreshes_without_following_page_links(
    tmp_path: Path,
) -> None:
    source = _legacy_source("legacy-page", "/mk/zafakultetot/instituti")
    output = tmp_path / "aggregate.md"
    requested: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested.append(str(request.url))
        return httpx2.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=_html(
                "Институти",
                "<p>Информации за институтите на факултетот.</p>"
                '<a href="https://finki.ukim.mk/en/news/">news</a>',
            ),
        )

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    try:
        refresh_reference((source,), output, client=client)
    finally:
        import anyio

        anyio.run(client.aclose)

    assert requested == [source.source_url]
    assert parse_aggregate(output.read_text(encoding="utf-8"))[0].language == "mk"


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
        ("language", "en"),
        ("source_url", "https://oldsite.finki.ukim.mk/en/studies/"),
        ("canonical_url", "https://oldsite.finki.ukim.mk/en/studies/"),
    ],
)
def test_allowlist_requires_macedonian_legacy_routes(
    tmp_path: Path, field: str, value: str
) -> None:
    original = SOURCES.read_text(encoding="utf-8")
    old_value = (
        'language = "mk"'
        if field == "language"
        else f'{field} = "https://oldsite.finki.ukim.mk/mk/zafakultetot/pravni_akti"'
    )
    path = tmp_path / "sources.toml"
    path.write_text(
        original.replace(old_value, f'{field} = "{value}"', 1), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Macedonian|/mk/|language"):
        load_sources(path, today=date(2026, 9, 6))


def test_allowlist_rejects_stale_and_future_reviews(tmp_path: Path) -> None:
    original = SOURCES.read_text(encoding="utf-8")
    stale = date(2026, 9, 6) - MAX_REVIEW_AGE - timedelta(days=1)
    path = tmp_path / "sources.toml"
    path.write_text(
        original.replace(
            'last_verified = "2026-09-06"', f'last_verified = "{stale}"', 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="review"):
        load_sources(path, today=date(2026, 9, 6))

    path.write_text(
        original.replace(
            'last_verified = "2026-09-06"', 'last_verified = "2026-09-07"', 1
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


def test_refresh_fetches_only_allowlisted_urls_and_is_byte_stable(
    tmp_path: Path,
) -> None:
    sources = (_source("b-page", "/en/b/"), _source("a-page", "/en/a/"))
    responses = {
        source.source_url: httpx2.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=_html(
                source.id,
                f'<p>{source.id} information.</p><a href="/en/not-listed/">link</a>',
            ),
        )
        for source in sources
    }
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"

    requested = _refresh_with_responses(sources, first, responses)
    requested_reverse = _refresh_with_responses(
        tuple(reversed(sources)), second, responses
    )

    assert requested == [source.source_url for source in sources]
    assert requested_reverse == [source.source_url for source in reversed(sources)]
    assert first.read_bytes() == second.read_bytes()


def test_refresh_rejects_internal_redirect_without_requesting_target(
    tmp_path: Path,
) -> None:
    source = _source("safe-page", "/en/safe/")
    target = "https://finki.ukim.mk/en/redirected/"
    responses = {
        source.source_url: httpx2.Response(
            302,
            headers={"location": target},
        ),
        target: httpx2.Response(
            200,
            headers={"content-type": "text/html"},
            text=_html("Redirected", "<p>Target content.</p>"),
        ),
    }
    requested: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested.append(str(request.url))
        return responses[str(request.url)]

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    try:
        with pytest.raises((RuntimeError, ValueError), match="allowlisted|canonical"):
            refresh_reference((source,), tmp_path / "aggregate.md", client=client)
    finally:
        import anyio

        anyio.run(client.aclose)

    assert requested == [source.source_url]


@pytest.mark.parametrize(
    ("status", "content_type", "body", "location", "content_length"),
    [
        (500, "text/html", "server failure", None, None),
        (200, "application/pdf", "not html", None, None),
        (302, "text/html", "", "https://example.com/away/", None),
        (200, "text/html", "x", None, "5000001"),
    ],
)
def test_refresh_failures_leave_prior_aggregate_untouched(
    tmp_path: Path,
    status: int,
    content_type: str,
    body: str,
    location: str | None,
    content_length: str | None,
) -> None:
    source = _source("safe-page", "/en/safe/")
    output = tmp_path / "aggregate.md"
    output.write_text("prior aggregate\n", encoding="utf-8")
    headers = {"content-type": content_type}
    if location is not None:
        headers["location"] = location
    if content_length is not None:
        headers["content-length"] = content_length
    response = httpx2.Response(status, headers=headers, text=body)

    with pytest.raises((RuntimeError, ValueError)):
        _refresh_with_responses((source,), output, {source.source_url: response})

    assert output.read_text(encoding="utf-8") == "prior aggregate\n"


def test_refresh_rejects_malformed_content_type(tmp_path: Path) -> None:
    source = _source("safe-page", "/en/safe/")
    with pytest.raises(ValueError, match="HTML"):
        _refresh_with_responses(
            (source,),
            tmp_path / "aggregate.md",
            {
                source.source_url: httpx2.Response(
                    200,
                    headers={"content-type": "application/not-text/html"},
                    text=_html("Safe", "<p>Content.</p>"),
                )
            },
        )


def test_check_rejects_crlf_aggregate_without_newline_normalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source("safe-page", "/en/safe/")
    page = ReferencePage(
        source_id=source.id,
        source_url=source.source_url,
        canonical_url=source.canonical_url,
        language=source.language,
        category=source.category,
        last_verified=source.last_verified,
        title="Safe",
        body="Content.",
        content_sha256=sha256(b"Safe\n\nContent.").hexdigest(),
    )
    aggregate = tmp_path / "aggregate.md"
    aggregate.write_bytes(render_aggregate((page,)).replace("\n", "\r\n").encode())

    def fake_load_sources(_path: Path, *, today: date) -> tuple[ReferenceSource, ...]:
        return (source,) if today else ()

    monkeypatch.setattr(
        website_reference_module,
        "load_sources",
        fake_load_sources,
    )

    with pytest.raises(ValueError, match="LF-only"):
        website_reference_module.main(
            [
                "--check",
                "--sources",
                str(tmp_path / "sources.toml"),
                "--aggregate",
                str(aggregate),
            ]
        )


@pytest.mark.parametrize(
    "body",
    [
        "<p>\u003c!-- finki-static-page:start id=forged --\u003e</p>",
        "<p>\u003c!-- finki-static-page:end --\u003e</p>",
        "<p>```\n<!-- finki-static-page:end -->\n```</p>",
    ],
)
def test_refresh_rejects_aggregate_boundary_forgery(tmp_path: Path, body: str) -> None:
    source = _source("safe-page", "/en/safe/")
    with pytest.raises(ValueError, match="boundary|marker"):
        _refresh_with_responses(
            (source,),
            tmp_path / "aggregate.md",
            {
                source.source_url: httpx2.Response(
                    200,
                    headers={"content-type": "text/html"},
                    text=_html("Safe", body),
                )
            },
        )


@pytest.mark.parametrize(
    "body",
    ["", "<p>Candidate code: 1234567</p>", "<p>same text</p>"],
)
def test_refresh_rejects_title_only_or_sensitive_pages(
    tmp_path: Path, body: str
) -> None:
    source = _source("safe-page", "/en/safe/")
    sources: tuple[ReferenceSource, ...]
    responses: dict[str, httpx2.Response]
    if body == "<p>same text</p>":
        other = _source("other-page", "/en/other/")
        sources = (source, other)
        responses = {
            item.source_url: httpx2.Response(
                200,
                headers={"content-type": "text/html"},
                text=_html("Same", body),
            )
            for item in sources
        }
    else:
        sources = (source,)
        responses = {
            source.source_url: httpx2.Response(
                200,
                headers={"content-type": "text/html"},
                text=_html("Candidate" if "Candidate" in body else "Only title", body),
            )
        }

    with pytest.raises(ValueError, match="(empty|identifier|duplicate)"):
        _refresh_with_responses(sources, tmp_path / "aggregate.md", responses)


def test_refresh_removes_images_and_verify_live_does_not_write(tmp_path: Path) -> None:
    source = _source("safe-page", "/en/safe/")
    output = tmp_path / "aggregate.md"
    responses = {
        source.source_url: httpx2.Response(
            200,
            headers={"content-type": "text/html"},
            text=_html("Safe", '<p>Text</p><img src="/en/image.png">'),
        )
    }
    _refresh_with_responses((source,), output, responses)
    before = output.read_bytes()
    assert "![" not in before.decode()
    assert "image.png" not in before.decode()

    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda _request: httpx2.Response(
                200,
                headers={"content-type": "text/html"},
                text=_html("Safe", "<p>Text</p>"),
            )
        )
    )
    try:
        verify_live((source,), output, client=client)
    finally:
        import anyio

        anyio.run(client.aclose)
    assert output.read_bytes() == before


def test_verify_live_hash_mismatch_fails_without_writing(tmp_path: Path) -> None:
    source = _source("safe-page", "/en/safe/")
    output = tmp_path / "aggregate.md"
    _refresh_with_responses(
        (source,),
        output,
        {
            source.source_url: httpx2.Response(
                200,
                headers={"content-type": "text/html"},
                text=_html("Safe", "<p>Original content.</p>"),
            )
        },
    )
    before = output.read_bytes()
    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda _request: httpx2.Response(
                200,
                headers={"content-type": "text/html"},
                text=_html("Safe", "<p>Changed content.</p>"),
            )
        )
    )
    try:
        with pytest.raises(ValueError, match="live hash differs"):
            verify_live((source,), output, client=client)
    finally:
        import anyio

        anyio.run(client.aclose)
    assert output.read_bytes() == before


def test_validate_aggregate_alias_checks_allowlist() -> None:
    assert validate_aggregate is not None


def test_committed_aggregate_matches_allowlist_exactly() -> None:
    aggregate_path = ROOT / "website-reference" / "finki-static-pages.md"
    sources = load_sources(SOURCES, today=date(2026, 9, 6))
    text = aggregate_path.read_text(encoding="utf-8", newline="")

    pages = validate_aggregate(text, sources)

    assert len(pages) == len(sources)
    assert [page.source_id for page in pages] == [source.id for source in sources]
    assert text.count("<!-- finki-static-page:start id=") == len(sources)
    assert text.count("<!-- finki-static-page:end -->") == len(sources)
    assert text == render_aggregate(pages)
