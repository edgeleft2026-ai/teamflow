"""测试脚本：获取飞书公司所有用户及其邮箱。

使用方式：
    python scripts/test_feishu_contacts.py

需要确保：
1. config.yaml 中 feishu 配置正确
2. 飞书应用已开通以下权限：
   - 获取部门组织架构信息 (contact:department.base:read)
   - 以应用身份读取通讯录 (contact:user.employee_id:read)
   - 获取用户邮箱信息 (contact:user.email:read)
   - 获取用户基本信息 (contact:user.base:read)
3. 飞书应用的通讯录权限范围设置为"全部员工"
   （管理后台 > 工作台 > 应用管理 > 应用详情 > 通讯录权限范围）
"""

from __future__ import annotations

import asyncio
import json
import os

import httpx

from teamflow.config import load_config


async def get_tenant_token(base_url: str, app_id: str, app_secret: str) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_token 失败: {data}")
        return data["tenant_access_token"]


async def check_scopes(client: httpx.AsyncClient, base_url: str, token: str) -> dict:
    r = await client.get(
        f"{base_url}/open-apis/contact/v3/scopes",
        headers={"Authorization": f"Bearer {token}"},
        params={"page_size": 100, "user_id_type": "open_id"},
    )
    return r.json()


async def get_all_departments(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
) -> list[dict]:
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
        r = await client.get(
            f"{base_url}/open-apis/contact/v3/departments",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        data = r.json()
        if data.get("code") != 0:
            print(f"  [WARN] 获取部门列表失败: {data.get('msg')} (code={data.get('code')})")
            break
        items = data.get("data", {}).get("items", [])
        departments.extend(items)
        if data.get("data", {}).get("has_more"):
            page_token = data["data"]["page_token"]
        else:
            break
    return departments


async def get_department_users(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    department_id: str = "0",
    page_size: int = 100,
) -> list[dict]:
    users = []
    page_token = ""
    while True:
        params = {
            "department_id": department_id,
            "department_id_type": "open_department_id",
            "page_size": page_size,
            "user_id_type": "open_id",
        }
        if page_token:
            params["page_token"] = page_token
        r = await client.get(
            f"{base_url}/open-apis/contact/v3/users",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        data = r.json()
        if data.get("code") != 0:
            print(f"  [WARN] 获取部门用户失败 (dept={department_id}): {data.get('msg')} (code={data.get('code')})")
            break
        items = data.get("data", {}).get("items", [])
        users.extend(items)
        if data.get("data", {}).get("has_more"):
            page_token = data["data"]["page_token"]
        else:
            break
    return users


async def get_users_no_dept(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    page_size: int = 100,
) -> list[dict]:
    users = []
    page_token = ""
    while True:
        params = {
            "page_size": page_size,
            "user_id_type": "open_id",
        }
        if page_token:
            params["page_token"] = page_token
        r = await client.get(
            f"{base_url}/open-apis/contact/v3/users",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        data = r.json()
        if data.get("code") != 0:
            print(f"  [WARN] 获取用户列表失败: {data.get('msg')} (code={data.get('code')})")
            break
        items = data.get("data", {}).get("items", [])
        users.extend(items)
        if data.get("data", {}).get("has_more"):
            page_token = data["data"]["page_token"]
        else:
            break
    return users


async def get_user_detail(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    open_id: str,
) -> dict:
    r = await client.get(
        f"{base_url}/open-apis/contact/v3/users/{open_id}",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "user_id_type": "open_id",
            "fields": "open_id,union_id,user_id,name,en_name,email,mobile,enterprise_email,employee_no,employee_type,department_ids,job_title,status",
        },
    )
    data = r.json()
    if data.get("code") != 0:
        return {}
    return data.get("data", {}).get("user", {})


async def main():
    config = load_config()
    feishu = config.feishu

    base_url = (
        "https://open.feishu.cn"
        if feishu.brand == "feishu"
        else "https://open.larksuite.com"
    )

    print("=" * 60)
    print("飞书通讯录测试脚本")
    print("=" * 60)
    print(f"App ID: {feishu.app_id[:8]}...")
    print(f"Brand:  {feishu.brand}")
    print()

    # Step 1: 获取 tenant_access_token
    print("[1/5] 获取 tenant_access_token...")
    token = await get_tenant_token(base_url, feishu.app_id, feishu.app_secret)
    print(f"  Token: {token[:16]}...")
    print()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 2: 检查通讯录权限范围
        print("[2/5] 检查通讯录权限范围...")
        scope_info = await check_scopes(client, base_url, token)
        if scope_info.get("code") == 0:
            scope_data = scope_info.get("data", {})
            dept_ids = scope_data.get("department_ids", [])
            user_ids = scope_data.get("user_ids", [])
            group_ids = scope_data.get("group_ids", [])
            print(f"  授权部门数: {len(dept_ids)}")
            print(f"  授权用户数: {len(user_ids)}")
            print(f"  授权用户组数: {len(group_ids)}")
            if dept_ids:
                print(f"  部门 IDs (前5): {dept_ids[:5]}")
        else:
            print(f"  [WARN] 无法获取权限范围: {scope_info.get('msg')}")
        print()

        # Step 3: 获取所有部门
        print("[3/5] 获取部门列表...")
        all_departments = await get_all_departments(client, base_url, token)
        print(f"  共获取到 {len(all_departments)} 个部门")
        for dept in all_departments[:10]:
            print(f"    - {dept.get('name', '?')} (id={dept.get('open_department_id', '?')})")
        if len(all_departments) > 10:
            print(f"    ... 还有 {len(all_departments) - 10} 个")
        print()

        # Step 4: 获取用户
        print("[4/5] 获取用户列表...")
        all_users_map: dict[str, dict] = {}

        # 方式1: 不带 department_id，获取权限范围内的独立用户
        print("  方式1: 获取权限范围内的独立用户...")
        independent_users = await get_users_no_dept(client, base_url, token)
        for u in independent_users:
            oid = u.get("open_id", "")
            if oid and oid not in all_users_map:
                all_users_map[oid] = u
        print(f"    独立用户: {len(independent_users)} 人")

        # 方式2: 按部门遍历
        print("  方式2: 按部门遍历用户...")
        dept_ids_to_query = ["0"] + [d.get("open_department_id", "") for d in all_departments]
        for dept_id in dept_ids_to_query:
            if not dept_id:
                continue
            users = await get_department_users(client, base_url, token, department_id=dept_id)
            new_count = 0
            for u in users:
                oid = u.get("open_id", "")
                if oid and oid not in all_users_map:
                    all_users_map[oid] = u
                    new_count += 1
            if new_count > 0:
                dept_name = "?"
                for d in all_departments:
                    if d.get("open_department_id") == dept_id:
                        dept_name = d.get("name", "?")
                        break
                if dept_id == "0":
                    dept_name = "根部门"
                print(f"    部门 [{dept_name}]: 新增 {new_count} 人")

        print(f"  共获取到 {len(all_users_map)} 个不重复用户")
        print()

        # Step 5: 获取每个用户的邮箱
        print("[5/5] 获取用户邮箱详情...")
        results = []
        users_with_email = 0
        users_without_email = 0

        # 先打印列表接口返回的原始字段，方便排查
        print("  --- 列表接口原始字段样例 ---")
        for i, (oid, basic) in enumerate(list(all_users_map.items())[:3]):
            print(f"    用户 {i+1}: {basic.get('name', '?')}")
            print(f"      open_id: {oid}")
            print(f"      email (列表): {basic.get('email', '<无>')}")
            print(f"      mobile (列表): {basic.get('mobile', '<无>')}")
            print(f"      enterprise_email (列表): {basic.get('enterprise_email', '<无>')}")
            print(f"      keys: {list(basic.keys())}")
        print()

        open_ids = list(all_users_map.keys())
        for i, oid in enumerate(open_ids):
            basic = all_users_map[oid]
            name = basic.get("name", "(未知)")

            detail = await get_user_detail(client, base_url, token, oid)

            # 打印详情接口返回的原始字段
            if i < 3:
                print(f"    详情接口 [{name}] keys: {list(detail.keys())}")
                if detail:
                    print(f"      email (详情): {detail.get('email', '<无>')}")
                    print(f"      enterprise_email (详情): {detail.get('enterprise_email', '<无>')}")
                    print(f"      mobile (详情): {detail.get('mobile', '<无>')}")

            email = detail.get("email", "") or basic.get("email", "")
            enterprise_email = detail.get("enterprise_email", "")
            mobile = detail.get("mobile", "") or basic.get("mobile", "")

            final_email = email or enterprise_email
            if final_email:
                users_with_email += 1
            else:
                users_without_email += 1

            results.append({
                "open_id": oid,
                "name": name,
                "email": final_email,
                "enterprise_email": enterprise_email,
                "mobile": mobile,
            })

            if (i + 1) % 20 == 0 or i == len(open_ids) - 1:
                print(f"  进度: {i + 1}/{len(open_ids)}")

        print()
        print("=" * 60)
        print(f"统计结果:")
        print(f"  总用户数: {len(results)}")
        print(f"  有邮箱:   {users_with_email}")
        print(f"  无邮箱:   {users_without_email}")
        print("=" * 60)

        # 输出结果到文件
        output_path = "tmp/feishu_contacts.json"
        os.makedirs("tmp", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {output_path}")

        # 同时保存原始数据用于进一步分析
        raw_path = "tmp/feishu_contacts_raw.json"
        raw_data = {
            "users_map": all_users_map,
            "departments": all_departments,
            "scope_info": scope_info,
        }
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=2)
        print(f"原始数据已保存到: {raw_path}")

        # 打印前 30 条
        print("\n数据预览:")
        print("-" * 70)
        print(f"{'姓名':<12} {'邮箱':<35} {'手机号':<15}")
        print("-" * 70)
        for r in results[:30]:
            print(f"{r['name']:<12} {r['email']:<35} {r['mobile']:<15}")
        if len(results) > 30:
            print(f"... 还有 {len(results) - 30} 条")


if __name__ == "__main__":
    asyncio.run(main())
