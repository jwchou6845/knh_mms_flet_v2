# =====================================================
# KNH MMS v2
# File: repositories/inventory_repo.py
# File Revision: 2026-05-14-recycled-recent-sort-r2
# Status: ready for testing
# Last Updated: 2026-05-14 Asia/Taipei
#
# Purpose:
# - 原料入庫作業 Supabase 查詢層。
#
# Major Changes in This Revision:
# - 修正「最近回用料入庫紀錄」排序策略。
# - 避免 recycled_materials.inbound_date 為 NULL 的舊資料在 PostgreSQL DESC 排序時擠掉新資料。
# - 最近回用料入庫改採雙查詢候選資料：
#   1) 依 created_at 取得最近建立資料。
#   2) 依 inbound_date 取得最近入庫日期資料。
#   最後在 Python 端以有效入庫日期排序後取前 N 筆。
# - 有效入庫日期優先順序：inbound_date -> recycled_no 前 8 碼 -> created_at 日期。
#
# Notes:
# - Flet 0.84 專案使用。
# - 本次不修改 views/inventory.py UI、不修改 services/inventory_service.py。
# - 建議另以 SQL 補齊 recycled_materials.inbound_date，讓資料庫資料本身完整。
# =====================================================

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from db.supabase_client import supabase


TABLE_MATERIALS = "materials"
TABLE_PURCHASE_RECORDS = "purchase_records"
TABLE_RECYCLED_MATERIALS = "recycled_materials"
VIEW_MATERIAL_STOCK = "material_stock_view"


# ============================================================
# Internal helpers
# ============================================================

def _safe_limit(limit: int, default: int = 10, max_limit: int = 100) -> int:
    """
    保護查詢筆數，避免 UI 傳入異常值造成過量查詢。
    """
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = default

    if value <= 0:
        return default

    return min(value, max_limit)


def _parse_date_value(value: Any) -> date | None:
    """
    將 Supabase 回傳的 date / datetime / ISO 字串轉成 date。
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    # 常見格式：2026-05-14 或 2026-05-14T07:31:39+00:00
    try:
        normalized = text.replace("Z", "+00:00")
        if "T" in normalized or "+" in normalized:
            return datetime.fromisoformat(normalized).date()
        return date.fromisoformat(normalized[:10])
    except ValueError:
        return None


def _date_from_recycled_no(recycled_no: Any) -> date | None:
    """
    從回用料編號前 8 碼推回日期。
    例如：2026051401 -> 2026-05-14。
    """
    text = str(recycled_no or "").strip()
    if len(text) < 8 or not text[:8].isdigit():
        return None

    try:
        return date(
            int(text[:4]),
            int(text[4:6]),
            int(text[6:8]),
        )
    except ValueError:
        return None


def _effective_recycled_inbound_date(row: dict[str, Any]) -> date | None:
    """
    最近回用料入庫排序用日期。
    優先使用正式 inbound_date；舊資料沒有 inbound_date 時，才用 recycled_no 前 8 碼補判斷。
    """
    return (
        _parse_date_value(row.get("inbound_date"))
        or _date_from_recycled_no(row.get("recycled_no"))
        or _parse_date_value(row.get("created_at"))
    )


def _created_at_sort_value(row: dict[str, Any]) -> float:
    """
    回傳 created_at timestamp，供同一天資料排序使用。
    """
    raw_value = row.get("created_at")
    if raw_value is None:
        return 0.0

    text = str(raw_value).strip()
    if not text:
        return 0.0

    try:
        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return 0.0


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    合併多個查詢結果時去重。
    優先用 id；若沒有 id，改用 recycled_no。
    """
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in rows:
        key = str(row.get("id") or row.get("recycled_no") or "").strip()
        if not key:
            key = f"row-{len(result)}"

        if key in seen:
            continue

        seen.add(key)
        result.append(row)

    return result


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


def get_material_stock_view() -> list[dict[str, Any]]:
    """
    讀取正式即時庫存 view。
    後續 dashboard / inventory / feed 都應該共用這個 view。
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
    safe_limit = _safe_limit(limit)

    res = (
        supabase.table(TABLE_PURCHASE_RECORDS)
        .select("*")
        .eq("is_deleted", False)
        .order("purchase_date", desc=True)
        .order("created_at", desc=True)
        .limit(safe_limit)
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

    重要：
    recycled_materials 舊資料可能沒有 inbound_date。
    若直接使用 order("inbound_date", desc=True).limit(10)，PostgreSQL 的 NULL 排序可能讓舊資料擠掉新資料。
    因此這裡先抓候選資料，再以 Python 的有效入庫日期排序。
    """
    safe_limit = _safe_limit(limit)
    candidate_limit = max(safe_limit * 10, 50)

    candidates: list[dict[str, Any]] = []

    # 先抓最近建立的資料，確保今天剛新增的回用料一定有機會進候選清單。
    created_res = (
        supabase.table(TABLE_RECYCLED_MATERIALS)
        .select("*")
        .order("created_at", desc=True)
        .limit(candidate_limit)
        .execute()
    )
    candidates.extend(created_res.data or [])

    # 再抓入庫日期較新的資料，保留「最近入庫日期」的業務語意。
    # filter("inbound_date", "not.is", "null") 可避免 NULL 排序干擾。
    try:
        inbound_res = (
            supabase.table(TABLE_RECYCLED_MATERIALS)
            .select("*")
            .filter("inbound_date", "not.is", "null")
            .order("inbound_date", desc=True)
            .order("created_at", desc=True)
            .limit(candidate_limit)
            .execute()
        )
        candidates.extend(inbound_res.data or [])
    except Exception:
        # 若目前 Supabase Python / PostgREST 版本不支援該 filter 寫法，
        # fallback 至普通排序，再交給 Python 排序與去重。
        inbound_res = (
            supabase.table(TABLE_RECYCLED_MATERIALS)
            .select("*")
            .order("inbound_date", desc=True)
            .order("created_at", desc=True)
            .limit(candidate_limit)
            .execute()
        )
        candidates.extend(inbound_res.data or [])

    unique_rows = _dedupe_rows(candidates)

    sorted_rows = sorted(
        unique_rows,
        key=lambda row: (
            (_effective_recycled_inbound_date(row) or date.min).toordinal(),
            _created_at_sort_value(row),
            str(row.get("recycled_no") or ""),
        ),
        reverse=True,
    )

    return sorted_rows[:safe_limit]
