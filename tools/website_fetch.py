from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from hashlib import sha256
from urllib.parse import urlsplit

import anyio
import httpx2
from selectolax.parser import HTMLParser

from tools.website_markdown import document_from_page, document_from_rest
from tools.website_models import (
    BASE_URL,
    REST_RECORDS,
    REST_TYPES,
    TEXT_REST_BASES,
    CrawlPlan,
    PageSnapshot,
    RestInventory,
    RestRecord,
    WebsiteDocument,
    normalize_url,
)

_ASSET_SUFFIXES = (
    ".7z",
    ".avi",
    ".csv",
    ".doc",
    ".docx",
    ".gif",
    ".jpeg",
    ".jpg",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".ods",
    ".odt",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".svg",
    ".webp",
    ".xls",
    ".xlsx",
    ".zip",
)


async def fetch_rest_inventory(client: httpx2.AsyncClient) -> RestInventory:
    types_response = await client.get(f"{BASE_URL}wp-json/wp/v2/types")
    _ = types_response.raise_for_status()
    rest_types = REST_TYPES.validate_json(types_response.content)
    records_by_url: dict[str, RestRecord] = {}
    totals: dict[str, int] = {}
    for rest_type in sorted(rest_types.values(), key=lambda item: item.rest_base or ""):
        rest_base = rest_type.rest_base
        if rest_base not in TEXT_REST_BASES:
            continue
        endpoint = f"{BASE_URL}wp-json/wp/v2/{rest_base}"
        response = await client.get(endpoint, params={"page": 1, "per_page": 100})
        _ = response.raise_for_status()
        total_pages = int(response.headers.get("X-WP-TotalPages", "1"))
        totals[rest_base] = int(response.headers.get("X-WP-Total", "0"))
        responses = [response]
        for page in range(2, total_pages + 1):
            next_response = await client.get(
                endpoint,
                params={"page": page, "per_page": 100},
            )
            _ = next_response.raise_for_status()
            responses.append(next_response)
        for page_response in responses:
            for record in REST_RECORDS.validate_json(page_response.content):
                canonical_url = normalize_url(record.link)
                if canonical_url is not None:
                    records_by_url[canonical_url] = record
    return RestInventory(records_by_url=records_by_url, totals=totals)


def _page_links(html: str, url: str) -> tuple[str, ...]:
    parser = HTMLParser(html)
    links: set[str] = set()
    for node in parser.css("a[href]"):
        href = node.attributes.get("href")
        if href and (normalized := normalize_url(href, url)) is not None:
            path = urlsplit(normalized).path.casefold()
            if not path.endswith(_ASSET_SUFFIXES):
                links.add(normalized)
    return tuple(sorted(links))


async def _fetch_page(
    client: httpx2.AsyncClient,
    requested_url: str,
) -> PageSnapshot | None:
    try:
        async with client.stream("GET", requested_url) as response:
            if response.status_code >= 400:
                return None
            content_type = response.headers.get("content-type", "").casefold()
            if "text/html" not in content_type:
                return None
            body = await response.aread()
            final_url = normalize_url(str(response.url))
            if final_url is None:
                return None
            html = body.decode(response.encoding or "utf-8", errors="replace")
            return PageSnapshot(
                final_url=final_url,
                html=html,
                links=_page_links(html, final_url),
                requested_url=requested_url,
                status=response.status_code,
            )
    except httpx2.HTTPError:
        return None


async def crawl_pages(
    client: httpx2.AsyncClient,
    plan: CrawlPlan,
) -> tuple[PageSnapshot, ...]:
    frontier: dict[str, None] = {}
    for url in plan.seed_urls:
        if (normalized := normalize_url(url)) is not None:
            frontier.setdefault(normalized, None)
    excluded_urls = {
        normalized
        for url in plan.excluded_urls
        if (normalized := normalize_url(url)) is not None
    }
    visited: set[str] = set()
    snapshots: dict[str, PageSnapshot] = {}
    requested_count = 0
    while frontier and requested_count < plan.max_pages:
        batch: list[str] = []
        while frontier and len(batch) < min(4, plan.max_pages - requested_count):
            url = next(iter(frontier))
            frontier.pop(url)
            if url in visited:
                continue
            visited.add(url)
            if url not in excluded_urls:
                batch.append(url)
        if not batch:
            continue
        requested_count += len(batch)
        results: list[PageSnapshot] = []

        async def fetch(url: str, output: list[PageSnapshot]) -> None:
            if snapshot := await _fetch_page(client, url):
                output.append(snapshot)

        async with anyio.create_task_group() as tasks:
            for url in batch:
                visited.add(url)
                _ = tasks.start_soon(fetch, url, results)
        for snapshot in sorted(results, key=lambda item: item.final_url):
            snapshots[snapshot.final_url] = snapshot
            for link in snapshot.links:
                if link not in visited and link not in excluded_urls:
                    frontier.setdefault(link, None)
    return tuple(snapshots[url] for url in sorted(snapshots))


def build_documents(
    inventory: RestInventory,
    pages: Iterable[PageSnapshot],
) -> tuple[WebsiteDocument, ...]:
    documents_by_url: dict[str, WebsiteDocument] = {}
    fingerprints: dict[str, str] = {}

    def add(document: WebsiteDocument) -> None:
        fingerprint = sha256(
            f"{document.language}\0{document.title}\0{document.markdown}".encode()
        ).hexdigest()
        if canonical_url := fingerprints.get(fingerprint):
            canonical = documents_by_url[canonical_url]
            documents_by_url[canonical_url] = replace(
                canonical,
                aliases=tuple(sorted({*canonical.aliases, document.url})),
            )
            return
        fingerprints[fingerprint] = document.url
        documents_by_url[document.url] = document

    for _url, record in sorted(inventory.records_by_url.items()):
        if record.content and record.content.rendered.strip():
            add(document_from_rest(record))
    for page in sorted(pages, key=lambda item: item.final_url):
        if page.final_url in documents_by_url or "pg=" in urlsplit(page.final_url).query:
            continue
        document = document_from_page(page.html, page.final_url)
        if len(f"{document.title} {document.markdown}".strip()) >= 20:
            add(document)
    return tuple(documents_by_url[url] for url in sorted(documents_by_url))
