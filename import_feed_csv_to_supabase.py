# import_feed_csv_to_supabase.py
# KNH MMS - Feed module CSV importer
# 將 Airtable 匯出的 CSV 匯入 Supabase：materials / purchase_records / recycled_materials / feed_records

from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from db.supabase_client import supabase

TAIPEI_TZ = ZoneInfo("Asia/Taipei")

BASE_DIR = Path(__file__).resolve().parent

TABLE_MATERIALS = "materials"
TABLE_PURCHASE_RECORDS = "purchase_records"
TABLE_RECYCLED_MATERIALS = "recycled_materials"
TABLE_FEED_RECORDS = "feed_records"


def find_csv(keyword: str) -> Path:
    matches = sorted(BASE_DIR.glob(f"*{keyword}*.csv"))
    if not matches:
        raise FileNotFoundError(f"找不到包含「{keyword}」的 CSV，請確認檔案放在專案根目錄。")
    return matches[0]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows: list[dict[str, str]] = []
        for row in reader:
            clean_row = {str(k).strip(): clean_text(v) for k, v in row.items() if k is not None}
            rows.append(clean_row)
        return rows


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ["nan", "none", "null"]:
        return ""
    return text


def to_int(value: Any, default: int = 0) -> int:
    text = clean_text(value).replace(",", "")
    if not text:
        return default
    try:
        return int(float(text))
    except Exception:
        return default


def to_decimal(value: Any, default: str = "0") -> str:
    text = clean_text(value).replace(",", "")
    if not text:
        return default
    try:
        return str(Decimal(text))
    except (InvalidOperation, ValueError):
        return default


def parse_date(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None

    normalized = text.replace("/", "-")
    for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"]:
        try:
            return datetime.strptime(normalized, fmt).date().isoformat()
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(normalized).date().isoformat()
    except Exception:
        return None


def parse_datetime_taipei(value: Any) -> str:
    """
    CSV 內日期時間視為台灣現場時間，寫入 Supabase timestamptz 時明確帶 +08:00。
    """
    text = clean_text(value)
    if not text:
        return datetime.now(TAIPEI_TZ).replace(microsecond=0).isoformat()

    normalized = text.replace("/", "-")

    for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(normalized, fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=0, minute=0, second=0)
            return dt.replace(tzinfo=TAIPEI_TZ, microsecond=0).isoformat()
        except ValueError:
            pass

    try:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TAIPEI_TZ)
        else:
            dt = dt.astimezone(TAIPEI_TZ)
        return dt.replace(microsecond=0).isoformat()
    except Exception:
        return datetime.now(TAIPEI_TZ).replace(microsecond=0).isoformat()


def is_aux_material(category: str) -> bool:
    text = clean_text(category)
    return "母粒" in text or "輔助母粒" in text


def upsert_materials() -> dict[str, str]:
    path = find_csv("原料庫存表")
    rows = read_csv_rows(path)

    count = 0
    for row in rows:
        material_name = clean_text(row.get("原料名稱"))
        if not material_name:
            continue

        payload = {
            "material_name": material_name,
            "main_category": clean_text(row.get("大類")) or None,
            "material_type": clean_text(row.get("種類")) or None,
            "supplier": clean_text(row.get("供應商")) or None,
            "stock_status": clean_text(row.get("庫存狀態")) or None,
            "current_stock_bags": to_int(row.get("目前庫存(包)")),
            "bag_weight_kg": to_decimal(row.get("單包規格(KG)")),
            "current_stock_kg": to_decimal(row.get("目前庫存(KG)")),
            "is_active": True,
        }

        supabase.table(TABLE_MATERIALS).upsert(payload, on_conflict="material_name").execute()
        count += 1

    print(f"materials 匯入 / 更新完成：{count} 筆")
    return get_material_id_map()


def get_material_id_map() -> dict[str, str]:
    res = supabase.table(TABLE_MATERIALS).select("id, material_name").execute()
    data = res.data or []
    return {row["material_name"]: row["id"] for row in data if row.get("material_name")}


def import_purchase_records(material_id_map: dict[str, str]) -> None:
    path = find_csv("進貨紀錄表")
    rows = read_csv_rows(path)

    inserted = 0
    skipped = 0

    for row in rows:
        batch_no = clean_text(row.get("進貨批號"))
        if not batch_no:
            continue

        exists = (
            supabase.table(TABLE_PURCHASE_RECORDS)
            .select("id")
            .eq("purchase_batch_no", batch_no)
            .limit(1)
            .execute()
        )
        if exists.data:
            skipped += 1
            continue

        material_name = clean_text(row.get("原料名稱")) or clean_text(row.get("關聯原料"))
        payload = {
            "purchase_batch_no": batch_no,
            "purchase_date": parse_date(row.get("進貨日期")),
            "material_id": material_id_map.get(material_name),
            "material_name": material_name or None,
            "supplier": clean_text(row.get("供應商")) or None,
            "quantity_bags": to_int(row.get("進貨數量(包)")),
        }

        supabase.table(TABLE_PURCHASE_RECORDS).insert(payload).execute()
        inserted += 1

    print(f"purchase_records 匯入完成：新增 {inserted} 筆，略過已存在 {skipped} 筆")


