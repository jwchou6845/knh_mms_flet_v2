from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
import csv
import re
from urllib.parse import quote
from zoneinfo import ZoneInfo

from repositories.reports_repo import (
    get_active_maintenance_items,
    get_available_recycled_material_rows,
    get_feed_records_between,
    get_handover_items_between,
    get_maintenance_records,
    get_maintenance_records_between,
    get_material_stock_rows,
    get_monthly_usage_rows,
    get_open_handover_items,
    get_purchase_records_between,
    get_purchase_records_for_options,
    get_feed_records_for_options,
    get_user_rows,
)


TAIPEI_TZ = ZoneInfo("Asia/Taipei")
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_EXPORT_DIR = "exports"
DEFAULT_EXPORT_RETENTION_DAYS = 14


QUICK_REPORTS = [
    "本月用料摘要",
    "上月用料摘要",
    "指定月份用料摘要",
    "目前低水位清單",
    "目前庫存總表",
    "本月入庫紀錄",
    "保養逾期清單",
    "未完成交接待辦",
]

ADVANCED_DATA_TYPES = [
    "打料紀錄",
    "入庫紀錄",
    "保養紀錄",
    "交接紀錄",
]


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


def month_start(target: date) -> date:
    return target.replace(day=1)


def add_months(target: date, months: int) -> date:
    year = target.year + ((target.month - 1 + months) // 12)
    month = ((target.month - 1 + months) % 12) + 1
    return date(year, month, 1)


def parse_date(value: Any, default: date | None = None) -> date | None:
    if not value:
        return default

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    text = str(value).strip().replace("/", "-")

    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except Exception:
        return default


def parse_month(value: Any, default: date | None = None) -> date:
    fallback = default or month_start(today_taipei())
    text = str(value or "").strip().replace("/", "-")

    try:
        if len(text) == 7:
            return datetime.strptime(text + "-01", "%Y-%m-%d").date()
        return datetime.strptime(text[:10], "%Y-%m-%d").date().replace(day=1)
    except Exception:
        return fallback


def date_start_iso(value: date) -> str:
    return datetime.combine(value, time.min, tzinfo=TAIPEI_TZ).isoformat()


def date_end_iso_exclusive(value: date) -> str:
    return datetime.combine(value, time.min, tzinfo=TAIPEI_TZ).isoformat()


def format_date(value: Any) -> str:
    parsed = parse_date(value)

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


def first_value(row: dict[str, Any], keys: list[str], default: Any = "") -> Any:
    for key in keys:
        value = row.get(key)
        if value not in [None, ""]:
            return value
    return default


def purchase_quantity_value(row: dict[str, Any]) -> Any:
    """
    入庫紀錄的數量欄位。

    Supabase 的 purchase_records 正式欄位目前是：
    - quantity_bags：進貨包數
    - quantity_kg：進貨重量

    舊版 reports_service.py 只抓 qty / quantity / package_qty / weight_kg，
    因此正式資料只有 quantity_bags 時，報表會顯示 0。
    這裡優先顯示包數；若沒有包數，再退回重量或舊欄位名稱。
    """
    if row.get("quantity_bags") not in [None, ""]:
        return row.get("quantity_bags")

    if row.get("quantity_kg") not in [None, ""]:
        return row.get("quantity_kg")

    return first_value(
        row,
        ["qty", "quantity", "package_qty", "weight_kg", "weight"],
        0,
    )


def purchase_quantity_unit(row: dict[str, Any]) -> str:
    """
    配合 purchase_quantity_value() 顯示單位。
    若取用包數欄位，單位固定為「包」；若只剩重量欄位，單位為 KG。
    """
    unit = clean_text(row.get("unit"))
    if unit:
        return unit

    if row.get("quantity_bags") not in [None, ""]:
        return "包"

    if row.get("quantity_kg") not in [None, ""] or row.get("weight_kg") not in [None, ""]:
        return "KG"

    return "包"


def pick_number(row: dict[str, Any], keys: list[str], default: float = 0.0) -> float:
    """
    用於欄位名稱仍可能調整的庫存數字欄位。
    依序尋找第一個存在且非空值的欄位。
    """
    for key in keys:
        if key in row and row.get(key) not in [None, ""]:
            return to_float(row.get(key), default)
    return default


def classify_material_category(row: dict[str, Any]) -> str:
    """
    將 material_stock_view 的品項拆成「新料」或「母粒」。
    不再顯示模糊的「新料/母粒」。
    """
    combined = " ".join(
        [
            clean_text(row.get("category")),
            clean_text(row.get("material_category")),
            clean_text(row.get("material_type")),
            clean_text(row.get("main_category")),
            clean_text(row.get("material_name")),
            clean_text(row.get("display_name")),
        ]
    )

    if "母粒" in combined or "助劑" in combined or "aux" in combined.lower():
        return "母粒"

    return "新料"


def normalize_material_family(value: Any) -> str:
    """
    報表篩選用的原料種類。
    例如 PET-南紡、[南紡] PET 都歸類為 PET。
    """
    text = clean_text(value).upper().replace(" ", "").replace("-", "")

    if not text:
        return ""

    if "PET308A" in text or "308A" in text:
        return "PET308A"

    if "RPET" in text:
        return "RPET"

    if "PA6" in text:
        return "PA6"

    if "PET" in text:
        return "PET"

    if "PP" in text or "台塑" in text:
        return "PP"

    if "母粒" in text or "輔助" in text or "MASTER" in text:
        return "母粒"

    return clean_text(value)



def contains_filter(value: Any, keyword: str) -> bool:
    keyword = clean_text(keyword)
    if not keyword or keyword == "全部":
        return True
    return keyword in clean_text(value)


def equal_filter(value: Any, expected: str) -> bool:
    expected = clean_text(expected)
    if not expected or expected == "全部":
        return True
    return clean_text(value) == expected


def build_result(
    title: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    summary_text: str = "",
) -> ServiceResult:
    return ServiceResult(
        ok=True,
        data={
            "title": title,
            "columns": columns,
            "rows": rows,
            "count": len(rows),
            "summary_text": summary_text,
        },
    )


# ============================================================
# Quick reports
# ============================================================

def normalize_usage_display_name(row: dict[str, Any]) -> str:
    """
    統一月用量報表名稱，避免同一個品項因不同資料來源而重複出現。

    常見來源差異：
    - PET-南紡
    - [南紡] PET
    - PET308A-南紡
    - [南紡308A] PET-308A
    - 輔助母粒-南亞
    """
    category = clean_text(row.get("category"))
    display_name = clean_text(row.get("display_name"))
    material_name = clean_text(row.get("material_name"))
    supplier = clean_text(row.get("supplier"))

    if category == "母粒":
        return "母粒"

    name = display_name or material_name or ""

    # 解析 [南紡] PET / [南紡308A] PET-308A 類格式
    if name.startswith("[") and "]" in name:
        bracket = name[1:name.find("]")].strip()
        rest = name[name.find("]") + 1 :].strip()

        if bracket:
            supplier = bracket

        if rest:
            material_name = rest
            name = rest

    compact = f"{name} {material_name} {supplier}".upper().replace(" ", "").replace("-", "")

    supplier_clean = supplier

    if "南紡" in supplier_clean:
        supplier_clean = "南紡"
    elif "南亞" in supplier_clean:
        supplier_clean = "南亞"
    elif "集盛" in supplier_clean:
        supplier_clean = "集盛"
    elif "力鵬" in supplier_clean:
        supplier_clean = "力鵬"
    elif "遠東" in supplier_clean:
        supplier_clean = "遠東"
    elif "中國岳化" in supplier_clean:
        supplier_clean = "中國岳化"
    elif "中國儀征" in supplier_clean:
        supplier_clean = "中國儀征"

    if "308A" in compact:
        material_clean = "PET308A"
    elif "RPET" in compact:
        material_clean = "RPET"
    elif "PA6" in compact:
        material_clean = "PA6"
    elif "PET" in compact:
        material_clean = "PET"
    else:
        cleaned = (
            name.replace("PET-308A", "PET308A")
            .replace("PET 308A", "PET308A")
            .strip()
        )
        return cleaned or "未知原料"

    if supplier_clean:
        return f"{material_clean}-{supplier_clean}"

    for known_supplier in ["南紡", "南亞", "集盛", "力鵬", "遠東", "中國岳化", "中國儀征"]:
        if known_supplier in name:
            return f"{material_clean}-{known_supplier}"

    return material_clean

def quick_month_usage_report(month_value: Any) -> ServiceResult:
    target_month = parse_month(month_value)
    next_month = add_months(target_month, 1)

    rows = get_monthly_usage_rows(
        target_month.isoformat(),
        next_month.isoformat(),
    )

    bucket: dict[tuple[str, str], float] = {}

    for row in rows:
        category = clean_text(row.get("category"), "未分類")
        name = normalize_usage_display_name(row)
        weight = to_float(row.get("weight_kg"), 0)

        key = (category, name)
        bucket[key] = bucket.get(key, 0.0) + weight

    category_rank = {
        "新料": 1,
        "母粒": 2,
        "回用料": 3,
    }

    output_rows = [
        {
            "月份": target_month.strftime("%Y-%m"),
            "類別": category,
            "名稱": name,
            "數量": round(weight, 2),
            "單位": "KG",
        }
        for (category, name), weight in sorted(
            bucket.items(),
            key=lambda x: (category_rank.get(x[0][0], 99), x[0][1]),
        )
    ]

    return build_result(
        title=f"{target_month.strftime('%Y-%m')} 用料摘要",
        columns=["月份", "類別", "名稱", "數量", "單位"],
        rows=output_rows,
        summary_text=f"{target_month.strftime('%Y-%m')} 共 {len(output_rows)} 個用料項目。",
    )


def quick_low_stock_report() -> ServiceResult:
    rows = get_material_stock_rows()

    output_rows = []

    for row in rows:
        is_low = bool(row.get("is_low_stock", False))
        current_qty = pick_number(
            row,
            ["current_stock_bags", "current_qty", "stock_qty", "current_stock", "qty"],
            0,
        )
        safe_qty = pick_number(
            row,
            [
                "safety_stock_bags",
                "safe_stock_bags",
                "low_stock_threshold_bags",
                "low_stock_bags",
                "min_stock_bags",
                "low_stock_threshold",
                "safe_stock",
                "safety_stock",
                "min_qty",
            ],
            0,
        )

        if not is_low and not (safe_qty and current_qty <= safe_qty):
            continue

        output_rows.append(
            {
                "原料名稱": first_value(row, ["material_name", "name"], "-"),
                "供應商": first_value(row, ["supplier"], "-"),
                "目前庫存": current_qty,
                "安全庫存": safe_qty,
                "單位": "包",
            }
        )

    return build_result(
        title="目前低水位清單",
        columns=["原料名稱", "供應商", "目前庫存", "安全庫存", "單位"],
        rows=output_rows,
        summary_text=f"目前共有 {len(output_rows)} 筆低水位項目。",
    )


def quick_stock_report() -> ServiceResult:
    material_rows = get_material_stock_rows()
    recycled_rows = get_available_recycled_material_rows()

    output_rows = []

    for row in material_rows:
        output_rows.append(
            {
                "資料類型": classify_material_category(row),
                "名稱": first_value(row, ["material_name", "name"], "-"),
                "供應商": first_value(row, ["supplier"], "-"),
                "數量": pick_number(row, ["current_stock_bags", "current_qty", "stock_qty", "current_stock", "qty"], 0),
                "單位": "包",
            }
        )

    recycled_summary: dict[tuple[str, str], float] = {}

    for row in recycled_rows:
        supplier = clean_text(first_value(row, ["supplier"], "未知供應商"))
        material_type = clean_text(first_value(row, ["material_type", "material_name", "name"], "未知種類"))
        weight = to_float(first_value(row, ["weight_kg", "weight", "qty"], 0))
        key = (supplier, material_type)
        recycled_summary[key] = recycled_summary.get(key, 0.0) + weight

    for (supplier, material_type), weight in sorted(recycled_summary.items(), key=lambda x: (x[0][0], x[0][1])):
        output_rows.append(
            {
                "資料類型": "回用料",
                "名稱": material_type,
                "供應商": supplier,
                "數量": round(weight, 2),
                "單位": "KG",
            }
        )

    return build_result(
        title="目前庫存總表",
        columns=["資料類型", "名稱", "供應商", "數量", "單位"],
        rows=output_rows,
        summary_text=f"目前庫存總表共 {len(output_rows)} 筆。",
    )


def quick_current_month_purchase_report() -> ServiceResult:
    start = month_start(today_taipei())
    end = add_months(start, 1)

    rows = get_purchase_records_between(
        start.isoformat(),
        end.isoformat(),
    )

    output_rows = []
    for row in rows:
        output_rows.append(
            {
                "日期": format_date(first_value(row, ["purchase_date", "created_at"])),
                "原料名稱": first_value(row, ["material_name", "name"], "-"),
                "供應商": first_value(row, ["supplier"], "-"),
                "數量": purchase_quantity_value(row),
                "單位": purchase_quantity_unit(row),
            }
        )

    return build_result(
        title="本月入庫紀錄",
        columns=["日期", "原料名稱", "供應商", "數量", "單位"],
        rows=output_rows,
        summary_text=f"本月入庫紀錄共 {len(output_rows)} 筆。",
    )


def display_maintenance_item_name(item: dict[str, Any]) -> str:
    item_name = clean_text(item.get("item_name"), "-")
    maintenance_type = clean_text(item.get("maintenance_type"))
    sub_category = clean_text(item.get("sub_category"))

    if maintenance_type == "耗材更換" and sub_category:
        return f"{sub_category}-{item_name}"

    return item_name


def latest_record_map(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    for record in records:
        item_id = record.get("maintenance_item_id")

        if item_id and item_id not in result:
            result[item_id] = record

    return result


def quick_overdue_maintenance_report() -> ServiceResult:
    items = get_active_maintenance_items()
    records = get_maintenance_records(limit=1000)
    record_map = latest_record_map(records)
    today = today_taipei()

    output_rows = []

    for item in items:
        item_id = item.get("id")
        latest = record_map.get(item_id)

        last_date = parse_date(latest.get("executed_date")) if latest else None
        cycle_days = to_int(item.get("cycle_days"), 30)
        next_date = None

        if last_date:
            next_date = last_date.fromordinal(last_date.toordinal() + cycle_days)

        if not next_date:
            output_rows.append(
                {
                    "狀態": "未建立",
                    "項目": display_maintenance_item_name(item),
                    "類型": item.get("maintenance_type") or "-",
                    "區域": item.get("machine_area") or "-",
                    "下次日期": "-",
                }
            )
            continue

        if next_date < today:
            overdue_days = (today - next_date).days
            output_rows.append(
                {
                    "狀態": f"逾期 {overdue_days} 天",
                    "項目": display_maintenance_item_name(item),
                    "類型": item.get("maintenance_type") or "-",
                    "區域": item.get("machine_area") or "-",
                    "下次日期": next_date.strftime("%Y/%m/%d"),
                }
            )

    return build_result(
        title="保養逾期清單",
        columns=["狀態", "項目", "類型", "區域", "下次日期"],
        rows=output_rows,
        summary_text=f"目前共有 {len(output_rows)} 筆保養逾期或未建立項目。",
    )


def quick_open_handover_report() -> ServiceResult:
    rows = get_open_handover_items()

    output_rows = []
    for row in rows:
        record = row.get("handover_records") or {}
        output_rows.append(
            {
                "日期": format_date(record.get("handover_date")),
                "班別": record.get("shift") or "-",
                "類型": row.get("item_type") or "-",
                "嚴重度": row.get("severity") or "-",
                "內容": row.get("content") or "-",
                "填單人": record.get("sender_name") or "-",
                "接班人": record.get("receiver_name") or "-",
            }
        )

    return build_result(
        title="未完成交接待辦",
        columns=["日期", "班別", "類型", "嚴重度", "內容", "填單人", "接班人"],
        rows=output_rows,
        summary_text=f"目前共有 {len(output_rows)} 筆未完成交接項目。",
    )


def run_quick_report(
    report_name: str,
    month_value: Any = None,
) -> ServiceResult:
    try:
        report_name = clean_text(report_name)

        if report_name == "本月用料摘要":
            return quick_month_usage_report(month_start(today_taipei()))

        if report_name == "上月用料摘要":
            return quick_month_usage_report(add_months(month_start(today_taipei()), -1))

        if report_name == "指定月份用料摘要":
            return quick_month_usage_report(month_value or month_start(today_taipei()))

        if report_name == "目前低水位清單":
            return quick_low_stock_report()

        if report_name == "目前庫存總表":
            return quick_stock_report()

        if report_name == "本月入庫紀錄":
            return quick_current_month_purchase_report()

        if report_name == "保養逾期清單":
            return quick_overdue_maintenance_report()

        if report_name == "未完成交接待辦":
            return quick_open_handover_report()

        return ServiceResult(ok=False, message=f"未知快速報表：{report_name}")

    except Exception as exc:
        return ServiceResult(ok=False, message=f"快速報表產生失敗：{exc}")


# ============================================================
# Advanced filters
# ============================================================

def filter_common_rows(
    rows: list[dict[str, Any]],
    category: str = "全部",
    material_name: str = "",
    supplier: str = "全部",
    machine: str = "全部",
    user_name: str = "全部",
) -> list[dict[str, Any]]:
    result = []

    for row in rows:
        category_value = first_value(row, ["category", "material_category", "feed_type", "item_type", "maintenance_type"], "")
        material_value = first_value(row, ["material_name", "display_name", "name", "content"], "")
        supplier_value = first_value(row, ["supplier"], "")
        machine_value = first_value(row, ["machine", "tower", "tower_code", "machine_area", "shift"], "")
        user_value = first_value(row, ["created_by_name", "operator_name", "executed_by", "completed_by_name", "sender_name", "receiver_name"], "")

        if not equal_filter(category_value, category):
            continue

        if clean_text(material_name) and clean_text(material_name) != "全部":
            query_family = normalize_material_family(material_name)
            row_family = normalize_material_family(material_value)
            if query_family and row_family:
                if query_family != row_family and not contains_filter(material_value, material_name):
                    continue
            elif not contains_filter(material_value, material_name):
                continue

        if not equal_filter(supplier_value, supplier):
            continue

        if not equal_filter(machine_value, machine):
            continue

        if not contains_filter(user_value, user_name if user_name != "全部" else ""):
            continue

        result.append(row)

    return result


def build_feed_result(rows: list[dict[str, Any]]) -> ServiceResult:
    output = []

    for row in rows:
        output.append(
            {
                "日期": format_datetime(row.get("feed_at")),
                "類別": first_value(row, ["category", "feed_type", "material_category"], "-"),
                "原料名稱": first_value(row, ["display_name", "material_name", "recycled_no"], "-"),
                "供應商": first_value(row, ["supplier"], "-"),
                "機台/塔別": first_value(row, ["tower_code", "tower", "machine"], "-"),
                "數量": first_value(row, ["weight_kg", "qty", "quantity"], 0),
                "人員": first_value(row, ["created_by_name", "operator_name"], "-"),
            }
        )

    return build_result(
        title="打料紀錄查詢",
        columns=["日期", "類別", "原料名稱", "供應商", "機台/塔別", "數量", "人員"],
        rows=output,
        summary_text=f"查詢到 {len(output)} 筆打料紀錄。",
    )


def build_purchase_result(rows: list[dict[str, Any]]) -> ServiceResult:
    output = []

    for row in rows:
        output.append(
            {
                "日期": format_date(first_value(row, ["purchase_date", "created_at"])),
                "類別": first_value(row, ["category", "material_category"], "-"),
                "原料名稱": first_value(row, ["material_name", "name"], "-"),
                "供應商": first_value(row, ["supplier"], "-"),
                "數量": purchase_quantity_value(row),
                "單位": purchase_quantity_unit(row),
                "人員": first_value(row, ["created_by_name", "operator_name"], "-"),
            }
        )

    return build_result(
        title="入庫紀錄查詢",
        columns=["日期", "類別", "原料名稱", "供應商", "數量", "單位", "人員"],
        rows=output,
        summary_text=f"查詢到 {len(output)} 筆入庫紀錄。",
    )


def build_maintenance_result(rows: list[dict[str, Any]]) -> ServiceResult:
    output = []

    for row in rows:
        item = row.get("maintenance_items") or {}
        output.append(
            {
                "日期": format_date(row.get("executed_date")),
                "類別": item.get("maintenance_type") or row.get("maintenance_type") or "-",
                "項目": display_maintenance_item_name(item) if item else row.get("item_name") or "-",
                "機台/區域": item.get("machine_area") or row.get("machine_area") or "-",
                "結果": row.get("result") or "-",
                "人員": row.get("executed_by") or row.get("created_by_name") or "-",
            }
        )

    return build_result(
        title="保養紀錄查詢",
        columns=["日期", "類別", "項目", "機台/區域", "結果", "人員"],
        rows=output,
        summary_text=f"查詢到 {len(output)} 筆保養紀錄。",
    )


def build_handover_result(rows: list[dict[str, Any]]) -> ServiceResult:
    output = []

    for row in rows:
        record = row.get("handover_records") or {}
        output.append(
            {
                "日期": format_date(record.get("handover_date")),
                "班別": record.get("shift") or "-",
                "類型": row.get("item_type") or "-",
                "嚴重度": row.get("severity") or "-",
                "內容": row.get("content") or "-",
                "填單人": record.get("sender_name") or "-",
                "接班人": record.get("receiver_name") or "-",
            }
        )

    return build_result(
        title="交接紀錄查詢",
        columns=["日期", "班別", "類型", "嚴重度", "內容", "填單人", "接班人"],
        rows=output,
        summary_text=f"查詢到 {len(output)} 筆交接項目。",
    )


def run_advanced_query(
    data_type: str,
    start_date: Any,
    end_date: Any,
    category: str = "全部",
    material_name: str = "",
    supplier: str = "全部",
    machine: str = "全部",
    user_name: str = "全部",
) -> ServiceResult:
    try:
        data_type = clean_text(data_type)

        start = parse_date(start_date, month_start(today_taipei())) or month_start(today_taipei())
        end = parse_date(end_date, today_taipei()) or today_taipei()

        # UI 使用日期迄包含當日，因此查詢上要 +1 天作 exclusive end。
        end_exclusive = date.fromordinal(end.toordinal() + 1)

        if data_type == "打料紀錄":
            rows = get_feed_records_between(date_start_iso(start), date_start_iso(end_exclusive))
            rows = filter_common_rows(rows, category, material_name, supplier, machine, user_name)
            return build_feed_result(rows)

        if data_type == "入庫紀錄":
            rows = get_purchase_records_between(start.isoformat(), end_exclusive.isoformat())
            rows = filter_common_rows(rows, category, material_name, supplier, machine, user_name)
            return build_purchase_result(rows)

        if data_type == "保養紀錄":
            rows = get_maintenance_records_between(start.isoformat(), end_exclusive.isoformat())
            # 保養類欄位多在 maintenance_items 內，先轉成 service 結果，再以結果做輕量過濾。
            return build_maintenance_result(rows)

        if data_type == "交接紀錄":
            rows = get_handover_items_between(start.isoformat(), end_exclusive.isoformat())
            return build_handover_result(rows)

        return ServiceResult(ok=False, message=f"未知資料類型：{data_type}")

    except Exception as exc:
        return ServiceResult(ok=False, message=f"全條件查詢失敗：{exc}")




# ============================================================
# Filter options
# ============================================================

def add_unique(target: list[str], value: Any):
    text = clean_text(value)
    if text and text not in target:
        target.append(text)


def infer_material_supplier_pair(row: dict[str, Any]) -> tuple[str, str]:
    name = first_value(row, ["material_name", "display_name", "name", "material_type"], "")
    supplier = clean_text(first_value(row, ["supplier"], ""))

    family = normalize_material_family(name)

    # 針對 supplier 欄位空白，但名稱含供應商的情況補判斷。
    if not supplier:
        for candidate in ["南紡308A", "南紡", "南亞", "遠東", "集盛", "力鵬", "中國岳化", "中國儀征", "台塑"]:
            if candidate in clean_text(name):
                supplier = candidate
                break

    if supplier == "南紡308A" and family == "PET308A":
        supplier = "南紡"

    return family, supplier


def build_report_filter_options() -> ServiceResult:
    """
    給 reports.py 下拉選單使用。
    供應商、人員、原料種類從 Supabase 實際資料彙整，不再寫死。
    """
    try:
        suppliers: list[str] = ["全部"]
        users: list[str] = ["全部"]
        material_families: list[str] = ["全部"]
        machines: list[str] = ["全部", "S1", "S2", "S1-PET", "S1-PA6", "S2-PET", "S2-PA6"]
        material_supplier_map: dict[str, list[str]] = {}

        material_rows = get_material_stock_rows()
        recycled_rows = get_available_recycled_material_rows()
        purchase_rows = get_purchase_records_for_options(limit=1000)
        feed_rows = get_feed_records_for_options(limit=1000)
        user_rows = get_user_rows()

        option_source_rows = []
        option_source_rows.extend(material_rows)
        option_source_rows.extend(recycled_rows)
        option_source_rows.extend(purchase_rows)
        option_source_rows.extend(feed_rows)

        for row in option_source_rows:
            family, supplier = infer_material_supplier_pair(row)

            if family:
                add_unique(material_families, family)

            if supplier:
                add_unique(suppliers, supplier)

            if family:
                material_supplier_map.setdefault(family, ["全部"])
                if supplier and supplier not in material_supplier_map[family]:
                    material_supplier_map[family].append(supplier)

            for key in ["machine", "tower", "tower_code", "machine_area"]:
                add_unique(machines, row.get(key))

        for row in user_rows:
            add_unique(users, row.get("name"))

        # 依現場常用順序排序；未知項目排後面。
        material_order = {
            "全部": 0,
            "PET": 1,
            "PET308A": 2,
            "PA6": 3,
            "RPET": 4,
            "母粒": 5,
            "PP": 6,
        }
        material_families.sort(key=lambda x: (material_order.get(x, 99), x))
        suppliers.sort(key=lambda x: (0 if x == "全部" else 1, x))
        users.sort(key=lambda x: (0 if x == "全部" else 1, x))
        machines.sort(key=lambda x: (0 if x == "全部" else 1, x))

        for family, values in material_supplier_map.items():
            values.sort(key=lambda x: (0 if x == "全部" else 1, x))

        return ServiceResult(
            ok=True,
            data={
                "categories": ["全部", "新料", "母粒", "回用料", "清潔", "耗材更換", "異常", "待辦"],
                "material_families": material_families,
                "suppliers": suppliers,
                "material_supplier_map": material_supplier_map,
                "machines": machines,
                "users": users,
            },
        )

    except Exception as exc:
        return ServiceResult(
            ok=False,
            message=f"報表篩選選項載入失敗：{exc}",
            data={
                "categories": ["全部", "新料", "母粒", "回用料", "清潔", "耗材更換", "異常", "待辦"],
                "material_families": ["全部", "PET", "PET308A", "PA6", "RPET", "母粒", "PP"],
                "suppliers": ["全部"],
                "material_supplier_map": {},
                "machines": ["全部", "S1", "S2", "S1-PET", "S1-PA6", "S2-PET", "S2-PA6"],
                "users": ["全部"],
            },
        )

# ============================================================
# CSV / downloadable export helpers
# ============================================================

def safe_filename(value: str) -> str:
    text = clean_text(value, "report")
    text = re.sub(r"[\\/:*?\"<>|\\s]+", "_", text)
    return text.strip("_") or "report"


def resolve_export_folder(export_dir: str = DEFAULT_EXPORT_DIR) -> Path:
    """
    取得報表匯出資料夾。

    systemd 啟動時工作目錄不一定是專案根目錄，因此不能使用
    Path("exports") 這種相對路徑。這裡一律以 services/ 的上一層
    專案根目錄為基準，對應 Nginx 的 /exports/ 靜態下載路徑。
    """
    raw = clean_text(export_dir, DEFAULT_EXPORT_DIR).strip()

    if not raw:
        raw = DEFAULT_EXPORT_DIR

    candidate = Path(raw)

    if candidate.is_absolute():
        folder = candidate
    else:
        folder = BASE_DIR / raw.strip("/")

    folder.mkdir(parents=True, exist_ok=True)
    return folder


def cleanup_old_exports(
    export_dir: str = DEFAULT_EXPORT_DIR,
    older_than_days: int = DEFAULT_EXPORT_RETENTION_DAYS,
) -> dict[str, Any]:
    """
    機會式清理舊匯出檔。

    目前 Nginx 已提供 /exports/ 靜態下載，匯出的 CSV / PDF 都會先放在 VM。
    這裡先清理 csv/pdf/docx/xlsx，避免 exports 資料夾長期累積。
    """
    folder = resolve_export_folder(export_dir)
    cutoff = now_taipei() - timedelta(days=max(1, older_than_days))
    deleted_count = 0
    failed: list[str] = []

    for path in folder.iterdir():
        if not path.is_file():
            continue

        if path.suffix.lower() not in [".csv", ".pdf", ".docx", ".xlsx"]:
            continue

        try:
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, TAIPEI_TZ)
            if modified_at < cutoff:
                path.unlink()
                deleted_count += 1
        except Exception:
            failed.append(path.name)

    return {
        "deleted_count": deleted_count,
        "failed": failed,
        "older_than_days": older_than_days,
    }


def build_export_url_path(filename: str) -> str:
    return f"/exports/{quote(filename)}"


def export_report_to_csv(
    report_data: dict[str, Any],
    export_dir: str = DEFAULT_EXPORT_DIR,
) -> ServiceResult:
    """
    將報表資料輸出成 CSV。

    - 寫入專案根目錄 exports/ 絕對路徑。
    - 回傳 /exports/<filename>，由 Nginx 80 port 提供正式下載。
    - 使用 utf-8-sig，方便 Windows Excel 直接開啟不亂碼。
    """
    try:
        title = clean_text(report_data.get("title"), "report")
        columns = report_data.get("columns") or []
        rows = report_data.get("rows") or []

        if not columns:
            return ServiceResult(ok=False, message="沒有可匯出的欄位。")

        folder = resolve_export_folder(export_dir)
        cleanup = cleanup_old_exports(export_dir, DEFAULT_EXPORT_RETENTION_DAYS)

        timestamp = now_taipei().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{safe_filename(title)}.csv"
        path = folder / filename

        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=columns,
                extrasaction="ignore",
            )
            writer.writeheader()

            for row in rows:
                writer.writerow({col: row.get(col, "") for col in columns})

        url_path = build_export_url_path(filename)

        return ServiceResult(
            ok=True,
            message=f"CSV 已匯出：{url_path}",
            data={
                "path": str(path),
                "absolute_path": str(path),
                "filename": filename,
                "url_path": url_path,
                "download_path": url_path,
                "expires_after_days": DEFAULT_EXPORT_RETENTION_DAYS,
                "cleanup": cleanup,
            },
        )

    except Exception as exc:
        return ServiceResult(ok=False, message=f"CSV 匯出失敗：{exc}")


def _register_pdf_font() -> str:
    """
    註冊 PDF 中文字型。

    優先使用 VM 系統已安裝的 Noto / WenQuanYi / AR PL 字型；
    若找不到，退回 ReportLab 內建 CID 字型 STSong-Light，避免直接失敗。
    """
    from reportlab.pdfbase import pdfmetrics

    # 已註冊過就直接回傳。
    try:
        pdfmetrics.getFont("KNH_CJK")
        return "KNH_CJK"
    except Exception:
        pass

    font_candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/usr/share/fonts/truetype/arphic/ukai.ttc",
    ]

    try:
        from reportlab.pdfbase.ttfonts import TTFont
        for font_path in font_candidates:
            path = Path(font_path)
            if not path.exists():
                continue
            try:
                pdfmetrics.registerFont(TTFont("KNH_CJK", str(path)))
                return "KNH_CJK"
            except Exception:
                continue
    except Exception:
        pass

    try:
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light"
    except Exception:
        return "Helvetica"


def _wrap_text_for_pdf(value: Any, max_chars: int = 18) -> str:
    """讓中文表格內容可在 PDF 表格中換行，避免欄位過寬或文字溢出。"""
    from xml.sax.saxutils import escape

    text = clean_text(value, "-")
    if not text:
        text = "-"

    wrapped_lines: list[str] = []
    for raw_line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            wrapped_lines.append("")
            continue
        while len(line) > max_chars:
            wrapped_lines.append(line[:max_chars])
            line = line[max_chars:]
        wrapped_lines.append(line)

    return "<br/>".join(escape(line) for line in wrapped_lines)


def export_report_to_pdf(
    report_data: dict[str, Any],
    export_dir: str = DEFAULT_EXPORT_DIR,
) -> ServiceResult:
    """
    將報表資料輸出成 PDF。

    - 寫入專案根目錄 exports/ 絕對路徑。
    - 回傳 /exports/<filename>.pdf，由 Nginx 80 port 提供正式下載。
    - 使用 ReportLab 產生；若 VM 缺少 reportlab，會回傳明確錯誤。
    """
    try:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except Exception as import_exc:
            return ServiceResult(
                ok=False,
                message=(
                    "PDF 匯出失敗：VM 尚未安裝 reportlab。"
                    "請先執行 pip install reportlab，或將 reportlab 加入 requirements.txt。"
                    f" 原始錯誤：{import_exc}"
                ),
            )

        title = clean_text(report_data.get("title"), "report")
        columns = report_data.get("columns") or []
        rows = report_data.get("rows") or []
        summary_text = clean_text(report_data.get("summary_text"), "")

        if not columns:
            return ServiceResult(ok=False, message="沒有可匯出的欄位。")

        folder = resolve_export_folder(export_dir)
        cleanup = cleanup_old_exports(export_dir, DEFAULT_EXPORT_RETENTION_DAYS)

        timestamp = now_taipei().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{safe_filename(title)}.pdf"
        path = folder / filename

        font_name = _register_pdf_font()
        page_size = landscape(A4)

        doc = SimpleDocTemplate(
            str(path),
            pagesize=page_size,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title=title,
            author="KNH MMS",
        )

        title_style = ParagraphStyle(
            "KNHTitle",
            fontName=font_name,
            fontSize=18,
            leading=24,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=8,
        )
        meta_style = ParagraphStyle(
            "KNHMeta",
            fontName=font_name,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#64748B"),
            spaceAfter=6,
        )
        header_style = ParagraphStyle(
            "KNHHeader",
            fontName=font_name,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#0F172A"),
            alignment=1,
        )
        cell_style = ParagraphStyle(
            "KNHCell",
            fontName=font_name,
            fontSize=8,
            leading=10.5,
            textColor=colors.HexColor("#1E293B"),
        )

        story = []
        story.append(Paragraph(_wrap_text_for_pdf(title, 40), title_style))
        story.append(
            Paragraph(
                f"產生時間：{now_taipei().strftime('%Y/%m/%d %H:%M')}｜共 {len(rows)} 筆資料",
                meta_style,
            )
        )
        if summary_text:
            story.append(Paragraph(_wrap_text_for_pdf(summary_text, 60), meta_style))
        story.append(Spacer(1, 6))

        table_data = [[Paragraph(_wrap_text_for_pdf(col, 10), header_style) for col in columns]]
        for row in rows:
            table_data.append([
                Paragraph(_wrap_text_for_pdf(row.get(col, ""), 18), cell_style)
                for col in columns
            ])

        available_width = doc.width
        column_count = max(1, len(columns))
        col_widths = [available_width / column_count for _ in columns]

        table = Table(
            table_data,
            colWidths=col_widths,
            repeatRows=1,
            splitByRow=True,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5F0FF")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#DDE7F3")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ]
            )
        )
        story.append(table)
        doc.build(story)

        url_path = build_export_url_path(filename)

        return ServiceResult(
            ok=True,
            message=f"PDF 已匯出：{url_path}",
            data={
                "path": str(path),
                "absolute_path": str(path),
                "filename": filename,
                "url_path": url_path,
                "download_path": url_path,
                "expires_after_days": DEFAULT_EXPORT_RETENTION_DAYS,
                "cleanup": cleanup,
            },
        )

    except Exception as exc:
        return ServiceResult(ok=False, message=f"PDF 匯出失敗：{exc}")
