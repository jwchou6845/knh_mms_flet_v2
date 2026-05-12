# =====================================================
# KNH MMS v2
# File: services/admin_service.py
# File Revision: 2026-05-13-admin-materials-r1
# Status: /admin materials phase 1 implementation
# Last Updated: 2026-05-13 Asia/Taipei
#
# Purpose:
# - /admin 系統控制中心服務層。
# - 整理控制中心首頁、保養管理入口摘要，以及 /admin/materials 原料與庫存設定頁資料。
#
# Major Changes in This Revision:
# - 保留 load_admin_home_data() 與 load_admin_maintenance_page_data()。
# - 新增 load_admin_materials_page_data()，讀取 materials 真實清單並合併 material_stock_view 庫存狀態。
# - 新增 create_material_from_form()、update_material_from_form()、toggle_material_active()。
# - 新增原料表單驗證、同名 + 同供應商重複檢查、數字欄位轉換。
#
# Notes:
# - 所有時間處理使用 Asia/Taipei。
# - 不修改 auth_session_service.py，不觸碰 cleanup_expired_user_sessions / restore_persistent_session / revoke_persistent_session。
# - 新增原料只建立 materials 主檔，不建立初始庫存，不覆蓋正式庫存數字。
# =====================================================

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from repositories.admin_repo import (
    create_material,
    get_material_by_id_for_admin,
    get_material_rows_for_admin,
    get_material_stock_rows_for_admin,
    get_user_session_rows_for_admin,
    get_maintenance_item_rows_for_admin,
    get_maintenance_node_rows_for_admin,
    set_material_active,
    update_material,
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


def now_taipei_iso() -> str:
    return now_taipei().isoformat()


def clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def normalize_text(value: Any) -> str:
    text = clean_text(value).replace("　", " ")
    return " ".join(text.split()).casefold()


def to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ["true", "1", "yes", "y", "是", "啟用", "納管"]:
        return True
    if text in ["false", "0", "no", "n", "否", "停用", "未納管"]:
        return False
    return default


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", ""))
    except Exception:
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(str(value).replace(",", "")))
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


def format_number(value: Any, digits: int = 0, default: str = "-") -> str:
    if value in [None, ""]:
        return default

    try:
        num = float(value)
    except Exception:
        return str(value)

    if digits <= 0:
        if abs(num - int(num)) < 0.000001:
            return f"{int(num):,}"
        return f"{num:,.1f}"

    return f"{num:,.{digits}f}"


# ============================================================
# Materials summary / stock helpers
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


