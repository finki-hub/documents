from __future__ import annotations

import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

from tools.website_output_paths import OutputSafetyError, identity, is_link

_LOCK_RETRY_SECONDS: Final = 0.05
_LOCK_TIMEOUT_SECONDS: Final = 10.0


def _lock_file(file_descriptor: int) -> None:
    deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
    while True:
        try:
            if os.name == "nt":
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
    if os.name == "nt":
        import msvcrt

        _ = os.lseek(file_descriptor, 0, os.SEEK_SET)
        msvcrt.locking(file_descriptor, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(file_descriptor, fcntl.LOCK_UN)


@contextmanager
def publication_lock(output_path: Path) -> Generator[None]:
    lock_path = output_path.parent / f".{output_path.name}.lock"
    if is_link(lock_path):
        raise OutputSafetyError(path=lock_path, reason="link or junction in path")
    flags = os.O_RDWR | os.O_CREAT
    if os.name != "nt":
        flags |= os.O_NOFOLLOW
    created = False
    try:
        try:
            file_descriptor = os.open(lock_path, flags | os.O_EXCL, 0o600)
            created = True
        except FileExistsError:
            file_descriptor = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise OutputSafetyError(path=lock_path, reason="publication locked") from error
    locked = False
    try:
        status = os.fstat(file_descriptor)
        if is_link(lock_path) or identity(lock_path) != (status.st_dev, status.st_ino):
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
