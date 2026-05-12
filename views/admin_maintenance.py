# =====================================================
# KNH MMS v2
# File: views/admin_maintenance.py
# File Revision: 2026-05-12-admin-maintenance-phase1-r1
# Status: phase 1 new file
# Last Updated: 2026-05-12 Asia/Taipei
#
# Purpose:
# - /admin/maintenance 保養管理入口整合頁。
# - 將超級管理員的保養管理入口逐步收斂到 /admin。
#
# Major Changes in This Revision:
# - 新增保養項目管理與已刪除項目 / 節點入口。
# - 顯示保養項目、節點、已刪除資料摘要。
# - 重新命名與移至位置先標示為第二階段，不連到不存在流程。
#
# Notes:
# - Flet 0.84；不使用 page.push_route()。
# - 不重做 maintenance_items.py，僅導向既有穩定頁。
# - 僅超級管理員可使用。
# =====================================================

from __future__ import annotations

import threading
import time
from typing import Any

import flet as ft

from services.admin_service import load_admin_maintenance_page_data


BG = "#F6F8FB"
CARD_BG = "#FFFFFF"
TEXT = "#1E293B"
TEXT_MUTED = "#64748B"
BORDER = "#E2E8F0"

BLUE_BTN = "#4F7FB8"
BLUE_SOFT = "#E5F0FF"
BLUE_BORDER = "#B0D0FF"
PURPLE_BTN = "#7358B8"
PURPLE_SOFT = "#F3E8FF"
PURPLE_BORDER = "#D8B4FE"
ORANGE_BTN = "#C96D32"
ORANGE_SOFT = "#FFF7ED"
ORANGE_BORDER = "#FDBA74"
GREEN = "#059669"
GREEN_SOFT = "#ECFDF5"
GREEN_BORDER = "#A7F3D0"
RED = "#DC2626"
RED_SOFT = "#FEE2E2"
RED_BORDER = "#FCA5A5"
MOBILE_WIDTH = 920


