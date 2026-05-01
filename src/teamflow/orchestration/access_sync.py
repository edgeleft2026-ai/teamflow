"""Access sync flow — synchronize Feishu group membership with Gitea Team membership.

When a user joins a Feishu project group:
  1. Look up the Project by chat_id
  2. Look up the ProjectAccessBinding to find the Gitea Team
  3. Look up or create the UserIdentityBinding (via Feishu email → Gitea user)
  4. Add the user to the Gitea Team
  5. Record the ProjectMember

When a user leaves a Feishu project group:
  1. Same lookups as above
  2. Remove the user from the Gitea Team
  3. Update the ProjectMember status
"""

from __future__ import annotations

import logging
import re

import httpx

from teamflow.config import FeishuConfig
from teamflow.config.settings import GiteaConfig
from teamflow.core.enums import ActionResult, MemberRole
from teamflow.git.gitea_service import GiteaService
from teamflow.storage.database import get_session
from teamflow.storage.repository import (
    ActionLogRepo,
    ProjectAccessBindingRepo,
    ProjectMemberRepo,
    ProjectRepo,
    UserIdentityBindingRepo,
)

logger = logging.getLogger(__name__)

_TEAM_NAME_PATTERN = r"[^a-zA-Z0-9._\-]"


def _safe_team_name(project_name: str) -> str:
    safe = re.sub(_TEAM_NAME_PATTERN, "-", project_name).strip("-._")
    return safe[:50] or "project-team"


def _parse_repo_ref(repo_ref: str) -> tuple[str, str] | None:
    """从仓库引用中提取 (org, repo)。

    支持格式:
      - "Edgeleft/TeamFlow"
      - "https://git.lighter.games/Edgeleft/TeamFlow"
      - "https://git.lighter.games/Edgeleft/TeamFlow.git"
    """
    if not repo_ref:
        return None
    if "/" not in repo_ref:
        return None
    if repo_ref.startswith(("http://", "https://")):
        path = repo_ref.split("://", 1)[1]
        parts = path.split("/")
        if len(parts) >= 3:
            org = parts[-2]
            repo = parts[-1]
            if repo.endswith(".git"):
                repo = repo[:-4]
            return (org, repo)
        return None
    if "/" in repo_ref and not repo_ref.startswith("/"):
        parts = repo_ref.split("/", 1)
        return (parts[0], parts[1].removesuffix(".git"))
    return None


