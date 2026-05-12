# =====================================================
# KNH MMS v2
# File: repositories/admin_repo.py
# File Revision: 2026-05-12-admin-phase1-r1
# Status: phase 1 new file
# Last Updated: 2026-05-12 Asia/Taipei
#
# Purpose:
# - /admin 系統控制中心資料存取層。
# - 第一階段提供控制中心首頁、原料摘要、低水位摘要、Session 摘要與保養管理入口摘要。
#
# Major Changes in This Revision:
# - 新增 materials / material_stock_view / user_sessions / maintenance_items / maintenance_nodes 讀取函式。
# - 採容錯查詢，避免 user_sessions 或部分欄位差異造成 /admin 首頁無法載入。
# - 不修改 auth_session_service.py，不影響 12 小時免重登正式流程。
#
# Notes:
# - Flet 0.84；此檔不含 UI。
# - Supabase 查詢集中於 repository，view 不直接呼叫 Supabase。
# - 時間顯示與判斷由 service 層轉換為 Asia/Taipei。
# =====================================================

from __future__ import annotations

from typing import Any

from db.supabase_client import supabase


TABLE_MATERIALS = "materials"
VIEW_MATERIAL_STOCK = "material_stock_view"
TABLE_USER_SESSIONS = "user_sessions"
TABLE_MAINTENANCE_ITEMS = "maintenance_items"
TABLE_MAINTENANCE_NODES = "maintenance_nodes"


# ============================================================
# Generic helpers
# ============================================================

def _safe_execute(query, fallback: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    try:
        res = query.execute()
        return res.data or []
    except Exception as exc:
        print("admin_repo query failed:", repr(exc))
        return fallback or []


# ============================================================
# Materials
# ============================================================

def get_material_rows_for_admin() -> list[dict[str, Any]]:
    """
    讀取原料主檔。
    第一階段先抓全部 rows，篩選與統計由 service 層整理。
    """
    query = (
        supabase.table(TABLE_MATERIALS)
        .select("*")
        .order("main_category", desc=False)
        .order("material_name", desc=False)
    )
    return _safe_execute(query)


def get_material_stock_rows_for_admin() -> list[dict[str, Any]]:
    """
    讀取即時庫存 view，用於低水位摘要。
    若 view 欄位或 RLS 異常，回傳空陣列，避免首頁整頁失敗。
    """
    query = supabase.table(VIEW_MATERIAL_STOCK).select("*")
    return _safe_execute(query)


# ============================================================
# User sessions
# ============================================================

def get_user_session_rows_for_admin(limit: int = 500) -> list[dict[str, Any]]:
    """
    讀取 user_sessions 供控制中心摘要使用。
    不在這裡做刪除、revoke 或清理，避免影響 auth_session_service.py 穩定流程。
    """
    query = (
        supabase.table(TABLE_USER_SESSIONS)
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    return _safe_execute(query)


# ============================================================
# Maintenance admin summaries
# ============================================================

def get_maintenance_item_rows_for_admin() -> list[dict[str, Any]]:
    query = supabase.table(TABLE_MAINTENANCE_ITEMS).select("*")
    return _safe_execute(query)


def get_maintenance_node_rows_for_admin() -> list[dict[str, Any]]:
    query = supabase.table(TABLE_MAINTENANCE_NODES).select("*")
    return _safe_execute(query)
