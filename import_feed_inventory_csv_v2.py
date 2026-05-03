# import_feed_inventory_csv_v2.py
# KNH MMS - Feed / Inventory 正式版 CSV 匯入腳本 v2
#
# 目的：
# 1. 將 Airtable CSV 匯入 Supabase 正式版資料表
# 2. 建立 materials / stock_adjustments / purchase_records / recycled_materials / feed_records
# 3. 使用「開帳校正 + 進貨 - 打料」讓 material_stock_view 等於 Airtable 原料庫存表目前庫存
# 4. 所有 datetime / timestamp 一律以 Asia/Taipei / UTC+8 處理
#
# 使用方式：
# 1. 將此檔放在專案根目錄，與 main.py 同一層
# 2. 將 Airtable 匯出的 CSV 放在同一層
# 3. 執行：python import_feed_inventory_csv_v2.py

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from db.supabase_client import supabase


TAIPEI_TZ = ZoneInfo("Asia/Taipei")
BASE_DIR = Path(__file__).resolve().parent

TABLE_MATERIALS = "materials"
TABLE_STOCK_ADJUSTMENTS = "stock_adjustments"
TABLE_PURCHASE_RECORDS = "purchase_records"
TABLE_RECYCLED_MATERIALS = "recycled_materials"
TABLE_FEED_RECORDS = "feed_records"

SOURCE = "airtable_csv_v2"
SOURCE_OPENING = "airtable_opening_stock_v2"


@dataclass
class MaterialImportState:
    material_id_map: dict[str, str]
    bag_weight_map: dict[str, Decimal]
    airtable_current_bags: dict[str, int]
    airtable_current_kg: dict[str, Decimal]
    imported_purchase_bags: dict[str, int]
    imported_purchase_kg: dict[str, Decimal]
    imported_feed_bags: dict[str, int]
    imported_feed_kg: dict[str, Decimal]


# ============================================================
# 基礎工具
# ============================================================

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


def to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    text = clean_text(value).replace(",", "")
    if not text:
        return default
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return default


def decimal_to_db(value: Decimal | int | float | str | None) -> str:
    if value is None:
        return "0"
    try:
        return str(Decimal(str(value)))
    except Exception:
        return "0"


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
    CSV 中的日期時間視為台灣現場時間。
    寫入 Supabase timestamptz 時明確帶 +08:00。
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


def today_taipei_date() -> str:
    return datetime.now(TAIPEI_TZ).date().isoformat()


def stable_source_id(prefix: str, row: dict[str, str], index: int) -> str:
    """
    CSV 沒有 Airtable record id，因此用列內容產生穩定來源 ID。
    讓腳本重複執行時可以避免重複匯入。
    """
    parts = [prefix, str(index)]
    for key in sorted(row.keys()):
        parts.append(f"{key}={clean_text(row.get(key))}")
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def find_csv(keyword: str) -> Path:
    matches = sorted(BASE_DIR.glob(f"*{keyword}*.csv"))
    if not matches:
        raise FileNotFoundError(f"找不到包含「{keyword}」的 CSV，請確認檔案放在專案根目錄：{BASE_DIR}")
    return matches[0]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows: list[dict[str, str]] = []
        for row in reader:
            clean_row = {str(k).strip(): clean_text(v) for k, v in row.items() if k is not None}
            rows.append(clean_row)
        return rows


