# Enterprise Gmail MCP Server

A secure, enterprise-centric MCP server for Gmail that mirrors the [official MCP toolset by Google](https://developers.google.com/workspace/gmail/api/reference/mcp), enabling AI agents to impersonate corporate Gmail users in **domain-wide delegation (DWD)** scenarios. Assumes a service account, [DWD](https://knowledge.workspace.google.com/admin/apps/control-api-access-with-domain-wide-delegation) and [**Workload Identity Federation (WIF)**](https://docs.cloud.google.com/iam/docs/workload-identity-federation) have been set up.

This tool is used by Vincent, a SAS [agent](https://github.com/singulart/google-workspace-agent) running on AWS Bedrock AgentCore.

## Tools

Same names and schemas as Google's official MCP ([reference](https://developers.google.com/workspace/gmail/api/reference/mcp)), plus required `email` (user to impersonate):

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
2. **Workspace admin**: Domain-wide delegation for that SA with scope `https://www.googleapis.com/auth/gmail.modify` (or `https://mail.google.com/`).
3. **AWS**: WIF external-account JSON (or service account JSON) stored in **SSM Parameter Store** (SecureString recommended).
4. **Runtime IAM**: Permission to `ssm:GetParameter` on that parameter.

### SSM parameter value

Store the Google credential config JSON. Supported `type` values:

- `external_account` — [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation) (recommended on AWS).
- `service_account` — classic SA key JSON (if your org still uses keys).

Example (WIF): the JSON downloaded when configuring an AWS workload identity pool provider for your GCP service account.

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `GMAIL_WIF_SSM_PARAMETER` | Yes | SSM parameter name for the WIF/SA JSON |
| `AWS_REGION` | No | AWS region for SSM (uses default chain if unset) |
| `GMAIL_WIF_CACHE_TTL_SECONDS` | No | In-memory cache TTL for SSM payload (default `3600`; `0` = cache until process exit) |

Standard AWS credential chain applies (`AWS_ACCESS_KEY_ID`, instance role, etc.).

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