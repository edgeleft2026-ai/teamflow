"""Tests for orchestration/event_bus.py — event publishing and subscription."""

import pytest
from sqlmodel import Session, SQLModel, create_engine

from teamflow.orchestration.event_bus import EventBus
from teamflow.storage.repository import EventLogRepo


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def event_bus(session):
    return EventBus(session)


class TestEventBusPublish:
    def test_publish_creates_event_log(self, event_bus, session):
        event = event_bus.publish(
            event_type="project.created",
            idempotency_key="project.created:abc123",
            project_id="proj_001",
            payload={"project_name": "Test"},
        )
        assert event is not None
        assert event.event_type == "project.created"
        assert event.project_id == "proj_001"
        assert event.status == "succeeded"

    def test_publish_is_idempotent(self, event_bus, session):
        event1 = event_bus.publish(
            event_type="test.event",
            idempotency_key="key_duplicate",
            project_id="p1",
        )
        event2 = event_bus.publish(
            event_type="test.event",
            idempotency_key="key_duplicate",
            project_id="p1",
        )
        assert event1 is not None
        assert event2 is None  # Duplicate, should not create new event

        repo = EventLogRepo(session)
        assert repo.exists_by_idempotency_key("key_duplicate") is True

    def test_publish_without_project_id(self, event_bus, session):
        event = event_bus.publish(
            event_type="system.startup",
            idempotency_key="startup_001",
        )
        assert event is not None
        assert event.event_type == "system.startup"
        assert event.project_id is None


class TestEventBusSubscribe:
    def test_global_subscription_called_on_publish(self, event_bus, session):
        received_events = []

        def handler(event):
            received_events.append(event)

        EventBus.subscribe_global("test.event", handler)
        event_bus.publish(
            event_type="test.event",
            idempotency_key="key_001",
            project_id="p1",
        )

        assert len(received_events) == 1
        assert received_events[0].event_type == "test.event"

    def test_global_subscription_not_called_on_duplicate(self, event_bus, session):
        received_events = []

        def handler(event):
            received_events.append(event)

        EventBus.subscribe_global("test.event", handler)
        event_bus.publish(
            event_type="test.event",
            idempotency_key="key_dup",
            project_id="p1",
        )
        event_bus.publish(
            event_type="test.event",
            idempotency_key="key_dup",
            project_id="p1",
        )

        assert len(received_events) == 1  # Handler only called once

    def test_multiple_global_subscribers(self, event_bus, session):
        results = []

        def handler_a(event):
            results.append("A")

        def handler_b(event):
            results.append("B")

        EventBus.subscribe_global("test.multi", handler_a)
        EventBus.subscribe_global("test.multi", handler_b)
        event_bus.publish(
            event_type="test.multi",
            idempotency_key="key_multi",
            project_id="p1",
        )

        assert results == ["A", "B"]

    def test_subscriber_exception_does_not_block_others(self, event_bus, session):
        results = []

        def failing_handler(event):
            raise RuntimeError("test error")

        def ok_handler(event):
            results.append("ok")

        EventBus.subscribe_global("test.exc", failing_handler)
        EventBus.subscribe_global("test.exc", ok_handler)
        event_bus.publish(
            event_type="test.exc",
            idempotency_key="key_exc",
            project_id="p1",
        )

        assert results == ["ok"]
