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
from tools.website_output_lock import publication_lock
from tools.website_output_paths import (
    OutputSafetyError,
    OutputState,
    hold_directory,
    identity,
    is_link,
    make_temporary_directory,
    validate_output,
    validate_staging,
)
from tools.website_output_publish import SnapshotPublication, commit_snapshot
from tools.website_output_staging import write_staged_text

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
    parent_descriptor: int | None,
) -> None:
    ordered = sorted(documents, key=lambda item: (item.language, item.url))
    temporary = make_temporary_directory(
        state.path.parent,
        f".{state.path.name}-",
        parent_descriptor,
    )
    temporary_identity = identity(temporary)
    if temporary_identity is None:
        raise OutputSafetyError(path=temporary, reason="staging directory unavailable")
    entries: list[ManifestEntry] = []
    rendered_documents: list[str] = []
    with hold_directory(temporary):
        for document in ordered:
            relative_path = _document_relative_path(document)
            rendered = render_document(document)
            write_staged_text(
                temporary,
                relative_path,
                rendered,
                temporary_identity,
            )
            rendered_documents.append(rendered.rstrip())
            entries.append(_manifest_entry(document, relative_path))
        combined = "\n---\n\n".join(rendered_documents)
        write_staged_text(
            temporary,
            Path("finki-website.md"),
            f"{combined}\n" if combined else "",
            temporary_identity,
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
        write_staged_text(
            temporary,
            Path("manifest.json"),
            manifest.model_dump_json(indent=2) + "\n",
            temporary_identity,
        )
        temporary_signature = validate_staging(temporary, temporary_identity)
    commit_snapshot(
        SnapshotPublication(
            state=state,
            snapshot=temporary,
            snapshot_identity=temporary_identity,
            snapshot_signature=temporary_signature,
            parent_descriptor=parent_descriptor,
        )
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
    with hold_directory(state.path.parent) as parent_descriptor:
        if (
            is_link(state.path.parent)
            or identity(state.path.parent) != state.parent_identity
        ):
            raise OutputSafetyError(
                path=state.path.parent,
                reason="link or junction in path",
            )
        with publication_lock(state.path, parent_descriptor):
            locked_state = validate_output(output_dir)
            if (
                locked_state.identity != state.identity
                or locked_state.parent_identity != state.parent_identity
                or locked_state.tree_signature != state.tree_signature
            ):
                raise OutputSafetyError(
                    path=state.path,
                    reason="changed during generation",
                )
            _write_output_locked(
                locked_state,
                documents,
                metadata,
                parent_descriptor,
            )
