"""Test fixtures for TeamFlow tests."""

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture_json(name: str) -> dict:
    path = FIXTURES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def load_fixture_raw(name: str) -> str:
    path = FIXTURES_DIR / name
    return path.read_text(encoding="utf-8")


@pytest.fixture
def sample_message_event() -> dict:
    return load_fixture_json("events/sample_message_event.json")


@pytest.fixture
def sample_card_action_event() -> dict:
    return load_fixture_json("events/sample_card_action_event.json")


@pytest.fixture
def sample_chat_member_added_event() -> dict:
    return load_fixture_json("events/sample_chat_member_added_event.json")


@pytest.fixture
def sample_ndjson_line() -> str:
    return load_fixture_raw("events/sample_message.ndjson").strip()
