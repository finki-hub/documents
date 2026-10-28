import ipaddress
import json
import os
import sys
import urllib.parse
import urllib.request
from contextlib import suppress
from http.client import HTTPResponse
from pathlib import Path
from typing import Never

from tools.document_metadata import (
    header_value,
    ingest_metadata,
    source_filenames,
    validated_corpus,
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        _req: object,
        _fp: object,
        _code: int,
        _msg: str,
        _headers: object,
        _newurl: str,
    ) -> Never:
        raise ValueError("API redirects are not permitted")


def _validate_api_origin(parsed: urllib.parse.SplitResult) -> None:
    origin = f"{parsed.scheme}://{parsed.netloc}".lower()
    allowed = {
        value.strip().lower().rstrip("/")
        for value in os.environ.get("DOCUMENT_API_ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    }
    host = (parsed.hostname or "").casefold()
    local = host == "localhost"
    with suppress(ValueError):
        local = local or ipaddress.ip_address(host).is_loopback
    if not local and origin not in allowed:
        raise ValueError(
            "Remote API origin must be configured in DOCUMENT_API_ALLOWED_ORIGINS"
        )


def _api_base(api_url: str) -> str:
    """The operator selects the API, not arbitrary URL schemes or metadata services.

    Non-loopback private deployments require an explicitly configured origin.
    Public remote deployments also require this separate trust configuration;
    it prevents CLI input from choosing where the API credential is sent.
    """
    if any(character.isspace() or ord(character) < 32 for character in api_url):
        raise ValueError("API URL must not contain whitespace or control characters")
    parsed = urllib.parse.urlsplit(api_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("API URL must use http or https with a hostname")
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or "\\" in api_url
    ):
        raise ValueError(
            "API URL must not contain credentials, query, fragment or backslashes"
        )
    port = parsed.port
    _validate_api_origin(parsed)
    if port == 0 or any(
        part in {".", ".."} for part in urllib.parse.unquote(parsed.path).split("/")
    ):
        raise ValueError("Invalid API port or base path")
    return api_url.rstrip("/")


def _open_api_request(request: urllib.request.Request) -> HTTPResponse:
    # Do not use environment proxies or follow redirects carrying the API key.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    return opener.open(request, timeout=60)


def ingest(api_url: str, out_dir: Path, r2_prefix: str) -> None:
    api_key = os.environ.get("API_KEY")
    if not api_key:
        sys.exit("Set API_KEY in the environment to ingest.")

    documents = validated_corpus(out_dir)
    api_url = _api_base(api_url)
    for document in documents:
        md_path = document.path
        content = document.content
        title = header_value(content, "title") or md_path.stem
        source_files = source_filenames(content)
        metadata: dict[str, str | list[str]] = {}
        metadata.update(ingest_metadata(content))
        if source_files:
            metadata.update(
                source_file=source_files[0],
                source_files=list(source_files),
                r2_key=f"{r2_prefix}{source_files[0]}",
                r2_keys=[f"{r2_prefix}{source}" for source in source_files],
            )
        body = {
            "name": md_path.stem,
            "title": title,
            "content": content,
            "source_type": "markdown",
            "metadata": metadata or None,
        }
        request = urllib.request.Request(
            f"{api_url}/documents/",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-api-key": api_key},
            method="POST",
        )
        try:
            with _open_api_request(request) as response:
                result = json.loads(response.read())
                print(
                    f"OK    ingested {md_path.name} -> {result.get('chunk_count')} chunks"
                )
        except Exception as error:  # noqa: BLE001
            print(f"FAIL  {md_path.name}: {error}")
    print(
        "\nNow run: preprocess.py fill  (or POST /documents/fill) to generate embeddings."
    )


def fill(api_url: str) -> None:
    api_url = _api_base(api_url)
    api_key = os.environ.get("API_KEY")
    if not api_key:
        sys.exit("Set API_KEY in the environment to fill embeddings.")

    body = {"all_models": True, "all_chunks": False}
    request = urllib.request.Request(
        f"{api_url}/documents/fill",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": api_key},
        method="POST",
    )
    ok = err = 0
    try:
        with _open_api_request(request) as response:
            for raw in response:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[len("data:") :].strip())
                if event.get("status") == "ok":
                    ok += 1
                else:
                    err += 1
                    print(
                        f"  FAIL [{event.get('model')}] {event.get('name')}: {event.get('error')}"
                    )
                done = ok + err
                if done % 50 == 0:
                    print(f"  ... {done}/{event.get('total')} ({err} errors)")
    except Exception as error:  # noqa: BLE001
        sys.exit(f"Fill request failed: {error}")
    if err:
        sys.exit(f"\nFill finished with errors: {ok} ok, {err} failed.")
    print(f"\nFill complete: {ok} ok, {err} errors.")


def sync(api_url: str, out_dir: Path, r2_prefix: str) -> None:
    api_url = _api_base(api_url)
    api_key = os.environ.get("API_KEY")
    if not api_key:
        sys.exit("Set API_KEY in the environment to sync.")

    ingest(api_url, out_dir, r2_prefix)
    desired = {path.stem for path in out_dir.glob("*.md")}
    list_request = urllib.request.Request(
        f"{api_url}/documents/list",
        headers={"x-api-key": api_key},
        method="GET",
    )
    try:
        with _open_api_request(list_request) as response:
            stored = json.loads(response.read())
    except Exception as error:  # noqa: BLE001
        sys.exit(f"Failed to list documents: {error}")

    orphans = [document for document in stored if document["name"] not in desired]
    if not orphans:
        print("\nIn sync: every stored document has a matching file; nothing to prune.")
    else:
        print(
            f"\nPruning {len(orphans)} document(s) with no matching file (rename/removal):"
        )
        for document in orphans:
            name = document["name"]
            delete_request = urllib.request.Request(
                f"{api_url}/documents/{urllib.parse.quote(name, safe='')}",
                headers={"x-api-key": api_key},
                method="DELETE",
            )
            try:
                with _open_api_request(delete_request) as response:
                    deleted = json.loads(response.read())
                r2_key = (deleted.get("metadata") or {}).get("r2_key")
                note = f"  (R2 original kept as archive: {r2_key})" if r2_key else ""
                print(f"  pruned {name}{note}")
            except Exception as error:  # noqa: BLE001
                print(f"  FAIL pruning {name}: {error}")

    print("\nNow run: preprocess.py fill  to embed any new/changed chunks.")