def import_recycled_materials() -> dict[str, str]:
    path = find_csv("回用料庫存清單")
    rows = read_csv_rows(path)

    count = 0
    for row in rows:
        recycled_no = clean_text(row.get("回用料編號"))
        if not recycled_no:
            continue

        usage_status = clean_text(row.get("使用狀態")) or "在庫"
        is_used = "已領用" in usage_status or "領用" in usage_status and "在庫" not in usage_status

        payload = {
            "recycled_no": recycled_no,
            "inbound_date": parse_date(row.get("入庫日期")),
            "weight_kg": to_decimal(row.get("重量(KG)")),
            "material_type": clean_text(row.get("原料種類")) or None,
            "source_machine": clean_text(row.get("來源機台")) or None,
            "supplier": clean_text(row.get("供應商")) or None,
            "usage_status": usage_status,
            "is_used": is_used,
        }

        supabase.table(TABLE_RECYCLED_MATERIALS).upsert(payload, on_conflict="recycled_no").execute()
        count += 1

    print(f"recycled_materials 匯入 / 更新完成：{count} 筆")
    return get_recycled_id_map()


def get_recycled_id_map() -> dict[str, str]:
    res = supabase.table(TABLE_RECYCLED_MATERIALS).select("id, recycled_no").execute()
    data = res.data or []
    return {row["recycled_no"]: row["id"] for row in data if row.get("recycled_no")}


def feed_record_exists(feed_type: str, batch_no: str | None, feed_at: str, machine_code: str) -> bool:
    query = (
        supabase.table(TABLE_FEED_RECORDS)
        .select("id")
        .eq("feed_type", feed_type)
        .eq("feed_at", feed_at)
        .eq("machine_code", machine_code)
        .limit(1)
    )

    if batch_no:
        query = query.eq("batch_no", batch_no)
    else:
        query = query.is_("batch_no", "null")

    res = query.execute()
    return bool(res.data)


def import_dry_feed_records(material_id_map: dict[str, str]) -> None:
    path = find_csv("乾燥打料紀錄表")
    rows = read_csv_rows(path)

    inserted = 0
    skipped = 0

    for row in rows:
        source = clean_text(row.get("原料來源")) or "新料"
        feed_type = "aux" if is_aux_material(source) else "new"
        batch_no = clean_text(row.get("原料批號")) or None
        feed_at = parse_datetime_taipei(row.get("日期"))
        machine_code = clean_text(row.get("機台選擇"))

        if not machine_code:
            continue

        if feed_record_exists(feed_type, batch_no, feed_at, machine_code):
            skipped += 1
            continue

        material_name = clean_text(row.get("原料名稱")) or clean_text(row.get("領用新料"))
        bag_weight = to_decimal(row.get("單包規格(KG) (from 領用新料)"))

        payload = {
            "feed_type": feed_type,
            "batch_no": batch_no,
            "feed_at": feed_at,
            "machine_code": machine_code,
            "material_id": material_id_map.get(material_name),
            "material_name": material_name or None,
            "material_source": "輔助母粒" if feed_type == "aux" else "新料",
            "supplier": clean_text(row.get("供應商")) or None,
            "quantity_bags": to_int(row.get("領用數量(包)"), 1),
            "weight_kg": to_decimal(row.get("重量(KG)")),
            "bag_weight_kg": bag_weight,
            "operator_name": None,
            "note": None,
            "is_deleted": False,
        }

        supabase.table(TABLE_FEED_RECORDS).insert(payload).execute()
        inserted += 1

    print(f"feed_records 乾燥打料匯入完成：新增 {inserted} 筆，略過已存在 {skipped} 筆")


def import_recycled_feed_records(recycled_id_map: dict[str, str]) -> None:
    path = find_csv("回用料打料紀錄表")
    rows = read_csv_rows(path)

    inserted = 0
    skipped = 0

    for row in rows:
        recycled_no = clean_text(row.get("領用回用料")) or clean_text(row.get("繼承原料批號"))
        batch_no = clean_text(row.get("繼承原料批號")) or recycled_no or None
        feed_at = parse_datetime_taipei(row.get("日期"))
        machine_code = clean_text(row.get("機台選擇"))

        if not machine_code:
            continue

        if feed_record_exists("recycled", batch_no, feed_at, machine_code):
            skipped += 1
            continue

        recycled_material_id = recycled_id_map.get(recycled_no)

        payload = {
            "feed_type": "recycled",
            "batch_no": batch_no,
            "feed_at": feed_at,
            "machine_code": machine_code,
            "material_id": None,
            "recycled_material_id": recycled_material_id,
            "material_name": clean_text(row.get("原料種類")) or None,
            "material_source": "回用料",
            "supplier": clean_text(row.get("供應商")) or None,
            "quantity_bags": None,
            "weight_kg": to_decimal(row.get("重量(KG)")),
            "bag_weight_kg": None,
            "operator_name": clean_text(row.get("填單人")) or None,
            "note": None,
            "is_deleted": False,
        }

        created = supabase.table(TABLE_FEED_RECORDS).insert(payload).execute()
        inserted += 1

        # 如果剛好有對應 recycled_materials，將其標記已領用。
        if recycled_material_id and created.data:
            feed_record_id = created.data[0].get("id")
            supabase.table(TABLE_RECYCLED_MATERIALS).update(
                {
                    "usage_status": "已領用",
                    "is_used": True,
                    "used_feed_record_id": feed_record_id,
                }
            ).eq("id", recycled_material_id).execute()

    print(f"feed_records 回用料匯入完成：新增 {inserted} 筆，略過已存在 {skipped} 筆")


def main() -> None:
    print("開始匯入 Feed CSV → Supabase")
    print(f"CSV 搜尋目錄：{BASE_DIR}")

    material_id_map = upsert_materials()
    import_purchase_records(material_id_map)

    recycled_id_map = import_recycled_materials()

    import_dry_feed_records(material_id_map)
    import_recycled_feed_records(recycled_id_map)

    print("Feed CSV 匯入完成。")


if __name__ == "__main__":
    main()
