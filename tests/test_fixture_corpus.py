from __future__ import annotations

import pytest

from tests.conftest import (
    FIXTURES_DIR,
    list_thread_fixture_names,
    load_fixture,
    load_payload_fixture,
    load_thread_fixture,
)

THREAD_FIXTURE = "long_thread.json"
MIN_FIXTURE_COUNT = 8


def test_fixture_directory_has_required_count() -> None:
    names = list_thread_fixture_names()
    assert len(names) >= MIN_FIXTURE_COUNT


@pytest.mark.parametrize("fixture_name", list_thread_fixture_names())
def test_each_fixture_loads_as_json(fixture_name: str) -> None:
    data = load_fixture(fixture_name)
    assert isinstance(data, dict)
    assert data, f"{fixture_name} is empty"


@pytest.mark.parametrize("fixture_name", list_thread_fixture_names())
def test_each_fixture_has_description(fixture_name: str) -> None:
    data = load_fixture(fixture_name)
    assert data.get("description"), f"{fixture_name} missing description"


def test_long_thread_has_at_least_ten_messages() -> None:
    thread = load_thread_fixture(THREAD_FIXTURE)
    assert thread["id"]
    assert len(thread["messages"]) >= 10
    for msg in thread["messages"]:
        assert msg.get("id")
        assert msg.get("payload")


@pytest.mark.parametrize(
    "fixture_name",
    [n for n in list_thread_fixture_names() if n != THREAD_FIXTURE],
)
def test_single_message_fixtures_expose_payload(fixture_name: str) -> None:
    payload = load_payload_fixture(fixture_name)
    assert payload.get("mimeType")


def test_readme_documents_all_json_fixtures() -> None:
    readme = (FIXTURES_DIR / "README.md").read_text(encoding="utf-8")
    for name in list_thread_fixture_names():
        assert name in readme, f"README missing {name}"
