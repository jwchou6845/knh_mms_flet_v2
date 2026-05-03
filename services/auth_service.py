from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from repositories.user_repo import (
    create_password_reset_request,
    get_user_by_employee_id,
    update_last_login,
    update_password_after_first_login,
    update_quick_shortcuts,
)


TAIPEI_TZ = ZoneInfo("Asia/Taipei")


@dataclass
class ServiceResult:
    ok: bool
    message: str = ""
    data: Any = None


def now_taipei_iso() -> str:
    return datetime.now(TAIPEI_TZ).isoformat()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def authenticate_user(employee_id: str, password: str) -> ServiceResult:
    employee_id = (employee_id or "").strip()
    password = (password or "").strip()

    if not employee_id:
        return ServiceResult(ok=False, message="請輸入員工編號。")

    if not password:
        return ServiceResult(ok=False, message="請輸入密碼。")

    try:
        user = get_user_by_employee_id(employee_id)

        if not user:
            return ServiceResult(ok=False, message="此員工編號尚未授權，請聯絡管理員。")

        if not user.get("is_active", False):
            return ServiceResult(ok=False, message="此帳號尚未啟用或已停用，請聯絡管理員。")

        stored_hash = str(user.get("password_hash") or "").strip()
        input_hash = hash_password(password)

        if not stored_hash or stored_hash != input_hash:
            return ServiceResult(ok=False, message="密碼錯誤，請重新輸入。")

        return ServiceResult(ok=True, message="登入成功。", data=user)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"登入失敗：{exc}")


def save_user_last_login(user_id: str) -> ServiceResult:
    if not user_id:
        return ServiceResult(ok=False, message="缺少使用者 ID。")

    try:
        updated = update_last_login(
            user_id=user_id,
            login_at=now_taipei_iso(),
        )
        return ServiceResult(ok=True, data=updated)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"更新最近登入時間失敗：{exc}")


def change_password_first_login(
    user_id: str,
    current_hash: str,
    new_password: str,
    confirm_password: str,
) -> ServiceResult:
    new_password = (new_password or "").strip()
    confirm_password = (confirm_password or "").strip()

    if len(new_password) < 6:
        return ServiceResult(ok=False, message="新密碼至少需要 6 碼。")

    if new_password != confirm_password:
        return ServiceResult(ok=False, message="兩次輸入的新密碼不一致。")

    new_hash = hash_password(new_password)

    if new_hash == current_hash:
        return ServiceResult(ok=False, message="新密碼不可與預設密碼相同。")

    try:
        updated = update_password_after_first_login(
            user_id=user_id,
            new_password_hash=new_hash,
            password_updated_at=now_taipei_iso(),
        )

        if not updated:
            return ServiceResult(ok=False, message="密碼修改失敗，Supabase 未回傳資料。")

        return ServiceResult(ok=True, message="密碼已修改完成。", data=updated)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"密碼修改失敗：{exc}")


def submit_password_reset_request(
    employee_id: str,
    name: str,
    contact: str,
    reason: str,
) -> ServiceResult:
    employee_id = (employee_id or "").strip()
    name = (name or "").strip()
    contact = (contact or "").strip()
    reason = (reason or "").strip()

    if not employee_id:
        return ServiceResult(ok=False, message="請填寫員工編號。")

    if not name:
        return ServiceResult(ok=False, message="請填寫員工姓名。")

    payload = {
        "employee_id": employee_id,
        "name": name,
        "contact": contact or None,
        "reason": reason or "忘記密碼，申請管理員協助重設。",
        "status": "待處理",
        "created_at": now_taipei_iso(),
    }

    try:
        created = create_password_reset_request(payload)

        if not created:
            return ServiceResult(ok=False, message="密碼重設申請送出失敗，Supabase 未回傳資料。")

        return ServiceResult(ok=True, message="密碼重設申請已送出，請等待管理員處理。", data=created)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"送出失敗：{exc}")


def update_user_shortcuts(user_id: str, shortcuts: list[str]) -> ServiceResult:
    if not user_id:
        return ServiceResult(ok=False, message="缺少使用者 ID。")

    if len(shortcuts) > 2:
        return ServiceResult(ok=False, message="自訂快捷功能最多只能選 2 個。")

    try:
        updated = update_quick_shortcuts(user_id, shortcuts)

        if not updated:
            return ServiceResult(ok=False, message="快捷功能更新失敗，Supabase 未回傳資料。")

        return ServiceResult(ok=True, message="快捷功能已更新。", data=updated)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"快捷功能更新失敗：{exc}")