from typing import Any

from db.supabase_client import supabase


TABLE_ITEMS = "maintenance_items"
TABLE_RECORDS = "maintenance_records"
TABLE_NODES = "maintenance_nodes"


def get_maintenance_items(
    include_inactive: bool = False,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    """
    讀取保養項目。
    include_inactive=True 時包含已停用項目，供超級管理員項目管理頁使用。
    include_deleted=False 時排除已軟刪除項目。
    """
    query = supabase.table(TABLE_ITEMS).select("*")

    if not include_inactive:
        query = query.eq("is_active", True)

    if not include_deleted:
        query = query.eq("is_deleted", False)

    res = query.execute()
    rows = res.data or []

    def sort_key(row: dict[str, Any]):
        return (
            str(row.get("maintenance_type") or ""),
            str(row.get("main_category") or ""),
            str(row.get("sub_category") or ""),
            str(row.get("machine_area") or ""),
            int(row.get("sort_order") or 999),
            str(row.get("item_name") or ""),
        )

    return sorted(rows, key=sort_key)


def get_active_maintenance_items() -> list[dict[str, Any]]:
    """
    讀取啟用中的保養項目。
    已排除軟刪除項目，依 sort_order 由小到大排序。
    """
    res = (
        supabase.table(TABLE_ITEMS)
        .select("*")
        .eq("is_active", True)
        .eq("is_deleted", False)
        .order("sort_order", desc=False)
        .execute()
    )

    return res.data or []


def get_maintenance_item_by_id(item_id: str) -> dict[str, Any] | None:
    """
    依 id 讀取單一保養項目。
    """
    res = (
        supabase.table(TABLE_ITEMS)
        .select("*")
        .eq("id", item_id)
        .limit(1)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def get_maintenance_nodes(
    include_inactive: bool = True,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    """
    讀取保養節點樹。
    管理頁需要包含停用節點；預設排除已刪除節點。
    """
    query = supabase.table(TABLE_NODES).select("*")

    if not include_inactive:
        query = query.eq("is_active", True)

    if not include_deleted:
        query = query.eq("is_deleted", False)

    res = query.execute()
    rows = res.data or []

    def sort_key(row: dict[str, Any]):
        return (
            str(row.get("maintenance_type") or ""),
            int(row.get("node_level") or 0),
            int(row.get("sort_order") or 999),
            str(row.get("node_name") or ""),
        )

    return sorted(rows, key=sort_key)


def get_maintenance_node_by_id(node_id: str) -> dict[str, Any] | None:
    """
    依 id 讀取單一保養節點。
    """
    res = (
        supabase.table(TABLE_NODES)
        .select("*")
        .eq("id", node_id)
        .limit(1)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def get_root_maintenance_node(maintenance_type: str) -> dict[str, Any] | None:
    """
    讀取指定類型的根節點，例如：清潔 / 耗材更換。
    """
    rows = get_maintenance_nodes(include_inactive=True, include_deleted=False)
    for row in rows:
        if (
            row.get("maintenance_type") == maintenance_type
            and row.get("parent_id") is None
            and int(row.get("node_level") or 0) == 0
        ):
            return row
    return None


def get_child_maintenance_node(
    parent_id: str,
    node_name: str,
    include_inactive: bool = True,
) -> dict[str, Any] | None:
    """
    讀取同父節點底下的指定子節點。
    """
    rows = get_maintenance_nodes(include_inactive=include_inactive, include_deleted=False)
    target_name = str(node_name or "").strip()
    for row in rows:
        if row.get("parent_id") == parent_id and str(row.get("node_name") or "").strip() == target_name:
            return row
    return None


def create_maintenance_node(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    新增保養節點。
    """
    res = (
        supabase.table(TABLE_NODES)
        .insert(payload)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def get_recent_maintenance_records(limit: int = 10) -> list[dict[str, Any]]:
    """
    讀取最近保養紀錄。
    同時帶出 maintenance_items 的項目資料。
    已排除軟刪除紀錄。
    """
    res = (
        supabase.table(TABLE_RECORDS)
        .select(
            """
            *,
            maintenance_items (
                id,
                item_name,
                maintenance_type,
                main_category,
                sub_category,
                machine_area
            )
            """
        )
        .eq("is_deleted", False)
        .order("executed_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    return res.data or []


def get_records_by_item_id(item_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """
    讀取單一保養項目的歷史紀錄。
    已排除軟刪除紀錄。
    """
    res = (
        supabase.table(TABLE_RECORDS)
        .select(
            """
            *,
            maintenance_items (
                id,
                item_name,
                maintenance_type,
                main_category,
                sub_category,
                machine_area
            )
            """
        )
        .eq("maintenance_item_id", item_id)
        .eq("is_deleted", False)
        .order("executed_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    return res.data or []


def create_maintenance_record(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    新增一筆保養紀錄。
    """
    res = (
        supabase.table(TABLE_RECORDS)
        .insert(payload)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def soft_delete_maintenance_record(record_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    軟刪除保養紀錄，不做實體 delete。
    payload 應包含：
    is_deleted, deleted_at, deleted_by_user_id, deleted_by_name, delete_reason
    """
    res = (
        supabase.table(TABLE_RECORDS)
        .update(payload)
        .eq("id", record_id)
        .eq("is_deleted", False)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def create_maintenance_item(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    新增保養項目。
    用於：新增清潔項目 / 新增耗材項目。
    """
    res = (
        supabase.table(TABLE_ITEMS)
        .insert(payload)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def update_maintenance_item(item_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    更新保養項目。
    用於：編輯週期、停用項目、調整排序。
    """
    res = (
        supabase.table(TABLE_ITEMS)
        .update(payload)
        .eq("id", item_id)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]
