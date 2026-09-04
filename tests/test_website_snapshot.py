import re
import unicodedata
from pathlib import Path
from typing import Final

from tools.website_models import WebsiteManifest
from tools.website_privacy import contains_sensitive_personal_identifier

SNAPSHOT_ROOT: Final = Path("website")
MANIFEST_PATH: Final = SNAPSHOT_ROOT / "manifest.json"
FORBIDDEN_FIN_IDENTIFIER: Final = re.compile(
    r"\bf[\W_]{0,3}i[\W_]{0,3}n[\W_]{0,3}\d(?:[\W_]{0,3}\d){6}\b",
    re.IGNORECASE,
)


def _load_manifest() -> WebsiteManifest:
    assert MANIFEST_PATH.is_file()
    return WebsiteManifest.model_validate_json(
        MANIFEST_PATH.read_text(encoding="utf-8")
    )


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
        normalized_markdown = unicodedata.normalize("NFKC", markdown)
        assert not FORBIDDEN_FIN_IDENTIFIER.search(normalized_markdown), (
            f"FIN-prefixed personal identifier in {path}"
        )
        assert not contains_sensitive_personal_identifier(
            title=entry.title,
            markdown=markdown,
        ), f"sensitive candidate identifier in {path}"
