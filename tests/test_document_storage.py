import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools.document_storage import _r2_client, upload_originals


@pytest.fixture
def boto3_stub(monkeypatch: pytest.MonkeyPatch) -> Mock:
    for name in (
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "R2_REGION",
        "R2_ENDPOINT",
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("R2_ACCOUNT_ID", "dummy-account")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "dummy-access-key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "dummy-secret-key")
    stub = Mock()
    monkeypatch.setitem(sys.modules, "boto3", stub)
    return stub


@pytest.mark.parametrize("aws_variable", [None, "AWS_REGION", "AWS_DEFAULT_REGION"])
def test_default_region_ignores_aws_environment(
    monkeypatch: pytest.MonkeyPatch, boto3_stub: Mock, aws_variable: str | None
) -> None:
    if aws_variable is not None:
        monkeypatch.setenv(aws_variable, "eu-west-1")

    assert _r2_client() is boto3_stub.client.return_value

    boto3_stub.client.assert_called_once_with(
        "s3",
        endpoint_url="https://dummy-account.r2.cloudflarestorage.com",
        aws_access_key_id="dummy-access-key",
        aws_secret_access_key="dummy-secret-key",  # noqa: S106 - isolated dummy credential
        region_name="auto",
    )


@pytest.mark.parametrize("region", ["auto", "", "us-east-1"])
def test_supported_r2_regions(
    monkeypatch: pytest.MonkeyPatch, boto3_stub: Mock, region: str
) -> None:
    monkeypatch.setenv("R2_REGION", region)
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")

    _r2_client()

    assert boto3_stub.client.call_args.kwargs["region_name"] == region


@pytest.mark.parametrize("region", ["eu-west-1", "AUTO", " "])
def test_invalid_r2_region_rejected(
    monkeypatch: pytest.MonkeyPatch, boto3_stub: Mock, region: str
) -> None:
    monkeypatch.setenv("R2_REGION", region)

    with pytest.raises(ValueError, match="R2_REGION must be auto, empty, or us-east-1"):
        _r2_client()

    boto3_stub.client.assert_not_called()


def test_upload_preserves_endpoint_and_file_selection(
    monkeypatch: pytest.MonkeyPatch, boto3_stub: Mock, tmp_path: Path
) -> None:
    monkeypatch.setenv("R2_ENDPOINT", "https://r2.example.invalid")
    monkeypatch.delenv("R2_ACCOUNT_ID")
    monkeypatch.setenv("R2_BUCKET", "dummy-bucket")
    document = tmp_path / "document.pdf"
    document.write_bytes(b"dummy document")
    (tmp_path / "SKIP.pdf").write_bytes(b"excluded")
    (tmp_path / "directory").mkdir()

    upload_originals(tmp_path, "originals/", frozenset({"skip.pdf"}))

    assert boto3_stub.client.call_args.kwargs["endpoint_url"] == (
        "https://r2.example.invalid"
    )
    boto3_stub.client.return_value.upload_file.assert_called_once_with(
        str(document), "dummy-bucket", "originals/document.pdf"
    )
