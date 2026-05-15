# =====================================================
# KNH MMS v2
# File: services/admin_user_service.py
# File Revision: 2026-05-15-admin-users-r1
# Status: phase 2B users and permissions service
# Last Updated: 2026-05-15 Asia/Taipei
#
# Purpose:
# - /admin/users 使用者與權限管理服務層。
# - 整理 users 與 user_sessions 資料，提供角色、啟用狀態與權限更新。
#
# Major Changes in This Revision:
# - 新增 load_admin_users_page_data()。
# - 新增 update_admin_user_from_form()。
# - 使用 Asia/Taipei 格式化 last_login_at / updated_at。
# - 加入防呆：不可停用自己、不可把自己降權、不可移除最後一位啟用的超級管理員。
#
# Notes:
# - 所有時間處理使用 Asia/Taipei。
# - 不修改 auth_session_service.py。
# - 不提供密碼重設、不新增使用者、不直接 revoke Session。
# - 第一版維持角色制，不建立細項 permission table。
# =====================================================

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from repositories.admin_user_repo import (
    get_user_by_id_for_admin,
    get_user_rows_for_admin,
    get_user_session_rows_for_admin,
    update_user_for_admin,
)


TAIPEI_TZ = ZoneInfo("Asia/Taipei")

ALLOWED_ROLES = ["超級管理員", "部門主管", "組長/副組長", "操作員", "部門外成員"]

PERMISSION_FIELDS = [
    "can_view_all_tasks",
    "can_access_reports",
    "can_access_spinneret",
    "can_access_maintenance",
]


@dataclass
class ServiceResult:
    ok: bool
    message: str = ""
    data: Any = None


def now_taipei() -> datetime:
    return datetime.now(TAIPEI_TZ)


def now_taipei_iso() -> str:
    return now_taipei().isoformat()


def clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def normalize_text(value: Any) -> str:
    text = clean_text(value).replace("　", " ")
    return " ".join(text.split()).casefold()


def to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default

    text = str(value).strip().lower()
    if text in ["true", "1", "yes", "y", "是", "啟用", "可用", "active"]:
        return True
    if text in ["false", "0", "no", "n", "否", "停用", "inactive"]:
        return False
    return default


def parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None

    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TAIPEI_TZ)
        return dt.astimezone(TAIPEI_TZ)
    except Exception:
        return None


def format_datetime_taipei(value: Any) -> str:
    dt = parse_datetime(value)
    if not dt:
        return "-"
    return dt.strftime("%Y/%m/%d %H:%M")


def is_session_active(row: dict[str, Any]) -> bool:
    """
    支援既有 user_sessions schema：
    - revoked boolean
    - revoked_at timestamp
    - expires_at timestamptz
    """
    if to_bool(row.get("revoked"), False):
        return False

    if row.get("revoked_at") not in [None, ""]:
        return False

    expires_at = parse_datetime(row.get("expires_at"))
    if expires_at and expires_at <= now_taipei():
        return False

    if "expires_at" not in row:
        return False

    return True


