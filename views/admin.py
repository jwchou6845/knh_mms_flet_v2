# =====================================================
# KNH MMS v2
# File: views/admin.py
# File Revision: 2026-05-12-admin-home-phase1-r1
# Status: phase 1 new file
# Last Updated: 2026-05-12 Asia/Taipei
#
# Purpose:
# - /admin 系統控制中心首頁。
# - 提供超級管理員集中管理入口與第一階段真實摘要資料。
#
# Major Changes in This Revision:
# - 新增控制中心首頁 UI。
# - 摘要卡讀取 Supabase 真實資料：啟用原料、停用原料、低水位品項、有效 Session。
# - 管理入口卡提供 /admin/materials、/admin/maintenance 與第二階段 placeholder 提示。
# - 使用背景 thread 載入資料，避免阻塞 Flet Web 手機畫面。
# - 新增人工盤點管理入口，導向既有 /inventory/stocktake 頁面。
# - 新增人工盤點摘要：草稿、待審核、本月已確認、已作廢。
#
# Notes:
# - Flet 0.84；不使用 page.push_route()。
# - 僅超級管理員可使用；非超級管理員顯示無權限頁。
# - 第一階段不產生假管理紀錄；最近管理動作明確標示為第二階段稽核功能。
# =====================================================

from __future__ import annotations

import threading
import time
from typing import Any

import flet as ft

from services.admin_service import load_admin_home_data


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
PURPLE_BTN = "#7358B8"

ORANGE = "#F97316"
ORANGE_SOFT = "#FFF7ED"
ORANGE_BORDER = "#FDBA74"
ORANGE_BTN = "#C96D32"

GREEN = "#059669"
GREEN_SOFT = "#ECFDF5"
GREEN_BORDER = "#A7F3D0"

RED = "#DC2626"
RED_SOFT = "#FEE2E2"
RED_BORDER = "#FCA5A5"

MOBILE_WIDTH = 920


