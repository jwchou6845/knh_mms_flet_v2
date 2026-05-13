# =====================================================
# KNH MMS v2
# File: services/feed_service.py
# File Revision: 2026-05-13-feed-active-material-guard-r1
# Status: current working version
# Last Updated: 2026-05-13 Asia/Taipei
#
# Purpose:
# - 現場打料作業服務層：載入原料/回用料清單、近期打料紀錄整理、送出打料紀錄。
#
# Major Changes in This Revision:
# - 新料 / 母粒打料送出前，增加 materials.is_active 與 is_stock_managed 防呆檢查。
# - 避免控制中心停用或取消納管後，舊頁面下拉殘留仍可送出打料紀錄。
# - 保留既有近期打料紀錄欄位、回用料流程與 Asia/Taipei 時間處理。
#
# Notes:
# - Flet 0.84 專案使用。
# - 本次不修改 views/feed.py UI、不修改回用料領用流程、不修改 Supabase schema。
# =====================================================

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from repositories.feed_repo import (
    create_feed_record,
    get_available_recycled_materials,
    get_material_by_id,
    get_material_stock_rows,
    get_recent_feed_records,
    get_recycled_material_by_id,
    mark_recycled_material_used,
)


TAIPEI_TZ = ZoneInfo("Asia/Taipei")


@dataclass
class ServiceResult:
    ok: bool
    message: str = ""
    data: Any = None


# ============================================================
# 日期 / 時間工具
# ============================================================

def now_taipei() -> datetime:
    return datetime.now(TAIPEI_TZ)


def today_taipei_date() -> date:
    return now_taipei().date()


def today_slash_date() -> str:
    return today_taipei_date().strftime("%Y/%m/%d")


def today_dash_date() -> str:
    return today_taipei_date().strftime("%Y-%m-%d")


def parse_feed_date_to_taipei_iso(date_text: str | None) -> str:
    """
    將畫面輸入日期轉為 Asia/Taipei datetime ISO。
    使用者輸入日期代表台灣現場日期，時分秒採目前台灣時間。
    """
    raw = (date_text or "").strip().replace("/", "-")
    current = now_taipei()

    try:
        parsed_date = datetime.strptime(raw, "%Y-%m-%d").date()
        dt = datetime(
            year=parsed_date.year,
            month=parsed_date.month,
            day=parsed_date.day,
            hour=current.hour,
            minute=current.minute,
            second=0,
            microsecond=0,
            tzinfo=TAIPEI_TZ,
        )
        return dt.isoformat()
    except Exception:
        return current.replace(microsecond=0).isoformat()


def format_feed_datetime(value: str | None) -> tuple[str, str]:
    """
    Supabase timestamptz 顯示為台灣時間。
    回傳：
    - date_label: MM/DD
    - time_label: HH:MM
    """
    text = str(value or "").strip()

    if not text:
        return "-", "-"

    try:
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TAIPEI_TZ)

        dt = dt.astimezone(TAIPEI_TZ)
        return dt.strftime("%m/%d"), dt.strftime("%H:%M")

    except Exception:
        return (
            text[5:10].replace("-", "/") if len(text) >= 10 else "-",
            text[11:16] if len(text) >= 16 else "-",
        )


# ============================================================
# 資料整理
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


def is_aux_material(row: dict[str, Any]) -> bool:
    category = str(row.get("main_category") or "")
    material_type = str(row.get("material_type") or "")
    name = str(row.get("material_name") or "")
    combined = f"{category} {material_type} {name}"
    return "母粒" in combined or "輔助母粒" in combined


