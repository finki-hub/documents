from __future__ import annotations

import argparse
import socket
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, Final

import anyio
import httpx2
from pydantic import BaseModel, ConfigDict

from tools.website_fetch import build_documents, crawl_pages, fetch_rest_inventory
from tools.website_markdown import document_from_rest
from tools.website_models import BASE_URL, CrawlPlan, GenerationMetadata
from tools.website_output import write_output

DEFAULT_OUTPUT: Final = Path("website")


class CliArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    max_pages: int
    output: Path


async def update_website(output_dir: Path, max_pages: int) -> int:
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
            if document_from_rest(record).markdown
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
    return len(documents)


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

    async def run() -> int:
        return await update_website(args.output, args.max_pages)

    document_count = anyio.run(run)
    print(f"Generated {document_count} documents in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
