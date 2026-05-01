"""批量注册编排流程：从飞书通讯录获取用户，批量创建 Gitea 账号。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from teamflow.access.feishu_contact import FeishuContactService
from teamflow.config.settings import FeishuConfig, GiteaConfig
from teamflow.git.gitea_service import GiteaService

logger = logging.getLogger(__name__)


class GiteaAdminRequiredError(Exception):
    """Gitea Token 缺少管理员权限。"""


def _derive_username(email: str) -> str:
    """从邮箱地址派生 Gitea 用户名（@ 前缀）。

    Gitea 用户名规则: 只允许字母、数字、下划线、连字符和点号。
    """
    local_part = email.split("@")[0] if "@" in email else email
    safe = re.sub(r"[^a-zA-Z0-9._\-]", "_", local_part)
    safe = re.sub(r"_+", "_", safe).strip("_.-")
    if not safe:
        safe = "user"
    return safe


def _strip_country_code(mobile: str) -> str:
    """去掉手机号的国际区号前缀（如 +86、+1 等）。"""
    return re.sub(r"^\+\d{1,4}", "", mobile)


def _derive_password(mobile: str) -> str:
    """从手机号派生初始密码（去掉区号后的纯数字）。"""
    return _strip_country_code(mobile)


def _build_gitea_account_card(
    *,
    name: str,
    username: str,
    password: str,
    gitea_base_url: str,
    org_name: str = "",
    added_to_org: bool = False,
) -> dict:
    """构建 Gitea 账号创建通知的飞书互动卡片。"""
    login_url = f"{gitea_base_url}/user/login"
    settings_url = f"{gitea_base_url}/user/settings/account"

    org_section = ""
    if added_to_org and org_name:
        org_section = (
            f"\n- **所属组织：**{org_name}"
        )

    body_md = (
        f"你好，**{name}**！\n\n"
        f"公司已为你自动创建 Gitea 代码仓库账号，详情如下：\n\n"
        f"---\n\n"
        f"📋 **账号信息**\n\n"
        f"- **用户名：**`{username}`\n\n"
        f"- **初始密码：**`{password}`\n\n"
        f"- **仓库地址：**[{gitea_base_url}]({gitea_base_url})"
        f"{org_section}\n\n"
        f"---\n\n"
        f"🔐 **安全提醒**\n\n"
        f"- 请尽快登录并修改初始密码\n"
        f"- 登录地址：[点击登录]({login_url})\n"
        f"- 修改密码：[账号设置]({settings_url})\n\n"
        f"---\n\n"
        f"💡 **使用指引**\n\n"
    )

    if added_to_org and org_name:
        body_md += (
            f"- 你已加入组织「{org_name}」，可查看组织下的所有仓库\n"
            f"- 如需创建新仓库，请联系管理员或在组织下新建\n"
        )
    else:
        body_md += (
            "- 加入项目群后，你将自动获得对应仓库的访问权限\n"
            "- 如需创建新仓库，请联系管理员\n"
        )

    elements = [
        {"tag": "markdown", "content": body_md},
    ]

    card = {
        "header": {
            "title": {
                "tag": "plain_text",
                "content": "🎉 Gitea 账号已创建",
            },
            "template": "turquoise",
        },
        "elements": elements,
    }
    return card


@dataclass
class RegistrationResult:
    username: str
    name: str
    email: str
    open_id: str = ""
    status: str = ""  # "created" | "skipped" | "error"
    message: str = ""
    notified: bool = False


async def batch_register(
    feishu_config: FeishuConfig,
    gitea_config: GiteaConfig,
    *,
    org_name: str = "",
    must_change_password: bool = False,
    send_notification: bool = True,
    add_to_org: bool = False,
) -> list[RegistrationResult]:
    """从飞书通讯录获取所有用户，批量注册 Gitea 账号。

    Args:
        feishu_config: 飞书配置
        gitea_config: Gitea 配置
        org_name: 组织名
        must_change_password: 是否强制首次登录修改密码
        send_notification: 是否通过飞书发送注册通知
        add_to_org: 是否将用户加入组织（默认 False，
            用户加入项目群时会自动加入对应项目 Team）

    Returns:
        注册结果列表
    """
    contact_svc = FeishuContactService(feishu_config)
    gitea_svc = GiteaService(gitea_config)

    try:
        logger.info("开始批量注册流程")

        # 0. 检查 Gitea 管理员权限
        has_admin = await gitea_svc.check_admin_access()
        if not has_admin:
            raise GiteaAdminRequiredError(
                "Gitea Token 缺少 write:admin 权限，无法创建用户。"
                "请在 Gitea 上重新生成 Token，勾选 write:admin scope。"
            )

        # 1. 获取飞书用户列表
        logger.info("正在获取飞书通讯录...")
        feishu_users = await contact_svc.get_all_users()
        logger.info("获取到 %d 个飞书用户", len(feishu_users))

        if not feishu_users:
            logger.warning("未获取到任何飞书用户，请检查通讯录权限")
            return []

        # 2. 过滤掉没有邮箱的用户
        valid_users = [u for u in feishu_users if u.email]
        skipped_no_email = len(feishu_users) - len(valid_users)
        if skipped_no_email > 0:
            logger.info("跳过 %d 个无邮箱用户", skipped_no_email)

        # 3. 批量注册
        results: list[RegistrationResult] = []
        username_counter: dict[str, int] = {}

        for i, user in enumerate(valid_users):
            username = _derive_username(user.email)

            # 处理用户名冲突：如果同名用户已处理过，追加数字后缀
            if username in username_counter:
                username_counter[username] += 1
                username = f"{username}_{username_counter[username]}"
            else:
                username_counter[username] = 0

            # 检查是否已存在
            existing = await gitea_svc.admin_search_user(username)
            if existing:
                results.append(RegistrationResult(
                    username=username,
                    name=user.name,
                    email=user.email,
                    status="skipped",
                    message=f"用户已存在 (id={existing.id})",
                ))
                logger.info(
                    "[%d/%d] 跳过 %s: 用户已存在",
                    i + 1, len(valid_users), username,
                )
                continue

            # 派生密码
            password = _derive_password(user.mobile) if user.mobile else ""
            if not password:
                results.append(RegistrationResult(
                    username=username,
                    name=user.name,
                    email=user.email,
                    status="error",
                    message="无手机号，无法生成初始密码",
                ))
                logger.warning(
                    "[%d/%d] 跳过 %s: 无手机号",
                    i + 1, len(valid_users), username,
                )
                continue

            # 创建用户
            try:
                created = await gitea_svc.admin_create_user(
                    username=username,
                    email=user.email,
                    password=password,
                    full_name=user.name,
                    must_change_password=must_change_password,
                    send_notification=False,
                )

                # 加入组织
                user_added_to_org = False
                if add_to_org and org_name:
                    try:
                        await gitea_svc.add_org_member(org_name, username)
                        user_added_to_org = True
                        logger.info(
                            "[%d/%d] 已将 %s 加入组织 %s",
                            i + 1, len(valid_users), username, org_name,
                        )
                    except Exception as exc:
                        logger.warning(
                            "将 %s 加入组织 %s 失败: %s",
                            username, org_name, exc,
                        )

                # 通过飞书发送注册通知
                notified = False
                if send_notification and user.open_id:
                    try:
                        card = _build_gitea_account_card(
                            name=user.name,
                            username=username,
                            password=password,
                            gitea_base_url=gitea_config.base_url,
                            org_name=org_name,
                            added_to_org=user_added_to_org,
                        )
                        await contact_svc.send_card_message(user.open_id, card)
                        notified = True
                        logger.info(
                            "[%d/%d] 已发送飞书通知给 %s",
                            i + 1, len(valid_users), username,
                        )
                    except Exception as exc:
                        logger.warning(
                            "发送飞书通知给 %s 失败: %s",
                            username, exc,
                        )

                results.append(RegistrationResult(
                    username=username,
                    name=user.name,
                    email=user.email,
                    open_id=user.open_id,
                    status="created",
                    message=f"已创建 (id={created.id})",
                    notified=notified,
                ))
                logger.info(
                    "[%d/%d] 已创建 %s (%s)",
                    i + 1, len(valid_users), username, user.email,
                )

            except Exception as exc:
                results.append(RegistrationResult(
                    username=username,
                    name=user.name,
                    email=user.email,
                    status="error",
                    message=str(exc),
                ))
                logger.error(
                    "[%d/%d] 创建 %s 失败: %s",
                    i + 1, len(valid_users), username, exc,
                )

        # 4. 汇总
        created = sum(1 for r in results if r.status == "created")
        notified = sum(1 for r in results if r.notified)
        skipped = sum(1 for r in results if r.status == "skipped")
        errors = sum(1 for r in results if r.status == "error")
        logger.info(
            "批量注册完成: 创建=%d, 已通知=%d, 跳过=%d, 失败=%d",
            created, notified, skipped, errors,
        )

        return results

    finally:
        await contact_svc.close()
        await gitea_svc.close()
