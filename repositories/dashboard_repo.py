# =====================================================
# KNH MMS v2
# File: repositories/dashboard_repo.py
# File Revision: 2026-05-13-dashboard-active-material-filter-r1
# Status: current working version
# Last Updated: 2026-05-13 Asia/Taipei
#
# Purpose:
# - 首頁儀表板 Supabase 查詢層。
#
# Major Changes in This Revision:
# - get_active_maintenance_items() 保留 is_deleted = false 條件。
# - 首頁即時新料庫存查詢追加 is_stock_managed = true，排除未納管原料。
# - 新增 get_dashboard_active_material_rows()，供首頁月用量小卡依 active / stock-managed 原料名單過濾。
#
# Notes:
# - Flet 0.84 專案使用。
# - 時間顯示與業務邏輯由 service 層統一使用 Asia/Taipei。
# - 不修改 views/dashboard.py 與 sparkline UI，只調整資料查詢。
# - 本次不修改 Supabase schema / RLS / SQL view。
# =====================================================

from __future__ import annotations

from typing import Any

from db.supabase_client import supabase


VIEW_MATERIAL_STOCK = "material_stock_view"
TABLE_RECYCLED_MATERIALS = "recycled_materials"
TABLE_FEED_RECORDS = "feed_records"
TABLE_MATERIALS = "materials"
TABLE_MAINTENANCE_ITEMS = "maintenance_items"
TABLE_MAINTENANCE_RECORDS = "maintenance_records"
VIEW_MONTHLY_USAGE = "monthly_usage_view"


# ============================================================
# Stock / Inventory
# ============================================================

def get_material_stock_rows() -> list[dict[str, Any]]:
    """
    讀取正式即時庫存 view。
    來源：
    stock_adjustments + purchase_records - feed_records
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


def get_dashboard_active_material_rows() -> list[dict[str, Any]]:
    """
    讀取首頁目前作業用的原料主檔。

    用途：
    - 首頁「本月新料用量 / 本月母粒用量」小卡只顯示仍啟用且納管庫存的原料。
    - 停用或取消納管後，不影響歷史報表，但不再出現在首頁目前作業摘要。
    """
    res = (
        supabase.table(TABLE_MATERIALS)
        .select(
            """
            id,
            material_name,
            main_category,
            material_type,
            supplier,
            is_active,
            is_stock_managed
            """
        )
        .eq("is_active", True)
        .eq("is_stock_managed", True)
        .order("material_name", desc=False)
        .execute()
    )
    return res.data or []


def get_available_recycled_materials() -> list[dict[str, Any]]:
    """
    讀取在庫回用料。
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
# Feed / Usage
# ============================================================

def get_feed_records_between(start_iso: str, end_iso: str) -> list[dict[str, Any]]:
    """
    讀取指定時間區間內的打料紀錄。
    start_iso / end_iso 請由 service 以 Asia/Taipei 產生。
    """
    res = (
        supabase.table(TABLE_FEED_RECORDS)
        .select("*")
        .eq("is_deleted", False)
        .gte("feed_at", start_iso)
        .lt("feed_at", end_iso)
        .order("feed_at", desc=True)
        .execute()
    )
    return res.data or []


def get_recent_feed_records(limit: int = 10) -> list[dict[str, Any]]:
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


def get_monthly_usage_rows(start_month: str, end_month: str) -> list[dict[str, Any]]:
    """
    讀取 dashboard 用的月用量統計。
    來源是 monthly_usage_view：
    - monthly_usage_snapshots 歷史補登 / 月結快照
    - feed_records 系統打料紀錄即時計算
    """
    res = (
        supabase.table(VIEW_MONTHLY_USAGE)
        .select("*")
        .gte("usage_month", start_month)
        .lt("usage_month", end_month)
        .order("usage_month", desc=False)
        .execute()
    )
    return res.data or []


# ============================================================
# Maintenance
# ============================================================

def get_active_maintenance_items() -> list[dict[str, Any]]:
    res = (
        supabase.table(TABLE_MAINTENANCE_ITEMS)
        .select("*")
        .eq("is_active", True)
        .eq("is_deleted", False)
        .order("sort_order", desc=False)
        .execute()
    )
    return res.data or []


def get_maintenance_records_for_summary(limit: int = 500) -> list[dict[str, Any]]:
    """
    讀取保養紀錄供首頁摘要使用。
    若 maintenance_records 已有 is_deleted 欄位，排除軟刪除資料。
    """
    res = (
        supabase.table(TABLE_MAINTENANCE_RECORDS)
        .select(
            """
            *,
            maintenance_items (
                id,
                item_name,
                maintenance_type,
                main_category,
                sub_category,
                machine_area,
                cycle_days
            )
            """
        )
        .eq("is_deleted", False)
        .order("executed_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []
