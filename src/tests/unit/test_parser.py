"""Tests for access/parser.py — NDJSON event parsing."""

import json

from teamflow.access.parser import (
    extract_card_action_data,
    extract_chat_id,
    extract_chat_member_data,
    extract_message_text,
    extract_open_id,
    is_bot_message,
    parse_ndjson_line,
)
from teamflow.core.types import CardActionData, ChatMemberEventData, FeishuEvent


class TestParseNdjsonLine:
    def test_parse_valid_compact_event(self, sample_message_event):
        line = json.dumps(sample_message_event, ensure_ascii=False)
        event = parse_ndjson_line(line)
        assert event is not None
        assert isinstance(event, FeishuEvent)
        assert event.event_id == "abc123def456"
        assert event.event_type == "im.message.receive_v1"

    def test_parse_empty_line(self):
        assert parse_ndjson_line("") is None
        assert parse_ndjson_line("   ") is None

    def test_parse_invalid_json(self):
        assert parse_ndjson_line("{invalid json}") is None

    def test_parse_non_dict_json(self):
        assert parse_ndjson_line("42") is None
        assert parse_ndjson_line('"string"') is None

    def test_parse_event_without_type(self):
        event = parse_ndjson_line('{"header": {}, "data": "test"}')
        assert event is None

    def test_parse_event_with_flat_structure(self):
        line = json.dumps({
            "event_id": "evt_001",
            "event_type": "im.message.receive_v1",
            "message": {"chat_id": "oc_001"},
            "sender": {"sender_id": {"open_id": "ou_001"}, "sender_type": "user"},
        })
        event = parse_ndjson_line(line)
        assert event is not None
        assert event.event_id == "evt_001"

    def test_parse_event_with_nested_body(self):
        line = json.dumps({
            "header": {"event_id": "evt_nested", "event_type": "im.message.receive_v1"},
            "im.message.receive_v1": {
                "message": {"chat_id": "oc_nested"},
                "sender": {"sender_id": {"open_id": "ou_nested"}, "sender_type": "user"},
            },
        })
        event = parse_ndjson_line(line)
        assert event is not None
        assert event.event_type == "im.message.receive_v1"
        assert "message" in event.body


class TestIsBotMessage:
    def test_sender_type_app_is_bot(self):
        event = FeishuEvent(
            event_id="e1", event_type="im.message.receive_v1",
            body={"sender": {"sender_type": "app"}},
        )
        assert is_bot_message(event, "cli_test") is True

    def test_sender_type_bot_is_bot(self):
        event = FeishuEvent(
            event_id="e2", event_type="im.message.receive_v1",
            body={"sender": {"sender_type": "bot"}},
        )
        assert is_bot_message(event, "cli_test") is True

    def test_app_id_match_is_bot(self):
        event = FeishuEvent(
            event_id="e3", event_type="im.message.receive_v1",
            body={"sender": {"sender_id": {"app_id": "cli_test"}, "sender_type": "user"}},
        )
        assert is_bot_message(event, "cli_test") is True

    def test_user_message_is_not_bot(self):
        event = FeishuEvent(
            event_id="e4", event_type="im.message.receive_v1",
            body={"sender": {"sender_id": {"open_id": "ou_123"}, "sender_type": "user"}},
        )
        assert is_bot_message(event, "cli_test") is False


class TestExtractOpenId:
    def test_extract_from_sender(self, sample_message_event):
        event = FeishuEvent(
            event_id="e1",
            event_type="im.message.receive_v1",
            body=sample_message_event["event"],
        )
        assert extract_open_id(event) == "ou_user123"

    def test_extract_flat_sender_id(self):
        event = FeishuEvent(
            event_id="e1", event_type="im.message.receive_v1",
            body={"sender": {"sender_id": "ou_flat123"}, "sender_type": "user"},
        )
        assert extract_open_id(event) == "ou_flat123"


