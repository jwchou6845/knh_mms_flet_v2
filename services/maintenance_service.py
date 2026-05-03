from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any

from repositories.maintenance_repo import (
    create_maintenance_item,
    create_maintenance_record,
    get_active_maintenance_items,
    get_recent_maintenance_records,
    get_records_by_item_id,
    soft_delete_maintenance_record,
    update_maintenance_item,
)


TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def now_taipei_iso() -> str:
    return datetime.now(TAIPEI_TZ).isoformat()


# =========================
# 回傳結果物件
# =========================

@dataclass
class ServiceResult:
    ok: bool
    message: str = ""
    data: Any = None


# =========================
# 日期工具
# =========================

def _parse_date(value: str | None) -> date | None:
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        pass

    try:
        return datetime.strptime(value, "%Y/%m/%d").date()
    except ValueError:
        return None


def _format_date(value: date | str | None) -> str:
    if not value:
        return "-"

    if isinstance(value, str):
        parsed = _parse_date(value)
        if not parsed:
            return value
        return parsed.strftime("%Y/%m/%d")

    return value.strftime("%Y/%m/%d")


def _today() -> date:
    return datetime.now(TAIPEI_TZ).date()


# =========================
# 狀態計算
# =========================

def calculate_next_date(last_date: date | None, cycle_days: int | None) -> date | None:
    if not last_date:
        return None

    days = cycle_days or 30
    return last_date + timedelta(days=days)


def calculate_status(next_date: date | None) -> str:
    if not next_date:
        return "未建立紀錄"

    today = _today()

    if next_date < today:
        return "逾期"

    diff_days = (next_date - today).days

    if diff_days <= 3:
        return "提醒"

    return "正常"


def calculate_due_tag(next_date: date | None) -> str:
    if not next_date:
        return "未建立"

    today = _today()

    if next_date < today:
        return "逾期"

    diff_days = (next_date - today).days

    if diff_days == 0:
        return "今日"

    if diff_days == 1:
        return "明日"

    if diff_days <= 3:
        return f"{diff_days}天內"

    return ""


# =========================
# 資料整理
# =========================

