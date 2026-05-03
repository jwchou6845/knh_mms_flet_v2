from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from repositories.dryer_status_repo import (
    get_dryer_status_rows,
    update_dryer_status,
)


TAIPEI_TZ = ZoneInfo("Asia/Taipei")


@dataclass
class ServiceResult:
    ok: bool
    message: str = ""
    data: Any = None


def now_taipei_iso() -> str:
    return datetime.now(TAIPEI_TZ).replace(microsecond=0).isoformat()


def format_updated_at(value: str | None) -> str:
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


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def normalize_percent(value: Any) -> int:
    percent = _to_int(value, 0)
    return max(0, min(100, percent))


def build_dryer_status_card_data(row: dict[str, Any]) -> dict[str, Any]:
    tower_code = str(row.get("tower_code") or "")
    tower_type = str(row.get("tower_type") or "")
    material = str(row.get("material") or "").strip()
    note = str(row.get("note") or "").strip()
    percent = normalize_percent(row.get("percent"))

    return {
        "tower_code": tower_code,
        "tower_type": tower_type,
        "material": material or "未填寫",
        "percent": percent,
        "note": note or "無備註",
        "updated_at": format_updated_at(row.get("updated_at")),
        "updated_by_name": row.get("updated_by_name") or "-",
    }


def load_dryer_status() -> ServiceResult:
    try:
        rows = get_dryer_status_rows()
        data = [build_dryer_status_card_data(row) for row in rows]

        latest_updated = "-"
        if data:
            latest_updated = max(
                [item.get("updated_at") or "-" for item in data]
            )

        return ServiceResult(
            ok=True,
            data={
                "items": data,
                "latest_updated": latest_updated,
            },
        )

    except Exception as exc:
        return ServiceResult(
            ok=False,
            message=f"讀取乾燥塔內存備忘失敗：{exc}",
            data={
                "items": [],
                "latest_updated": "-",
            },
        )


def save_dryer_status(
    tower_code: str,
    material: str,
    percent: Any,
    note: str,
    updated_by_user_id: str | None = None,
    updated_by_name: str | None = None,
) -> ServiceResult:
    tower_code = str(tower_code or "").strip()
    material = str(material or "").strip()
    note = str(note or "").strip()

    if tower_code not in ["S1-PET", "S1-PA6", "S2-PET", "S2-PA6"]:
        return ServiceResult(ok=False, message="乾燥塔代號錯誤。")

    if not material:
        return ServiceResult(ok=False, message="請輸入目前塔內原料。")

    percent_value = normalize_percent(percent)

    try:
        updated = update_dryer_status(
            tower_code=tower_code,
            payload={
                "material": material,
                "percent": percent_value,
                "note": note or None,
                "updated_at": now_taipei_iso(),
                "updated_by_user_id": updated_by_user_id,
                "updated_by_name": updated_by_name,
            },
        )

        if not updated:
            return ServiceResult(ok=False, message="儲存失敗，Supabase 未回傳資料。")

        return ServiceResult(
            ok=True,
            message="乾燥塔內存備忘已更新。",
            data=build_dryer_status_card_data(updated),
        )

    except Exception as exc:
        return ServiceResult(ok=False, message=f"儲存失敗：{exc}")