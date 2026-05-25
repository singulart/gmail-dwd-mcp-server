from __future__ import annotations

from unittest.mock import MagicMock

from gmail_dwd_mcp.gmail_service import GmailService


def _gmail_with_list(n_threads: int) -> tuple[GmailService, MagicMock]:
    gmail = GmailService(wif_cache=MagicMock())
    mock_service = MagicMock()
    mock_service.users.return_value.threads.return_value.list.return_value.execute.return_value = {
        "threads": [{"id": f"thread-{i}"} for i in range(n_threads)],
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
    for thread in result.threads:
        assert thread.id.startswith("thread-")
        assert thread.messages == []
        dumped = thread.model_dump(by_alias=True)
        assert "body" not in dumped
        assert "plaintextBody" not in dumped
        assert "htmlBody" not in dumped
