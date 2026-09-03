from __future__ import annotations

from urllib.parse import parse_qs

import anyio
import httpx2
import pytest

from tools.website_fetch import build_documents
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

    documents = build_documents(
        inventory,
        CrawlResult(pages=pages, requested_count=2, truncated=False),
    )

    assert len(documents) == 1
    assert documents[0].source_kind is SourceKind.RENDERED
    assert documents[0].aliases == ("https://finki.ukim.mk/team/",)


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