def record_exists(table: str, source: str, source_id: str) -> bool:
    res = (
        supabase.table(table)
        .select("id")
        .eq("source", source)
        .eq("source_airtable_record_id", source_id)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def material_name_candidates(value: str) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    return [text]


def find_material_id(name: str, material_id_map: dict[str, str]) -> str | None:
    for candidate in material_name_candidates(name):
        if candidate in material_id_map:
            return material_id_map[candidate]
    return None


def is_aux_source(source: str) -> bool:
    text = clean_text(source)
    return "母粒" in text or "輔助母粒" in text


# ============================================================
# 匯入：materials
# ============================================================

def import_materials() -> MaterialImportState:
    path = find_csv("原料庫存表")
    rows = read_csv_rows(path)

    imported = 0
    skipped = 0

    bag_weight_map: dict[str, Decimal] = {}
    airtable_current_bags: dict[str, int] = {}
    airtable_current_kg: dict[str, Decimal] = {}

    for index, row in enumerate(rows, start=1):
        material_name = clean_text(row.get("原料名稱"))
        if not material_name:
            skipped += 1
            continue

        bag_weight = to_decimal(row.get("單包規格(KG)"))
        current_bags = to_int(row.get("目前庫存(包)"))
        current_kg = to_decimal(row.get("目前庫存(KG)"))

        if current_kg == Decimal("0") and current_bags and bag_weight:
            current_kg = Decimal(current_bags) * bag_weight

        payload = {
            "material_name": material_name,
            "main_category": clean_text(row.get("大類")) or None,
            "material_type": clean_text(row.get("種類")) or None,
            "supplier": clean_text(row.get("供應商")) or None,
            "bag_weight_kg": decimal_to_db(bag_weight),
            "low_stock_threshold_bags": 3,
            "is_stock_managed": True,
            "is_active": True,
            "note": clean_text(row.get("庫存狀態")) or None,
            "source_airtable_record_id": stable_source_id("material", row, index),
        }

        supabase.table(TABLE_MATERIALS).upsert(payload, on_conflict="material_name").execute()
        imported += 1

        bag_weight_map[material_name] = bag_weight
        airtable_current_bags[material_name] = current_bags
        airtable_current_kg[material_name] = current_kg

    material_id_map = get_material_id_map()

    print(f"materials 匯入 / 更新完成：{imported} 筆，略過 {skipped} 筆")

    return MaterialImportState(
        material_id_map=material_id_map,
        bag_weight_map=bag_weight_map,
        airtable_current_bags=airtable_current_bags,
        airtable_current_kg=airtable_current_kg,
        imported_purchase_bags={},
        imported_purchase_kg={},
        imported_feed_bags={},
        imported_feed_kg={},
    )


def get_material_id_map() -> dict[str, str]:
    res = supabase.table(TABLE_MATERIALS).select("id, material_name").execute()
    data = res.data or []
    return {row["material_name"]: row["id"] for row in data if row.get("material_name")}


def get_material_by_name(name: str) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_MATERIALS)
        .select("*")
        .eq("material_name", name)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]


def add_sum_int(target: dict[str, int], key: str, value: int) -> None:
    target[key] = target.get(key, 0) + value


def add_sum_decimal(target: dict[str, Decimal], key: str, value: Decimal) -> None:
    target[key] = target.get(key, Decimal("0")) + value


# ============================================================
# 匯入：purchase_records
# ============================================================

def import_purchase_records(state: MaterialImportState) -> None:
    path = find_csv("進貨紀錄表")
    rows = read_csv_rows(path)

    inserted = 0
    skipped = 0
    missing_material = 0

    for index, row in enumerate(rows, start=1):
        source_id = stable_source_id("purchase", row, index)
        if record_exists(TABLE_PURCHASE_RECORDS, SOURCE, source_id):
            skipped += 1
            continue

        material_name = clean_text(row.get("原料名稱")) or clean_text(row.get("關聯原料"))
        material_id = find_material_id(material_name, state.material_id_map)

        if not material_id:
            print(f"[WARN] 進貨紀錄找不到原料：{material_name}，此筆略過。")
            missing_material += 1
            continue

        material = get_material_by_name(material_name) or {}
        supplier = clean_text(row.get("供應商")) or material.get("supplier")
        qty_bags = to_int(row.get("進貨數量(包)"))
        bag_weight = to_decimal(material.get("bag_weight_kg"), state.bag_weight_map.get(material_name, Decimal("0")))
        qty_kg = Decimal(qty_bags) * bag_weight if qty_bags and bag_weight else Decimal("0")
        purchase_date = parse_date(row.get("進貨日期")) or today_taipei_date()

        payload = {
            "purchase_date": purchase_date,
            "purchase_batch_no": clean_text(row.get("進貨批號")) or None,
            "material_id": material_id,
            "material_name": material_name,
            "supplier": supplier or None,
            "quantity_bags": qty_bags,
            "bag_weight_kg": decimal_to_db(bag_weight),
            "quantity_kg": decimal_to_db(qty_kg),
            "note": None,
            "created_by_user_id": None,
            "created_by_name": "Airtable CSV 匯入",
            "source": SOURCE,
            "source_airtable_record_id": source_id,
            "is_deleted": False,
        }

        supabase.table(TABLE_PURCHASE_RECORDS).insert(payload).execute()
        inserted += 1

        add_sum_int(state.imported_purchase_bags, material_name, qty_bags)
        add_sum_decimal(state.imported_purchase_kg, material_name, qty_kg)

    print(f"purchase_records 匯入完成：新增 {inserted} 筆，略過 {skipped} 筆，找不到原料 {missing_material} 筆")


