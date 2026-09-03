import pytest

from tools.website_models import normalize_url


def test_normalize_url_keeps_supported_public_variants() -> None:
    assert (
        normalize_url(
            "https://www.finki.ukim.mk/kadar/?kat=profesori&utm_source=test#staff",
            "https://finki.ukim.mk/",
        )
        == "https://finki.ukim.mk/kadar/?kat=profesori"
    )


def test_normalize_url_rejects_non_content_routes() -> None:
    assert normalize_url("https://example.com/page", "https://finki.ukim.mk/") is None
    assert normalize_url("/wp-json/wp/v2/pages", "https://finki.ukim.mk/") is None
    assert normalize_url("/announcements/feed/", "https://finki.ukim.mk/") is None


@pytest.mark.parametrize(
    "path",
    [
        "/feed",
        "/news/feed/",
        "/news/trackback/",
        "/wp-login.php",
        "/safe/%252e%252e/wp-admin/",
    ],
)
def test_normalize_url_rejects_non_content_route_segments(path: str) -> None:
    assert normalize_url(path) is None


def test_normalize_url_allows_content_segment_with_reserved_prefix() -> None:
    assert normalize_url("/wp-administration/") == (
        "https://finki.ukim.mk/wp-administration/"
    )
