from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from repositories.handover_repo import (
    complete_handover_item,
    create_handover_items,
    create_handover_record,
    get_active_user_names,
    get_completed_handover_items,
    get_completed_outgoing_handover_items,
    get_open_handover_items,
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


def now_taipei_iso() -> str:
    return now_taipei().replace(microsecond=0).isoformat()


def today_dash_date() -> str:
    return now_taipei().strftime("%Y-%m-%d")


def normalize_date(date_text: str) -> str:
    raw = str(date_text or "").strip().replace("/", "-")
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception:
        return today_dash_date()


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


def format_date_label(value: Any) -> str:
    parsed = parse_date(value)
    if not parsed:
        return "-"
    return parsed.strftime("%m/%d")


def format_datetime_label(value: Any) -> str:
    text = str(value or "").strip()

    if not text:
        return "-"

    try:
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TAIPEI_TZ)

        dt = dt.astimezone(TAIPEI_TZ)
        return dt.strftime("%m/%d %H:%M")

    except Exception:
        return text[:16].replace("-", "/")


# ============================================================
# Business helpers
# ============================================================

def clean_text(value: Any) -> str:
    return str(value or "").strip()


def get_machine_severity(machine_status: list[dict[str, str]]) -> str:
    statuses = [m.get("status") for m in machine_status]

    if "異常" in statuses:
        return "高"

    if "注意" in statuses:
        return "中"

    return "低"


def get_text_severity(text: str, default: str = "中") -> str:
    value = str(text or "")

    high_keywords = [
        "停機",
        "無法啟動",
        "無法運轉",
        "斷料",
        "漏料",
        "異音",
        "警報",
        "安全",
        "品質",
        "用錯料",
        "混料",
        "溫度失控",
        "壓力異常",
        "空壓異常",
    ]

    for keyword in high_keywords:
        if keyword in value:
            return "高"

    return default


def machine_status_text(machine_status: list[dict[str, str]]) -> str:
    return "；".join([f"{m.get('name')} {m.get('status')}" for m in machine_status])


def status_by_machine_name(machine_status: list[dict[str, str]], name: str) -> str:
    for item in machine_status:
        if item.get("name") == name:
            return item.get("status") or "正常"
    return "正常"


# ============================================================
# Form loader
# ============================================================

def load_handover_form_data(current_user_name: str = "") -> ServiceResult:
    try:
        users = get_active_user_names()

        if current_user_name:
            receiver_options = [u for u in users if u != current_user_name] or users
        else:
            receiver_options = users

        return ServiceResult(
            ok=True,
            data={
                "users": users,
                "receiver_options": receiver_options,
                "today": today_dash_date(),
            },
        )

    except Exception as exc:
        return ServiceResult(
            ok=False,
            message=f"讀取接班人清單失敗：{exc}",
            data={
                "users": [],
                "receiver_options": [],
                "today": today_dash_date(),
            },
        )


# ============================================================
# Submit handover
# ============================================================

def submit_handover_record(
    handover_date: str,
    shift: str,
    sender_name: str,
    receiver_name: str,
    machine_status: list[dict[str, str]],
    abnormal_note: str = "",
    todo_note: str = "",
    created_by_user_id: str | None = None,
    created_by_name: str | None = None,
) -> ServiceResult:
    handover_date_value = normalize_date(handover_date)
    shift = clean_text(shift) or "早班"
    sender_name = clean_text(sender_name)
    receiver_name = clean_text(receiver_name)
    abnormal_note = clean_text(abnormal_note)
    todo_note = clean_text(todo_note)

    if not sender_name or sender_name == "未登入":
        return ServiceResult(ok=False, message="目前無法取得登入者，請重新登入。")

    if not receiver_name or receiver_name == "資料載入中":
        return ServiceResult(ok=False, message="請選擇接班人員。")

    machine_has_issue = any(
        m.get("status") in ["注意", "異常"] for m in machine_status
    )

    if machine_has_issue and not abnormal_note:
        return ServiceResult(
            ok=False,
            message="機台狀態有注意或異常，請在異常事項補充原因。",
        )

    try:
        record_payload = {
            "handover_date": handover_date_value,
            "shift": shift,
            "sender_name": sender_name,
            "receiver_name": receiver_name,
            "machine_s1_status": status_by_machine_name(machine_status, "S1"),
            "machine_s2_status": status_by_machine_name(machine_status, "S2"),
            "air_status": status_by_machine_name(machine_status, "空壓"),
            "status": "已送出",
            "created_by_user_id": created_by_user_id,
            "created_by_name": created_by_name or sender_name,
        }

        main_record = create_handover_record(record_payload)

        if not main_record:
            return ServiceResult(ok=False, message="交接主表建立失敗。")

        record_id = main_record["id"]

        item_payloads = [
            {
                "handover_record_id": record_id,
                "item_type": "狀態",
                "content": machine_status_text(machine_status),
                "severity": get_machine_severity(machine_status),
                "is_completed": True,
            }
        ]

        if abnormal_note:
            item_payloads.append(
                {
                    "handover_record_id": record_id,
                    "item_type": "異常",
                    "content": abnormal_note,
                    "severity": get_text_severity(abnormal_note, default="中"),
                    "is_completed": False,
                }
            )

        if todo_note:
            item_payloads.append(
                {
                    "handover_record_id": record_id,
                    "item_type": "待辦",
                    "content": todo_note,
                    "severity": get_text_severity(todo_note, default="中"),
                    "is_completed": False,
                }
            )

        items = create_handover_items(item_payloads)

        return ServiceResult(
            ok=True,
            message="交接紀錄已送出。",
            data={
                "record": main_record,
                "items": items,
            },
        )

    except Exception as exc:
        return ServiceResult(ok=False, message=f"送出失敗：{exc}")


