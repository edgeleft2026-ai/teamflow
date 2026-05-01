from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from teamflow.config.settings import GiteaConfig

logger = logging.getLogger(__name__)

_REPO_NAME_MAX_LEN = 100
_REPO_NAME_PATTERN = r"[^a-zA-Z0-9._\-]"


@dataclass
class RepoResult:
    full_name: str
    html_url: str
    clone_url: str
    ssh_url: str


@dataclass
class UserInfo:
    id: int
    username: str
    email: str
    is_admin: bool


@dataclass
class OrgInfo:
    id: int
    username: str
    full_name: str
    avatar_url: str


@dataclass
class TeamInfo:
    id: int
    name: str
    description: str
    permission: str
    includes_all_repositories: bool


@dataclass
class SearchedUser:
    id: int
    username: str
    email: str
    full_name: str
    avatar_url: str


@dataclass
class CreatedUser:
    id: int
    username: str
    email: str


class GiteaServiceError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GiteaService:
    def __init__(self, config: GiteaConfig) -> None:
        self._base_url = config.base_url.rstrip("/")
        self._token = config.access_token
        self._default_private = config.default_private
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"token {self._token}"},
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._token)

    async def get_current_user(self) -> UserInfo:
        r = await self._client.get("/api/v1/user")
        if r.status_code != 200:
            raise GiteaServiceError(
                f"Failed to get current user: {r.text}", r.status_code
            )
        data = r.json()
        return UserInfo(
            id=data["id"],
            username=data["username"],
            email=data.get("email", ""),
            is_admin=data.get("is_admin", False),
        )

    async def create_repo(
        self,
        name: str,
        *,
        org: str = "",
        private: bool | None = None,
        description: str = "",
        auto_init: bool = True,
    ) -> RepoResult:
        import re

        safe_name = re.sub(_REPO_NAME_PATTERN, "-", name).strip("-._")
        safe_name = safe_name[:_REPO_NAME_MAX_LEN]
        if not safe_name:
            raise GiteaServiceError(f"Invalid repo name after sanitization: {name}")

        payload = {
            "name": safe_name,
            "private": private if private is not None else self._default_private,
            "description": description,
            "auto_init": auto_init,
        }
        if org:
            endpoint = f"/api/v1/org/{org}/repos"
        else:
            endpoint = "/api/v1/user/repos"
        r = await self._client.post(endpoint, json=payload)
        if r.status_code not in (200, 201):
            raise GiteaServiceError(
                f"创建仓库 '{safe_name}' 失败: {r.text}", r.status_code
            )
        data = r.json()
        logger.info(
            "仓库已创建: %s (org=%s)", data["full_name"], org or "(个人)"
        )
        return RepoResult(
            full_name=data["full_name"],
            html_url=data["html_url"],
            clone_url=data["clone_url"],
            ssh_url=data.get("ssh_url", ""),
        )

    async def add_collaborator(
        self,
        repo_full_name: str,
        username: str,
        permission: str = "write",
    ) -> None:
        r = await self._client.put(
            f"/api/v1/repos/{repo_full_name}/collaborators/{username}",
            json={"permission": permission},
        )
        if r.status_code not in (200, 201, 204):
            raise GiteaServiceError(
                f"Failed to add collaborator '{username}' to '{repo_full_name}': {r.text}",
                r.status_code,
            )

    async def delete_repo(self, repo_full_name: str) -> None:
        r = await self._client.delete(f"/api/v1/repos/{repo_full_name}")
        if r.status_code not in (200, 204):
            raise GiteaServiceError(
                f"Failed to delete repo '{repo_full_name}': {r.text}",
                r.status_code,
            )

    async def list_orgs(self) -> list[OrgInfo]:
        """获取当前用户所属的组织列表。"""
        r = await self._client.get("/api/v1/user/orgs")
        if r.status_code != 200:
            raise GiteaServiceError(
                f"获取组织列表失败: {r.text}", r.status_code
            )
        data = r.json()
        orgs = []
        for item in data:
            orgs.append(OrgInfo(
                id=item["id"],
                username=item.get("username", ""),
                full_name=item.get("full_name", ""),
                avatar_url=item.get("avatar_url", ""),
            ))
        logger.info("已获取 %d 个组织", len(orgs))
        return orgs

    async def search_user_by_email(self, email: str) -> SearchedUser | None:
        """通过邮箱搜索 Gitea 用户（需要管理员 Token）。"""
        r = await self._client.get(
            "/api/v1/admin/users",
            params={"q": email, "limit": 10},
        )
        if r.status_code != 200:
            logger.warning("搜索用户失败 (非管理员Token?): %s", r.status_code)
            r2 = await self._client.get(
                "/api/v1/users/search",
                params={"q": email, "limit": 10},
            )
            if r2.status_code != 200:
                return None
            data = r2.json().get("data", [])
        else:
            data = r.json()

        for item in data:
            if item.get("email", "").lower() == email.lower():
                return SearchedUser(
                    id=item["id"],
                    username=item.get("login") or item.get("username", ""),
                    email=item.get("email", ""),
                    full_name=item.get("full_name", ""),
                    avatar_url=item.get("avatar_url", ""),
                )
        return None

    async def create_team(
        self,
        org: str,
        name: str,
        *,
        description: str = "",
        permission: str = "write",
        includes_all_repositories: bool = False,
    ) -> TeamInfo:
        """在组织下创建 Team。"""
        payload = {
            "name": name,
            "description": description,
            "permission": permission,
            "includes_all_repositories": includes_all_repositories,
            "units": [
                "repo.code",
                "repo.issues",
                "repo.pulls",
                "repo.releases",
            ],
        }
        r = await self._client.post(
            f"/api/v1/orgs/{org}/teams", json=payload
        )
        if r.status_code not in (200, 201):
            raise GiteaServiceError(
                f"创建 Team '{name}' 失败: {r.text}", r.status_code
            )
        data = r.json()
        logger.info("Team 已创建: %s (org=%s id=%d)", name, org, data["id"])
        return TeamInfo(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            permission=data.get("permission", permission),
            includes_all_repositories=data.get(
                "includes_all_repositories", includes_all_repositories
            ),
        )

    async def list_org_teams(self, org: str) -> list[TeamInfo]:
        """列出组织下的所有 Team。"""
        r = await self._client.get(f"/api/v1/orgs/{org}/teams")
        if r.status_code != 200:
            raise GiteaServiceError(
                f"获取组织 Team 列表失败: {r.text}", r.status_code
            )
        data = r.json()
        teams = []
        for item in data:
            teams.append(TeamInfo(
                id=item["id"],
                name=item.get("name", ""),
                description=item.get("description", ""),
                permission=item.get("permission", ""),
                includes_all_repositories=item.get(
                    "includes_all_repositories", False
                ),
            ))
        return teams

    async def add_team_member(self, team_id: int, username: str) -> None:
        """将用户添加到 Team。"""
        r = await self._client.put(
            f"/api/v1/teams/{team_id}/members/{username}"
        )
        if r.status_code not in (200, 204):
            raise GiteaServiceError(
                f"添加 Team 成员失败 (team={team_id}, user={username}): {r.text}",
                r.status_code,
            )
        logger.info("已添加 Team 成员: team=%d user=%s", team_id, username)

    async def remove_team_member(self, team_id: int, username: str) -> None:
        """从 Team 移除用户。"""
        r = await self._client.delete(
            f"/api/v1/teams/{team_id}/members/{username}"
        )
        if r.status_code not in (200, 204):
            raise GiteaServiceError(
                f"移除 Team 成员失败 (team={team_id}, user={username}): {r.text}",
                r.status_code,
            )
        logger.info("已移除 Team 成员: team=%d user=%s", team_id, username)

    async def add_team_repo(self, team_id: int, org: str, repo: str) -> None:
        """将仓库关联到 Team。"""
        r = await self._client.put(
            f"/api/v1/teams/{team_id}/repos/{org}/{repo}"
        )
        if r.status_code not in (200, 204):
            raise GiteaServiceError(
                f"关联仓库到 Team 失败 (team={team_id}, repo={org}/{repo}): {r.text}",
                r.status_code,
            )
        logger.info("已关联仓库到 Team: team=%d repo=%s/%s", team_id, org, repo)

    async def check_token(self) -> bool:
        try:
            user = await self.get_current_user()
            logger.info(
                "Gitea 令牌有效, user=%s (admin=%s)", user.username, user.is_admin
            )
            return True
        except GiteaServiceError:
            logger.warning("Gitea 令牌无效或不可达")
            return False

    async def admin_search_user(self, username: str) -> SearchedUser | None:
        """通过用户名精确搜索 Gitea 用户。

        优先使用管理员 API，失败则降级到公开搜索 API。
        """
        r = await self._client.get(
            "/api/v1/admin/users",
            params={"q": username, "limit": 10},
        )
        if r.status_code == 200:
            for item in r.json():
                if item.get("login", "").lower() == username.lower():
                    return SearchedUser(
                        id=item["id"],
                        username=item.get("login", ""),
                        email=item.get("email", ""),
                        full_name=item.get("full_name", ""),
                        avatar_url=item.get("avatar_url", ""),
                    )
            return None

        logger.warning("管理员搜索用户失败: status=%d, 降级到公开搜索", r.status_code)
        r2 = await self._client.get(
            "/api/v1/users/search",
            params={"q": username, "limit": 10},
        )
        if r2.status_code != 200:
            logger.warning("公开搜索用户也失败: status=%d", r2.status_code)
            return None
        for item in r2.json().get("data", []):
            if item.get("login", "").lower() == username.lower():
                return SearchedUser(
                    id=item["id"],
                    username=item.get("login", ""),
                    email=item.get("email", ""),
                    full_name=item.get("full_name", ""),
                    avatar_url=item.get("avatar_url", ""),
                )
        return None

    async def admin_create_user(
        self,
        username: str,
        email: str,
        password: str,
        *,
        full_name: str = "",
        must_change_password: bool = False,
        send_notification: bool = True,
    ) -> CreatedUser:
        """创建 Gitea 用户（管理员 API）。

        Args:
            username: 用户名
            email: 邮箱地址
            password: 初始密码
            full_name: 显示名称
            must_change_password: 是否强制首次登录修改密码
            send_notification: 是否发送注册通知邮件
        """
        payload = {
            "username": username,
            "email": email,
            "password": password,
            "must_change_password": must_change_password,
            "send_notification": send_notification,
            "full_name": full_name,
            "visibility": "public",
        }
        r = await self._client.post("/api/v1/admin/users", json=payload)
        if r.status_code not in (200, 201):
            raise GiteaServiceError(
                f"创建用户 '{username}' 失败: {r.text}", r.status_code
            )
        data = r.json()
        logger.info(
            "用户已创建: %s (email=%s)", data.get("login", username), email
        )
        return CreatedUser(
            id=data["id"],
            username=data.get("login", username),
            email=data.get("email", email),
        )

    async def admin_list_users(self, page: int = 1, limit: int = 50) -> list[SearchedUser]:
        """列出 Gitea 所有用户（管理员 API）。"""
        users = []
        r = await self._client.get(
            "/api/v1/admin/users",
            params={"page": page, "limit": limit},
        )
        if r.status_code != 200:
            raise GiteaServiceError(
                f"获取用户列表失败: {r.text}", r.status_code
            )
        for item in r.json():
            users.append(SearchedUser(
                id=item["id"],
                username=item.get("login", ""),
                email=item.get("email", ""),
                full_name=item.get("full_name", ""),
                avatar_url=item.get("avatar_url", ""),
            ))
        return users

    async def add_org_member(self, org: str, username: str) -> None:
        """将用户添加到组织。

        Gitea 通过团队来管理组织成员，此方法自动查找组织的
        Owners 团队并将用户加入该团队。
        """
        teams = await self.list_org_teams(org)
        owner_team = None
        for t in teams:
            if t.permission == "owner" or t.name == "Owners":
                owner_team = t
                break
        if not owner_team:
            raise GiteaServiceError(
                f"未找到组织 '{org}' 的 Owners 团队", 404
            )
        await self.add_team_member(owner_team.id, username)
        logger.info(
            "已添加组织成员: org=%s team=%s user=%s",
            org, owner_team.id, username,
        )

    async def check_admin_access(self) -> bool:
        """检查当前 Token 是否拥有管理员权限（write:admin scope）。

        通过调用 /api/v1/admin/users 接口来验证，403 表示权限不足。
        """
        r = await self._client.get(
            "/api/v1/admin/users", params={"limit": 1}
        )
        if r.status_code == 200:
            return True
        if r.status_code == 403:
            return False
        logger.warning("检查管理员权限返回异常: status=%d", r.status_code)
        return False
