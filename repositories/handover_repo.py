from __future__ import annotations

from typing import Any

from db.supabase_client import supabase


TABLE_USERS = "users"
TABLE_HANDOVER_RECORDS = "handover_records"
TABLE_HANDOVER_ITEMS = "handover_items"

ALLOWED_RECEIVER_ROLES = ["操作員", "組長/副組長", "超級管理員"]


# ============================================================
# Users
# ============================================================

def get_active_user_names() -> list[str]:
    """
    讀取可接班使用者清單。
    來源：public.users
    """
    res = (
        supabase.table(TABLE_USERS)
        .select("name,role,is_active")
        .eq("is_active", True)
        .in_("role", ALLOWED_RECEIVER_ROLES)
        .order("name", desc=False)
        .execute()
    )

    names: list[str] = []

    for row in res.data or []:
        name = str(row.get("name") or "").strip()
        if name and name not in names:
            names.append(name)

    return names


# ============================================================
# Handover records
# ============================================================

def create_handover_record(payload: dict[str, Any]) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_HANDOVER_RECORDS)
        .insert(payload)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def create_handover_item(payload: dict[str, Any]) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_HANDOVER_ITEMS)
        .insert(payload)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def create_handover_items(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not payloads:
        return []

    res = (
        supabase.table(TABLE_HANDOVER_ITEMS)
        .insert(payloads)
        .execute()
    )

    return res.data or []


# ============================================================
# Handover tasks
# ============================================================

def get_open_handover_items() -> list[dict[str, Any]]:
    """
    讀取尚未完成的異常 / 待辦。
    權限過濾交給 service 依目前使用者處理。
    """
    res = (
        supabase.table(TABLE_HANDOVER_ITEMS)
        .select(
            """
            *,
            handover_records (
                id,
                handover_date,
                shift,
                sender_name,
                receiver_name,
                status,
                created_at
            )
            """
        )
        .eq("is_deleted", False)
        .eq("is_completed", False)
        .in_("item_type", ["異常", "待辦"])
        .order("created_at", desc=True)
        .execute()
    )

    return res.data or []



def get_completed_handover_items(limit: int = 100) -> list[dict[str, Any]]:
    """
    讀取已完成的異常 / 待辦紀錄。
    權限過濾交給 service 依目前使用者處理。
    """
    res = (
        supabase.table(TABLE_HANDOVER_ITEMS)
        .select(
            """
            *,
            handover_records (
                id,
                handover_date,
                shift,
                sender_name,
                receiver_name,
                status,
                created_at
            )
            """
        )
        .eq("is_deleted", False)
        .eq("is_completed", True)
        .in_("item_type", ["異常", "待辦"])
        .order("completed_at", desc=True)
        .limit(limit)
        .execute()
    )

    return res.data or []


def get_completed_outgoing_handover_items(
    sender_name: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    首頁提示用：
    讀取「我交出的」且已完成的異常 / 待辦。
    """
    res = (
        supabase.table(TABLE_HANDOVER_ITEMS)
        .select(
            """
            *,
            handover_records!inner (
                id,
                handover_date,
                shift,
                sender_name,
                receiver_name,
                status,
                created_at
            )
            """
        )
        .eq("is_deleted", False)
        .eq("is_completed", True)
        .in_("item_type", ["異常", "待辦"])
        .eq("handover_records.sender_name", sender_name)
        .order("completed_at", desc=True)
        .limit(limit)
        .execute()
    )

    return res.data or []


def complete_handover_item(
    item_id: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_HANDOVER_ITEMS)
        .update(payload)
        .eq("id", item_id)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]
