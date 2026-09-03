from __future__ import annotations

from dataclasses import dataclass
from typing import Final, final, override
from urllib.parse import urlencode

import httpx2

from tools.website_models import (
    BASE_URL,
    REST_RECORDS,
    REST_TYPES,
    TEXT_REST_BASES,
    RestInventory,
    RestRecord,
    normalize_rest_url,
    normalize_url,
)

_REDIRECT_STATUSES: Final = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS: Final = 5
_MAX_REST_PAGES: Final = 100
_MAX_REST_BYTES: Final = 200_000_000
_MAX_REST_RECORDS: Final = 100_000


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


class PublicFetchError(RuntimeError):
    __slots__: tuple[str, str] = ("reason", "url")
    reason: str
    url: str

    def __init__(self, reason: str, url: str) -> None:
        self.reason = reason
        self.url = url
        super().__init__(reason, url)

    @override
    def __str__(self) -> str:
        return f"{self.reason}: {self.url}"


@final
class NonPublicRedirectError(PublicFetchError):
    pass


PAGE_FETCH_POLICY: Final = FetchPolicy(
    allow_rest=False,
    max_bytes=5_000_000,
    missing_statuses=frozenset({404, 410}),
)
REST_FETCH_POLICY: Final = FetchPolicy(allow_rest=True, max_bytes=20_000_000)


def _safe_url(raw_url: str, base_url: str, policy: FetchPolicy) -> str:
    normalized = (
        normalize_rest_url(raw_url, base_url)
        if policy.allow_rest
        else normalize_url(raw_url, base_url)
    )
    if normalized is None:
        reason = "unsafe REST URL" if policy.allow_rest else "unsafe public URL"
        raise PublicFetchError(reason=reason, url=raw_url)
    return normalized


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
                    try:
                        current_url = _safe_url(location, current_url, policy)
                    except PublicFetchError as error:
                        raise NonPublicRedirectError(
                            reason=error.reason,
                            url=error.url,
                        ) from error
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


async def fetch_rest_inventory(client: httpx2.AsyncClient) -> RestInventory:
    types_response = await fetch_public(
        client,
        f"{BASE_URL}wp-json/wp/v2/types",
        REST_FETCH_POLICY,
    )
    rest_types = REST_TYPES.validate_json(types_response.body)
    records_by_url: dict[str, RestRecord] = {}
    totals: dict[str, int] = {}
    fetched_bases: set[str] = set()
    received_bytes = len(types_response.body)
    received_records = 0
    for rest_type in sorted(rest_types.values(), key=lambda item: item.rest_base or ""):
        rest_base = rest_type.rest_base
        if rest_base not in TEXT_REST_BASES or rest_base in fetched_bases:
            continue
        fetched_bases.add(rest_base)
        endpoint = f"{BASE_URL}wp-json/wp/v2/{rest_base}"
        response = await fetch_public(
            client,
            f"{endpoint}?{urlencode({'page': 1, 'per_page': 100})}",
            REST_FETCH_POLICY,
        )
        total_pages = int(response.headers.get("X-WP-TotalPages", "1"))
        if total_pages > _MAX_REST_PAGES:
            raise PublicFetchError(
                reason="REST pagination limit exceeded", url=endpoint
            )
        totals[rest_base] = int(response.headers.get("X-WP-Total", "0"))
        for page in range(1, total_pages + 1):
            if page > 1:
                response = await fetch_public(
                    client,
                    f"{endpoint}?{urlencode({'page': page, 'per_page': 100})}",
                    REST_FETCH_POLICY,
                )
            received_bytes += len(response.body)
            page_records = REST_RECORDS.validate_json(response.body)
            received_records += len(page_records)
            if received_bytes > _MAX_REST_BYTES or received_records > _MAX_REST_RECORDS:
                raise PublicFetchError(
                    reason="REST inventory limit exceeded", url=endpoint
                )
            for record in page_records:
                canonical_url = normalize_url(record.link)
                if canonical_url is not None:
                    records_by_url[canonical_url] = record
    return RestInventory(records_by_url=records_by_url, totals=totals)