def _active_session_count_map(session_rows: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in session_rows:
        if not is_session_active(row):
            continue

        user_id = clean_text(row.get("user_id") or row.get("user_record_id"))
        if not user_id:
            continue

        result[user_id] = result.get(user_id, 0) + 1

    return result


def normalize_user_row(row: dict[str, Any], active_session_map: dict[str, int]) -> dict[str, Any]:
    user_id = clean_text(row.get("id"))
    active = to_bool(row.get("is_active"), True)
    first_login = to_bool(row.get("is_first_login"), False)
    must_change = to_bool(row.get("must_change_password"), False)
    role = clean_text(row.get("role"), "操作員")

    return {
        "id": user_id,
        "employee_id": clean_text(row.get("employee_id"), "-"),
        "name": clean_text(row.get("name"), "-"),
        "role": role,
        "shift": clean_text(row.get("shift"), "-"),
        "is_active": active,
        "active_label": "啟用" if active else "停用",
        "is_first_login": first_login,
        "must_change_password": must_change,
        "password_state_label": "需改密碼" if (first_login or must_change) else "已完成",
        "can_view_all_tasks": to_bool(row.get("can_view_all_tasks"), False),
        "can_access_reports": to_bool(row.get("can_access_reports"), False),
        "can_access_spinneret": to_bool(row.get("can_access_spinneret"), False),
        "can_access_maintenance": to_bool(row.get("can_access_maintenance"), False),
        "quick_shortcuts": row.get("quick_shortcuts") or [],
        "last_login_at": row.get("last_login_at"),
        "last_login_at_label": format_datetime_taipei(row.get("last_login_at")),
        "password_updated_at_label": format_datetime_taipei(row.get("password_updated_at")),
        "created_at_label": format_datetime_taipei(row.get("created_at")),
        "updated_at_label": format_datetime_taipei(row.get("updated_at")),
        "active_session_count": active_session_map.get(user_id, 0),
        "note": clean_text(row.get("note"), ""),
    }


def build_user_summary(users: list[dict[str, Any]], active_session_total: int) -> dict[str, Any]:
    active_users = [row for row in users if row.get("is_active")]
    inactive_users = [row for row in users if not row.get("is_active")]
    active_admins = [
        row for row in users
        if row.get("is_active") and row.get("role") == "超級管理員"
    ]
    must_change_users = [
        row for row in users
        if row.get("is_first_login") or row.get("must_change_password")
    ]

    role_counts: dict[str, int] = {}
    for row in users:
        role = clean_text(row.get("role"), "操作員")
        role_counts[role] = role_counts.get(role, 0) + 1

    return {
        "total_user_count": len(users),
        "active_user_count": len(active_users),
        "inactive_user_count": len(inactive_users),
        "active_super_admin_count": len(active_admins),
        "must_change_password_count": len(must_change_users),
        "active_session_count": active_session_total,
        "role_counts": role_counts,
    }


def load_admin_users_page_data() -> ServiceResult:
    try:
        user_rows = get_user_rows_for_admin()
        session_rows = get_user_session_rows_for_admin(limit=1000)
        active_session_map = _active_session_count_map(session_rows)

        users = [
            normalize_user_row(row, active_session_map)
            for row in user_rows
        ]

        users.sort(
            key=lambda row: (
                0 if row.get("role") == "超級管理員" else 1,
                row.get("role") or "",
                row.get("employee_id") or "",
            )
        )

        summary = build_user_summary(
            users,
            active_session_total=sum(active_session_map.values()),
        )

        return ServiceResult(
            ok=True,
            data={
                "users": users,
                "summary": summary,
                "allowed_roles": ALLOWED_ROLES,
                "generated_at": now_taipei().strftime("%Y/%m/%d %H:%M"),
            },
        )

    except Exception as exc:
        return ServiceResult(
            ok=False,
            message=f"讀取使用者與權限資料失敗：{exc}",
            data={
                "users": [],
                "summary": {
                    "total_user_count": 0,
                    "active_user_count": 0,
                    "inactive_user_count": 0,
                    "active_super_admin_count": 0,
                    "must_change_password_count": 0,
                    "active_session_count": 0,
                    "role_counts": {},
                },
                "allowed_roles": ALLOWED_ROLES,
                "generated_at": now_taipei().strftime("%Y/%m/%d %H:%M"),
            },
        )


def _active_super_admin_count(raw_users: list[dict[str, Any]]) -> int:
    return len([
        row for row in raw_users
        if to_bool(row.get("is_active"), True)
        and clean_text(row.get("role")) == "超級管理員"
    ])


def update_admin_user_from_form(
    user_id: str,
    form_data: dict[str, Any],
    current_user_id: str | None,
    current_user_role: str | None,
) -> ServiceResult:
    if clean_text(current_user_role) != "超級管理員":
        return ServiceResult(ok=False, message="只有超級管理員可以修改使用者權限。")

    user_id = clean_text(user_id)
    current_user_id = clean_text(current_user_id)

    if not user_id:
        return ServiceResult(ok=False, message="缺少使用者 ID。")

    role = clean_text(form_data.get("role"), "操作員")
    if role not in ALLOWED_ROLES:
        return ServiceResult(ok=False, message="角色不在允許清單內。")

    is_active = to_bool(form_data.get("is_active"), True)

    try:
        original = get_user_by_id_for_admin(user_id)
        if not original:
            return ServiceResult(ok=False, message="找不到此使用者。")

        original_role = clean_text(original.get("role"))
        original_active = to_bool(original.get("is_active"), True)

        if current_user_id and user_id == current_user_id:
            if not is_active:
                return ServiceResult(ok=False, message="不能停用目前登入中的自己。")
            if role != "超級管理員":
                return ServiceResult(ok=False, message="不能把目前登入中的自己降為非超級管理員。")

        raw_users = get_user_rows_for_admin()
        active_admin_count = _active_super_admin_count(raw_users)

        removing_last_admin = (
            original_role == "超級管理員"
            and original_active
            and active_admin_count <= 1
            and (role != "超級管理員" or not is_active)
        )
        if removing_last_admin:
            return ServiceResult(ok=False, message="系統至少需要保留一位啟用中的超級管理員。")

        payload: dict[str, Any] = {
            "role": role,
            "is_active": is_active,
            "can_view_all_tasks": to_bool(form_data.get("can_view_all_tasks"), False),
            "can_access_reports": to_bool(form_data.get("can_access_reports"), False),
            "can_access_spinneret": to_bool(form_data.get("can_access_spinneret"), False),
            "can_access_maintenance": to_bool(form_data.get("can_access_maintenance"), False),
            "updated_at": now_taipei_iso(),
        }

        updated = update_user_for_admin(user_id, payload)
        if not updated:
            return ServiceResult(ok=False, message="更新使用者資料失敗，Supabase 未回傳資料。")

        return ServiceResult(
            ok=True,
            message="使用者權限已更新。",
            data=normalize_user_row(updated, active_session_map={}),
        )

    except Exception as exc:
        return ServiceResult(ok=False, message=f"更新使用者權限失敗：{exc}")
