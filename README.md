# Enterprise Gmail MCP Server

A secure, enterprise-centric MCP server for Gmail that mirrors the [official MCP toolset by Google](https://developers.google.com/workspace/gmail/api/reference/mcp), enabling AI agents to impersonate corporate Gmail users in domain-wide delegation (DWD) scenarios. Assumes a service account, [DWD](https://knowledge.workspace.google.com/admin/apps/control-api-access-with-domain-wide-delegation) and [**Workload Identity Federation (WIF)**](https://docs.cloud.google.com/iam/docs/workload-identity-federation) have been set up.

This tool is used by Vincent, a SAS [agent](https://github.com/singulart/google-workspace-agent) running on AWS Bedrock AgentCore.

## Tools

We kept same names and schemas as Google's official MCP ([reference](https://developers.google.com/workspace/gmail/api/reference/mcp)), and added a required `email` parameter to each tool to set a corporate Gmail user to impersonate:

| Tool | Description |
|------|-------------|
| `search_threads` | List threads with optional Gmail query |
| `get_thread` | Fetch a thread and its messages |
| `list_drafts` | List drafts |
| `create_draft` | Create a draft |
| `list_labels` | List user labels |
| `create_label` | Create a label |
| `label_message` | Add labels to a message |
| `unlabel_message` | Remove labels from a message |
| `label_thread` | Add labels to a thread |
| `unlabel_thread` | Remove labels from a thread |

## Prerequisites

1. **Google Cloud**: Service account with Gmail API enabled.
2. **Google Cloud**: Note that `gmailmcp.googleapis.com` API doesn't have to be enabled.
3. **Workspace admin**: Domain-wide delegation for that SA with scope `https://www.googleapis.com/auth/gmail.modify` (or `https://mail.google.com/`).
4. **AWS**: WIF external-account JSON (or service account JSON) stored in **SSM Parameter Store** (SecureString recommended).
5. **Runtime IAM**: Permission to `ssm:GetParameter` on the WIF and (if used) allowed-hosts parameters.

### SSM parameter value

Store the Google credential config JSON. Supported `type` values:

- `external_account` — [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation) (recommended on AWS).
- `service_account` — classic SA key JSON (if your org still uses keys).

Example (WIF): the JSON downloaded when configuring an AWS workload identity pool provider for your GCP service account.

### Allowed hosts (Streamable HTTP)

When running with Streamable HTTP transport, create a separate **plain-text** SSM parameter (one host per line and/or comma-separated), for example your public API hostname:

```text
api.example.com
```

Point `GMAIL_ALLOWED_HOSTS_SSM_PARAMETER` at that parameter name. MCP validates exact `Host` values only (no `*.domain` wildcards). Omit this variable for stdio-only use; DNS rebinding checks stay disabled.

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `GMAIL_WIF_SSM_PARAMETER` | Yes | SSM parameter name for the WIF/SA JSON |
| `GMAIL_ALLOWED_HOSTS_SSM_PARAMETER` | No | SSM parameter name for plain-text allowed `Host` values (DNS rebinding protection for HTTP) |
| `AWS_REGION` | No | AWS region for SSM (uses default chain if unset) |
| `GMAIL_WIF_CACHE_TTL_SECONDS` | No | In-memory cache TTL for SSM parameters (default `3600`; `0` = cache until process exit) |
| `MCP_TRANSPORT` | No | `stdio` (default), `sse`, or `streamable-http` (set in Docker image) |
| `FASTMCP_HOST` / `FASTMCP_PORT` | No | HTTP bind address / port (default `127.0.0.1` / `8000`; Docker uses `0.0.0.0`) |

Standard AWS credential chain applies (`AWS_ACCESS_KEY_ID`, instance role, etc.).

## Observability (OpenTelemetry / ADOT on AgentCore Runtime)

This MCP server is intended to run on [Amazon Bedrock AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html) as a custom container (`0.0.0.0:8000/mcp`, stateless streamable HTTP). That is **not** an ECS task with an ADOT Collector sidecar on `localhost:4317`.

The server uses the [ADOT Python SDK](https://aws-otel.github.io/docs/getting-started/python-sdk) with in-process auto-instrumentation (**Starlette/ASGI**, **botocore**, outbound HTTP) plus custom spans per MCP tool and Gmail API call.

### AgentCore Runtime (recommended)

On AgentCore Runtime there is no local OTLP collector. With `AGENT_OBSERVABILITY_ENABLED=true`, the ADOT `aws_distro` configures **collector-less** export to regional AWS OTLP endpoints (using the runtime task role and `AWS_REGION`):

- Traces → `https://xray.<region>.amazonaws.com/v1/traces`
- Logs → `https://logs.<region>.amazonaws.com/v1/logs`

The Docker image sets this mode by default. **Do not** set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317` on AgentCore — it overrides ADOT’s auto-configuration and spans will not reach CloudWatch / X-Ray.

Prerequisites (once per account): enable [CloudWatch Transaction Search](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html#observability-configure-builtin) and enable **Tracing** on your AgentCore runtime in the console (spans appear in the `aws/spans` log group and GenAI Observability).

Optional correlation with runtime logs (replace `<agent-id>` with your runtime id):

```bash
export OTEL_RESOURCE_ATTRIBUTES=service.name=gmail-dwd-mcp-server,aws.log.group.names=/aws/bedrock-agentcore/runtimes/<agent-id>
export OTEL_EXPORTER_OTLP_LOGS_HEADERS=x-aws-log-group=/aws/bedrock-agentcore/runtimes/<agent-id>,x-aws-log-stream=runtime-logs,x-aws-metric-namespace=bedrock-agentcore
```

For distributed traces with the invoking agent, propagate `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` on MCP requests (ADOT maps this for session correlation). See [AgentCore observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html).

### Common environment variables

| Variable | AgentCore default | Description |
|----------|-------------------|-------------|
| `AGENT_OBSERVABILITY_ENABLED` | `true` (Docker) | Enables ADOT regional OTLP export (not localhost collector) |
| `OTEL_SERVICE_NAME` | `gmail-dwd-mcp-server` | Service name in traces / GenAI Observability |
| `OTEL_PYTHON_DISTRO` | `aws_distro` | ADOT defaults |
| `OTEL_PYTHON_CONFIGURATOR` | `aws_configurator` | ADOT SDK wiring |
| `OTEL_PROPAGATORS` | `xray` | X-Ray trace context propagation |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | Required for AWS OTLP endpoints |
| `OTEL_AWS_APPLICATION_SIGNALS_ENABLED` | `false` | Keep off unless using Application Signals |

Telemetry is **off** unless `AGENT_OBSERVABILITY_ENABLED=true` (set in the Docker image for AgentCore; omit locally). To disable in AWS, unset the variable or set `AGENT_OBSERVABILITY_ENABLED=false` on the runtime.

### Local dev or ECS with an ADOT Collector

Only if you run **outside** AgentCore with a collector sidecar, point OTLP at the collector (gRPC is typical):

```bash
unset AGENT_OBSERVABILITY_ENABLED
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
```

### Manual X-Ray endpoint (non-AgentCore)

```bash
unset AGENT_OBSERVABILITY_ENABLED
export OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://xray.us-east-1.amazonaws.com/v1/traces
export OTEL_RESOURCE_ATTRIBUTES=service.name=gmail-dwd-mcp-server
```

## Docker

```bash
docker build -t gmail-dwd-mcp-server .
docker run --rm -p 8000:8000 \
  -e GMAIL_WIF_SSM_PARAMETER=/your/org/gmail-wif-config \
  -e GMAIL_ALLOWED_HOSTS_SSM_PARAMETER=/your/org/gmail-allowed-hosts \
  -e AWS_REGION=us-east-1 \
  gmail-dwd-mcp-server
```

The image uses `python:3.14-slim`, listens on port **8000**, and runs Streamable HTTP at `/mcp` (`MCP_TRANSPORT=streamable-http`). Provide AWS credentials (task role, env keys, etc.) so the container can read SSM.

## Install & run

```bash
cd gmail-dwd-mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

export GMAIL_WIF_SSM_PARAMETER=/your/org/gmail-wif-config
export AWS_REGION=us-east-1

# stdio (Cursor, Claude Desktop, etc.)
gmail-dwd-mcp

# or
python -m gmail_dwd_mcp
```

### Cursor MCP config

```json
{
  "mcpServers": {
    "gmail-dwd": {
      "command": "/path/to/.venv/bin/gmail-dwd-mcp",
      "env": {
        "GMAIL_WIF_SSM_PARAMETER": "/your/org/gmail-wif-config",
        "AWS_REGION": "us-east-1"
      }
    }
  }
}
```

## Example tool call

Impersonate `user@company.com` and search inbox:

```json
{
  "name": "search_threads",
  "arguments": {
    "email": "user@company.com",
    "query": "is:unread",
    "pageSize": 10
  }
}
```

## License

MIT

## Credits

Built with ❤️ and AI in the District of Columbia
