# =====================================================
# KNH MMS v2
# File: repositories/reports_repo.py
# File Revision: 2026-05-14-reports-recycled-inbound-r2
# Status: ready for testing
# Last Updated: 2026-05-14 Asia/Taipei
#
# Purpose:
# - 報表中心資料存取層：Supabase 查詢快速報表與全條件篩選資料來源。
#
# Major Changes in This Revision:
# - 新增 get_recycled_materials_between()，供報表中心「入庫紀錄」合併回用料入庫。
# - 新增 get_recycled_materials_for_options()，讓篩選選項可參考完整回用料歷史資料。
# - 保留目前狀態類報表只讀取 is_active = true 且 is_stock_managed = true 的原料邏輯。
# - 歷史報表來源仍保留停用原料歷史資料，不因原料停用或未納管而消失。
#
# Notes:
# - 本次不修改 views/reports.py。
# - 回用料入庫正式來源為 recycled_materials，日期欄位使用 inbound_date。
# - 所有日期區間函式採 end_date exclusive，與 service 層一致。
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
    """
    讀取目前有效且納管的正式庫存資料。

    用於「目前低水位清單」與「目前庫存總表」這類目前狀態報表。
    歷史用量、打料紀錄與入庫紀錄不得使用此函式過濾，避免停用原料歷史資料消失。
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


def get_recycled_materials_for_options(limit: int = 1000) -> list[dict[str, Any]]:
    """
    報表篩選選項用回用料來源。

    與 get_available_recycled_material_rows() 不同，這裡保留已領用 / 已報廢歷史資料，
    避免歷史報表的供應商或原料種類下拉選項缺漏。
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


def get_purchase_records_between(
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    """
    讀取供應商新料 / 母粒入庫紀錄。
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


def get_recycled_materials_between(
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    """
    讀取回用料入庫紀錄。

    recycled_materials 是回用料入庫主檔，日期欄位為 inbound_date。
    start_date / end_date 使用 YYYY-MM-DD，end_date 為 exclusive。

    注意：
    - 本函式只回傳日期區間內的回用料入庫。
    - 已領用或已報廢的回用料仍是歷史入庫紀錄，不應在報表中排除。
    """
    res = (
        supabase.table(TABLE_RECYCLED_MATERIALS)
        .select("*")
        .gte("inbound_date", start_date)
        .lt("inbound_date", end_date)
        .order("inbound_date", desc=True)
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

