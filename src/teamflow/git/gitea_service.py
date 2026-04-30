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
        r = await self._client.post("/api/v1/user/repos", json=payload)
        if r.status_code not in (200, 201):
            raise GiteaServiceError(
                f"Failed to create repo '{safe_name}': {r.text}", r.status_code
            )
        data = r.json()
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

    async def check_token(self) -> bool:
        try:
            user = await self.get_current_user()
            logger.info(
                "Gitea token valid, user=%s (admin=%s)", user.username, user.is_admin
            )
            return True
        except GiteaServiceError:
            logger.warning("Gitea token invalid or unreachable")
            return False
