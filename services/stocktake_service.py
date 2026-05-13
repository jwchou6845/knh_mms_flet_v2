# =====================================================
# KNH MMS v2
# File: services/stocktake_service.py
# File Revision: 2026-05-13-stocktake-service-r1
# Status: first implementation for inventory stocktake module
# Last Updated: 2026-05-13 Asia/Taipei
#
# Purpose:
# - 人工盤點功能服務層。
# - 負責建立盤點單、產生盤點明細、輸入實盤數、送出待審核、確認盤點並寫入 stock_adjustments。
#
# Major Changes in This Revision:
# - 新增盤點單建立流程，從 material_stock_view 取得啟用且納管原料。
# - 新增盤點明細差異計算：實盤包數 - 帳面包數。
# - 新增送出待審核、超級管理員確認、作廢盤點單流程。
# - 確認盤點時只針對差異不為 0 的項目寫入 stock_adjustments。
#
# Notes:
# - 所有時間處理使用 Asia/Taipei。
# - 第一版只處理新料 / 母粒，不處理回用料逐筆盤點。
# - 不直接覆蓋庫存；確認後透過 stock_adjustments 影響 material_stock_view。
# - stock_adjustments 第一版沿用 source / source_airtable_record_id 記錄盤點來源。
# =====================================================

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

from repositories.stocktake_repo import (
    create_inventory_count,
    create_inventory_count_items,
    create_stock_adjustment,
    get_inventory_count_by_id,
    get_inventory_count_item_by_id,
    get_inventory_count_items,
    get_inventory_counts,
    get_stocktake_material_stock_rows,
    update_inventory_count,
    update_inventory_count_item,
)


TAIPEI_TZ = ZoneInfo("Asia/Taipei")


@dataclass
class ServiceResult:
    ok: bool
    message: str = ""
    data: Any = None


# ============================================================
# Time helpers
# ============================================================

def now_taipei() -> datetime:
    return datetime.now(TAIPEI_TZ)


def today_taipei() -> date:
    return now_taipei().date()


def now_taipei_iso() -> str:
    return now_taipei().isoformat()


def parse_date_text(value: Any, default: date | None = None) -> date | None:
    if not value:
        return default

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    text = str(value).strip().replace("/", "-")

    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except Exception:
        return default


def format_date(value: Any) -> str:
    parsed = parse_date_text(value)
    if not parsed:
        return "-"
    return parsed.strftime("%Y/%m/%d")


def format_datetime(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"

    try:
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TAIPEI_TZ)
        return dt.astimezone(TAIPEI_TZ).strftime("%Y/%m/%d %H:%M")
    except Exception:
        return text[:16].replace("-", "/")


# ============================================================
# Generic helpers
# ============================================================

def clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value is None or value == "":
            return default
        return Decimal(str(value))
    except Exception:
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(Decimal(str(value)).to_integral_value(rounding=ROUND_HALF_UP))
    except Exception:
        return default


def decimal_to_float(value: Decimal | int | float | str | None) -> float:
    return float(to_decimal(value))


def is_aux_material(row: dict[str, Any]) -> bool:
    combined = " ".join(
        [
            clean_text(row.get("main_category")),
            clean_text(row.get("material_type")),
            clean_text(row.get("material_name")),
        ]
    )
    return "母粒" in combined or "輔助母粒" in combined


def count_type_label(value: Any) -> str:
    text = clean_text(value, "all")
    mapping = {
        "all": "全部",
        "new": "新料",
        "aux": "母粒",
    }
    return mapping.get(text, text)


def status_label(value: Any) -> str:
    text = clean_text(value, "draft")
    mapping = {
        "draft": "草稿",
        "submitted": "待審核",
        "confirmed": "已確認",
        "voided": "已作廢",
    }
    return mapping.get(text, text)


def validate_count_type(count_type: str) -> str:
    value = clean_text(count_type, "all")
    if value not in ["all", "new", "aux"]:
        return "all"
    return value


def generate_count_no() -> str:
    return f"STK-{now_taipei().strftime('%Y%m%d-%H%M%S')}"


# ============================================================
# Row normalizers
# ============================================================

