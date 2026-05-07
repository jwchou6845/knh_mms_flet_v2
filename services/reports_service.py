from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
import csv
import re
import secrets
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
                "數量": first_value(row, ["qty", "quantity", "package_qty", "weight_kg"], 0),
                "單位": first_value(row, ["unit"], "包"),
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
                "數量": first_value(row, ["qty", "quantity", "package_qty", "weight_kg"], 0),
                "人員": first_value(row, ["created_by_name", "operator_name"], "-"),
            }
        )

    return build_result(
        title="入庫紀錄查詢",
        columns=["日期", "類別", "原料名稱", "供應商", "數量", "人員"],
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
# CSV export
# ============================================================

EXPORT_KEEP_DAYS = 3
EXPORT_MAX_TOTAL_MB = 100


def resolve_export_folder(export_dir: str = "exports") -> Path:
    """
    以專案根目錄為基準解析匯出資料夾。
    避免 systemd / VM 工作目錄不是專案根目錄時，CSV 被寫到 /home/jwchou/exports。
    """
    base_dir = Path(__file__).resolve().parent.parent
    clean_dir = str(export_dir or "exports").strip().strip("/") or "exports"
    return base_dir / clean_dir


def safe_filename(value: str) -> str:
    text = clean_text(value, "report")
    text = re.sub(r'[\/:*?"<>|\s]+', "_", text)
    return text.strip("_") or "report"


def safe_ascii_filename(value: str) -> str:
    """
    下載用檔名盡量使用 ASCII，避免手機瀏覽器或 URL 編碼造成下載失敗。
    畫面仍可顯示中文報表標題，實際檔名使用 report_*。
    """
    text = clean_text(value, "report").lower()
    text = re.sub(r"[^a-z0-9_-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._-")
    return text or "report"


def cleanup_old_exports(
    export_dir: str = "exports",
    keep_days: int = EXPORT_KEEP_DAYS,
    max_total_mb: int = EXPORT_MAX_TOTAL_MB,
) -> dict[str, Any]:
    folder = resolve_export_folder(export_dir)
    folder.mkdir(parents=True, exist_ok=True)

    now_ts = now_taipei().timestamp()
    cutoff_ts = now_ts - (keep_days * 24 * 60 * 60)

    deleted_count = 0
    deleted_bytes = 0

    files = []
    for path in folder.glob("*.csv"):
        try:
            stat = path.stat()
            files.append((path, stat.st_mtime, stat.st_size))
            if stat.st_mtime < cutoff_ts:
                deleted_bytes += stat.st_size
                path.unlink()
                deleted_count += 1
        except Exception:
            continue

    # 容量上限保護：若仍超過上限，從最舊檔案開始刪。
    try:
        remaining = []
        for path in folder.glob("*.csv"):
            stat = path.stat()
            remaining.append((path, stat.st_mtime, stat.st_size))

        max_bytes = max_total_mb * 1024 * 1024
        total_bytes = sum(item[2] for item in remaining)

        if total_bytes > max_bytes:
            for path, _mtime, size in sorted(remaining, key=lambda item: item[1]):
                if total_bytes <= max_bytes:
                    break
                try:
                    path.unlink()
                    total_bytes -= size
                    deleted_bytes += size
                    deleted_count += 1
                except Exception:
                    continue
    except Exception:
        pass

    return {
        "deleted_count": deleted_count,
        "deleted_bytes": deleted_bytes,
        "keep_days": keep_days,
        "max_total_mb": max_total_mb,
        "folder": str(folder),
    }


def export_report_to_csv(
    report_data: dict[str, Any],
    export_dir: str = "exports",
) -> ServiceResult:
    """
    將報表資料輸出成 CSV。
    使用 utf-8-sig，方便 Windows Excel 直接開啟不亂碼。
    CSV 固定寫入專案根目錄 / exports，不依賴 process working directory。
    """
    try:
        title = clean_text(report_data.get("title"), "report")
        columns = report_data.get("columns") or []
        rows = report_data.get("rows") or []

        if not columns:
            return ServiceResult(ok=False, message="沒有可匯出的欄位。")

        cleanup = cleanup_old_exports(export_dir=export_dir)

        folder = resolve_export_folder(export_dir)
        folder.mkdir(parents=True, exist_ok=True)

        timestamp = now_taipei().strftime("%Y%m%d_%H%M%S")
        suffix = secrets.token_hex(3)
        filename = f"report_{timestamp}_{safe_ascii_filename(title)}_{suffix}.csv"
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

        csv_text = path.read_text(encoding="utf-8-sig")
        encoded_filename = filename  # ASCII-only; no need to quote here.

        return ServiceResult(
            ok=True,
            message=f"CSV 已匯出：{path}",
            data={
                "path": str(path),
                "folder": str(folder),
                "filename": filename,
                "url_path": f"/assets/exports/{encoded_filename}",
                "asset_url_path": f"/assets/exports/{encoded_filename}",
                "csv_text": csv_text,
                "expires_after_days": EXPORT_KEEP_DAYS,
                "cleanup": cleanup,
            },
        )

    except Exception as exc:
        return ServiceResult(ok=False, message=f"CSV 匯出失敗：{exc}")
