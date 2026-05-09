from __future__ import annotations

from typing import Any

from db.supabase_client import supabase


TABLE_NAME = "user_sessions"


def _first_row(response) -> dict[str, Any] | None:
    data = getattr(response, "data", None) or []
    return data[0] if data else None


def _rows(response) -> list[dict[str, Any]]:
    data = getattr(response, "data", None) or []
    return data if isinstance(data, list) else []


def create_user_session(payload: dict[str, Any]) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_NAME)
        .insert(payload)
        .execute()
    )
    return _first_row(res)


def get_user_session_by_token(session_token: str) -> dict[str, Any] | None:
    token = str(session_token or "").strip()
    if not token:
        return None

    res = (
        supabase.table(TABLE_NAME)
        .select("*")
        .eq("session_token", token)
        .eq("revoked", False)
        .limit(1)
        .execute()
    )
    return _first_row(res)


def update_user_session_last_seen(session_token: str, last_seen_at: str) -> dict[str, Any] | None:
    token = str(session_token or "").strip()
    if not token:
        return None

    res = (
        supabase.table(TABLE_NAME)
        .update({"last_seen_at": last_seen_at})
        .eq("session_token", token)
        .execute()
    )
    return _first_row(res)


def revoke_user_session(session_token: str) -> dict[str, Any] | None:
    token = str(session_token or "").strip()
    if not token:
        return None

    res = (
        supabase.table(TABLE_NAME)
        .update({"revoked": True})
        .eq("session_token", token)
        .execute()
    )
    return _first_row(res)


def cleanup_expired_user_sessions(
    now_iso: str,
    revoked_before_iso: str | None = None,
) -> dict[str, int]:
    """
    清理 user_sessions。

    - expires_at < now_iso：刪除已過期 session。
    - revoked = true 且 created_at < revoked_before_iso：刪除很舊的登出紀錄。

    這裡使用 delete，而不是只標記 revoked，目的是避免 user_sessions 長期累積。
    """
    result = {
        "expired_deleted_count": 0,
        "revoked_deleted_count": 0,
    }

    now_text = str(now_iso or "").strip()
    if now_text:
        expired_res = (
            supabase.table(TABLE_NAME)
            .delete()
            .lt("expires_at", now_text)
            .execute()
        )
        result["expired_deleted_count"] = len(_rows(expired_res))

    revoked_before_text = str(revoked_before_iso or "").strip()
    if revoked_before_text:
        revoked_res = (
            supabase.table(TABLE_NAME)
            .delete()
            .eq("revoked", True)
            .lt("created_at", revoked_before_text)
            .execute()
        )
        result["revoked_deleted_count"] = len(_rows(revoked_res))

    return result
