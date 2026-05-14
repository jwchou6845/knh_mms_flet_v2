# =====================================================
# KNH MMS v2
# File: repositories/stocktake_repo.py
# File Revision: 2026-05-14-stocktake-recycled-r2
# Status: recycled item stocktake repository update
# Last Updated: 2026-05-13 Asia/Taipei
#
# Purpose:
# - 人工盤點功能 Supabase 查詢層。
# - 負責 inventory_counts / inventory_count_items / stock_adjustments / material_stock_view 的資料存取。
#
# Major Changes in This Revision:
# - 新增盤點單主表與明細表 CRUD 查詢。
# - 新增從 material_stock_view 讀取目前啟用且納管原料，用於建立盤點明細。
# - 新增盤點確認後寫入 stock_adjustments 的 repository 函式。
# - 新增回用料逐筆盤點查詢與 inventory_count_recycled_items CRUD。
#
# Notes:
# - Flet 0.84 專案使用。
# - 時間與業務邏輯由 services/stocktake_service.py 統一以 Asia/Taipei 處理。
# - 不修改 Supabase schema；本檔假設 inventory_counts / inventory_count_items / inventory_count_recycled_items 已建立。
# - stock_adjustments 第一版沿用 source / source_airtable_record_id 記錄盤點來源。
# =====================================================

from __future__ import annotations

from typing import Any

from db.supabase_client import supabase


TABLE_INVENTORY_COUNTS = "inventory_counts"
TABLE_INVENTORY_COUNT_ITEMS = "inventory_count_items"
TABLE_INVENTORY_COUNT_RECYCLED_ITEMS = "inventory_count_recycled_items"
TABLE_RECYCLED_MATERIALS = "recycled_materials"
TABLE_STOCK_ADJUSTMENTS = "stock_adjustments"
VIEW_MATERIAL_STOCK = "material_stock_view"


# ============================================================
# Material stock source
# ============================================================

def get_stocktake_material_stock_rows() -> list[dict[str, Any]]:
    """
    讀取盤點用帳面庫存。

    條件：
    - is_active = true
    - is_stock_managed = true

    不在 repository 判斷新料 / 母粒分類；分類由 service 層依 main_category / material_type / material_name 判斷。
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
# Recycled material source
# ============================================================

def get_stocktake_recycled_material_rows() -> list[dict[str, Any]]:
    """
    讀取回用料逐筆盤點來源。

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


# ============================================================
# Inventory counts
# ============================================================

def create_inventory_count(payload: dict[str, Any]) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_INVENTORY_COUNTS)
        .insert(payload)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]


def update_inventory_count(count_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_INVENTORY_COUNTS)
        .update(payload)
        .eq("id", count_id)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]


def get_inventory_count_by_id(count_id: str) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_INVENTORY_COUNTS)
        .select("*")
        .eq("id", count_id)
        .eq("is_deleted", False)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]


def get_inventory_counts(limit: int = 50, include_deleted: bool = False) -> list[dict[str, Any]]:
    query = supabase.table(TABLE_INVENTORY_COUNTS).select("*")

    if not include_deleted:
        query = query.eq("is_deleted", False)

    res = (
        query
        .order("count_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ============================================================
# Inventory count items
# ============================================================

def create_inventory_count_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return []

    res = (
        supabase.table(TABLE_INVENTORY_COUNT_ITEMS)
        .insert(items)
        .execute()
    )
    return res.data or []


def get_inventory_count_items(count_id: str, include_deleted: bool = False) -> list[dict[str, Any]]:
    query = (
        supabase.table(TABLE_INVENTORY_COUNT_ITEMS)
        .select("*")
        .eq("inventory_count_id", count_id)
    )

    if not include_deleted:
        query = query.eq("is_deleted", False)

    res = (
        query
        .order("material_name", desc=False)
        .execute()
    )
    return res.data or []


def get_inventory_count_item_by_id(item_id: str) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_INVENTORY_COUNT_ITEMS)
        .select("*")
        .eq("id", item_id)
        .eq("is_deleted", False)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]


def update_inventory_count_item(item_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_INVENTORY_COUNT_ITEMS)
        .update(payload)
        .eq("id", item_id)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]


# ============================================================
# Inventory count recycled items
# ============================================================

def create_inventory_count_recycled_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return []

    res = (
        supabase.table(TABLE_INVENTORY_COUNT_RECYCLED_ITEMS)
        .insert(items)
        .execute()
    )
    return res.data or []


def get_inventory_count_recycled_items(count_id: str, include_deleted: bool = False) -> list[dict[str, Any]]:
    query = (
        supabase.table(TABLE_INVENTORY_COUNT_RECYCLED_ITEMS)
        .select("*")
        .eq("inventory_count_id", count_id)
    )

    if not include_deleted:
        query = query.eq("is_deleted", False)

    res = (
        query
        .order("supplier", desc=False)
        .order("material_type", desc=False)
        .order("recycled_no", desc=False)
        .execute()
    )
    return res.data or []


def get_inventory_count_recycled_item_by_id(item_id: str) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_INVENTORY_COUNT_RECYCLED_ITEMS)
        .select("*")
        .eq("id", item_id)
        .eq("is_deleted", False)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]


def update_inventory_count_recycled_item(item_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_INVENTORY_COUNT_RECYCLED_ITEMS)
        .update(payload)
        .eq("id", item_id)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]


# ============================================================
# Stock adjustments
# ============================================================

def create_stock_adjustment(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    建立正式庫存調整。

    第一版人工盤點會寫入：
    - adjustment_type = stocktake
    - source = inventory_count
    - source_airtable_record_id = inventory_count_items.id
    """
    res = (
        supabase.table(TABLE_STOCK_ADJUSTMENTS)
        .insert(payload)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]