def _build_latest_record_map(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    依 maintenance_item_id 建立最近一筆紀錄對照表。
    records 已由 repository 依 executed_date desc / created_at desc 排序。
    """
    latest_map: dict[str, dict[str, Any]] = {}

    for record in records:
        item_id = record.get("maintenance_item_id")
        if not item_id:
            continue

        if item_id not in latest_map:
            latest_map[item_id] = record

    return latest_map


def enrich_items_with_status(
    items: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    latest_record_map = _build_latest_record_map(records)

    enriched_items: list[dict[str, Any]] = []

    for item in items:
        item_id = item.get("id")
        latest_record = latest_record_map.get(item_id)

        last_date = None
        last_result = None
        last_operator = None
        last_note = None

        if latest_record:
            last_date = _parse_date(latest_record.get("executed_date"))
            last_result = latest_record.get("result")
            last_operator = latest_record.get("operator_name")
            last_note = latest_record.get("note")

        cycle_days = item.get("cycle_days") or 30
        next_date = calculate_next_date(last_date, cycle_days)
        status = calculate_status(next_date)
        due_tag = calculate_due_tag(next_date)

        enriched_items.append(
            {
                "id": item.get("id"),
                "item_name": item.get("item_name") or "",
                "maintenance_type": item.get("maintenance_type") or "",
                "main_category": item.get("main_category") or "",
                "sub_category": item.get("sub_category") or "",
                "machine_area": item.get("machine_area") or "",
                "cycle_days": cycle_days,
                "sort_order": item.get("sort_order") or 999,
                "description": item.get("description") or "",
                "last_date": _format_date(last_date),
                "last_result": last_result or "-",
                "last_operator": last_operator or "-",
                "last_note": last_note or "",
                "next_date": _format_date(next_date),
                "status": status,
                "due_tag": due_tag,
                "raw": item,
            }
        )

    return enriched_items


def build_recent_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for record in records:
        item = record.get("maintenance_items") or {}

        result.append(
            {
                "id": record.get("id"),
                "executed_date": _format_date(record.get("executed_date")),
                "date_short": _format_short_date(record.get("executed_date")),
                "maintenance_item_id": record.get("maintenance_item_id"),
                "item_name": item.get("item_name") or "-",
                "maintenance_type": item.get("maintenance_type") or "-",
                "main_category": item.get("main_category") or "-",
                "sub_category": item.get("sub_category") or "",
                "machine_area": item.get("machine_area") or "-",
                "operator_name": record.get("operator_name") or "-",
                "result": record.get("result") or "-",
                "note": record.get("note") or "",
                "created_at": record.get("created_at"),
                "raw": record,
            }
        )

    return result


def _format_short_date(value: str | None) -> str:
    parsed = _parse_date(value)
    if not parsed:
        return "-"
    return parsed.strftime("%m/%d")


def _format_datetime_taipei(value: str | None) -> str:
    if not value:
        return "-"

    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TAIPEI_TZ)
        return dt.astimezone(TAIPEI_TZ).strftime("%Y/%m/%d %H:%M")
    except Exception:
        return value


def build_item_record_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for record in records:
        item = record.get("maintenance_items") or {}
        rows.append(
            {
                "id": record.get("id"),
                "executed_date": _format_date(record.get("executed_date")),
                "date_short": _format_short_date(record.get("executed_date")),
                "maintenance_item_id": record.get("maintenance_item_id"),
                "item_name": item.get("item_name") or "-",
                "maintenance_type": item.get("maintenance_type") or "-",
                "main_category": item.get("main_category") or "-",
                "sub_category": item.get("sub_category") or "",
                "machine_area": item.get("machine_area") or "-",
                "operator_name": record.get("operator_name") or "-",
                "result": record.get("result") or "-",
                "note": record.get("note") or "",
                "created_at": _format_datetime_taipei(record.get("created_at")),
                "raw": record,
            }
        )

    return rows


def build_today_tasks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    今日待辦：顯示逾期、今日、明日、3天內。
    """
    tasks: list[dict[str, Any]] = []

    priority = {
        "逾期": 1,
        "今日": 2,
        "明日": 3,
        "2天內": 4,
        "3天內": 5,
        "未建立": 6,
    }

    for item in items:
        due_tag = item.get("due_tag") or ""

        if due_tag in ["逾期", "今日", "明日", "2天內", "3天內", "未建立"]:
            tasks.append(
                {
                    "id": item.get("id"),
                    "item_name": _display_item_name(item),
                    "maintenance_type": item.get("maintenance_type"),
                    "machine_area": item.get("machine_area"),
                    "next_date": item.get("next_date"),
                    "status": item.get("status"),
                    "due_tag": due_tag,
                    "priority": priority.get(due_tag, 99),
                }
            )

    tasks.sort(key=lambda x: (x.get("priority", 99), x.get("next_date") or "9999/99/99"))

    return tasks[:6]


def _display_item_name(item: dict[str, Any]) -> str:
    item_name = item.get("item_name") or ""
    maintenance_type = item.get("maintenance_type") or ""
    sub_category = item.get("sub_category") or ""

    if maintenance_type == "耗材更換" and sub_category:
        return f"{sub_category}-{item_name}"

    return item_name


def build_summary(items: list[dict[str, Any]], recent_records: list[dict[str, Any]]) -> dict[str, int]:
    current_month = _today().strftime("%Y/%m")

    clean_count = 0
    material_count = 0

    for record in recent_records:
        executed_date = record.get("executed_date") or ""
        maintenance_type = record.get("maintenance_type") or ""

        if executed_date.startswith(current_month):
            if maintenance_type == "清潔":
                clean_count += 1
            elif maintenance_type == "耗材更換":
                material_count += 1

    due_count = 0
    abnormal_count = 0

    for item in items:
        if item.get("status") in ["提醒", "逾期", "未建立紀錄"]:
            due_count += 1

    for record in recent_records:
        if record.get("result") == "異常":
            abnormal_count += 1

    return {
        "clean_count": clean_count,
        "material_count": material_count,
        "due_count": due_count,
        "abnormal_count": abnormal_count,
    }


def group_items_by_type(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "清潔": [item for item in items if item.get("maintenance_type") == "清潔"],
        "耗材更換": [item for item in items if item.get("maintenance_type") == "耗材更換"],
    }


# =========================
# 頁面載入
# =========================

def load_maintenance_page_data() -> ServiceResult:
    try:
        items = get_active_maintenance_items()

        # 多讀一些 records，因為 service 需要用來計算每個項目的最近保養日
        raw_records = get_recent_maintenance_records(limit=300)

        enriched_items = enrich_items_with_status(items, raw_records)
        recent_records = build_recent_records(raw_records[:10])
        today_tasks = build_today_tasks(enriched_items)
        summary = build_summary(enriched_items, recent_records)
        grouped_items = group_items_by_type(enriched_items)

        return ServiceResult(
            ok=True,
            data={
                "items": enriched_items,
                "items_by_type": grouped_items,
                "recent_records": recent_records,
                "today_tasks": today_tasks,
                "summary": summary,
            },
        )

    except Exception as exc:
        return ServiceResult(
            ok=False,
            message=f"讀取保養資料失敗：{exc}",
            data={
                "items": [],
                "items_by_type": {"清潔": [], "耗材更換": []},
                "recent_records": [],
                "today_tasks": [],
                "summary": {
                    "clean_count": 0,
                    "material_count": 0,
                    "due_count": 0,
                    "abnormal_count": 0,
                },
            },
        )


# =========================
# 單一項目紀錄 / 軟刪除
# =========================

def load_item_records(item_id: str, limit: int = 20) -> ServiceResult:
    if not item_id:
        return ServiceResult(ok=False, message="缺少保養項目 ID。", data=[])

    try:
        records = get_records_by_item_id(item_id=item_id, limit=limit)
        return ServiceResult(ok=True, data=build_item_record_rows(records))

    except Exception as exc:
        return ServiceResult(ok=False, message=f"讀取項目保養紀錄失敗：{exc}", data=[])


def delete_maintenance_record(
    record_id: str,
    deleted_by_user_id: str | None,
    deleted_by_name: str | None,
    delete_reason: str = "超級管理員於保養紀錄頁面刪除",
    role: str | None = None,
) -> ServiceResult:
    if role != "超級管理員":
        return ServiceResult(ok=False, message="權限不足，只有超級管理員可以刪除紀錄。")

    if not record_id:
        return ServiceResult(ok=False, message="缺少保養紀錄 ID。")

    payload = {
        "is_deleted": True,
        "deleted_at": now_taipei_iso(),
        "deleted_by_user_id": deleted_by_user_id,
        "deleted_by_name": deleted_by_name or "未命名管理員",
        "delete_reason": delete_reason or "超級管理員於保養紀錄頁面刪除",
    }

    try:
        deleted = soft_delete_maintenance_record(record_id=record_id, payload=payload)

        if not deleted:
            return ServiceResult(ok=False, message="刪除失敗，可能紀錄不存在或已被刪除。")

        return ServiceResult(ok=True, message="保養紀錄已刪除。", data=deleted)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"刪除保養紀錄失敗：{exc}")


