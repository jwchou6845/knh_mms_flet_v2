# =====================================================
# KNH MMS v2
# File: services/auth_session_service.py
# File Revision: 2026-05-11-auth-restore-guard-r1
# Status: current working version
# Last Updated: 2026-05-11 Asia/Taipei
#
# Purpose:
# - 12 小時免重登 session 的建立、恢復、撤銷與清理
#
# Major Changes in This Revision:
# - 補上明確版本註記，確認 restore 流程以 session_token 精準查詢 user_sessions
# - 本輪 restore timeout / late result guard 實作於 main.py；本檔保留既有商業邏輯
#
# Notes:
# - 所有 session 時間均以 Asia/Taipei 處理
# - 前端只保存 session_token，不保存密碼或 password_hash
# =====================================================

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from repositories.user_repo import get_user_by_id
from repositories.user_session_repo import (
    create_user_session as repo_create_user_session,
    get_user_session_by_token,
    revoke_user_session as repo_revoke_user_session,
    update_user_session_last_seen,
)


TAIPEI_TZ = ZoneInfo("Asia/Taipei")
SESSION_HOURS = 12


@dataclass
class ServiceResult:
    ok: bool
    message: str = ""
    data: Any = None


def now_taipei() -> datetime:
    return datetime.now(TAIPEI_TZ)


def now_taipei_iso() -> str:
    return now_taipei().isoformat()


def parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None

    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TAIPEI_TZ)
        return parsed.astimezone(TAIPEI_TZ)
    except Exception:
        return None


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def create_persistent_session(
    user: dict[str, Any],
    user_agent: str = "",
    ip_address: str = "",
) -> ServiceResult:
    """
    建立 12 小時免重登 session。
    前端只保存 session_token；使用者資料與過期時間保存在 Supabase user_sessions。
    """
    try:
        user_id = str(user.get("id") or "").strip()
        employee_id = str(user.get("employee_id") or "").strip()
        user_name = str(user.get("name") or "").strip() or employee_id
        role = str(user.get("role") or "操作員").strip() or "操作員"

        if not user_id:
            return ServiceResult(ok=False, message="缺少使用者 ID，無法建立登入狀態。")

        if not employee_id:
            return ServiceResult(ok=False, message="缺少員工編號，無法建立登入狀態。")

        expires_at = now_taipei() + timedelta(hours=SESSION_HOURS)
        token = create_session_token()

        payload = {
            "user_id": user_id,
            "employee_id": employee_id,
            "user_name": user_name,
            "role": role,
            "session_token": token,
            "expires_at": expires_at.isoformat(),
            "revoked": False,
            "created_at": now_taipei_iso(),
            "last_seen_at": now_taipei_iso(),
            "user_agent": str(user_agent or "")[:500] or None,
            "ip_address": str(ip_address or "")[:80] or None,
        }

        created = repo_create_user_session(payload)
        if not created:
            return ServiceResult(ok=False, message="建立登入狀態失敗，Supabase 未回傳資料。")

        return ServiceResult(
            ok=True,
            message="登入狀態已建立。",
            data={
                "session_token": token,
                "expires_at": expires_at.isoformat(),
                "session": created,
            },
        )

    except Exception as exc:
        return ServiceResult(ok=False, message=f"建立登入狀態失敗：{exc}")


def restore_persistent_session(
    session_token: str,
    user_agent: str = "",
    ip_address: str = "",
) -> ServiceResult:
    """
    由 localStorage 取出的 session_token 還原登入狀態。
    """
    token = str(session_token or "").strip()
    if not token:
        return ServiceResult(ok=False, message="沒有登入 token。")

    try:
        session = get_user_session_by_token(token)
        if not session:
            return ServiceResult(ok=False, message="登入狀態不存在或已登出。")

        expires_at = parse_datetime(session.get("expires_at"))
        if not expires_at:
            repo_revoke_user_session(token)
            return ServiceResult(ok=False, message="登入狀態時間格式錯誤，已失效。")

        if expires_at <= now_taipei():
            repo_revoke_user_session(token)
            return ServiceResult(ok=False, message="登入狀態已超過 12 小時，請重新登入。")

        user_id = str(session.get("user_id") or "").strip()
        user = get_user_by_id(user_id)
        if not user:
            repo_revoke_user_session(token)
            return ServiceResult(ok=False, message="找不到使用者資料，請重新登入。")

        if not user.get("is_active", False):
            repo_revoke_user_session(token)
            return ServiceResult(ok=False, message="此帳號已停用，請聯絡管理員。")

        update_user_session_last_seen(token, now_taipei_iso())

        return ServiceResult(
            ok=True,
            message="登入狀態已還原。",
            data={
                "user": user,
                "session": session,
                "session_token": token,
                "expires_at": expires_at.isoformat(),
            },
        )

    except Exception as exc:
        return ServiceResult(ok=False, message=f"還原登入狀態失敗：{exc}")


def revoke_persistent_session(session_token: str) -> ServiceResult:
    token = str(session_token or "").strip()
    if not token:
        return ServiceResult(ok=True, message="沒有需要撤銷的登入狀態。")

    try:
        revoked = repo_revoke_user_session(token)
        return ServiceResult(ok=True, message="登入狀態已撤銷。", data=revoked)
    except Exception as exc:
        return ServiceResult(ok=False, message=f"撤銷登入狀態失敗：{exc}")