def _stock_map_by_material(stock_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in stock_rows:
        material_id = clean_text(row.get("material_id") or row.get("id"))
        if material_id:
            result[material_id] = row
    return result


def _find_stock_row(material: dict[str, Any], stock_rows: list[dict[str, Any]], stock_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    material_id = clean_text(material.get("id"))
    if material_id and material_id in stock_map:
        return stock_map[material_id]

    material_name = normalize_text(material.get("material_name"))
    supplier = normalize_text(material.get("supplier"))
    for row in stock_rows:
        same_name = normalize_text(row.get("material_name")) == material_name
        same_supplier = normalize_text(row.get("supplier")) == supplier
        if same_name and same_supplier:
            return row

    return {}


def normalize_material_row(
    material: dict[str, Any],
    stock_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stock = stock_row or {}

    current_bags = stock.get("current_stock_bags")
    current_kg = stock.get("current_stock_kg") or stock.get("current_stock_weight_kg")
    low_stock = _is_low_stock_row({**material, **stock})

    bag_weight = to_float(material.get("bag_weight_kg"), 0)
    threshold = to_int(material.get("low_stock_threshold_bags"), 0)
    active = to_bool(material.get("is_active"), True)
    managed = to_bool(material.get("is_stock_managed"), False)

    if current_bags not in [None, ""]:
        stock_label = f"{format_number(current_bags)} 包"
    elif current_kg not in [None, ""]:
        stock_label = f"{format_number(current_kg)} KG"
    else:
        stock_label = "-"

    return {
        "id": material.get("id"),
        "material_name": clean_text(material.get("material_name"), "未命名原料"),
        "main_category": clean_text(material.get("main_category"), "-"),
        "material_type": clean_text(material.get("material_type"), "-"),
        "supplier": clean_text(material.get("supplier"), "-"),
        "bag_weight_kg": bag_weight,
        "bag_weight_label": f"{format_number(bag_weight)} KG" if bag_weight else "-",
        "low_stock_threshold_bags": threshold,
        "low_stock_threshold_label": f"{format_number(threshold)} 包" if threshold or threshold == 0 else "-",
        "is_stock_managed": managed,
        "stock_managed_label": "納管" if managed else "未納管",
        "is_active": active,
        "active_label": "啟用" if active else "停用",
        "note": clean_text(material.get("note"), ""),
        "current_stock_bags": current_bags,
        "current_stock_kg": current_kg,
        "stock_label": stock_label,
        "is_low_stock": bool(low_stock and active and managed),
        "low_stock_label": "低水位" if bool(low_stock and active and managed) else "正常",
        "created_at": material.get("created_at"),
        "updated_at": material.get("updated_at"),
        "created_at_label": format_datetime_taipei(material.get("created_at")),
        "updated_at_label": format_datetime_taipei(material.get("updated_at")),
        "raw": material,
        "stock_raw": stock,
    }


def build_material_filter_options(materials: list[dict[str, Any]]) -> dict[str, list[str]]:
    categories = sorted({row.get("main_category") for row in materials if row.get("main_category") and row.get("main_category") != "-"})
    types = sorted({row.get("material_type") for row in materials if row.get("material_type") and row.get("material_type") != "-"})
    suppliers = sorted({row.get("supplier") for row in materials if row.get("supplier") and row.get("supplier") != "-"})

    return {
        "main_categories": categories,
        "material_types": types,
        "suppliers": suppliers,
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
# Materials form validation / write
# ============================================================

def _parse_material_form(form_data: dict[str, Any]) -> tuple[ServiceResult | None, dict[str, Any]]:
    material_name = clean_text(form_data.get("material_name"))
    main_category = clean_text(form_data.get("main_category"))
    material_type = clean_text(form_data.get("material_type"))
    supplier = clean_text(form_data.get("supplier"))
    note = clean_text(form_data.get("note"))

    if not material_name:
        return ServiceResult(ok=False, message="請輸入原料名稱。"), {}
    if not main_category:
        return ServiceResult(ok=False, message="請輸入主分類。"), {}
    if not material_type:
        return ServiceResult(ok=False, message="請輸入原料類型。"), {}

    try:
        bag_weight_kg = float(str(form_data.get("bag_weight_kg") or "").replace(",", ""))
    except Exception:
        return ServiceResult(ok=False, message="包重 KG 必須是數字。"), {}

    try:
        low_stock_threshold_bags = int(float(str(form_data.get("low_stock_threshold_bags") or "").replace(",", "")))
    except Exception:
        return ServiceResult(ok=False, message="低水位門檻必須是整數。"), {}

    if bag_weight_kg <= 0:
        return ServiceResult(ok=False, message="包重 KG 必須大於 0。"), {}
    if low_stock_threshold_bags < 0:
        return ServiceResult(ok=False, message="低水位門檻不可小於 0。"), {}

    payload = {
        "material_name": material_name,
        "main_category": main_category,
        "material_type": material_type,
        "supplier": supplier or None,
        "bag_weight_kg": bag_weight_kg,
        "low_stock_threshold_bags": low_stock_threshold_bags,
        "is_stock_managed": to_bool(form_data.get("is_stock_managed"), True),
        "is_active": to_bool(form_data.get("is_active"), True),
        "note": note or None,
        "updated_at": now_taipei_iso(),
    }

    return None, payload


def _find_duplicate_material(
    material_rows: list[dict[str, Any]],
    material_name: str,
    supplier: str | None,
    exclude_id: str | None = None,
) -> dict[str, Any] | None:
    target_name = normalize_text(material_name)
    target_supplier = normalize_text(supplier)
    exclude = clean_text(exclude_id)

    for row in material_rows:
        if exclude and clean_text(row.get("id")) == exclude:
            continue
        same_name = normalize_text(row.get("material_name")) == target_name
        same_supplier = normalize_text(row.get("supplier")) == target_supplier
        if same_name and same_supplier:
            return row

    return None


def create_material_from_form(form_data: dict[str, Any], current_user: dict[str, Any] | None = None) -> ServiceResult:
    del current_user  # 目前 materials schema 尚未提供 created_by 欄位；保留參數供第二階段擴充。

    validation_error, payload = _parse_material_form(form_data)
    if validation_error:
        return validation_error

    try:
        existing_rows = get_material_rows_for_admin()
        duplicate = _find_duplicate_material(
            existing_rows,
            material_name=payload.get("material_name"),
            supplier=payload.get("supplier"),
        )
        if duplicate:
            return ServiceResult(
                ok=False,
                message="已有相同原料名稱與供應商，請確認是否重複。",
                data=duplicate,
            )

        created = create_material(payload)
        if not created:
            return ServiceResult(ok=False, message="新增原料失敗，Supabase 未回傳資料。")

        return ServiceResult(ok=True, message="原料已新增。", data=created)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"新增原料失敗：{exc}")


def update_material_from_form(
    material_id: str,
    form_data: dict[str, Any],
    current_user: dict[str, Any] | None = None,
) -> ServiceResult:
    del current_user

    material_id = clean_text(material_id)
    if not material_id:
        return ServiceResult(ok=False, message="缺少原料 ID。")

    validation_error, payload = _parse_material_form(form_data)
    if validation_error:
        return validation_error

    try:
        original = get_material_by_id_for_admin(material_id)
        if not original:
            return ServiceResult(ok=False, message="找不到此原料資料，可能已被刪除或權限不足。")

        existing_rows = get_material_rows_for_admin()
        duplicate = _find_duplicate_material(
            existing_rows,
            material_name=payload.get("material_name"),
            supplier=payload.get("supplier"),
            exclude_id=material_id,
        )
        if duplicate:
            return ServiceResult(
                ok=False,
                message="已有相同原料名稱與供應商，請確認是否重複。",
                data=duplicate,
            )

        updated = update_material(material_id, payload)
        if not updated:
            return ServiceResult(ok=False, message="更新原料失敗，Supabase 未回傳資料。")

        return ServiceResult(ok=True, message="原料資料已更新。", data=updated)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"更新原料失敗：{exc}")


def toggle_material_active(
    material_id: str,
    is_active: bool,
    current_user: dict[str, Any] | None = None,
) -> ServiceResult:
    del current_user

    material_id = clean_text(material_id)
    if not material_id:
        return ServiceResult(ok=False, message="缺少原料 ID。")

    try:
        original = get_material_by_id_for_admin(material_id)
        if not original:
            return ServiceResult(ok=False, message="找不到此原料資料。")

        updated = set_material_active(
            material_id,
            bool(is_active),
            payload_extra={"updated_at": now_taipei_iso()},
        )
        if not updated:
            return ServiceResult(ok=False, message="更新原料啟用狀態失敗，Supabase 未回傳資料。")

        return ServiceResult(
            ok=True,
            message="原料已啟用。" if is_active else "原料已停用。",
            data=updated,
        )

    except Exception as exc:
        return ServiceResult(ok=False, message=f"更新原料啟用狀態失敗：{exc}")


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


def load_admin_materials_page_data() -> ServiceResult:
    try:
        material_rows = get_material_rows_for_admin()
        stock_rows = get_material_stock_rows_for_admin()
        stock_map = _stock_map_by_material(stock_rows)

        normalized_rows = [
            normalize_material_row(
                material=row,
                stock_row=_find_stock_row(row, stock_rows, stock_map),
            )
            for row in material_rows
        ]

        normalized_rows.sort(
            key=lambda row: (
                row.get("main_category") or "",
                row.get("material_type") or "",
                row.get("supplier") or "",
                row.get("material_name") or "",
            )
        )

        return ServiceResult(
            ok=True,
            data={
                "materials": normalized_rows,
                "summary": build_material_summary(material_rows, stock_rows),
                "filter_options": build_material_filter_options(normalized_rows),
                "generated_at": now_taipei().strftime("%Y/%m/%d %H:%M"),
            },
        )

    except Exception as exc:
        return ServiceResult(
            ok=False,
            message=f"讀取原料與庫存設定資料失敗：{exc}",
            data={
                "materials": [],
                "summary": {
                    "active_material_count": 0,
                    "inactive_material_count": 0,
                    "stock_managed_count": 0,
                    "low_stock_count": 0,
                },
                "filter_options": {
                    "main_categories": [],
                    "material_types": [],
                    "suppliers": [],
                },
                "generated_at": now_taipei().strftime("%Y/%m/%d %H:%M"),
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
