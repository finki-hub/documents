from http.client import HTTPResponse
from pathlib import Path
from urllib.request import OpenerDirector, Request

import pytest

from tools.docpipe import _validated_input
from tools.document_api import _api_base, _NoRedirect, _open_api_request
from tools.document_metadata import _is_valid_date
from tools.rag_corpus_bundle import _read_utf8


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://localhost/file",
        "http://user:pass@localhost",
        "http://localhost/#fragment",
        "http://localhost/?query=1",
        "http://localhost/../secret",
        "http://localhost/%2e%2e/secret",
        "http://169.254.169.254/latest/meta-data",
        "https://untrusted.example",
        "http://localhost\\@evil.example",
        "http://localhost\n.evil.example",
    ],
)
def test_api_rejects_untrusted_urls(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCUMENT_API_ALLOWED_ORIGINS", raising=False)
    with pytest.raises(ValueError, match="API|Port|port"):
        _api_base(url)


@pytest.mark.parametrize(
    "url", ["http://localhost:8880", "http://127.0.0.1:8880", "http://[::1]:8880"]
)
def test_local_api_remains_supported(url: str) -> None:
    assert _api_base(url) == url


def test_remote_api_requires_exact_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCUMENT_API_ALLOWED_ORIGINS", "https://api.example:8443")
    assert (
        _api_base("https://api.example:8443/base/") == "https://api.example:8443/base"
    )
    with pytest.raises(ValueError, match="Port|port|origin"):
        _api_base("https://api.example:8443.evil.example")
    with pytest.raises(ValueError, match="Port|port|origin"):
        _api_base("http://api.example:8443")


def test_api_redirects_fail_closed() -> None:
    handler = _NoRedirect()
    with pytest.raises(ValueError, match="redirects"):
        handler.redirect_request(
            None, None, 302, "Found", None, "http://169.254.169.254"
        )


def test_transport_has_timeout_and_disables_proxies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = Request("http://localhost:8880/documents/list")
    observed: list[object] = []

    def build_opener(*handlers: object) -> OpenerDirector:
        observed.extend(handlers)
        return OpenerDirector()

    def open_request(
        _self: OpenerDirector, received: Request, *, timeout: int
    ) -> HTTPResponse:
        assert received is request
        assert timeout == 60
        raise RuntimeError("transport intercepted")

    monkeypatch.setattr("urllib.request.build_opener", build_opener)
    monkeypatch.setattr(OpenerDirector, "open", open_request)
    with pytest.raises(RuntimeError, match="intercepted"):
        _open_api_request(request)
    assert isinstance(observed[1], _NoRedirect)
    assert getattr(observed[0], "proxies", None) == {}


def test_explicit_markdown_path_supported(tmp_path: Path) -> None:
    document = tmp_path / "document.md"
    document.write_text("# Document", encoding="utf-8")
    assert _validated_input(document) == document.resolve()


def test_parent_traversal_rejected(tmp_path: Path) -> None:
    path = tmp_path / "child" / ".." / "secret.md"
    with pytest.raises(ValueError, match="traversal"):
        _validated_input(path)


def test_symlink_rejected(tmp_path: Path) -> None:
    document = tmp_path / "document.md"
    document.write_text("content", encoding="utf-8")
    link = tmp_path / "link.md"
    try:
        link.symlink_to(document)
    except OSError:
        pytest.skip("Host does not permit creating symlinks")
    with pytest.raises(ValueError, match="symlinks"):
        _validated_input(link)


def test_non_document_input_rejected(tmp_path: Path) -> None:
    document = tmp_path / "credentials.txt"
    document.write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError, match="PDF"):
        _validated_input(document)


def test_bundle_reader_preserves_raw_newlines(tmp_path: Path) -> None:
    document = tmp_path / "document.md"
    document.write_bytes(b"one\r\ntwo\rthree\n")
    assert _read_utf8(document) == "one\r\ntwo\rthree\n"


@pytest.mark.parametrize(
    ("value", "precision", "expected"),
    [
        ("2024-02-29", "day", True),
        ("2023-02-29", "day", False),
        ("2024-13", "month", False),
        ("2024-02", "month", True),
        ("0000", "year", False),
        ("2024", "year", True),
        ("2024/25", "academic_year", True),
        ("2024/26", "academic_year", False),
    ],
)
def test_date_refactor_preserves_validation(
    value: str, precision: str, *, expected: bool
) -> None:
    assert _is_valid_date(value, precision) is expected
