from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Final

from tools.website_output_paths import (
    OutputSafetyError,
    OutputState,
    TreeSignature,
    identity,
    is_generator_output,
    tree_signature,
)

_RENAME_ATTEMPTS: Final = 3
_RENAME_DELAY_SECONDS: Final = 0.05


def _rename(
    source: Path,
    destination: Path,
    *,
    expected_source_identity: tuple[int, int] | None = None,
) -> None:
    source_identity = identity(source)
    if (
        expected_source_identity is not None
        and source_identity != expected_source_identity
    ):
        raise OutputSafetyError(path=source, reason="staging directory changed")
    destination_identity = identity(destination)
    for attempt in range(_RENAME_ATTEMPTS):
        try:
            os.rename(source, destination)
            if (
                expected_source_identity is not None
                and identity(destination) != expected_source_identity
            ):
                raise OutputSafetyError(
                    path=destination,
                    reason="staging directory changed during install",
                )
            return
        except PermissionError:
            if attempt + 1 == _RENAME_ATTEMPTS:
                raise
            if (
                identity(source) != source_identity
                or identity(destination) != destination_identity
            ):
                raise OutputSafetyError(
                    path=source,
                    reason="changed during rename retry",
                ) from None
            time.sleep(_RENAME_DELAY_SECONDS)


def commit_snapshot(
    state: OutputState,
    snapshot: Path,
    snapshot_identity: tuple[int, int],
    snapshot_signature: TreeSignature,
) -> None:
    if (
        identity(snapshot) != snapshot_identity
        or tree_signature(snapshot) != snapshot_signature
    ):
        raise OutputSafetyError(path=snapshot, reason="staging directory changed")
    if (
        identity(state.path) != state.identity
        or identity(state.path.parent) != state.parent_identity
        or tree_signature(state.path) != state.tree_signature
    ):
        raise OutputSafetyError(path=state.path, reason="changed during generation")
    recovery = Path(
        tempfile.mkdtemp(prefix=f".{state.path.name}-recovery-", dir=state.path.parent)
    )
    previous = recovery / "previous"
    if state.identity is not None:
        _rename(state.path, previous)
        if (
            identity(previous) != state.identity
            or tree_signature(previous) != state.tree_signature
        ):
            _rename(previous, state.path)
            recovery.rmdir()
            raise OutputSafetyError(
                path=state.path,
                reason="changed during generation",
            )
    try:
        _rename(
            snapshot,
            state.path,
            expected_source_identity=snapshot_identity,
        )
        if tree_signature(state.path) != snapshot_signature:
            raise OutputSafetyError(
                path=state.path,
                reason="staging directory changed during install",
            )
    except (OSError, OutputSafetyError) as install_error:
        installed_identity = identity(state.path)
        should_quarantine = installed_identity == snapshot_identity or (
            identity(snapshot) is None
            and installed_identity is not None
            and not is_generator_output(state.path)
        )
        if should_quarantine:
            try:
                _rename(
                    state.path,
                    recovery / "rejected",
                    expected_source_identity=installed_identity,
                )
            except (OSError, OutputSafetyError) as quarantine_error:
                raise quarantine_error from install_error
        if state.identity is not None and identity(state.path) is None:
            try:
                _rename(
                    previous,
                    state.path,
                    expected_source_identity=state.identity,
                )
            except (OSError, OutputSafetyError) as rollback_error:
                raise rollback_error from install_error
        raise
    if state.identity is None:
        recovery.rmdir()