# =========================
# 新增保養紀錄
# =========================

def submit_maintenance_record(
    maintenance_item_id: str,
    executed_date: str,
    operator_name: str,
    result: str,
    note: str = "",
    created_by_user_id: str | None = None,
    created_by_name: str | None = None,
) -> ServiceResult:
    if not maintenance_item_id:
        return ServiceResult(ok=False, message="請選擇保養項目。")

    if not executed_date:
        return ServiceResult(ok=False, message="請輸入執行日期。")

    if not _parse_date(executed_date):
        return ServiceResult(ok=False, message="執行日期格式錯誤，請使用 YYYY-MM-DD。")

    if not operator_name:
        return ServiceResult(ok=False, message="請輸入或選擇執行人員。")

    if result not in ["正常", "待確認", "異常"]:
        return ServiceResult(ok=False, message="請選擇正確的執行結果。")

    payload = {
        "maintenance_item_id": maintenance_item_id,
        "executed_date": executed_date,
        "operator_name": operator_name,
        "result": result,
        "note": note or None,
        "created_by_user_id": created_by_user_id,
        "created_by_name": created_by_name,
    }

    try:
        created = create_maintenance_record(payload)

        if not created:
            return ServiceResult(ok=False, message="新增保養紀錄失敗，Supabase 未回傳資料。")

        return ServiceResult(ok=True, message="保養紀錄已新增。", data=created)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"新增保養紀錄失敗：{exc}")


