from __future__ import annotations

import os
import stat
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

from tools.website_output_paths import OutputSafetyError, is_link

_LOCK_RETRY_SECONDS: Final = 0.05
_LOCK_TIMEOUT_SECONDS: Final = 10.0


def _lock_file(file_descriptor: int) -> None:
    deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
    while True:
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(file_descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(_LOCK_RETRY_SECONDS)


def _unlock_file(file_descriptor: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        _ = os.lseek(file_descriptor, 0, os.SEEK_SET)
        msvcrt.locking(file_descriptor, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(file_descriptor, fcntl.LOCK_UN)


@contextmanager
def publication_lock(
    output_path: Path,
    parent_descriptor: int | None = None,
) -> Generator[None]:
    lock_path = output_path.parent / f".{output_path.name}.lock"
    if parent_descriptor is None and is_link(lock_path):
        raise OutputSafetyError(path=lock_path, reason="link or junction in path")
    lock_target: str | Path = (
        lock_path.name if parent_descriptor is not None else lock_path
    )
    flags = os.O_RDWR | os.O_CREAT
    if sys.platform != "win32":
        flags |= os.O_NOFOLLOW
    created = False
    try:
        try:
            file_descriptor = os.open(
                lock_target,
                flags | os.O_EXCL,
                0o600,
                dir_fd=parent_descriptor,
            )
            created = True
        except FileExistsError:
            file_descriptor = os.open(
                lock_target,
                flags,
                0o600,
                dir_fd=parent_descriptor,
            )
    except OSError as error:
        raise OutputSafetyError(path=lock_path, reason="publication locked") from error
    locked = False
    try:
        status = os.fstat(file_descriptor)
        path_status = (
            lock_path.lstat()
            if parent_descriptor is None
            else os.stat(
                lock_path.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        )
        if stat.S_ISLNK(path_status.st_mode) or (
            path_status.st_dev,
            path_status.st_ino,
        ) != (status.st_dev, status.st_ino):
            raise OutputSafetyError(path=lock_path, reason="lock file changed")
        if created:
            _ = os.write(file_descriptor, b"\0")
        _ = os.lseek(file_descriptor, 0, os.SEEK_SET)
        try:
            _lock_file(file_descriptor)
        except OSError as error:
            raise OutputSafetyError(
                path=lock_path,
                reason="publication locked",
            ) from error
        locked = True
        yield
    finally:
        try:
            if locked:
                _unlock_file(file_descriptor)
        finally:
            os.close(file_descriptor)