# ============================================================
# 匯入：recycled_materials
# ============================================================

def import_recycled_materials_from_inventory_csv() -> dict[str, str]:
    path = find_csv("回用料庫存清單")
    rows = read_csv_rows(path)

    imported = 0
    skipped = 0

    for index, row in enumerate(rows, start=1):
        recycled_no = clean_text(row.get("回用料編號"))
        if not recycled_no:
            skipped += 1
            continue

        usage_status = clean_text(row.get("使用狀態")) or "在庫"
        is_used = ("已領用" in usage_status) or ("領用" in usage_status and "在庫" not in usage_status)
        is_scrapped = "報廢" in usage_status

        payload = {
            "recycled_no": recycled_no,
            "inbound_date": parse_date(row.get("入庫日期")),
            "weight_kg": decimal_to_db(to_decimal(row.get("重量(KG)"))),
            "material_type": clean_text(row.get("原料種類")) or None,
            "source_machine": clean_text(row.get("來源機台")) or None,
            "supplier": clean_text(row.get("供應商")) or None,
            "usage_status": usage_status,
            "is_used": is_used,
            "is_scrapped": is_scrapped,
            "note": None,
            "source_airtable_record_id": stable_source_id("recycled", row, index),
        }

        supabase.table(TABLE_RECYCLED_MATERIALS).upsert(payload, on_conflict="recycled_no").execute()
        imported += 1

    print(f"recycled_materials 匯入 / 更新完成：{imported} 筆，略過 {skipped} 筆")
    return get_recycled_id_map()


def get_recycled_id_map() -> dict[str, str]:
    res = supabase.table(TABLE_RECYCLED_MATERIALS).select("id, recycled_no").execute()
    data = res.data or []
    return {row["recycled_no"]: row["id"] for row in data if row.get("recycled_no")}


def ensure_recycled_material_from_feed_row(row: dict[str, str], recycled_id_map: dict[str, str]) -> str | None:
    recycled_no = clean_text(row.get("領用回用料")) or clean_text(row.get("繼承原料批號"))
    if not recycled_no:
        return None

    if recycled_no in recycled_id_map:
        return recycled_id_map[recycled_no]

    payload = {
        "recycled_no": recycled_no,
        "inbound_date": None,
        "weight_kg": decimal_to_db(to_decimal(row.get("重量(KG)"))),
        "material_type": clean_text(row.get("原料種類")) or None,
        "source_machine": None,
        "supplier": clean_text(row.get("供應商")) or None,
        "usage_status": "已領用",
        "is_used": True,
        "is_scrapped": False,
        "note": "由回用料打料紀錄 CSV 自動補建。",
        "source_airtable_record_id": stable_source_id("recycled_from_feed", row, 0),
    }

    created = supabase.table(TABLE_RECYCLED_MATERIALS).upsert(payload, on_conflict="recycled_no").execute()
    if created.data:
        recycled_id = created.data[0].get("id")
    else:
        recycled_id = get_recycled_id_map().get(recycled_no)

    if recycled_id:
        recycled_id_map[recycled_no] = recycled_id

    return recycled_id


# ============================================================
# 匯入：feed_records 乾燥打料
# ============================================================

