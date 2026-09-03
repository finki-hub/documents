from __future__ import annotations

import argparse
import socket
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import ClassVar, Final
from urllib.parse import urlsplit

import anyio
import httpx2
from pydantic import BaseModel, ConfigDict

from tools.website_fetch import crawl_pages
from tools.website_http import fetch_rest_inventory
from tools.website_markdown import document_from_page, document_from_rest
from tools.website_models import (
    BASE_URL,
    CrawlPlan,
    CrawlResult,
    GenerationMetadata,
    RestInventory,
    WebsiteDocument,
)
from tools.website_output import write_output

DEFAULT_OUTPUT: Final = Path("website")


class CliArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    max_pages: int
    output: Path


@dataclass(frozen=True, slots=True)
class UpdateResult:
    document_count: int
    crawl_truncated: bool


def build_documents(
    inventory: RestInventory,
    crawl: CrawlResult,
) -> tuple[WebsiteDocument, ...]:
    documents_by_url: dict[str, WebsiteDocument] = {}

    def add(document: WebsiteDocument) -> None:
        documents_by_url[document.url] = document

    redirects = {*crawl.redirects}
    redirects.update(
        (page.final_url, alias) for page in crawl.pages for alias in page.aliases
    )
    aliases_by_url: dict[str, set[str]] = {}
    final_by_alias = {alias: final_url for final_url, alias in redirects}
    for final_url, alias in redirects:
        aliases_by_url.setdefault(final_url, set()).add(alias)

    rest_candidates: dict[str, list[tuple[str, WebsiteDocument, WebsiteDocument]]] = {}
    for _url, record in sorted(inventory.records_by_url.items()):
        document = document_from_rest(record, include_excerpt=False)
        source_url = document.url
        final_url = final_by_alias.get(document.url, document.url)
        aliases = {*aliases_by_url.get(final_url, set())}
        if final_url != document.url:
            aliases.add(document.url)
        aliases.discard(final_url)
        document = replace(
            document,
            aliases=tuple(sorted(aliases)),
            url=final_url,
        )
        fallback = replace(
            document_from_rest(record),
            aliases=document.aliases,
            url=document.url,
        )
        rest_candidates.setdefault(final_url, []).append(
            (source_url, document, fallback)
        )
    rest_fallbacks: list[WebsiteDocument] = []
    for final_url, candidates in sorted(rest_candidates.items()):
        candidates.sort(key=lambda item: (item[0] != final_url, item[0]))
        _source_url, document, fallback = candidates[0]
        merged_aliases = {
            alias
            for source_url, candidate, _candidate_fallback in candidates
            for alias in (*candidate.aliases, source_url)
            if alias != final_url
        }
        document = replace(document, aliases=tuple(sorted(merged_aliases)))
        fallback = replace(fallback, aliases=document.aliases)
        if document.markdown:
            add(document)
        elif fallback.markdown:
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
        if document.markdown:
            add(document)
    for fallback in rest_fallbacks:
        if fallback.url not in documents_by_url:
            add(fallback)
    return tuple(documents_by_url[url] for url in sorted(documents_by_url))


async def update_website(output_dir: Path, max_pages: int) -> UpdateResult:
    timeout = httpx2.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)
    limits = httpx2.Limits(
        max_connections=4,
        max_keepalive_connections=4,
        keepalive_expiry=30.0,
    )
    transport = httpx2.AsyncHTTPTransport(
        http2=True,
        retries=3,
        limits=limits,
        socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)],
    )
    headers = {"User-Agent": "finki-hub-documents/website-generator"}
    async with httpx2.AsyncClient(
        follow_redirects=False,
        headers=headers,
        timeout=timeout,
        transport=transport,
    ) as client:
        inventory = await fetch_rest_inventory(client)
        complete_rest_urls = frozenset(
            url
            for url, record in inventory.records_by_url.items()
            if document_from_rest(record, include_excerpt=False).markdown
        )
        empty_rest_urls = tuple(
            url for url in inventory.records_by_url if url not in complete_rest_urls
        )
        plan = CrawlPlan(
            seed_urls=(
                BASE_URL,
                f"{BASE_URL}en/",
                *empty_rest_urls,
                *sorted(complete_rest_urls),
            ),
            discovery_only_urls=complete_rest_urls,
            max_pages=max_pages,
        )
        crawl = await crawl_pages(client, plan)
    documents = build_documents(inventory, crawl)
    write_output(
        output_dir,
        documents,
        GenerationMetadata(
            crawled_pages=crawl.requested_count,
            crawl_truncated=crawl.truncated,
            rest_totals=inventory.totals,
        ),
    )
    return UpdateResult(
        document_count=len(documents),
        crawl_truncated=crawl.truncated,
    )


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic Markdown from the public FINKI website."
    )
    _ = parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    _ = parser.add_argument("--max-pages", type=_positive_int, default=10_000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = CliArgs.model_validate(vars(build_parser().parse_args(argv)))

    async def run() -> UpdateResult:
        return await update_website(args.output, args.max_pages)

    result = anyio.run(run)
    print(f"Generated {result.document_count} documents in {args.output}")
    if result.crawl_truncated:
        print(
            "WARNING: crawl stopped at --max-pages; output is incomplete",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
