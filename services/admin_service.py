# =====================================================
# KNH MMS v2
# File: services/admin_service.py
# File Revision: 2026-05-12-admin-phase1-r1
# Status: phase 1 new file
# Last Updated: 2026-05-12 Asia/Taipei
#
# Purpose:
# - /admin 系統控制中心服務層。
# - 整理控制中心首頁、原料摘要、Session 摘要與保養管理入口摘要。
#
# Major Changes in This Revision:
# - 新增 load_admin_home_data()，供 views/admin.py 顯示真實統計。
# - 新增 load_admin_maintenance_page_data()，供 /admin/maintenance 入口整合頁顯示摘要。
# - 對 user_sessions 的 revoked / revoked_at / expires_at 做容錯判斷。
#
# Notes:
# - 所有時間處理使用 Asia/Taipei。
# - 不修改 auth_session_service.py，不觸碰 cleanup_expired_user_sessions / restore_persistent_session / revoke_persistent_session。
# - 第一階段不新增假資料；未實作功能只回傳明確 placeholder 文字。
# =====================================================

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from repositories.admin_repo import (
    get_material_rows_for_admin,
    get_material_stock_rows_for_admin,
    get_user_session_rows_for_admin,
    get_maintenance_item_rows_for_admin,
    get_maintenance_node_rows_for_admin,
)


TAIPEI_TZ = ZoneInfo("Asia/Taipei")


@dataclass
class ServiceResult:
    ok: bool
    message: str = ""
    data: Any = None


# ============================================================
# Time / generic helpers
# ============================================================

def now_taipei() -> datetime:
    return datetime.now(TAIPEI_TZ)


def clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ["true", "1", "yes", "y", "是", "啟用"]:
        return True
    if text in ["false", "0", "no", "n", "否", "停用"]:
        return False
    return default


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None

    try:
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TAIPEI_TZ)
        return dt.astimezone(TAIPEI_TZ)
    except Exception:
        return None


def format_datetime_taipei(value: Any) -> str:
    dt = parse_datetime(value)
    if not dt:
        return "-"
    return dt.strftime("%Y/%m/%d %H:%M")


# ============================================================
# Materials summary
# ============================================================

def _is_low_stock_row(row: dict[str, Any]) -> bool:
    if to_bool(row.get("is_low_stock"), False):
        return True

    current = row.get("current_stock_bags")
    threshold = row.get("low_stock_threshold_bags")

    if current in [None, ""] or threshold in [None, ""]:
        return False

    return to_float(current, 0) <= to_float(threshold, 0)