def AdminMaintenanceContent(page: ft.Page) -> ft.Control:
    if not hasattr(page, "session_data"):
        page.session_data = {}

    state: dict[str, Any] = {
        "loading": True,
        "sync_status": "loading",
        "sync_message": "資料同步中",
        "sync_badge_visible": True,
        "error_message": "",
        "data": {
            "summary": {
                "active_item_count": 0,
                "inactive_item_count": 0,
                "active_node_count": 0,
                "deleted_item_count": 0,
                "deleted_node_count": 0,
            },
            "generated_at": "-",
        },
    }

    view_token = f"admin-maintenance-{time.time_ns()}"
    page.session_data["_admin_maintenance_view_token"] = view_token
    ui_lock = threading.RLock()
    main_host = ft.Container(expand=True)
    root = ft.Container(expand=True, bgcolor=BG, content=main_host)

    def session_get(key: str, default=None):
        try:
            return page.session_data.get(key, default)
        except Exception:
            return default

    def is_super_admin() -> bool:
        return session_get("role") == "超級管理員"

    def is_active_view() -> bool:
        route = str(getattr(page, "route", "") or "")
        return page.session_data.get("_admin_maintenance_view_token") == view_token and (not route or route == "/admin/maintenance")

    def navigate(route: str) -> None:
        nav = session_get("_navigate")
        if callable(nav):
            nav(route)
        else:
            page.go(route)

    def safe_update() -> None:
        if not is_active_view():
            return
        try:
            with ui_lock:
                if is_active_view():
                    page.update()
        except Exception:
            pass

    def show_snack(message: str, success: bool = True):
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

    def set_sync_state(status: str, message: str, visible: bool = True):
        state["sync_status"] = status
        state["sync_message"] = message
        state["sync_badge_visible"] = visible
        state["loading"] = status == "loading"

    def hide_sync_badge_later(delay_seconds: float = 3.0):
        def worker():
            time.sleep(delay_seconds)
            if not is_active_view():
                return
            if state.get("sync_status") == "success":
                state["sync_badge_visible"] = False
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def card(content: ft.Control, padding: int = 16, border_color: str = BORDER, bgcolor: str = CARD_BG) -> ft.Container:
        return ft.Container(
            width=float("inf"),
            bgcolor=bgcolor,
            border=ft.border.all(1, border_color),
            border_radius=18,
            padding=padding,
            content=content,
        )

    def section_title(title: str, subtitle: str | None = None) -> ft.Column:
        controls: list[ft.Control] = [ft.Text(title, size=20, weight=ft.FontWeight.BOLD, color=TEXT)]
        if subtitle:
            controls.append(ft.Text(subtitle, size=13, color=TEXT_MUTED, max_lines=3))
        return ft.Column(spacing=4, controls=controls)

    def breadcrumb() -> ft.Control:
        def crumb(label: str, route: str | None, active: bool = False):
            return ft.Container(
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                border_radius=8,
                bgcolor=BLUE_SOFT if active else "transparent",
                ink=bool(route),
                on_click=(lambda _: navigate(route)) if route else None,
                content=ft.Text(label, size=12, color=BLUE_BTN if route or active else TEXT_MUTED, weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_500),
            )

        return ft.Row(
            wrap=True,
            spacing=2,
            run_spacing=4,
            controls=[
                crumb("控制中心", "/admin"),
                ft.Text(">", size=12, color=TEXT_MUTED),
                crumb("保養管理", None, active=True),
            ],
        )

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
            content=ft.Row(tight=True, spacing=7, controls=[icon, ft.Text(state.get("sync_message") or "資料已同步", size=12, color=fg, weight=ft.FontWeight.W_600)]),
        )

    def build_header() -> ft.Control:
        return ft.Column(
            spacing=10,
            controls=[
                breadcrumb(),
                ft.Row(
                    spacing=14,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Container(width=58, height=58, border_radius=16, bgcolor=PURPLE_SOFT, alignment=ft.Alignment(0, 0), content=ft.Icon(ft.Icons.HANDYMAN_OUTLINED, size=31, color=PURPLE_BTN)),
                        ft.Column(expand=True, spacing=5, controls=[
                            ft.Text("保養管理", size=26, weight=ft.FontWeight.BOLD, color=TEXT, max_lines=2),
                            ft.Text("集中管理保養項目、刪除還原與後續管理功能。", size=14, color=TEXT_MUTED, max_lines=3),
                        ]),
                    ],
                ),
                sync_badge(),
            ],
        )

    def summary_card(title: str, value: Any, unit: str, icon, color: str, soft: str, border: str) -> ft.Control:
        return card(
            padding=14,
            border_color=border,
            content=ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(width=48, height=48, border_radius=16, bgcolor=soft, alignment=ft.Alignment(0, 0), content=ft.Icon(icon, size=25, color=color)),
                    ft.Column(spacing=2, controls=[
                        ft.Text(title, size=12, color=TEXT_MUTED),
                        ft.Row(tight=True, spacing=5, controls=[ft.Text(str(value), size=24, weight=ft.FontWeight.BOLD, color=TEXT), ft.Text(unit, size=12, color=TEXT_MUTED)]),
                    ]),
                ],
            ),
        )

    def build_summary(is_mobile: bool) -> ft.Control:
        summary = (state.get("data") or {}).get("summary") or {}
        cards = [
            summary_card("啟用項目", summary.get("active_item_count", 0), "項", ft.Icons.CHECK_CIRCLE_OUTLINE, GREEN, GREEN_SOFT, GREEN_BORDER),
            summary_card("停用項目", summary.get("inactive_item_count", 0), "項", ft.Icons.PAUSE_CIRCLE_OUTLINE, ORANGE_BTN, ORANGE_SOFT, ORANGE_BORDER),
            summary_card("啟用節點", summary.get("active_node_count", 0), "個", ft.Icons.ACCOUNT_TREE_OUTLINED, PURPLE_BTN, PURPLE_SOFT, PURPLE_BORDER),
            summary_card("已刪除", f"{summary.get('deleted_item_count', 0)} / {summary.get('deleted_node_count', 0)}", "項/節點", ft.Icons.DELETE_OUTLINE, RED, RED_SOFT, RED_BORDER),
        ]
        if is_mobile:
            return ft.Column(spacing=10, controls=[
                ft.Row(spacing=10, controls=[ft.Container(expand=True, content=cards[0]), ft.Container(expand=True, content=cards[1])]),
                ft.Row(spacing=10, controls=[ft.Container(expand=True, content=cards[2]), ft.Container(expand=True, content=cards[3])]),
            ])
        return ft.Row(spacing=12, controls=[ft.Container(expand=True, content=c) for c in cards])

    def action_card(title: str, subtitle: str, icon, color: str, soft: str, border: str, button_text: str, route: str | None = None, planned: bool = False) -> ft.Control:
        def handle_click(_=None):
            if planned or not route:
                show_snack("此功能將於第二階段開放。", success=False)
                return
            navigate(route)

        return ft.Container(
            col={"xs": 12, "sm": 6},
            content=card(
                padding=18,
                border_color=border if not planned else BORDER,
                content=ft.Column(
                    spacing=14,
                    controls=[
                        ft.Row(spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                            ft.Container(width=52, height=52, border_radius=16, bgcolor=soft, alignment=ft.Alignment(0, 0), content=ft.Icon(icon, size=28, color=color)),
                            ft.Column(expand=True, spacing=3, controls=[
                                ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=TEXT),
                                ft.Text(subtitle, size=13, color=TEXT_MUTED, max_lines=3),
                            ]),
                        ]),
                        ft.ElevatedButton(
                            text=button_text if not planned else "第二階段開放",
                            icon=ft.Icons.OPEN_IN_NEW if not planned else ft.Icons.LOCK_CLOCK_OUTLINED,
                            bgcolor=color if not planned else "#94A3B8",
                            color="#FFFFFF",
                            on_click=handle_click,
                        ),
                    ],
                ),
            ),
        )

    def build_action_grid() -> ft.Control:
        return ft.ResponsiveRow(
            columns=12,
            spacing=12,
            run_spacing=12,
            controls=[
                action_card("保養項目管理", "管理保養節點、項目、週期、啟用與停用。", ft.Icons.ACCOUNT_TREE_OUTLINED, PURPLE_BTN, PURPLE_SOFT, PURPLE_BORDER, "前往管理", "/maintenance/items"),
                action_card("已刪除項目 / 節點", "查看已刪除保養項目與節點，必要時可還原。", ft.Icons.DELETE_OUTLINE, RED, RED_SOFT, RED_BORDER, "查看已刪除", "/maintenance/items/deleted"),
                action_card("重新命名", "節點或項目重新命名功能，將以安全流程處理。", ft.Icons.EDIT_NOTE_OUTLINED, BLUE_BTN, BLUE_SOFT, BLUE_BORDER, "規劃中", None, planned=True),
                action_card("移至位置", "將既有項目移至其他節點位置，避免重複建立。", ft.Icons.DRIVE_FILE_MOVE_OUTLINE, ORANGE_BTN, ORANGE_SOFT, ORANGE_BORDER, "規劃中", None, planned=True),
            ],
        )

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
                        ft.Text("此頁面僅限超級管理員使用。", size=14, color=TEXT_MUTED),
                        ft.ElevatedButton(text="返回首頁", icon=ft.Icons.HOME_OUTLINED, bgcolor=BLUE_BTN, color="#FFFFFF", on_click=lambda _: navigate("/")),
                    ],
                ),
            ),
        )

    def build_layout() -> ft.Control:
        is_mobile = (page.width or 390) < MOBILE_WIDTH
        padding = ft.padding.only(left=16, right=16, top=18, bottom=18) if is_mobile else ft.padding.only(left=24, right=24, top=22, bottom=18)
        controls: list[ft.Control] = [
            build_header(),
            build_summary(is_mobile),
            section_title("管理入口", "第一版先整合既有穩定保養管理頁，不重做主流程。"),
            build_action_grid(),
            ft.Container(height=90),
        ]
        if state.get("error_message"):
            controls.insert(1, card(ft.Text(state.get("error_message") or "資料讀取失敗", size=13, color=RED), padding=14, border_color=RED_BORDER, bgcolor=RED_SOFT))
        return ft.Container(
            expand=True,
            bgcolor=BG,
            padding=padding,
            content=ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=18, controls=controls),
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
            print("admin_maintenance rebuild failed:", repr(exc))

    def start_background_load():
        if not is_super_admin():
            return
        set_sync_state("loading", "資料同步中", visible=True)

        def worker():
            result = load_admin_maintenance_page_data()
            if not is_active_view():
                return
            if result.ok:
                state["data"] = result.data or state["data"]
                state["error_message"] = ""
                set_sync_state("success", "資料已同步", visible=True)
            else:
                state["data"] = result.data or state["data"]
                state["error_message"] = result.message
                set_sync_state("error", "資料同步失敗", visible=True)
            rebuild()
            if result.ok:
                hide_sync_badge_later(3.0)

        threading.Thread(target=worker, daemon=True).start()

    if not is_super_admin():
        main_host.content = build_access_denied()
        return root

    main_host.content = build_layout()
    threading.Timer(0.25, start_background_load).start()
    return root