def build_material_maps(stock_rows: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    """
    使用 material_stock_view 回傳的資料建立下拉清單。
    回傳：
    - new_materials: {顯示名稱: material_id}
    - aux_materials: {顯示名稱: material_id}
    """
    new_materials: dict[str, str] = {}
    aux_materials: dict[str, str] = {}

    for row in stock_rows:
        name = str(row.get("material_name") or "").strip()
        material_id = str(row.get("material_id") or "").strip()

        if not name or not material_id:
            continue

        if is_aux_material(row):
            aux_materials[name] = material_id
        else:
            new_materials[name] = material_id

    return new_materials, aux_materials


def build_low_stock_items(stock_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    低水位警示改讀 material_stock_view。
    判斷依據：current_stock_bags <= low_stock_threshold_bags。
    """
    result: list[dict[str, Any]] = []

    for row in stock_rows:
        if not row.get("is_low_stock"):
            continue

        qty = _to_int(row.get("current_stock_bags"), 0)

        result.append(
            {
                "id": row.get("material_id"),
                "name": row.get("material_name") or "-",
                "qty": qty,
                "main_category": row.get("main_category") or "",
                "material_type": row.get("material_type") or "",
                "threshold": _to_int(row.get("low_stock_threshold_bags"), 3),
            }
        )

    result.sort(key=lambda x: (x.get("qty", 0), x.get("name") or ""))
    return result


def build_recycled_material_map(rows: list[dict[str, Any]]) -> dict[str, str]:
    """
    回用料下拉顯示格式：
    【供應商】 回用料編號 ｜ 原料種類 ｜ 重量 KG
    """
    result: dict[str, str] = {}

    for row in rows:
        recycled_id = str(row.get("id") or "").strip()
        recycled_no = str(row.get("recycled_no") or "").strip()
        supplier = str(row.get("supplier") or "未知供應商").strip()
        mat_type = str(row.get("material_type") or "未知種類").strip()
        weight = _to_float(row.get("weight_kg"), 0)

        if not recycled_id or not recycled_no:
            continue

        display = f"【{supplier}】 {recycled_no} ｜ {mat_type} ｜ {int(weight)} KG"
        result[display] = recycled_id

    return result


def build_recent_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for record in records:
        feed_type = record.get("feed_type") or ""

        if feed_type == "aux":
            tag = "母粒"
            tag_color = "#8B5CF6"
            tag_bg = "#F3E8FF"
        elif feed_type == "recycled":
            tag = "回用料"
            tag_color = "#F97316"
            tag_bg = "#FFF7ED"
        else:
            tag = "新料"
            tag_color = "#2F80ED"
            tag_bg = "#E5F0FF"

        date_label, time_label = format_feed_datetime(record.get("feed_at"))

        if feed_type == "recycled":
            weight = _to_float(record.get("weight_kg"), 0)
            qty_text = f"{int(weight)} KG" if weight else "1 筆"
        else:
            qty = _to_int(record.get("quantity_bags"), 0)
            qty_text = f"{qty} 包"

        operator_text = (
            record.get("operator_name")
            or record.get("created_by_name")
            or "-"
        )
        note_text = record.get("note") or "-"

        result.append(
            {
                "id": record.get("id"),
                "date": date_label,
                "time": time_label,
                "type": tag,
                "batch_no": record.get("batch_no") or "-",
                "machine_code": record.get("machine_code") or "-",
                "material": record.get("material_name") or "-",
                "qty": qty_text,
                "operator": operator_text,
                "note": note_text,
                "tag_bg": tag_bg,
                "tag_color": tag_color,
                "raw": record,
            }
        )

    return result


# ============================================================
# 頁面載入資料
# ============================================================

def load_feed_page_data() -> ServiceResult:
    try:
        stock_rows = get_material_stock_rows()
        recycled_rows = get_available_recycled_materials()
        recent_raw = get_recent_feed_records(limit=40)

        new_materials, aux_materials = build_material_maps(stock_rows)
        rec_materials = build_recycled_material_map(recycled_rows)
        low_stock_items = build_low_stock_items(stock_rows)
        recent_records = build_recent_records(recent_raw)

        return ServiceResult(
            ok=True,
            data={
                "new_materials": new_materials,
                "aux_materials": aux_materials,
                "rec_materials": rec_materials,
                "low_stock_items": low_stock_items,
                "recent_records": recent_records,
                "stock_rows": stock_rows,
            },
        )

    except Exception as exc:
        return ServiceResult(
            ok=False,
            message=f"讀取打料資料失敗：{exc}",
            data={
                "new_materials": {},
                "aux_materials": {},
                "rec_materials": {},
                "low_stock_items": [],
                "recent_records": [],
                "stock_rows": [],
            },
        )


# ============================================================
# 送出新料 / 母粒
# ============================================================

def submit_material_feed_record(
    feed_type: str,
    material_id: str,
    batch_no: str,
    feed_date: str,
    machine_code: str,
    quantity_bags: int,
    operator_name: str | None = None,
    note: str | None = None,
    created_by_user_id: str | None = None,
    created_by_name: str | None = None,
) -> ServiceResult:
    if feed_type not in ["new", "aux"]:
        return ServiceResult(ok=False, message="打料類型錯誤。")

    if not material_id:
        return ServiceResult(ok=False, message="請選擇領用原料。")

    if not batch_no:
        return ServiceResult(ok=False, message="請輸入原料批號。")

    if not feed_date:
        return ServiceResult(ok=False, message="請填寫日期。")

    if not machine_code:
        return ServiceResult(ok=False, message="請選擇乾燥塔。")

    if quantity_bags <= 0:
        return ServiceResult(ok=False, message="領用數量必須大於 0。")

    try:
        material = get_material_by_id(material_id)

        if not material:
            return ServiceResult(ok=False, message="找不到此原料資料。")

        if not bool(material.get("is_active", True)):
            return ServiceResult(ok=False, message="此原料已停用，請重新整理後選擇其他原料。")

        if not bool(material.get("is_stock_managed", True)):
            return ServiceResult(ok=False, message="此原料未納管庫存，不能建立正式打料紀錄。")

        material_name = material.get("material_name") or ""
        bag_weight_kg = _to_float(material.get("bag_weight_kg"), 0)
        weight_kg = bag_weight_kg * quantity_bags if bag_weight_kg else None

        material_source = "新料" if feed_type == "new" else "輔助母粒"

        payload = {
            "feed_type": feed_type,
            "batch_no": batch_no,
            "feed_at": parse_feed_date_to_taipei_iso(feed_date),
            "machine_code": machine_code,
            "material_id": material_id,
            "recycled_material_id": None,
            "material_name": material_name,
            "material_source": material_source,
            "supplier": material.get("supplier"),
            "quantity_bags": quantity_bags,
            "weight_kg": weight_kg,
            "bag_weight_kg": bag_weight_kg,
            "operator_name": operator_name or created_by_name,
            "note": note or None,
            "created_by_user_id": created_by_user_id,
            "created_by_name": created_by_name,
        }

        created = create_feed_record(payload)

        if not created:
            return ServiceResult(ok=False, message="新增打料紀錄失敗，Supabase 未回傳資料。")

        return ServiceResult(ok=True, message="打料紀錄已成功寫入。", data=created)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"寫入失敗：{exc}")


# ============================================================
# 送出回用料
# ============================================================

def submit_recycled_feed_record(
    recycled_material_id: str,
    feed_date: str,
    machine_code: str,
    operator_name: str,
    created_by_user_id: str | None = None,
    created_by_name: str | None = None,
) -> ServiceResult:
    if not recycled_material_id:
        return ServiceResult(ok=False, message="請選擇領用回用料。")

    if not feed_date:
        return ServiceResult(ok=False, message="請填寫日期。")

    if not machine_code:
        return ServiceResult(ok=False, message="請選擇乾燥塔。")

    if not operator_name:
        return ServiceResult(ok=False, message="請選擇或輸入填單人。")

    try:
        recycled = get_recycled_material_by_id(recycled_material_id)

        if not recycled:
            return ServiceResult(ok=False, message="找不到此回用料資料。")

        if recycled.get("is_used"):
            return ServiceResult(ok=False, message="此回用料已被領用，請重新整理資料。")

        if recycled.get("is_scrapped"):
            return ServiceResult(ok=False, message="此回用料已報廢，不能領用。")

        usage_status = str(recycled.get("usage_status") or "")

        if "在庫" not in usage_status:
            return ServiceResult(ok=False, message="此回用料目前不是在庫狀態，不能領用。")

        recycled_no = recycled.get("recycled_no") or ""
        supplier = recycled.get("supplier") or ""
        material_type = recycled.get("material_type") or ""
        weight_kg = _to_float(recycled.get("weight_kg"), 0)

        if supplier:
            material_name = f"[{supplier}] {material_type}"
        else:
            material_name = material_type or recycled_no

        payload = {
            "feed_type": "recycled",
            "batch_no": recycled_no,
            "feed_at": parse_feed_date_to_taipei_iso(feed_date),
            "machine_code": machine_code,
            "material_id": None,
            "recycled_material_id": recycled_material_id,
            "material_name": material_name,
            "material_source": "回用料",
            "supplier": supplier or None,
            "quantity_bags": None,
            "weight_kg": weight_kg,
            "bag_weight_kg": None,
            "operator_name": operator_name,
            "note": None,
            "created_by_user_id": created_by_user_id,
            "created_by_name": created_by_name,
        }

        created = create_feed_record(payload)

        if not created:
            return ServiceResult(ok=False, message="新增回用料紀錄失敗，Supabase 未回傳資料。")

        updated_recycled = mark_recycled_material_used(
            recycled_material_id=recycled_material_id,
            feed_record_id=created.get("id"),
        )

        if not updated_recycled:
            return ServiceResult(
                ok=False,
                message="回用料紀錄已寫入，但回用料狀態更新失敗，請檢查資料。",
                data=created,
            )

        return ServiceResult(ok=True, message="回用料紀錄已寫入，回用料狀態已更新。", data=created)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"寫入失敗：{exc}")
