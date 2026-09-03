from __future__ import annotations

import re
import tempfile
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
    OutputState,
    hold_directory,
    identity,
    is_link,
    validate_output,
    validate_staging,
    write_new_text,
)
from tools.website_output_publish import commit_snapshot

__all__ = ["OutputSafetyError", "write_output"]


def _document_relative_path(document: WebsiteDocument) -> Path:
    parsed = urlsplit(document.url)
    identity_text = unquote(f"{parsed.path}-{parsed.query}").casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", identity_text).strip("-") or "home"
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


def _write_output_locked(
    state: OutputState,
    documents: Iterable[WebsiteDocument],
    metadata: GenerationMetadata,
) -> None:
    ordered = sorted(documents, key=lambda item: (item.language, item.url))
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{state.path.name}-", dir=state.path.parent)
    )
    temporary_identity = identity(temporary)
    if temporary_identity is None:
        raise OutputSafetyError(path=temporary, reason="staging directory unavailable")
    entries: list[ManifestEntry] = []
    with hold_directory(temporary):
        with (temporary / "finki-website.md").open(
            "x",
            encoding="utf-8",
            newline="\n",
        ) as combined:
            for document in ordered:
                relative_path = _document_relative_path(document)
                destination = temporary / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                rendered = render_document(document)
                write_new_text(destination, rendered)
                if entries:
                    _ = combined.write("\n---\n\n")
                _ = combined.write(f"{rendered.rstrip()}\n")
                entries.append(_manifest_entry(document, relative_path))
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
        write_new_text(
            temporary / "manifest.json",
            manifest.model_dump_json(indent=2) + "\n",
        )
        temporary_signature = validate_staging(temporary, temporary_identity)
    commit_snapshot(
        state,
        temporary,
        temporary_identity,
        temporary_signature,
    )


def write_output(
    output_dir: Path,
    documents: Iterable[WebsiteDocument],
    metadata: GenerationMetadata,
) -> None:
    initial = validate_output(output_dir)
    initial.path.parent.mkdir(parents=True, exist_ok=True)
    state = validate_output(output_dir)
    if (
        state.identity != initial.identity
        or state.tree_signature != initial.tree_signature
    ):
        raise OutputSafetyError(path=state.path, reason="changed during generation")
    with hold_directory(state.path.parent):
        if (
            is_link(state.path.parent)
            or identity(state.path.parent) != state.parent_identity
        ):
            raise OutputSafetyError(
                path=state.path.parent,
                reason="link or junction in path",
            )
        _write_output_locked(state, documents, metadata)
