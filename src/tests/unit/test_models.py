"""Tests for storage/models.py — SQLModel model definitions."""

import json
from datetime import UTC, datetime

from teamflow.core.enums import (
    BindingStatus,
    MemberRole,
    MemberStatus,
    ProjectStatus,
    WorkspaceStatus,
)
from teamflow.storage.models import (
    ActionLog,
    ConversationState,
    EventLog,
    Project,
    ProjectAccessBinding,
    ProjectMember,
    UserIdentityBinding,
)


class TestProjectModel:
    def test_create_project_defaults(self):
        project = Project(
            name="Test Project",
            admin_open_id="ou_admin",
        )
        assert project.name == "Test Project"
        assert project.admin_open_id == "ou_admin"
        assert project.status == ProjectStatus.creating
        assert project.workspace_status == WorkspaceStatus.pending
        assert project.id is not None  # UUID auto-generated
        assert project.created_at is not None
        assert project.updated_at is not None

    def test_create_project_with_git_repo(self):
        project = Project(
            name="Test Project",
            git_repo_path="https://git.example.com/org/repo",
            admin_open_id="ou_admin",
        )
        assert project.git_repo_path == "https://git.example.com/org/repo"
        assert project.git_repo_platform is None

    def test_project_feishu_fields_default_empty(self):
        project = Project(name="P1", admin_open_id="ou_1")
        assert project.feishu_group_id is None
        assert project.feishu_group_link is None
        assert project.feishu_doc_url is None


class TestConversationStateModel:
    def test_create_conversation_state(self):
        conv = ConversationState(
            open_id="ou_user",
            chat_id="oc_chat",
            flow="create_project",
            state="collecting_name",
            payload=json.dumps({"key": "value"}),
            expires_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
        assert conv.flow == "create_project"
        assert conv.state == "collecting_name"
        parsed = json.loads(conv.payload)
        assert parsed["key"] == "value"


class TestEventLogModel:
    def test_create_event_log(self):
        event = EventLog(
            event_type="project.created",
            idempotency_key="project.created:abc123",
            project_id="p1",
            source="teamflow",
            payload=json.dumps({"project_name": "Test"}),
        )
        assert event.event_type == "project.created"
        assert event.project_id == "p1"
        assert event.status == "pending"
        parsed = json.loads(event.payload)
        assert parsed["project_name"] == "Test"


class TestActionLogModel:
    def test_create_action_log(self):
        action = ActionLog(
            project_id="p1",
            action_name="project_flow.create",
            target="ou_user",
            input_summary=json.dumps({"name": "Test"}),
            result="success",
        )
        assert action.action_name == "project_flow.create"
        assert action.result == "success"
        assert action.created_at is not None


class TestUserIdentityBindingModel:
    def test_create_binding(self):
        binding = UserIdentityBinding(
            open_id="ou_user",
            gitea_username="gituser",
            gitea_user_id=42,
            email="user@example.com",
        )
        assert binding.open_id == "ou_user"
        assert binding.gitea_username == "gituser"
        assert binding.email == "user@example.com"
        assert binding.status == BindingStatus.active


class TestProjectAccessBindingModel:
    def test_create_binding(self):
        binding = ProjectAccessBinding(
            project_id="p1",
            feishu_chat_id="oc_chat",
            gitea_org_name="MyOrg",
            gitea_team_id=99,
            gitea_team_name="test-team",
        )
        assert binding.project_id == "p1"
        assert binding.gitea_team_id == 99
        assert binding.status == BindingStatus.active


class TestProjectMemberModel:
    def test_create_member(self):
        member = ProjectMember(
            project_id="p1",
            open_id="ou_user",
            gitea_username="gituser",
            role=MemberRole.developer,
            source="chat_join",
        )
        assert member.project_id == "p1"
        assert member.role == MemberRole.developer
        assert member.status == MemberStatus.active

    def test_admin_role(self):
        member = ProjectMember(
            project_id="p1",
            open_id="ou_admin",
            role=MemberRole.admin,
        )
        assert member.role == MemberRole.admin
