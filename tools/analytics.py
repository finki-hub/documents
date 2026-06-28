"""PostHog product analytics for the offline ingest pipeline.

Metadata-only by construction: callers pass dicts of ids / names / counts / sizes /
sources — never document text. The pipeline handles sovereign Macedonian legal text,
so SDK exception autocapture (which could embed source text in the breadcrumbs) is
disabled; instead, ``capture_exception`` is called manually with curated metadata only.

No-op when POSTHOG_KEY is unset, so dev / CI / tests emit nothing. As a short-lived
batch the client must be flushed and shut down before exit or queued events are dropped.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from posthog import Posthog

SERVICE = "documents-ingest"
DEFAULT_HOST = "https://eu.i.posthog.com"
DISTINCT_ID = "documents-ingest"


class Analytics:
    """Thin PostHog wrapper that degrades to a no-op without POSTHOG_KEY."""

    def __init__(self, client: Posthog | None) -> None:
        self._client = client

    @classmethod
    def from_env(cls) -> Analytics:
        key = os.environ.get("POSTHOG_KEY", "").strip()
        if not key:
            return cls(None)
        from posthog import Posthog

        client = Posthog(
            key,
            host=os.environ.get("POSTHOG_HOST", DEFAULT_HOST),
            enable_exception_autocapture=False,
        )
        return cls(client)

    def capture(self, event: str, properties: dict[str, Any]) -> None:
        if self._client is None:
            return
        # Fresh dict per event; only the metadata the caller passed, plus `service`.
        self._client.capture(
            event,
            distinct_id=DISTINCT_ID,
            properties={"service": SERVICE, **properties},
        )

    def capture_exception(
        self,
        exc: BaseException,
        distinct_id: str = DISTINCT_ID,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Capture an exception with curated metadata; no-op when disabled, never raises."""
        if self._client is None:
            return
        try:
            props: dict[str, Any] = {"service": SERVICE}
            if properties:
                props.update(properties)
            self._client.capture_exception(
                exc, distinct_id=distinct_id, properties=props
            )
        except Exception:  # noqa: BLE001
            pass

    def shutdown(self) -> None:
        if self._client is None:
            return
        self._client.flush()
        self._client.shutdown()
