from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from repositories.spinneret_repo import (
    get_spinneret_rows,
    update_spinneret_row,
)


TAIPEI_TZ = ZoneInfo("Asia/Taipei")


STATUS_OPTIONS_BASE = [
    "上機生產中(S1)",
    "上機生產中(S2)",
    "真空燒解中",
    "真空燒解二次",
    "超音波清潔中",
    "組裝中",
    "預熱爐備用中",
    "組裝完成備用中",
    "尚未組裝",
    "尚未燒解",
    "尚未清潔",
    "待下機",
]

SPEC_OPTIONS_BASE = [
    "32分割",
    "15分割",
    "無",
]


@dataclass
class ServiceResult:
    ok: bool
    message: str = ""
    data: Any = None


def now_taipei() -> datetime:
    return datetime.now(TAIPEI_TZ)


def now_taipei_iso() -> str:
    return now_taipei().replace(microsecond=0).isoformat()


def format_datetime_taipei(value: Any) -> str:
    text = str(value or "").strip()

    if not text:
        return "尚無紀錄"

    try:
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TAIPEI_TZ)

        dt = dt.astimezone(TAIPEI_TZ)
        return dt.strftime("%Y/%m/%d %H:%M")

    except Exception:
        return text[:16].replace("-", "/")


def clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def set_sort_key(set_code: str) -> tuple[int, str]:
    text = str(set_code or "").upper().replace(" ", "")

    if "SET#1" in text:
        return (1, text)
    if "SET#2" in text:
        return (2, text)
    if "SET#3" in text:
        return (3, text)
    if "SET#4" in text:
        return (4, text)

    return (99, text)


def build_spinneret_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "set_code": clean_text(row.get("set_code"), "未知組件"),
        "current_status": clean_text(row.get("current_status"), "尚未組裝"),
        "plate_spec": clean_text(row.get("plate_spec"), "無"),
        "status_updated_at": format_datetime_taipei(row.get("status_updated_at")),
        "updated_by_name": clean_text(row.get("updated_by_name"), "-"),
        "note": clean_text(row.get("note"), ""),
    }


def build_options(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    status_options = list(STATUS_OPTIONS_BASE)
    spec_options = list(SPEC_OPTIONS_BASE)

    for row in rows:
        st = clean_text(row.get("current_status"))
        sp = clean_text(row.get("plate_spec"))

        if st and st not in status_options:
            status_options.append(st)

        if sp and sp not in spec_options:
            spec_options.append(sp)

    return {
        "status_options": status_options,
        "spec_options": spec_options,
    }


def build_kpi(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(items),
        "running": sum(1 for item in items if "生產" in item.get("current_status", "")),
        "cleaning": sum(
            1
            for item in items
            if any(keyword in item.get("current_status", "") for keyword in ["燒解", "清潔"])
        ),
        "standby": sum(
            1
            for item in items
            if item.get("current_status", "") in ["預熱爐備用中", "組裝中", "尚未組裝", "待下機"]
        ),
    }


def load_spinneret_page_data() -> ServiceResult:
    try:
        rows = get_spinneret_rows()
        rows.sort(key=lambda row: set_sort_key(row.get("set_code", "")))

        items = [build_spinneret_item(row) for row in rows]
        options = build_options(rows)

        return ServiceResult(
            ok=True,
            data={
                "items": items,
                "kpi": build_kpi(items),
                "status_options": options["status_options"],
                "spec_options": options["spec_options"],
            },
        )

    except Exception as exc:
        return ServiceResult(
            ok=False,
            message=f"讀取噴頭組件狀態失敗：{exc}",
            data={
                "items": [],
                "kpi": {
                    "total": 0,
                    "running": 0,
                    "cleaning": 0,
                    "standby": 0,
                },
                "status_options": list(STATUS_OPTIONS_BASE),
                "spec_options": list(SPEC_OPTIONS_BASE),
            },
        )


def update_spinneret_status(
    row_id: str,
    current_status: str,
    plate_spec: str,
    note: str = "",
    updated_by_user_id: str | None = None,
    updated_by_name: str | None = None,
) -> ServiceResult:
    row_id = clean_text(row_id)
    current_status = clean_text(current_status)
    plate_spec = clean_text(plate_spec)
    note = clean_text(note)

    if not row_id:
        return ServiceResult(ok=False, message="找不到噴頭組件 ID。")

    if not current_status:
        return ServiceResult(ok=False, message="請選擇目前狀態。")

    if not plate_spec:
        return ServiceResult(ok=False, message="請選擇分配板規格。")

    try:
        updated = update_spinneret_row(
            row_id=row_id,
            payload={
                "current_status": current_status,
                "plate_spec": plate_spec,
                "note": note or None,
                "status_updated_at": now_taipei_iso(),
                "updated_by_user_id": updated_by_user_id,
                "updated_by_name": updated_by_name,
            },
        )

        if not updated:
            return ServiceResult(ok=False, message="更新失敗，Supabase 未回傳資料。")

        return ServiceResult(
            ok=True,
            message="噴頭組件狀態已更新。",
            data=build_spinneret_item(updated),
        )

    except Exception as exc:
        return ServiceResult(ok=False, message=f"更新失敗：{exc}")
