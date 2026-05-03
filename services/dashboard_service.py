from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from repositories.dashboard_repo import (
    get_active_maintenance_items,
    get_available_recycled_materials,
    get_feed_records_between,
    get_maintenance_records_for_summary,
    get_monthly_usage_rows,
    get_material_stock_rows,
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


def month_start(target: date) -> date:
    return target.replace(day=1)


def add_months(target: date, months: int) -> date:
    year = target.year + ((target.month - 1 + months) // 12)
    month = ((target.month - 1 + months) % 12) + 1
    return date(year, month, 1)


def date_to_taipei_start_iso(value: date) -> str:
    return datetime.combine(value, time.min, tzinfo=TAIPEI_TZ).isoformat()


def current_month_label() -> str:
    return now_taipei().strftime("%Y-%m")


def current_time_label() -> str:
    return now_taipei().strftime("%H:%M")


def parse_date(value: Any) -> date | None:
    if not value:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    text = str(value).strip().replace("/", "-")

    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def format_date(value: date | None) -> str:
    if not value:
        return "-"
    return value.strftime("%Y/%m/%d")


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


# ============================================================
# Stock data
# ============================================================

def stock_bar_colors(row: dict[str, Any]) -> tuple[str, str]:
    if bool(row.get("is_low_stock", False)):
        return "#EF4444", "#FFCDD2"

    material_type = str(row.get("material_type") or "")
    main_category = str(row.get("main_category") or "")

    combined = f"{material_type} {main_category}"

    if "已結晶" in combined:
        return "#F59E0B", "#FCD34D"

    if "未結晶" in combined:
        return "#3B82F6", "#93C5FD"

    return "#10B981", "#6EE7B7"


def recycled_bar_colors(name: str, mat_type: str) -> tuple[str, str]:
    combined = f"{name} {mat_type}".upper()

    if "308A" in combined:
        return "#EF4444", "#FFCDD2"

    if "RPET" in combined:
        return "#F472B6", "#FBCFE8"

    if "PA6" in combined:
        return "#38BDF8", "#BAE6FD"

    return "#2563EB", "#93C5FD"


def build_new_stock_data(stock_rows: list[dict[str, Any]]) -> list[tuple[str, int, str, str]]:
    result: list[tuple[str, int, str, str]] = []

    for row in stock_rows:
        name = str(row.get("material_name") or "-")
        qty = to_int(row.get("current_stock_bags"), 0)
        color_top, color_bottom = stock_bar_colors(row)
        result.append((name, qty, color_top, color_bottom))

    return result


def build_low_stock_alerts(stock_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    alerts = []

    for row in stock_rows:
        if bool(row.get("is_low_stock", False)):
            alerts.append(
                {
                    "name": row.get("material_name") or "-",
                    "qty": to_int(row.get("current_stock_bags"), 0),
                }
            )

    alerts.sort(key=lambda x: (x["qty"], x["name"]))
    return alerts


def build_recycled_stock_data(rows: list[dict[str, Any]]) -> list[tuple[str, int, str, str]]:
    summary: dict[str, dict[str, Any]] = {}

    for row in rows:
        supplier = str(row.get("supplier") or "未知供應商")
        mat_type = str(row.get("material_type") or "未知種類")
        weight = to_float(row.get("weight_kg"), 0)
        key = f"{supplier} {mat_type}"

        if key not in summary:
            summary[key] = {"weight": 0.0, "material_type": mat_type}

        summary[key]["weight"] += weight

    result: list[tuple[str, int, str, str]] = []

    for name, data in summary.items():
        color_top, color_bottom = recycled_bar_colors(name, data["material_type"])
        result.append((name, int(data["weight"]), color_top, color_bottom))

    result.sort(key=lambda x: x[1], reverse=True)
    return result


# ============================================================
# Usage data
# ============================================================

def usage_category(record: dict[str, Any]) -> str:
    feed_type = str(record.get("feed_type") or "")

    if feed_type == "recycled":
        return "回用料"

    if feed_type == "aux":
        return "母粒"

    material_source = str(record.get("material_source") or "")
    material_name = str(record.get("material_name") or "")

    if "母粒" in material_source or "母粒" in material_name:
        return "母粒"

    return "新料"


def usage_display_name(record: dict[str, Any]) -> str:
    material_name = str(record.get("material_name") or "未知")
    supplier = str(record.get("supplier") or "").strip()

    if supplier and supplier not in material_name:
        return f"{material_name}-{supplier}".strip("-")

    return material_name


def month_key(value: Any) -> str:
    parsed = parse_date(value)
    if not parsed:
        return ""
    return parsed.strftime("%Y-%m")


def build_month_labels(end_month: date, count: int = 7) -> list[str]:
    start_month = add_months(month_start(end_month), -(count - 1))
    labels = []
    for idx in range(count):
        labels.append(add_months(start_month, idx).strftime("%Y-%m"))
    return labels


def normalize_usage_display_name(category: str, display_name: str, material_name: str = "", supplier: str = "") -> str:
    """
    統一首頁月用量小卡名稱，避免同一個品項因不同資料來源而重複出現。

    例：
    - 母粒 / 輔助母粒-南亞 → 母粒
    - [南紡] PET → PET-南紡
    - [南紡308A] PET-308A → PET308A-南紡
    - PET-308A-南紡 → PET308A-南紡
    """
    cat = str(category or "").strip()
    name = str(display_name or material_name or "").strip()
    mat = str(material_name or "").strip()
    sup = str(supplier or "").strip()

    if cat == "母粒":
        return "母粒"

    # 解析 feed_records 可能產生的格式：[南紡] PET / [南紡308A] PET-308A
    if name.startswith("[") and "]" in name:
        bracket = name[1:name.find("]")].strip()
        rest = name[name.find("]") + 1 :].strip()

        if bracket:
            sup = bracket

        if rest:
            mat = rest
            name = rest

    # 常見供應商與原料標準化
    compact = f"{name} {mat} {sup}".upper().replace(" ", "")

    supplier_clean = sup
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

    if "308A" in compact:
        material_clean = "PET308A"
    elif "RPET" in compact:
        material_clean = "RPET"
    elif "PA6" in compact:
        material_clean = "PA6"
    elif "PET" in compact:
        material_clean = "PET"
    else:
        # 如果判斷不出原料，就先清理常見符號後回傳
        cleaned = name.replace("PET-308A", "PET308A").replace("PET308A", "PET308A")
        return cleaned or "未知"

    if supplier_clean:
        return f"{material_clean}-{supplier_clean}"

    # 如果 display_name 本身已含供應商，例如 PET-南紡
    for known_supplier in ["南紡", "南亞", "集盛", "力鵬", "遠東"]:
        if known_supplier in name:
            return f"{material_clean}-{known_supplier}"

    return material_clean



def build_usage_summary_from_monthly_rows(
    monthly_rows: list[dict[str, Any]],
    selected_month: date,
    history_month_count: int = 7,
) -> dict[str, dict[str, dict[str, Any]]]:
    """
    由 monthly_usage_view 建立首頁小卡資料。

    每個項目的資料結構：
    {
        "this_month": 1000,
        "last_month": 2000,
        "history": [0, 100, 200, ...],
        "history_labels": ["2025-11", ...]
    }
    """
    summary: dict[str, dict[str, dict[str, Any]]] = {
        "新料": {},
        "母粒": {},
        "回用料": {},
    }

    selected_month_start = month_start(selected_month)
    last_month_start = add_months(selected_month_start, -1)

    selected_key = selected_month_start.strftime("%Y-%m")
    last_key = last_month_start.strftime("%Y-%m")
    history_labels = build_month_labels(selected_month_start, history_month_count)

    # 先依 category / display_name / month 聚合
    bucket: dict[str, dict[str, dict[str, float]]] = {
        "新料": {},
        "母粒": {},
        "回用料": {},
    }

    for row in monthly_rows:
        category = str(row.get("category") or "").strip()
        raw_display_name = str(row.get("display_name") or "未知").strip()
        material_name = str(row.get("material_name") or "").strip()
        supplier = str(row.get("supplier") or "").strip()
        display_name = normalize_usage_display_name(
            category=category,
            display_name=raw_display_name,
            material_name=material_name,
            supplier=supplier,
        )
        usage_key = month_key(row.get("usage_month"))
        weight = to_float(row.get("weight_kg"), 0)

        if category not in bucket or not display_name or not usage_key:
            continue

        if display_name not in bucket[category]:
            bucket[category][display_name] = {}

        bucket[category][display_name][usage_key] = bucket[category][display_name].get(usage_key, 0) + weight

    for category, items in bucket.items():
        for display_name, month_values in items.items():
            history = [month_values.get(label, 0.0) for label in history_labels]
            this_month = month_values.get(selected_key, 0.0)
            last_month = month_values.get(last_key, 0.0)

            # 完全沒有選定月份、上月與歷史值的項目就不顯示
            if this_month == 0 and last_month == 0 and not any(history):
                continue

            summary[category][display_name] = {
                "this_month": this_month,
                "last_month": last_month,
                "history": history,
                "history_labels": history_labels,
            }

    return summary


# ============================================================
# Maintenance summary
# ============================================================

def display_maintenance_item_name(item: dict[str, Any]) -> str:
    item_name = item.get("item_name") or "-"
    maintenance_type = item.get("maintenance_type") or ""
    sub_category = item.get("sub_category") or ""

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


def calculate_due_tag(next_date: date | None) -> str:
    if not next_date:
        return "未建立"

    today = now_taipei().date()

    if next_date < today:
        return "逾期"

    diff = (next_date - today).days

    if diff == 0:
        return "今日"

    if diff == 1:
        return "明日"

    if diff <= 3:
        return f"{diff}天內"

    return ""


def build_maintenance_summary(
    items: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    record_map = latest_record_map(records)

    due_items: list[dict[str, Any]] = []
    overdue_count = 0
    today_count = 0
    abnormal_count = 0

    priority = {
        "逾期": 1,
        "今日": 2,
        "明日": 3,
        "2天內": 4,
        "3天內": 5,
        "未建立": 6,
    }

    for item in items:
        item_id = item.get("id")
        latest = record_map.get(item_id)

        last_date = parse_date(latest.get("executed_date")) if latest else None
        cycle_days = to_int(item.get("cycle_days"), 30)

        next_date = None
        if last_date:
            next_date = last_date + timedelta(days=cycle_days)

        due_tag = calculate_due_tag(next_date)

        if due_tag in ["逾期", "今日", "明日", "2天內", "3天內", "未建立"]:
            if due_tag == "逾期":
                overdue_count += 1
            if due_tag == "今日":
                today_count += 1

            due_items.append(
                {
                    "item_name": display_maintenance_item_name(item),
                    "maintenance_type": item.get("maintenance_type") or "-",
                    "machine_area": item.get("machine_area") or "-",
                    "due_tag": due_tag,
                    "next_date": format_date(next_date),
                    "priority": priority.get(due_tag, 99),
                }
            )

    # 近期異常：以最近讀回來的保養紀錄中 result != 正常 計算
    for record in records:
        result = str(record.get("result") or "")
        if result and result != "正常":
            abnormal_count += 1

    due_items.sort(key=lambda x: (x.get("priority", 99), x.get("next_date") or "9999/99/99"))

    total = len(due_items)

    return {
        "total": total,
        "overdue": overdue_count,
        "today": today_count,
        "abnormal": abnormal_count,
        "preview": due_items[:3],
        "error": "",
    }


# ============================================================
# Public loader
# ============================================================

def load_dashboard_page_data() -> ServiceResult:
    try:
        now = now_taipei()
        this_month_start = month_start(now.date())
        next_month_start = add_months(this_month_start, 1)
        last_month_start = add_months(this_month_start, -1)

        stock_rows = get_material_stock_rows()
        recycled_rows = get_available_recycled_materials()

        # 首頁用量趨勢使用 monthly_usage_view：
        # 2025-10~2026-04 紙本歷史補登 + 2026-05 後 feed_records 即時計算
        history_month_count = 7
        history_start_month = add_months(this_month_start, -(history_month_count - 1))
        monthly_usage_rows = get_monthly_usage_rows(
            history_start_month.isoformat(),
            next_month_start.isoformat(),
        )

        maintenance_items = get_active_maintenance_items()
        maintenance_records = get_maintenance_records_for_summary(limit=500)

        data = {
            "current_ym": current_month_label(),
            "current_time": current_time_label(),
            "new_stock_data": build_new_stock_data(stock_rows),
            "recycled_stock_data": build_recycled_stock_data(recycled_rows),
            "alert_items": build_low_stock_alerts(stock_rows),
            "usage_summary": build_usage_summary_from_monthly_rows(
                monthly_usage_rows,
                selected_month=this_month_start,
                history_month_count=history_month_count,
            ),
            "maintenance_summary": build_maintenance_summary(maintenance_items, maintenance_records),
        }

        return ServiceResult(ok=True, data=data)

    except Exception as exc:
        return ServiceResult(
            ok=False,
            message=f"讀取首頁資料失敗：{exc}",
            data={
                "current_ym": current_month_label(),
                "current_time": current_time_label(),
                "new_stock_data": [],
                "recycled_stock_data": [],
                "alert_items": [],
                "usage_summary": {"新料": {}, "母粒": {}, "回用料": {}},
                "maintenance_summary": {
                    "total": 0,
                    "overdue": 0,
                    "today": 0,
                    "abnormal": 0,
                    "preview": [],
                    "error": str(exc),
                },
            },
        )