def import_dry_feed_records(state: MaterialImportState) -> None:
    path = find_csv("乾燥打料紀錄表")
    rows = read_csv_rows(path)

    inserted = 0
    skipped = 0
    missing_material = 0

    for index, row in enumerate(rows, start=1):
        source_id = stable_source_id("dry_feed", row, index)
        if record_exists(TABLE_FEED_RECORDS, SOURCE, source_id):
            skipped += 1
            continue

        source_text = clean_text(row.get("原料來源")) or "新料"
        feed_type = "aux" if is_aux_source(source_text) else "new"
        material_name = clean_text(row.get("原料名稱")) or clean_text(row.get("領用新料"))
        material_id = find_material_id(material_name, state.material_id_map)

        if not material_id:
            print(f"[WARN] 乾燥打料紀錄找不到原料：{material_name}，此筆略過。")
            missing_material += 1
            continue

        machine_code = clean_text(row.get("機台選擇"))
        if not machine_code:
            print("[WARN] 乾燥打料紀錄缺少機台選擇，此筆略過。")
            skipped += 1
            continue

        qty_bags = to_int(row.get("領用數量(包)"), 1)
        bag_weight = to_decimal(row.get("單包規格(KG) (from 領用新料)"), state.bag_weight_map.get(material_name, Decimal("0")))
        weight_kg = to_decimal(row.get("重量(KG)"))

        if weight_kg == Decimal("0") and qty_bags and bag_weight:
            weight_kg = Decimal(qty_bags) * bag_weight

        payload = {
            "feed_type": feed_type,
            "batch_no": clean_text(row.get("原料批號")) or None,
            "feed_at": parse_datetime_taipei(row.get("日期")),
            "machine_code": machine_code,
            "material_id": material_id,
            "recycled_material_id": None,
            "material_name": material_name,
            "material_source": "輔助母粒" if feed_type == "aux" else "新料",
            "supplier": clean_text(row.get("供應商")) or None,
            "quantity_bags": qty_bags,
            "bag_weight_kg": decimal_to_db(bag_weight),
            "weight_kg": decimal_to_db(weight_kg),
            "operator_name": None,
            "note": None,
            "created_by_user_id": None,
            "created_by_name": "Airtable CSV 匯入",
            "source": SOURCE,
            "source_airtable_record_id": source_id,
            "is_deleted": False,
        }

        supabase.table(TABLE_FEED_RECORDS).insert(payload).execute()
        inserted += 1

        add_sum_int(state.imported_feed_bags, material_name, qty_bags)
        add_sum_decimal(state.imported_feed_kg, material_name, weight_kg)

    print(f"feed_records 乾燥打料匯入完成：新增 {inserted} 筆，略過 {skipped} 筆，找不到原料 {missing_material} 筆")


# ============================================================
# 匯入：feed_records 回用料
# ============================================================

def import_recycled_feed_records(recycled_id_map: dict[str, str]) -> None:
    path = find_csv("回用料打料紀錄表")
    rows = read_csv_rows(path)

    inserted = 0
    skipped = 0
    missing_recycled = 0

    for index, row in enumerate(rows, start=1):
        source_id = stable_source_id("recycled_feed", row, index)
        if record_exists(TABLE_FEED_RECORDS, SOURCE, source_id):
            skipped += 1
            continue

        recycled_id = ensure_recycled_material_from_feed_row(row, recycled_id_map)
        if not recycled_id:
            print("[WARN] 回用料打料紀錄找不到或無法建立回用料資料，此筆略過。")
            missing_recycled += 1
            continue

        machine_code = clean_text(row.get("機台選擇"))
        if not machine_code:
            print("[WARN] 回用料打料紀錄缺少機台選擇，此筆略過。")
            skipped += 1
            continue

        recycled_no = clean_text(row.get("領用回用料")) or clean_text(row.get("繼承原料批號"))
        material_type = clean_text(row.get("原料種類"))
        supplier = clean_text(row.get("供應商"))
        weight_kg = to_decimal(row.get("重量(KG)"))

        material_name = f"[{supplier}] {material_type}" if supplier else (material_type or recycled_no)

        payload = {
            "feed_type": "recycled",
            "batch_no": clean_text(row.get("繼承原料批號")) or recycled_no or None,
            "feed_at": parse_datetime_taipei(row.get("日期")),
            "machine_code": machine_code,
            "material_id": None,
            "recycled_material_id": recycled_id,
            "material_name": material_name,
            "material_source": "回用料",
            "supplier": supplier or None,
            "quantity_bags": None,
            "bag_weight_kg": None,
            "weight_kg": decimal_to_db(weight_kg),
            "operator_name": clean_text(row.get("填單人")) or None,
            "note": None,
            "created_by_user_id": None,
            "created_by_name": "Airtable CSV 匯入",
            "source": SOURCE,
            "source_airtable_record_id": source_id,
            "is_deleted": False,
        }

        created = supabase.table(TABLE_FEED_RECORDS).insert(payload).execute()
        inserted += 1

        if created.data:
            feed_record_id = created.data[0].get("id")
            supabase.table(TABLE_RECYCLED_MATERIALS).update(
                {
                    "usage_status": "已領用",
                    "is_used": True,
                    "used_feed_record_id": feed_record_id,
                }
            ).eq("id", recycled_id).execute()

    print(f"feed_records 回用料匯入完成：新增 {inserted} 筆，略過 {skipped} 筆，找不到回用料 {missing_recycled} 筆")


