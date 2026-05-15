# =====================================================
# KNH MMS v2
# File: repositories/admin_user_repo.py
# File Revision: 2026-05-15-admin-users-r1
# Status: phase 2B users and permissions repository
# Last Updated: 2026-05-15 Asia/Taipei
#
# Purpose:
# - /admin/users 使用者與權限管理資料存取層。
# - 集中讀取 users 與 user_sessions，並提供使用者角色、啟用狀態與權限欄位更新。
#
# Major Changes in This Revision:
# - 新增使用者清單查詢。
# - 新增單一使用者查詢。
# - 新增使用者基本權限更新。
# - 新增 user_sessions 讀取，用於顯示有效 Session 數量。
#
# Notes:
# - Flet 0.84；此檔不含 UI。
# - 不修改 auth_session_service.py。
# - 不提供密碼重設，不新增使用者，不直接清除 Session。
# - Supabase 查詢集中於 repository，view 不直接呼叫 Supabase。
# =====================================================

from __future__ import annotations

from typing import Any

from db.supabase_client import supabase


TABLE_USERS = "users"
TABLE_USER_SESSIONS = "user_sessions"


def _safe_execute(query, fallback: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    try:
        res = query.execute()
        return res.data or []
    except Exception as exc:
        print("admin_user_repo query failed:", repr(exc), flush=True)
        return fallback or []


def get_user_rows_for_admin() -> list[dict[str, Any]]:
    """
    讀取 users 主檔。
    注意：password_hash 仍會由 Supabase 回傳，但 service 層會移除，不交給 UI 使用。
    """
    query = (
        supabase.table(TABLE_USERS)
        .select("*")
        .order("role", desc=False)
        .order("employee_id", desc=False)
    )
    return _safe_execute(query)


def get_user_by_id_for_admin(user_id: str) -> dict[str, Any] | None:
    user_id = str(user_id or "").strip()
    if not user_id:
        return None

    try:
        res = (
            supabase.table(TABLE_USERS)
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        return res.data[0]
    except Exception as exc:
        print("admin_user_repo get_user_by_id_for_admin failed:", repr(exc), flush=True)
        return None


def update_user_for_admin(user_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    更新使用者角色、啟用狀態與權限欄位。
    本函式不更新 password_hash，不處理密碼重設。
    """
    user_id = str(user_id or "").strip()
    if not user_id:
        return None

    res = (
        supabase.table(TABLE_USERS)
        .update(payload)
        .eq("id", user_id)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def get_user_session_rows_for_admin(limit: int = 1000) -> list[dict[str, Any]]:
    """
    讀取 user_sessions 供 /admin/users 顯示有效登入數。
    此處只讀取，不 revoke、不清理，避免影響 12 小時免重登穩定流程。
    """
    query = (
        supabase.table(TABLE_USER_SESSIONS)
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    return _safe_execute(query)
