from __future__ import annotations

from typing import Any

from db.supabase_client import supabase


TABLE_MATERIALS = "materials"
TABLE_PURCHASE_RECORDS = "purchase_records"
TABLE_RECYCLED_MATERIALS = "recycled_materials"
VIEW_MATERIAL_STOCK = "material_stock_view"


# ============================================================
# Materials
# ============================================================

def get_active_materials() -> list[dict[str, Any]]:
    """
    讀取啟用中的原料主檔。
    用於 inventory.py 的「關聯原料」下拉選單。
    """
    res = (
        supabase.table(TABLE_MATERIALS)
        .select("*")
        .eq("is_active", True)
        .order("material_name", desc=False)
        .execute()
    )

    return res.data or []


def get_material_by_id(material_id: str) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_MATERIALS)
        .select("*")
        .eq("id", material_id)
        .limit(1)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def get_material_stock_view() -> list[dict[str, Any]]:
    """
    讀取正式即時庫存 view。
    後續 dashboard / inventory / feed 都應該共用這個 view。
    """
    res = (
        supabase.table(VIEW_MATERIAL_STOCK)
        .select("*")
        .eq("is_active", True)
        .order("material_name", desc=False)
        .execute()
    )

    return res.data or []


# ============================================================
# Purchase Records
# ============================================================

def purchase_batch_exists(batch_no: str) -> bool:
    """
    檢查供應商新料入庫批號是否已存在。
    排除軟刪除紀錄。
    """
    res = (
        supabase.table(TABLE_PURCHASE_RECORDS)
        .select("id")
        .eq("purchase_batch_no", batch_no)
        .eq("is_deleted", False)
        .limit(1)
        .execute()
    )

    return bool(res.data)


def create_purchase_record(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    新增進貨紀錄。
    """
    res = (
        supabase.table(TABLE_PURCHASE_RECORDS)
        .insert(payload)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def get_recent_purchase_records(limit: int = 10) -> list[dict[str, Any]]:
    """
    最近進貨紀錄。
    """
    res = (
        supabase.table(TABLE_PURCHASE_RECORDS)
        .select("*")
        .eq("is_deleted", False)
        .order("purchase_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    return res.data or []


# ============================================================
# Recycled Materials
# ============================================================

def recycled_no_exists(recycled_no: str) -> bool:
    """
    檢查回用料編號是否已存在。
    """
    res = (
        supabase.table(TABLE_RECYCLED_MATERIALS)
        .select("id")
        .eq("recycled_no", recycled_no)
        .limit(1)
        .execute()
    )

    return bool(res.data)


def create_recycled_material(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    新增回用料入庫紀錄。
    """
    res = (
        supabase.table(TABLE_RECYCLED_MATERIALS)
        .insert(payload)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def get_recent_recycled_materials(limit: int = 10) -> list[dict[str, Any]]:
    """
    最近回用料入庫紀錄。
    """
    res = (
        supabase.table(TABLE_RECYCLED_MATERIALS)
        .select("*")
        .order("inbound_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    return res.data or []