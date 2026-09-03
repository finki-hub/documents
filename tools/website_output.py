from __future__ import annotations

import re
from collections.abc import Iterable
from hashlib import sha256
from pathlib import Path
from urllib.parse import unquote, urlsplit

from tools.website_markdown import render_document
from tools.website_models import (
    BASE_URL,
    GenerationMetadata,
    ManifestEntry,
    WebsiteDocument,
    WebsiteManifest,
)
from tools.website_output_paths import (
    OutputSafetyError,
    make_temporary_directory,
    validate_output,
    validate_staging,
)

__all__ = ["OutputSafetyError", "write_output"]


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


def _write_staged_text(root: Path, relative_path: Path, content: str) -> None:
    destination = root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as output:
        _ = output.write(content)


def _stage_output(
    output: Path,
    documents: Iterable[WebsiteDocument],
    metadata: GenerationMetadata,
) -> Path:
    staging = make_temporary_directory(output.parent, f".{output.name}-")
    ordered = sorted(documents, key=lambda item: (item.language, item.url))
    entries: list[ManifestEntry] = []
    rendered_documents: list[str] = []

    for document in ordered:
        relative_path = _document_relative_path(document)
        rendered = render_document(document)
        _write_staged_text(staging, relative_path, rendered)
        rendered_documents.append(rendered.rstrip())
        entries.append(_manifest_entry(document, relative_path))

    combined = "\n---\n\n".join(rendered_documents)
    _write_staged_text(
        staging,
        Path("finki-website.md"),
        f"{combined}\n" if combined else "",
    )
    manifest = WebsiteManifest(
        base_url=BASE_URL,
        crawled_pages=metadata.crawled_pages,
        crawl_truncated=metadata.crawl_truncated,
        document_count=len(entries),
        documents=tuple(entries),
        generator="finki-website-content",
        rest_totals=dict(sorted(metadata.rest_totals.items())),
        schema_version=2,
    )
    _write_staged_text(
        staging,
        Path("manifest.json"),
        manifest.model_dump_json(indent=2) + "\n",
    )
    validate_staging(staging)
    return staging


def _publish_snapshot(output: Path, staging: Path) -> None:
    recovery: Path | None = None
    previous: Path | None = None
    if output.exists():
        recovery = make_temporary_directory(
            output.parent,
            f".{output.name}-recovery-",
        )
        previous = recovery / "previous"
        _ = output.rename(previous)

    try:
        _ = staging.rename(output)
    except OSError:
        if previous is not None and not output.exists():
            try:
                _ = previous.rename(output)
            except OSError as rollback_error:
                raise OutputSafetyError(
                    path=output,
                    reason="install failed; previous snapshot preserved in recovery",
                ) from rollback_error
            if recovery is not None:
                recovery.rmdir()
        raise


def write_output(
    output_dir: Path,
    documents: Iterable[WebsiteDocument],
    metadata: GenerationMetadata,
) -> None:
    output = validate_output(output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output = validate_output(output)
    staging = _stage_output(output, documents, metadata)
    _ = validate_output(output)
    _publish_snapshot(output, staging)
