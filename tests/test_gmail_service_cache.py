from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gmail_dwd_mcp.auth import WifConfigCache
from gmail_dwd_mcp.gmail_service import GmailService


@pytest.fixture
def wif_cache() -> WifConfigCache:
    settings = MagicMock()
    settings.aws_region = "us-east-1"
    settings.wif_cache_ttl_seconds = 3600
    settings.ssm_parameter_name = "/test/wif"
    with patch("gmail_dwd_mcp.auth.boto3.client"):
        return WifConfigCache(settings)


@pytest.fixture
def gmail(wif_cache: WifConfigCache) -> GmailService:
    return GmailService(wif_cache)


@patch("gmail_dwd_mcp.gmail_service.build")
@patch("gmail_dwd_mcp.gmail_service.credentials_for_user")
def test_service_uses_credentials_for_user(
    mock_credentials_for_user: MagicMock,
    mock_build: MagicMock,
    gmail: GmailService,
) -> None:
    creds = MagicMock(valid=True)
    mock_credentials_for_user.return_value = creds
    client = MagicMock()
    mock_build.return_value = client

    result = gmail._service("alice@example.com")

    mock_credentials_for_user.assert_called_once_with(gmail._wif_cache, "alice@example.com")
    mock_build.assert_called_once_with(
        "gmail",
        "v1",
        credentials=creds,
        cache_discovery=False,
    )
    assert result is client


def test_wif_cache_invalidate_clears_config(wif_cache: WifConfigCache) -> None:
    wif_cache._config = {"type": "service_account"}
    wif_cache._loaded_at = 1.0

    wif_cache.invalidate()

    assert wif_cache._config is None
    assert wif_cache._loaded_at == 0.0
