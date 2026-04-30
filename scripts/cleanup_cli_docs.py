"""交互式删除当前 bot 创建的飞书云文档。

用法:
  python scripts/cleanup_cli_docs.py

交互方式:
  - 上下方向键移动光标
  - 空格切换选中
  - A 全选
  - N 清空
  - Enter 确认删除
  - Q 退出
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

PAGE_SIZE = 12


@dataclass
class DocEntry:
    token: str
    title: str
    url: str
    owner_id: str
    parent_token: str
    modified_time: int


def info(text: str) -> None:
    print(f"[..] {text}")


def ok(text: str) -> None:
    print(f"[OK] {text}")


def fail(text: str) -> None:
    print(f"[FAIL] {text}")


def _build_client(feishu):
    import lark_oapi as lark

    base_url = (
        "https://open.feishu.cn" if feishu.brand == "feishu" else "https://open.larksuite.com"
    )
    return (
        lark.Client.builder()
        .app_id(feishu.app_id)
        .app_secret(feishu.app_secret)
        .domain(base_url)
        .log_level(lark.LogLevel.WARNING)
        .build()
    )


def _load_config():
    from teamflow.config import load_config

    config = load_config()
    if not config.feishu.app_id or not config.feishu.app_secret:
        raise RuntimeError("飞书配置不完整，请先运行 teamflow setup")
    return config.feishu


def _get_bot_open_id(feishu) -> str:
    from teamflow.execution.cli import _exchange_tenant_token

    token = _exchange_tenant_token(feishu)
    base_url = (
        "https://open.feishu.cn" if feishu.brand == "feishu" else "https://open.larksuite.com"
    )
    req = Request(
        f"{base_url}/open-apis/bot/v3/info",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    bot = payload.get("bot") or payload.get("data", {}).get("bot") or {}
    open_id = bot.get("open_id") or bot.get("bot_open_id")
    if not open_id:
        raise RuntimeError("bot/v3/info 未返回 open_id，无法识别 bot 创建的文档")
    return open_id


def _list_bot_created_docs(client, bot_open_id: str) -> list[DocEntry]:
    import lark_oapi as lark

    matched: list[DocEntry] = []
    pending_folders = [""]
    visited_folders = {""}

    while pending_folders:
        folder_token = pending_folders.pop(0)
        page_token = ""

        while True:
            builder = (
                lark.drive.v1.ListFileRequest.builder()
                .page_size(200)
                .order_by("EditedTime")
                .direction("DESC")
            )
            if folder_token:
                builder = builder.folder_token(folder_token)
            if page_token:
                builder = builder.page_token(page_token)

            req = builder.build()
            resp = client.drive.v1.file.list(req)
            if not resp.success():
                raise RuntimeError(f"列出文档失败: {resp.msg} ({resp.code})")

            data = resp.data
            files = data.files if data and data.files else []
            for file in files:
                if not file.token:
                    continue

                if file.type == "folder":
                    if file.token not in visited_folders:
                        visited_folders.add(file.token)
                        pending_folders.append(file.token)
                    continue

                if file.type != "docx":
                    continue
                if file.owner_id != bot_open_id:
                    continue

                matched.append(
                    DocEntry(
                        token=file.token,
                        title=file.name or "(未命名文档)",
                        url=file.url or "",
                        owner_id=file.owner_id or "",
                        parent_token=file.parent_token or "",
                        modified_time=file.modified_time or 0,
                    )
                )

            if not data or not data.has_more or not data.next_page_token:
                break
            page_token = data.next_page_token

    matched.sort(key=lambda item: item.modified_time, reverse=True)
    return matched


def _render_entries(entries: list[DocEntry], selected: set[int], cursor: int, start: int) -> None:
    os.system("cls")
    print("当前 bot 创建的文档")
    print("操作: ↑/↓ 移动  Space 选中  A 全选  N 清空  Enter 删除  Q 退出")
    print(f"文档总数: {len(entries)}  已选: {len(selected)}")
    print("-" * 100)

    end = min(start + PAGE_SIZE, len(entries))
    for idx in range(start, end):
        entry = entries[idx]
        pointer = ">" if idx == cursor else " "
        mark = "[x]" if idx in selected else "[ ]"
        title = entry.title[:64]
        token = entry.token[:16]
        print(f"{pointer} {mark} {idx + 1:>3}. {title:<64} {token}")

    print("-" * 100)
    if entries:
        current = entries[cursor]
        print(f"当前文档: {current.title}")
        print(f"链接: {current.url or '—'}")
        print(f"token: {current.token}")


def _select_docs(entries: list[DocEntry]) -> list[DocEntry]:
    import msvcrt

    if not entries:
        return []

    cursor = 0
    start = 0
    selected: set[int] = set()

    while True:
        _render_entries(entries, selected, cursor, start)
        key = msvcrt.getwch()

        if key in ("\r", "\n"):
            return [entries[index] for index in sorted(selected)]
        if key == " ":
            if cursor in selected:
                selected.remove(cursor)
            else:
                selected.add(cursor)
        elif key.lower() == "a":
            selected = set(range(len(entries)))
        elif key.lower() == "n":
            selected.clear()
        elif key.lower() == "q":
            return []
        elif key in ("\x00", "\xe0"):
            special = msvcrt.getwch()
            if special == "H" and cursor > 0:
                cursor -= 1
            elif special == "P" and cursor < len(entries) - 1:
                cursor += 1

        if cursor < start:
            start = cursor
        elif cursor >= start + PAGE_SIZE:
            start = cursor - PAGE_SIZE + 1


def _delete_doc(client, token: str) -> None:
    import lark_oapi as lark

    req = lark.drive.v1.DeleteFileRequest.builder().file_token(token).type("docx").build()
    resp = client.drive.v1.file.delete(req)
    if not resp.success():
        raise RuntimeError(f"{resp.msg} ({resp.code})")


def main() -> None:
    feishu = _load_config()
    client = _build_client(feishu)
    bot_open_id = _get_bot_open_id(feishu)
    info(f"bot_open_id: {bot_open_id}")

    matches = _list_bot_created_docs(client, bot_open_id)
    info(f"bot 创建的文档数: {len(matches)}")
    if not matches:
        ok("没有找到当前 bot 创建的文档")
        return

    selected_docs = _select_docs(matches)
    os.system("cls")
    if not selected_docs:
        info("未选择任何文档，已取消删除")
        return

    info(f"准备删除 {len(selected_docs)} 个文档")
    for entry in selected_docs:
        print(f"- {entry.title}")

    deleted = 0
    failed = 0

    for entry in selected_docs:
        try:
            _delete_doc(client, entry.token)
            deleted += 1
            ok(f"已删除: {entry.title}")
        except Exception as exc:
            failed += 1
            fail(f"删除失败: {entry.title} | {exc}")

    print("\n结果汇总")
    print(f"- 删除成功: {deleted}")
    print(f"- 删除失败: {failed}")


if __name__ == "__main__":
    main()
