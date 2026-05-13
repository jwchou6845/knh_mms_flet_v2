# =====================================================
# KNH MMS v2
# File: services/inventory_service.py
# File Revision: 2026-05-13-inventory-active-material-guard-r1
# Status: current working version
# Last Updated: 2026-05-13 Asia/Taipei
#
# Purpose:
# - 原料入庫作業服務層：載入原料清單、近期入庫紀錄、寫入供應商新料/母粒與回用料入庫。
#
# Major Changes in This Revision:
# - 供應商新料 / 母粒入庫送出前，增加 materials.is_active 與 is_stock_managed 防呆檢查。
# - 避免控制中心停用或取消納管後，舊頁面下拉殘留仍可建立正式入庫紀錄。
# - 保留回用料入庫流程、近期紀錄整理與 Asia/Taipei 日期處理。
#
# Notes:
# - Flet 0.84 專案使用。
# - 本次不修改 views/inventory.py UI、不修改 Supabase schema。
# =====================================================

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from repositories.inventory_repo import (
    create_purchase_record,
    create_recycled_material,
    get_active_materials,
    get_material_by_id,
    get_material_stock_view,
    get_recent_purchase_records,
    get_recent_recycled_materials,
    purchase_batch_exists,
    recycled_no_exists,
)


TAIPEI_TZ = ZoneInfo("Asia/Taipei")


@dataclass
class ServiceResult:
    ok: bool
    message: str = ""
    data: Any = None


# ============================================================
# Date / Time
# ============================================================

def now_taipei() -> datetime:
    return datetime.now(TAIPEI_TZ)


def today_taipei_date() -> date:
    return now_taipei().date()


def today_batch_prefix() -> str:
    return today_taipei_date().strftime("%Y%m%d")


def today_dash_date() -> str:
    return today_taipei_date().strftime("%Y-%m-%d")


def parse_date_text(value: str | None) -> date | None:
    text = str(value or "").strip()

    if not text:
        return None

    normalized = text.replace("/", "-")

    try:
        return datetime.strptime(normalized, "%Y-%m-%d").date()
    except Exception:
        return None


def format_date(value: str | date | None) -> str:
    if not value:
        return "-"

    if isinstance(value, date):
        return value.strftime("%Y/%m/%d")

    parsed = parse_date_text(str(value))
    if parsed:
        return parsed.strftime("%Y/%m/%d")

    return str(value)


# ============================================================
# Helpers
# ============================================================

def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def build_material_options(materials: list[dict[str, Any]]) -> dict[str, str]:
    """
    回傳：
    {
        "原料名稱": "material_id"
    }
    """
    result: dict[str, str] = {}

    for material in materials:
        material_id = str(material.get("id") or "").strip()
        material_name = str(material.get("material_name") or "").strip()

        if material_id and material_name:
            result[material_name] = material_id

    return result


