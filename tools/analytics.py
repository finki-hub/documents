"""PostHog product analytics for the offline ingest pipeline.

Metadata-only by construction: callers pass dicts of ids / names / counts / sizes /
sources — never document text. The pipeline handles sovereign Macedonian legal text,
so SDK exception autocapture (which could embed source text in breadcrumbs) is
disabled. ``capture_exception`` also never forwards the exception object to the SDK —
PostHog's ``capture_exception()`` serialises the full stacktrace including frame-local
variables, which would embed document text. Instead it emits a ``$exception`` event
with a redacted ``$exception_list`` so errors still surface in PostHog Error Tracking.

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
        try:
            # service is set last so callers cannot accidentally override it.
            self._client.capture(
                event,
                distinct_id=DISTINCT_ID,
                properties={**properties, "service": SERVICE},
            )
        except Exception:  # noqa: BLE001
            pass

    def capture_exception(
        self,
        exc: BaseException,
        distinct_id: str = DISTINCT_ID,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Emit a redacted $exception event; no-op when disabled, never raises.

        The exception object is never forwarded to the SDK — PostHog serialises
        full stacktraces with frame-local variables, which would leak document text.
        The ``$exception_list`` entry carries only the class name so the event still
        surfaces in PostHog Error Tracking.
        """
        if self._client is None:
            return
        try:
            props: dict[str, Any] = {}
            if properties:
                props.update(properties)
            # service and $exception_list are set last so callers cannot override them.
            props["service"] = SERVICE
            props["$exception_list"] = [
                {"type": type(exc).__name__, "value": "(redacted for residency)"}
            ]
            self._client.capture(
                "$exception",
                distinct_id=distinct_id,
                properties=props,
            )
        except Exception:  # noqa: BLE001
            pass

    def shutdown(self) -> None:
        if self._client is None:
            return
        try:
            self._client.flush()
            self._client.shutdown()
        except Exception:  # noqa: BLE001
            pass
