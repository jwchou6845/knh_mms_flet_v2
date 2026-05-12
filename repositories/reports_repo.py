# =====================================================
# KNH MMS v2
# File: repositories/reports_repo.py
# File Revision: 2026-05-12-reports-advanced-mapping-r1
# Status: current working version
# Last Updated: 2026-05-12 Asia/Taipei
#
# Purpose:
# - 報表中心資料存取層：Supabase 查詢快速報表與全條件篩選資料來源。
#
# Major Changes in This Revision:
# - 入庫紀錄查詢排除 is_deleted = true，避免已刪除入庫資料進入報表。
# - 本月入庫、全條件入庫與篩選選項來源一致排除已刪除資料。
# - 保養逾期清單來源排除已軟刪除保養項目。
#
# Notes:
# - 本次不變更資料表結構、不變更 Nginx /exports/ 下載機制。
# - reports_service.py 負責欄位 mapping；本檔只維持資料來源查詢。
# =====================================================
from __future__ import annotations

from typing import Any

from db.supabase_client import supabase


VIEW_MONTHLY_USAGE = "monthly_usage_view"
VIEW_MATERIAL_STOCK = "material_stock_view"

TABLE_RECYCLED_MATERIALS = "recycled_materials"
TABLE_PURCHASE_RECORDS = "purchase_records"
TABLE_FEED_RECORDS = "feed_records"
TABLE_MAINTENANCE_ITEMS = "maintenance_items"
TABLE_MAINTENANCE_RECORDS = "maintenance_records"
TABLE_HANDOVER_RECORDS = "handover_records"
TABLE_HANDOVER_ITEMS = "handover_items"
TABLE_USERS = "users"


# ============================================================
# Quick report sources
# ============================================================

def get_monthly_usage_rows(
    start_month: str,
    end_month: str,
) -> list[dict[str, Any]]:
    """
    讀取 monthly_usage_view。
    start_month / end_month 使用 YYYY-MM-01 字串。
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


def get_material_stock_rows() -> list[dict[str, Any]]:
    res = (
        supabase.table(VIEW_MATERIAL_STOCK)
        .select("*")
        .eq("is_active", True)
        .order("material_name", desc=False)
        .execute()
    )
    return res.data or []


def get_recycled_material_rows() -> list[dict[str, Any]]:
    res = (
        supabase.table(TABLE_RECYCLED_MATERIALS)
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def get_available_recycled_material_rows() -> list[dict[str, Any]]:
    res = (
        supabase.table(TABLE_RECYCLED_MATERIALS)
        .select("*")
        .eq("is_used", False)
        .eq("is_scrapped", False)
        .ilike("usage_status", "%在庫%")
        .order("supplier", desc=False)
        .order("material_type", desc=False)
        .execute()
    )
    return res.data or []


def get_purchase_records_between(
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    """
    讀取入庫紀錄。
    purchase_records 實際日期欄位為 purchase_date，不是 purchase_at。
    start_date / end_date 使用 YYYY-MM-DD，end_date 為 exclusive。
    """
    res = (
        supabase.table(TABLE_PURCHASE_RECORDS)
        .select("*")
        .eq("is_deleted", False)
        .gte("purchase_date", start_date)
        .lt("purchase_date", end_date)
        .order("purchase_date", desc=True)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def get_feed_records_between(
    start_iso: str,
    end_iso: str,
) -> list[dict[str, Any]]:
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


def get_maintenance_records(
    limit: int = 1000,
) -> list[dict[str, Any]]:
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


def get_maintenance_records_between(
    start_date: str,
    end_date: str,
    limit: int = 1000,
) -> list[dict[str, Any]]:
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
        .gte("executed_date", start_date)
        .lt("executed_date", end_date)
        .order("executed_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def get_open_handover_items() -> list[dict[str, Any]]:
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


def get_handover_items_between(
    start_date: str,
    end_date: str,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """
    交接紀錄第一版以 handover_items 為主，join handover_records 顯示來源。
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
        .gte("handover_records.handover_date", start_date)
        .lt("handover_records.handover_date", end_date)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ============================================================
# Filter option sources
# ============================================================

def get_user_rows() -> list[dict[str, Any]]:
    """
    報表篩選人員來源。
    第一版抓啟用使用者；若欄位不存在，service 會做容錯。
    """
    res = (
        supabase.table(TABLE_USERS)
        .select("id,name,role,is_active")
        .eq("is_active", True)
        .order("name", desc=False)
        .execute()
    )
    return res.data or []


def get_purchase_records_for_options(limit: int = 1000) -> list[dict[str, Any]]:
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


def get_feed_records_for_options(limit: int = 1000) -> list[dict[str, Any]]:
    res = (
        supabase.table(TABLE_FEED_RECORDS)
        .select("*")
        .eq("is_deleted", False)
        .order("feed_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []

