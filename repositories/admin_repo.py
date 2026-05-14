# =====================================================
# KNH MMS v2
# File: repositories/admin_repo.py
# File Revision: 2026-05-14-admin-stocktake-summary-r1
# Status: /admin stocktake management summary integration
# Last Updated: 2026-05-14 Asia/Taipei
#
# Purpose:
# - /admin 系統控制中心資料存取層。
# - 提供控制中心首頁、保養管理摘要、原料與庫存設定頁資料讀寫。
#
# Major Changes in This Revision:
# - 保留 Phase 1 控制中心首頁使用的 materials / material_stock_view / user_sessions / maintenance 摘要查詢。
# - 新增 create_material()、update_material()、set_material_active()，支援 /admin/materials 正式功能頁。
# - 原料管理只更新 materials 主檔，不直接覆蓋庫存數字，不修改 Supabase schema。
# - 新增 inventory_counts 查詢，供控制中心首頁顯示人工盤點摘要與入口。
#
# Notes:
# - Flet 0.84；此檔不含 UI。
# - Supabase 查詢集中於 repository，view 不直接呼叫 Supabase。
# - 時間顯示與業務判斷由 service 層轉換為 Asia/Taipei。
# - 不修改 auth_session_service.py，不影響 12 小時免重登正式流程。
# =====================================================

from __future__ import annotations

from typing import Any

from db.supabase_client import supabase


TABLE_MATERIALS = "materials"
VIEW_MATERIAL_STOCK = "material_stock_view"
TABLE_USER_SESSIONS = "user_sessions"
TABLE_MAINTENANCE_ITEMS = "maintenance_items"
TABLE_MAINTENANCE_NODES = "maintenance_nodes"
TABLE_INVENTORY_COUNTS = "inventory_counts"


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
    /admin/materials 第一版先抓全部 rows，篩選與統計由 service / view 層整理。
    """
    query = (
        supabase.table(TABLE_MATERIALS)
        .select("*")
        .order("main_category", desc=False)
        .order("material_name", desc=False)
    )
    return _safe_execute(query)


def get_material_by_id_for_admin(material_id: str) -> dict[str, Any] | None:
    if not material_id:
        return None

    try:
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
    except Exception as exc:
        print("admin_repo get_material_by_id_for_admin failed:", repr(exc))
        return None


def get_material_stock_rows_for_admin() -> list[dict[str, Any]]:
    """
    讀取即時庫存 view，用於低水位摘要與 /admin/materials 目前庫存顯示。
    若 view 欄位或 RLS 異常，回傳空陣列，避免整頁失敗。
    """
    query = supabase.table(VIEW_MATERIAL_STOCK).select("*")
    return _safe_execute(query)


def create_material(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    新增 materials 主檔。
    注意：此函式不新增庫存，不寫 stock_adjustments，不直接覆蓋庫存數字。
    """
    res = (
        supabase.table(TABLE_MATERIALS)
        .insert(payload)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def update_material(material_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    更新 materials 主檔。
    """
    if not material_id:
        return None

    res = (
        supabase.table(TABLE_MATERIALS)
        .update(payload)
        .eq("id", material_id)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def set_material_active(material_id: str, is_active: bool, payload_extra: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """
    啟用 / 停用原料。
    只更新 materials.is_active，不刪除歷史紀錄。
    """
    payload: dict[str, Any] = {"is_active": bool(is_active)}
    if payload_extra:
        payload.update(payload_extra)

    return update_material(material_id, payload)


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
# Stocktake admin summaries
# ============================================================

def get_inventory_count_rows_for_admin(limit: int = 500) -> list[dict[str, Any]]:
    """
    讀取人工盤點單供控制中心摘要使用。

    注意：
    - 此查詢只讀取 inventory_counts 主表，不讀取盤點明細，避免控制中心首頁載入過重。
    - is_deleted=true 的資料不進入一般控制中心摘要；未來若建立已刪除盤點單頁再另開查詢。
    - VM 後端目前使用 Supabase secret key，可 bypass RLS；仍保留 RLS enabled 的資料表安全設定。
    """
    query = (
        supabase.table(TABLE_INVENTORY_COUNTS)
        .select("*")
        .eq("is_deleted", False)
        .order("count_date", desc=True)
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
