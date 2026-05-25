from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixture_loader import (
    FIXTURES_DIR,
    b64_text,
    list_thread_fixture_names,
    load_fixture,
    load_payload_fixture,
    load_thread_fixture,
)

__all__ = [
    "FIXTURES_DIR",
    "b64_text",
    "list_thread_fixture_names",
    "load_fixture",
    "load_payload_fixture",
    "load_thread_fixture",
]


@pytest.fixture
def thread_fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture(params=list_thread_fixture_names())
def thread_fixture_name(request: pytest.FixtureRequest) -> str:
    return request.param
