import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from tools.document_metadata import (
    header_value,
    ingest_metadata,
    source_filenames,
    validated_corpus,
)


def ingest(api_url: str, out_dir: Path, r2_prefix: str) -> None:
    api_key = os.environ.get("API_KEY")
    if not api_key:
        sys.exit("Set API_KEY in the environment to ingest.")

    documents = validated_corpus(out_dir)
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
            with urllib.request.urlopen(request) as response:
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
        with urllib.request.urlopen(request) as response:
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
        with urllib.request.urlopen(list_request) as response:
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
                with urllib.request.urlopen(delete_request) as response:
                    deleted = json.loads(response.read())
                r2_key = (deleted.get("metadata") or {}).get("r2_key")
                note = f"  (R2 original kept as archive: {r2_key})" if r2_key else ""
                print(f"  pruned {name}{note}")
            except Exception as error:  # noqa: BLE001
                print(f"  FAIL pruning {name}: {error}")

    print("\nNow run: preprocess.py fill  to embed any new/changed chunks.")
