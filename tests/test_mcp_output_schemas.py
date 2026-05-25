"""MCP tools/list outputSchema contracts for read tools."""

from __future__ import annotations

import asyncio
import json

from gmail_dwd_mcp.server import mcp


def _tool_schema(name: str) -> dict:
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    assert name in tools
    schema = tools[name].outputSchema
    assert schema is not None
    return schema


def test_get_thread_output_schema_describes_hydrated_thread() -> None:
    schema = _tool_schema("get_thread")
    assert schema["type"] == "object"
    props = schema["properties"]
    assert "id" in props
    assert "messages" in props
    msg_props = schema["$defs"]["HydratedMessage"]["properties"]
    assert "body" in msg_props
    assert "plaintextBody" not in msg_props
    assert "htmlBody" not in msg_props
    assert schema.get("additionalProperties") is not True


def test_get_threads_output_schema_describes_hydrate_result() -> None:
    schema = _tool_schema("get_threads")
    props = schema["properties"]
    assert set(props) >= {"threads", "errors", "meta"}
    assert "HydrateResult" in json.dumps(schema)


def test_search_threads_output_schema_describes_search_threads() -> None:
    schema = _tool_schema("search_threads")
    props = schema["properties"]
    assert "threads" in props
    search_thread = schema["$defs"]["SearchThread"]["properties"]
    assert "id" in search_thread
    assert "snippet" in search_thread
    assert "messages" not in search_thread
    assert "body" not in search_thread
    assert "SearchThread" in json.dumps(schema)
