# views/maintenance_items.py
# KNH MMS - 保養項目管理頁
# Flet 0.84 + Supabase
# 第一版：A+B 混合版
# - 桌機：左側保養項目地圖 + 右側節點內容
# - 手機：一步一步選位置 + 既有項目清單
# - 僅超級管理員可使用管理功能

from __future__ import annotations

import threading
import time
from typing import Any

import flet as ft

from services.maintenance_service import (
    create_cleaning_item,
    create_consumable_item,
    load_maintenance_items_page_data,
    set_maintenance_item_active,
    update_item_cycle,
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

DISABLED = "#94A3B8"
MOBILE_WIDTH = 920


def MaintenanceItemsContent(page: ft.Page) -> ft.Control:
    """
    保養項目管理子頁。
    只給超級管理員使用；一般角色即使直接輸入 /maintenance/items，也只會看到權限不足。
    """

    if not hasattr(page, "session_data"):
        page.session_data = {}

    view_token = f"maintenance-items-{time.time_ns()}"
    page.session_data["_maintenance_items_view_token"] = view_token

    state: dict[str, Any] = {
        "loading": True,
        "sync_status": "loading",
        "sync_message": "資料同步中",
        "sync_badge_visible": True,
        "error_message": "",
        "items": [],
        "count": 0,
        "active_count": 0,
        "inactive_count": 0,
        "selected_type": "清潔",
        "selected_machine": "",
        "selected_main": "",
        "selected_sub": "",
        "active_form": None,
        "editing_item": None,
        "load_seq": 0,
    }

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
        try:
            if page.session_data.get("_maintenance_items_view_token") != view_token:
                return False
        except Exception:
            return False

        route = str(getattr(page, "route", "") or "")
        return not route or route.startswith("/maintenance/items")

    def safe_page_update() -> None:
        if not is_active_view():
            return
        try:
            with ui_lock:
                if is_active_view():
                    page.update()
        except Exception as ex:
            print("maintenance_items page.update failed:", repr(ex))

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

    def to_int(value: Any, default: int = 0) -> int:
        try:
            return int(str(value or "").strip())
        except Exception:
            return default

    def normalize_duplicate_text(value: Any) -> str:
        text = str(value or "").strip().replace("　", " ")
        return " ".join(text.split()).casefold()

    def item_display_name(item: dict[str, Any]) -> str:
        sub = clean_text(item.get("sub_category"))
        name = clean_text(item.get("item_name"), "未命名項目")
        if item.get("maintenance_type") == "耗材更換" and sub:
            return f"{sub}-{name}"
        return name

    def item_path(item: dict[str, Any]) -> str:
        if item.get("maintenance_type") == "清潔":
            return f"清潔 > {item.get('machine_area') or '-'}"

        main = item.get("main_category") or "-"
        sub = item.get("sub_category") or ""
        if sub:
            return f"耗材更換 > {main} > {sub}"
        return f"耗材更換 > {main}"

    def unique_values(values: list[Any]) -> list[str]:
        result: list[str] = []
        for value in values:
            text = clean_text(value)
            if text and text not in result:
                result.append(text)
        return sorted(result)

    def card(content: ft.Control, padding: int = 16, bgcolor: str = CARD_BG, border_color: str = BORDER) -> ft.Container:
        return ft.Container(
            bgcolor=bgcolor,
            border=ft.border.all(1, border_color),
            border_radius=18,
            padding=padding,
            content=content,
        )

    def primary_style(bg: str = BLUE_BTN) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            bgcolor={
                ft.ControlState.DEFAULT: bg,
                ft.ControlState.HOVERED: bg,
                ft.ControlState.PRESSED: bg,
                ft.ControlState.DISABLED: DISABLED,
            },
            color={
                ft.ControlState.DEFAULT: "#FFFFFF",
                ft.ControlState.HOVERED: "#FFFFFF",
                ft.ControlState.PRESSED: "#FFFFFF",
                ft.ControlState.DISABLED: "#FFFFFF",
            },
            shape=ft.RoundedRectangleBorder(radius=12),
            padding=ft.padding.symmetric(horizontal=14, vertical=12),
            elevation={
                ft.ControlState.DEFAULT: 0,
                ft.ControlState.HOVERED: 1,
                ft.ControlState.PRESSED: 0,
                ft.ControlState.DISABLED: 0,
            },
        )

    def outline_style(color: str = BLUE_BTN, border_color: str = BLUE_BORDER) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            bgcolor={
                ft.ControlState.DEFAULT: "#FFFFFF",
                ft.ControlState.HOVERED: "#F8FAFC",
                ft.ControlState.PRESSED: "#F1F5F9",
                ft.ControlState.DISABLED: "#F1F5F9",
            },
            color={
                ft.ControlState.DEFAULT: color,
                ft.ControlState.HOVERED: color,
                ft.ControlState.PRESSED: color,
                ft.ControlState.DISABLED: DISABLED,
            },
            side={
                ft.ControlState.DEFAULT: ft.BorderSide(1, border_color),
                ft.ControlState.HOVERED: ft.BorderSide(1, color),
                ft.ControlState.PRESSED: ft.BorderSide(1, color),
                ft.ControlState.DISABLED: ft.BorderSide(1, BORDER),
            },
            shape=ft.RoundedRectangleBorder(radius=12),
            padding=ft.padding.symmetric(horizontal=14, vertical=11),
        )

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
                crumb("保養項目管理", None, active=True),
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
                        content=ft.Icon(ft.Icons.ACCOUNT_TREE_OUTLINED, size=31, color=PURPLE_BTN),
                    ),
                    ft.Column(
                        expand=True,
                        spacing=5,
                        controls=[
                            ft.Text("保養項目管理", size=26, weight=ft.FontWeight.BOLD, color=TEXT, max_lines=2),
                            ft.Text(
                                "以設備與區域分層整理清潔、耗材更換項目，避免重複建立與分類錯誤。",
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
                        bgcolor="#FFFFFF",
                        content=ft.Column(
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=14,
                            controls=[
                                ft.Icon(ft.Icons.LOCK_OUTLINE, size=46, color=RED),
                                ft.Text("權限不足", size=24, color=TEXT, weight=ft.FontWeight.BOLD),
                                ft.Text(
                                    "此功能僅限超級管理員使用。一般使用者可回到保養紀錄頁新增日常保養紀錄。",
                                    size=14,
                                    color=TEXT_MUTED,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                ft.ElevatedButton(
                                    text="返回保養紀錄",
                                    icon=ft.Icons.ARROW_BACK,
                                    style=primary_style(BLUE_BTN),
                                    on_click=lambda _: navigate("/maintenance"),
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        )

    # =====================================================
    # 資料處理
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

    def all_items() -> list[dict[str, Any]]:
        return list(state.get("items") or [])

    def active_items() -> list[dict[str, Any]]:
        return [item for item in all_items() if item.get("is_active")]

    def clean_machines() -> list[str]:
        return unique_values([
            item.get("machine_area")
            for item in all_items()
            if item.get("maintenance_type") == "清潔"
        ])

    def consumable_mains() -> list[str]:
        return unique_values([
            item.get("main_category")
            for item in all_items()
            if item.get("maintenance_type") == "耗材更換"
        ])

    def consumable_subs(main_category: str) -> list[str]:
        return unique_values([
            item.get("sub_category") or "未分區"
            for item in all_items()
            if item.get("maintenance_type") == "耗材更換"
            and clean_text(item.get("main_category")) == main_category
        ])

    def ensure_default_selection() -> None:
        if state["selected_type"] == "清潔":
            machines = clean_machines()
            if not state.get("selected_machine") and machines:
                state["selected_machine"] = machines[0]
            return

        mains = consumable_mains()
        if not state.get("selected_main") and mains:
            state["selected_main"] = mains[0]
        subs = consumable_subs(state.get("selected_main") or "")
        if not state.get("selected_sub") and subs:
            state["selected_sub"] = subs[0]

    def current_path_text() -> str:
        if state["selected_type"] == "清潔":
            return f"清潔 > {state.get('selected_machine') or '未選擇'}"
        sub = state.get("selected_sub") or ""
        if sub and sub != "未分區":
            return f"耗材更換 > {state.get('selected_main') or '未選擇'} > {sub}"
        return f"耗材更換 > {state.get('selected_main') or '未選擇'}"

    def current_node_items() -> list[dict[str, Any]]:
        items = all_items()
        if state["selected_type"] == "清潔":
            machine = clean_text(state.get("selected_machine"))
            return [
                item for item in items
                if item.get("maintenance_type") == "清潔"
                and clean_text(item.get("machine_area")) == machine
            ]

        main = clean_text(state.get("selected_main"))
        sub = clean_text(state.get("selected_sub"))
        result = [
            item for item in items
            if item.get("maintenance_type") == "耗材更換"
            and clean_text(item.get("main_category")) == main
        ]
        if sub and sub != "未分區":
            result = [item for item in result if clean_text(item.get("sub_category")) == sub]
        elif sub == "未分區":
            result = [item for item in result if not clean_text(item.get("sub_category"))]

        return result

    def has_duplicate_cleaning(item_name: str, machine_area: str) -> dict[str, Any] | None:
        target_name = normalize_duplicate_text(item_name)
        target_machine = normalize_duplicate_text(machine_area)
        if not target_name or not target_machine:
            return None
        for item in all_items():
            if item.get("maintenance_type") != "清潔":
                continue
            if normalize_duplicate_text(item.get("item_name")) == target_name and normalize_duplicate_text(item.get("machine_area")) == target_machine:
                return item
        return None

    def has_duplicate_consumable(main_category: str, sub_category: str, item_name: str, machine_area: str) -> dict[str, Any] | None:
        target_main = normalize_duplicate_text(main_category)
        target_sub = normalize_duplicate_text(sub_category)
        target_name = normalize_duplicate_text(item_name)
        target_machine = normalize_duplicate_text(machine_area)
        if not target_main or not target_name or not target_machine:
            return None
        for item in all_items():
            if item.get("maintenance_type") != "耗材更換":
                continue
            if (
                normalize_duplicate_text(item.get("main_category")) == target_main
                and normalize_duplicate_text(item.get("sub_category")) == target_sub
                and normalize_duplicate_text(item.get("item_name")) == target_name
                and normalize_duplicate_text(item.get("machine_area")) == target_machine
            ):
                return item
        return None

    def load_data(update_sync_state: bool = True) -> bool:
        """
        管理子頁資料載入。
        這裡必須把任何例外轉成錯誤狀態，避免畫面永久停在「資料同步中」。
        """
        try:
            result = load_maintenance_items_page_data(include_inactive=True)
        except Exception as exc:
            state["items"] = []
            state["count"] = 0
            state["active_count"] = 0
            state["inactive_count"] = 0
            state["error_message"] = f"讀取保養項目管理資料失敗：{exc}"
            if update_sync_state:
                set_sync_state("error", "資料同步失敗", visible=True)
            return False

        data = result.data if isinstance(result.data, dict) else {}

        if result.ok:
            state["items"] = data.get("items") or []
            state["count"] = data.get("count", len(state["items"]))
            state["active_count"] = data.get("active_count", 0)
            state["inactive_count"] = data.get("inactive_count", 0)
            state["error_message"] = ""
            ensure_default_selection()
            if update_sync_state:
                set_sync_state("success", "資料已同步", visible=True)
            return True

        state["items"] = data.get("items") or []
        state["count"] = 0
        state["active_count"] = 0
        state["inactive_count"] = 0
        state["error_message"] = result.message or "讀取保養項目管理資料失敗。"
        if update_sync_state:
            set_sync_state("error", "資料同步失敗", visible=True)
        return False

    def start_background_load(show_loading: bool = True) -> None:
        """
        非阻塞背景載入 + 離頁保護 + 逾時回退。
        - 背景 thread 只改 state，最後集中 rebuild。
        - 若 Supabase 或 service 等待過久，20 秒後顯示錯誤與重試按鈕。
        - 若使用者切離本頁，舊 thread 不再更新 UI。
        """
        state["load_seq"] = int(state.get("load_seq") or 0) + 1
        current_load_seq = state["load_seq"]

        if show_loading:
            set_sync_state("loading", "資料同步中", visible=True)
            if is_active_view():
                rebuild()

        def watchdog():
            time.sleep(20)
            if not is_active_view():
                return
            if state.get("load_seq") != current_load_seq:
                return
            if state.get("loading"):
                state["error_message"] = "保養項目管理資料同步逾時，請按重試。"
                set_sync_state("error", "資料同步逾時", visible=True)
                rebuild()

        def worker():
            ok = False
            try:
                ok = load_data(update_sync_state=True)
            except Exception as exc:
                state["error_message"] = f"讀取保養項目管理資料失敗：{exc}"
                set_sync_state("error", "資料同步失敗", visible=True)
                ok = False

            if not is_active_view():
                return
            if state.get("load_seq") != current_load_seq:
                return

            rebuild()
            if ok:
                hide_sync_badge_later(3.0)

        threading.Thread(target=watchdog, daemon=True).start()
        threading.Thread(target=worker, daemon=True).start()

    def refresh(_=None) -> None:
        start_background_load(show_loading=True)

    # =====================================================
    # 動作
    # =====================================================
    def set_type(value: str) -> None:
        state["selected_type"] = value
        state["active_form"] = None
        state["editing_item"] = None
        if value == "清潔":
            state["selected_main"] = ""
            state["selected_sub"] = ""
            if not state.get("selected_machine"):
                machines = clean_machines()
                state["selected_machine"] = machines[0] if machines else ""
        else:
            state["selected_machine"] = ""
            if not state.get("selected_main"):
                mains = consumable_mains()
                state["selected_main"] = mains[0] if mains else ""
            subs = consumable_subs(state.get("selected_main") or "")
            state["selected_sub"] = subs[0] if subs else ""
        rebuild()

    def select_clean_machine(machine: str) -> None:
        state["selected_type"] = "清潔"
        state["selected_machine"] = machine
        state["active_form"] = None
        state["editing_item"] = None
        rebuild()

    def select_consumable_node(main_category: str, sub_category: str = "") -> None:
        state["selected_type"] = "耗材更換"
        state["selected_main"] = main_category
        state["selected_sub"] = sub_category
        state["active_form"] = None
        state["editing_item"] = None
        rebuild()

    def open_create_form(_=None) -> None:
        state["editing_item"] = None
        if state["selected_type"] == "清潔":
            if not state.get("selected_machine"):
                show_snack("請先選擇清潔項目的設備 / 區域。", success=False)
                return
            state["active_form"] = "create_clean"
        else:
            if not state.get("selected_main"):
                show_snack("請先選擇耗材更換的設備 / 系統。", success=False)
                return
            state["active_form"] = "create_consumable"
        rebuild()

    def open_edit_cycle(item: dict[str, Any]) -> None:
        state["editing_item"] = item
        state["active_form"] = "edit_cycle"
        rebuild()

    def cancel_form(_=None) -> None:
        state["active_form"] = None
        state["editing_item"] = None
        rebuild()

    def run_after_write(result_message: str = "資料已更新。") -> None:
        load_data(update_sync_state=True)
        state["active_form"] = None
        state["editing_item"] = None
        rebuild()
        hide_sync_badge_later(3.0)
        show_snack(result_message, success=True)

    def toggle_active(item: dict[str, Any]) -> None:
        item_id = item.get("id") or ""
        next_active = not bool(item.get("is_active"))
        if not item_id:
            show_snack("缺少保養項目 ID。", success=False)
            return

        if not action_lock.acquire(blocking=False):
            show_snack("資料寫入中，請稍候。", success=False)
            return

        def worker():
            try:
                result = set_maintenance_item_active(item_id=item_id, is_active=next_active)
                if not is_active_view():
                    return
                if result.ok:
                    run_after_write(result.message or "項目狀態已更新。")
                else:
                    show_snack(result.message or "項目狀態更新失敗。", success=False)
            finally:
                try:
                    action_lock.release()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    # =====================================================
    # UI：統計 / 樹 / 清單
    # =====================================================
    def build_summary_cards(is_mobile: bool) -> ft.Control:
        total = state.get("count", 0)
        active = state.get("active_count", 0)
        inactive = state.get("inactive_count", 0)
        clean_count = len([item for item in all_items() if item.get("maintenance_type") == "清潔"])
        material_count = len([item for item in all_items() if item.get("maintenance_type") == "耗材更換"])

        data = [
            ("全部項目", total, ft.Icons.FORMAT_LIST_BULLETED, BLUE_BTN, BLUE_SOFT),
            ("啟用中", active, ft.Icons.CHECK_CIRCLE_OUTLINE, GREEN, GREEN_SOFT),
            ("已停用", inactive, ft.Icons.PAUSE_CIRCLE_OUTLINE, TEXT_MUTED, "#F1F5F9"),
            ("清潔 / 耗材", f"{clean_count} / {material_count}", ft.Icons.ACCOUNT_TREE_OUTLINED, PURPLE_BTN, PURPLE_SOFT),
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
            return ft.Column(
                spacing=10,
                controls=[
                    ft.Row(spacing=10, controls=[ft.Container(expand=True, content=cards[0]), ft.Container(expand=True, content=cards[1])]),
                    ft.Row(spacing=10, controls=[ft.Container(expand=True, content=cards[2]), ft.Container(expand=True, content=cards[3])]),
                ],
            )

        return ft.Row(spacing=12, controls=[ft.Container(expand=True, content=c) for c in cards])

    def type_switch() -> ft.Control:
        def btn(label: str, color: str, soft: str):
            active = state["selected_type"] == label
            return ft.Container(
                expand=True,
                height=48,
                border_radius=14,
                bgcolor=soft if active else "#FFFFFF",
                border=ft.border.all(1, color if active else BORDER),
                alignment=ft.Alignment(0, 0),
                ink=True,
                on_click=lambda _: set_type(label),
                content=ft.Text(
                    label,
                    size=14,
                    color=color if active else TEXT_MUTED,
                    weight=ft.FontWeight.BOLD,
                ),
            )

        return ft.Row(
            spacing=10,
            controls=[
                btn("清潔", BLUE_BTN, BLUE_SOFT),
                btn("耗材更換", ORANGE_BTN, ORANGE_SOFT),
            ],
        )

    def node_count(label_type: str, key_a: str = "", key_b: str = "") -> int:
        if label_type == "clean":
            return len([item for item in all_items() if item.get("maintenance_type") == "清潔" and clean_text(item.get("machine_area")) == key_a])

        rows = [item for item in all_items() if item.get("maintenance_type") == "耗材更換" and clean_text(item.get("main_category")) == key_a]
        if key_b:
            if key_b == "未分區":
                rows = [item for item in rows if not clean_text(item.get("sub_category"))]
            else:
                rows = [item for item in rows if clean_text(item.get("sub_category")) == key_b]
        return len(rows)

    def tree_node(label: str, selected: bool, icon, color: str, subtitle: str, on_click) -> ft.Control:
        return ft.Container(
            bgcolor=(BLUE_SOFT if color == BLUE_BTN else ORANGE_SOFT if color == ORANGE_BTN else PURPLE_SOFT) if selected else "#FFFFFF",
            border=ft.border.all(1, color if selected else BORDER),
            border_radius=12,
            padding=ft.padding.symmetric(horizontal=11, vertical=9),
            ink=True,
            on_click=on_click,
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(icon, size=18, color=color if selected else TEXT_MUTED),
                    ft.Column(
                        expand=True,
                        spacing=2,
                        controls=[
                            ft.Text(label, size=13, color=TEXT, weight=ft.FontWeight.BOLD if selected else ft.FontWeight.W_500, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(subtitle, size=11, color=TEXT_MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=color if selected else TEXT_MUTED),
                ],
            ),
        )

    def build_desktop_tree() -> ft.Control:
        clean_controls: list[ft.Control] = []
        for machine in clean_machines():
            selected = state["selected_type"] == "清潔" and state.get("selected_machine") == machine
            clean_controls.append(
                tree_node(
                    machine,
                    selected,
                    ft.Icons.CLEANING_SERVICES_OUTLINED,
                    BLUE_BTN,
                    f"{node_count('clean', machine)} 筆項目",
                    lambda _, m=machine: select_clean_machine(m),
                )
            )

        material_controls: list[ft.Control] = []
        for main in consumable_mains():
            main_selected = state["selected_type"] == "耗材更換" and state.get("selected_main") == main and not state.get("selected_sub")
            material_controls.append(
                tree_node(
                    main,
                    main_selected,
                    ft.Icons.INVENTORY_2_OUTLINED,
                    ORANGE_BTN,
                    f"{node_count('material', main)} 筆項目",
                    lambda _, m=main: select_consumable_node(m, ""),
                )
            )
            for sub in consumable_subs(main):
                selected = state["selected_type"] == "耗材更換" and state.get("selected_main") == main and state.get("selected_sub") == sub
                material_controls.append(
                    ft.Container(
                        margin=ft.margin.only(left=18),
                        content=tree_node(
                            sub,
                            selected,
                            ft.Icons.SUBDIRECTORY_ARROW_RIGHT,
                            ORANGE_BTN,
                            f"{node_count('material', main, sub)} 筆項目",
                            lambda _, m=main, s=sub: select_consumable_node(m, s),
                        ),
                    )
                )

        return card(
            padding=16,
            content=ft.Column(
                spacing=14,
                controls=[
                    section_title("保養項目地圖", "從既有結構選擇新增位置。"),
                    type_switch(),
                    ft.Divider(height=4),
                    ft.Text("清潔", size=13, color=BLUE_BTN, weight=ft.FontWeight.BOLD),
                    ft.Column(spacing=8, controls=clean_controls or [ft.Text("尚無清潔項目。", size=13, color=TEXT_MUTED)]),
                    ft.Container(height=4),
                    ft.Text("耗材更換", size=13, color=ORANGE_BTN, weight=ft.FontWeight.BOLD),
                    ft.Column(spacing=8, controls=material_controls or [ft.Text("尚無耗材項目。", size=13, color=TEXT_MUTED)]),
                ],
            ),
        )

    def status_badge(item: dict[str, Any]) -> ft.Container:
        active = bool(item.get("is_active"))
        return ft.Container(
            padding=ft.padding.symmetric(horizontal=9, vertical=4),
            border_radius=8,
            bgcolor=GREEN_SOFT if active else "#F1F5F9",
            border=ft.border.all(1, GREEN_BORDER if active else BORDER),
            content=ft.Text(
                "啟用" if active else "停用",
                size=12,
                color=GREEN if active else TEXT_MUTED,
                weight=ft.FontWeight.BOLD,
            ),
        )

    def build_item_row(item: dict[str, Any]) -> ft.Control:
        active = bool(item.get("is_active"))
        icon = ft.Icons.CLEANING_SERVICES_OUTLINED if item.get("maintenance_type") == "清潔" else ft.Icons.INVENTORY_2_OUTLINED
        color = BLUE_BTN if item.get("maintenance_type") == "清潔" else ORANGE_BTN

        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.border.all(1, BORDER),
            border_radius=14,
            padding=14,
            opacity=1 if active else 0.72,
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
                                bgcolor=BLUE_SOFT if color == BLUE_BTN else ORANGE_SOFT,
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(icon, size=22, color=color),
                            ),
                            ft.Column(
                                expand=True,
                                spacing=4,
                                controls=[
                                    ft.Text(item_display_name(item), size=16, color=TEXT, weight=ft.FontWeight.BOLD, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                    ft.Text(item_path(item), size=12, color=TEXT_MUTED, max_lines=2),
                                    ft.Text(f"週期：{item.get('cycle_days') or 0} 天｜排序：{item.get('sort_order') or 999}", size=12, color=TEXT_MUTED),
                                ],
                            ),
                            status_badge(item),
                        ],
                    ),
                    ft.ResponsiveRow(
                        columns=12,
                        spacing=10,
                        run_spacing=10,
                        controls=[
                            ft.Container(
                                col={"xs": 6, "md": 4},
                                content=ft.OutlinedButton(
                                    text="編輯週期",
                                    icon=ft.Icons.EVENT_REPEAT_OUTLINED,
                                    style=outline_style(PURPLE_BTN, PURPLE_BORDER),
                                    on_click=lambda _, current=item: open_edit_cycle(current),
                                ),
                            ),
                            ft.Container(
                                col={"xs": 6, "md": 4},
                                content=ft.OutlinedButton(
                                    text="停用" if active else "啟用",
                                    icon=ft.Icons.PAUSE_CIRCLE_OUTLINE if active else ft.Icons.PLAY_CIRCLE_OUTLINE,
                                    style=outline_style(RED if active else GREEN, RED_BORDER if active else GREEN_BORDER),
                                    on_click=lambda _, current=item: toggle_active(current),
                                ),
                            ),
                        ],
                    ),
                ],
            ),
        )

    def build_node_detail() -> ft.Control:
        items = current_node_items()
        active = len([item for item in items if item.get("is_active")])
        inactive = len(items) - active

        create_label = "在此位置新增清潔項目" if state["selected_type"] == "清潔" else "在此位置新增耗材項目"
        create_icon = ft.Icons.CLEANING_SERVICES_OUTLINED if state["selected_type"] == "清潔" else ft.Icons.INVENTORY_2_OUTLINED
        create_color = BLUE_BTN if state["selected_type"] == "清潔" else ORANGE_BTN

        item_controls = [build_item_row(item) for item in items]
        if not item_controls:
            item_controls = [
                card(
                    padding=22,
                    bgcolor="#FFFFFF",
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.SEARCH_OFF_OUTLINED, size=34, color=TEXT_MUTED),
                            ft.Text("目前位置尚未建立保養項目。", size=14, color=TEXT_MUTED),
                            ft.Text("請確認位置正確後，再從此節點新增項目。", size=12, color=TEXT_MUTED),
                        ],
                    ),
                )
            ]

        controls: list[ft.Control] = [
            ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Column(
                        expand=True,
                        spacing=4,
                        controls=[
                            ft.Text("目前位置", size=12, color=TEXT_MUTED, weight=ft.FontWeight.W_600),
                            ft.Text(current_path_text(), size=22, color=TEXT, weight=ft.FontWeight.BOLD, max_lines=3),
                            ft.Text(f"此位置共 {len(items)} 筆，啟用 {active} 筆，停用 {inactive} 筆。", size=13, color=TEXT_MUTED),
                        ],
                    ),
                    ft.ElevatedButton(
                        text=create_label,
                        icon=create_icon,
                        style=primary_style(create_color),
                        on_click=open_create_form,
                    ),
                ],
            ),
        ]

        form = build_active_form()
        if form:
            controls.append(form)

        controls.extend([
            ft.Divider(height=12),
            section_title("既有項目", "同一位置下的項目會在新增前用來比對重複。"),
            ft.Column(spacing=10, controls=item_controls),
        ])

        return card(padding=18, content=ft.Column(spacing=14, controls=controls))

    # =====================================================
    # UI：表單
    # =====================================================
    def make_field(label: str, value: str = "", hint: str = "", read_only: bool = False, multiline: bool = False, keyboard_type=None) -> ft.TextField:
        return ft.TextField(
            label=label,
            value=value,
            hint_text=hint,
            read_only=read_only,
            multiline=multiline,
            min_lines=2 if multiline else 1,
            max_lines=4 if multiline else 1,
            keyboard_type=keyboard_type,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE_BTN,
            bgcolor="#FFFFFF",
            filled=True,
            text_size=14,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=11),
        )

    def build_create_clean_form() -> ft.Control:
        machine = clean_text(state.get("selected_machine"))
        item_tf = make_field("清潔項目名稱 *", hint="例如：旋風分離器、油劑槽周邊")
        machine_tf = make_field("設備 / 區域", value=machine, read_only=True)
        cycle_tf = make_field("週期天數 *", value="30", hint="例如：7、14、30", keyboard_type=ft.KeyboardType.NUMBER)
        desc_tf = make_field("備註 / 注意事項", hint="可輸入清潔方式或判定基準", multiline=True)

        submit_btn = ft.ElevatedButton(text="確認新增", icon=ft.Icons.CHECK_CIRCLE_OUTLINE, style=primary_style(BLUE_BTN))

        def submit(_=None):
            if not action_lock.acquire(blocking=False):
                show_snack("資料寫入中，請稍候。", success=False)
                return

            item_name = clean_text(item_tf.value)
            cycle_days = to_int(cycle_tf.value, 0)
            desc = clean_text(desc_tf.value)

            if not item_name:
                action_lock.release()
                show_snack("請輸入清潔項目名稱。", success=False)
                return
            if cycle_days <= 0:
                action_lock.release()
                show_snack("週期天數必須大於 0。", success=False)
                return

            duplicate = has_duplicate_cleaning(item_name, machine)
            if duplicate:
                action_lock.release()
                show_snack(f"已存在相同清潔項目：{item_display_name(duplicate)}｜{duplicate.get('machine_area') or '-'}。", success=False)
                return

            def worker():
                try:
                    result = create_cleaning_item(
                        item_name=item_name,
                        machine_area=machine,
                        cycle_days=cycle_days,
                        sort_order=999,
                        description=desc,
                    )
                    if not is_active_view():
                        return
                    if result.ok:
                        run_after_write(result.message or "清潔項目已新增。")
                    else:
                        show_snack(result.message or "新增清潔項目失敗。", success=False)
                finally:
                    try:
                        action_lock.release()
                    except Exception:
                        pass

            threading.Thread(target=worker, daemon=True).start()

        submit_btn.on_click = submit

        return card(
            padding=16,
            bgcolor="#F8FAFC",
            border_color=BLUE_BORDER,
            content=ft.Column(
                spacing=12,
                controls=[
                    section_title("新增清潔項目", "系統已依目前節點自動帶入設備 / 區域。"),
                    machine_tf,
                    item_tf,
                    cycle_tf,
                    desc_tf,
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.OutlinedButton(text="取消", icon=ft.Icons.CLOSE, style=outline_style(), on_click=cancel_form),
                            submit_btn,
                        ],
                    ),
                ],
            ),
        )

    def build_create_consumable_form() -> ft.Control:
        main = clean_text(state.get("selected_main"))
        sub = clean_text(state.get("selected_sub"))
        if sub == "未分區":
            sub = ""
        default_machine = f"{main}{sub}" if sub else main

        main_tf = make_field("設備 / 系統", value=main, read_only=True)
        sub_tf = make_field("耗材類型 / 區段", value=sub, read_only=True)
        item_tf = make_field("耗材名稱 *", hint="例如：除油濾芯、冷卻水濾芯、清洗藥水")
        machine_tf = make_field("適用位置 *", value=default_machine, hint="例如：除濕機A管")
        cycle_tf = make_field("週期天數 *", value="30", hint="例如：30、90、180", keyboard_type=ft.KeyboardType.NUMBER)
        desc_tf = make_field("備註 / 注意事項", hint="可輸入規格、廠牌或更換基準", multiline=True)

        submit_btn = ft.ElevatedButton(text="確認新增", icon=ft.Icons.CHECK_CIRCLE_OUTLINE, style=primary_style(ORANGE_BTN))

        def submit(_=None):
            if not action_lock.acquire(blocking=False):
                show_snack("資料寫入中，請稍候。", success=False)
                return

            item_name = clean_text(item_tf.value)
            machine_area = clean_text(machine_tf.value)
            cycle_days = to_int(cycle_tf.value, 0)
            desc = clean_text(desc_tf.value)

            if not item_name:
                action_lock.release()
                show_snack("請輸入耗材名稱。", success=False)
                return
            if not machine_area:
                action_lock.release()
                show_snack("請輸入適用位置。", success=False)
                return
            if cycle_days <= 0:
                action_lock.release()
                show_snack("週期天數必須大於 0。", success=False)
                return

            duplicate = has_duplicate_consumable(main, sub, item_name, machine_area)
            if duplicate:
                action_lock.release()
                show_snack(f"已存在相同耗材項目：{item_path(duplicate)}｜{duplicate.get('item_name') or '-'}。", success=False)
                return

            def worker():
                try:
                    result = create_consumable_item(
                        main_category=main,
                        sub_category=sub,
                        item_name=item_name,
                        machine_area=machine_area,
                        cycle_days=cycle_days,
                        sort_order=999,
                        description=desc,
                    )
                    if not is_active_view():
                        return
                    if result.ok:
                        run_after_write(result.message or "耗材項目已新增。")
                    else:
                        show_snack(result.message or "新增耗材項目失敗。", success=False)
                finally:
                    try:
                        action_lock.release()
                    except Exception:
                        pass

            threading.Thread(target=worker, daemon=True).start()

        submit_btn.on_click = submit

        return card(
            padding=16,
            bgcolor="#F8FAFC",
            border_color=ORANGE_BORDER,
            content=ft.Column(
                spacing=12,
                controls=[
                    section_title("新增耗材項目", "系統已依目前節點自動帶入設備 / 系統與區段。"),
                    main_tf,
                    sub_tf,
                    item_tf,
                    machine_tf,
                    cycle_tf,
                    desc_tf,
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.OutlinedButton(text="取消", icon=ft.Icons.CLOSE, style=outline_style(), on_click=cancel_form),
                            submit_btn,
                        ],
                    ),
                ],
            ),
        )

    def build_edit_cycle_form() -> ft.Control:
        item = state.get("editing_item") or {}
        if not item:
            return ft.Container(height=0)

        cycle_tf = make_field("週期天數 *", value=str(item.get("cycle_days") or 30), keyboard_type=ft.KeyboardType.NUMBER)
        active_dd = ft.Dropdown(
            label="啟用狀態",
            value="啟用" if item.get("is_active") else "停用",
            options=[ft.dropdown.Option("啟用"), ft.dropdown.Option("停用")],
            border_radius=12,
            border_color=BORDER,
            focused_border_color=PURPLE_BTN,
            bgcolor="#FFFFFF",
            filled=True,
        )
        submit_btn = ft.ElevatedButton(text="儲存週期", icon=ft.Icons.SAVE_OUTLINED, style=primary_style(PURPLE_BTN))

        def submit(_=None):
            if not action_lock.acquire(blocking=False):
                show_snack("資料寫入中，請稍候。", success=False)
                return

            cycle_days = to_int(cycle_tf.value, 0)
            if cycle_days <= 0:
                action_lock.release()
                show_snack("週期天數必須大於 0。", success=False)
                return

            def worker():
                try:
                    result = update_item_cycle(
                        item_id=item.get("id") or "",
                        cycle_days=cycle_days,
                        sort_order=None,
                        is_active=(active_dd.value == "啟用"),
                    )
                    if not is_active_view():
                        return
                    if result.ok:
                        run_after_write(result.message or "週期設定已更新。")
                    else:
                        show_snack(result.message or "更新週期失敗。", success=False)
                finally:
                    try:
                        action_lock.release()
                    except Exception:
                        pass

            threading.Thread(target=worker, daemon=True).start()

        submit_btn.on_click = submit

        return card(
            padding=16,
            bgcolor="#F8FAFC",
            border_color=PURPLE_BORDER,
            content=ft.Column(
                spacing=12,
                controls=[
                    section_title("編輯週期", item_display_name(item)),
                    ft.Text(item_path(item), size=13, color=TEXT_MUTED),
                    cycle_tf,
                    active_dd,
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.OutlinedButton(text="取消", icon=ft.Icons.CLOSE, style=outline_style(PURPLE_BTN, PURPLE_BORDER), on_click=cancel_form),
                            submit_btn,
                        ],
                    ),
                ],
            ),
        )

    def build_active_form() -> ft.Control | None:
        active_form = state.get("active_form")
        if active_form == "create_clean":
            return build_create_clean_form()
        if active_form == "create_consumable":
            return build_create_consumable_form()
        if active_form == "edit_cycle":
            return build_edit_cycle_form()
        return None

    # =====================================================
    # 手機版：一步一步選位置
    # =====================================================
    def mobile_chip(label: str, selected: bool, color: str, on_click) -> ft.Control:
        return ft.Container(
            height=42,
            border_radius=21,
            bgcolor=(BLUE_SOFT if color == BLUE_BTN else ORANGE_SOFT) if selected else "#FFFFFF",
            border=ft.border.all(1, color if selected else BORDER),
            padding=ft.padding.symmetric(horizontal=13),
            alignment=ft.Alignment(0, 0),
            ink=True,
            on_click=on_click,
            content=ft.Text(
                label,
                size=13,
                color=color if selected else TEXT_MUTED,
                weight=ft.FontWeight.BOLD if selected else ft.FontWeight.W_500,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        )

    def build_mobile_steps() -> ft.Control:
        controls: list[ft.Control] = [
            section_title("步驟 1：選擇類型", "先選清潔或耗材更換。"),
            type_switch(),
        ]

        if state["selected_type"] == "清潔":
            controls.append(section_title("步驟 2：選擇設備 / 區域", "選定後下方會列出此位置既有項目。"))
            machine_controls = [
                mobile_chip(machine, state.get("selected_machine") == machine, BLUE_BTN, lambda _, m=machine: select_clean_machine(m))
                for machine in clean_machines()
            ]
            controls.append(ft.Row(wrap=True, spacing=8, run_spacing=8, controls=machine_controls or [ft.Text("尚無清潔節點。", size=13, color=TEXT_MUTED)]))
        else:
            controls.append(section_title("步驟 2：選擇設備 / 系統", "再選耗材所在設備或系統。"))
            main_controls = [
                mobile_chip(main, state.get("selected_main") == main, ORANGE_BTN, lambda _, m=main: select_consumable_node(m, ""))
                for main in consumable_mains()
            ]
            controls.append(ft.Row(wrap=True, spacing=8, run_spacing=8, controls=main_controls or [ft.Text("尚無耗材節點。", size=13, color=TEXT_MUTED)]))

            if state.get("selected_main"):
                controls.append(section_title("步驟 3：選擇區段", "例如 A管、B管、清洗藥水。"))
                sub_controls = [
                    mobile_chip(sub, state.get("selected_sub") == sub, ORANGE_BTN, lambda _, m=state.get("selected_main") or "", s=sub: select_consumable_node(m, s))
                    for sub in consumable_subs(state.get("selected_main") or "")
                ]
                controls.append(ft.Row(wrap=True, spacing=8, run_spacing=8, controls=sub_controls or [ft.Text("此設備尚無區段。", size=13, color=TEXT_MUTED)]))

        return card(padding=16, content=ft.Column(spacing=14, controls=controls))

    # =====================================================
    # Layout
    # =====================================================
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
                    ft.TextButton(text="重試", on_click=refresh),
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
                    ft.Text("正在讀取保養項目管理資料...", size=14, color=BLUE_BTN, weight=ft.FontWeight.BOLD),
                ],
            ),
        )

    def build_mobile_layout() -> ft.Control:
        page.bgcolor = BG
        controls: list[ft.Control] = [
            build_header(),
            build_error_banner(),
            build_summary_cards(is_mobile=True),
        ]

        if state.get("loading") and not all_items():
            controls.append(build_loading_block())
        else:
            controls.extend([
                build_mobile_steps(),
                build_node_detail(),
            ])

        controls.append(ft.Container(height=90))

        return ft.Container(
            expand=True,
            bgcolor=BG,
            padding=ft.padding.only(left=16, right=16, top=18, bottom=18),
            content=ft.Column(
                expand=True,
                scroll=ft.ScrollMode.AUTO,
                spacing=18,
                controls=controls,
            ),
        )

    def build_desktop_layout() -> ft.Control:
        page.bgcolor = BG
        controls: list[ft.Control] = [
            build_header(),
            build_error_banner(),
            build_summary_cards(is_mobile=False),
        ]

        if state.get("loading") and not all_items():
            controls.append(build_loading_block())
        else:
            controls.append(
                ft.Row(
                    spacing=18,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Container(width=330, content=build_desktop_tree()),
                        ft.Container(expand=True, content=build_node_detail()),
                    ],
                )
            )

        controls.append(ft.Container(height=80))

        return ft.Container(
            expand=True,
            bgcolor=BG,
            padding=ft.padding.only(left=24, right=24, top=22, bottom=18),
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
                    main_host.content = build_mobile_layout() if width < MOBILE_WIDTH else build_desktop_layout()

                try:
                    main_host.update()
                except Exception:
                    page.update()
        except Exception as ex:
            print("maintenance_items rebuild failed:", repr(ex))

    # =====================================================
    # 初始化
    # =====================================================
    if not is_super_admin():
        main_host.content = build_access_denied()
        return root

    width = page.width or 390
    main_host.content = build_mobile_layout() if width < MOBILE_WIDTH else build_desktop_layout()
    start_background_load(show_loading=True)

    return root
