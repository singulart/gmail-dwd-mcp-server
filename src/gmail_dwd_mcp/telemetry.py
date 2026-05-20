"""OpenTelemetry setup for AWS Distro for OpenTelemetry (ADOT)."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, TypeVar

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import NoOpTracerProvider, ProxyTracerProvider
from opentelemetry.trace import SpanKind, Status, StatusCode

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

_TRACER: trace.Tracer | None = None


def is_telemetry_enabled() -> bool:
    """Telemetry runs only when deployed with AgentCore observability (e.g. Docker image)."""
    return os.environ.get("AGENT_OBSERVABILITY_ENABLED", "").lower() in ("true", "1", "yes")


def _otel_already_configured() -> bool:
    provider = trace.get_tracer_provider()
    return isinstance(provider, TracerProvider) and not isinstance(
        provider, (NoOpTracerProvider, ProxyTracerProvider)
    )


def setup_telemetry() -> None:
    """Configure ADOT and auto-instrumentation (call once before serving traffic)."""
    global _TRACER

    if not is_telemetry_enabled():
        logger.debug("OpenTelemetry disabled (AGENT_OBSERVABILITY_ENABLED is not set)")
        return

    if _otel_already_configured():
        _TRACER = trace.get_tracer("gmail_dwd_mcp")
        logger.debug("OpenTelemetry already configured (e.g. opentelemetry-instrument)")
        return

    os.environ.setdefault("OTEL_PYTHON_DISTRO", "aws_distro")
    os.environ.setdefault("OTEL_PYTHON_CONFIGURATOR", "aws_configurator")
    os.environ.setdefault("OTEL_PROPAGATORS", "xray")
    os.environ.setdefault("OTEL_AWS_APPLICATION_SIGNALS_ENABLED", "false")
    os.environ.setdefault("OTEL_SERVICE_NAME", "gmail-dwd-mcp-server")
    # AgentCore Runtime: collector-less export to regional X-Ray / CloudWatch OTLP (http/protobuf).
    # Do not set OTEL_EXPORTER_OTLP_ENDPOINT to localhost:4317 — that blocks ADOT auto-config.
    os.environ.setdefault("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")

    from opentelemetry.instrumentation.auto_instrumentation import initialize

    try:
        initialize(swallow_exceptions=False)
    except Exception:
        logger.exception("Failed to initialize OpenTelemetry (ADOT)")
        raise

    _TRACER = trace.get_tracer("gmail_dwd_mcp")
    traces_endpoint = (
        os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        or "(ADOT default)"
    )
    logger.info(
        "OpenTelemetry initialized (distro=%s, agent_observability=%s, traces_endpoint=%s)",
        os.environ.get("OTEL_PYTHON_DISTRO"),
        os.environ.get("AGENT_OBSERVABILITY_ENABLED", "false"),
        traces_endpoint,
    )


def get_tracer() -> trace.Tracer:
    if _TRACER is None:
        return trace.get_tracer("gmail_dwd_mcp")
    return _TRACER


@contextmanager
def tool_span(tool_name: str, *, email: str) -> Iterator[None]:
    """Span for an MCP tool invocation."""
    tracer = get_tracer()
    with tracer.start_as_current_span(
        tool_name,
        kind=SpanKind.INTERNAL,
        attributes={
            "mcp.tool.name": tool_name,
            "enduser.email": email,
        },
    ):
        yield


def traced_gmail_method(method: F) -> F:
    """Decorator for GmailService methods: span per API operation."""

    @wraps(method)
    def wrapper(self: Any, email: str, *args: Any, **kwargs: Any) -> Any:
        tracer = get_tracer()
        span_name = f"gmail.{method.__name__}"
        with tracer.start_as_current_span(
            span_name,
            kind=SpanKind.CLIENT,
            attributes={
                "enduser.email": email,
                "gmail.operation": method.__name__,
            },
        ) as span:
            try:
                return method(self, email, *args, **kwargs)
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.record_exception(exc)
                raise

    return wrapper  # type: ignore[return-value]


__all__ = [
    "get_tracer",
    "is_telemetry_enabled",
    "setup_telemetry",
    "tool_span",
    "traced_gmail_method",
]
