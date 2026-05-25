from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "threads"


def b64_text(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def list_thread_fixture_names() -> list[str]:
    return sorted(path.name for path in FIXTURES_DIR.glob("*.json"))


def load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def load_payload_fixture(name: str) -> dict:
    data = load_fixture(name)
    if "payload" in data:
        return data["payload"]
    return data


def load_thread_fixture(name: str) -> dict:
    data = load_fixture(name)
    if "messages" not in data:
        raise ValueError(f"{name} is not a thread fixture (missing messages[])")
    return data


@pytest.fixture
def thread_fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture(params=list_thread_fixture_names())
def thread_fixture_name(request: pytest.FixtureRequest) -> str:
    return request.param
