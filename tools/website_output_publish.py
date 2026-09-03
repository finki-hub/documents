from __future__ import annotations

import os
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from tools.website_output_paths import (
    OutputSafetyError,
    OutputState,
    TreeSignature,
    hold_directory,
    identity,
    is_generator_output,
    make_temporary_directory,
    tree_signature,
)

_RENAME_ATTEMPTS: Final = 3
_RENAME_DELAY_SECONDS: Final = 0.05


@dataclass(frozen=True, slots=True)
class SnapshotPublication:
    state: OutputState
    snapshot: Path
    snapshot_identity: tuple[int, int]
    snapshot_signature: TreeSignature
    parent_descriptor: int | None


@dataclass(frozen=True, slots=True)
class _RenameOperation:
    source: Path
    destination: Path
    expected_source_identity: tuple[int, int] | None = None
    source_descriptor: int | None = None
    destination_descriptor: int | None = None


def _rename(operation: _RenameOperation) -> None:
    source_identity = identity(operation.source)
    if (
        operation.expected_source_identity is not None
        and source_identity != operation.expected_source_identity
    ):
        raise OutputSafetyError(
            path=operation.source,
            reason="staging directory changed",
        )
    destination_identity = identity(operation.destination)
    for attempt in range(_RENAME_ATTEMPTS):
        try:
            if (
                operation.source_descriptor is not None
                and operation.destination_descriptor is not None
            ):
                os.rename(
                    operation.source.name,
                    operation.destination.name,
                    src_dir_fd=operation.source_descriptor,
                    dst_dir_fd=operation.destination_descriptor,
                )
            else:
                os.rename(operation.source, operation.destination)
            if (
                operation.expected_source_identity is not None
                and identity(operation.destination)
                != operation.expected_source_identity
            ):
                raise OutputSafetyError(
                    path=operation.destination,
                    reason="staging directory changed during install",
                )
            return
        except PermissionError:
            if attempt + 1 == _RENAME_ATTEMPTS:
                raise
            if (
                identity(operation.source) != source_identity
                or identity(operation.destination) != destination_identity
            ):
                raise OutputSafetyError(
                    path=operation.source,
                    reason="changed during rename retry",
                ) from None
            time.sleep(_RENAME_DELAY_SECONDS)


@contextmanager
def _hold_recovery(
    recovery: Path,
    parent_descriptor: int | None,
) -> Generator[int | None]:
    if parent_descriptor is None:
        with hold_directory(recovery):
            yield None
        return
    if sys.platform == "win32":
        raise RuntimeError("directory descriptors require POSIX")
    try:
        recovery_descriptor = os.open(
            recovery.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent_descriptor,
        )
    except OSError as error:
        raise OutputSafetyError(
            path=recovery,
            reason="recovery directory changed",
        ) from error
    try:
        yield recovery_descriptor
    finally:
        os.close(recovery_descriptor)


def _remove_recovery(
    recovery: Path,
    parent_descriptor: int | None,
    expected_identity: tuple[int, int],
) -> None:
    if identity(recovery) != expected_identity:
        raise OutputSafetyError(path=recovery, reason="recovery directory changed")
    if parent_descriptor is None:
        recovery.rmdir()
        return
    os.rmdir(recovery.name, dir_fd=parent_descriptor)


def _install_snapshot(
    publication: SnapshotPublication,
    recovery: Path,
    recovery_descriptor: int | None,
) -> OutputSafetyError | None:
    state = publication.state
    previous = recovery / "previous"
    if state.identity is not None:
        _rename(
            _RenameOperation(
                source=state.path,
                destination=previous,
                source_descriptor=publication.parent_descriptor,
                destination_descriptor=recovery_descriptor,
            )
        )
        if (
            identity(previous) != state.identity
            or tree_signature(previous) != state.tree_signature
        ):
            _rename(
                _RenameOperation(
                    source=previous,
                    destination=state.path,
                    source_descriptor=recovery_descriptor,
                    destination_descriptor=publication.parent_descriptor,
                )
            )
            return OutputSafetyError(
                path=state.path,
                reason="changed during generation",
            )
    try:
        _rename(
            _RenameOperation(
                source=publication.snapshot,
                destination=state.path,
                expected_source_identity=publication.snapshot_identity,
                source_descriptor=publication.parent_descriptor,
                destination_descriptor=publication.parent_descriptor,
            )
        )
        if tree_signature(state.path) != publication.snapshot_signature:
            raise OutputSafetyError(
                path=state.path,
                reason="staging directory changed during install",
            )
    except (OSError, OutputSafetyError) as install_error:
        installed_identity = identity(state.path)
        should_quarantine = installed_identity == publication.snapshot_identity or (
            identity(publication.snapshot) is None
            and installed_identity is not None
            and not is_generator_output(state.path)
        )
        if should_quarantine:
            try:
                _rename(
                    _RenameOperation(
                        source=state.path,
                        destination=recovery / "rejected",
                        expected_source_identity=installed_identity,
                        source_descriptor=publication.parent_descriptor,
                        destination_descriptor=recovery_descriptor,
                    )
                )
            except (OSError, OutputSafetyError) as quarantine_error:
                raise quarantine_error from install_error
        if state.identity is not None and identity(state.path) is None:
            try:
                _rename(
                    _RenameOperation(
                        source=previous,
                        destination=state.path,
                        expected_source_identity=state.identity,
                        source_descriptor=recovery_descriptor,
                        destination_descriptor=publication.parent_descriptor,
                    )
                )
            except (OSError, OutputSafetyError) as rollback_error:
                raise rollback_error from install_error
        raise
    return None


def commit_snapshot(publication: SnapshotPublication) -> None:
    if (
        identity(publication.snapshot) != publication.snapshot_identity
        or tree_signature(publication.snapshot) != publication.snapshot_signature
    ):
        raise OutputSafetyError(
            path=publication.snapshot,
            reason="staging directory changed",
        )
    state = publication.state
    if (
        identity(state.path) != state.identity
        or identity(state.path.parent) != state.parent_identity
        or tree_signature(state.path) != state.tree_signature
    ):
        raise OutputSafetyError(path=state.path, reason="changed during generation")
    recovery = make_temporary_directory(
        state.path.parent,
        f".{state.path.name}-recovery-",
        publication.parent_descriptor,
    )
    recovery_identity = identity(recovery)
    if recovery_identity is None:
        raise OutputSafetyError(path=recovery, reason="recovery directory changed")
    with _hold_recovery(recovery, publication.parent_descriptor) as recovery_descriptor:
        recovered_error = _install_snapshot(publication, recovery, recovery_descriptor)
    if state.identity is None or recovered_error is not None:
        _remove_recovery(recovery, publication.parent_descriptor, recovery_identity)
    if recovered_error is not None:
        raise recovered_error
