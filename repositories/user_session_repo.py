from __future__ import annotations

from typing import Any

from db.supabase_client import supabase


TABLE_USER_SESSIONS = "user_sessions"


def create_user_session(payload: dict[str, Any]) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_USER_SESSIONS)
        .insert(payload)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def get_user_session_by_token(session_token: str) -> dict[str, Any] | None:
    token = str(session_token or "").strip()
    if not token:
        return None

    res = (
        supabase.table(TABLE_USER_SESSIONS)
        .select("*")
        .eq("session_token", token)
        .eq("revoked", False)
        .limit(1)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def update_user_session_last_seen(session_token: str, last_seen_at: str) -> dict[str, Any] | None:
    token = str(session_token or "").strip()
    if not token:
        return None

    res = (
        supabase.table(TABLE_USER_SESSIONS)
        .update({"last_seen_at": last_seen_at})
        .eq("session_token", token)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def revoke_user_session(session_token: str) -> dict[str, Any] | None:
    token = str(session_token or "").strip()
    if not token:
        return None

    res = (
        supabase.table(TABLE_USER_SESSIONS)
        .update({"revoked": True})
        .eq("session_token", token)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def revoke_user_sessions_by_user_id(user_id: str) -> list[dict[str, Any]]:
    uid = str(user_id or "").strip()
    if not uid:
        return []

    res = (
        supabase.table(TABLE_USER_SESSIONS)
        .update({"revoked": True})
        .eq("user_id", uid)
        .eq("revoked", False)
        .execute()
    )

    return res.data or []
