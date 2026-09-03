from __future__ import annotations

import anyio
import httpx2
import pytest

from tools import website_fetch
from tools.website_content import build_documents
from tools.website_fetch import CrawlIncompleteError, crawl_pages
from tools.website_models import CrawlPlan, RestInventory


def test_crawl_pages_follows_only_canonical_html_routes() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/":
            return httpx2.Response(
                200,
                headers={"content-type": "text/html; charset=UTF-8"},
                text="""
                <main><a href="/en/about/">About</a>
                <a href="https://example.com/ignored">External</a>
                <a href="/announcements/feed/">Feed</a></main>
                """,
            )
        return httpx2.Response(
            200,
            headers={"content-type": "text/html; charset=UTF-8"},
            text="<main><h1>About</h1><p>English content.</p></main>",
        )

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            pages = await crawl_pages(
                client,
                CrawlPlan(seed_urls=("https://finki.ukim.mk/",)),
            )
        assert [page.final_url for page in pages] == [
            "https://finki.ukim.mk/",
            "https://finki.ukim.mk/en/about/",
        ]

    anyio.run(run)


def test_crawl_pages_preserves_explicit_seed_priority() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"content-type": "text/html; charset=UTF-8"},
            text=f"<main><h1>{request.url.path}</h1></main>",
        )

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            pages = await crawl_pages(
                client,
                CrawlPlan(
                    seed_urls=(
                        "https://finki.ukim.mk/en/",
                        "https://finki.ukim.mk/announcements/example/",
                    ),
                    max_pages=1,
                ),
            )
        assert [page.final_url for page in pages] == ["https://finki.ukim.mk/en/"]

    anyio.run(run)


def test_crawl_pages_reports_when_page_limit_truncates_frontier() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"content-type": "text/html; charset=UTF-8"},
            text='<main><a href="/next/">Next</a></main>',
        )

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            result = await crawl_pages(
                client,
                CrawlPlan(seed_urls=("https://finki.ukim.mk/",), max_pages=1),
            )
        assert result.requested_count == 1
        assert result.truncated is True

    anyio.run(run)


def test_crawl_pages_uses_rest_documents_for_rendered_link_discovery() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/announcement/rest-backed/":
            return httpx2.Response(
                200,
                headers={"content-type": "text/html; charset=UTF-8"},
                text='<main><a href="/rendered-only/">Rendered only</a></main>',
            )
        return httpx2.Response(
            200,
            headers={"content-type": "text/html; charset=UTF-8"},
            text="<main><h1>Rendered only</h1><p>Unique content.</p></main>",
        )

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            pages = await crawl_pages(
                client,
                CrawlPlan(
                    seed_urls=("https://finki.ukim.mk/announcement/rest-backed/",),
                    discovery_only_urls=frozenset(
                        {"https://finki.ukim.mk/announcement/rest-backed/"}
                    ),
                ),
            )
        assert requested_paths == ["/announcement/rest-backed/", "/rendered-only/"]
        assert [page.final_url for page in pages] == [
            "https://finki.ukim.mk/rendered-only/"
        ]

    anyio.run(run)


def test_crawl_pages_rejects_redirects_outside_public_hosts() -> None:
    requested_hosts: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested_hosts.append(request.url.host)
        if request.url.host == "finki.ukim.mk":
            return httpx2.Response(302, headers={"location": "https://example.com/"})
        return httpx2.Response(
            200,
            headers={"content-type": "text/html"},
            text="<main>External content.</main>",
        )

    async def run() -> None:
        async with httpx2.AsyncClient(
            follow_redirects=True,
            transport=httpx2.MockTransport(handler),
        ) as client:
            with pytest.raises(RuntimeError):
                _ = await crawl_pages(
                    client,
                    CrawlPlan(seed_urls=("https://finki.ukim.mk/redirect/",)),
                )
        assert requested_hosts == ["finki.ukim.mk"]

    anyio.run(run)


def test_crawl_pages_fails_when_a_page_returns_server_error() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(503)

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            with pytest.raises(RuntimeError):
                _ = await crawl_pages(
                    client,
                    CrawlPlan(seed_urls=("https://finki.ukim.mk/unavailable/",)),
                )

    anyio.run(run)


def test_crawl_pages_rejects_oversized_html_response() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"x" * 5_000_001,
        )

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            with pytest.raises(RuntimeError):
                _ = await crawl_pages(
                    client,
                    CrawlPlan(seed_urls=("https://finki.ukim.mk/oversized/",)),
                )

    anyio.run(run)


def test_crawl_pages_preserves_same_host_redirect_as_alias() -> None:
    requested_url = "https://finki.ukim.mk/old-page/"
    canonical_url = "https://finki.ukim.mk/new-page/"

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/old-page/":
            return httpx2.Response(301, headers={"location": canonical_url})
        return httpx2.Response(
            200,
            headers={"content-type": "text/html"},
            text="<main><h1>New page</h1><p>Canonical content.</p></main>",
        )

    async def run() -> None:
        async with httpx2.AsyncClient(
            follow_redirects=True,
            transport=httpx2.MockTransport(handler),
        ) as client:
            pages = await crawl_pages(client, CrawlPlan(seed_urls=(requested_url,)))
        documents = build_documents(RestInventory(records_by_url={}, totals={}), pages)
        assert documents[0].url == canonical_url
        assert documents[0].aliases == (requested_url,)

    anyio.run(run)


def test_crawl_pages_enforces_aggregate_response_byte_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(website_fetch, "_MAX_CRAWL_BYTES", 10)

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(
                lambda _request: httpx2.Response(
                    200,
                    headers={"content-type": "text/html"},
                    text="<main>More than ten bytes.</main>",
                )
            )
        ) as client:
            with pytest.raises(CrawlIncompleteError, match="crawl byte limit exceeded"):
                _ = await crawl_pages(
                    client,
                    CrawlPlan(seed_urls=("https://finki.ukim.mk/",), max_pages=1),
                )

    anyio.run(run)


def test_crawl_pages_counts_discarded_response_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(website_fetch, "_MAX_CRAWL_BYTES", 10)

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(
                lambda _request: httpx2.Response(
                    200,
                    headers={"content-type": "application/octet-stream"},
                    content=b"more than ten bytes",
                )
            )
        ) as client:
            with pytest.raises(CrawlIncompleteError, match="crawl byte limit exceeded"):
                _ = await crawl_pages(
                    client,
                    CrawlPlan(seed_urls=("https://finki.ukim.mk/file",), max_pages=1),
                )

    anyio.run(run)
