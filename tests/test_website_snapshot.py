import re
import unicodedata
from pathlib import Path
from typing import Final
from urllib.parse import unquote

from tools.website_models import WebsiteManifest
from tools.website_privacy import contains_sensitive_personal_identifier

SNAPSHOT_ROOT: Final = Path("website")
MANIFEST_PATH: Final = SNAPSHOT_ROOT / "manifest.json"
MAX_DECODE_PASSES: Final = 20
FORBIDDEN_FIN_IDENTIFIER: Final = re.compile(
    r"(?<!\w)f[\W_]*i[\W_]*n[\W_]*\d(?:[\W_]*\d){6}(?!\d)",
    re.IGNORECASE,
)


def _load_manifest() -> WebsiteManifest:
    assert MANIFEST_PATH.is_file()
    return WebsiteManifest.model_validate_json(
        MANIFEST_PATH.read_text(encoding="utf-8")
    )


def _decoded_text(value: str) -> str | None:
    for _ in range(MAX_DECODE_PASSES):
        decoded = unquote(unicodedata.normalize("NFKC", value))
        if decoded == value:
            return decoded
        value = decoded
    return None


def test_tracked_website_snapshot_is_complete() -> None:
    manifest = _load_manifest()

    assert not manifest.crawl_truncated
    assert manifest.document_count > 0


def test_tracked_website_manifest_matches_document_tree() -> None:
    manifest = _load_manifest()
    listed_paths = {entry.path for entry in manifest.documents}
    document_paths = {
        path.relative_to(SNAPSHOT_ROOT).as_posix()
        for path in (SNAPSHOT_ROOT / "documents").rglob("*.md")
    }

    assert listed_paths == document_paths
    assert manifest.document_count == len(manifest.documents) == len(document_paths)


def test_tracked_website_snapshot_excludes_personal_identifier_tables() -> None:
    manifest = _load_manifest()
    for entry in manifest.documents:
        path = SNAPSHOT_ROOT / entry.path
        markdown = path.read_text(encoding="utf-8")
        emitted_text = "\n".join((entry.title, entry.url, *entry.aliases, markdown))
        decoded_text = _decoded_text(emitted_text)
        assert decoded_text is not None, f"over-encoded output in {path}"
        assert not any(
            FORBIDDEN_FIN_IDENTIFIER.search(line) for line in decoded_text.splitlines()
        ), f"FIN-prefixed personal identifier in {path}"
        assert not contains_sensitive_personal_identifier(
            title=entry.title,
            markdown=emitted_text,
        ), f"sensitive candidate identifier in {path}"
