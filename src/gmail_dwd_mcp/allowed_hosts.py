from __future__ import annotations

import threading
import time

import boto3


def parse_allowed_hosts(raw: str) -> list[str]:
    """Parse plain-text allowed hosts (one per line and/or comma-separated)."""
    hosts: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for part in line.split(","):
            host = part.strip()
            if host and not host.startswith("#"):
                hosts.append(host)
    return hosts


class AllowedHostsCache:
    """Loads and caches allowed HTTP Host values from SSM Parameter Store."""

    def __init__(
        self,
        parameter_name: str,
        *,
        aws_region: str | None,
        ttl_seconds: int,
    ) -> None:
        self._parameter_name = parameter_name
        self._ttl_seconds = max(ttl_seconds, 0)
        self._lock = threading.Lock()
        self._hosts: list[str] | None = None
        self._loaded_at: float = 0.0
        self._ssm = boto3.client("ssm", region_name=aws_region)

    def get_hosts(self) -> list[str]:
        now = time.monotonic()
        with self._lock:
            if self._hosts is not None and (
                self._ttl_seconds == 0 or now - self._loaded_at < self._ttl_seconds
            ):
                return list(self._hosts)
            response = self._ssm.get_parameter(
                Name=self._parameter_name,
                WithDecryption=True,
            )
            self._hosts = parse_allowed_hosts(response["Parameter"]["Value"])
            self._loaded_at = now
            return list(self._hosts)

    def invalidate(self) -> None:
        with self._lock:
            self._hosts = None
            self._loaded_at = 0.0
