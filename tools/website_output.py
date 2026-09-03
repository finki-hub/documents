from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Iterable
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


def _validate_output(output_dir: Path) -> None:
    absolute = output_dir.absolute()
    if absolute == Path.cwd().absolute() or absolute == Path(absolute.anchor):
        raise OutputSafetyError(path=output_dir, reason="protected path")
    for path in (absolute, *absolute.parents):
        if path.exists() and _is_link(path):
            raise OutputSafetyError(path=path, reason="link or junction in path")
    if not output_dir.exists():
        return
    if not output_dir.is_dir():
        raise OutputSafetyError(path=output_dir, reason="target is not a directory")
    entries = tuple(output_dir.iterdir())
    if not entries:
        return
    for path in output_dir.rglob("*"):
        if _is_link(path):
            raise OutputSafetyError(path=path, reason="link or junction in output")
    manifest_path = output_dir / "manifest.json"
    try:
        manifest = WebsiteManifest.model_validate_json(manifest_path.read_bytes())
    except (OSError, ValidationError) as error:
        raise OutputSafetyError(
            path=output_dir, reason="missing ownership manifest"
        ) from error
    if manifest.generator != "finki-website-content":
        raise OutputSafetyError(path=output_dir, reason="foreign ownership manifest")


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
    for directory in sorted(
        directories, key=lambda path: len(path.parts), reverse=True
    ):
        if not any(directory.iterdir()):
            directory.rmdir()
    _atomic_copy(snapshot / manifest, output_dir / manifest)


def write_output(
    output_dir: Path,
    documents: Iterable[WebsiteDocument],
    metadata: GenerationMetadata,
) -> None:
    _validate_output(output_dir)
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
            crawled_pages=metadata.crawled_pages,
            crawl_truncated=metadata.crawl_truncated,
            document_count=len(entries),
            documents=tuple(entries),
            rest_totals=dict(sorted(metadata.rest_totals.items())),
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
