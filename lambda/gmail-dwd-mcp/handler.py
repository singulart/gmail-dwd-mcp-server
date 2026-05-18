"""AWS Lambda entrypoint for Gmail DWD MCP (Streamable HTTP transport).

Configure the Lambda handler as ``handler.handler``. Point API Gateway (HTTP API)
at ``ANY /mcp`` (and ``ANY /mcp/{proxy+}`` if needed) so clients can reach the
MCP Streamable HTTP endpoint (default path ``/mcp``).

Required environment variables (same as stdio server):
  GMAIL_WIF_SSM_PARAMETER, optional GMAIL_WIF_CACHE_TTL_SECONDS, AWS_REGION.
Optional:
  API_GATEWAY_BASE_PATH — stage prefix when using REST API (e.g. ``/prod``).
"""

from __future__ import annotations

import os

from mangum import Mangum

from gmail_dwd_mcp.server import mcp

# Built once per execution environment (warm container reuse).
_app = mcp.streamable_http_app()

handler = Mangum(
    _app,
    lifespan="auto",
    api_gateway_base_path=os.environ.get("API_GATEWAY_BASE_PATH") or None,
)
