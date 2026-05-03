from typing import Any

from db.supabase_client import supabase


TABLE_USERS = "users"
TABLE_PASSWORD_RESET_REQUESTS = "password_reset_requests"


def get_user_by_employee_id(employee_id: str) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_USERS)
        .select("*")
        .eq("employee_id", employee_id)
        .limit(1)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def update_last_login(user_id: str, login_at: str) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_USERS)
        .update({"last_login_at": login_at})
        .eq("id", user_id)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def update_password_after_first_login(
    user_id: str,
    new_password_hash: str,
    password_updated_at: str,
) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_USERS)
        .update(
            {
                "password_hash": new_password_hash,
                "is_first_login": False,
                "must_change_password": False,
                "password_updated_at": password_updated_at,
            }
        )
        .eq("id", user_id)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def update_quick_shortcuts(user_id: str, shortcuts: list[str]) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_USERS)
        .update({"quick_shortcuts": shortcuts})
        .eq("id", user_id)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]


def create_password_reset_request(payload: dict[str, Any]) -> dict[str, Any] | None:
    res = (
        supabase.table(TABLE_PASSWORD_RESET_REQUESTS)
        .insert(payload)
        .execute()
    )

    if not res.data:
        return None

    return res.data[0]