# ============================================================
# Tasks
# ============================================================

def can_current_user_see_task(
    row: dict[str, Any],
    current_user_name: str,
    can_view_all_tasks: bool = False,
) -> bool:
    if can_view_all_tasks:
        return True

    record = row.get("handover_records") or {}
    sender = str(record.get("sender_name") or "").strip()
    receiver = str(record.get("receiver_name") or "").strip()

    if not sender and not receiver:
        return True

    return current_user_name in [sender, receiver]


def build_task_source(record: dict[str, Any]) -> str:
    d = format_date_label(record.get("handover_date"))
    shift = str(record.get("shift") or "").strip()
    sender = str(record.get("sender_name") or "").strip()
    receiver = str(record.get("receiver_name") or "").strip()

    parts = []
    if d and d != "-":
        parts.append(d)
    if shift:
        parts.append(shift)
    if sender:
        parts.append(f"填：{sender}")
    if receiver:
        parts.append(f"接：{receiver}")

    return "｜".join(parts) if parts else "來源資訊未設定"


def load_open_handover_tasks(
    current_user_name: str,
    can_view_all_tasks: bool = False,
) -> ServiceResult:
    try:
        rows = get_open_handover_items()
        tasks = []

        for row in rows:
            if not can_current_user_see_task(row, current_user_name, can_view_all_tasks):
                continue

            record = row.get("handover_records") or {}

            tasks.append(
                {
                    "record_id": row.get("id"),
                    "type": row.get("item_type") or "待辦",
                    "severity": row.get("severity") or "中",
                    "content": clean_text(row.get("content")) or "(無內容)",
                    "source": build_task_source(record),
                }
            )

        severity_rank = {"高": 0, "中": 1, "低": 2}
        tasks.sort(key=lambda x: (severity_rank.get(x["severity"], 9), x["type"], x["source"]))

        return ServiceResult(
            ok=True,
            data={
                "tasks": tasks,
            },
        )

    except Exception as exc:
        return ServiceResult(
            ok=False,
            message=f"未完成待辦載入失敗：{exc}",
            data={
                "tasks": [],
            },
        )




def build_handover_task(row: dict[str, Any], completed: bool = False) -> dict[str, Any]:
    record = row.get("handover_records") or {}

    task = {
        "record_id": row.get("id"),
        "type": row.get("item_type") or "待辦",
        "severity": row.get("severity") or "中",
        "content": clean_text(row.get("content")) or "(無內容)",
        "source": build_task_source(record),
        "sender_name": str(record.get("sender_name") or "").strip(),
        "receiver_name": str(record.get("receiver_name") or "").strip(),
    }

    if completed:
        task.update(
            {
                "completed_by_name": row.get("completed_by_name") or "-",
                "completed_at": format_datetime_label(row.get("completed_at")),
                "complete_note": clean_text(row.get("complete_note")) or "無處理備註",
            }
        )

    return task


def load_completed_handover_tasks(
    current_user_name: str,
    can_view_all_tasks: bool = False,
    limit: int = 100,
) -> ServiceResult:
    try:
        rows = get_completed_handover_items(limit=limit)
        tasks = []

        for row in rows:
            if not can_current_user_see_task(row, current_user_name, can_view_all_tasks):
                continue

            tasks.append(build_handover_task(row, completed=True))

        return ServiceResult(
            ok=True,
            data={
                "tasks": tasks,
            },
        )

    except Exception as exc:
        return ServiceResult(
            ok=False,
            message=f"已完成紀錄載入失敗：{exc}",
            data={
                "tasks": [],
            },
        )


def load_completed_outgoing_handover_summary(
    current_user_name: str,
    limit: int = 50,
) -> ServiceResult:
    current_user_name = clean_text(current_user_name)

    if not current_user_name or current_user_name == "未登入":
        return ServiceResult(
            ok=True,
            data={
                "total": 0,
                "preview": [],
            },
        )

    try:
        rows = get_completed_outgoing_handover_items(
            sender_name=current_user_name,
            limit=limit,
        )

        preview = []
        for row in rows[:3]:
            preview.append(build_handover_task(row, completed=True))

        return ServiceResult(
            ok=True,
            data={
                "total": len(rows),
                "preview": preview,
            },
        )

    except Exception as exc:
        return ServiceResult(
            ok=False,
            message=f"已完成交接提示載入失敗：{exc}",
            data={
                "total": 0,
                "preview": [],
            },
        )

def complete_handover_task(
    item_id: str,
    completed_by_name: str,
    complete_note: str = "",
) -> ServiceResult:
    item_id = clean_text(item_id)
    completed_by_name = clean_text(completed_by_name)
    complete_note = clean_text(complete_note)

    if not item_id:
        return ServiceResult(ok=False, message="找不到待辦項目 ID。")

    if not completed_by_name or completed_by_name == "未登入":
        return ServiceResult(ok=False, message="目前無法取得登入者，請重新登入。")

    try:
        updated = complete_handover_item(
            item_id,
            {
                "is_completed": True,
                "completed_by_name": completed_by_name,
                "completed_at": now_taipei_iso(),
                "complete_note": complete_note or None,
            },
        )

        if not updated:
            return ServiceResult(ok=False, message="標記完成失敗，Supabase 未回傳資料。")

        return ServiceResult(
            ok=True,
            message="已標記完成。",
            data=updated,
        )

    except Exception as exc:
        return ServiceResult(ok=False, message=f"標記完成失敗：{exc}")
