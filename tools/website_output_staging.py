from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import ExitStack, contextmanager, suppress
from pathlib import Path
from typing import IO, Final

from tools.website_output_paths import OutputSafetyError, identity, is_link

_WINDOWS_SHARE_READ_WRITE: Final = 0x00000001 | 0x00000002
_WINDOWS_OPEN_EXISTING: Final = 3
_WINDOWS_OPEN_DIRECTORY: Final = 0x02000000
_WINDOWS_OPEN_REPARSE_POINT: Final = 0x00200000


def _write_stream(output: IO[str], content: str) -> None:
    _ = output.write(content)


@contextmanager
def _hold_windows_directory(
    path: Path,
    expected_identity: tuple[int, int] | None = None,
) -> Generator[None]:
    import _winapi
    import msvcrt

    before = identity(path)
    if before is None or is_link(path):
        raise OutputSafetyError(path=path, reason="staging path changed")
    try:
        handle = _winapi.CreateFile(
            str(path),
            0,
            _WINDOWS_SHARE_READ_WRITE,
            0,
            _WINDOWS_OPEN_EXISTING,
            _WINDOWS_OPEN_DIRECTORY | _WINDOWS_OPEN_REPARSE_POINT,
            0,
        )
    except OSError as error:
        raise OutputSafetyError(path=path, reason="staging path changed") from error
    try:
        file_descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY)
    except OSError as error:
        _winapi.CloseHandle(handle)
        raise OutputSafetyError(path=path, reason="staging path changed") from error
    try:
        status = os.fstat(file_descriptor)
        if (
            (status.st_dev, status.st_ino) != before
            or identity(path) != before
            or is_link(path)
            or (expected_identity is not None and before != expected_identity)
        ):
            raise OutputSafetyError(path=path, reason="staging path changed")
        yield
    finally:
        os.close(file_descriptor)


def _write_windows(
    root: Path,
    relative_path: Path,
    content: str,
    root_identity: tuple[int, int],
) -> None:
    current = root
    try:
        with ExitStack() as stack:
            stack.enter_context(_hold_windows_directory(root, root_identity))
            for component in relative_path.parent.parts:
                current /= component
                current.mkdir(exist_ok=True)
                stack.enter_context(_hold_windows_directory(current))
            with (current / relative_path.name).open(
                "x",
                encoding="utf-8",
                newline="\n",
            ) as output:
                _write_stream(output, content)
    except OutputSafetyError:
        raise
    except OSError as error:
        raise OutputSafetyError(
            path=root / relative_path,
            reason="staging path changed",
        ) from error


def _write_posix(
    root: Path,
    relative_path: Path,
    content: str,
    root_identity: tuple[int, int],
) -> None:
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        with ExitStack() as stack:
            directory = os.open(root, directory_flags)
            _ = stack.callback(os.close, directory)
            status = os.fstat(directory)
            if (status.st_dev, status.st_ino) != root_identity:
                raise OutputSafetyError(path=root, reason="staging path changed")
            for component in relative_path.parent.parts:
                with suppress(FileExistsError):
                    os.mkdir(component, dir_fd=directory)
                child = os.open(component, directory_flags, dir_fd=directory)
                _ = stack.callback(os.close, child)
                directory = child
            file_descriptor = os.open(
                relative_path.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o666,
                dir_fd=directory,
            )
            with os.fdopen(
                file_descriptor,
                "w",
                encoding="utf-8",
                newline="\n",
            ) as output:
                _write_stream(output, content)
    except OutputSafetyError:
        raise
    except OSError as error:
        raise OutputSafetyError(
            path=root / relative_path,
            reason="staging path changed",
        ) from error


def write_staged_text(
    root: Path,
    relative_path: Path,
    content: str,
    root_identity: tuple[int, int],
) -> None:
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise OutputSafetyError(path=relative_path, reason="invalid staging path")
    if os.name == "nt":
        _write_windows(root, relative_path, content, root_identity)
        return
    _write_posix(root, relative_path, content, root_identity)
