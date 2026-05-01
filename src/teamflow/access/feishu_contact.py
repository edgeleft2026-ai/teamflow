"""飞书通讯录服务：获取企业全部用户及邮箱，发送互动卡片消息。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx

from teamflow.config.settings import FeishuConfig

logger = logging.getLogger(__name__)


@dataclass
class FeishuUser:
    open_id: str
    name: str
    email: str
    enterprise_email: str
    mobile: str


class FeishuContactService:
    def __init__(self, config: FeishuConfig) -> None:
        self._app_id = config.app_id
        self._app_secret = config.app_secret
        self._base_url = (
            "https://open.feishu.cn"
            if config.brand == "feishu"
            else "https://open.larksuite.com"
        )
        self._token = ""
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def _ensure_token(self) -> str:
        if self._token:
            return self._token
        r = await self._client.post(
            f"{self._base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self._app_id, "app_secret": self._app_secret},
        )
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_token 失败: {data}")
        self._token = data["tenant_access_token"]
        return self._token

    async def _get(self, path: str, params: dict | None = None) -> dict:
        token = await self._ensure_token()
        r = await self._client.get(
            f"{self._base_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
        )
        return r.json()

    async def get_all_departments(self) -> list[dict]:
        departments = []
        page_token = ""
        while True:
            params = {
                "department_id": "0",
                "department_id_type": "open_department_id",
                "fetch_child": "true",
                "page_size": 50,
                "user_id_type": "open_id",
            }
            if page_token:
                params["page_token"] = page_token
            data = await self._get("/open-apis/contact/v3/departments", params)
            if data.get("code") != 0:
                logger.warning("获取部门列表失败: %s", data.get("msg"))
                break
            departments.extend(data.get("data", {}).get("items", []))
            if data.get("data", {}).get("has_more"):
                page_token = data["data"]["page_token"]
            else:
                break
        return departments

    async def get_department_users(self, department_id: str = "0") -> list[dict]:
        users = []
        page_token = ""
        while True:
            params = {
                "department_id": department_id,
                "department_id_type": "open_department_id",
                "page_size": 100,
                "user_id_type": "open_id",
            }
            if page_token:
                params["page_token"] = page_token
            data = await self._get("/open-apis/contact/v3/users", params)
            if data.get("code") != 0:
                logger.warning(
                    "获取部门用户失败 (dept=%s): %s",
                    department_id,
                    data.get("msg"),
                )
                break
            users.extend(data.get("data", {}).get("items", []))
            if data.get("data", {}).get("has_more"):
                page_token = data["data"]["page_token"]
            else:
                break
        return users

    async def get_user_detail(self, open_id: str) -> dict:
        params = {
            "user_id_type": "open_id",
            "fields": (
                "open_id,union_id,user_id,name,en_name,email,mobile,"
                "enterprise_email,employee_no,employee_type,department_ids,"
                "job_title,status"
            ),
        }
        data = await self._get(f"/open-apis/contact/v3/users/{open_id}", params)
        if data.get("code") != 0:
            return {}
        return data.get("data", {}).get("user", {})

    async def get_all_users(self) -> list[FeishuUser]:
        """获取企业内所有用户（含邮箱、手机号）。

        遍历所有部门获取用户列表，去重后逐个获取详情（含邮箱）。
        """
        all_users_map: dict[str, dict] = {}

        departments = await self.get_all_departments()
        logger.info("获取到 %d 个部门", len(departments))

        dept_ids = ["0"] + [
            d.get("open_department_id", "") for d in departments
        ]
        for dept_id in dept_ids:
            if not dept_id:
                continue
            users = await self.get_department_users(dept_id)
            for u in users:
                oid = u.get("open_id", "")
                if oid and oid not in all_users_map:
                    all_users_map[oid] = u

        logger.info("去重后共 %d 个用户，开始获取详情", len(all_users_map))

        results: list[FeishuUser] = []
        for i, (oid, basic) in enumerate(all_users_map.items()):
            detail = await self.get_user_detail(oid)
            name = basic.get("name", "") or detail.get("name", "")
            email = detail.get("email", "") or basic.get("email", "")
            enterprise_email = detail.get("enterprise_email", "")
            mobile = detail.get("mobile", "") or basic.get("mobile", "")

            results.append(FeishuUser(
                open_id=oid,
                name=name,
                email=email or enterprise_email,
                enterprise_email=enterprise_email,
                mobile=mobile,
            ))

            if (i + 1) % 50 == 0:
                logger.info("获取用户详情进度: %d/%d", i + 1, len(all_users_map))

        logger.info("共获取 %d 个用户详情", len(results))
        return results

    async def send_card_message(
        self, open_id: str, card: dict
    ) -> str:
        """向指定用户发送互动卡片消息。

        Args:
            open_id: 接收用户的 open_id
            card: 卡片 JSON 结构（会自动序列化）

        Returns:
            消息 ID (message_id)
        """
        token = await self._ensure_token()
        payload = {
            "receive_id": open_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        }
        r = await self._client.post(
            f"{self._base_url}/open-apis/im/v1/messages",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            params={"receive_id_type": "open_id"},
            json=payload,
        )
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(
                f"发送卡片消息失败: code={data.get('code')}, "
                f"msg={data.get('msg')}"
            )
        msg_id = data.get("data", {}).get("message_id", "")
        logger.info("已发送卡片消息: open_id=%s, message_id=%s", open_id, msg_id)
        return msg_id
