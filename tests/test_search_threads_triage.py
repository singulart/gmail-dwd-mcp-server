from __future__ import annotations

from unittest.mock import MagicMock

from gmail_dwd_mcp.gmail_service import GmailService


def _gmail_with_list(n_threads: int) -> tuple[GmailService, MagicMock]:
    gmail = GmailService(wif_cache=MagicMock())
    mock_service = MagicMock()
    mock_service.users.return_value.threads.return_value.list.return_value.execute.return_value = {
        "threads": [
            {"id": f"thread-{i}", "snippet": f"Preview for thread {i}"}
            for i in range(n_threads)
        ],
    }
    gmail._service = MagicMock(return_value=mock_service)  # type: ignore[method-assign]
    return gmail, mock_service


def test_search_threads_uses_only_threads_list() -> None:
    n = 20
    gmail, mock_service = _gmail_with_list(n)

    result = gmail.search_threads("user@example.com", page_size=n)

    assert mock_service.users.return_value.threads.return_value.list.return_value.execute.call_count == 1
    assert (
        mock_service.users.return_value.threads.return_value.get.return_value.execute.call_count
        == 0
    )
    assert len(result.threads) == n
    for i, thread in enumerate(result.threads):
        assert thread.id.startswith("thread-")
        assert thread.snippet == f"Preview for thread {i}"
        dumped = thread.model_dump(by_alias=True)
        assert dumped == {"id": thread.id, "snippet": f"Preview for thread {i}"}
        assert "messages" not in dumped
        assert "body" not in dumped


def test_search_threads_omits_snippet_when_list_row_has_none() -> None:
    gmail, _ = _gmail_with_list(1)
    mock_service = gmail._service("user@example.com")
    mock_service.users.return_value.threads.return_value.list.return_value.execute.return_value = {
        "threads": [{"id": "thread-0"}],
    }

    result = gmail.search_threads("user@example.com", page_size=1)

    assert result.threads[0].snippet is None
    assert "snippet" not in result.threads[0].model_dump(by_alias=True, exclude_none=True)
