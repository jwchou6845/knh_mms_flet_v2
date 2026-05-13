# =====================================================
# KNH MMS v2
# File: repositories/feed_repo.py
# File Revision: 2026-05-13-feed-active-material-filter-r1
# Status: current working version
# Last Updated: 2026-05-13 Asia/Taipei
#
# Purpose:
# - 現場打料作業 Supabase 查詢層。
#
# Major Changes in This Revision:
# - 確認 feed.py 新料 / 母粒下拉來源只讀取 is_active=true 且 is_stock_managed=true 的 material_stock_view。
# - get_active_materials() 也同步排除未納管原料，避免未來若被引用時邏輯不一致。
# - 保留回用料在庫查詢與近期打料紀錄查詢不變。
#
# Notes:
# - Flet 0.84 專案使用。
# - 本次不修改 views/feed.py UI、不修改 Supabase schema。
# =====================================================

from __future__ import annotations

from typing import Any

from db.supabase_client import supabase


TABLE_MATERIALS = "materials"
TABLE_RECYCLED_MATERIALS = "recycled_materials"
TABLE_FEED_RECORDS = "feed_records"
VIEW_MATERIAL_STOCK = "material_stock_view"


# ============================================================
# Material stock view
# ============================================================

def get_material_stock_rows() -> list[dict[str, Any]]:
    """
    讀取正式即時庫存 View。
    material_stock_view = 開帳/調整 + 進貨 - 打料。
    feed.py 的原料清單與低水位警示都應該以此為準。
    """
    res = (
        supabase.table(VIEW_MATERIAL_STOCK)
        .select("*")
        .eq("is_active", True)
        .eq("is_stock_managed", True)
        .order("material_name", desc=False)
        .execute()
    )

    return res.data or []


# ============================================================
# Materials
# ============================================================

def get_active_materials() -> list[dict[str, Any]]:
    """
    讀取啟用中的原料主檔。
    主要保留給寫入打料紀錄時補 supplier / bag_weight_kg 等欄位。
    """
    res = (
        supabase.table(TABLE_MATERIALS)
        .select("*")
        .eq("is_active", True)
        .eq("is_stock_managed", True)
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


# ============================================================
# Recycled Materials
# ============================================================

def get_available_recycled_materials() -> list[dict[str, Any]]:
    """
    讀取可領用的回用料。
    條件：
    - is_used = false
    - is_scrapped = false
    - usage_status 包含「在庫」
    """
    res = (
        supabase.table(TABLE_RECYCLED_MATERIALS)
        .select("*")
        .eq("is_used", False)
        .eq("is_scrapped", False)
        .ilike("usage_status", "%在庫%")
        .order("supplier", desc=False)
        .order("material_type", desc=False)
        .order("recycled_no", desc=False)
        .execute()
    )

    return res.data or []


def get_recycled_material_by_id(recycled_material_id: str) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_RECYCLED_MATERIALS)
        .select("*")
        .eq("id", recycled_material_id)
        .limit(1)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def mark_recycled_material_used(
    recycled_material_id: str,
    feed_record_id: str,
) -> dict[str, Any] | None:
    """
    回用料領用後，標記為已領用。
    Supabase 版直接更新狀態，不再依賴 Airtable formula 欄位。
    """
    res = (
        supabase.table(TABLE_RECYCLED_MATERIALS)
        .update(
            {
                "is_used": True,
                "usage_status": "已領用",
                "used_feed_record_id": feed_record_id,
            }
        )
        .eq("id", recycled_material_id)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


# ============================================================
# Feed Records
# ============================================================

def get_recent_feed_records(limit: int = 40) -> list[dict[str, Any]]:
    """
    讀取最近打料紀錄，排除軟刪除資料。
    """
    res = (
        supabase.table(TABLE_FEED_RECORDS)
        .select("*")
        .eq("is_deleted", False)
        .order("feed_at", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    return res.data or []


def create_feed_record(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    新增打料紀錄。
    feed_type:
    - new
    - aux
    - recycled
    """
    res = (
        supabase.table(TABLE_FEED_RECORDS)
        .insert(payload)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]
