from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import final, override
from urllib.parse import unquote, urlsplit

from pydantic import ValidationError

from tools.website_markdown import render_document
from tools.website_models import (
    BASE_URL,
    GenerationMetadata,
    ManifestEntry,
    WebsiteDocument,
    WebsiteManifest,
)


@final
class OutputSafetyError(RuntimeError):
    __slots__ = ("path", "reason")
    path: Path
    reason: str

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(path, reason)

    @override
    def __str__(self) -> str:
        return f"unsafe output directory ({self.reason}): {self.path}"


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


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


@dataclass(frozen=True, slots=True)
class _OutputState:
    identity: tuple[int, int] | None
    path: Path


def _identity(path: Path) -> tuple[int, int] | None:
    try:
        status = path.lstat()
    except FileNotFoundError:
        return None
    return status.st_dev, status.st_ino


def _validate_output(output_dir: Path) -> _OutputState:
    lexical = output_dir.absolute()
    for path in (lexical, *lexical.parents):
        if os.path.lexists(path) and _is_link(path):
            raise OutputSafetyError(path=path, reason="link or junction in path")
    absolute = lexical.resolve(strict=False)
    if absolute == Path.cwd().resolve() or absolute == Path(absolute.anchor):
        raise OutputSafetyError(path=output_dir, reason="protected path")
    identity = _identity(absolute)
    if identity is None:
        return _OutputState(identity=None, path=absolute)
    if not absolute.is_dir():
        raise OutputSafetyError(path=absolute, reason="target is not a directory")
    entries = tuple(absolute.iterdir())
    if not entries:
        return _OutputState(identity=identity, path=absolute)
    for path in absolute.rglob("*"):
        if _is_link(path):
            raise OutputSafetyError(path=path, reason="link or junction in output")
    manifest_path = absolute / "manifest.json"
    try:
        manifest = WebsiteManifest.model_validate_json(manifest_path.read_bytes())
    except (OSError, ValidationError) as error:
        raise OutputSafetyError(
            path=absolute, reason="missing ownership manifest"
        ) from error
    if manifest.generator != "finki-website-content":
        raise OutputSafetyError(path=absolute, reason="foreign ownership manifest")
    return _OutputState(identity=identity, path=absolute)


def _commit_snapshot(state: _OutputState, snapshot: Path) -> None:
    current_identity = _identity(state.path)
    if current_identity != state.identity:
        raise OutputSafetyError(path=state.path, reason="changed during generation")
    recovery = Path(
        tempfile.mkdtemp(prefix=f".{state.path.name}-recovery-", dir=state.path.parent)
    )
    previous = recovery / "previous"
    preserve_recovery = False
    try:
        if state.identity is not None:
            os.rename(state.path, previous)
            if _identity(previous) != state.identity:
                os.rename(previous, state.path)
                raise OutputSafetyError(
                    path=state.path,
                    reason="changed during generation",
                )
        try:
            os.rename(snapshot, state.path)
        except OSError as install_error:
            if state.identity is not None:
                try:
                    os.rename(previous, state.path)
                except OSError as rollback_error:
                    preserve_recovery = True
                    raise rollback_error from install_error
            raise
    finally:
        if not preserve_recovery:
            shutil.rmtree(recovery)


def write_output(
    output_dir: Path,
    documents: Iterable[WebsiteDocument],
    metadata: GenerationMetadata,
) -> None:
    state = _validate_output(output_dir)
    ordered = sorted(documents, key=lambda item: (item.language, item.url))
    state.path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{state.path.name}-", dir=state.path.parent)
    )
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
            crawled_pages=metadata.crawled_pages,
            crawl_truncated=metadata.crawl_truncated,
            document_count=len(entries),
            documents=tuple(entries),
            generator="finki-website-content",
            rest_totals=dict(sorted(metadata.rest_totals.items())),
            schema_version=2,
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
        _commit_snapshot(state, temporary)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