class AccessSyncFlow:
    def __init__(
        self,
        feishu: FeishuConfig,
        gitea_config: GiteaConfig,
    ) -> None:
        self.feishu = feishu
        self.gitea_config = gitea_config

    async def on_member_added(self, chat_id: str, open_id: str) -> None:
        try:
            await self._sync_member_added(chat_id, open_id)
        except Exception:
            logger.exception(
                "入群权限同步失败: chat=%s user=%s",
                chat_id[:8], open_id[:8],
            )

    async def on_member_removed(self, chat_id: str, open_id: str) -> None:
        try:
            await self._sync_member_removed(chat_id, open_id)
        except Exception:
            logger.exception(
                "退群权限回收失败: chat=%s user=%s",
                chat_id[:8], open_id[:8],
            )

    async def _sync_member_added(self, chat_id: str, open_id: str) -> None:
        with get_session() as session:
            project_repo = ProjectRepo(session)
            binding_repo = ProjectAccessBindingRepo(session)
            identity_repo = UserIdentityBindingRepo(session)
            member_repo = ProjectMemberRepo(session)
            action_repo = ActionLogRepo(session)

            access_binding = binding_repo.get_by_chat_id(chat_id)
            if not access_binding:
                logger.debug("群 %s 未绑定项目，跳过权限同步", chat_id[:8])
                return

            project = project_repo.get_by_id(access_binding.project_id)
            if not project:
                logger.warning("项目未找到: %s", access_binding.project_id[:8])
                return

            role = (
                MemberRole.admin
                if project.admin_open_id == open_id
                else MemberRole.developer
            )

            identity = identity_repo.get_by_open_id(open_id)
            gitea_username = identity.gitea_username if identity else ""

            if not gitea_username:
                email = await self._get_feishu_user_email(open_id)
                if email:
                    gitea_username = await self._try_bind_identity(
                        open_id, email, identity_repo, session,
                    )

            if gitea_username and access_binding.gitea_team_id:
                try:
                    gitea = GiteaService(self.gitea_config)
                    await gitea.add_team_member(
                        access_binding.gitea_team_id, gitea_username
                    )
                    await gitea.close()
                    logger.info(
                        "已添加 Gitea Team 成员: team=%d user=%s",
                        access_binding.gitea_team_id, gitea_username,
                    )
                except Exception as exc:
                    logger.warning(
                        "添加 Gitea Team 成员失败: team=%d user=%s, %s",
                        access_binding.gitea_team_id, gitea_username, exc,
                    )

            member_repo.add(
                access_binding.project_id,
                open_id,
                gitea_username=gitea_username,
                role=role,
                source="chat_join",
            )
            session.commit()

            action_repo.create(
                action_name="access_sync.member_added",
                project_id=access_binding.project_id,
                target=open_id,
                input_summary={
                    "chat_id": chat_id,
                    "gitea_username": gitea_username,
                    "team_id": access_binding.gitea_team_id,
                },
            )
            session.commit()

    async def _sync_member_removed(self, chat_id: str, open_id: str) -> None:
        with get_session() as session:
            binding_repo = ProjectAccessBindingRepo(session)
            identity_repo = UserIdentityBindingRepo(session)
            member_repo = ProjectMemberRepo(session)
            action_repo = ActionLogRepo(session)

            access_binding = binding_repo.get_by_chat_id(chat_id)
            if not access_binding:
                return

            identity = identity_repo.get_by_open_id(open_id)
            gitea_username = identity.gitea_username if identity else ""

            if gitea_username and access_binding.gitea_team_id:
                try:
                    gitea = GiteaService(self.gitea_config)
                    await gitea.remove_team_member(
                        access_binding.gitea_team_id, gitea_username
                    )
                    await gitea.close()
                    logger.info(
                        "已移除 Gitea Team 成员: team=%d user=%s",
                        access_binding.gitea_team_id, gitea_username,
                    )
                except Exception as exc:
                    logger.warning(
                        "移除 Gitea Team 成员失败: team=%d user=%s, %s",
                        access_binding.gitea_team_id, gitea_username, exc,
                    )

            member_repo.remove(access_binding.project_id, open_id)
            session.commit()

            action_repo.create(
                action_name="access_sync.member_removed",
                project_id=access_binding.project_id,
                target=open_id,
                input_summary={
                    "chat_id": chat_id,
                    "gitea_username": gitea_username,
                    "team_id": access_binding.gitea_team_id,
                },
                result=ActionResult.success,
            )
            session.commit()

    async def _try_bind_identity(
        self,
        open_id: str,
        email: str,
        identity_repo: UserIdentityBindingRepo,
        session,
    ) -> str:
        try:
            gitea = GiteaService(self.gitea_config)
            user = await gitea.search_user_by_email(email)
            await gitea.close()
            if user:
                identity_repo.upsert(
                    open_id,
                    user.username,
                    gitea_user_id=user.id,
                    email=email,
                )
                session.commit()
                logger.info(
                    "自动绑定身份: open_id=%s -> gitea=%s (email=%s)",
                    open_id[:8], user.username, email,
                )
                return user.username
        except Exception as exc:
            logger.warning("自动绑定身份失败: open_id=%s, %s", open_id[:8], exc)
        return ""

    async def _get_feishu_user_email(self, open_id: str) -> str:
        try:
            base_url = (
                "https://open.feishu.cn"
                if self.feishu.brand == "feishu"
                else "https://open.larksuite.com"
            )
            tenant_token = await self._get_tenant_token()
            if not tenant_token:
                return ""

            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{base_url}/open-apis/contact/v3/users/{open_id}",
                    headers={
                        "Authorization": f"Bearer {tenant_token}",
                        "Content-Type": "application/json",
                    },
                    params={"user_id_type": "open_id"},
                )
                if r.status_code == 200:
                    data = r.json()
                    user = data.get("data", {}).get("user", {})
                    return user.get("email") or user.get("enterprise_email") or ""
                logger.warning("获取飞书用户邮箱失败: status=%d", r.status_code)
        except Exception:
            logger.exception("获取飞书用户邮箱异常: open_id=%s", open_id[:8])
        return ""

    async def _get_tenant_token(self) -> str:
        try:
            base_url = (
                "https://open.feishu.cn"
                if self.feishu.brand == "feishu"
                else "https://open.larksuite.com"
            )
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{base_url}/open-apis/auth/v3/tenant_access_token/internal",
                    json={
                        "app_id": self.feishu.app_id,
                        "app_secret": self.feishu.app_secret,
                    },
                )
                if r.status_code == 200:
                    return r.json().get("tenant_access_token", "")
        except Exception:
            logger.exception("获取飞书 tenant_token 失败")
        return ""

    @staticmethod
    async def ensure_project_team(
        gitea_config: GiteaConfig,
        project_id: str,
        project_name: str,
        chat_id: str,
        org_name: str,
        repo_full_name: str | None = None,
    ) -> int | None:
        gitea = GiteaService(gitea_config)
        try:
            team_name = _safe_team_name(project_name)
            description = f"Team for project: {project_name}"

            existing_teams = await gitea.list_org_teams(org_name)
            team_id: int | None = None
            for t in existing_teams:
                if t.name == team_name:
                    team_id = t.id
                    logger.info("Team 已存在: %s (id=%d)", team_name, team_id)
                    break

            if team_id is None:
                team = await gitea.create_team(
                    org_name,
                    team_name,
                    description=description,
                    permission="write",
                    includes_all_repositories=False,
                )
                team_id = team.id

            if repo_full_name:
                parsed = _parse_repo_ref(repo_full_name)
                if parsed:
                    org, repo = parsed
                    await gitea.add_team_repo(team_id, org, repo)

            with get_session() as session:
                binding_repo = ProjectAccessBindingRepo(session)
                existing = binding_repo.get_by_project_id(project_id)
                if existing:
                    binding_repo.update_team(
                        project_id,
                        gitea_team_id=team_id,
                        gitea_team_name=team_name,
                    )
                else:
                    binding_repo.create(
                        project_id,
                        chat_id,
                        gitea_org_name=org_name,
                        gitea_team_id=team_id,
                        gitea_team_name=team_name,
                    )
                session.commit()

            return team_id
        except Exception:
            logger.exception("确保项目 Team 失败: project=%s", project_id[:8])
            return None
        finally:
            await gitea.close()
