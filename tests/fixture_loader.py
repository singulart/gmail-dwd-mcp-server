"""Load thread fixtures: human-readable bodyText → Gmail API body.data (base64url)."""

from __future__ import annotations

import base64
import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "threads"


def b64_text(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode()


def materialize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert bodyText fields into Gmail API body.size + body.data."""
    payload = copy.deepcopy(payload)
    body_text = payload.pop("bodyText", None)
    if body_text is not None:
        encoded = body_text.encode("utf-8")
        payload["body"] = {"size": len(encoded), "data": b64_text(body_text)}
    parts = payload.get("parts")
    if parts:
        payload["parts"] = [materialize_payload(part) for part in parts]
    return payload


def materialize_fixture(data: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(data)
    if "payload" in data:
        data["payload"] = materialize_payload(data["payload"])
    elif "mimeType" in data:
        return materialize_payload(data)
    if "messages" in data:
        for msg in data["messages"]:
            if "payload" in msg:
                msg["payload"] = materialize_payload(msg["payload"])
    return data


def _resolve_fixture_path(name: str) -> Path:
    path = FIXTURES_DIR / name
    if path.exists():
        return path
    stem = Path(name).stem
    for suffix in (".py", ".json"):
        candidate = FIXTURES_DIR / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Fixture not found: {name}")


def _load_python_fixture(path: Path) -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location(f"thread_fixture_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load fixture module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixture = getattr(module, "FIXTURE", None)
    if not isinstance(fixture, dict):
        raise ValueError(f"{path.name} must define FIXTURE dict")
    return fixture


def load_fixture_raw(name: str) -> dict[str, Any]:
    path = _resolve_fixture_path(name)
    if path.suffix == ".py":
        return _load_python_fixture(path)
    return json.loads(path.read_text(encoding="utf-8"))


def load_fixture(name: str) -> dict[str, Any]:
    return materialize_fixture(load_fixture_raw(name))


def load_payload_fixture(name: str) -> dict[str, Any]:
    data = load_fixture(name)
    if "payload" in data:
        return data["payload"]
    return data


def load_thread_fixture(name: str) -> dict[str, Any]:
    data = load_fixture(name)
    if "messages" not in data:
        raise ValueError(f"{name} is not a thread fixture (missing messages[])")
    return data


def list_thread_fixture_names() -> list[str]:
    return sorted(
        path.name
        for path in FIXTURES_DIR.glob("*.py")
        if path.name != "__init__.py" and not path.name.startswith("_")
    )
