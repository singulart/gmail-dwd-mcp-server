"""AWS Lambda entrypoint for Gmail DWD MCP (Streamable HTTP transport).

Required environment variables (same as stdio server):
  GMAIL_WIF_SSM_PARAMETER, optional GMAIL_WIF_CACHE_TTL_SECONDS, AWS_REGION.
  GMAIL_ALLOWED_HOSTS_SSM_PARAMETER — SSM parameter name (plain text) listing
    allowed HTTP Host header values for DNS rebinding protection.
Optional:
  API_GATEWAY_BASE_PATH — stage prefix when using REST API (e.g. ``/prod``).
  LOG_LEVEL — Python root log level (default INFO; use DEBUG for verbose output).
  FASTMCP_LOG_LEVEL — MCP SDK log level (DEBUG, INFO, …).
  FASTMCP_DEBUG — set to ``true`` for Starlette/MCP debug mode.

Each HTTP request uses a fresh ``StreamableHTTPSessionManager`` so MCP background
tasks are cancelled when the response is sent. A container-wide session manager
would keep ``app.run()`` alive and cause Lambda to hit its timeout.
"""

from __future__ import annotations

import logging
import os
import sys

from mangum import Mangum
from starlette.types import Receive, Scope, Send

from mcp.server.fastmcp.server import StreamableHTTPASGIApp

from gmail_dwd_mcp.server import create_http_session_manager, mcp

_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=_log_level,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger("gmail_dwd_mcp.lambda")

# Ensure transport security / routes are initialized once per cold start.
mcp.streamable_http_app()

logger.info(
    "Handler module loaded (LOG_LEVEL=%s, GMAIL_ALLOWED_HOSTS_SSM_PARAMETER=%s)",
    _log_level,
    os.environ.get("GMAIL_ALLOWED_HOSTS_SSM_PARAMETER", "(unset)"),
)


def _header(scope: Scope, name: str) -> str | None:
    name_bytes = name.lower().encode()
    for key, value in scope.get("headers", []):
        if key.lower() == name_bytes:
            return value.decode("latin-1")
    return None


async def _drain_disconnect(receive: Receive) -> None:
    """Consume Mangum's http.disconnect so the ASGI stack can finish."""
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return


class _LambdaASGIApp:
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return

        method = scope.get("method")
        path = scope.get("path")
        host = _header(scope, "host")
        logger.info("HTTP %s %s Host=%s", method, path, host)

        manager = create_http_session_manager()
        async with manager.run():
            await StreamableHTTPASGIApp(manager)(scope, receive, send)

        await _drain_disconnect(receive)
        logger.info("HTTP %s %s completed", method, path)


handler = Mangum(
    _LambdaASGIApp(),
    lifespan="off",
    api_gateway_base_path=os.environ.get("API_GATEWAY_BASE_PATH") or None,
)

logger.info("Mangum handler configured (lifespan=off, per-request session manager)")
