from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import replace
from hashlib import sha256
from typing import Final, final, override
from urllib.parse import urlencode, urlsplit

import anyio
import httpx2
from selectolax.parser import HTMLParser

from tools.website_http import (
    PAGE_FETCH_POLICY,
    REST_FETCH_POLICY,
    PublicFetchError,
    fetch_public,
)
from tools.website_markdown import document_from_page, document_from_rest
from tools.website_models import (
    BASE_URL,
    REST_RECORDS,
    REST_TYPES,
    TEXT_REST_BASES,
    CrawlPlan,
    CrawlResult,
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
_MAX_REST_PAGES: Final = 100


@final
class CrawlIncompleteError(RuntimeError):
    __slots__ = ("failures",)
    failures: tuple[PublicFetchError, ...]

    def __init__(self, failures: tuple[PublicFetchError, ...]) -> None:
        self.failures = failures
        super().__init__(failures)

    @override
    def __str__(self) -> str:
        return "; ".join(str(failure) for failure in self.failures)


async def fetch_rest_inventory(client: httpx2.AsyncClient) -> RestInventory:
    types_response = await fetch_public(
        client,
        f"{BASE_URL}wp-json/wp/v2/types",
        REST_FETCH_POLICY,
    )
    rest_types = REST_TYPES.validate_json(types_response.body)
    records_by_url: dict[str, RestRecord] = {}
    totals: dict[str, int] = {}
    for rest_type in sorted(rest_types.values(), key=lambda item: item.rest_base or ""):
        rest_base = rest_type.rest_base
        if rest_base not in TEXT_REST_BASES:
            continue
        endpoint = f"{BASE_URL}wp-json/wp/v2/{rest_base}"
        response = await fetch_public(
            client,
            f"{endpoint}?{urlencode({'page': 1, 'per_page': 100})}",
            REST_FETCH_POLICY,
        )
        total_pages = int(response.headers.get("X-WP-TotalPages", "1"))
        if total_pages > _MAX_REST_PAGES:
            raise PublicFetchError(
                reason="REST pagination limit exceeded", url=endpoint
            )
        totals[rest_base] = int(response.headers.get("X-WP-Total", "0"))
        responses = [response]
        for page in range(2, total_pages + 1):
            next_response = await fetch_public(
                client,
                f"{endpoint}?{urlencode({'page': page, 'per_page': 100})}",
                REST_FETCH_POLICY,
            )
            responses.append(next_response)
        for page_response in responses:
            for record in REST_RECORDS.validate_json(page_response.body):
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
    response = await fetch_public(client, requested_url, PAGE_FETCH_POLICY)
    if response.status in PAGE_FETCH_POLICY.missing_statuses:
        return None
    if "text/html" not in response.content_type:
        return None
    html = response.body.decode(response.encoding, errors="replace")
    aliases = (requested_url,) if requested_url != response.url else ()
    return PageSnapshot(
        final_url=response.url,
        html=html,
        links=_page_links(html, response.url),
        requested_url=requested_url,
        status=response.status,
        aliases=aliases,
    )


async def crawl_pages(
    client: httpx2.AsyncClient,
    plan: CrawlPlan,
) -> CrawlResult:
    frontier: deque[str] = deque()
    queued: set[str] = set()
    for url in plan.seed_urls:
        if (normalized := normalize_url(url)) is not None:
            frontier.append(normalized)
            queued.add(normalized)
    discovery_only_urls = {
        normalized
        for url in plan.discovery_only_urls
        if (normalized := normalize_url(url)) is not None
    }
    visited: set[str] = set()
    snapshots: dict[str, PageSnapshot] = {}
    requested_count = 0
    while frontier and requested_count < plan.max_pages:
        batch: list[str] = []
        while frontier and len(batch) < min(4, plan.max_pages - requested_count):
            url = frontier.popleft()
            queued.discard(url)
            if url in visited:
                continue
            visited.add(url)
            batch.append(url)
        if not batch:
            continue
        requested_count += len(batch)
        results: list[PageSnapshot] = []
        failures: list[PublicFetchError] = []

        async def fetch(
            url: str,
            output: list[PageSnapshot],
            output_failures: list[PublicFetchError],
        ) -> None:
            try:
                if snapshot := await _fetch_page(client, url):
                    output.append(snapshot)
            except PublicFetchError as error:
                output_failures.append(error)

        async with anyio.create_task_group() as tasks:
            for url in batch:
                visited.add(url)
                _ = tasks.start_soon(fetch, url, results, failures)
        if failures:
            raise CrawlIncompleteError(tuple(failures))
        discovered: set[str] = set()
        for snapshot in sorted(
            results,
            key=lambda item: (item.final_url, item.requested_url),
        ):
            if snapshot.requested_url not in discovery_only_urls:
                if existing := snapshots.get(snapshot.final_url):
                    snapshots[snapshot.final_url] = replace(
                        existing,
                        aliases=tuple(sorted({*existing.aliases, *snapshot.aliases})),
                        links=tuple(sorted({*existing.links, *snapshot.links})),
                    )
                else:
                    snapshots[snapshot.final_url] = snapshot
            discovered.update(snapshot.links)
        for link in sorted(discovered, reverse=True):
            if link not in visited and link not in queued:
                frontier.appendleft(link)
                queued.add(link)
    return CrawlResult(
        pages=tuple(snapshots[url] for url in sorted(snapshots)),
        requested_count=requested_count,
        truncated=bool(frontier),
    )


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
                aliases=tuple(
                    sorted({*canonical.aliases, document.url, *document.aliases})
                ),
            )
            return
        fingerprints[fingerprint] = document.url
        documents_by_url[document.url] = document

    for _url, record in sorted(inventory.records_by_url.items()):
        document = document_from_rest(record)
        if document.markdown:
            add(document)
    for page in sorted(pages, key=lambda item: item.final_url):
        if (
            page.final_url in documents_by_url
            or "pg=" in urlsplit(page.final_url).query
        ):
            continue
        document = replace(
            document_from_page(page.html, page.final_url),
            aliases=page.aliases,
        )
        if len(f"{document.title} {document.markdown}".strip()) >= 20:
            add(document)
    return tuple(documents_by_url[url] for url in sorted(documents_by_url))
