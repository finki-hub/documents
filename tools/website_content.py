from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import tempfile
from collections.abc import Iterable, Sequence
from hashlib import sha256
from pathlib import Path
from typing import ClassVar, Final
from urllib.parse import unquote, urlsplit

import anyio
import httpx2
from pydantic import BaseModel, ConfigDict

from tools.website_fetch import build_documents, crawl_pages, fetch_rest_inventory
from tools.website_markdown import render_document
from tools.website_models import (
    BASE_URL,
    CrawlPlan,
    ManifestEntry,
    WebsiteDocument,
    WebsiteManifest,
)

DEFAULT_OUTPUT: Final = Path("website")


class CliArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    max_pages: int
    output: Path


def _document_relative_path(document: WebsiteDocument) -> Path:
    parsed = urlsplit(document.url)
    identity = unquote(f"{parsed.path}-{parsed.query}").casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", identity).strip("-") or "home"
    slug = slug[:80].rstrip("-")
    digest = sha256(document.url.encode()).hexdigest()[:10]
    return Path("documents", document.language, f"{slug}-{digest}.md")


def _manifest_entry(document: WebsiteDocument, path: Path) -> ManifestEntry:
    return ManifestEntry(
        aliases=document.aliases,
        language=document.language,
        modified=document.modified,
        path=path.as_posix(),
        source_kind=document.source_kind,
        title=document.title,
        url=document.url,
        wordpress_id=document.wordpress_id,
        wordpress_type=document.wordpress_type,
    )


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, pending_name = tempfile.mkstemp(
        prefix=f".{destination.name}-",
        dir=destination.parent,
    )
    os.close(descriptor)
    pending = Path(pending_name)
    try:
        _ = shutil.copyfile(source, pending)
        os.replace(pending, destination)
    finally:
        pending.unlink(missing_ok=True)


def _install_snapshot(snapshot: Path, output_dir: Path) -> None:
    wanted = {
        path.relative_to(snapshot) for path in snapshot.rglob("*") if path.is_file()
    }
    manifest = Path("manifest.json")
    output_dir.mkdir(parents=True, exist_ok=True)
    for relative_path in sorted(wanted - {manifest}, key=Path.as_posix):
        _atomic_copy(snapshot / relative_path, output_dir / relative_path)
    for existing in tuple(output_dir.rglob("*")):
        if existing.is_file() and existing.relative_to(output_dir) not in wanted:
            existing.unlink()
    directories = (path for path in output_dir.rglob("*") if path.is_dir())
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()
    _atomic_copy(snapshot / manifest, output_dir / manifest)


def write_output(
    output_dir: Path,
    documents: Iterable[WebsiteDocument],
    rest_totals: dict[str, int],
) -> None:
    ordered = sorted(documents, key=lambda item: (item.language, item.url))
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent)
    )
    backup = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}-previous-", dir=output_dir.parent)
    )
    preserve_recovery = False
    try:
        entries: list[ManifestEntry] = []
        rendered_documents: list[str] = []
        for document in ordered:
            relative_path = _document_relative_path(document)
            destination = temporary / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            rendered = render_document(document)
            _ = destination.write_text(rendered, encoding="utf-8", newline="\n")
            entries.append(_manifest_entry(document, relative_path))
            rendered_documents.append(rendered.rstrip())
        manifest = WebsiteManifest(
            base_url=BASE_URL,
            document_count=len(entries),
            documents=tuple(entries),
            rest_totals=dict(sorted(rest_totals.items())),
        )
        _ = (temporary / "manifest.json").write_text(
            manifest.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        combined = "\n\n---\n\n".join(rendered_documents)
        _ = (temporary / "finki-website.md").write_text(
            f"{combined}\n" if combined else "",
            encoding="utf-8",
            newline="\n",
        )
        had_output = output_dir.exists()
        if had_output:
            _ = shutil.copytree(output_dir, backup, dirs_exist_ok=True)
        try:
            _install_snapshot(temporary, output_dir)
        except OSError as install_error:
            try:
                if had_output:
                    _install_snapshot(backup, output_dir)
                elif output_dir.exists():
                    shutil.rmtree(output_dir)
            except OSError as rollback_error:
                preserve_recovery = True
                raise ExceptionGroup(
                    "website output installation and rollback both failed",
                    [install_error, rollback_error],
                ) from install_error
            raise
    finally:
        if temporary.exists() and not preserve_recovery:
            shutil.rmtree(temporary)
        if backup.exists() and not preserve_recovery:
            shutil.rmtree(backup)


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
        follow_redirects=True,
        headers=headers,
        timeout=timeout,
        transport=transport,
    ) as client:
        inventory = await fetch_rest_inventory(client)
        complete_rest_urls = frozenset(
            url
            for url, record in inventory.records_by_url.items()
            if record.content and record.content.rendered.strip()
        )
        empty_rest_urls = tuple(
            url for url in inventory.records_by_url if url not in complete_rest_urls
        )
        plan = CrawlPlan(
            seed_urls=(BASE_URL, f"{BASE_URL}en/", *empty_rest_urls),
            excluded_urls=complete_rest_urls,
            max_pages=max_pages,
        )
        pages = await crawl_pages(client, plan)
    documents = build_documents(inventory, pages)
    write_output(output_dir, documents, inventory.totals)
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
