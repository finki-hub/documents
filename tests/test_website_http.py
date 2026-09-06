from __future__ import annotations

import anyio
import httpx2
import pytest

from tools.website_http import PAGE_FETCH_POLICY, PublicFetchError, fetch_public


def test_fetch_public_strict_redirect_mode_does_not_request_target() -> None:
    requested: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested.append(str(request.url))
        return httpx2.Response(
            302,
            headers={"location": "https://finki.ukim.mk/en/redirected/"},
        )

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            with pytest.raises(PublicFetchError, match="allowlisted"):
                await fetch_public(
                    client,
                    "https://finki.ukim.mk/en/source/",
                    PAGE_FETCH_POLICY,
                    allowed_redirect_urls=frozenset(
                        {"https://finki.ukim.mk/en/source/"}
                    ),
                )

    anyio.run(run)
    assert requested == ["https://finki.ukim.mk/en/source/"]


def test_fetch_public_default_redirect_behavior_is_preserved() -> None:
    requested: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested.append(str(request.url))
        if request.url.path == "/en/source/":
            return httpx2.Response(
                302,
                headers={"location": "https://finki.ukim.mk/en/target/"},
            )
        return httpx2.Response(
            200,
            headers={"content-type": "text/html"},
            text="target",
        )

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            response = await fetch_public(
                client,
                "https://finki.ukim.mk/en/source/",
                PAGE_FETCH_POLICY,
            )
        assert response.url == "https://finki.ukim.mk/en/target/"

    anyio.run(run)
    assert requested == [
        "https://finki.ukim.mk/en/source/",
        "https://finki.ukim.mk/en/target/",
    ]
