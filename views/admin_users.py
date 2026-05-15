# =====================================================
# KNH MMS v2
# File: views/admin_users.py
# File Revision: 2026-05-15-admin-users-r1
# Status: phase 2B users and permissions page
# Last Updated: 2026-05-15 Asia/Taipei
#
# Purpose:
# - /admin/users 使用者與權限管理頁。
# - 讓超級管理員查看使用者清單、啟用狀態、角色、基本權限與有效 Session 數量。
#
# Major Changes in This Revision:
# - 新增使用者清單與摘要卡。
# - 新增角色 / 狀態 / 關鍵字篩選。
# - 新增編輯面板，可更新角色、啟用狀態與既有四個權限布林欄位。
# - 加入防呆提示：不處理新增使用者、密碼重設與強制登出。
#
# Notes:
# - Flet 0.84。
# - 不使用 page.push_route()。
# - 手機 Web 關鍵按鈕使用原生 text / icon 按鈕，不使用 content=Row(...)。
# - 此頁不修改 auth_session_service.py，不影響 12 小時免重登正式流程。
# =====================================================

from __future__ import annotations

import threading
import time
from typing import Any

import flet as ft

from services.admin_user_service import (
    ALLOWED_ROLES,
    load_admin_users_page_data,
    update_admin_user_from_form,
)


BG = "#F6F8FB"
CARD_BG = "#FFFFFF"
TEXT = "#1E293B"
TEXT_MUTED = "#64748B"
BORDER = "#E2E8F0"

BLUE = "#2F80ED"
BLUE_SOFT = "#E5F0FF"
BLUE_BORDER = "#B0D0FF"
BLUE_BTN = "#4F7FB8"

PURPLE = "#8B5CF6"
PURPLE_SOFT = "#F3E8FF"
PURPLE_BORDER = "#D8B4FE"

ORANGE = "#F97316"
ORANGE_SOFT = "#FFF7ED"
ORANGE_BORDER = "#FDBA74"
ORANGE_BTN = "#C96D32"

GREEN = "#059669"
GREEN_SOFT = "#ECFDF5"
GREEN_BORDER = "#A7F3D0"
GREEN_BTN = "#3F8F5A"

RED = "#DC2626"
RED_SOFT = "#FEE2E2"
RED_BORDER = "#FCA5A5"

GRAY_SOFT = "#F1F5F9"

MOBILE_WIDTH = 920


PERMISSION_LABELS = {
    "can_view_all_tasks": "可看全部交接待辦",
    "can_access_reports": "可進報表中心",
    "can_access_spinneret": "可進噴頭狀態",
    "can_access_maintenance": "可進保養紀錄",
}


