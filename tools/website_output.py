from __future__ import annotations

import os
import re
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Final, final, override
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

_RENAME_ATTEMPTS: Final = 3
_RENAME_DELAY_SECONDS: Final = 0.05


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
    parent_identity: tuple[int, int] | None
    path: Path
    tree_signature: tuple[tuple[str, int, int, int, int], ...] | None


def _identity(path: Path) -> tuple[int, int] | None:
    try:
        status = path.lstat()
    except FileNotFoundError:
        return None
    return status.st_dev, status.st_ino


def _tree_signature(path: Path) -> tuple[tuple[str, int, int, int, int], ...] | None:
    if _identity(path) is None:
        return None
    try:
        entries = (path, *sorted(path.rglob("*")))
        return tuple(
            (
                entry.relative_to(path).as_posix(),
                status.st_ino,
                status.st_mode,
                status.st_size,
                status.st_mtime_ns,
            )
            for entry in entries
            for status in (entry.lstat(),)
        )
    except OSError as error:
        raise OutputSafetyError(
            path=path, reason="changed during generation"
        ) from error


def _rename(source: Path, destination: Path) -> None:
    source_identity = _identity(source)
    destination_identity = _identity(destination)
    for attempt in range(_RENAME_ATTEMPTS):
        try:
            os.rename(source, destination)
            return
        except PermissionError:
            if attempt + 1 == _RENAME_ATTEMPTS:
                raise
            if (
                _identity(source) != source_identity
                or _identity(destination) != destination_identity
            ):
                raise OutputSafetyError(
                    path=source,
                    reason="changed during rename retry",
                ) from None
            time.sleep(_RENAME_DELAY_SECONDS)


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
        return _OutputState(
            identity=None,
            parent_identity=_identity(absolute.parent),
            path=absolute,
            tree_signature=None,
        )
    if not absolute.is_dir():
        raise OutputSafetyError(path=absolute, reason="target is not a directory")
    entries = tuple(absolute.iterdir())
    if not entries:
        return _OutputState(
            identity=identity,
            parent_identity=_identity(absolute.parent),
            path=absolute,
            tree_signature=_tree_signature(absolute),
        )
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
    return _OutputState(
        identity=identity,
        parent_identity=_identity(absolute.parent),
        path=absolute,
        tree_signature=_tree_signature(absolute),
    )


def _commit_snapshot(state: _OutputState, snapshot: Path) -> None:
    current_identity = _identity(state.path)
    if (
        current_identity != state.identity
        or _identity(state.path.parent) != state.parent_identity
        or _tree_signature(state.path) != state.tree_signature
    ):
        raise OutputSafetyError(path=state.path, reason="changed during generation")
    recovery = Path(
        tempfile.mkdtemp(prefix=f".{state.path.name}-recovery-", dir=state.path.parent)
    )
    previous = recovery / "previous"
    if state.identity is not None:
        _rename(state.path, previous)
        if (
            _identity(previous) != state.identity
            or _tree_signature(previous) != state.tree_signature
        ):
            _rename(previous, state.path)
            recovery.rmdir()
            raise OutputSafetyError(
                path=state.path,
                reason="changed during generation",
            )
    try:
        _rename(snapshot, state.path)
    except OSError as install_error:
        if state.identity is not None:
            try:
                _rename(previous, state.path)
            except OSError as rollback_error:
                raise rollback_error from install_error
        recovery.rmdir()
        raise
    if state.identity is None:
        recovery.rmdir()


def write_output(
    output_dir: Path,
    documents: Iterable[WebsiteDocument],
    metadata: GenerationMetadata,
) -> None:
    state = _validate_output(output_dir)
    ordered = sorted(documents, key=lambda item: (item.language, item.url))
    state.path.parent.mkdir(parents=True, exist_ok=True)
    state = replace(state, parent_identity=_identity(state.path.parent))
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{state.path.name}-", dir=state.path.parent)
    )
    entries: list[ManifestEntry] = []
    with (temporary / "finki-website.md").open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as combined:
        for document in ordered:
            relative_path = _document_relative_path(document)
            destination = temporary / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            rendered = render_document(document)
            _ = destination.write_text(rendered, encoding="utf-8", newline="\n")
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
    _ = (temporary / "manifest.json").write_text(
        manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _commit_snapshot(state, temporary)
