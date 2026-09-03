from __future__ import annotations

from urllib.parse import parse_qs

import anyio
import httpx2
import pytest

from tools.website_content import build_documents
from tools.website_http import fetch_rest_inventory
from tools.website_models import (
    CrawlResult,
    PageSnapshot,
    RestInventory,
    RestRecord,
    SourceKind,
)


def test_fetch_rest_inventory_paginates_viewable_text_types() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/types"):
            return httpx2.Response(
                200,
                json={
                    "announcement": {"rest_base": "announcement"},
                    "attachment": {"rest_base": "media"},
                },
            )
        page = parse_qs(request.url.query.decode())["page"][0]
        identifier = 1 if page == "1" else 2
        return httpx2.Response(
            200,
            headers={"X-WP-Total": "2", "X-WP-TotalPages": "2"},
            json=[
                {
                    "id": identifier,
                    "link": f"https://finki.ukim.mk/announcement/{identifier}/",
                    "slug": str(identifier),
                    "title": {"rendered": f"Notice {identifier}"},
                    "content": {"rendered": f"<p>Body {identifier}</p>"},
                    "type": "announcement",
                }
            ],
        )

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            inventory = await fetch_rest_inventory(client)
        assert inventory.totals == {"announcement": 2}
        assert sorted(record.id for record in inventory.records_by_url.values()) == [
            1,
            2,
        ]

    anyio.run(run)


def test_fetch_rest_inventory_rejects_excessive_pagination() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/types"):
            return httpx2.Response(
                200,
                json={"announcement": {"rest_base": "announcement"}},
            )
        return httpx2.Response(
            200,
            headers={"X-WP-Total": "0", "X-WP-TotalPages": "101"},
            json=[],
        )

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            with pytest.raises(RuntimeError):
                _ = await fetch_rest_inventory(client)

    anyio.run(run)


def test_build_documents_preserves_independent_sources_with_equal_content() -> None:
    record = RestRecord.model_validate(
        {
            "id": 7,
            "link": "https://finki.ukim.mk/kadar/",
            "slug": "kadar",
            "title": {"rendered": "Кадар"},
            "content": {"rendered": ""},
            "type": "page",
        }
    )
    inventory = RestInventory(records_by_url={record.link: record}, totals={"pages": 1})
    pages = (
        PageSnapshot(
            final_url=record.link,
            html="<main><h1>Кадар</h1><p>Професори и соработници.</p></main>",
            links=(),
            requested_url=record.link,
            status=200,
        ),
        PageSnapshot(
            final_url="https://finki.ukim.mk/team/",
            html="<main><h1>Кадар</h1><p>Професори и соработници.</p></main>",
            links=(),
            requested_url="https://finki.ukim.mk/team/",
            status=200,
        ),
    )

    documents = build_documents(
        inventory,
        CrawlResult(pages=pages, requested_count=2, truncated=False),
    )

    assert len(documents) == 2
    assert all(document.source_kind is SourceKind.RENDERED for document in documents)
    assert all(not document.aliases for document in documents)


def test_build_documents_uses_excerpt_when_rest_content_has_no_text() -> None:
    record = RestRecord.model_validate(
        {
            "id": 8,
            "link": "https://finki.ukim.mk/announcement/summary/",
            "slug": "summary",
            "title": {"rendered": "Summary"},
            "content": {"rendered": "<script>ignored()</script>"},
            "excerpt": {"rendered": "<p>Useful summary.</p>"},
            "type": "announcement",
        }
    )
    inventory = RestInventory(records_by_url={record.link: record}, totals={})

    documents = build_documents(
        inventory,
        CrawlResult(pages=(), requested_count=0, truncated=False),
    )

    assert documents[0].markdown == "Useful summary."


def test_build_documents_uses_rest_excerpt_when_rendered_page_is_title_only() -> None:
    url = "https://finki.ukim.mk/title-only/"
    record = RestRecord.model_validate(
        {
            "id": 20,
            "link": url,
            "slug": "title-only",
            "title": {"rendered": "A sufficiently long title"},
            "content": {"rendered": ""},
            "excerpt": {"rendered": "<p>Useful REST summary.</p>"},
            "type": "page",
        }
    )
    page = PageSnapshot(
        final_url=url,
        html="<main><h1>A sufficiently long title</h1></main>",
        links=(),
        requested_url=url,
        status=200,
    )

    documents = build_documents(
        RestInventory(records_by_url={url: record}, totals={}),
        CrawlResult(pages=(page,), requested_count=1, truncated=False),
    )

    assert documents[0].source_kind is SourceKind.REST
    assert documents[0].markdown == "Useful REST summary."


def test_build_documents_prefers_record_at_redirect_destination() -> None:
    final_url = "https://finki.ukim.mk/a-new/"
    old_url = "https://finki.ukim.mk/z-old/"
    canonical = RestRecord.model_validate(
        {
            "id": 21,
            "link": final_url,
            "slug": "a-new",
            "title": {"rendered": "Canonical"},
            "content": {"rendered": "<p>Canonical content.</p>"},
            "type": "page",
        }
    )
    redirected = RestRecord.model_validate(
        {
            "id": 22,
            "link": old_url,
            "slug": "z-old",
            "title": {"rendered": "Stale"},
            "content": {"rendered": "<p>Stale content.</p>"},
            "type": "page",
        }
    )

    documents = build_documents(
        RestInventory(
            records_by_url={final_url: canonical, old_url: redirected},
            totals={},
        ),
        CrawlResult(
            pages=(),
            requested_count=0,
            truncated=False,
            redirects=((final_url, old_url),),
        ),
    )

    assert documents[0].wordpress_id == canonical.id
    assert documents[0].markdown == "Canonical content."
    assert documents[0].aliases == (old_url,)


def test_build_documents_does_not_emit_fallback_for_rendered_source() -> None:
    first_url = "https://finki.ukim.mk/a/"
    fallback_url = "https://finki.ukim.mk/b/"
    fallback_record = RestRecord.model_validate(
        {
            "id": 23,
            "link": fallback_url,
            "slug": "b",
            "title": {"rendered": "Fallback"},
            "content": {"rendered": ""},
            "excerpt": {"rendered": "<p>Fallback excerpt.</p>"},
            "type": "page",
        }
    )
    pages = tuple(
        PageSnapshot(
            final_url=url,
            html="<main><h1>Rendered</h1><p>Same rendered body.</p></main>",
            links=(),
            requested_url=url,
            status=200,
        )
        for url in (first_url, fallback_url)
    )

    documents = build_documents(
        RestInventory(records_by_url={fallback_url: fallback_record}, totals={}),
        CrawlResult(pages=pages, requested_count=2, truncated=False),
    )

    assert {document.url for document in documents} == {first_url, fallback_url}
    assert all(document.source_kind is SourceKind.RENDERED for document in documents)
