import os
import sys
from pathlib import Path
from typing import Protocol


class _R2Client(Protocol):
    def upload_file(self, filename: str, bucket: str, key: str) -> None: ...


def _r2_client() -> _R2Client:
    import boto3

    endpoint = os.environ.get("R2_ENDPOINT") or (
        f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def upload_originals(
    raw_dir: Path,
    r2_prefix: str,
    excluded_sources: frozenset[str],
) -> None:
    bucket = os.environ.get("R2_BUCKET")
    if not bucket:
        sys.exit(
            "Set R2_BUCKET (+ R2_ACCOUNT_ID/R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY)."
        )
    client = _r2_client()
    for source in sorted(raw_dir.iterdir()):
        if source.is_dir() or source.name.casefold() in excluded_sources:
            continue
        key = f"{r2_prefix}{source.name}"
        client.upload_file(str(source), bucket, key)
        print(f"OK    uploaded {source.name} -> r2://{bucket}/{key}")
    print(
        "\nOriginals archived. The R2 key is stored in each document's metadata at ingest time."
    )
