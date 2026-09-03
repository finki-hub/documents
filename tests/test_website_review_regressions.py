from __future__ import annotations

import anyio
import httpx2
import pytest

from tools import website_http
from tools.website_fetch import build_documents, crawl_pages
from tools.website_http import (
    PAGE_FETCH_POLICY,
    PublicFetchError,
    fetch_public,
    fetch_rest_inventory,
)
from tools.website_models import (
    CrawlPlan,
    CrawlResult,
    PageSnapshot,
    RestInventory,
    RestRecord,
    SourceKind,
    normalize_url,
)


def test_normalize_url_rejects_dot_segment_non_content_route() -> None:
    assert normalize_url("/safe/../wp-admin/") is None


def test_fetch_public_keeps_rest_redirects_inside_rest_api() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.startswith("/wp-json/"):
            return httpx2.Response(302, headers={"location": "/wp-admin/"})
        return httpx2.Response(200, text="private")

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            with pytest.raises(PublicFetchError, match="unsafe REST URL"):
                _ = await fetch_rest_inventory(client)

    anyio.run(run)


def test_fetch_public_rejects_page_dot_segment_bypass() -> None:
    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(lambda _request: httpx2.Response(200))
        ) as client:
            with pytest.raises(PublicFetchError, match="unsafe public URL"):
                _ = await fetch_public(
                    client,
                    "https://finki.ukim.mk/safe/../wp-admin/",
                    PAGE_FETCH_POLICY,
                )

    anyio.run(run)


def test_crawl_pages_deduplicates_seeds_before_reporting_truncation() -> None:
    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(
                lambda _request: httpx2.Response(
                    200,
                    headers={"content-type": "text/html"},
                    text="<main>Content</main>",
                )
            )
        ) as client:
            result = await crawl_pages(
                client,
                CrawlPlan(
                    seed_urls=(
                        "https://finki.ukim.mk/one/",
                        "https://finki.ukim.mk/one/",
                    ),
                    max_pages=1,
                ),
            )

        assert result.requested_count == 1
        assert result.truncated is False

    anyio.run(run)


def test_crawl_pages_exhausts_explicit_seeds_before_discovered_links() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested_paths.append(request.url.path)
        link = (
            '<a href="/discovered/">Discovered</a>' if request.url.path == "/1/" else ""
        )
        return httpx2.Response(
            200,
            headers={"content-type": "text/html"},
            text=f"<main>{link}<p>{request.url.path}</p></main>",
        )

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            result = await crawl_pages(
                client,
                CrawlPlan(
                    seed_urls=tuple(
                        f"https://finki.ukim.mk/{index}/" for index in range(1, 6)
                    ),
                    max_pages=5,
                ),
            )

        assert requested_paths == [f"/{index}/" for index in range(1, 6)]
        assert result.truncated is True

    anyio.run(run)


def test_build_documents_merges_redirect_alias_into_rest_document() -> None:
    record = RestRecord.model_validate(
        {
            "id": 9,
            "link": "https://finki.ukim.mk/new/",
            "slug": "new",
            "title": {"rendered": "New"},
            "content": {"rendered": "<p>Canonical REST content.</p>"},
            "type": "page",
        }
    )
    old_url = "https://finki.ukim.mk/old/"
    page = PageSnapshot(
        final_url=record.link,
        html="<main><p>Canonical rendered content.</p></main>",
        links=(),
        requested_url=old_url,
        status=200,
        aliases=(old_url,),
    )

    documents = build_documents(
        RestInventory(records_by_url={record.link: record}, totals={}),
        CrawlResult(pages=(page,), requested_count=1, truncated=False),
    )

    assert documents[0].url == record.link
    assert documents[0].aliases == (old_url,)


def test_build_documents_prefers_rendered_page_over_rest_excerpt() -> None:
    record = RestRecord.model_validate(
        {
            "id": 10,
            "link": "https://finki.ukim.mk/summary/",
            "slug": "summary",
            "title": {"rendered": "Summary"},
            "content": {"rendered": ""},
            "excerpt": {"rendered": "<p>Short summary.</p>"},
            "type": "page",
        }
    )
    page = PageSnapshot(
        final_url=record.link,
        html="<main><h1>Summary</h1><p>Complete rendered page content.</p></main>",
        links=(),
        requested_url=record.link,
        status=200,
    )

    documents = build_documents(
        RestInventory(records_by_url={record.link: record}, totals={}),
        CrawlResult(pages=(page,), requested_count=1, truncated=False),
    )

    assert documents[0].source_kind is SourceKind.RENDERED
    assert documents[0].markdown == "Complete rendered page content."


def test_discovery_only_redirect_reconciles_rest_document_url() -> None:
    old_url = "https://finki.ukim.mk/old-rest/"
    final_url = "https://finki.ukim.mk/final-rest/"
    record = RestRecord.model_validate(
        {
            "id": 11,
            "link": old_url,
            "slug": "old-rest",
            "title": {"rendered": "REST page"},
            "content": {"rendered": "<p>REST content.</p>"},
            "type": "page",
        }
    )

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/old-rest/":
            return httpx2.Response(301, headers={"location": final_url})
        return httpx2.Response(
            200,
            headers={"content-type": "text/html"},
            text="<main><p>Rendered content.</p></main>",
        )

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            crawl = await crawl_pages(
                client,
                CrawlPlan(
                    seed_urls=(old_url,),
                    discovery_only_urls=frozenset({old_url}),
                ),
            )
        documents = build_documents(
            RestInventory(records_by_url={old_url: record}, totals={}),
            crawl,
        )

        assert documents[0].url == final_url
        assert documents[0].aliases == (old_url,)

    anyio.run(run)


def test_fetch_rest_inventory_enforces_aggregate_byte_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(website_http, "_MAX_REST_BYTES", 10)

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/types"):
            return httpx2.Response(
                200,
                json={"announcement": {"rest_base": "announcement"}},
            )
        return httpx2.Response(
            200,
            headers={"X-WP-Total": "0", "X-WP-TotalPages": "1"},
            json=[],
        )

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            with pytest.raises(PublicFetchError, match="REST inventory limit exceeded"):
                _ = await fetch_rest_inventory(client)

    anyio.run(run)
