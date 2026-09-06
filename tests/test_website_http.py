from __future__ import annotations

import anyio
import httpx2
import pytest

from tools.website_http import PAGE_FETCH_POLICY, PublicFetchError, fetch_public


def test_fetch_public_direct_legacy_url_is_allowed_only_when_explicitly_enabled() -> (
    None
):
    requested: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested.append(str(request.url))
        return httpx2.Response(
            200,
            headers={"content-type": "text/html"},
            text='<main><p>директна страница</p><a href="https://finki.ukim.mk/en/">link</a></main>',
        )

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            response = await fetch_public(
                client,
                "https://oldsite.finki.ukim.mk/mk/zafakultetot/instituti",
                PAGE_FETCH_POLICY,
                allowed_redirect_urls=frozenset(
                    {"https://oldsite.finki.ukim.mk/mk/zafakultetot/instituti"}
                ),
                allowed_hosts=frozenset({"finki.ukim.mk", "oldsite.finki.ukim.mk"}),
            )
        assert response.url == (
            "https://oldsite.finki.ukim.mk/mk/zafakultetot/instituti"
        )

    anyio.run(run)
    assert requested == ["https://oldsite.finki.ukim.mk/mk/zafakultetot/instituti"]


@pytest.mark.parametrize(
    "location",
    [
        "https://finki.ukim.mk/en/studies/",
        "https://oldsite.finki.ukim.mk/mk/other-page",
        "https://oldsite.finki.ukim.mk.evil/mk/other-page",
    ],
)
def test_curated_legacy_fetch_rejects_cross_host_or_unlisted_redirects(
    location: str,
) -> None:
    requested: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested.append(str(request.url))
        return httpx2.Response(302, headers={"location": location})

    async def run() -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler)
        ) as client:
            with pytest.raises(PublicFetchError):
                await fetch_public(
                    client,
                    "https://oldsite.finki.ukim.mk/mk/source",
                    PAGE_FETCH_POLICY,
                    allowed_redirect_urls=frozenset(
                        {"https://oldsite.finki.ukim.mk/mk/source"}
                    ),
                    allowed_hosts=frozenset({"finki.ukim.mk", "oldsite.finki.ukim.mk"}),
                )

    anyio.run(run)
    assert requested == ["https://oldsite.finki.ukim.mk/mk/source"]


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
