from __future__ import annotations

import json
import threading
import time
from typing import Any

import boto3
from google.auth import default as google_auth_default
from google.auth import load_credentials_from_dict
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request

from gmail_dwd_mcp.config import GMAIL_SCOPES, Settings


class WifConfigCache:
    """Loads and caches WIF / service-account config from SSM Parameter Store."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._config: dict[str, Any] | None = None
        self._loaded_at: float = 0.0
        self._ssm = boto3.client("ssm", region_name=settings.aws_region)

    def get_config(self) -> dict[str, Any]:
        ttl = self._settings.wif_cache_ttl_seconds
        now = time.monotonic()
        with self._lock:
            if self._config is not None and (ttl == 0 or now - self._loaded_at < ttl):
                return self._config
            response = self._ssm.get_parameter(
                Name=self._settings.ssm_parameter_name,
                WithDecryption=True,
            )
            raw = response["Parameter"]["Value"]
            self._config = json.loads(raw)
            self._loaded_at = now
            return self._config

    def invalidate(self) -> None:
        with self._lock:
            self._config = None
            self._loaded_at = 0.0


def _base_credentials(config: dict[str, Any]) -> Credentials:
    cred_type = config.get("type")
    if cred_type == "external_account":
        credentials, _ = load_credentials_from_dict(config)
        return credentials
    if cred_type == "service_account":
        credentials, _ = load_credentials_from_dict(config, scopes=GMAIL_SCOPES)
        return credentials
    # Allow ADC when running on GCP or with GOOGLE_APPLICATION_CREDENTIALS.
    credentials, _ = google_auth_default(scopes=GMAIL_SCOPES)
    return credentials


def credentials_for_user(cache: WifConfigCache, email: str) -> Credentials:
    """Return scoped credentials impersonating `email` via domain-wide delegation."""
    config = cache.get_config()
    credentials = _base_credentials(config)
    if hasattr(credentials, "with_scopes"):
        credentials = credentials.with_scopes(GMAIL_SCOPES)
    if not credentials.valid:
        credentials.refresh(Request())
    delegated = credentials.with_subject(email)
    if hasattr(delegated, "with_scopes"):
        delegated = delegated.with_scopes(GMAIL_SCOPES)
    if not delegated.valid:
        delegated.refresh(Request())
    return delegated
