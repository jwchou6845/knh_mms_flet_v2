from __future__ import annotations

from typing import Any

from db.supabase_client import supabase


TABLE_DRYER_STATUS = "dryer_status"


TOWER_ORDER = {
    "S1-PET": 1,
    "S1-PA6": 2,
    "S2-PET": 3,
    "S2-PA6": 4,
}


def get_dryer_status_rows() -> list[dict[str, Any]]:
    res = (
        supabase.table(TABLE_DRYER_STATUS)
        .select("*")
        .execute()
    )

    rows = res.data or []

    rows.sort(
        key=lambda row: TOWER_ORDER.get(str(row.get("tower_code") or ""), 99)
    )

    return rows


def get_dryer_status_by_tower(tower_code: str) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_DRYER_STATUS)
        .select("*")
        .eq("tower_code", tower_code)
        .limit(1)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def update_dryer_status(
    tower_code: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_DRYER_STATUS)
        .update(payload)
        .eq("tower_code", tower_code)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]