def normalize_count_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "count_no": row.get("count_no") or "-",
        "count_date": format_date(row.get("count_date")),
        "count_date_raw": row.get("count_date"),
        "count_type": row.get("count_type") or "all",
        "count_type_label": count_type_label(row.get("count_type")),
        "status": row.get("status") or "draft",
        "status_label": status_label(row.get("status")),
        "note": row.get("note") or "",
        "created_by_name": row.get("created_by_name") or "-",
        "created_at": format_datetime(row.get("created_at")),
        "submitted_by_name": row.get("submitted_by_name") or "-",
        "submitted_at": format_datetime(row.get("submitted_at")) if row.get("submitted_at") else "-",
        "confirmed_by_name": row.get("confirmed_by_name") or "-",
        "confirmed_at": format_datetime(row.get("confirmed_at")) if row.get("confirmed_at") else "-",
        "voided_by_name": row.get("voided_by_name") or "-",
        "voided_at": format_datetime(row.get("voided_at")) if row.get("voided_at") else "-",
        "void_reason": row.get("void_reason") or "",
        "adjustment_batch_no": row.get("adjustment_batch_no") or "",
        "raw": row,
    }


def normalize_item_row(row: dict[str, Any]) -> dict[str, Any]:
    system_bags = to_decimal(row.get("system_stock_bags"))
    system_kg = to_decimal(row.get("system_stock_kg"))
    actual_bags_raw = row.get("actual_stock_bags")
    actual_kg_raw = row.get("actual_stock_kg")
    difference_bags = to_decimal(row.get("difference_bags"))
    difference_kg = to_decimal(row.get("difference_kg"))

    has_actual = actual_bags_raw not in [None, ""]

    return {
        "id": row.get("id"),
        "inventory_count_id": row.get("inventory_count_id"),
        "material_id": row.get("material_id"),
        "material_name": row.get("material_name") or "-",
        "main_category": row.get("main_category") or "",
        "material_type": row.get("material_type") or "",
        "supplier": row.get("supplier") or "",
        "bag_weight_kg": decimal_to_float(row.get("bag_weight_kg")),
        "system_stock_bags": decimal_to_float(system_bags),
        "system_stock_kg": decimal_to_float(system_kg),
        "actual_stock_bags": decimal_to_float(actual_bags_raw) if has_actual else None,
        "actual_stock_kg": decimal_to_float(actual_kg_raw) if actual_kg_raw not in [None, ""] else None,
        "difference_bags": decimal_to_float(difference_bags),
        "difference_kg": decimal_to_float(difference_kg),
        "has_actual": has_actual,
        "difference_label": build_difference_label(difference_bags),
        "note": row.get("note") or "",
        "stock_adjustment_id": row.get("stock_adjustment_id"),
        "raw": row,
    }


def build_difference_label(difference_bags: Decimal) -> str:
    if difference_bags == 0:
        return "無差異"
    if difference_bags > 0:
        return f"盤盈 +{difference_bags:g} 包"
    return f"盤虧 {difference_bags:g} 包"


def summarize_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(items)
    entered = 0
    diff_count = 0
    plus_count = 0
    minus_count = 0
    total_diff_bags = Decimal("0")
    total_diff_kg = Decimal("0")

    for item in items:
        normalized = normalize_item_row(item)
        if normalized["has_actual"]:
            entered += 1

        diff_bags = to_decimal(item.get("difference_bags"))
        diff_kg = to_decimal(item.get("difference_kg"))

        if diff_bags != 0 or diff_kg != 0:
            diff_count += 1
            total_diff_bags += diff_bags
            total_diff_kg += diff_kg
            if diff_bags > 0:
                plus_count += 1
            elif diff_bags < 0:
                minus_count += 1

    return {
        "total_items": total,
        "entered_items": entered,
        "not_entered_items": max(0, total - entered),
        "difference_items": diff_count,
        "plus_items": plus_count,
        "minus_items": minus_count,
        "total_difference_bags": decimal_to_float(total_diff_bags),
        "total_difference_kg": decimal_to_float(total_diff_kg),
    }


# ============================================================
# Build initial count items
# ============================================================

def filter_stock_rows_by_count_type(rows: list[dict[str, Any]], count_type: str) -> list[dict[str, Any]]:
    count_type = validate_count_type(count_type)

    if count_type == "all":
        return rows

    result: list[dict[str, Any]] = []
    for row in rows:
        aux = is_aux_material(row)
        if count_type == "aux" and aux:
            result.append(row)
        elif count_type == "new" and not aux:
            result.append(row)

    return result


