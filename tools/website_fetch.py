from __future__ import annotations

from collections import deque
from dataclasses import replace
from typing import Final, final, override
from urllib.parse import urlsplit

import anyio
import httpx2
from selectolax.parser import HTMLParser

from tools.website_http import (
    PAGE_FETCH_POLICY,
    PublicFetchError,
    fetch_public,
)
from tools.website_models import (
    CrawlPlan,
    CrawlResult,
    PageSnapshot,
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
_MAX_CRAWL_BYTES: Final = 250_000_000
_MAX_CRAWL_URLS: Final = 100_000


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
        size_bytes=len(response.body),
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
    received_bytes = 0
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
        received_bytes += sum(snapshot.size_bytes for snapshot in results)
        if received_bytes > _MAX_CRAWL_BYTES:
            raise CrawlIncompleteError(
                (
                    PublicFetchError(
                        reason="crawl byte limit exceeded",
                        url=results[-1].final_url,
                    ),
                )
            )
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
                if len(visited) + len(queued) >= _MAX_CRAWL_URLS:
                    raise CrawlIncompleteError(
                        (PublicFetchError(reason="crawl URL limit exceeded", url=link),)
                    )
                discovered_frontier.append(link)
                queued.add(link)
    return CrawlResult(
        pages=tuple(snapshots[url] for url in sorted(snapshots)),
        requested_count=requested_count,
        truncated=bool(seed_frontier or discovered_frontier),
        redirects=tuple(sorted(redirects)),
    )