class TestExtractChatId:
    def test_extract_from_message(self, sample_message_event):
        event = FeishuEvent(
            event_id="e1",
            event_type="im.message.receive_v1",
            body=sample_message_event["event"],
        )
        assert extract_chat_id(event) == "oc_test123"

    def test_extract_flat(self):
        event = FeishuEvent(
            event_id="e1", event_type="im.message.receive_v1",
            body={"chat_id": "oc_flat"},
        )
        assert extract_chat_id(event) == "oc_flat"


class TestExtractMessageText:
    def test_extract_json_content(self, sample_message_event):
        event = FeishuEvent(
            event_id="e1",
            event_type="im.message.receive_v1",
            body=sample_message_event["event"],
        )
        assert extract_message_text(event) == "开始创建项目"

    def test_extract_plain_text(self):
        event = FeishuEvent(
            event_id="e1", event_type="im.message.receive_v1",
            body={"message": {"content": "plain text"}, "message_type": "text"},
        )
        assert extract_message_text(event) == "plain text"

    def test_empty_content(self):
        event = FeishuEvent(
            event_id="e1", event_type="im.message.receive_v1",
            body={},
        )
        assert extract_message_text(event) is None


class TestExtractCardActionData:
    def test_extract_full_card_action(self, sample_card_action_event):
        event = FeishuEvent(
            event_id="e1",
            event_type="card.action.trigger",
            body=sample_card_action_event,
        )
        card_data = extract_card_action_data(event)
        assert card_data is not None
        assert isinstance(card_data, CardActionData)
        assert card_data.open_id == "ou_user123"
        assert card_data.chat_id == "oc_test123"
        assert card_data.action_tag == "submit_project_form"
        assert card_data.form_values["project_name"] == "My Test Project"

    def test_extract_without_chat_id(self):
        event = FeishuEvent(
            event_id="e1", event_type="card.action.trigger",
            body={"event": {"operator": {"open_id": "ou_1"}}},
        )
        assert extract_card_action_data(event) is None

    def test_extract_without_open_id(self):
        event = FeishuEvent(
            event_id="e1", event_type="card.action.trigger",
            body={"event": {"context": {"open_chat_id": "oc_1"}}},
        )
        assert extract_card_action_data(event) is None


class TestExtractChatMemberData:
    def test_extract_member_added(self, sample_chat_member_added_event):
        event = FeishuEvent(
            event_id="e1",
            event_type="im.chat.member.user.added_v1",
            body=sample_chat_member_added_event,
        )
        data = extract_chat_member_data(event)
        assert data is not None
        assert isinstance(data, ChatMemberEventData)
        assert data.chat_id == "oc_test123"
        assert "ou_newmember_1" in data.open_ids

    def test_extract_flat_format(self):
        event = FeishuEvent(
            event_id="e1", event_type="im.chat.member.user.added_v1",
            body={"chat_id": "oc_flat", "users": [{"open_id": "ou_1"}, {"open_id": "ou_2"}]},
        )
        data = extract_chat_member_data(event)
        assert data is not None
        assert len(data.open_ids) == 2

    def test_extract_single_user_id(self):
        event = FeishuEvent(
            event_id="e1", event_type="im.chat.member.user.added_v1",
            body={"chat_id": "oc_1", "user_id": "ou_single"},
        )
        data = extract_chat_member_data(event)
        assert data is not None
        assert data.open_ids == ["ou_single"]

    def test_extract_without_users(self):
        event = FeishuEvent(
            event_id="e1", event_type="im.chat.member.user.added_v1",
            body={"chat_id": "oc_1"},
        )
        assert extract_chat_member_data(event) is None

    def test_extract_without_chat_id(self):
        event = FeishuEvent(
            event_id="e1", event_type="im.chat.member.user.added_v1",
            body={"users": [{"open_id": "ou_1"}]},
        )
        assert extract_chat_member_data(event) is None