# =========================
# 新增清潔項目
# =========================

def create_cleaning_item(
    item_name: str,
    machine_area: str,
    cycle_days: int,
    sort_order: int,
    description: str = "",
) -> ServiceResult:
    if not item_name:
        return ServiceResult(ok=False, message="請輸入清潔項目名稱。")

    if not machine_area:
        return ServiceResult(ok=False, message="請輸入機台 / 區位。")

    if cycle_days <= 0:
        return ServiceResult(ok=False, message="週期天數必須大於 0。")

    payload = {
        "item_name": item_name,
        "maintenance_type": "清潔",
        "main_category": "清潔項目",
        "sub_category": None,
        "machine_area": machine_area,
        "cycle_days": cycle_days,
        "sort_order": sort_order,
        "is_active": True,
        "description": description or None,
    }

    try:
        created = create_maintenance_item(payload)

        if not created:
            return ServiceResult(ok=False, message="新增清潔項目失敗，Supabase 未回傳資料。")

        return ServiceResult(ok=True, message="清潔項目已新增。", data=created)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"新增清潔項目失敗：{exc}")


# =========================
# 新增耗材項目
# =========================

def create_consumable_item(
    main_category: str,
    sub_category: str,
    item_name: str,
    machine_area: str,
    cycle_days: int,
    sort_order: int,
    description: str = "",
) -> ServiceResult:
    if not main_category:
        return ServiceResult(ok=False, message="請輸入主分類。")

    if not item_name:
        return ServiceResult(ok=False, message="請輸入耗材項目名稱。")

    if not machine_area:
        return ServiceResult(ok=False, message="請輸入機台 / 區位。")

    if cycle_days <= 0:
        return ServiceResult(ok=False, message="週期天數必須大於 0。")

    payload = {
        "item_name": item_name,
        "maintenance_type": "耗材更換",
        "main_category": main_category,
        "sub_category": sub_category or None,
        "machine_area": machine_area,
        "cycle_days": cycle_days,
        "sort_order": sort_order,
        "is_active": True,
        "description": description or None,
    }

    try:
        created = create_maintenance_item(payload)

        if not created:
            return ServiceResult(ok=False, message="新增耗材項目失敗，Supabase 未回傳資料。")

        return ServiceResult(ok=True, message="耗材項目已新增。", data=created)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"新增耗材項目失敗：{exc}")


# =========================
# 編輯週期
# =========================

def update_item_cycle(
    item_id: str,
    cycle_days: int,
    sort_order: int | None = None,
    is_active: bool | None = None,
) -> ServiceResult:
    if not item_id:
        return ServiceResult(ok=False, message="請選擇保養項目。")

    if cycle_days <= 0:
        return ServiceResult(ok=False, message="週期天數必須大於 0。")

    payload: dict[str, Any] = {
        "cycle_days": cycle_days,
    }

    if sort_order is not None:
        payload["sort_order"] = sort_order

    if is_active is not None:
        payload["is_active"] = is_active

    try:
        updated = update_maintenance_item(item_id, payload)

        if not updated:
            return ServiceResult(ok=False, message="更新保養項目失敗，Supabase 未回傳資料。")

        return ServiceResult(ok=True, message="週期設定已更新。", data=updated)

    except Exception as exc:
        return ServiceResult(ok=False, message=f"更新週期失敗：{exc}")