def build_material_summary(
    material_rows: list[dict[str, Any]],
    stock_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    active_count = len([row for row in material_rows if to_bool(row.get("is_active"), True)])
    inactive_count = len([row for row in material_rows if not to_bool(row.get("is_active"), True)])
    stock_managed_count = len([row for row in material_rows if to_bool(row.get("is_stock_managed"), False)])

    low_stock_rows = []
    for row in stock_rows:
        if not to_bool(row.get("is_active"), True):
            continue
        if not to_bool(row.get("is_stock_managed"), True):
            continue
        if _is_low_stock_row(row):
            low_stock_rows.append(row)

    return {
        "active_material_count": active_count,
        "inactive_material_count": inactive_count,
        "stock_managed_count": stock_managed_count,
        "low_stock_count": len(low_stock_rows),
    }


# ============================================================
# User session summary
# ============================================================

def is_session_active(row: dict[str, Any]) -> bool:
    # 支援兩種 schema：revoked boolean 或 revoked_at timestamp。
    if to_bool(row.get("revoked"), False):
        return False

    if row.get("revoked_at") not in [None, ""]:
        return False

    expires_at = parse_datetime(row.get("expires_at"))
    if expires_at and expires_at <= now_taipei():
        return False

    # 若表中沒有 expires_at 欄位，第一階段保守視為非活躍，避免誤報。
    if "expires_at" not in row:
        return False

    return True


def build_session_summary(session_rows: list[dict[str, Any]]) -> dict[str, Any]:
    active_rows = [row for row in session_rows if is_session_active(row)]
    return {
        "active_session_count": len(active_rows),
        "total_session_rows": len(session_rows),
    }


# ============================================================
# Maintenance summary
# ============================================================

def build_maintenance_summary(
    item_rows: list[dict[str, Any]],
    node_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    not_deleted_items = [row for row in item_rows if not to_bool(row.get("is_deleted"), False)]
    deleted_items = [row for row in item_rows if to_bool(row.get("is_deleted"), False)]
    not_deleted_nodes = [row for row in node_rows if not to_bool(row.get("is_deleted"), False)]
    deleted_nodes = [row for row in node_rows if to_bool(row.get("is_deleted"), False)]

    active_items = [row for row in not_deleted_items if to_bool(row.get("is_active"), True)]
    inactive_items = [row for row in not_deleted_items if not to_bool(row.get("is_active"), True)]
    active_nodes = [row for row in not_deleted_nodes if to_bool(row.get("is_active"), True)]

    return {
        "active_item_count": len(active_items),
        "inactive_item_count": len(inactive_items),
        "active_node_count": len(active_nodes),
        "deleted_item_count": len(deleted_items),
        "deleted_node_count": len(deleted_nodes),
    }


# ============================================================
# Public service API
# ============================================================

def load_admin_home_data() -> ServiceResult:
    try:
        material_rows = get_material_rows_for_admin()
        stock_rows = get_material_stock_rows_for_admin()
        session_rows = get_user_session_rows_for_admin(limit=500)
        item_rows = get_maintenance_item_rows_for_admin()
        node_rows = get_maintenance_node_rows_for_admin()

        material_summary = build_material_summary(material_rows, stock_rows)
        session_summary = build_session_summary(session_rows)
        maintenance_summary = build_maintenance_summary(item_rows, node_rows)

        return ServiceResult(
            ok=True,
            data={
                "material_summary": material_summary,
                "session_summary": session_summary,
                "maintenance_summary": maintenance_summary,
                "generated_at": now_taipei().strftime("%Y/%m/%d %H:%M"),
                "recent_actions": [],
            },
        )

    except Exception as exc:
        return ServiceResult(
            ok=False,
            message=f"讀取控制中心資料失敗：{exc}",
            data={
                "material_summary": {
                    "active_material_count": 0,
                    "inactive_material_count": 0,
                    "stock_managed_count": 0,
                    "low_stock_count": 0,
                },
                "session_summary": {
                    "active_session_count": 0,
                    "total_session_rows": 0,
                },
                "maintenance_summary": {
                    "active_item_count": 0,
                    "inactive_item_count": 0,
                    "active_node_count": 0,
                    "deleted_item_count": 0,
                    "deleted_node_count": 0,
                },
                "generated_at": now_taipei().strftime("%Y/%m/%d %H:%M"),
                "recent_actions": [],
            },
        )


def load_admin_maintenance_page_data() -> ServiceResult:
    try:
        item_rows = get_maintenance_item_rows_for_admin()
        node_rows = get_maintenance_node_rows_for_admin()
        summary = build_maintenance_summary(item_rows, node_rows)

        return ServiceResult(
            ok=True,
            data={
                "summary": summary,
                "generated_at": now_taipei().strftime("%Y/%m/%d %H:%M"),
            },
        )

    except Exception as exc:
        return ServiceResult(
            ok=False,
            message=f"讀取保養管理摘要失敗：{exc}",
            data={
                "summary": {
                    "active_item_count": 0,
                    "inactive_item_count": 0,
                    "active_node_count": 0,
                    "deleted_item_count": 0,
                    "deleted_node_count": 0,
                },
                "generated_at": now_taipei().strftime("%Y/%m/%d %H:%M"),
            },
        )
