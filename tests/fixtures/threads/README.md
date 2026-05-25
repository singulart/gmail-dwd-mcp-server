# Thread fixtures (Gmail API JSON)

Synthetic Gmail API-shaped JSON for offline tests. No credentials or live mailbox data.

## Single-message payloads

Use `payload` (or the file root for legacy loaders) with `load_payload_fixture(name)`.

| File | Purpose |
|------|---------|
| `plain_only.json` | Single `text/plain` body |
| `html_only.json` | Single `text/html` body with anchor link |
| `multipart_alternative.json` | `multipart/alternative` with plain + HTML |
| `nested_multipart.json` | `multipart/mixed` wrapping alternative + PDF attachment |
| `gmail_quote.json` | HTML with Gmail `gmail_quote` block (reply stripping) |
| `outlook_quoted_reply.json` | Plain text with `-----Original Message-----` (reply stripping) |
| `html_marketing.json` | HTML-heavy marketing layout (tables, images, links) |
| `empty_body.json` | Whitespace-only plain body |

## Full thread

| File | Purpose |
|------|---------|
| `long_thread.json` | Thread with 12 messages (message limits, window tests) |

## Loaders

- `load_payload_fixture("plain_only.json")` → message `payload` dict
- `load_thread_fixture("long_thread.json")` → full thread object with `messages[]`

Run corpus smoke tests: `pytest tests/test_fixture_corpus.py`
