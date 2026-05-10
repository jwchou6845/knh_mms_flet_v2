# views/maintenance_items_deleted.py
# KNH MMS - 已刪除保養項目 / 節點管理頁
# Flet 0.84 + Supabase

from __future__ import annotations

import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

import flet as ft

from services.maintenance_service import (
    load_deleted_maintenance_entities_page_data,
    restore_deleted_maintenance_item,
    restore_deleted_maintenance_node,
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

PURPLE_SOFT = "#F3E8FF"
PURPLE_BORDER = "#D8B4FE"
PURPLE_BTN = "#7358B8"

GREEN = "#059669"
GREEN_SOFT = "#ECFDF5"
GREEN_BORDER = "#A7F3D0"

RED = "#DC2626"
RED_SOFT = "#FEE2E2"
RED_BORDER = "#FCA5A5"

MOBILE_WIDTH = 920
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def MaintenanceItemsDeletedContent(page: ft.Page) -> ft.Control:
    if not hasattr(page, "session_data"):
        page.session_data = {}

    previous_dispose = page.session_data.get("_maintenance_items_dispose")
    if callable(previous_dispose):
        try:
            previous_dispose("replaced by maintenance_items_deleted instance")
        except Exception as ex:
            print("MAINTENANCE_ITEMS_DELETED PREVIOUS DISPOSE FAILED:", repr(ex), flush=True)

    instance_id = f"maintenance-items-deleted-{time.time_ns()}"

    state: dict[str, Any] = {
        "loading": True,
        "sync_status": "loading",
        "sync_message": "資料同步中",
        "sync_badge_visible": True,
        "error_message": "",
        "deleted_items": [],
        "deleted_nodes": [],
        "all_nodes": [],
        "deleted_item_count": 0,
        "deleted_node_count": 0,
        "load_seq": 0,
        "_alive": True,
    }

    def dispose_this_view(reason: str = "") -> None:
        if not state.get("_alive", True):
            return
        state["_alive"] = False
        print(f"MAINTENANCE_ITEMS_DELETED DISPOSE: instance={instance_id}, reason={reason}", flush=True)

    page.session_data["_maintenance_items_dispose"] = dispose_this_view
    page.session_data["_maintenance_items_instance_id"] = instance_id

    ui_lock = threading.RLock()
    action_lock = threading.Lock()

    main_host = ft.Container(expand=True)
    root = ft.Container(expand=True, bgcolor=BG, content=main_host)

    # =====================================================
    # 基礎工具
    # =====================================================
    def session_get(key: str, default=None):
        try:
            return page.session_data.get(key, default)
        except Exception:
            return default

    def is_super_admin() -> bool:
        return session_get("role") == "超級管理員"

    def is_active_view() -> bool:
        return bool(state.get("_alive", True))

    def safe_page_update() -> None:
        if not is_active_view():
            return
        try:
            with ui_lock:
                if is_active_view():
                    page.update()
        except Exception as ex:
            print("maintenance_items_deleted page.update failed:", repr(ex), flush=True)

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
        safe_page_update()

    def clean_text(value: Any, default: str = "") -> str:
        text = str(value or "").strip()
        return text if text else default

    def format_datetime_taipei(value: str | None) -> str:
        if not value:
            return "-"
        try:
            normalized = str(value).replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TAIPEI_TZ)
            return dt.astimezone(TAIPEI_TZ).strftime("%Y/%m/%d %H:%M")
        except Exception:
            return str(value)

    def card(content: ft.Control, padding: int = 16, bgcolor: str = CARD_BG, border_color: str = BORDER) -> ft.Container:
        return ft.Container(
            bgcolor=bgcolor,
            border=ft.border.all(1, border_color),
            border_radius=18,
            padding=padding,
            content=content,
        )

    def stable_outline_action_button(
        label: str,
        color: str = BLUE_BTN,
        border_color: str = BLUE_BORDER,
        on_click=None,
        height: int = 42,
    ) -> ft.Container:
        btn = ft.Container(
            height=height,
            border_radius=12,
            bgcolor="#FFFFFF",
            border=ft.border.all(1, border_color),
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.symmetric(horizontal=12),
            ink=True,
            content=ft.Text(
                label,
                size=14,
                color=color,
                weight=ft.FontWeight.BOLD,
                text_align=ft.TextAlign.CENTER,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        )
        btn.disabled = False

        def handle_click(e):
            if getattr(btn, "disabled", False):
                return
            if callable(on_click):
                on_click(e)

        btn.on_click = handle_click
        return btn

    def stable_filled_action_button(
        label: str,
        bg: str = BLUE_BTN,
        on_click=None,
        height: int = 44,
    ) -> ft.Container:
        btn = ft.Container(
            height=height,
            border_radius=12,
            bgcolor=bg,
            border=ft.border.all(1, bg),
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.symmetric(horizontal=16),
            ink=True,
            content=ft.Text(
                label,
                size=14,
                color="#FFFFFF",
                weight=ft.FontWeight.BOLD,
                text_align=ft.TextAlign.CENTER,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        )
        btn.disabled = False

        def handle_click(e):
            if getattr(btn, "disabled", False):
                return
            if callable(on_click):
                on_click(e)

        btn.on_click = handle_click
        return btn

    def section_title(title: str, subtitle: str | None = None) -> ft.Column:
        controls: list[ft.Control] = [
            ft.Text(title, size=20, weight=ft.FontWeight.BOLD, color=TEXT),
        ]
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
                content=ft.Text(
                    label,
                    size=12,
                    color=BLUE_BTN if route or active else TEXT_MUTED,
                    weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_500,
                ),
            )

        return ft.Row(
            wrap=True,
            spacing=2,
            run_spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                crumb("保養紀錄", "/maintenance"),
                ft.Text(">", size=12, color=TEXT_MUTED),
                crumb("保養項目管理", "/maintenance/items"),
                ft.Text(">", size=12, color=TEXT_MUTED),
                crumb("已刪除項目", None, active=True),
            ],
        )

    def build_header() -> ft.Control:
        sync_status = state.get("sync_status") or "success"
        sync_message = state.get("sync_message") or "資料已同步"
        show_badge = bool(state.get("sync_badge_visible"))

        if sync_status == "loading":
            fg, bg, border = BLUE_BTN, BLUE_SOFT, BLUE_BORDER
            icon_control = ft.ProgressRing(width=15, height=15, stroke_width=2, color=fg)
        elif sync_status == "error":
            fg, bg, border = RED, RED_SOFT, RED_BORDER
            icon_control = ft.Icon(ft.Icons.ERROR_OUTLINE, size=17, color=fg)
            show_badge = True
        else:
            fg, bg, border = GREEN, GREEN_SOFT, GREEN_BORDER
            icon_control = ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=17, color=fg)

        controls: list[ft.Control] = [
            breadcrumb(),
            ft.Row(
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Container(
                        width=58,
                        height=58,
                        border_radius=16,
                        bgcolor=PURPLE_SOFT,
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(ft.Icons.DELETE_OUTLINE, size=31, color=PURPLE_BTN),
                    ),
                    ft.Column(
                        expand=True,
                        spacing=5,
                        controls=[
                            ft.Text("已刪除項目", size=26, weight=ft.FontWeight.BOLD, color=TEXT, max_lines=2),
                            ft.Text(
                                "管理已刪除的保養項目與空節點；可在不破壞歷史資料的前提下還原。",
                                size=14,
                                color=TEXT_MUTED,
                                max_lines=3,
                            ),
                        ],
                    ),
                ],
            ),
        ]

        if show_badge:
            controls.append(
                ft.Container(
                    height=34,
                    border_radius=17,
                    bgcolor=bg,
                    border=ft.border.all(1, border),
                    alignment=ft.Alignment(0, 0),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=7,
                        controls=[
                            icon_control,
                            ft.Text(sync_message, size=12, color=fg, weight=ft.FontWeight.W_600),
                        ],
                    ),
                )
            )

        return ft.Column(spacing=10, controls=controls)

    def build_access_denied() -> ft.Control:
        page.bgcolor = BG
        return ft.Container(
            expand=True,
            bgcolor=BG,
            padding=ft.padding.all(22),
            content=ft.Column(
                spacing=18,
                controls=[
                    breadcrumb(),
                    card(
                        padding=24,
                        border_color=RED_BORDER,
                        content=ft.Column(
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=14,
                            controls=[
                                ft.Icon(ft.Icons.LOCK_OUTLINE, size=46, color=RED),
                                ft.Text("權限不足", size=24, color=TEXT, weight=ft.FontWeight.BOLD),
                                ft.Text(
                                    "此功能僅限超級管理員使用。",
                                    size=14,
                                    color=TEXT_MUTED,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                stable_filled_action_button(
                                    "返回保養紀錄",
                                    bg=BLUE_BTN,
                                    on_click=lambda _: navigate("/maintenance"),
                                    height=46,
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        )

    # =====================================================
    # 載入 / 更新
    # =====================================================
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

    def load_data(update_sync_state: bool = True) -> bool:
        try:
            result = load_deleted_maintenance_entities_page_data()
        except Exception as exc:
            state["deleted_items"] = []
            state["deleted_nodes"] = []
            state["all_nodes"] = []
            state["deleted_item_count"] = 0
            state["deleted_node_count"] = 0
            state["error_message"] = f"讀取已刪除保養資料失敗：{exc}"
            if update_sync_state:
                set_sync_state("error", "資料同步失敗", visible=True)
            return False

        data = result.data if isinstance(result.data, dict) else {}
        if result.ok:
            state["deleted_items"] = data.get("deleted_items") or []
            state["deleted_nodes"] = data.get("deleted_nodes") or []
            state["all_nodes"] = data.get("all_nodes") or []
            state["deleted_item_count"] = data.get("deleted_item_count", 0)
            state["deleted_node_count"] = data.get("deleted_node_count", 0)
            state["error_message"] = ""
            if update_sync_state:
                set_sync_state("success", "資料已同步", visible=True)
            return True

        state["deleted_items"] = data.get("deleted_items") or []
        state["deleted_nodes"] = data.get("deleted_nodes") or []
        state["all_nodes"] = data.get("all_nodes") or []
        state["deleted_item_count"] = 0
        state["deleted_node_count"] = 0
        state["error_message"] = result.message or "讀取已刪除保養資料失敗。"
        if update_sync_state:
            set_sync_state("error", "資料同步失敗", visible=True)
        return False

    def start_background_load(show_loading: bool = True, render_loading: bool = True) -> None:
        state["load_seq"] = int(state.get("load_seq") or 0) + 1
        current_load_seq = state["load_seq"]
        print(f"MAINTENANCE_ITEMS_DELETED LOAD START: seq={current_load_seq}, route={getattr(page, 'route', '')}", flush=True)

        if show_loading:
            set_sync_state("loading", "資料同步中", visible=True)
            if render_loading and is_active_view():
                rebuild()

        def watchdog():
            time.sleep(15)
            if not is_active_view() or state.get("load_seq") != current_load_seq:
                return
            if state.get("loading"):
                state["error_message"] = "已刪除保養資料同步逾時，請按重試。"
                set_sync_state("error", "資料同步逾時", visible=True)
                rebuild()

        def worker():
            ok = False
            try:
                ok = load_data(update_sync_state=True)
                print(f"MAINTENANCE_ITEMS_DELETED LOAD DONE: seq={current_load_seq}, ok={ok}, item_count={state.get('deleted_item_count')}, node_count={state.get('deleted_node_count')}", flush=True)
            except Exception as exc:
                state["error_message"] = f"讀取已刪除保養資料失敗：{exc}"
                set_sync_state("error", "資料同步失敗", visible=True)
                ok = False

            if not is_active_view() or state.get("load_seq") != current_load_seq:
                return

            rebuild()
            if ok:
                hide_sync_badge_later(3.0)

        threading.Thread(target=watchdog, daemon=True).start()
        threading.Thread(target=worker, daemon=True).start()

    def refresh(_=None) -> None:
        start_background_load(show_loading=True, render_loading=True)

    def run_after_write(result_message: str) -> None:
        load_data(update_sync_state=True)
        rebuild()
        hide_sync_badge_later(3.0)
        show_snack(result_message, success=True)

    # =====================================================
    # 動作
    # =====================================================
    def restore_item(item: dict[str, Any]) -> None:
        item_id = clean_text(item.get("id"))
        if not item_id:
            show_snack("缺少保養項目 ID。", success=False)
            return

        if not action_lock.acquire(blocking=False):
            show_snack("資料寫入中，請稍候。", success=False)
            return

        def worker():
            try:
                result = restore_deleted_maintenance_item(item_id=item_id, role=session_get("role"))
                if not is_active_view():
                    return
                if result.ok:
                    run_after_write(result.message or "保養項目已還原。")
                else:
                    show_snack(result.message or "還原保養項目失敗。", success=False)
            finally:
                try:
                    action_lock.release()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def restore_node(node: dict[str, Any]) -> None:
        node_id = clean_text(node.get("id"))
        if not node_id:
            show_snack("缺少保養節點 ID。", success=False)
            return

        if not action_lock.acquire(blocking=False):
            show_snack("資料寫入中，請稍候。", success=False)
            return

        def worker():
            try:
                result = restore_deleted_maintenance_node(node_id=node_id, role=session_get("role"))
                if not is_active_view():
                    return
                if result.ok:
                    run_after_write(result.message or "保養節點已還原。")
                else:
                    show_snack(result.message or "還原保養節點失敗。", success=False)
            finally:
                try:
                    action_lock.release()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    # =====================================================
    # UI
    # =====================================================
    def build_summary_cards(is_mobile: bool) -> ft.Control:
        data = [
            ("已刪除項目", state.get("deleted_item_count", 0), ft.Icons.DELETE_OUTLINE, RED, RED_SOFT),
            ("已刪除節點", state.get("deleted_node_count", 0), ft.Icons.ACCOUNT_TREE_OUTLINED, PURPLE_BTN, PURPLE_SOFT),
        ]

        def summary_card(title: str, value: Any, icon, color: str, bg: str) -> ft.Control:
            return card(
                padding=14,
                content=ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=48,
                            height=48,
                            border_radius=24,
                            bgcolor=bg,
                            alignment=ft.Alignment(0, 0),
                            content=ft.Icon(icon, color=color, size=25),
                        ),
                        ft.Column(
                            spacing=2,
                            controls=[
                                ft.Text(title, size=12, color=TEXT_MUTED),
                                ft.Text(str(value), size=23, weight=ft.FontWeight.BOLD, color=TEXT),
                            ],
                        ),
                    ],
                ),
            )

        cards = [summary_card(*row) for row in data]
        if is_mobile:
            return ft.Column(spacing=10, controls=cards)
        return ft.Row(spacing=12, controls=[ft.Container(expand=True, content=c) for c in cards])

    def build_error_banner() -> ft.Control:
        if not state.get("error_message"):
            return ft.Container(height=0)
        return ft.Container(
            bgcolor=RED_SOFT,
            border=ft.border.all(1, RED_BORDER),
            border_radius=12,
            padding=12,
            content=ft.Row(
                spacing=8,
                controls=[
                    ft.Icon(ft.Icons.ERROR_OUTLINE, color=RED, size=22),
                    ft.Text(state.get("error_message") or "", expand=True, size=13, color=RED),
                    stable_outline_action_button("重試", color=RED, border_color=RED_BORDER, on_click=refresh, height=40),
                ],
            ),
        )

    def build_loading_block() -> ft.Control:
        return card(
            padding=22,
            bgcolor=BLUE_SOFT,
            border_color=BLUE_BORDER,
            content=ft.Row(
                spacing=10,
                controls=[
                    ft.ProgressRing(width=18, height=18, stroke_width=2, color=BLUE_BTN),
                    ft.Text("正在讀取已刪除保養資料...", size=14, color=BLUE_BTN, weight=ft.FontWeight.BOLD),
                ],
            ),
        )

    def build_item_row(item: dict[str, Any]) -> ft.Control:
        return card(
            padding=14,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Container(
                                width=44,
                                height=44,
                                border_radius=22,
                                bgcolor=BLUE_SOFT if item.get("maintenance_type") == "清潔" else "#FFF7ED",
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(
                                    ft.Icons.CLEANING_SERVICES_OUTLINED if item.get("maintenance_type") == "清潔" else ft.Icons.INVENTORY_2_OUTLINED,
                                    size=22,
                                    color=BLUE_BTN if item.get("maintenance_type") == "清潔" else "#C96D32",
                                ),
                            ),
                            ft.Column(
                                expand=True,
                                spacing=4,
                                controls=[
                                    ft.Text(clean_text(item.get("item_name"), "未命名項目"), size=16, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ft.Text(clean_text(item.get("node_path"), "-"), size=12, color=TEXT_MUTED),
                                    ft.Text(f"刪除時間：{format_datetime_taipei(item.get('deleted_at'))}", size=12, color=TEXT_MUTED),
                                    ft.Text(f"刪除人員：{clean_text(item.get('deleted_by_name'), '-')}", size=12, color=TEXT_MUTED),
                                    ft.Text(f"原因：{clean_text(item.get('delete_reason'), '-')}", size=12, color=TEXT_MUTED),
                                ],
                            ),
                        ],
                    ),
                    stable_outline_action_button(
                        "還原項目",
                        color=GREEN,
                        border_color=GREEN_BORDER,
                        on_click=lambda _, current=item: restore_item(current),
                        height=42,
                    ),
                ],
            ),
        )

    def build_node_row(node: dict[str, Any]) -> ft.Control:
        return card(
            padding=14,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Container(
                                width=44,
                                height=44,
                                border_radius=22,
                                bgcolor=PURPLE_SOFT,
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(ft.Icons.ACCOUNT_TREE_OUTLINED, size=22, color=PURPLE_BTN),
                            ),
                            ft.Column(
                                expand=True,
                                spacing=4,
                                controls=[
                                    ft.Text(clean_text(node.get("node_name"), "未命名節點"), size=16, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ft.Text(clean_text(node.get("node_path"), "-"), size=12, color=TEXT_MUTED),
                                    ft.Text(f"刪除時間：{format_datetime_taipei(node.get('deleted_at'))}", size=12, color=TEXT_MUTED),
                                    ft.Text(f"刪除人員：{clean_text(node.get('deleted_by_name'), '-')}", size=12, color=TEXT_MUTED),
                                    ft.Text(f"原因：{clean_text(node.get('delete_reason'), '-')}", size=12, color=TEXT_MUTED),
                                ],
                            ),
                        ],
                    ),
                    stable_outline_action_button(
                        "還原節點",
                        color=GREEN,
                        border_color=GREEN_BORDER,
                        on_click=lambda _, current=node: restore_node(current),
                        height=42,
                    ),
                ],
            ),
        )

    def build_deleted_sections() -> ft.Control:
        item_controls = [build_item_row(item) for item in state.get("deleted_items") or []]
        node_controls = [build_node_row(node) for node in state.get("deleted_nodes") or []]

        if not item_controls:
            item_controls = [card(ft.Text("目前沒有已刪除保養項目。", size=13, color=TEXT_MUTED), padding=16)]
        if not node_controls:
            node_controls = [card(ft.Text("目前沒有已刪除保養節點。", size=13, color=TEXT_MUTED), padding=16)]

        return ft.Column(
            spacing=18,
            controls=[
                card(
                    padding=18,
                    content=ft.Column(
                        spacing=14,
                        controls=[
                            section_title("已刪除保養項目", "軟刪除後仍保留歷史資料；還原前會檢查所屬節點與重複名稱。"),
                            ft.Column(spacing=10, controls=item_controls),
                        ],
                    ),
                ),
                card(
                    padding=18,
                    content=ft.Column(
                        spacing=14,
                        controls=[
                            section_title("已刪除節點", "目前只允許刪除空節點；還原時會檢查上層節點與同層重名。"),
                            ft.Column(spacing=10, controls=node_controls),
                        ],
                    ),
                ),
            ],
        )

    def build_layout(is_mobile: bool) -> ft.Control:
        page.bgcolor = BG
        controls: list[ft.Control] = [
            build_header(),
            build_error_banner(),
            build_summary_cards(is_mobile=is_mobile),
            stable_outline_action_button(
                "返回保養項目管理",
                color=BLUE_BTN,
                border_color=BLUE_BORDER,
                on_click=lambda _: navigate("/maintenance/items"),
                height=44,
            ),
        ]

        if state.get("loading") and not state.get("deleted_items") and not state.get("deleted_nodes"):
            controls.append(build_loading_block())
        else:
            controls.append(build_deleted_sections())

        controls.append(ft.Container(height=90 if is_mobile else 80))

        return ft.Container(
            expand=True,
            bgcolor=BG,
            padding=ft.padding.only(left=16 if is_mobile else 24, right=16 if is_mobile else 24, top=18 if is_mobile else 22, bottom=18),
            content=ft.Column(
                expand=True,
                scroll=ft.ScrollMode.AUTO,
                spacing=18,
                controls=controls,
            ),
        )

    def rebuild() -> None:
        if not is_active_view():
            return
        try:
            with ui_lock:
                if not is_active_view():
                    return
                if not is_super_admin():
                    main_host.content = build_access_denied()
                else:
                    width = page.width or 390
                    main_host.content = build_layout(is_mobile=width < MOBILE_WIDTH)
                page.update()
        except Exception as ex:
            print("maintenance_items_deleted rebuild failed:", repr(ex), flush=True)

    # =====================================================
    # 初始化
    # =====================================================
    if not is_super_admin():
        main_host.content = build_access_denied()
        return root

    width = page.width or 390
    main_host.content = build_layout(is_mobile=width < MOBILE_WIDTH)

    print(f"MAINTENANCE_ITEMS_DELETED INIT: instance={instance_id}, route={getattr(page, 'route', '')}, role={session_get('role')}", flush=True)
    try:
        threading.Timer(0.35, lambda: start_background_load(show_loading=True, render_loading=False)).start()
    except Exception as ex:
        print("MAINTENANCE_ITEMS_DELETED TIMER START FAILED:", repr(ex), flush=True)
        start_background_load(show_loading=True, render_loading=False)

    return root
