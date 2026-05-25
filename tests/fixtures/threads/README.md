# Thread fixtures (Gmail API shape)

Synthetic Gmail API-shaped data for offline tests. No credentials or live mailbox data.

## Python modules with `"""` body text

Each `*.py` file defines a **`FIXTURE`** dict. Message bodies use **`bodyText`** as a normal Python string (triple-quoted for multi-line HTML/plain):

```python
FIXTURE = {
    "description": "HTML-only with anchor link",
    "payload": {
        "mimeType": "text/html",
        "bodyText": """<p>Hello <a href="https://example.com">click here</a></p>""",
    },
}
```

At load time, `tests/fixture_loader.py` converts `bodyText` → Gmail API `body.size` + `body.data` (base64url). Tests call `load_fixture()` so they see the same shape as production.

## Single-message payloads

| File | Purpose |
|------|---------|
| `plain_only.py` | Single `text/plain` body |
| `html_only.py` | Single `text/html` body with anchor link |
| `multipart_alternative.py` | `multipart/alternative` with plain + HTML |
| `nested_multipart.py` | `multipart/mixed` with alternative + PDF attachment |
| `gmail_quote.py` | HTML with Gmail `gmail_quote` block (reply stripping) |
| `outlook_quoted_reply.py` | Plain text with `-----Original Message-----` |
| `html_marketing.py` | HTML-heavy marketing newsletter layout |
| `empty_body.py` | Whitespace-only plain body |

## Full thread

| File | Purpose |
|------|---------|
| `long_thread.py` | Thread with 12 messages (message limits, window tests) |

## Loaders

```python
from tests.fixture_loader import load_payload_fixture, load_thread_fixture

load_payload_fixture("plain_only.py")
load_thread_fixture("long_thread.py")
```

Pass `plain_only` or `plain_only.py` — both resolve to the `.py` module.

```bash
pytest tests/test_fixture_corpus.py
```
