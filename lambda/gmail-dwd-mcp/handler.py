"""AWS Lambda entrypoint for Gmail DWD MCP (Streamable HTTP transport).

Configure the Lambda handler as ``handler.handler``. Point API Gateway (HTTP API)
or Lambda Function URL at ``/mcp`` (Streamable HTTP endpoint).

Required environment variables (same as stdio server):
  GMAIL_WIF_SSM_PARAMETER, optional GMAIL_WIF_CACHE_TTL_SECONDS, AWS_REGION.
Optional:
  GMAIL_ALLOWED_HOSTS_SSM_PARAMETER — SSM parameter name (plain text) listing
    allowed HTTP Host header values for DNS rebinding protection.
  API_GATEWAY_BASE_PATH — stage prefix when using REST API (e.g. ``/prod``).
  LOG_LEVEL — Python root log level (default INFO; use DEBUG for verbose output).
  FASTMCP_LOG_LEVEL — MCP SDK log level (DEBUG, INFO, …).
  FASTMCP_DEBUG — set to ``true`` for Starlette/MCP debug mode.

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

_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=_log_level,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger("gmail_dwd_mcp.lambda")

logger.info(
    "Handler module loaded (LOG_LEVEL=%s, FASTMCP_LOG_LEVEL=%s, FASTMCP_DEBUG=%s, "
    "GMAIL_ALLOWED_HOSTS_SSM_PARAMETER=%s)",
    _log_level,
    os.environ.get("FASTMCP_LOG_LEVEL", "(default)"),
    os.environ.get("FASTMCP_DEBUG", "(default)"),
    os.environ.get("GMAIL_ALLOWED_HOSTS_SSM_PARAMETER", "(unset)"),
)

_starlette_app = mcp.streamable_http_app()
_lifecycle = AsyncExitStack()
_init_lock: asyncio.Lock | None = None
_session_manager_started = False



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
            await _ensure_session_manager()
        await _starlette_app(scope, receive, send)


handler = Mangum(
    _LambdaASGIApp(),
    lifespan="off",
    api_gateway_base_path=os.environ.get("API_GATEWAY_BASE_PATH") or None,
)

logger.info("Mangum handler configured (lifespan=off)")