def build_stock_rows(stock_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for row in stock_rows:
        rows.append(
            {
                "material_id": row.get("material_id"),
                "material_name": row.get("material_name") or "-",
                "main_category": row.get("main_category") or "",
                "material_type": row.get("material_type") or "",
                "supplier": row.get("supplier") or "",
                "current_stock_bags": _to_int(row.get("current_stock_bags"), 0),
                "current_stock_kg": _to_float(row.get("current_stock_kg"), 0),
                "low_stock_threshold_bags": _to_int(row.get("low_stock_threshold_bags"), 3),
                "is_low_stock": bool(row.get("is_low_stock", False)),
            }
        )

    return rows


def build_recent_purchase_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for record in records:
        rows.append(
            {
                "id": record.get("id"),
                "date": format_date(record.get("purchase_date")),
                "batch_no": record.get("purchase_batch_no") or "-",
                "material_name": record.get("material_name") or "-",
                "supplier": record.get("supplier") or "-",
                "quantity_bags": _to_int(record.get("quantity_bags"), 0),
                "quantity_kg": _to_float(record.get("quantity_kg"), 0),
            }
        )

    return rows


def build_recent_recycled_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for record in records:
        rows.append(
            {
                "id": record.get("id"),
                "date": format_date(record.get("inbound_date")),
                "recycled_no": record.get("recycled_no") or "-",
                "material_type": record.get("material_type") or "-",
                "source_machine": record.get("source_machine") or "-",
                "supplier": record.get("supplier") or "-",
                "weight_kg": _to_float(record.get("weight_kg"), 0),
                "usage_status": record.get("usage_status") or "-",
                "is_used": bool(record.get("is_used", False)),
            }
        )

    return rows


# ============================================================
# Page Data
# ============================================================

def load_inventory_page_data() -> ServiceResult:
    try:
        materials = get_active_materials()
        stock_rows_raw = get_material_stock_view()
        recent_purchase_raw = get_recent_purchase_records(limit=10)
        recent_recycled_raw = get_recent_recycled_materials(limit=10)

        return ServiceResult(
            ok=True,
            data={
                "material_options": build_material_options(materials),
                "stock_rows": build_stock_rows(stock_rows_raw),
                "recent_purchase_records": build_recent_purchase_rows(recent_purchase_raw),
                "recent_recycled_records": build_recent_recycled_rows(recent_recycled_raw),
            },
        )

    except Exception as exc:
        return ServiceResult(
            ok=False,
            message=f"讀取入庫資料失敗：{exc}",
            data={
                "material_options": {},
                "stock_rows": [],
                "recent_purchase_records": [],
                "recent_recycled_records": [],
            },
        )


# ============================================================
# Submit: Purchase
# ============================================================

def submit_purchase_record(
    purchase_batch_no: str,
    purchase_date: str,
    material_id: str,
    quantity_bags: int,
    created_by_user_id: str | None = None,
    created_by_name: str | None = None,
) -> ServiceResult:
    batch_no = str(purchase_batch_no or "").strip()
    material_id = str(material_id or "").strip()
    parsed_date = parse_date_text(purchase_date)
    qty = _to_int(quantity_bags, 0)

    if not batch_no:
        return ServiceResult(ok=False, message="請輸入進貨批號。")

    if not parsed_date:
        return ServiceResult(ok=False, message="進貨日期格式錯誤，請使用 YYYY-MM-DD。")

    if not material_id:
        return ServiceResult(ok=False, message="請選擇關聯原料。")

    if qty <= 0:
        return ServiceResult(ok=False, message="請輸入正確的進貨數量。")

    try:
        if purchase_batch_exists(batch_no):
            return ServiceResult(ok=False, message="此進貨批號已存在，請更換。")

        material = get_material_by_id(material_id)

        if not material:
            return ServiceResult(ok=False, message="找不到此原料資料。")

        if not bool(material.get("is_active", True)):
            return ServiceResult(ok=False, message="此原料已停用，請重新整理後選擇其他原料。")

        if not bool(material.get("is_stock_managed", True)):
            return ServiceResult(ok=False, message="此原料未納管庫存，不能建立正式入庫紀錄。")

        material_name = material.get("material_name") or ""
        supplier = material.get("supplier") or ""
        bag_weight_kg = _to_float(material.get("bag_weight_kg"), 0)
        quantity_kg = qty * bag_weight_kg if bag_weight_kg else 0

        payload = {
            "purchase_date": parsed_date.isoformat(),
            "purchase_batch_no": batch_no,
            "material_id": material_id,
            "material_name": material_name,
            "supplier": supplier or None,
            "quantity_bags": qty,
            "bag_weight_kg": bag_weight_kg,
            "quantity_kg": quantity_kg,
            "note": None,
            "created_by_user_id": created_by_user_id,
            "created_by_name": created_by_name,
            "source": "app",
        }

        created = create_purchase_record(payload)

        if not created:
            return ServiceResult(ok=False, message="新增進貨紀錄失敗，Supabase 未回傳資料。")

        return ServiceResult(ok=True, message=f"新料 {material_name} 入庫紀錄建立成功。", data=created)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"寫入失敗：{exc}")


# ============================================================
# Submit: Recycled Material
# ============================================================

def submit_recycled_material(
    recycled_no: str,
    inbound_date: str,
    material_type: str,
    source_machine: str,
    weight_kg: float,
    supplier: str,
) -> ServiceResult:
    recycled_no = str(recycled_no or "").strip()
    material_type = str(material_type or "").strip()
    source_machine = str(source_machine or "").strip()
    supplier = str(supplier or "").strip()
    parsed_date = parse_date_text(inbound_date)
    weight = _to_float(weight_kg, 0)

    if not recycled_no:
        return ServiceResult(ok=False, message="請完整填寫回用料編號。")

    if not parsed_date:
        return ServiceResult(ok=False, message="入庫日期格式錯誤，請使用 YYYY-MM-DD。")

    if not material_type:
        return ServiceResult(ok=False, message="請選擇原料種類。")

    if not source_machine:
        return ServiceResult(ok=False, message="請選擇來源機台。")

    if weight <= 0:
        return ServiceResult(ok=False, message="請輸入正確的重量。")

    if not supplier:
        return ServiceResult(ok=False, message="請選擇供應商。")

    try:
        if recycled_no_exists(recycled_no):
            return ServiceResult(ok=False, message="此回用料編號已存在，請更換。")

        payload = {
            "recycled_no": recycled_no,
            "inbound_date": parsed_date.isoformat(),
            "weight_kg": weight,
            "material_type": material_type,
            "source_machine": source_machine,
            "supplier": supplier,
            "usage_status": "在庫",
            "is_used": False,
            "is_scrapped": False,
            "note": None,
        }

        created = create_recycled_material(payload)

        if not created:
            return ServiceResult(ok=False, message="新增回用料入庫失敗，Supabase 未回傳資料。")

        return ServiceResult(ok=True, message="廠內回用料入庫紀錄建立成功。", data=created)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"寫入失敗：{exc}")
