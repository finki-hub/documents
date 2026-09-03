from __future__ import annotations

from collections import deque
from dataclasses import replace
from hashlib import sha256
from typing import final, override
from urllib.parse import urlsplit

import anyio
import httpx2
from selectolax.parser import HTMLParser

from tools.website_http import (
    PAGE_FETCH_POLICY,
    PublicFetchError,
    fetch_public,
)
from tools.website_markdown import document_from_page, document_from_rest
from tools.website_models import (
    CrawlPlan,
    CrawlResult,
    PageSnapshot,
    RestInventory,
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
    seed_frontier: deque[str] = deque()
    discovered_frontier: deque[str] = deque()
    queued: set[str] = set()
    for url in plan.seed_urls:
        if (normalized := normalize_url(url)) is not None and normalized not in queued:
            seed_frontier.append(normalized)
            queued.add(normalized)
    discovery_only_urls = {
        normalized
        for url in plan.discovery_only_urls
        if (normalized := normalize_url(url)) is not None
    }
    visited: set[str] = set()
    snapshots: dict[str, PageSnapshot] = {}
    redirects: set[tuple[str, str]] = set()
    requested_count = 0
    while (seed_frontier or discovered_frontier) and requested_count < plan.max_pages:
        batch: list[str] = []
        batch_limit = min(4, plan.max_pages - requested_count)
        while (seed_frontier or discovered_frontier) and len(batch) < batch_limit:
            frontier = seed_frontier if seed_frontier else discovered_frontier
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
            redirects.update((snapshot.final_url, alias) for alias in snapshot.aliases)
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
        for link in sorted(discovered):
            if link not in visited and link not in queued:
                discovered_frontier.append(link)
                queued.add(link)
    return CrawlResult(
        pages=tuple(snapshots[url] for url in sorted(snapshots)),
        requested_count=requested_count,
        truncated=bool(seed_frontier or discovered_frontier),
        redirects=tuple(sorted(redirects)),
    )


def build_documents(
    inventory: RestInventory,
    crawl: CrawlResult,
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

    redirects = {*crawl.redirects}
    redirects.update(
        (page.final_url, alias) for page in crawl.pages for alias in page.aliases
    )
    aliases_by_url: dict[str, set[str]] = {}
    final_by_alias = {alias: final_url for final_url, alias in redirects}
    for final_url, alias in redirects:
        aliases_by_url.setdefault(final_url, set()).add(alias)

    rest_fallbacks: list[WebsiteDocument] = []
    for _url, record in sorted(inventory.records_by_url.items()):
        document = document_from_rest(record, include_excerpt=False)
        final_url = final_by_alias.get(document.url, document.url)
        aliases = aliases_by_url.get(final_url, set())
        if final_url != document.url:
            aliases.add(document.url)
        document = replace(
            document,
            aliases=tuple(sorted(aliases)),
            url=final_url,
        )
        if document.markdown:
            add(document)
        else:
            fallback = replace(
                document_from_rest(record),
                aliases=document.aliases,
                url=document.url,
            )
            if fallback.markdown:
                rest_fallbacks.append(fallback)
    for page in sorted(crawl.pages, key=lambda item: item.final_url):
        if existing := documents_by_url.get(page.final_url):
            documents_by_url[page.final_url] = replace(
                existing,
                aliases=tuple(
                    sorted(
                        {
                            *existing.aliases,
                            *page.aliases,
                            *aliases_by_url.get(page.final_url, set()),
                        }
                    )
                ),
            )
            continue
        if "pg=" in urlsplit(page.final_url).query:
            continue
        document = replace(
            document_from_page(page.html, page.final_url),
            aliases=page.aliases,
        )
        if len(f"{document.title} {document.markdown}".strip()) >= 20:
            add(document)
    for fallback in rest_fallbacks:
        if fallback.url not in documents_by_url:
            add(fallback)
    return tuple(documents_by_url[url] for url in sorted(documents_by_url))
