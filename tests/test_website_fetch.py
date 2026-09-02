from __future__ import annotations

from urllib.parse import parse_qs

import anyio
import httpx2

from tools.website_fetch import build_documents, crawl_pages, fetch_rest_inventory
from tools.website_models import (
    CrawlPlan,
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
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            inventory = await fetch_rest_inventory(client)
        assert inventory.totals == {"announcement": 2}
        assert sorted(record.id for record in inventory.records_by_url.values()) == [1, 2]

    anyio.run(run)


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
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
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
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
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


def test_crawl_pages_does_not_fetch_excluded_rest_documents() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested_paths.append(request.url.path)
        return httpx2.Response(
            200,
            headers={"content-type": "text/html; charset=UTF-8"},
            text='<main><a href="/en/about/">About</a></main>',
        )

    async def run() -> None:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            _ = await crawl_pages(
                client,
                CrawlPlan(
                    seed_urls=(
                        "https://finki.ukim.mk/announcement/rest-backed/",
                        "https://finki.ukim.mk/en/",
                    ),
                    excluded_urls=frozenset(
                        {"https://finki.ukim.mk/announcement/rest-backed/"}
                    ),
                ),
            )
        assert "/announcement/rest-backed/" not in requested_paths
        assert "/en/" in requested_paths

    anyio.run(run)


def test_build_documents_uses_rendered_fallback_and_deduplicates_aliases() -> None:
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

    documents = build_documents(inventory, pages)

    assert len(documents) == 1
    assert documents[0].source_kind is SourceKind.RENDERED
    assert documents[0].aliases == ("https://finki.ukim.mk/team/",)
