from __future__ import annotations

from typing import Any

from db.supabase_client import supabase


TABLE_SPINNERET_SETS = "spinneret_sets"


def get_spinneret_rows() -> list[dict[str, Any]]:
    res = (
        supabase.table(TABLE_SPINNERET_SETS)
        .select("*")
        .order("set_code", desc=False)
        .execute()
    )

    return res.data or []


def get_spinneret_row_by_id(row_id: str) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_SPINNERET_SETS)
        .select("*")
        .eq("id", row_id)
        .limit(1)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def update_spinneret_row(
    row_id: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_SPINNERET_SETS)
        .update(payload)
        .eq("id", row_id)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]