def AdminContent(page: ft.Page) -> ft.Control:
    if not hasattr(page, "session_data"):
        page.session_data = {}

    state: dict[str, Any] = {
        "loading": True,
        "sync_status": "loading",
        "sync_message": "資料同步中",
        "sync_badge_visible": True,
        "error_message": "",
        "data": {
            "material_summary": {
                "active_material_count": 0,
                "inactive_material_count": 0,
                "stock_managed_count": 0,
                "low_stock_count": 0,
            },
            "session_summary": {
                "active_session_count": 0,
                "total_session_rows": 0,
            },
            "maintenance_summary": {
                "active_item_count": 0,
                "inactive_item_count": 0,
                "active_node_count": 0,
                "deleted_item_count": 0,
                "deleted_node_count": 0,
            },
            "stocktake_summary": {
                "draft_count": 0,
                "submitted_count": 0,
                "confirmed_count": 0,
                "confirmed_this_month_count": 0,
                "voided_count": 0,
                "total_count": 0,
            },
            "generated_at": "-",
            "recent_actions": [],
        },
    }

    view_token = f"admin-home-{time.time_ns()}"
    page.session_data["_admin_view_token"] = view_token
    ui_lock = threading.RLock()

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

    def is_super_admin() -> bool:
        return session_get("role") == "超級管理員"

    def is_active_view() -> bool:
        route = str(getattr(page, "route", "") or "")
        return page.session_data.get("_admin_view_token") == view_token and (not route or route == "/admin")

    def safe_update() -> None:
        if not is_active_view():
            return
        try:
            with ui_lock:
                if is_active_view():
                    page.update()
        except Exception as exc:
            print("admin page.update failed:", repr(exc))

    def navigate(route: str) -> None:
        nav = session_get("_navigate")
        if callable(nav):
            nav(route)
        else:
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
        def worker():
            time.sleep(delay_seconds)
            if not is_active_view():
                return
            if state.get("sync_status") == "success":
                state["sync_badge_visible"] = False
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    # =====================================================
    # Shared UI
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
                    ft.Text(state.get("sync_message") or "資料已同步", size=12, color=fg, weight=ft.FontWeight.W_600),
                ],
            ),
        )

    def build_header(is_mobile: bool) -> ft.Control:
        title_block = ft.Row(
            spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Container(
                    width=58,
                    height=58,
                    border_radius=16,
                    bgcolor=BLUE_SOFT,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Icon(ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED, size=31, color=BLUE_BTN),
                ),
                ft.Column(
                    expand=True,
                    spacing=5,
                    controls=[
                        ft.Text("系統控制中心", size=26 if is_mobile else 28, weight=ft.FontWeight.BOLD, color=TEXT, max_lines=2),
                        ft.Text("集中管理原料、保養、權限與系統設定。", size=14, color=TEXT_MUTED, max_lines=3),
                    ],
                ),
            ],
        )
        return ft.Column(spacing=10, controls=[title_block, sync_badge()])

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
        data = state["data"]
        material = data.get("material_summary") or {}
        session = data.get("session_summary") or {}

        cards = [
            metric_card("啟用原料", material.get("active_material_count", 0), "項", ft.Icons.INVENTORY_2_OUTLINED, BLUE_BTN, BLUE_SOFT, BLUE_BORDER, "materials.is_active = true"),
            metric_card("停用原料", material.get("inactive_material_count", 0), "項", ft.Icons.PAUSE_CIRCLE_OUTLINE, ORANGE_BTN, ORANGE_SOFT, ORANGE_BORDER, "停用不刪除歷史紀錄"),
            metric_card("低水位品項", material.get("low_stock_count", 0), "項", ft.Icons.WATER_DROP_OUTLINED, RED, RED_SOFT, RED_BORDER, "啟用且納管庫存"),
            metric_card("有效 Session", session.get("active_session_count", 0), "筆", ft.Icons.PERSON_OUTLINE, GREEN, GREEN_SOFT, GREEN_BORDER, "不影響免重登流程"),
        ]

        if is_mobile:
            return ft.Column(
                spacing=10,
                controls=[
                    ft.Row(spacing=10, controls=[ft.Container(expand=True, content=cards[0]), ft.Container(expand=True, content=cards[1])]),
                    ft.Row(spacing=10, controls=[ft.Container(expand=True, content=cards[2]), ft.Container(expand=True, content=cards[3])]),
                ],
            )

        return ft.Row(spacing=12, controls=[ft.Container(expand=True, content=c) for c in cards])

    def build_stocktake_summary_cards(is_mobile: bool) -> ft.Control:
        data = state["data"]
        stocktake = data.get("stocktake_summary") or {}

        cards = [
            metric_card("草稿盤點", stocktake.get("draft_count", 0), "張", ft.Icons.EDIT_NOTE, BLUE_BTN, BLUE_SOFT, BLUE_BORDER, "尚未送出，可繼續盤點"),
            metric_card("待審核盤點", stocktake.get("submitted_count", 0), "張", ft.Icons.PENDING_ACTIONS, ORANGE_BTN, ORANGE_SOFT, ORANGE_BORDER, "需超級管理員確認"),
            metric_card("本月已確認", stocktake.get("confirmed_this_month_count", 0), "張", ft.Icons.CHECK_CIRCLE_OUTLINE, GREEN, GREEN_SOFT, GREEN_BORDER, "本月確認完成盤點"),
            metric_card("已作廢盤點", stocktake.get("voided_count", 0), "張", ft.Icons.BLOCK, RED, RED_SOFT, RED_BORDER, "保留作廢稽核紀錄"),
        ]

        if is_mobile:
            return ft.Column(
                spacing=10,
                controls=[
                    ft.Row(spacing=10, controls=[ft.Container(expand=True, content=cards[0]), ft.Container(expand=True, content=cards[1])]),
                    ft.Row(spacing=10, controls=[ft.Container(expand=True, content=cards[2]), ft.Container(expand=True, content=cards[3])]),
                ],
            )

        return ft.Row(spacing=12, controls=[ft.Container(expand=True, content=c) for c in cards])

    def module_card(
        number: int,
        title: str,
        description: str,
        icon,
        color: str,
        soft: str,
        border: str,
        route: str | None = None,
        planned: bool = False,
    ) -> ft.Control:
        def open_module(_=None):
            if planned or not route:
                show_snack("此功能將於第二階段開放。", success=False)
                return
            navigate(route)

        badge = ft.Container(
            padding=ft.padding.symmetric(horizontal=9, vertical=4),
            border_radius=8,
            bgcolor="#F1F5F9" if planned else GREEN_SOFT,
            border=ft.border.all(1, BORDER if planned else GREEN_BORDER),
            content=ft.Text("第二階段" if planned else "可使用", size=11, color=TEXT_MUTED if planned else GREEN, weight=ft.FontWeight.BOLD),
        )

        return ft.Container(
            col={"xs": 12, "sm": 6, "lg": 4},
            content=card(
                padding=16,
                border_color=border if not planned else BORDER,
                content=ft.Container(
                    ink=True,
                    on_click=open_module,
                    content=ft.Column(
                        spacing=14,
                        controls=[
                            ft.Row(
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Container(width=46, height=46, border_radius=14, bgcolor=soft, alignment=ft.Alignment(0, 0), content=ft.Icon(icon, size=25, color=color)),
                                    ft.Column(
                                        expand=True,
                                        spacing=2,
                                        controls=[
                                            ft.Text(f"{number}. {title}", size=16, weight=ft.FontWeight.BOLD, color=TEXT),
                                            ft.Text(description, size=12, color=TEXT_MUTED, max_lines=2),
                                        ],
                                    ),
                                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=20, color=color if not planned else TEXT_MUTED),
                                ],
                            ),
                            ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[badge]),
                        ],
                    ),
                ),
            ),
        )

    def build_module_grid() -> ft.Control:
        return ft.ResponsiveRow(
            columns=12,
            spacing=12,
            run_spacing=12,
            controls=[
                module_card(1, "原料與庫存設定", "新增、停用原料，管理包重與低水位。", ft.Icons.INVENTORY_2_OUTLINED, BLUE_BTN, BLUE_SOFT, BLUE_BORDER, "/admin/materials"),
                module_card(2, "人工盤點管理", "查看盤點單、待審核盤點與作廢紀錄。", ft.Icons.FACT_CHECK_OUTLINED, GREEN, GREEN_SOFT, GREEN_BORDER, "/inventory/stocktake"),
                module_card(3, "保養管理", "整合保養項目管理與已刪除項目入口。", ft.Icons.HANDYMAN_OUTLINED, PURPLE_BTN, PURPLE_SOFT, PURPLE_BORDER, "/admin/maintenance"),
                module_card(4, "使用者與權限", "管理帳號啟用狀態、角色與 Session。", ft.Icons.GROUP_OUTLINED, BLUE_BTN, BLUE_SOFT, BLUE_BORDER, "/admin/users", planned=True),
                module_card(5, "報表與匯出設定", "設定報表欄位、預覽筆數與匯出格式。", ft.Icons.BAR_CHART_OUTLINED, BLUE_BTN, BLUE_SOFT, BLUE_BORDER, "/admin/reports", planned=True),
                module_card(6, "系統參數", "管理同步秒數、預設查詢筆數與模組開關。", ft.Icons.SETTINGS_OUTLINED, ORANGE_BTN, ORANGE_SOFT, ORANGE_BORDER, "/admin/settings", planned=True),
                module_card(7, "稽核與刪除還原", "查詢操作紀錄與刪除還原紀錄。", ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED, GREEN, GREEN_SOFT, GREEN_BORDER, "/admin/audit", planned=True),
            ],
        )

    def build_recent_actions_placeholder() -> ft.Control:
        return card(
            padding=18,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.Icon(ft.Icons.HISTORY_OUTLINED, color=BLUE_BTN, size=22),
                            ft.Text("最近管理動作", size=18, weight=ft.FontWeight.BOLD, color=TEXT),
                        ],
                    ),
                    ft.Container(
                        bgcolor="#F8FAFC",
                        border=ft.border.all(1, BORDER),
                        border_radius=14,
                        padding=14,
                        content=ft.Column(
                            spacing=6,
                            controls=[
                                ft.Text("稽核紀錄功能尚未啟用。", size=14, color=TEXT, weight=ft.FontWeight.W_600),
                                ft.Text("第二階段將記錄原料新增、停用、保養項目調整、權限變更等操作。", size=13, color=TEXT_MUTED),
                            ],
                        ),
                    ),
                ],
            ),
        )

    def build_access_denied() -> ft.Control:
        return ft.Container(
            expand=True,
            bgcolor=BG,
            padding=ft.padding.all(22),
            content=ft.Column(
                spacing=18,
                controls=[
                    card(
                        padding=24,
                        border_color=RED_BORDER,
                        content=ft.Column(
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=14,
                            controls=[
                                ft.Icon(ft.Icons.LOCK_OUTLINE, size=48, color=RED),
                                ft.Text("無權限存取", size=24, color=TEXT, weight=ft.FontWeight.BOLD),
                                ft.Text("此頁面僅限超級管理員使用。如需調整權限，請聯繫系統管理員。", size=14, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                                ft.ElevatedButton(text="返回首頁", icon=ft.Icons.HOME_OUTLINED, bgcolor=BLUE_BTN, color="#FFFFFF", on_click=lambda _: navigate("/")),
                            ],
                        ),
                    )
                ],
            ),
        )

    def build_layout() -> ft.Control:
        is_mobile = (page.width or 390) < MOBILE_WIDTH
        padding = ft.padding.only(left=16, right=16, top=18, bottom=18) if is_mobile else ft.padding.only(left=24, right=24, top=22, bottom=18)

        controls: list[ft.Control] = [
            build_header(is_mobile),
            build_summary_cards(is_mobile),
            ft.Column(spacing=8, controls=[section_title("人工盤點摘要", "顯示盤點單目前狀態，方便超級管理員快速掌握待處理項目。"), build_stocktake_summary_cards(is_mobile)]),
            ft.Column(spacing=8, controls=[section_title("管理模組", "已完成項目可直接使用，未完成項目會標示第二階段。"), build_module_grid()]),
            build_recent_actions_placeholder(),
            ft.Container(height=90),
        ]

        if state.get("error_message"):
            controls.insert(
                1,
                card(
                    padding=14,
                    border_color=RED_BORDER,
                    bgcolor=RED_SOFT,
                    content=ft.Text(state.get("error_message") or "資料讀取失敗", size=13, color=RED),
                ),
            )

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
            print("admin rebuild failed:", repr(exc))

    def start_background_load() -> None:
        if not is_super_admin():
            return

        set_sync_state("loading", "資料同步中", visible=True)

        def worker():
            try:
                result = load_admin_home_data()
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
            except Exception as exc:
                if not is_active_view():
                    return
                state["error_message"] = f"控制中心資料載入失敗：{exc}"
                set_sync_state("error", "資料同步失敗", visible=True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    # =====================================================
    # Init
    # =====================================================
    if not is_super_admin():
        main_host.content = build_access_denied()
        return root

    main_host.content = build_layout()
    threading.Timer(0.25, start_background_load).start()
    return root
