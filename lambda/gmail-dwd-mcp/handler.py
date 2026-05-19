"""AWS Lambda entrypoint for Gmail DWD MCP (Streamable HTTP transport).

Configure the Lambda handler as ``handler.handler``. Point API Gateway (HTTP API)
at ``ANY /mcp`` (and ``ANY /mcp/{proxy+}`` if needed) so clients can reach the
MCP Streamable HTTP endpoint (default path ``/mcp``).

Required environment variables (same as stdio server):
  GMAIL_WIF_SSM_PARAMETER, optional GMAIL_WIF_CACHE_TTL_SECONDS, AWS_REGION.
Optional:
  API_GATEWAY_BASE_PATH — stage prefix when using REST API (e.g. ``/prod``).
  LOG_LEVEL — Python root log level (default INFO; use DEBUG for verbose output).
  FASTMCP_LOG_LEVEL — MCP SDK log level (DEBUG, INFO, …).
  FASTMCP_DEBUG — set to ``true`` for Starlette/MCP debug mode.
  MCP_ALLOWED_HOST_SUFFIXES — comma-separated DNS suffixes (e.g.
    ``.lambda-url.us-east-1.on.aws``); MCP has no ``*.domain`` wildcard support.
  MCP_ALLOWED_HOSTS — comma-separated exact Host values (alternative to suffixes).
  MCP_DISABLE_DNS_REBINDING_PROTECTION — set to ``true`` to skip host checks.

Mangum uses ``lifespan="off"`` because it runs ASGI lifespan startup/shutdown on
every invocation. The MCP ``StreamableHTTPSessionManager`` only allows ``run()``
once per instance; shutting down between warm invocations would break the next
request. We start the session manager once per execution environment instead.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import AsyncExitStack

from mangum import Mangum
from starlette.types import Receive, Scope, Send

from gmail_dwd_mcp.server import mcp

# Lambda sends stdout/stderr and root-logger output to CloudWatch.
_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=_log_level,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger("gmail_dwd_mcp.lambda")

logger.info(
    "Handler module loaded (LOG_LEVEL=%s, FASTMCP_LOG_LEVEL=%s, FASTMCP_DEBUG=%s)",
    _log_level,
    os.environ.get("FASTMCP_LOG_LEVEL", "(default)"),
    os.environ.get("FASTMCP_DEBUG", "(default)"),
)

_starlette_app = mcp.streamable_http_app()
_lifecycle = AsyncExitStack()
_init_lock: asyncio.Lock | None = None
_session_manager_started = False


def _parse_host_suffixes() -> tuple[str, ...]:
    raw = os.environ.get("MCP_ALLOWED_HOST_SUFFIXES", "")
    suffixes: list[str] = []
    for part in raw.split(","):
        part = part.strip().lower()
        if not part:
            continue
        if not part.startswith("."):
            part = f".{part}"
        suffixes.append(part)
    return tuple(suffixes)


_ALLOWED_HOST_SUFFIXES = _parse_host_suffixes()


def _header(scope: Scope, name: str) -> str | None:
    name_bytes = name.lower().encode()
    for key, value in scope.get("headers", []):
        if key.lower() == name_bytes:
            return value.decode("latin-1")
    return None


def _host_matches_suffix(host: str | None) -> bool:
    if not _ALLOWED_HOST_SUFFIXES:
        return True
    if not host:
        return False
    hostname = host.split(":")[0].lower()
    return any(
        hostname.endswith(suffix) or hostname == suffix[1:]
        for suffix in _ALLOWED_HOST_SUFFIXES
    )


async def _send_plain_response(
    scope: Scope,
    receive: Receive,
    send: Send,
    *,
    status: int,
    body: bytes,
) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [[b"content-type", b"text/plain"]],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _ensure_session_manager() -> None:
    """Start StreamableHTTP session manager once per Lambda container."""
    global _init_lock, _session_manager_started

    if _session_manager_started:
        return

    if _init_lock is None:
        _init_lock = asyncio.Lock()

    async with _init_lock:
        if _session_manager_started:
            return
        logger.info("Starting StreamableHTTP session manager")
        await _lifecycle.enter_async_context(mcp.session_manager.run())
        _session_manager_started = True
        logger.info("StreamableHTTP session manager ready")


class _LambdaASGIApp:
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            host = _header(scope, "host")
            await _ensure_session_manager()
            logger.info(
                "HTTP %s %s Host=%s",
                scope.get("method"),
                scope.get("path"),
                host,
            )
            if not _host_matches_suffix(host):
                logger.warning("Rejected Host header (suffix allowlist): %s", host)
                await _send_plain_response(
                    scope,
                    receive,
                    send,
                    status=421,
                    body=b"Invalid Host header",
                )
                return
        await _starlette_app(scope, receive, send)


handler = Mangum(
    _LambdaASGIApp(),
    lifespan="off",
    api_gateway_base_path=os.environ.get("API_GATEWAY_BASE_PATH") or None,
)

logger.info("Mangum handler configured (lifespan=off)")
