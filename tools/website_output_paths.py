from __future__ import annotations

import os
import secrets
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, final, override

from pydantic import ValidationError

from tools.website_models import WebsiteManifest

TreeSignature = tuple[tuple[str, int, int, int, int], ...]
_TEMPORARY_DIRECTORY_ATTEMPTS: Final = 100


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


@dataclass(frozen=True, slots=True)
class OutputState:
    identity: tuple[int, int] | None
    parent_identity: tuple[int, int] | None
    path: Path
    tree_signature: TreeSignature | None


def is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def identity(path: Path) -> tuple[int, int] | None:
    try:
        status = path.lstat()
    except FileNotFoundError:
        return None
    return status.st_dev, status.st_ino


def tree_signature(path: Path) -> TreeSignature | None:
    if identity(path) is None:
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


@contextmanager
def hold_directory(path: Path) -> Generator[int | None]:
    if os.name != "nt":
        before = identity(path)
        if before is None or is_link(path):
            raise OutputSafetyError(path=path, reason="directory changed")
        try:
            file_descriptor = os.open(
                path,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        except OSError as error:
            raise OutputSafetyError(path=path, reason="directory changed") from error
        try:
            status = os.fstat(file_descriptor)
            if (status.st_dev, status.st_ino) != before:
                raise OutputSafetyError(path=path, reason="directory changed")
            yield file_descriptor
        finally:
            os.close(file_descriptor)
        return

    import _winapi

    handle = _winapi.CreateFile(
        str(path),
        0,
        0x00000001 | 0x00000002,
        0,
        3,
        0x02000000,
        0,
    )
    try:
        yield None
    finally:
        _winapi.CloseHandle(handle)


def make_temporary_directory(
    parent: Path,
    prefix: str,
    parent_descriptor: int | None,
) -> Path:
    if parent_descriptor is None:
        return Path(tempfile.mkdtemp(prefix=prefix, dir=parent))
    for _attempt in range(_TEMPORARY_DIRECTORY_ATTEMPTS):
        name = f"{prefix}{secrets.token_hex(8)}"
        try:
            os.mkdir(name, dir_fd=parent_descriptor)
        except FileExistsError:
            continue
        except OSError as error:
            raise OutputSafetyError(
                path=parent / name,
                reason="temporary directory unavailable",
            ) from error
        return parent / name
    raise OutputSafetyError(
        path=parent,
        reason="temporary directory unavailable",
    )


def validate_staging(path: Path, expected_identity: tuple[int, int]) -> TreeSignature:
    if identity(path) != expected_identity:
        raise OutputSafetyError(path=path, reason="staging directory changed")
    try:
        for entry in path.rglob("*"):
            if is_link(entry):
                raise OutputSafetyError(
                    path=entry,
                    reason="link or junction in staging directory",
                )
    except OSError as error:
        raise OutputSafetyError(
            path=path, reason="staging directory changed"
        ) from error
    signature = tree_signature(path)
    if signature is None:
        raise OutputSafetyError(path=path, reason="staging directory changed")
    return signature


def is_generator_output(path: Path) -> bool:
    try:
        manifest = WebsiteManifest.model_validate_json(
            (path / "manifest.json").read_bytes()
        )
    except OSError, ValidationError:
        return False
    return manifest.generator == "finki-website-content"


def validate_output(output_dir: Path) -> OutputState:
    lexical = output_dir.absolute()
    for path in (lexical, *lexical.parents):
        if os.path.lexists(path) and is_link(path):
            raise OutputSafetyError(path=path, reason="link or junction in path")
    absolute = lexical.resolve(strict=False)
    if absolute == Path.cwd().resolve() or absolute == Path(absolute.anchor):
        raise OutputSafetyError(path=output_dir, reason="protected path")
    output_identity = identity(absolute)
    if output_identity is None:
        return OutputState(
            identity=None,
            parent_identity=identity(absolute.parent),
            path=absolute,
            tree_signature=None,
        )
    if not absolute.is_dir():
        raise OutputSafetyError(path=absolute, reason="target is not a directory")
    entries = tuple(absolute.iterdir())
    if not entries:
        return OutputState(
            identity=output_identity,
            parent_identity=identity(absolute.parent),
            path=absolute,
            tree_signature=tree_signature(absolute),
        )
    for path in absolute.rglob("*"):
        if is_link(path):
            raise OutputSafetyError(path=path, reason="link or junction in output")
    try:
        manifest = WebsiteManifest.model_validate_json(
            (absolute / "manifest.json").read_bytes()
        )
    except (OSError, ValidationError) as error:
        raise OutputSafetyError(
            path=absolute, reason="missing ownership manifest"
        ) from error
    if manifest.generator != "finki-website-content":
        raise OutputSafetyError(path=absolute, reason="foreign ownership manifest")
    return OutputState(
        identity=output_identity,
        parent_identity=identity(absolute.parent),
        path=absolute,
        tree_signature=tree_signature(absolute),
    )
