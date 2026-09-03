from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Final, final, override

from pydantic import ValidationError

from tools.website_models import WebsiteManifest

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parent.parent
_PROTECTED_OUTPUT_ROOTS: Final = (
    _REPOSITORY_ROOT / "raw",
    _REPOSITORY_ROOT / "processed",
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


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _reject_links(path: Path, reason: str) -> None:
    if _is_link(path):
        raise OutputSafetyError(path=path, reason=reason)
    try:
        for entry in path.rglob("*"):
            if _is_link(entry):
                raise OutputSafetyError(path=entry, reason=reason)
    except OSError as error:
        raise OutputSafetyError(path=path, reason=reason) from error


def _is_generator_output(path: Path) -> bool:
    try:
        manifest = WebsiteManifest.model_validate_json(
            (path / "manifest.json").read_bytes()
        )
    except OSError, ValidationError:
        return False
    return manifest.generator == "finki-website-content"


def make_temporary_directory(parent: Path, prefix: str) -> Path:
    try:
        return Path(tempfile.mkdtemp(prefix=prefix, dir=parent))
    except OSError as error:
        raise OutputSafetyError(
            path=parent,
            reason="temporary directory unavailable",
        ) from error


def validate_staging(path: Path) -> None:
    if not path.is_dir():
        raise OutputSafetyError(path=path, reason="staging directory unavailable")
    _reject_links(path, "link or junction in staging directory")
    if not _is_generator_output(path):
        raise OutputSafetyError(path=path, reason="invalid staging manifest")


def validate_output(output_dir: Path) -> Path:
    lexical = output_dir.absolute()
    for candidate in (lexical, *lexical.parents):
        if os.path.lexists(candidate) and _is_link(candidate):
            raise OutputSafetyError(path=candidate, reason="link or junction in path")

    output = lexical.resolve(strict=False)
    if (
        output == Path.cwd().resolve()
        or output == Path(output.anchor)
        or any(
            output == root or output.is_relative_to(root)
            for root in _PROTECTED_OUTPUT_ROOTS
        )
    ):
        raise OutputSafetyError(path=output_dir, reason="protected path")
    if not os.path.lexists(output):
        return output
    if not output.is_dir():
        raise OutputSafetyError(path=output, reason="target is not a directory")
    if not any(output.iterdir()):
        return output

    _reject_links(output, "link or junction in output")
    if not _is_generator_output(output):
        raise OutputSafetyError(path=output, reason="missing ownership manifest")
    return output