def build_count_item_payloads(count_id: str, stock_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []

    for row in stock_rows:
        material_id = clean_text(row.get("material_id"))
        material_name = clean_text(row.get("material_name"))
        if not material_id or not material_name:
            continue

        bag_weight = to_decimal(row.get("bag_weight_kg"))
        system_bags = to_decimal(row.get("current_stock_bags"))
        system_kg = to_decimal(row.get("current_stock_kg"))

        payloads.append(
            {
                "inventory_count_id": count_id,
                "material_id": material_id,
                "material_name": material_name,
                "main_category": row.get("main_category"),
                "material_type": row.get("material_type"),
                "supplier": row.get("supplier"),
                "bag_weight_kg": decimal_to_float(bag_weight),
                "system_stock_bags": decimal_to_float(system_bags),
                "system_stock_kg": decimal_to_float(system_kg),
                "actual_stock_bags": None,
                "actual_stock_kg": None,
                "difference_bags": 0,
                "difference_kg": 0,
                "note": None,
            }
        )

    return payloads


# ============================================================
# Public APIs
# ============================================================

def load_inventory_counts(limit: int = 50) -> ServiceResult:
    try:
        rows = get_inventory_counts(limit=limit)
        normalized = [normalize_count_row(row) for row in rows]

        summary = {
            "draft": 0,
            "submitted": 0,
            "confirmed": 0,
            "voided": 0,
        }
        for row in rows:
            status = clean_text(row.get("status"), "draft")
            if status in summary:
                summary[status] += 1

        return ServiceResult(
            ok=True,
            data={
                "counts": normalized,
                "summary": summary,
            },
        )
    except Exception as exc:
        return ServiceResult(ok=False, message=f"讀取盤點單失敗：{exc}", data={"counts": [], "summary": {}})


def load_inventory_count_detail(count_id: str) -> ServiceResult:
    try:
        count = get_inventory_count_by_id(count_id)
        if not count:
            return ServiceResult(ok=False, message="找不到盤點單。")

        items = get_inventory_count_items(count_id)

        return ServiceResult(
            ok=True,
            data={
                "count": normalize_count_row(count),
                "items": [normalize_item_row(item) for item in items],
                "summary": summarize_items(items),
            },
        )
    except Exception as exc:
        return ServiceResult(ok=False, message=f"讀取盤點明細失敗：{exc}")


def create_new_inventory_count(
    count_date: Any,
    count_type: str = "all",
    note: str | None = None,
    created_by_user_id: str | None = None,
    created_by_name: str | None = None,
) -> ServiceResult:
    try:
        parsed_date = parse_date_text(count_date, today_taipei())
        if not parsed_date:
            return ServiceResult(ok=False, message="盤點日期格式錯誤。")

        safe_count_type = validate_count_type(count_type)
        stock_rows = get_stocktake_material_stock_rows()
        stock_rows = filter_stock_rows_by_count_type(stock_rows, safe_count_type)

        if not stock_rows:
            return ServiceResult(ok=False, message="目前沒有符合條件的啟用且納管原料可建立盤點單。")

        count_no = generate_count_no()

        count_payload = {
            "count_no": count_no,
            "count_date": parsed_date.isoformat(),
            "count_type": safe_count_type,
            "status": "draft",
            "note": clean_text(note) or None,
            "created_by_user_id": created_by_user_id,
            "created_by_name": created_by_name,
        }

        count = create_inventory_count(count_payload)
        if not count:
            return ServiceResult(ok=False, message="建立盤點單失敗，Supabase 未回傳資料。")

        item_payloads = build_count_item_payloads(str(count.get("id")), stock_rows)
        created_items = create_inventory_count_items(item_payloads)

        if len(created_items) != len(item_payloads):
            return ServiceResult(
                ok=False,
                message="盤點單已建立，但盤點明細建立不完整，請檢查資料。",
                data={"count": normalize_count_row(count), "items": created_items},
            )

        return ServiceResult(
            ok=True,
            message=f"盤點單 {count_no} 已建立。",
            data={
                "count": normalize_count_row(count),
                "items": [normalize_item_row(item) for item in created_items],
                "summary": summarize_items(created_items),
            },
        )

    except Exception as exc:
        return ServiceResult(ok=False, message=f"建立盤點單失敗：{exc}")


def update_count_item_actual_stock(
    item_id: str,
    actual_stock_bags: Any,
    note: str | None = None,
) -> ServiceResult:
    try:
        item = get_inventory_count_item_by_id(item_id)
        if not item:
            return ServiceResult(ok=False, message="找不到盤點明細。")

        count = get_inventory_count_by_id(str(item.get("inventory_count_id")))
        if not count:
            return ServiceResult(ok=False, message="找不到盤點單。")

        if clean_text(count.get("status"), "draft") != "draft":
            return ServiceResult(ok=False, message="只有草稿狀態可以修改盤點數量。")

        actual_bags = to_decimal(actual_stock_bags, Decimal("-1"))
        if actual_bags < 0:
            return ServiceResult(ok=False, message="實盤包數不可小於 0。")

        # 第一版以整包盤點為主；stock_adjustments.quantity_bags 是 integer。
        if actual_bags != actual_bags.to_integral_value():
            return ServiceResult(ok=False, message="第一版實盤包數請輸入整數包。")

        bag_weight = to_decimal(item.get("bag_weight_kg"))
        system_bags = to_decimal(item.get("system_stock_bags"))
        system_kg = to_decimal(item.get("system_stock_kg"))

        actual_kg = actual_bags * bag_weight
        difference_bags = actual_bags - system_bags
        difference_kg = actual_kg - system_kg

        payload = {
            "actual_stock_bags": decimal_to_float(actual_bags),
            "actual_stock_kg": decimal_to_float(actual_kg),
            "difference_bags": decimal_to_float(difference_bags),
            "difference_kg": decimal_to_float(difference_kg),
            "note": clean_text(note) or None,
        }

        updated = update_inventory_count_item(item_id, payload)
        if not updated:
            return ServiceResult(ok=False, message="更新盤點明細失敗，Supabase 未回傳資料。")

        return ServiceResult(
            ok=True,
            message="實盤數已更新。",
            data={"item": normalize_item_row(updated)},
        )

    except Exception as exc:
        return ServiceResult(ok=False, message=f"更新實盤數失敗：{exc}")


def submit_inventory_count(
    count_id: str,
    submitted_by_user_id: str | None = None,
    submitted_by_name: str | None = None,
) -> ServiceResult:
    try:
        count = get_inventory_count_by_id(count_id)
        if not count:
            return ServiceResult(ok=False, message="找不到盤點單。")

        if clean_text(count.get("status"), "draft") != "draft":
            return ServiceResult(ok=False, message="只有草稿盤點單可以送出待審核。")

        items = get_inventory_count_items(count_id)
        if not items:
            return ServiceResult(ok=False, message="盤點單沒有明細，不能送出。")

        missing = [item for item in items if item.get("actual_stock_bags") in [None, ""]]
        if missing:
            return ServiceResult(ok=False, message=f"尚有 {len(missing)} 筆原料未輸入實盤包數。")

        updated = update_inventory_count(
            count_id,
            {
                "status": "submitted",
                "submitted_by_user_id": submitted_by_user_id,
                "submitted_by_name": submitted_by_name,
                "submitted_at": now_taipei_iso(),
            },
        )

        if not updated:
            return ServiceResult(ok=False, message="送出盤點單失敗，Supabase 未回傳資料。")

        return ServiceResult(
            ok=True,
            message="盤點單已送出待審核。",
            data={"count": normalize_count_row(updated), "summary": summarize_items(items)},
        )

    except Exception as exc:
        return ServiceResult(ok=False, message=f"送出盤點單失敗：{exc}")


def confirm_inventory_count(
    count_id: str,
    confirmed_by_user_id: str | None = None,
    confirmed_by_name: str | None = None,
) -> ServiceResult:
    try:
        count = get_inventory_count_by_id(count_id)
        if not count:
            return ServiceResult(ok=False, message="找不到盤點單。")

        if clean_text(count.get("status")) != "submitted":
            return ServiceResult(ok=False, message="只有待審核盤點單可以確認。")

        items = get_inventory_count_items(count_id)
        if not items:
            return ServiceResult(ok=False, message="盤點單沒有明細，不能確認。")

        missing = [item for item in items if item.get("actual_stock_bags") in [None, ""]]
        if missing:
            return ServiceResult(ok=False, message=f"尚有 {len(missing)} 筆原料未輸入實盤包數。")

        count_no = clean_text(count.get("count_no"), "盤點單")
        adjustment_batch_no = f"ADJ-{now_taipei().strftime('%Y%m%d-%H%M%S')}"
        created_adjustments: list[dict[str, Any]] = []

        for item in items:
            diff_bags = to_decimal(item.get("difference_bags"))
            diff_kg = to_decimal(item.get("difference_kg"))

            if diff_bags == 0 and diff_kg == 0:
                continue

            # stock_adjustments.quantity_bags 為 integer，第一版只允許整數包數盤點。
            quantity_bags = int(diff_bags.to_integral_value())

            item_note = clean_text(item.get("note"))
            note_parts = [
                f"盤點單：{count_no}",
                f"原料：{clean_text(item.get('material_name'), '-')}",
                f"帳面：{to_decimal(item.get('system_stock_bags')):g} 包",
                f"實盤：{to_decimal(item.get('actual_stock_bags')):g} 包",
                f"差異：{diff_bags:g} 包",
            ]
            if item_note:
                note_parts.append(f"明細備註：{item_note}")

            adjustment_payload = {
                "material_id": item.get("material_id"),
                "adjustment_type": "stocktake",
                "adjustment_date": count.get("count_date"),
                "quantity_bags": quantity_bags,
                "quantity_kg": decimal_to_float(diff_kg),
                "reason": "人工盤點調整",
                "note": "；".join(note_parts),
                "created_by_user_id": confirmed_by_user_id,
                "created_by_name": confirmed_by_name,
                "source": "inventory_count",
                "source_airtable_record_id": str(item.get("id")),
            }

            adjustment = create_stock_adjustment(adjustment_payload)
            if not adjustment:
                return ServiceResult(
                    ok=False,
                    message=f"盤點調整寫入失敗：{item.get('material_name') or '-'}。已建立的調整需人工檢查。",
                    data={"created_adjustments": created_adjustments},
                )

            created_adjustments.append(adjustment)
            update_inventory_count_item(
                str(item.get("id")),
                {"stock_adjustment_id": adjustment.get("id")},
            )

        updated = update_inventory_count(
            count_id,
            {
                "status": "confirmed",
                "confirmed_by_user_id": confirmed_by_user_id,
                "confirmed_by_name": confirmed_by_name,
                "confirmed_at": now_taipei_iso(),
                "adjustment_batch_no": adjustment_batch_no,
            },
        )

        if not updated:
            return ServiceResult(ok=False, message="庫存調整已寫入，但盤點單確認狀態更新失敗，請人工檢查。")

        return ServiceResult(
            ok=True,
            message=f"盤點單已確認，已建立 {len(created_adjustments)} 筆庫存調整。",
            data={
                "count": normalize_count_row(updated),
                "created_adjustments": created_adjustments,
                "summary": summarize_items(items),
            },
        )

    except Exception as exc:
        return ServiceResult(ok=False, message=f"確認盤點單失敗：{exc}")


def void_inventory_count(
    count_id: str,
    void_reason: str,
    voided_by_user_id: str | None = None,
    voided_by_name: str | None = None,
) -> ServiceResult:
    try:
        reason = clean_text(void_reason)
        if not reason:
            return ServiceResult(ok=False, message="請輸入作廢原因。")

        count = get_inventory_count_by_id(count_id)
        if not count:
            return ServiceResult(ok=False, message="找不到盤點單。")

        status = clean_text(count.get("status"), "draft")
        if status == "confirmed":
            return ServiceResult(ok=False, message="已確認盤點單已寫入庫存調整，不可直接作廢。")

        if status == "voided":
            return ServiceResult(ok=False, message="此盤點單已作廢。")

        updated = update_inventory_count(
            count_id,
            {
                "status": "voided",
                "voided_by_user_id": voided_by_user_id,
                "voided_by_name": voided_by_name,
                "voided_at": now_taipei_iso(),
                "void_reason": reason,
            },
        )

        if not updated:
            return ServiceResult(ok=False, message="作廢盤點單失敗，Supabase 未回傳資料。")

        return ServiceResult(ok=True, message="盤點單已作廢。", data={"count": normalize_count_row(updated)})

    except Exception as exc:
        return ServiceResult(ok=False, message=f"作廢盤點單失敗：{exc}")