# ============================================================
# 開帳校正：stock_adjustments
# ============================================================

def create_opening_stock_adjustments(state: MaterialImportState) -> None:
    """
    重要：
    Airtable「原料庫存表」目前庫存是轉移當下的真實庫存。
    同時我們又匯入了歷史進貨與歷史打料紀錄。

    因此開帳不是直接等於 Airtable 目前庫存，而是：

    opening = Airtable目前庫存 - 匯入進貨 + 匯入打料

    讓 material_stock_view：
    opening + purchase - feed = Airtable目前庫存
    """
    inserted = 0
    skipped = 0

    for material_name, material_id in state.material_id_map.items():
        source_id = f"opening:{material_name}"

        if record_exists(TABLE_STOCK_ADJUSTMENTS, SOURCE_OPENING, source_id):
            skipped += 1
            continue

        target_bags = state.airtable_current_bags.get(material_name, 0)
        target_kg = state.airtable_current_kg.get(material_name, Decimal("0"))

        purchase_bags = state.imported_purchase_bags.get(material_name, 0)
        purchase_kg = state.imported_purchase_kg.get(material_name, Decimal("0"))

        feed_bags = state.imported_feed_bags.get(material_name, 0)
        feed_kg = state.imported_feed_kg.get(material_name, Decimal("0"))

        opening_bags = target_bags - purchase_bags + feed_bags
        opening_kg = target_kg - purchase_kg + feed_kg

        payload = {
            "material_id": material_id,
            "adjustment_type": "opening",
            "adjustment_date": today_taipei_date(),
            "quantity_bags": opening_bags,
            "quantity_kg": decimal_to_db(opening_kg),
            "reason": "Airtable 轉移開帳校正",
            "note": (
                f"目標庫存={target_bags}包/{target_kg}KG；"
                f"匯入進貨={purchase_bags}包/{purchase_kg}KG；"
                f"匯入打料={feed_bags}包/{feed_kg}KG。"
            ),
            "created_by_user_id": None,
            "created_by_name": "Airtable CSV 匯入",
            "source": SOURCE_OPENING,
            "source_airtable_record_id": source_id,
            "is_deleted": False,
        }

        supabase.table(TABLE_STOCK_ADJUSTMENTS).insert(payload).execute()
        inserted += 1

    print(f"stock_adjustments 開帳校正完成：新增 {inserted} 筆，略過 {skipped} 筆")


# ============================================================
# 匯入後檢查
# ============================================================

def print_stock_view_sample(limit: int = 20) -> None:
    try:
        res = (
            supabase.table("material_stock_view")
            .select("material_name, current_stock_bags, current_stock_kg, is_low_stock")
            .order("material_name", desc=False)
            .limit(limit)
            .execute()
        )
        rows = res.data or []

        print("\nmaterial_stock_view 檢查：")
        for row in rows:
            print(
                f"- {row.get('material_name')}: "
                f"{row.get('current_stock_bags')} 包 / "
                f"{row.get('current_stock_kg')} KG "
                f"低水位={row.get('is_low_stock')}"
            )
    except Exception as exc:
        print(f"[WARN] material_stock_view 檢查失敗：{exc}")


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("開始匯入 Feed / Inventory CSV v2 → Supabase")
    print(f"CSV 搜尋目錄：{BASE_DIR}")
    print("提醒：請確認你已先執行 Feed / Inventory 正式版 SQL v2。")
    print("-" * 72)

    state = import_materials()
    print("-" * 72)

    import_purchase_records(state)
    print("-" * 72)

    recycled_id_map = import_recycled_materials_from_inventory_csv()
    print("-" * 72)

    import_dry_feed_records(state)
    print("-" * 72)

    import_recycled_feed_records(recycled_id_map)
    print("-" * 72)

    create_opening_stock_adjustments(state)
    print("-" * 72)

    print_stock_view_sample()
    print("-" * 72)
    print("Feed / Inventory CSV v2 匯入完成。")
    print("請回 Supabase 查詢 material_stock_view，確認 current_stock_bags 是否接近 Airtable 原料庫存表目前庫存。")


if __name__ == "__main__":
    main()