def AdminUsersContent(page: ft.Page) -> ft.Control:
    if not hasattr(page, "session_data") or not isinstance(page.session_data, dict):
        page.session_data = {}

    view_token = f"admin-users-{time.time_ns()}"
    page.session_data["_admin_users_view_token"] = view_token
    ui_lock = threading.RLock()

    state: dict[str, Any] = {
        "loading": True,
        "busy": False,
        "sync_status": "loading",
        "sync_message": "使用者資料同步中",
        "sync_badge_visible": True,
        "error_message": "",
        "users": [],
        "summary": {
            "total_user_count": 0,
            "active_user_count": 0,
            "inactive_user_count": 0,
            "active_super_admin_count": 0,
            "must_change_password_count": 0,
            "active_session_count": 0,
            "role_counts": {},
        },
        "generated_at": "-",
        "status_filter": "all",
        "role_filter": "all",
        "query": "",
        "selected_user_id": "",
        "form": {},
    }

    search_field = ft.TextField(
        hint_text="搜尋姓名或員工編號",
        bgcolor="#FFFFFF",
        border_color=BORDER,
        focused_border_color=BLUE,
        border_radius=12,
        text_size=14,
        height=46,
        content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
    )

    main_host = ft.Container(expand=True)
    root = ft.Container(expand=True, bgcolor=BG, content=main_host)

    # =====================================================
    # Helpers
    # =====================================================
    def session_get(key: str, default=None):
        try:
            return page.session_data.get(key, default)
        except Exception:
            return default

    def current_user_id() -> str:
        return str(session_get("user_id") or session_get("user_record_id") or "").strip()

    def current_user_role() -> str:
        return str(session_get("role") or "").strip()

    def is_super_admin() -> bool:
        return current_user_role() == "超級管理員"

    def is_active_view() -> bool:
        route = str(getattr(page, "route", "") or "")
        return (
            page.session_data.get("_admin_users_view_token") == view_token
            and (not route or route.startswith("/admin/users"))
        )

    def safe_update() -> None:
        if not is_active_view():
            return
        try:
            with ui_lock:
                if is_active_view():
                    page.update()
        except Exception as exc:
            print("admin_users page.update failed:", repr(exc), flush=True)

    def navigate(route: str) -> None:
        nav = session_get("_navigate")
        if callable(nav):
            nav(route)
            return
        page.go(route)

    def show_snack(message: str, success: bool = True) -> None:
        snack = ft.SnackBar(
            content=ft.Text(str(message), color="#FFFFFF", weight=ft.FontWeight.W_600),
            bgcolor=GREEN if success else RED,
            duration=3000,
        )
        try:
            page.overlay.append(snack)
        except Exception:
            pass
        snack.open = True
        safe_update()

    def set_sync_state(status: str, message: str, visible: bool = True) -> None:
        state["sync_status"] = status
        state["sync_message"] = message
        state["sync_badge_visible"] = visible
        state["loading"] = status == "loading"

    def hide_sync_badge_later(delay_seconds: float = 3.0) -> None:
        version = time.time()
        state["sync_hide_version"] = version

        def worker():
            time.sleep(delay_seconds)
            if not is_active_view():
                return
            if state.get("sync_hide_version") != version:
                return
            if state.get("sync_status") == "success":
                state["sync_badge_visible"] = False
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def close_selected_user() -> None:
        state["selected_user_id"] = ""
        state["form"] = {}
        rebuild()

    def selected_user() -> dict[str, Any] | None:
        selected_id = str(state.get("selected_user_id") or "")
        if not selected_id:
            return None
        for user in state.get("users") or []:
            if str(user.get("id") or "") == selected_id:
                return user
        return None

    def open_edit_user(user: dict[str, Any]) -> None:
        state["selected_user_id"] = str(user.get("id") or "")
        state["form"] = {
            "role": user.get("role") or "操作員",
            "is_active": bool(user.get("is_active")),
            "can_view_all_tasks": bool(user.get("can_view_all_tasks")),
            "can_access_reports": bool(user.get("can_access_reports")),
            "can_access_spinneret": bool(user.get("can_access_spinneret")),
            "can_access_maintenance": bool(user.get("can_access_maintenance")),
        }
        rebuild()

    def set_status_filter(value: str) -> None:
        state["status_filter"] = value
        rebuild()

    def set_role_filter(value: str) -> None:
        state["role_filter"] = value
        rebuild()

    def apply_search(e=None) -> None:
        state["query"] = str(search_field.value or "").strip()
        rebuild()

    def clear_search(e=None) -> None:
        search_field.value = ""
        state["query"] = ""
        rebuild()

    def set_form_value(key: str, value: Any) -> None:
        form = state.setdefault("form", {})
        form[key] = value
        rebuild()

    def toggle_permission(key: str) -> None:
        form = state.setdefault("form", {})
        form[key] = not bool(form.get(key))
        rebuild()

    def refresh_data(show_loading: bool = True) -> None:
        if not is_super_admin():
            return

        if show_loading:
            set_sync_state("loading", "使用者資料同步中", visible=True)
            rebuild()

        def worker():
            try:
                result = load_admin_users_page_data()
                if not is_active_view():
                    return

                data = result.data or {}
                state["users"] = data.get("users", []) or []
                state["summary"] = data.get("summary", state["summary"]) or state["summary"]
                state["generated_at"] = data.get("generated_at", "-")

                if result.ok:
                    state["error_message"] = ""
                    set_sync_state("success", "使用者資料已同步", visible=True)
                else:
                    state["error_message"] = result.message
                    set_sync_state("error", "使用者資料同步失敗", visible=True)

                # 若更新後找不到原本選取的使用者，關閉編輯面板。
                if state.get("selected_user_id"):
                    exists = any(str(user.get("id") or "") == str(state.get("selected_user_id")) for user in state["users"])
                    if not exists:
                        state["selected_user_id"] = ""
                        state["form"] = {}

                rebuild()
                if result.ok:
                    hide_sync_badge_later(3.0)

            except Exception as exc:
                if not is_active_view():
                    return
                state["error_message"] = f"使用者資料載入失敗：{exc}"
                set_sync_state("error", "使用者資料同步失敗", visible=True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def save_user_changes(e=None) -> None:
        if state.get("busy"):
            show_snack("系統正在處理上一個動作，請稍候。", success=False)
            return

        user = selected_user()
        if not user:
            show_snack("尚未選取使用者。", success=False)
            return

        state["busy"] = True
        set_sync_state("loading", "正在更新使用者權限", visible=True)
        rebuild()

        user_id = str(user.get("id") or "")
        form_data = dict(state.get("form") or {})

        def worker():
            try:
                result = update_admin_user_from_form(
                    user_id=user_id,
                    form_data=form_data,
                    current_user_id=current_user_id(),
                    current_user_role=current_user_role(),
                )
                if not is_active_view():
                    return

                if not result.ok:
                    set_sync_state("error", result.message, visible=True)
                    show_snack(result.message, success=False)
                    state["busy"] = False
                    rebuild()
                    return

                show_snack(result.message or "使用者權限已更新。", success=True)
                state["busy"] = False
                refresh_data(show_loading=False)
                set_sync_state("success", result.message or "使用者權限已更新", visible=True)

            except Exception as exc:
                if not is_active_view():
                    return
                state["busy"] = False
                set_sync_state("error", f"更新失敗：{exc}", visible=True)
                show_snack(f"更新失敗：{exc}", success=False)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    # =====================================================
    # UI shared
    # =====================================================
    def card(content: ft.Control, padding: int = 16, border_color: str = BORDER, bgcolor: str = CARD_BG) -> ft.Container:
        return ft.Container(
            width=float("inf"),
            bgcolor=bgcolor,
            border=ft.border.all(1, border_color),
            border_radius=18,
            padding=padding,
            content=content,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=10,
                color="#06000000",
                offset=ft.Offset(0, 2),
            ),
        )

    def primary_button(label: str, icon, on_click=None, bgcolor: str = BLUE_BTN, disabled: bool = False) -> ft.ElevatedButton:
        return ft.ElevatedButton(
            label,
            icon=icon,
            bgcolor=bgcolor,
            color="#FFFFFF",
            height=44,
            disabled=disabled,
            on_click=on_click,
        )

    def outline_button(label: str, icon, on_click=None, color: str = BLUE_BTN, disabled: bool = False) -> ft.OutlinedButton:
        return ft.OutlinedButton(
            label,
            icon=icon,
            height=44,
            disabled=disabled,
            on_click=on_click,
            style=ft.ButtonStyle(color=color),
        )

    def section_title(title: str, subtitle: str | None = None) -> ft.Column:
        controls: list[ft.Control] = [ft.Text(title, size=20, weight=ft.FontWeight.BOLD, color=TEXT)]
        if subtitle:
            controls.append(ft.Text(subtitle, size=13, color=TEXT_MUTED, max_lines=3))
        return ft.Column(spacing=4, controls=controls)

    def sync_badge() -> ft.Control:
        if not state.get("sync_badge_visible"):
            return ft.Container(height=0, visible=False)

        status = state.get("sync_status") or "success"
        if status == "loading":
            fg, bg, border = BLUE_BTN, BLUE_SOFT, BLUE_BORDER
            icon = ft.ProgressRing(width=15, height=15, stroke_width=2, color=fg)
        elif status == "error":
            fg, bg, border = RED, RED_SOFT, RED_BORDER
            icon = ft.Icon(ft.Icons.ERROR_OUTLINE, size=17, color=fg)
        else:
            fg, bg, border = GREEN, GREEN_SOFT, GREEN_BORDER
            icon = ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=17, color=fg)

        return ft.Container(
            height=34,
            border_radius=17,
            bgcolor=bg,
            border=ft.border.all(1, border),
            padding=ft.padding.symmetric(horizontal=14),
            alignment=ft.Alignment(0, 0),
            content=ft.Row(
                tight=True,
                spacing=7,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    icon,
                    ft.Text(str(state.get("sync_message") or "資料已同步"), size=12, color=fg, weight=ft.FontWeight.W_600),
                ],
            ),
        )

    def breadcrumb() -> ft.Control:
        def item(label: str, route: str | None = None, active: bool = False) -> ft.Control:
            return ft.Container(
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                border_radius=8,
                bgcolor=BLUE_SOFT if active else "transparent",
                ink=bool(route),
                on_click=(lambda _: navigate(route)) if route else None,
                content=ft.Text(
                    label,
                    size=12,
                    color=BLUE_BTN if active or route else TEXT_MUTED,
                    weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_500,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            )

        return ft.Row(
            wrap=True,
            spacing=2,
            run_spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                item("系統控制中心", "/admin"),
                ft.Text(">", size=12, color=TEXT_MUTED),
                item("使用者與權限", active=True),
            ],
        )

    def build_header(is_mobile: bool) -> ft.Control:
        return ft.Column(
            spacing=10,
            controls=[
                breadcrumb(),
                ft.Row(
                    spacing=14,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Container(
                            width=58,
                            height=58,
                            border_radius=16,
                            bgcolor=BLUE_SOFT,
                            alignment=ft.Alignment(0, 0),
                            content=ft.Icon(ft.Icons.GROUP_OUTLINED, size=31, color=BLUE_BTN),
                        ),
                        ft.Column(
                            expand=True,
                            spacing=5,
                            controls=[
                                ft.Text("使用者與權限", size=26 if is_mobile else 28, weight=ft.FontWeight.BOLD, color=TEXT, max_lines=2),
                                ft.Text("管理帳號啟用狀態、角色與既有權限欄位；第一版不處理新增帳號、密碼重設與強制登出。", size=14, color=TEXT_MUTED, max_lines=3),
                            ],
                        ),
                    ],
                ),
                sync_badge(),
            ],
        )

    def metric_card(title: str, value: Any, unit: str, icon, color: str, soft: str, border: str, caption: str = "") -> ft.Control:
        return card(
            padding=16,
            border_color=border,
            content=ft.Row(
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=52,
                        height=52,
                        border_radius=16,
                        bgcolor=soft,
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(icon, color=color, size=27),
                    ),
                    ft.Column(
                        expand=True,
                        spacing=3,
                        controls=[
                            ft.Text(title, size=13, color=TEXT_MUTED, weight=ft.FontWeight.W_600),
                            ft.Row(
                                tight=True,
                                spacing=6,
                                vertical_alignment=ft.CrossAxisAlignment.END,
                                controls=[
                                    ft.Text(str(value), size=26, weight=ft.FontWeight.BOLD, color=TEXT),
                                    ft.Text(unit, size=12, color=TEXT_MUTED),
                                ],
                            ),
                            ft.Text(caption, size=11, color=TEXT_MUTED, visible=bool(caption)),
                        ],
                    ),
                ],
            ),
        )

    def build_summary_cards(is_mobile: bool) -> ft.Control:
        summary = state.get("summary") or {}
        cards = [
            metric_card("使用者總數", summary.get("total_user_count", 0), "人", ft.Icons.GROUP_OUTLINED, BLUE_BTN, BLUE_SOFT, BLUE_BORDER, "users 主檔"),
            metric_card("啟用帳號", summary.get("active_user_count", 0), "人", ft.Icons.CHECK_CIRCLE_OUTLINE, GREEN, GREEN_SOFT, GREEN_BORDER, "is_active = true"),
            metric_card("需改密碼", summary.get("must_change_password_count", 0), "人", ft.Icons.LOCK_RESET_OUTLINED, ORANGE_BTN, ORANGE_SOFT, ORANGE_BORDER, "首次登入或強制改密碼"),
            metric_card("有效 Session", summary.get("active_session_count", 0), "筆", ft.Icons.PERSON_OUTLINE, PURPLE, PURPLE_SOFT, PURPLE_BORDER, "只顯示，不強制登出"),
        ]

        if is_mobile:
            return ft.Column(
                spacing=10,
                controls=[
                    ft.Row(spacing=10, controls=[ft.Container(expand=True, content=cards[0]), ft.Container(expand=True, content=cards[1])]),
                    ft.Row(spacing=10, controls=[ft.Container(expand=True, content=cards[2]), ft.Container(expand=True, content=cards[3])]),
                ],
            )

        return ft.Row(spacing=12, controls=[ft.Container(expand=True, content=item) for item in cards])

    def role_color(role: str) -> tuple[str, str, str]:
        if role == "超級管理員":
            return RED_SOFT, RED, RED_BORDER
        if role == "部門主管":
            return PURPLE_SOFT, PURPLE, PURPLE_BORDER
        if role == "組長/副組長":
            return BLUE_SOFT, BLUE_BTN, BLUE_BORDER
        if role == "部門外成員":
            return ORANGE_SOFT, ORANGE_BTN, ORANGE_BORDER
        return GRAY_SOFT, TEXT_MUTED, BORDER

    def badge(label: str, bg: str, fg: str, border: str) -> ft.Container:
        return ft.Container(
            height=28,
            padding=ft.padding.symmetric(horizontal=10),
            border_radius=14,
            bgcolor=bg,
            border=ft.border.all(1, border),
            alignment=ft.Alignment(0, 0),
            content=ft.Text(label, size=12, color=fg, weight=ft.FontWeight.W_600, max_lines=1),
        )

    def role_badge(role: str) -> ft.Container:
        bg, fg, border = role_color(role)
        return badge(role or "-", bg, fg, border)

    def active_badge(is_active: bool) -> ft.Container:
        return badge("啟用" if is_active else "停用", GREEN_SOFT if is_active else RED_SOFT, GREEN if is_active else RED, GREEN_BORDER if is_active else RED_BORDER)

    def bool_badge(label: str, value: bool) -> ft.Container:
        return badge(label if value else f"無{label}", BLUE_SOFT if value else GRAY_SOFT, BLUE_BTN if value else TEXT_MUTED, BLUE_BORDER if value else BORDER)

    def filter_chip(label: str, selected: bool, on_click, color: str = BLUE_BTN) -> ft.Container:
        return ft.Container(
            height=34,
            padding=ft.padding.symmetric(horizontal=12),
            border_radius=17,
            bgcolor=BLUE_SOFT if selected else "#FFFFFF",
            border=ft.border.all(1, color if selected else BORDER),
            ink=True,
            on_click=on_click,
            content=ft.Text(label, size=13, color=color if selected else TEXT_MUTED, weight=ft.FontWeight.W_600),
        )

    def build_filters() -> ft.Control:
        role_chips = [
            filter_chip("全部角色", state.get("role_filter") == "all", lambda e: set_role_filter("all")),
        ]
        for role in ALLOWED_ROLES:
            role_chips.append(filter_chip(role, state.get("role_filter") == role, lambda e, r=role: set_role_filter(r)))

        return card(
            padding=16,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.FILTER_ALT_OUTLINED, size=22, color=BLUE_BTN),
                            section_title("篩選使用者", "可依角色、啟用狀態與姓名 / 員工編號搜尋。"),
                        ],
                    ),
                    ft.Row(
                        wrap=True,
                        spacing=8,
                        run_spacing=8,
                        controls=[
                            filter_chip("全部狀態", state.get("status_filter") == "all", lambda e: set_status_filter("all")),
                            filter_chip("只看啟用", state.get("status_filter") == "active", lambda e: set_status_filter("active"), GREEN),
                            filter_chip("只看停用", state.get("status_filter") == "inactive", lambda e: set_status_filter("inactive"), RED),
                        ],
                    ),
                    ft.Row(wrap=True, spacing=8, run_spacing=8, controls=role_chips),
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.Container(expand=True, content=search_field),
                            primary_button("搜尋", ft.Icons.SEARCH, apply_search, bgcolor=BLUE_BTN, disabled=state.get("busy")),
                            outline_button("清除", ft.Icons.CLEAR, clear_search, color=TEXT_MUTED, disabled=state.get("busy")),
                        ],
                    ),
                ],
            ),
        )

    def filtered_users() -> list[dict[str, Any]]:
        users = list(state.get("users") or [])

        status_filter = str(state.get("status_filter") or "all")
        if status_filter == "active":
            users = [user for user in users if bool(user.get("is_active"))]
        elif status_filter == "inactive":
            users = [user for user in users if not bool(user.get("is_active"))]

        role_filter = str(state.get("role_filter") or "all")
        if role_filter != "all":
            users = [user for user in users if str(user.get("role") or "") == role_filter]

        query = str(state.get("query") or "").strip().casefold()
        if query:
            users = [
                user for user in users
                if query in str(user.get("name") or "").casefold()
                or query in str(user.get("employee_id") or "").casefold()
            ]

        return users

    def build_user_card(user: dict[str, Any]) -> ft.Control:
        permission_badges = [
            bool_badge("報表", bool(user.get("can_access_reports"))),
            bool_badge("噴頭", bool(user.get("can_access_spinneret"))),
            bool_badge("保養", bool(user.get("can_access_maintenance"))),
            bool_badge("全部待辦", bool(user.get("can_view_all_tasks"))),
        ]

        return card(
            padding=16,
            border_color=BLUE_BORDER if str(user.get("id") or "") == str(state.get("selected_user_id") or "") else BORDER,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=48,
                                height=48,
                                border_radius=14,
                                bgcolor=BLUE_SOFT if user.get("is_active") else GRAY_SOFT,
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(ft.Icons.PERSON_OUTLINE, color=BLUE_BTN if user.get("is_active") else TEXT_MUTED, size=25),
                            ),
                            ft.Column(
                                expand=True,
                                spacing=3,
                                controls=[
                                    ft.Text(str(user.get("name") or "-"), size=17, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ft.Text(f"員工編號：{user.get('employee_id') or '-'}｜班別：{user.get('shift') or '-'}", size=13, color=TEXT_MUTED),
                                ],
                            ),
                            active_badge(bool(user.get("is_active"))),
                        ],
                    ),
                    ft.Row(
                        wrap=True,
                        spacing=8,
                        run_spacing=8,
                        controls=[
                            role_badge(str(user.get("role") or "-")),
                            badge(str(user.get("password_state_label") or "-"), ORANGE_SOFT if user.get("must_change_password") or user.get("is_first_login") else GREEN_SOFT, ORANGE_BTN if user.get("must_change_password") or user.get("is_first_login") else GREEN, ORANGE_BORDER if user.get("must_change_password") or user.get("is_first_login") else GREEN_BORDER),
                            badge(f"Session {user.get('active_session_count', 0)}", PURPLE_SOFT, PURPLE, PURPLE_BORDER),
                        ],
                    ),
                    ft.Row(wrap=True, spacing=8, run_spacing=8, controls=permission_badges),
                    ft.Container(
                        bgcolor="#F8FAFC",
                        border_radius=12,
                        padding=12,
                        content=ft.ResponsiveRow(
                            columns=12,
                            spacing=8,
                            run_spacing=8,
                            controls=[
                                ft.Container(
                                    col={"xs": 12, "md": 4},
                                    content=ft.Column(spacing=2, controls=[
                                        ft.Text("最近登入", size=12, color=TEXT_MUTED),
                                        ft.Text(str(user.get("last_login_at_label") or "-"), size=13, color=TEXT, weight=ft.FontWeight.W_600),
                                    ]),
                                ),
                                ft.Container(
                                    col={"xs": 12, "md": 4},
                                    content=ft.Column(spacing=2, controls=[
                                        ft.Text("密碼更新", size=12, color=TEXT_MUTED),
                                        ft.Text(str(user.get("password_updated_at_label") or "-"), size=13, color=TEXT, weight=ft.FontWeight.W_600),
                                    ]),
                                ),
                                ft.Container(
                                    col={"xs": 12, "md": 4},
                                    content=ft.Column(spacing=2, controls=[
                                        ft.Text("資料更新", size=12, color=TEXT_MUTED),
                                        ft.Text(str(user.get("updated_at_label") or "-"), size=13, color=TEXT, weight=ft.FontWeight.W_600),
                                    ]),
                                ),
                            ],
                        ),
                    ),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            outline_button("編輯權限", ft.Icons.EDIT_OUTLINED, lambda e, row=user: open_edit_user(row), color=BLUE_BTN, disabled=state.get("busy")),
                        ],
                    ),
                ],
            ),
        )

    def role_select_chip(role: str) -> ft.Container:
        form = state.get("form") or {}
        selected = str(form.get("role") or "") == role
        bg, fg, border = role_color(role)
        return ft.Container(
            height=36,
            padding=ft.padding.symmetric(horizontal=12),
            border_radius=18,
            bgcolor=bg if selected else "#FFFFFF",
            border=ft.border.all(1, fg if selected else BORDER),
            ink=True,
            on_click=lambda e, r=role: set_form_value("role", r),
            content=ft.Text(role, size=13, color=fg if selected else TEXT_MUTED, weight=ft.FontWeight.W_700 if selected else ft.FontWeight.W_600),
        )

    def active_select_chip(value: bool, label: str) -> ft.Container:
        form = state.get("form") or {}
        selected = bool(form.get("is_active")) == value
        color = GREEN if value else RED
        soft = GREEN_SOFT if value else RED_SOFT
        border = GREEN_BORDER if value else RED_BORDER
        return ft.Container(
            height=36,
            padding=ft.padding.symmetric(horizontal=12),
            border_radius=18,
            bgcolor=soft if selected else "#FFFFFF",
            border=ft.border.all(1, color if selected else BORDER),
            ink=True,
            on_click=lambda e, v=value: set_form_value("is_active", v),
            content=ft.Text(label, size=13, color=color if selected else TEXT_MUTED, weight=ft.FontWeight.W_700 if selected else ft.FontWeight.W_600),
        )

    def permission_chip(key: str) -> ft.Container:
        form = state.get("form") or {}
        selected = bool(form.get(key))
        return ft.Container(
            padding=ft.padding.symmetric(horizontal=12, vertical=9),
            border_radius=16,
            bgcolor=BLUE_SOFT if selected else "#FFFFFF",
            border=ft.border.all(1, BLUE_BTN if selected else BORDER),
            ink=True,
            on_click=lambda e, k=key: toggle_permission(k),
            content=ft.Row(
                tight=True,
                spacing=7,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE if selected else ft.Icons.RADIO_BUTTON_UNCHECKED, size=16, color=BLUE_BTN if selected else TEXT_MUTED),
                    ft.Text(PERMISSION_LABELS.get(key, key), size=13, color=BLUE_BTN if selected else TEXT_MUTED, weight=ft.FontWeight.W_600),
                ],
            ),
        )

    def build_edit_panel() -> ft.Control:
        user = selected_user()
        if not user:
            return card(
                padding=18,
                content=ft.Column(
                    spacing=12,
                    controls=[
                        ft.Row(
                            spacing=10,
                            controls=[
                                ft.Icon(ft.Icons.INFO_OUTLINE, color=BLUE_BTN, size=22),
                                ft.Text("尚未選取使用者", size=18, weight=ft.FontWeight.BOLD, color=TEXT),
                            ],
                        ),
                        ft.Text("請從左側或上方清單選擇一位使用者，再編輯角色、啟用狀態與基本權限。", size=13, color=TEXT_MUTED),
                    ],
                ),
            )

        form = state.get("form") or {}
        is_self = str(user.get("id") or "") == current_user_id()

        warnings: list[ft.Control] = []
        if is_self:
            warnings.append(
                ft.Container(
                    bgcolor=ORANGE_SOFT,
                    border=ft.border.all(1, ORANGE_BORDER),
                    border_radius=12,
                    padding=12,
                    content=ft.Text("你正在編輯目前登入中的自己；系統會阻擋停用自己或把自己降為非超級管理員。", size=12, color="#9A4A12", weight=ft.FontWeight.W_600),
                )
            )

        return card(
            padding=18,
            border_color=BLUE_BORDER,
            content=ft.Column(
                spacing=14,
                controls=[
                    ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=48,
                                height=48,
                                border_radius=14,
                                bgcolor=BLUE_SOFT,
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED, size=25, color=BLUE_BTN),
                            ),
                            ft.Column(
                                expand=True,
                                spacing=3,
                                controls=[
                                    ft.Text(f"編輯：{user.get('name') or '-'}", size=19, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ft.Text(f"員工編號：{user.get('employee_id') or '-'}", size=13, color=TEXT_MUTED),
                                ],
                            ),
                            outline_button("關閉", ft.Icons.CLOSE, lambda e: close_selected_user(), color=TEXT_MUTED, disabled=state.get("busy")),
                        ],
                    ),
                    *warnings,
                    ft.Column(
                        spacing=7,
                        controls=[
                            ft.Text("帳號狀態", size=13, color=TEXT, weight=ft.FontWeight.W_700),
                            ft.Row(wrap=True, spacing=8, run_spacing=8, controls=[
                                active_select_chip(True, "啟用"),
                                active_select_chip(False, "停用"),
                            ]),
                        ],
                    ),
                    ft.Column(
                        spacing=7,
                        controls=[
                            ft.Text("角色", size=13, color=TEXT, weight=ft.FontWeight.W_700),
                            ft.Row(wrap=True, spacing=8, run_spacing=8, controls=[role_select_chip(role) for role in ALLOWED_ROLES]),
                        ],
                    ),
                    ft.Column(
                        spacing=7,
                        controls=[
                            ft.Text("基本權限", size=13, color=TEXT, weight=ft.FontWeight.W_700),
                            ft.Row(wrap=True, spacing=8, run_spacing=8, controls=[permission_chip(key) for key in PERMISSION_LABELS.keys()]),
                        ],
                    ),
                    ft.Container(
                        bgcolor="#F8FAFC",
                        border=ft.border.all(1, BORDER),
                        border_radius=12,
                        padding=12,
                        content=ft.Column(
                            spacing=4,
                            controls=[
                                ft.Text("目前設定摘要", size=13, color=TEXT, weight=ft.FontWeight.W_700),
                                ft.Text(f"狀態：{'啟用' if form.get('is_active') else '停用'}｜角色：{form.get('role') or '-'}", size=13, color=TEXT_MUTED),
                                ft.Text("此版不處理新增使用者、重設密碼與強制登出；這些會放到下一階段。", size=12, color=TEXT_MUTED),
                            ],
                        ),
                    ),
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.Container(expand=True, content=outline_button("取消", ft.Icons.CLOSE, lambda e: close_selected_user(), color=TEXT_MUTED, disabled=state.get("busy"))),
                            ft.Container(expand=True, content=primary_button("儲存變更", ft.Icons.SAVE_OUTLINED, save_user_changes, bgcolor=BLUE_BTN, disabled=state.get("busy"))),
                        ],
                    ),
                ],
            ),
        )

    def build_user_list() -> ft.Control:
        users = filtered_users()

        controls: list[ft.Control] = [
            ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.LIST_ALT, size=23, color=BLUE_BTN),
                    section_title("使用者清單", f"目前篩選結果共 {len(users)} 人。"),
                ],
            )
        ]

        if not users:
            controls.append(
                ft.Container(
                    bgcolor="#FFFFFF",
                    border=ft.border.all(1, BORDER),
                    border_radius=14,
                    padding=16,
                    content=ft.Text("沒有符合條件的使用者。", size=14, color=TEXT_MUTED),
                )
            )
        else:
            for user in users:
                controls.append(build_user_card(user))

        return ft.Column(spacing=12, controls=controls)

    def build_access_denied() -> ft.Control:
        return ft.Container(
            expand=True,
            bgcolor=BG,
            padding=ft.padding.all(22),
            content=card(
                padding=24,
                border_color=RED_BORDER,
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=14,
                    controls=[
                        ft.Icon(ft.Icons.LOCK_OUTLINE, size=48, color=RED),
                        ft.Text("無權限存取", size=24, color=TEXT, weight=ft.FontWeight.BOLD),
                        ft.Text("此頁面僅限超級管理員使用。", size=14, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                        primary_button("返回首頁", ft.Icons.HOME_OUTLINED, lambda e: navigate("/"), bgcolor=BLUE_BTN),
                    ],
                ),
            ),
        )

    def build_error_banner() -> ft.Control:
        message = str(state.get("error_message") or "").strip()
        if not message:
            return ft.Container(height=0, visible=False)
        return card(
            padding=14,
            border_color=RED_BORDER,
            bgcolor=RED_SOFT,
            content=ft.Row(
                spacing=10,
                controls=[
                    ft.Icon(ft.Icons.ERROR_OUTLINE, color=RED, size=20),
                    ft.Text(message, size=13, color=RED, expand=True),
                ],
            ),
        )

    def build_layout() -> ft.Control:
        is_mobile = (page.width or 390) < MOBILE_WIDTH
        padding = ft.padding.only(left=16, right=16, top=18, bottom=18) if is_mobile else ft.padding.only(left=24, right=24, top=22, bottom=18)

        content: list[ft.Control] = [
            build_header(is_mobile),
            build_error_banner(),
            build_summary_cards(is_mobile),
            build_filters(),
        ]

        if is_mobile:
            content.extend([
                build_edit_panel(),
                build_user_list(),
            ])
        else:
            content.append(
                ft.ResponsiveRow(
                    columns=12,
                    spacing=14,
                    run_spacing=14,
                    controls=[
                        ft.Container(col={"xs": 12, "lg": 7}, content=build_user_list()),
                        ft.Container(col={"xs": 12, "lg": 5}, content=build_edit_panel()),
                    ],
                )
            )

        content.extend([
            ft.Container(
                bgcolor=ORANGE_SOFT,
                border=ft.border.all(1, ORANGE_BORDER),
                border_radius=14,
                padding=14,
                content=ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.INFO_OUTLINE, color=ORANGE_BTN, size=20),
                        ft.Text(
                            "安全邊界：此頁第一版只調整 users 既有欄位；新增帳號、密碼重設、強制登出與細權限矩陣另列下一階段。",
                            size=13,
                            color="#9A4A12",
                            weight=ft.FontWeight.W_600,
                            expand=True,
                        ),
                    ],
                ),
            ),
            ft.Container(height=90),
        ])

        return ft.Container(
            expand=True,
            bgcolor=BG,
            padding=padding,
            content=ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=18, controls=content),
        )

    def rebuild() -> None:
        if not is_active_view():
            return
        try:
            with ui_lock:
                if not is_active_view():
                    return
                main_host.content = build_access_denied() if not is_super_admin() else build_layout()
                page.update()
        except Exception as exc:
            print("admin_users rebuild failed:", repr(exc), flush=True)

    # =====================================================
    # Init
    # =====================================================
    if not is_super_admin():
        main_host.content = build_access_denied()
        return root

    main_host.content = build_layout()
    threading.Timer(0.25, lambda: refresh_data(show_loading=True)).start()

    return root
