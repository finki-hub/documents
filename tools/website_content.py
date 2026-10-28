from __future__ import annotations

import argparse
import socket
import sys
from collections.abc import Callable, Sequence
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
from tools.website_privacy import contains_sensitive_personal_identifier

DEFAULT_OUTPUT: Final = Path("website")
type _RestCandidate = tuple[str, WebsiteDocument, WebsiteDocument]


class CliArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    max_pages: int
    output: Path


@dataclass(frozen=True, slots=True)
class UpdateResult:
    document_count: int
    crawl_truncated: bool


@dataclass(slots=True)
class _DocumentBuilder:
    documents_by_url: dict[str, WebsiteDocument]
    blocked_urls: set[str]

    def is_blocked(self, document: WebsiteDocument) -> bool:
        if document.url in self.blocked_urls:
            return True
        emitted_text = "\n".join((document.markdown, document.url, *document.aliases))
        if not contains_sensitive_personal_identifier(
            title=document.title,
            markdown=emitted_text,
        ):
            return False
        self.blocked_urls.add(document.url)
        _ = self.documents_by_url.pop(document.url, None)
        return True

    def add(self, document: WebsiteDocument) -> None:
        if not self.is_blocked(document):
            self.documents_by_url[document.url] = document


def _redirect_aliases(crawl: CrawlResult) -> tuple[dict[str, str], dict[str, set[str]]]:
    redirects = {*crawl.redirects}
    redirects.update(
        (page.final_url, alias) for page in crawl.pages for alias in page.aliases
    )
    aliases_by_url: dict[str, set[str]] = {}
    final_by_alias = {alias: final_url for final_url, alias in redirects}
    for final_url, alias in redirects:
        aliases_by_url.setdefault(final_url, set()).add(alias)
    return final_by_alias, aliases_by_url


def _rest_candidates(
    inventory: RestInventory,
    final_by_alias: dict[str, str],
    aliases_by_url: dict[str, set[str]],
    builder: _DocumentBuilder,
) -> dict[str, list[_RestCandidate]]:
    rest_candidates: dict[str, list[_RestCandidate]] = {}
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
        if builder.is_blocked(document) or builder.is_blocked(fallback):
            continue
        rest_candidates.setdefault(final_url, []).append(
            (source_url, document, fallback)
        )
    return rest_candidates


def _candidate_order(final_url: str) -> Callable[[_RestCandidate], tuple[bool, str]]:
    return lambda item: (item[0] != final_url, item[0])


def _add_rest_documents(
    rest_candidates: dict[str, list[_RestCandidate]],
    builder: _DocumentBuilder,
) -> list[WebsiteDocument]:
    rest_fallbacks: list[WebsiteDocument] = []
    for final_url, candidates in sorted(rest_candidates.items()):
        if final_url in builder.blocked_urls:
            continue
        candidates.sort(key=_candidate_order(final_url))
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
            builder.add(document)
        elif fallback.markdown:
            rest_fallbacks.append(fallback)
    return rest_fallbacks


def _add_rendered_documents(
    crawl: CrawlResult,
    aliases_by_url: dict[str, set[str]],
    builder: _DocumentBuilder,
) -> None:
    for page in sorted(crawl.pages, key=lambda item: item.final_url):
        if "pg=" in urlsplit(page.final_url).query:
            continue
        document = replace(
            document_from_page(page.html, page.final_url),
            aliases=page.aliases,
        )
        if builder.is_blocked(document):
            continue
        if existing := builder.documents_by_url.get(page.final_url):
            merged = replace(
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
            if not builder.is_blocked(merged):
                builder.documents_by_url[page.final_url] = merged
            continue
        if document.markdown:
            builder.add(document)


def build_documents(
    inventory: RestInventory,
    crawl: CrawlResult,
) -> tuple[WebsiteDocument, ...]:
    builder = _DocumentBuilder({}, set())
    final_by_alias, aliases_by_url = _redirect_aliases(crawl)
    candidates = _rest_candidates(inventory, final_by_alias, aliases_by_url, builder)
    rest_fallbacks = _add_rest_documents(candidates, builder)
    _add_rendered_documents(crawl, aliases_by_url, builder)
    for fallback in rest_fallbacks:
        if fallback.url not in builder.documents_by_url:
            builder.add(fallback)
    return tuple(
        builder.documents_by_url[url] for url in sorted(builder.documents_by_url)
    )


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
