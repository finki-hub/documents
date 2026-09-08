"""Export the repository's reviewed corpus as a deterministic RAG bundle.

The repository content directories are the authority.  This exporter discovers
processed Markdown documents and pages in the checked-in website aggregate; it
does not consult a second source allowlist or use the current date to decide
which content is eligible.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Final

from . import document_metadata, website_privacy, website_reference

_RELEASE_SCHEMA_VERSION: Final = 2
_LEGAL_SOURCE_CLASS: Final = "official_legal"
_WEBSITE_SOURCE_CLASS: Final = "official_website_informational"


class BundleValidationError(ValueError):
    """Raised when a corpus release is incomplete or unsafe."""


@dataclass(frozen=True, slots=True)
class CorpusEntry:
    name: str
    title: str
    content: str
    metadata: dict[str, str]
    content_sha256: str
    metadata_sha256: str


@dataclass(frozen=True, slots=True)
class CorpusBundle:
    source_commit: str
    source_tree_sha256: str
    entries: tuple[CorpusEntry, ...]


def _fail(message: str) -> BundleValidationError:
    return BundleValidationError(f"invalid RAG corpus bundle: {message}")


def _canonical_markdown(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip() + "\n"


def _hash_text(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def bundle_sha256(bundle_json: str | bytes) -> str:
    """Return the checksum of the exact canonical bundle bytes."""
    encoded = (
        bundle_json.encode("utf-8") if isinstance(bundle_json, str) else bundle_json
    )
    return sha256(encoded).hexdigest()


def _hash_metadata(metadata: Mapping[str, str]) -> str:
    encoded = json.dumps(
        dict(metadata), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return _hash_text(encoded)


def _read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", newline="")
    except (OSError, UnicodeDecodeError) as exc:
        raise _fail(f"cannot read corpus source {path}: {exc}") from exc


def _relative_source_path(root: Path, path: Path) -> str:
    try:
        return path.absolute().relative_to(root.absolute()).as_posix()
    except ValueError as exc:
        raise _fail(f"corpus source escapes repository: {path}") from exc


def _reject_symlink_path(root: Path, path: Path, *, label: str) -> None:
    absolute = path.absolute()
    root_absolute = root.absolute()
    try:
        relative = absolute.relative_to(root_absolute)
    except ValueError as exc:
        raise _fail(f"{label} escapes repository: {path}") from exc
    current = root_absolute
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise _fail(f"{label} must not contain symlinks: {path}")


def _input_directory(root: Path, name: str, *, required: bool) -> Path | None:
    directory = root / name
    if not directory.exists():
        if required:
            raise _fail(f"missing corpus input directory: {name}/")
        return None
    if not directory.is_dir():
        raise _fail(f"corpus input is not a directory: {name}/")
    _reject_symlink_path(root, directory, label=f"{name}/")
    try:
        directory.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise _fail(f"{name}/ escapes repository") from exc
    return directory


def _reject_symlinks_in_directory(root: Path, directory: Path, *, label: str) -> None:
    for path in directory.rglob("*"):
        if path.is_symlink():
            _reject_symlink_path(root, path, label=label)


def _raw_reference_path(root: Path, raw_directory: Path, source: str) -> Path:
    if "\\" in source:
        raise _fail(f"raw source path is unsafe: {source!r}")
    parsed = PurePosixPath(source)
    windows_parsed = PureWindowsPath(source)
    if (
        parsed.is_absolute()
        or windows_parsed.is_absolute()
        or windows_parsed.drive
        or not parsed.parts
        or parsed.as_posix() != source
        or any(part in {"", ".", ".."} for part in parsed.parts)
    ):
        raise _fail(f"raw source path is unsafe: {source!r}")
    path = raw_directory.joinpath(*parsed.parts)
    _reject_symlink_path(root, path, label="raw source")
    try:
        path.resolve().relative_to(raw_directory.resolve())
    except ValueError as exc:
        raise _fail(f"raw source path escapes raw/: {source!r}") from exc
    if not path.is_file():
        raise _fail(f"missing raw source {source!r}")
    return path


def _raw_provenance_paths(
    root: Path, document_paths: Sequence[Path]
) -> tuple[Path, ...]:
    raw_directory = _input_directory(root, "raw", required=True)
    assert raw_directory is not None
    paths: set[Path] = set()
    for document_path in document_paths:
        content = _read_utf8(document_path)
        for source in document_metadata.source_filenames(content):
            paths.add(_raw_reference_path(root, raw_directory, source))
    return tuple(sorted(paths, key=lambda path: _relative_source_path(root, path)))


def _legal_entry(root: Path, path: Path) -> CorpusEntry:
    content = _read_utf8(path)
    try:
        fields = document_metadata.header_fields(content, path.name)
        document_metadata.validate_document(path)
    except document_metadata.MetadataError as exc:
        raise _fail(str(exc)) from exc

    source_files = document_metadata.source_filenames(content)

    relative = _relative_source_path(root, path)
    metadata = document_metadata.ingest_metadata(content)
    metadata.update(
        {
            "source_path": relative,
            "source_url": fields["authority_url"],
            "source_class": _LEGAL_SOURCE_CLASS,
            "authority_rank": "primary",
        }
    )
    if source_files:
        metadata["source_files"] = ",".join(source_files)
    emitted = _canonical_markdown(content)
    relative_document = Path(relative).relative_to("processed")
    name = f"legal/{relative_document.with_suffix('').as_posix()}"
    return CorpusEntry(
        name=name,
        title=fields["title"],
        content=emitted,
        metadata=metadata,
        content_sha256=_hash_text(emitted),
        metadata_sha256=_hash_metadata(metadata),
    )


def _website_entry(
    root: Path, aggregate: Path, page: website_reference.ReferencePage
) -> CorpusEntry:
    relative = _relative_source_path(root, aggregate)
    metadata = {
        "source_id": page.source_id,
        "source_path": relative,
        "authority_url": page.canonical_url,
        "source_url": page.source_url,
        "source_class": _WEBSITE_SOURCE_CLASS,
        "authority_rank": "informational",
        "current_status": "informational",
        "last_verified": page.last_verified.isoformat(),
        "canonical_url": page.canonical_url,
        "language": page.language,
        "category": page.category,
        "content_kind": page.content_kind,
    }
    emitted = _canonical_markdown(page.body)
    return CorpusEntry(
        name=f"website/{page.source_id}",
        title=page.title,
        content=emitted,
        metadata=metadata,
        content_sha256=_hash_text(emitted),
        metadata_sha256=_hash_metadata(metadata),
    )


def _discover_entries(root: Path) -> tuple[CorpusEntry, ...]:
    processed = _input_directory(root, "processed", required=True)
    assert processed is not None
    _reject_symlinks_in_directory(root, processed, label="processed corpus input")
    document_paths = sorted(path for path in processed.rglob("*.md") if path.is_file())
    if not document_paths:
        raise _fail(f"{processed}: no Markdown documents found")
    for path in document_paths:
        _reject_symlink_path(root, path, label="processed corpus input")
    _raw_provenance_paths(root, document_paths)

    entries = [_legal_entry(root, path) for path in document_paths]
    website_root = _input_directory(root, "website-reference", required=False)
    if website_root is not None:
        _reject_symlinks_in_directory(root, website_root, label="website corpus input")
        for aggregate in sorted(website_root.rglob("*.md")):
            if not aggregate.is_file():
                continue
            _reject_symlink_path(root, aggregate, label="website corpus input")
            text = _read_utf8(aggregate).replace("\r\n", "\n").replace("\r", "\n")
            if "<!-- finki-static-page:" not in text:
                continue
            try:
                pages = website_reference.parse_aggregate(text)
            except ValueError as exc:
                raise _fail(str(exc)) from exc
            seen_page_hashes: dict[str, str] = {}
            for page in pages:
                if website_privacy.contains_sensitive_personal_identifier(
                    title=page.title, markdown=page.body
                ):
                    raise _fail(
                        f"page {page.source_id} contains a sensitive identifier"
                    )
                duplicate_id = seen_page_hashes.get(page.content_sha256)
                if duplicate_id is not None:
                    raise _fail(
                        f"duplicate normalized content for {page.source_id} and {duplicate_id}"
                    )
                seen_page_hashes[page.content_sha256] = page.source_id
            entries.extend(_website_entry(root, aggregate, page) for page in pages)

    names = [entry.name for entry in entries]
    if len(set(names)) != len(names):
        raise _fail("discovered entry names must be unique")
    return tuple(sorted(entries, key=lambda entry: entry.name))


def _processed_files(root: Path) -> tuple[Path, ...]:
    processed = _input_directory(root, "processed", required=True)
    assert processed is not None
    _reject_symlinks_in_directory(root, processed, label="processed corpus input")
    processed_files = tuple(path for path in processed.rglob("*.md") if path.is_file())
    for path in processed_files:
        _reject_symlink_path(root, path, label="processed corpus input")
    return tuple(
        sorted(processed_files, key=lambda path: _relative_source_path(root, path))
    )


def _website_files(root: Path) -> tuple[Path, ...]:
    website_root = _input_directory(root, "website-reference", required=False)
    if website_root is None:
        return ()
    _reject_symlinks_in_directory(root, website_root, label="website corpus input")
    website_files = tuple(path for path in website_root.rglob("*.md") if path.is_file())
    for path in website_files:
        _reject_symlink_path(root, path, label="website corpus input")
    return tuple(
        sorted(website_files, key=lambda path: _relative_source_path(root, path))
    )


def _corpus_files(root: Path) -> tuple[Path, ...]:
    return _processed_files(root) + _website_files(root)


def _git_executable() -> str:
    git = shutil.which("git")
    if git is None:
        raise _fail("git executable is required for corpus export")
    return git


def _head_corpus_inventory(root: Path) -> tuple[str, ...]:
    git = _git_executable()
    try:
        result = subprocess.run(
            [
                git,
                "ls-tree",
                "--full-tree",
                "-r",
                "--name-only",
                "-z",
                "HEAD",
                "--",
                "processed",
                "website-reference",
            ],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _fail(f"cannot derive corpus inventory from HEAD: {exc}") from exc
    try:
        names = result.stdout.decode("utf-8").split("\0")
    except UnicodeDecodeError as exc:
        raise _fail("HEAD corpus inventory is not UTF-8") from exc
    return tuple(sorted(name for name in names if name.endswith(".md")))


def _validate_head_corpus_inventory(root: Path, corpus_files: Sequence[Path]) -> None:
    expected = set(_head_corpus_inventory(root))
    actual = {_relative_source_path(root, path) for path in corpus_files}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        detail = (
            f"missing from worktree {missing}" if missing else f"not in HEAD {extra}"
        )
        raise _fail(f"materialized corpus inventory differs from HEAD: {detail}")


def _source_files(root: Path) -> tuple[Path, ...]:
    processed_files = _processed_files(root)
    files: list[Path] = list(_corpus_files(root))
    files.extend(_raw_provenance_paths(root, processed_files))
    return tuple(sorted(files, key=lambda path: _relative_source_path(root, path)))


def _source_tree_sha256(root: Path) -> str:
    digest = sha256()
    digest.update(b"finki-hub-rag-corpus-source-tree-v3\0")
    for path in _source_files(root):
        relative = _relative_source_path(root, path)
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise _fail(
                f"cannot read source snapshot file {relative!r}: {exc}"
            ) from exc
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def _git_worktree_status(repo_root: Path) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(
            [git, "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError, subprocess.CalledProcessError:
        return None
    return result.stdout


def _git_head(repo_root: Path) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(
            [git, "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError, subprocess.CalledProcessError:
        return None
    commit = result.stdout.strip()
    if len(commit) != 40 or any(
        character not in "0123456789abcdef" for character in commit
    ):
        return None
    return commit


def _validate_git_inputs(root: Path, paths: Sequence[Path]) -> None:
    git = _git_executable()
    relatives = tuple(_relative_source_path(root, path) for path in paths)
    try:
        status = subprocess.run(
            [
                git,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignored=matching",
                "--",
                *relatives,
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _fail(f"cannot inspect corpus input status: {exc}") from exc
    if status:
        raise _fail(
            f"corpus inputs must be tracked at HEAD and clean: {status.strip()}"
        )

    for path, relative in zip(paths, relatives, strict=True):
        try:
            subprocess.run(
                [git, "cat-file", "-e", f"HEAD:{relative}"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            head_content = subprocess.run(
                [git, "show", f"HEAD:{relative}"],
                cwd=root,
                check=True,
                capture_output=True,
            ).stdout
            current_content = path.read_bytes()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise _fail(f"corpus input is not tracked at HEAD: {relative}") from exc
        if current_content != head_content:
            raise _fail(f"corpus input does not match HEAD: {relative}")


def _working_tree_revision(status: str | None, source_tree: str) -> str:
    digest = sha256()
    digest.update(b"finki-hub-rag-corpus-working-tree-v2\0")
    digest.update((status or "non-git").encode("utf-8"))
    digest.update(b"\0")
    digest.update(source_tree.encode("ascii"))
    return f"WORKTREE-{digest.hexdigest()}"


def build_bundle(repo_root: Path) -> CorpusBundle:
    """Discover every reviewed document/page and build its deterministic payload."""
    root = repo_root.resolve()
    corpus_files = _corpus_files(root)
    _validate_head_corpus_inventory(root, corpus_files)
    source_files = _source_files(root)
    _validate_git_inputs(root, source_files)
    entries = _discover_entries(root)
    source_tree = _source_tree_sha256(root)
    status = _git_worktree_status(root)
    source_commit = _git_head(root) if status == "" else None
    if source_commit is None:
        source_commit = _working_tree_revision(status, source_tree)
    return CorpusBundle(
        source_commit=source_commit,
        source_tree_sha256=source_tree,
        entries=entries,
    )


def _json_entry(entry: CorpusEntry) -> dict[str, object]:
    if entry.content_sha256 != _hash_text(entry.content):
        raise _fail(f"content hash mismatch for {entry.name}")
    if entry.metadata_sha256 != _hash_metadata(entry.metadata):
        raise _fail(f"metadata hash mismatch for {entry.name}")
    return {
        "name": entry.name,
        "title": entry.title,
        "content": entry.content,
        "metadata": entry.metadata,
        "content_sha256": entry.content_sha256,
        "metadata_sha256": entry.metadata_sha256,
    }


def serialize_bundle(bundle: CorpusBundle, *, release: bool = False) -> str:
    """Serialize a bundle as canonical UTF-8 JSON with a trailing LF."""
    if release and bundle.source_commit.startswith("WORKTREE-"):
        raise _fail("release export requires a clean pinned source revision")
    payload = {
        "schema_version": _RELEASE_SCHEMA_VERSION,
        "source_revision": bundle.source_commit,
        "source_tree_sha256": bundle.source_tree_sha256,
        "entries": [_json_entry(entry) for entry in bundle.entries],
    }
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )


def export_release_bundle(bundle: CorpusBundle) -> str:
    """Serialize a bundle for importer consumption after release checks."""
    return serialize_bundle(bundle, release=True)


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release",
        action="store_true",
        help="emit the complete release bundle on stdout and reports on stderr",
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    arguments = parser.parse_args(argv)
    if arguments.release:
        status = _git_worktree_status(arguments.repo_root.resolve())
        if status != "":
            raise _fail("release export requires a whole repository clean checkout")
        bundle = build_bundle(arguments.repo_root)
        encoded = export_release_bundle(bundle)
        print(f"source_revision={bundle.source_commit}", file=sys.stderr)
        print(f"source_tree_sha256={bundle.source_tree_sha256}", file=sys.stderr)
        print(f"bundle_sha256={bundle_sha256(encoded)}", file=sys.stderr)
        print(f"entries={len(bundle.entries)}", file=sys.stderr)
        stdout_buffer = getattr(sys.stdout, "buffer", None)
        if stdout_buffer is None:
            sys.stdout.write(encoded)
        else:
            stdout_buffer.write(encoded.encode("utf-8"))
            stdout_buffer.flush()
        return 0
    bundle = build_bundle(arguments.repo_root)
    print(f"source_revision={bundle.source_commit}")
    print(f"source_tree_sha256={bundle.source_tree_sha256}")
    print(f"bundle_sha256={bundle_sha256(serialize_bundle(bundle))}")
    print(f"entries={len(bundle.entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
