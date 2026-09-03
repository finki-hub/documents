from __future__ import annotations

from dataclasses import dataclass
from typing import Final, final, override
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx2

from tools.website_models import PUBLIC_HOSTS, normalize_url

_REDIRECT_STATUSES: Final = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS: Final = 5


@dataclass(frozen=True, slots=True)
class FetchPolicy:
    allow_rest: bool
    max_bytes: int
    missing_statuses: frozenset[int] = frozenset()


@dataclass(frozen=True, slots=True)
class PublicResponse:
    body: bytes
    content_type: str
    encoding: str
    headers: httpx2.Headers
    status: int
    url: str


@final
class PublicFetchError(RuntimeError):
    __slots__ = ("reason", "url")
    reason: str
    url: str

    def __init__(self, reason: str, url: str) -> None:
        self.reason = reason
        self.url = url
        super().__init__(reason, url)

    @override
    def __str__(self) -> str:
        return f"{self.reason}: {self.url}"


PAGE_FETCH_POLICY: Final = FetchPolicy(
    allow_rest=False,
    max_bytes=5_000_000,
    missing_statuses=frozenset({404, 410}),
)
REST_FETCH_POLICY: Final = FetchPolicy(allow_rest=True, max_bytes=20_000_000)


def _safe_url(raw_url: str, base_url: str, policy: FetchPolicy) -> str:
    if not policy.allow_rest:
        normalized = normalize_url(raw_url, base_url)
        if normalized is None:
            raise PublicFetchError(reason="unsafe public URL", url=raw_url)
        return normalized
    parsed = urlsplit(urljoin(base_url, raw_url))
    if parsed.scheme not in {"http", "https"}:
        raise PublicFetchError(reason="unsafe URL scheme", url=raw_url)
    if (parsed.hostname or "").casefold() not in PUBLIC_HOSTS:
        raise PublicFetchError(reason="unsafe public host", url=raw_url)
    return urlunsplit(("https", "finki.ukim.mk", parsed.path or "/", parsed.query, ""))


async def _read_body(response: httpx2.Response, policy: FetchPolicy) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError as error:
            raise PublicFetchError(
                reason="invalid Content-Length",
                url=str(response.url),
            ) from error
        if declared_size > policy.max_bytes:
            raise PublicFetchError(
                reason="response exceeds byte limit", url=str(response.url)
            )
    chunks: list[bytes] = []
    received = 0
    async for chunk in response.aiter_bytes():
        received += len(chunk)
        if received > policy.max_bytes:
            raise PublicFetchError(
                reason="response exceeds byte limit", url=str(response.url)
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def fetch_public(
    client: httpx2.AsyncClient,
    url: str,
    policy: FetchPolicy,
) -> PublicResponse:
    current_url = _safe_url(url, url, policy)
    redirects = 0
    try:
        while True:
            async with client.stream(
                "GET",
                current_url,
                follow_redirects=False,
            ) as response:
                if response.status_code in _REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if location is None:
                        raise PublicFetchError(
                            reason="redirect response has no Location",
                            url=current_url,
                        )
                    redirects += 1
                    if redirects > _MAX_REDIRECTS:
                        raise PublicFetchError(
                            reason="redirect limit exceeded",
                            url=current_url,
                        )
                    current_url = _safe_url(location, current_url, policy)
                    continue
                if (
                    response.status_code >= 400
                    and response.status_code not in policy.missing_statuses
                ):
                    raise PublicFetchError(
                        reason=f"HTTP {response.status_code}",
                        url=current_url,
                    )
                body = await _read_body(response, policy)
                return PublicResponse(
                    body=body,
                    content_type=response.headers.get("content-type", "").casefold(),
                    encoding=response.encoding or "utf-8",
                    headers=httpx2.Headers(response.headers),
                    status=response.status_code,
                    url=current_url,
                )
    except httpx2.HTTPError as error:
        raise PublicFetchError(reason=type(error).__name__, url=current_url) from error
