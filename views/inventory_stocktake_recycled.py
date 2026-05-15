# =====================================================
# KNH MMS v2
# File: views/inventory_stocktake_recycled.py
# File Revision: 2026-05-15-recycled-subpage-r12
# Status: lock non-editable list actions and compact list buttons
# Last Updated: 2026-05-15 Asia/Taipei
#
# Purpose:
# - 回用料逐筆盤點子頁。
# - 採待核對輕量清單 + 單筆核對卡片模式，避免一次渲染大量完整卡片造成 Flet Web 卡頓。
#
# Major Changes in This Revision:
# - r8 [BUG FIX] select_recycled_item 改為 debounced rebuild。
# - r8 [BUG FIX] _item_note_field 提升為 view-level 控制項。
# - r8 [BUG FIX] load 函式移除 show_loading 階段的 immediate rebuild()。
# - r8 [BUG FIX] 初始化改為先顯示 loading placeholder。
# - r9 [BUG FIX] create_recycled_count_action 建立成功後不再從 worker thread
#     呼叫 navigate()，改為直接將新盤點單 detail 載入 state 並 rebuild()，
#     消除背景 thread 觸發路由切換的潛在白畫面風險。
#     網址列不會帶 ?count_id=，但畫面會直接進入新盤點單明細。
# - r9.1 [BUG FIX] parse_count_id_from_route 只讀取網址列 ?count_id=，
#     不再 fallback 到 session_data 裡的上一張盤點單 ID，
#     確保 /inventory/stocktake/recycled 一定回到回用料盤點單列表。
#
# Notes:
# - Flet 0.84。
# - 不使用 page.push_route()，導頁一律使用 page.go() 或 main.py 提供的 _navigate。
# - 時間與資料寫入邏輯由 services/stocktake_service.py 統一使用 Asia/Taipei。
# - 第一版不自動修改 recycled_materials 狀態，只保留盤點紀錄。
# - r9.1 只改 views/inventory_stocktake_recycled.py，不動其他檔案。
# - r10 [UX] 新增單筆核對操作回饋與導頁防連點。
# - r11 [FEATURE] 補上回用料盤點單作廢流程：超級管理員可作廢草稿 / 待審核盤點單，作廢原因必填。
#   使用既有 services.stocktake_service.void_inventory_count，不直接修改資料庫。
# - r11 只改 views/inventory_stocktake_recycled.py，不動 main.py / service / repo。
# - r12 [UX] 回用料盤點單列表中，只有草稿盤點單顯示「進入逐筆盤點」；
#   待審核改為「查看 / 審核」，已確認 / 已作廢顯示鎖定提示，不再以逐筆盤點入口呈現。
# - r12 [UX] 列表卡片的主要動作按鈕改為較小的 compact button，避免手機版大面積綠色按鈕過重。
# - r12 只改 views/inventory_stocktake_recycled.py，不動 main.py / service / repo。
# =====================================================

from __future__ import annotations

import threading
from typing import Any
from urllib.parse import parse_qs, urlparse

import flet as ft

from services.stocktake_service import (
    confirm_inventory_count,
    create_new_inventory_count,
    load_inventory_count_detail,
    load_inventory_counts,
    now_taipei,
    submit_inventory_count,
    update_count_recycled_item_check,
    void_inventory_count,
)


# ============================================================
# 色彩設定
# ============================================================
BG = "#F8FAFC"
CARD = "#FFFFFF"
TEXT = "#0F172A"
TEXT_MUTED = "#64748B"
BORDER = "#E2E8F0"
INPUT_BG = "#F8FAFC"

BLUE = "#2F80ED"
BLUE_SOFT = "#E5F0FF"
BLUE_BORDER = "#B0D0FF"
BLUE_BTN = "#4F7FB8"

GREEN = "#10B981"
GREEN_SOFT = "#ECFDF5"
GREEN_BORDER = "#A7F3D0"
GREEN_BTN = "#3F8F5A"

ORANGE = "#F97316"
ORANGE_SOFT = "#FFF7ED"
ORANGE_BORDER = "#FDBA74"
ORANGE_BTN = "#C96D32"

RED = "#DC2626"
RED_SOFT = "#FEF2F2"
RED_BORDER = "#FECACA"
RED_BTN = "#C2410C"

PURPLE = "#7C3AED"
PURPLE_SOFT = "#F3E8FF"
PURPLE_BORDER = "#D8B4FE"

GRAY_SOFT = "#F1F5F9"
DISABLED = "#94A3B8"


STATUS_OPTIONS = [
    ("confirmed", "在庫確認", GREEN, GREEN_SOFT, GREEN_BORDER, ft.Icons.CHECK_CIRCLE_OUTLINE),
    ("missing", "找不到實物", RED, RED_SOFT, RED_BORDER, ft.Icons.SEARCH_OFF_OUTLINED),
    ("used_not_recorded", "已領用未登錄", RED, RED_SOFT, RED_BORDER, ft.Icons.OUTBOX_OUTLINED),
    ("scrap_required", "需報廢", RED, RED_SOFT, RED_BORDER, ft.Icons.DELETE_FOREVER_OUTLINED),
    ("data_abnormal", "資料異常", ORANGE, ORANGE_SOFT, ORANGE_BORDER, ft.Icons.REPORT_PROBLEM_OUTLINED),
]

STATUS_LABELS = {value: label for value, label, *_ in STATUS_OPTIONS}


def InventoryStocktakeRecycledContent(page: ft.Page) -> ft.Control:
    """
    給 main.py / shell() 呼叫：
        InventoryStocktakeRecycledContent(page)

    本頁只處理回用料逐筆盤點。
    """

    if not hasattr(page, "session_data") or not isinstance(page.session_data, dict):
        page.session_data = {}

    view_token = object()
    page.session_data["_stocktake_recycled_view_token"] = view_token

    state: dict[str, Any] = {
        "alive": True,
        "loading": True,
        "busy": False,
        "status_visible": True,
        "status_theme": "blue",
        "status_message": "回用料盤點資料同步中",
        "error_message": "",
        "counts": [],
        "detail": None,
        "active_count_id": "",
        "show_create_form": False,
        "show_void_form": False,
        "selected_recycled_item_id": "",
        "saving_recycled_item_ids": set(),
        "navigation_busy": False,
        "last_action_message": "",
        "last_action_theme": "green",
    }

    ui_lock = threading.RLock()

    # r8：debounce 用的 Timer 參考，存在 list 裡方便 nonlocal 替換
    _debounce_timer: list[threading.Timer | None] = [None]

    # =====================================================
    # 基礎工具
    # =====================================================
    def session_get(key: str, default=None):
        try:
            return page.session_data.get(key, default)
        except Exception:
            return default

    def current_user_id():
        value = session_get("user_id") or session_get("user_record_id")
        return str(value or "").strip() or None

    def current_user_name():
        return str(session_get("user_name") or "").strip() or None

    def is_super_admin() -> bool:
        return session_get("role") == "超級管理員"

    def is_active_view() -> bool:
        route = str(getattr(page, "route", "") or "")
        return (
            bool(state.get("alive", True))
            and page.session_data.get("_stocktake_recycled_view_token") is view_token
            and route.startswith("/inventory/stocktake/recycled")
        )

    def safe_page_update() -> None:
        if not is_active_view():
            return
        try:
            page.update()
        except Exception as ex:
            print("recycled stocktake page.update failed:", repr(ex), flush=True)

    def navigate(route: str) -> None:
        nav = session_get("_navigate")
        if callable(nav):
            nav(route)
            return
        page.go(route)

    def guarded_navigate(route: str, message: str = "正在切換頁面...") -> None:
        """
        r10：導頁防連點。

        回用料子頁在列表 / 明細間短時間多次切換時，會連續觸發 route_change、
        loading placeholder 與背景資料載入。此函式讓同一個 view 只送出一次導頁，
        並立即顯示狀態，避免使用者以為沒有點到而連點。
        """
        if state.get("navigation_busy"):
            return

        state["navigation_busy"] = True
        set_status(message, "blue", True)

        try:
            show_snack(message, success=True)
        except Exception:
            pass

        try:
            navigate(route)
        except Exception as ex:
            state["navigation_busy"] = False
            set_status(f"切換頁面失敗：{ex}", "red", True)
            rebuild()

    def parse_count_id_from_route() -> str:
        """
        r9.1：只依網址列 ?count_id= 判斷是否進入指定明細。

        重要：不再 fallback 到 session_data["_stocktake_recycled_count_id"]。
        這樣使用者點「回用料盤點單列表」進入 /inventory/stocktake/recycled 時，
        會穩定回到列表，而不是被上一張盤點單 ID 拉回明細。
        """
        route = str(getattr(page, "route", "") or "")
        try:
            parsed = urlparse(route)
            query = parse_qs(parsed.query or "")
            count_id = (query.get("count_id") or [""])[0]
            if count_id:
                return str(count_id).strip()
        except Exception:
            pass
        return ""

    def remember_count_id(count_id: str) -> None:
        try:
            page.session_data["_stocktake_recycled_count_id"] = str(count_id or "").strip()
        except Exception:
            pass

    def to_text(value: Any, default: str = "-") -> str:
        text = str(value if value is not None else "").strip()
        return text if text else default

    def fmt_num(value: Any, suffix: str = "") -> str:
        try:
            number = float(value if value not in [None, ""] else 0)
            if number.is_integer():
                text = f"{int(number):,}"
            else:
                text = f"{number:,.2f}".rstrip("0").rstrip(".")
            return f"{text}{suffix}"
        except Exception:
            return f"0{suffix}"

    def today_text() -> str:
        return now_taipei().strftime("%Y-%m-%d")

    def set_status(message: str, theme: str = "blue", visible: bool = True) -> None:
        state["status_message"] = str(message or "")
        state["status_theme"] = theme
        state["status_visible"] = visible

    def show_snack(message: str, success: bool = True) -> None:
        snack = ft.SnackBar(
            content=ft.Text(str(message), color="#FFFFFF", weight=ft.FontWeight.W_600),
            bgcolor=GREEN if success else RED,
            duration=2500,
        )
        try:
            page.overlay.append(snack)
        except Exception:
            pass
        snack.open = True
        safe_page_update()

    def rebuild() -> None:
        if not is_active_view():
            return
        try:
            with ui_lock:
                if not is_active_view():
                    return
                main_host.content = build_page()
                page.update()
        except Exception as ex:
            print("recycled stocktake rebuild failed:", repr(ex), flush=True)

    # =====================================================
    # r8：view-level note_field（不在 build 函式內每次重建）
    # =====================================================
    _item_note_field = ft.TextField(
        hint_text="備註（異常或找不到實物時建議填寫）",
        hint_style=ft.TextStyle(size=13, color="#94A3B8"),
        label="備註（選填）",
        label_style=ft.TextStyle(size=13, color="#94A3B8"),
        bgcolor="#FFFFFF",
        border_color=BORDER,
        focused_border_color=GREEN,
        border_radius=12,
        text_size=14,
        height=78,
        multiline=True,
        min_lines=2,
        max_lines=2,
        content_padding=ft.padding.symmetric(horizontal=14, vertical=10),
    )

    # =====================================================
    # UI 工具
    # =====================================================
    def section_title(title: str, subtitle: str | None = None) -> ft.Column:
        controls: list[ft.Control] = [
            ft.Text(title, size=20, weight=ft.FontWeight.BOLD, color=TEXT),
        ]
        if subtitle:
            controls.append(ft.Text(subtitle, size=13, color=TEXT_MUTED, max_lines=3))
        return ft.Column(spacing=4, controls=controls)

    def pill_button(
        label: str,
        icon,
        color: str,
        on_click=None,
        bgcolor: str = "#FFFFFF",
        border_color: str | None = None,
        disabled: bool = False,
        expand: bool = False,
        height: int = 50,
    ) -> ft.Container:
        safe_color = DISABLED if disabled else color
        safe_border = "#CBD5E1" if disabled else (border_color or color)
        safe_bg = "#F8FAFC" if disabled else bgcolor
        return ft.Container(
            height=height,
            expand=expand,
            border_radius=height / 2,
            bgcolor=safe_bg,
            border=ft.border.all(1.5, safe_border),
            padding=ft.padding.symmetric(horizontal=14),
            alignment=ft.Alignment(0, 0),
            ink=False,
            opacity=0.72 if disabled else 1,
            on_click=None if disabled else on_click,
            content=ft.Row(
                tight=True,
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(icon, size=18, color=safe_color),
                    ft.Text(
                        label,
                        size=14,
                        color=safe_color,
                        weight=ft.FontWeight.W_700,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
            ),
        )

    def native_button(label: str, icon, bg: str, fg: str = "#FFFFFF", on_click=None, disabled: bool = False, expand: bool = False):
        return pill_button(
            label=label,
            icon=icon,
            color=fg if not disabled else DISABLED,
            bgcolor=bg if not disabled else "#F8FAFC",
            border_color=bg if not disabled else "#CBD5E1",
            on_click=on_click,
            disabled=disabled,
            expand=expand,
            height=52,
        )

    def native_outline_button(label: str, icon, color: str, on_click=None, disabled: bool = False, expand: bool = False):
        return pill_button(
            label=label,
            icon=icon,
            color=color,
            bgcolor="#FFFFFF",
            border_color=color,
            on_click=on_click,
            disabled=disabled,
            expand=expand,
            height=52,
        )

    def compact_list_button(
        label: str,
        icon,
        color: str,
        on_click=None,
        bgcolor: str = "#FFFFFF",
        border_color: str | None = None,
        disabled: bool = False,
    ) -> ft.Control:
        """
        r12：列表卡片使用的較小動作按鈕。

        不再讓「進入逐筆盤點」佔滿整張卡片寬度，避免手機版綠色區塊過重。
        """
        safe_color = DISABLED if disabled else color
        safe_border = "#CBD5E1" if disabled else (border_color or color)
        safe_bg = "#F8FAFC" if disabled else bgcolor

        return ft.Container(
            width=238,
            height=44,
            border_radius=22,
            bgcolor=safe_bg,
            border=ft.border.all(1.4, safe_border),
            padding=ft.padding.symmetric(horizontal=12),
            alignment=ft.Alignment(0, 0),
            ink=False,
            opacity=0.72 if disabled else 1,
            on_click=None if disabled else on_click,
            content=ft.Row(
                tight=True,
                spacing=7,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(icon, size=17, color=safe_color),
                    ft.Text(
                        label,
                        size=13,
                        color=safe_color,
                        weight=ft.FontWeight.W_700,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
            ),
        )

    def locked_count_hint(status_label: str) -> ft.Control:
        return ft.Container(
            border_radius=14,
            bgcolor="#F8FAFC",
            border=ft.border.all(1, BORDER),
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.LOCK_OUTLINED, size=17, color=TEXT_MUTED),
                    ft.Text(
                        f"{status_label or '已鎖定'}，不可逐筆盤點。",
                        size=13,
                        color=TEXT_MUTED,
                        weight=ft.FontWeight.W_600,
                    ),
                ],
            ),
        )

    def build_count_list_action(count: dict[str, Any]) -> ft.Control:
        status = str(count.get("status") or "draft")
        status_text = str(count.get("status_label") or "")
        count_id = str(count.get("id") or "")

        if status == "draft":
            return ft.Row(
                alignment=ft.MainAxisAlignment.END,
                controls=[
                    compact_list_button(
                        "進入逐筆盤點",
                        ft.Icons.ARROW_FORWARD,
                        "#FFFFFF",
                        bgcolor=GREEN_BTN,
                        border_color=GREEN_BTN,
                        on_click=lambda e, cid=count_id: guarded_navigate(
                            f"/inventory/stocktake/recycled?count_id={cid}",
                            "正在前往逐筆盤點...",
                        ),
                        disabled=state.get("navigation_busy"),
                    )
                ],
            )

        if status == "submitted" and is_super_admin():
            return ft.Row(
                alignment=ft.MainAxisAlignment.END,
                controls=[
                    compact_list_button(
                        "查看 / 審核",
                        ft.Icons.VISIBILITY_OUTLINED,
                        ORANGE,
                        bgcolor="#FFFFFF",
                        border_color=ORANGE_BORDER,
                        on_click=lambda e, cid=count_id: guarded_navigate(
                            f"/inventory/stocktake/recycled?count_id={cid}",
                            "正在開啟待審核盤點單...",
                        ),
                        disabled=state.get("navigation_busy"),
                    )
                ],
            )

        return locked_count_hint(status_text)

    def result_action_button(
        label: str,
        icon,
        color: str,
        soft: str,
        border: str,
        on_click=None,
        disabled: bool = False,
    ) -> ft.Control:
        safe_color = DISABLED if disabled else color
        safe_bg = "#F8FAFC" if disabled else soft
        safe_border = "#CBD5E1" if disabled else border

        return ft.Container(
            height=46,
            border_radius=15,
            bgcolor=safe_bg,
            border=ft.border.all(1.4, safe_border),
            padding=ft.padding.symmetric(horizontal=10),
            alignment=ft.Alignment(0, 0),
            opacity=0.62 if disabled else 1,
            on_click=None if disabled else on_click,
            content=ft.Row(
                tight=True,
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(icon, size=17, color=safe_color),
                    ft.Text(
                        label,
                        size=13,
                        color=safe_color,
                        weight=ft.FontWeight.W_700,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
            ),
        )

    def disabled_submit_hint(pending_count: int) -> ft.Control:
        return ft.Container(
            border_radius=15,
            bgcolor="#FFFFFF",
            border=ft.border.all(1.2, ORANGE_BORDER),
            padding=ft.padding.symmetric(horizontal=14, vertical=12),
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=34,
                        height=34,
                        border_radius=17,
                        bgcolor=ORANGE_SOFT,
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(ft.Icons.SEND_OUTLINED, size=18, color=ORANGE),
                    ),
                    ft.Column(
                        expand=True,
                        spacing=2,
                        controls=[
                            ft.Text(f"尚有 {pending_count} 筆未核對", size=14, color=TEXT, weight=ft.FontWeight.W_700),
                            ft.Text("所有回用料核對完成後才可送出待審核。", size=12, color=TEXT_MUTED),
                        ],
                    ),
                ],
            ),
        )

    def text_field(value: Any = None, hint: str = "", multiline: bool = False, number: bool = False) -> ft.TextField:
        kwargs = dict(
            hint_text=hint,
            hint_style=ft.TextStyle(size=14, color="#94A3B8"),
            bgcolor=INPUT_BG,
            border_color=BORDER,
            focused_border_color=BLUE,
            border_radius=12,
            text_size=14,
            height=92 if multiline else 56,
            multiline=multiline,
            min_lines=2 if multiline else 1,
            max_lines=3 if multiline else 1,
            content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
            keyboard_type=ft.KeyboardType.NUMBER if number else ft.KeyboardType.TEXT,
        )
        if hint:
            kwargs["label"] = hint
            kwargs["label_style"] = ft.TextStyle(size=14, color="#94A3B8")
        if value not in [None, ""]:
            kwargs["value"] = str(value)
        return ft.TextField(**kwargs)

    def metric_card(label: str, value: Any, color: str, icon) -> ft.Container:
        return ft.Container(
            col={"xs": 6, "md": 3},
            bgcolor="#FFFFFF",
            border_radius=16,
            border=ft.border.all(1, BORDER),
            padding=14,
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=40,
                        height=40,
                        border_radius=12,
                        bgcolor="#F8FAFC",
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(icon, size=22, color=color),
                    ),
                    ft.Column(
                        spacing=1,
                        controls=[
                            ft.Text(str(value), size=22, color=TEXT, weight=ft.FontWeight.BOLD),
                            ft.Text(label, size=12, color=TEXT_MUTED),
                        ],
                    ),
                ],
            ),
        )

    def status_badge(status: str, label: str) -> ft.Container:
        if status == "confirmed":
            bg, fg, border = GREEN_SOFT, GREEN, GREEN_BORDER
        elif status == "submitted":
            bg, fg, border = ORANGE_SOFT, ORANGE, ORANGE_BORDER
        elif status == "voided":
            bg, fg, border = RED_SOFT, RED, RED_BORDER
        else:
            bg, fg, border = BLUE_SOFT, BLUE, BLUE_BORDER

        return ft.Container(
            height=28,
            padding=ft.padding.symmetric(horizontal=10),
            border_radius=14,
            bgcolor=bg,
            border=ft.border.all(1, border),
            alignment=ft.Alignment(0, 0),
            content=ft.Text(label, size=12, color=fg, weight=ft.FontWeight.W_600),
        )

    def result_badge(status: str, label: str) -> ft.Container:
        if status == "confirmed":
            bg, fg, border = GREEN_SOFT, GREEN, GREEN_BORDER
        elif status in ["missing", "used_not_recorded", "scrap_required", "data_abnormal"]:
            if status == "data_abnormal":
                bg, fg, border = ORANGE_SOFT, ORANGE, ORANGE_BORDER
            else:
                bg, fg, border = RED_SOFT, RED, RED_BORDER
        else:
            bg, fg, border = GRAY_SOFT, TEXT_MUTED, BORDER

        return ft.Container(
            height=28,
            padding=ft.padding.symmetric(horizontal=10),
            border_radius=14,
            bgcolor=bg,
            border=ft.border.all(1, border),
            alignment=ft.Alignment(0, 0),
            content=ft.Text(label, size=12, color=fg, weight=ft.FontWeight.W_600),
        )

    def breadcrumb_item(label: str, route: str | None = None, active: bool = False) -> ft.Control:
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
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        )

    def breadcrumb_separator() -> ft.Control:
        return ft.Text(">", size=12, color=TEXT_MUTED)

    def build_breadcrumb() -> ft.Control:
        detail = state.get("detail") or {}
        count = detail.get("count") or {}
        count_no = str(count.get("count_no") or "").strip()

        controls: list[ft.Control] = [
            breadcrumb_item("原料入庫作業", route="/inventory"),
            breadcrumb_separator(),
            breadcrumb_item("人工盤點", route="/inventory/stocktake"),
            breadcrumb_separator(),
            breadcrumb_item("回用料逐筆盤點", route=None if not count_no else "/inventory/stocktake/recycled", active=not bool(count_no)),
        ]

        if count_no:
            controls.extend(
                [
                    breadcrumb_separator(),
                    breadcrumb_item(count_no, active=True),
                ]
            )

        return ft.Row(
            wrap=True,
            spacing=2,
            run_spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=controls,
        )

    def build_header() -> ft.Control:
        return ft.Container(
            content=ft.Column(
                spacing=14,
                controls=[
                    build_breadcrumb(),
                    ft.Row(
                        spacing=16,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=58,
                                height=58,
                                border_radius=18,
                                bgcolor=GREEN_SOFT,
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(ft.Icons.RECYCLING_OUTLINED, size=31, color=GREEN),
                            ),
                            ft.Column(
                                expand=True,
                                spacing=4,
                                controls=[
                                    ft.Text("回用料逐筆盤點", size=28, weight=ft.FontWeight.BOLD, color=TEXT),
                                    ft.Text(
                                        "以回用料為單位逐筆核對；可依現場實際排列從待核對清單選取，不必照系統順序尋找。",
                                        size=14,
                                        color=TEXT_MUTED,
                                        max_lines=3,
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            )
        )

    def sync_status_banner() -> ft.Control:
        if not state.get("status_visible"):
            return ft.Container(height=0)

        theme = state.get("status_theme", "blue")
        if theme == "green":
            bg, border, fg, icon = GREEN_SOFT, GREEN_BORDER, GREEN, ft.Icons.CHECK_CIRCLE_OUTLINE
        elif theme == "red":
            bg, border, fg, icon = RED_SOFT, RED_BORDER, RED, ft.Icons.ERROR_OUTLINE
        elif theme == "orange":
            bg, border, fg, icon = ORANGE_SOFT, ORANGE_BORDER, ORANGE, ft.Icons.INFO_OUTLINE
        else:
            bg, border, fg, icon = BLUE_SOFT, BLUE_BORDER, BLUE, ft.Icons.SYNC

        lead = ft.ProgressRing(width=15, height=15, stroke_width=2, color=fg) if state.get("loading") else ft.Icon(icon, size=17, color=fg)

        return ft.Container(
            height=38,
            padding=ft.padding.symmetric(horizontal=14),
            border_radius=19,
            bgcolor=bg,
            border=ft.border.all(1, border),
            alignment=ft.Alignment(-1, 0),
            content=ft.Row(
                tight=True,
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    lead,
                    ft.Text(str(state.get("status_message") or ""), size=13, color=fg, weight=ft.FontWeight.W_600),
                ],
            ),
        )

    # =====================================================
    # 資料整理
    # =====================================================
    def recalc_recycled_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(items)
        checked = 0
        abnormal = 0
        status_counts = {
            "unchecked": 0,
            "confirmed": 0,
            "missing": 0,
            "used_not_recorded": 0,
            "scrap_required": 0,
            "data_abnormal": 0,
        }

        for item in items:
            status = str(item.get("check_status") or "unchecked")
            if status not in status_counts:
                status = "unchecked"
            status_counts[status] += 1
            if status != "unchecked":
                checked += 1
            if status in ["missing", "used_not_recorded", "scrap_required", "data_abnormal"]:
                abnormal += 1

        return {
            "total_items": total,
            "checked_items": checked,
            "unchecked_items": max(0, total - checked),
            "entered_items": checked,
            "not_entered_items": max(0, total - checked),
            "difference_items": abnormal,
            "abnormal_items": abnormal,
            "status_counts": status_counts,
        }

    def split_recycled_items() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        detail = state.get("detail") or {}
        items = list(detail.get("recycled_items") or [])
        pending = [item for item in items if not bool(item.get("has_checked"))]
        checked = [item for item in items if bool(item.get("has_checked"))]

        def checked_key(item: dict[str, Any]) -> str:
            raw = item.get("raw") or {}
            return str(raw.get("checked_at") or item.get("checked_at") or "")

        checked.sort(key=checked_key, reverse=True)
        return pending, checked

    def get_selected_pending_item(pending_items: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not pending_items:
            return None

        selected_id = str(state.get("selected_recycled_item_id") or "")
        if selected_id:
            for item in pending_items:
                if str(item.get("id") or "") == selected_id:
                    return item

        return pending_items[0]

    def select_recycled_item(item_id: str) -> None:
        """
        r8：改為 debounced rebuild。

        快速連點時取消舊的排程 Timer，只執行最後一次 rebuild，
        避免每次點選都在 UI 事件 thread 上同步重建整頁清單。
        同時更新 _item_note_field.value，讓備註欄顯示選取項目的既有備註。
        """
        if state.get("busy"):
            return

        state["selected_recycled_item_id"] = str(item_id or "").strip()

        # 更新 view-level note_field 的值，選取不同項目時自動帶入既有備註
        pending_items, _ = split_recycled_items()
        selected = get_selected_pending_item(pending_items)
        _item_note_field.value = str((selected or {}).get("note") or "")

        # 取消尚未執行的舊 Timer（debounce）
        old_timer = _debounce_timer[0]
        if old_timer is not None and old_timer.is_alive():
            old_timer.cancel()

        # 排程 80ms 後執行 rebuild（單次，不會與其他 page.update 重疊）
        t = threading.Timer(0.08, rebuild)
        _debounce_timer[0] = t
        t.start()

    def replace_recycled_item_in_state(updated_item: dict[str, Any]) -> None:
        if not updated_item:
            return

        detail = state.get("detail") or {}
        items = list(detail.get("recycled_items") or [])
        updated_id = str(updated_item.get("id") or "")
        if not updated_id:
            return

        replaced = False
        for index, current in enumerate(items):
            if str(current.get("id") or "") == updated_id:
                items[index] = updated_item
                replaced = True
                break

        if not replaced:
            items.append(updated_item)

        detail["recycled_items"] = items
        detail["summary"] = recalc_recycled_summary(items)
        state["detail"] = detail

    # =====================================================
    # 資料載入與操作
    # =====================================================
    def load_recycled_counts_background(show_loading: bool = True) -> None:
        """
        r8：移除 show_loading 階段的 immediate rebuild()。

        舊版在 show_loading=True 時會先 rebuild() 一次顯示 loading 狀態，
        接著 worker 完成後再 rebuild() 一次，造成雙重 page.update()。
        r8 改為只在 worker 完成後統一 rebuild() 一次；
        loading 狀態由初始化時顯示的 placeholder 承擔視覺回饋。
        """
        if show_loading:
            state["loading"] = True
            set_status("正在讀取回用料盤點單", "blue", True)
            # 不在這裡呼叫 rebuild()

        def worker():
            try:
                result = load_inventory_counts(limit=80)
                if not is_active_view():
                    return

                if result.ok:
                    rows = (result.data or {}).get("counts", []) or []
                    state["counts"] = [row for row in rows if str(row.get("count_type") or "") == "recycled"]
                    state["loading"] = False
                    set_status("回用料盤點單已同步", "green", True)
                else:
                    state["counts"] = []
                    state["loading"] = False
                    set_status(result.message, "red", True)

                rebuild()  # worker 完成後統一呼叫一次
            except Exception as ex:
                if not is_active_view():
                    return
                state["counts"] = []
                state["loading"] = False
                set_status(f"讀取回用料盤點單失敗：{ex}", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def load_detail_background(count_id: str, show_loading: bool = True) -> None:
        """
        r8：同樣移除 show_loading 階段的 immediate rebuild()。
        """
        count_id = str(count_id or "").strip()
        if not count_id:
            state["detail"] = None
            state["active_count_id"] = ""
            load_recycled_counts_background(show_loading=True)
            return

        state["active_count_id"] = count_id
        remember_count_id(count_id)

        if show_loading:
            state["loading"] = True
            set_status("正在讀取回用料盤點明細", "blue", True)
            # 不在這裡呼叫 rebuild()

        def worker():
            try:
                result = load_inventory_count_detail(count_id)
                if not is_active_view():
                    return

                if not result.ok:
                    state["detail"] = None
                    state["loading"] = False
                    set_status(result.message, "red", True)
                    rebuild()
                    return

                data = result.data or {}
                count = data.get("count") or {}
                if str(count.get("count_type") or "") != "recycled":
                    state["detail"] = None
                    state["loading"] = False
                    set_status("此盤點單不是回用料盤點單。", "red", True)
                    rebuild()
                    return

                state["detail"] = data
                state["loading"] = False
                set_status("回用料盤點明細已同步", "green", True)
                rebuild()  # worker 完成後統一呼叫一次

            except Exception as ex:
                if not is_active_view():
                    return
                state["detail"] = None
                state["loading"] = False
                set_status(f"讀取回用料明細失敗：{ex}", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    create_note_field = text_field(hint="例如：月盤、臨時盤點、回用料複查", multiline=True)
    void_reason_field = text_field(hint="請輸入作廢原因", multiline=True)

    def create_recycled_count_action(e=None) -> None:
        if state.get("busy"):
            return

        state["busy"] = True
        set_status("正在建立回用料盤點單", "blue", True)
        rebuild()

        def worker():
            try:
                result = create_new_inventory_count(
                    count_date=today_text(),
                    count_type="recycled",
                    count_mode="normal",
                    note=str(create_note_field.value or ""),
                    created_by_user_id=current_user_id(),
                    created_by_name=current_user_name(),
                )
                if not is_active_view():
                    state["busy"] = False
                    return

                state["busy"] = False

                if not result.ok:
                    set_status(result.message, "red", True)
                    rebuild()
                    return

                count = (result.data or {}).get("count") or {}
                count_id = str(count.get("id") or "")
                state["show_create_form"] = False
                create_note_field.value = ""

                if not count_id:
                    # count_id 取不到時退回列表並提示
                    set_status("盤點單已建立，但無法取得 ID，請重新整理。", "orange", True)
                    rebuild()
                    return

                # r9：不從 worker thread 呼叫 navigate()，
                # 改為直接把新盤點單的 detail 載入 state 再 rebuild()。
                # 網址列不會帶 ?count_id=，但畫面會直接進入新盤點單明細。
                # 等 r9 互動穩定後若需要補網址，再於 main.py 安全地處理路由。
                remember_count_id(count_id)
                state["active_count_id"] = count_id

                detail_result = load_inventory_count_detail(count_id)
                if not is_active_view():
                    return

                if detail_result.ok:
                    state["detail"] = detail_result.data or {}
                    set_status(f"回用料盤點單已建立，請開始逐筆核對。", "green", True)
                else:
                    # detail 讀取失敗時仍把 create result 的資料填入，讓使用者看到盤點單
                    state["detail"] = result.data or {}
                    set_status(f"盤點單已建立，但明細讀取失敗：{detail_result.message}", "orange", True)

                rebuild()

            except Exception as ex:
                state["busy"] = False
                if not is_active_view():
                    return
                set_status(f"建立回用料盤點單失敗：{ex}", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def save_current_item_action(item: dict[str, Any], check_status: str = "confirmed") -> None:
        """
        r8：note_field 改為使用 view-level 的 _item_note_field，
        不再從 build 函式傳入，避免每次 rebuild 後 reference 失效。
        """
        item_id = str(item.get("id") or "")
        if not item_id:
            set_status("找不到回用料盤點明細。", "red", True)
            rebuild()
            return

        saving_ids = state.setdefault("saving_recycled_item_ids", set())
        if item_id in saving_ids:
            return

        selected_status = str(check_status or "confirmed")
        if selected_status not in STATUS_LABELS:
            selected_status = "confirmed"

        # 在發出網路請求前先讀取備註欄位的當前值（view-level field 不受 rebuild 影響）
        note_value = str(_item_note_field.value or "")

        status_label = STATUS_LABELS.get(selected_status, "核對結果")
        recycled_no = str(item.get("recycled_no") or "-")

        saving_ids.add(item_id)
        set_status(f"正在儲存：{status_label}", "blue", True)
        state["last_action_message"] = f"已送出：{recycled_no}｜{status_label}，正在儲存..."
        state["last_action_theme"] = "blue"

        # r10：立即給操作員底部回饋，不等待整頁 rebuild。
        # 使用者盤點時通常已滑到頁面中段，看不到最上方同步膠囊。
        show_snack(f"已送出：{status_label}，正在儲存...", success=True)

        def worker():
            try:
                result = update_count_recycled_item_check(
                    item_id=item_id,
                    check_status=selected_status,
                    actual_weight_kg="",
                    actual_supplier="",
                    actual_status="",
                    note=note_value,
                    checked_by_user_id=current_user_id(),
                    checked_by_name=current_user_name(),
                )

                saving_ids.discard(item_id)

                if not is_active_view():
                    return

                if not result.ok:
                    set_status(result.message, "red", True)
                    state["last_action_message"] = result.message
                    state["last_action_theme"] = "red"
                    rebuild()
                    return

                updated_item = (result.data or {}).get("item") or {}
                replace_recycled_item_in_state(updated_item)

                # 儲存成功後清除選取與備註欄位
                if str(state.get("selected_recycled_item_id") or "") == item_id:
                    state["selected_recycled_item_id"] = ""
                    _item_note_field.value = ""

                state["last_action_message"] = f"剛剛已儲存：{updated_item.get('recycled_no') or recycled_no}｜{status_label}，已移到最近已核對清單。"
                state["last_action_theme"] = "green"
                set_status(f"已儲存：{status_label}", "green", True)
                rebuild()

            except Exception as ex:
                saving_ids.discard(item_id)
                if not is_active_view():
                    return
                state["last_action_message"] = f"回用料核對失敗：{ex}"
                state["last_action_theme"] = "red"
                set_status(f"回用料核對失敗：{ex}", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def toggle_void_form(e=None) -> None:
        if state.get("busy"):
            return
        state["show_void_form"] = not bool(state.get("show_void_form"))
        rebuild()

    def close_void_form(e=None) -> None:
        state["show_void_form"] = False
        try:
            void_reason_field.value = ""
        except Exception:
            pass
        rebuild()

    def void_recycled_count_action(e=None) -> None:
        if not is_super_admin():
            state["last_action_message"] = "只有超級管理員可以作廢盤點單。"
            state["last_action_theme"] = "red"
            set_status("只有超級管理員可以作廢盤點單。", "red", True)
            rebuild()
            return

        reason = str(void_reason_field.value or "").strip()
        if not reason:
            state["last_action_message"] = "請輸入作廢原因。"
            state["last_action_theme"] = "red"
            set_status("請輸入作廢原因。", "red", True)
            rebuild()
            return

        detail = state.get("detail") or {}
        count = detail.get("count") or {}
        count_id = str(count.get("id") or "")
        if not count_id or state.get("busy"):
            return

        state["busy"] = True
        set_status("正在作廢回用料盤點單", "blue", True)
        state["last_action_message"] = "正在作廢回用料盤點單..."
        state["last_action_theme"] = "blue"
        rebuild()

        def worker():
            try:
                result = void_inventory_count(
                    count_id=count_id,
                    void_reason=reason,
                    voided_by_user_id=current_user_id(),
                    voided_by_name=current_user_name(),
                )

                if not is_active_view():
                    state["busy"] = False
                    return

                state["busy"] = False

                if not result.ok:
                    state["last_action_message"] = result.message
                    state["last_action_theme"] = "red"
                    set_status(result.message, "red", True)
                    rebuild()
                    return

                void_reason_field.value = ""
                state["show_void_form"] = False
                state["selected_recycled_item_id"] = ""
                try:
                    _item_note_field.value = ""
                except Exception:
                    pass

                detail_result = load_inventory_count_detail(count_id)
                if detail_result.ok:
                    state["detail"] = detail_result.data or {}
                else:
                    # 作廢已成功，但明細重讀失敗時至少更新目前 count 狀態，避免畫面誤導。
                    updated_count = (result.data or {}).get("count") or {}
                    if updated_count:
                        current_detail = state.get("detail") or {}
                        current_detail["count"] = updated_count
                        state["detail"] = current_detail

                state["last_action_message"] = result.message or "回用料盤點單已作廢。"
                state["last_action_theme"] = "green"
                set_status(result.message or "回用料盤點單已作廢。", "green", True)
                rebuild()

            except Exception as ex:
                state["busy"] = False
                if not is_active_view():
                    return
                state["last_action_message"] = f"作廢回用料盤點單失敗：{ex}"
                state["last_action_theme"] = "red"
                set_status(f"作廢回用料盤點單失敗：{ex}", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def submit_recycled_count_action(e=None) -> None:
        detail = state.get("detail") or {}
        count = detail.get("count") or {}
        count_id = str(count.get("id") or "")
        if not count_id or state.get("busy"):
            return

        state["busy"] = True
        set_status("正在送出回用料盤點單", "blue", True)
        rebuild()

        def worker():
            try:
                result = submit_inventory_count(
                    count_id=count_id,
                    submitted_by_user_id=current_user_id(),
                    submitted_by_name=current_user_name(),
                )

                if not is_active_view():
                    state["busy"] = False
                    return

                state["busy"] = False

                if not result.ok:
                    set_status(result.message, "red", True)
                    rebuild()
                    return

                detail_result = load_inventory_count_detail(count_id)
                if detail_result.ok:
                    state["detail"] = detail_result.data or {}
                set_status(result.message, "green", True)
                rebuild()

            except Exception as ex:
                state["busy"] = False
                if not is_active_view():
                    return
                set_status(f"送出回用料盤點單失敗：{ex}", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def confirm_recycled_count_action(e=None) -> None:
        if not is_super_admin():
            set_status("只有超級管理員可以確認盤點。", "red", True)
            rebuild()
            return

        detail = state.get("detail") or {}
        count = detail.get("count") or {}
        count_id = str(count.get("id") or "")
        if not count_id or state.get("busy"):
            return

        state["busy"] = True
        set_status("正在確認回用料盤點單", "blue", True)
        rebuild()

        def worker():
            try:
                result = confirm_inventory_count(
                    count_id=count_id,
                    confirmed_by_user_id=current_user_id(),
                    confirmed_by_name=current_user_name(),
                )

                if not is_active_view():
                    state["busy"] = False
                    return

                state["busy"] = False

                if not result.ok:
                    set_status(result.message, "red", True)
                    rebuild()
                    return

                detail_result = load_inventory_count_detail(count_id)
                if detail_result.ok:
                    state["detail"] = detail_result.data or {}
                set_status(result.message, "green", True)
                rebuild()

            except Exception as ex:
                state["busy"] = False
                if not is_active_view():
                    return
                set_status(f"確認回用料盤點單失敗：{ex}", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    # =====================================================
    # 畫面區塊
    # =====================================================
    def build_action_feedback_card() -> ft.Control:
        """r10：顯示最近一次單筆核對結果，放在操作區附近，不依賴最上方同步膠囊。"""
        message = str(state.get("last_action_message") or "").strip()
        if not message:
            return ft.Container(height=0)

        theme = str(state.get("last_action_theme") or "green")
        if theme == "red":
            bg, fg, border, icon = RED_SOFT, RED, RED_BORDER, ft.Icons.ERROR_OUTLINE
        elif theme == "orange":
            bg, fg, border, icon = ORANGE_SOFT, ORANGE, ORANGE_BORDER, ft.Icons.INFO_OUTLINE
        elif theme == "blue":
            bg, fg, border, icon = BLUE_SOFT, BLUE, BLUE_BORDER, ft.Icons.SYNC
        else:
            bg, fg, border, icon = GREEN_SOFT, GREEN, GREEN_BORDER, ft.Icons.CHECK_CIRCLE_OUTLINE

        return ft.Container(
            bgcolor=bg,
            border=ft.border.all(1, border),
            border_radius=14,
            padding=12,
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(icon, size=20, color=fg),
                    ft.Text(message, size=13, color=fg, weight=ft.FontWeight.W_700, expand=True),
                ],
            ),
        )

    def build_summary_cards(summary: dict[str, Any]) -> ft.Control:
        return ft.ResponsiveRow(
            columns=12,
            spacing=12,
            run_spacing=12,
            controls=[
                metric_card("總筆數", summary.get("total_items", 0), BLUE, ft.Icons.RECYCLING_OUTLINED),
                metric_card("已核對", summary.get("checked_items", 0), GREEN, ft.Icons.CHECK_CIRCLE_OUTLINE),
                metric_card("異常", summary.get("abnormal_items", 0), ORANGE, ft.Icons.REPORT_PROBLEM_OUTLINED),
                metric_card("未核對", summary.get("unchecked_items", 0), RED, ft.Icons.ERROR_OUTLINE),
            ],
        )

    def build_result_action_buttons(item: dict[str, Any], saving: bool) -> ft.Control:
        """
        r8：on_click 改為直接呼叫 save_current_item_action(item, status_value)，
        不再傳入 note_field 參數（已改為 view-level _item_note_field）。
        """
        controls: list[ft.Control] = []
        for value, label, color, soft, border, icon in STATUS_OPTIONS:
            controls.append(
                ft.Container(
                    col={"xs": 6, "md": 4},
                    content=result_action_button(
                        label=label,
                        icon=icon,
                        color=color,
                        soft=soft,
                        border=border,
                        on_click=lambda e, it=item, sv=value: save_current_item_action(it, sv),
                        disabled=saving,
                    ),
                )
            )

        return ft.ResponsiveRow(
            columns=12,
            spacing=8,
            run_spacing=8,
            controls=controls,
        )

    def build_pending_item_row(self_item: dict[str, Any], selected: bool = False) -> ft.Control:
        border_color = GREEN if selected else BORDER
        bg_color = GREEN_SOFT if selected else "#FFFFFF"

        return ft.Container(
            bgcolor=bg_color,
            border=ft.border.all(1.2, border_color),
            border_radius=14,
            padding=12,
            ink=True,
            on_click=lambda e, item_id=str(self_item.get("id") or ""): select_recycled_item(item_id),
            content=ft.ResponsiveRow(
                columns=12,
                spacing=8,
                run_spacing=5,
                controls=[
                    ft.Container(
                        col={"xs": 12, "md": 3},
                        content=ft.Text(self_item.get("recycled_no") or "-", size=15, color=TEXT, weight=ft.FontWeight.BOLD),
                    ),
                    ft.Container(
                        col={"xs": 6, "md": 3},
                        content=ft.Text(to_text(self_item.get("material_type")), size=13, color=TEXT_MUTED),
                    ),
                    ft.Container(
                        col={"xs": 6, "md": 3},
                        content=ft.Text(fmt_num(self_item.get("weight_kg"), " KG"), size=13, color=TEXT_MUTED),
                    ),
                    ft.Container(
                        col={"xs": 12, "md": 3},
                        content=ft.Row(
                            tight=True,
                            spacing=6,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Icon(ft.Icons.CHECK_CIRCLE if selected else ft.Icons.RADIO_BUTTON_UNCHECKED, size=16, color=GREEN if selected else TEXT_MUTED),
                                ft.Text(
                                    "目前選取" if selected else to_text(self_item.get("supplier")),
                                    size=13,
                                    color=GREEN if selected else TEXT_MUTED,
                                    weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_500,
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        )

    def build_pending_item_list(pending_items: list[dict[str, Any]], selected_item_id: str) -> ft.Control:
        rows: list[ft.Control] = []
        for item in pending_items:
            rows.append(build_pending_item_row(item, selected=str(item.get("id") or "") == selected_item_id))

        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.border.all(1, BORDER),
            border_radius=18,
            padding=16,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.FORMAT_LIST_BULLETED, size=23, color=GREEN),
                            ft.Column(
                                expand=True,
                                spacing=2,
                                controls=[
                                    ft.Text(f"待核對回用料清單：{len(pending_items)} 筆", size=17, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ft.Text("請依現場實際看到的回用料編號點選，不必照系統順序盤點。", size=12, color=TEXT_MUTED),
                                ],
                            ),
                        ],
                    ),
                    ft.Container(
                        height=310,
                        bgcolor="#F8FAFC",
                        border_radius=14,
                        padding=10,
                        content=ft.Column(
                            spacing=8,
                            scroll=ft.ScrollMode.AUTO,
                            controls=rows,
                        ),
                    ),
                ],
            ),
        )

    def build_current_item_card(item: dict[str, Any], total_pending: int, total_all: int) -> ft.Control:
        """
        r8：不再在此函式內建立 note_field；改用 view-level 的 _item_note_field。
        saving 狀態依 saving_recycled_item_ids 判斷，結果按鈕 on_click 不再傳入 note_field。
        """
        saving_ids = state.get("saving_recycled_item_ids") or set()
        saving_current = str(item.get("id") or "") in saving_ids

        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.border.all(1.2, GREEN_BORDER),
            border_radius=22,
            padding=18,
            content=ft.Column(
                spacing=16,
                controls=[
                    ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=52,
                                height=52,
                                border_radius=16,
                                bgcolor=GREEN_SOFT,
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(ft.Icons.RECYCLING_OUTLINED, color=GREEN, size=28),
                            ),
                            ft.Column(
                                expand=True,
                                spacing=3,
                                controls=[
                                    ft.Text(f"目前選取回用料｜待核對 {total_pending} / {total_all} 筆", size=13, color=GREEN, weight=ft.FontWeight.W_700),
                                    ft.Text(item.get("recycled_no") or "-", size=22, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ft.Text(
                                        f"{item.get('material_type') or '-'}｜{item.get('supplier') or '-'}｜{fmt_num(item.get('weight_kg'), ' KG')}",
                                        size=13,
                                        color=TEXT_MUTED,
                                        max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                ],
                            ),
                            result_badge(item.get("check_status") or "unchecked", item.get("check_status_label") or "未核對"),
                        ],
                    ),
                    ft.Container(
                        bgcolor="#F8FAFC",
                        border_radius=14,
                        padding=14,
                        content=ft.ResponsiveRow(
                            columns=12,
                            spacing=10,
                            run_spacing=10,
                            controls=[
                                ft.Container(
                                    col={"xs": 6, "md": 3},
                                    content=ft.Column(
                                        spacing=2,
                                        controls=[
                                            ft.Text("重量", size=12, color=TEXT_MUTED),
                                            ft.Text(fmt_num(item.get("weight_kg"), " KG"), size=16, color=TEXT, weight=ft.FontWeight.BOLD),
                                        ],
                                    ),
                                ),
                                ft.Container(
                                    col={"xs": 6, "md": 3},
                                    content=ft.Column(
                                        spacing=2,
                                        controls=[
                                            ft.Text("供應商", size=12, color=TEXT_MUTED),
                                            ft.Text(to_text(item.get("supplier")), size=16, color=TEXT, weight=ft.FontWeight.BOLD),
                                        ],
                                    ),
                                ),
                                ft.Container(
                                    col={"xs": 12, "md": 6},
                                    content=ft.Column(
                                        spacing=2,
                                        controls=[
                                            ft.Text("目前狀態", size=12, color=TEXT_MUTED),
                                            ft.Text(to_text(item.get("usage_status")), size=16, color=TEXT, weight=ft.FontWeight.BOLD),
                                        ],
                                    ),
                                ),
                            ],
                        ),
                    ),
                    ft.Column(
                        spacing=8,
                        controls=[
                            ft.Text("盤點結果", size=13, color=TEXT, weight=ft.FontWeight.W_700),
                            ft.Text("點選結果後會直接儲存此筆；若是異常、找不到實物或需報廢，建議先填寫備註。", size=12, color=TEXT_MUTED),
                            build_result_action_buttons(item, saving_current),
                        ],
                    ),
                    build_action_feedback_card(),
                    # r8：使用 view-level _item_note_field，不在此重建 TextField
                    _item_note_field,
                    ft.Text(
                        "儲存成功後此筆會從待核對清單消失；請再從清單選擇現場正在盤點的下一包。",
                        size=12,
                        color=TEXT_MUTED,
                    ),
                ],
            ),
        )

    def build_recent_checked_rows(checked_items: list[dict[str, Any]], total_all: int) -> ft.Control:
        recent = checked_items[:5]
        rows: list[ft.Control] = [
            ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.DONE_ALL_OUTLINED, size=23, color=GREEN),
                    ft.Column(
                        expand=True,
                        spacing=2,
                        controls=[
                            ft.Text(f"最近已核對：{len(checked_items)} / {total_all} 筆", size=17, color=TEXT, weight=ft.FontWeight.BOLD),
                            ft.Text("只顯示最近 5 筆摘要，避免大量已核對項目造成畫面卡頓。", size=12, color=TEXT_MUTED),
                        ],
                    ),
                ],
            )
        ]

        if not recent:
            rows.append(
                ft.Container(
                    bgcolor="#F8FAFC",
                    border_radius=12,
                    padding=12,
                    content=ft.Text("尚無已核對回用料。", size=13, color=TEXT_MUTED),
                )
            )
        else:
            for item in recent:
                status = str(item.get("check_status") or "unchecked")
                rows.append(
                    ft.Container(
                        bgcolor="#F8FAFC",
                        border_radius=12,
                        padding=12,
                        content=ft.ResponsiveRow(
                            columns=12,
                            spacing=8,
                            run_spacing=4,
                            controls=[
                                ft.Container(
                                    col={"xs": 12, "md": 3},
                                    content=ft.Text(item.get("recycled_no") or "-", size=14, color=TEXT, weight=ft.FontWeight.BOLD),
                                ),
                                ft.Container(
                                    col={"xs": 6, "md": 3},
                                    content=result_badge(status, item.get("check_status_label") or "-"),
                                ),
                                ft.Container(
                                    col={"xs": 6, "md": 3},
                                    content=ft.Text(fmt_num(item.get("weight_kg"), " KG"), size=13, color=TEXT_MUTED),
                                ),
                                ft.Container(
                                    col={"xs": 12, "md": 3},
                                    content=ft.Text(to_text(item.get("supplier")), size=13, color=TEXT_MUTED),
                                ),
                            ],
                        ),
                    )
                )

        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.border.all(1, BORDER),
            border_radius=18,
            padding=16,
            content=ft.Column(spacing=12, controls=rows),
        )

    def build_counts_list() -> ft.Control:
        counts = state.get("counts") or []

        controls: list[ft.Control] = [
            ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    section_title("回用料盤點單", "選擇一張草稿盤點單繼續逐筆核對，或新增一張回用料盤點單。"),
                ],
            ),
            ft.ResponsiveRow(
                columns=12,
                spacing=10,
                run_spacing=10,
                controls=[
                    ft.Container(
                        col={"xs": 12, "md": 6},
                        content=native_button("新增回用料盤點單", ft.Icons.ADD, GREEN_BTN, on_click=lambda e: open_create_form(), expand=True, disabled=state.get("busy")),
                    ),
                ],
            ),
            build_create_form(),
        ]

        if state.get("loading"):
            controls.append(
                ft.Container(
                    bgcolor="#FFFFFF",
                    border=ft.border.all(1, BORDER),
                    border_radius=16,
                    padding=18,
                    content=ft.Row(
                        spacing=10,
                        controls=[
                            ft.ProgressRing(width=18, height=18, stroke_width=2, color=GREEN),
                            ft.Text("正在讀取回用料盤點單...", size=14, color=TEXT_MUTED),
                        ],
                    ),
                )
            )
        elif not counts:
            controls.append(
                ft.Container(
                    bgcolor="#FFFFFF",
                    border=ft.border.all(1, BORDER),
                    border_radius=16,
                    padding=18,
                    content=ft.Text("目前尚無回用料盤點單。", size=14, color=TEXT_MUTED),
                )
            )
        else:
            for count in counts:
                count_id = str(count.get("id") or "")
                controls.append(
                    ft.Container(
                        bgcolor="#FFFFFF",
                        border=ft.border.all(1, BORDER),
                        border_radius=18,
                        padding=16,
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
                                            bgcolor=GREEN_SOFT,
                                            alignment=ft.Alignment(0, 0),
                                            content=ft.Icon(ft.Icons.RECYCLING_OUTLINED, color=GREEN, size=25),
                                        ),
                                        ft.Column(
                                            expand=True,
                                            spacing=3,
                                            controls=[
                                                ft.Text(count.get("count_no") or "-", size=17, weight=ft.FontWeight.BOLD, color=TEXT),
                                                ft.Text(
                                                    f"{count.get('count_date') or '-'}｜建立人：{count.get('created_by_name') or '-'}",
                                                    size=13,
                                                    color=TEXT_MUTED,
                                                ),
                                            ],
                                        ),
                                        status_badge(count.get("status"), count.get("status_label") or "-"),
                                    ],
                                ),
                                build_count_list_action(count),
                            ],
                        ),
                    )
                )

        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.border.all(1, BORDER),
            border_radius=20,
            padding=18,
            content=ft.Column(spacing=14, controls=controls),
        )

    def open_create_form():
        state["show_create_form"] = True
        rebuild()

    def close_create_form(e=None):
        state["show_create_form"] = False
        rebuild()

    def build_create_form() -> ft.Control:
        if not state.get("show_create_form"):
            return ft.Container(height=0)

        return ft.Container(
            bgcolor=GREEN_SOFT,
            border=ft.border.all(1, GREEN_BORDER),
            border_radius=16,
            padding=14,
            content=ft.Column(
                spacing=12,
                controls=[
                    section_title("新增回用料盤點單", f"盤點日期會使用今日：{today_text()}"),
                    create_note_field,
                    ft.Row(
                        spacing=10,
                        controls=[
                            native_outline_button("取消", ft.Icons.CLOSE, TEXT_MUTED, on_click=close_create_form, expand=True, disabled=state.get("busy")),
                            native_button("建立", ft.Icons.SAVE_OUTLINED, GREEN_BTN, on_click=create_recycled_count_action, expand=True, disabled=state.get("busy")),
                        ],
                    ),
                ],
            ),
        )

    def build_void_section() -> ft.Control:
        """r11：回用料盤點單作廢區塊。僅超級管理員、草稿 / 待審核可見。"""
        if state.get("show_void_form"):
            return ft.Container(
                bgcolor=RED_SOFT,
                border=ft.border.all(1, RED_BORDER),
                border_radius=16,
                padding=14,
                content=ft.Column(
                    spacing=12,
                    controls=[
                        ft.Row(
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=RED, size=22),
                                ft.Column(
                                    expand=True,
                                    spacing=2,
                                    controls=[
                                        ft.Text("危險操作：作廢回用料盤點單", size=16, color=RED, weight=ft.FontWeight.BOLD),
                                        ft.Text("作廢後不會修改回用料狀態，但會保留稽核紀錄；請務必填寫原因。", size=12, color=TEXT_MUTED),
                                    ],
                                ),
                            ],
                        ),
                        void_reason_field,
                        ft.Row(
                            spacing=10,
                            controls=[
                                native_outline_button(
                                    "取消作廢",
                                    ft.Icons.CLOSE,
                                    TEXT_MUTED,
                                    on_click=close_void_form,
                                    expand=True,
                                    disabled=state.get("busy"),
                                ),
                                native_button(
                                    "確認作廢",
                                    ft.Icons.BLOCK,
                                    RED_BTN,
                                    on_click=void_recycled_count_action,
                                    expand=True,
                                    disabled=state.get("busy"),
                                ),
                            ],
                        ),
                    ],
                ),
            )

        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.border.all(1, RED_BORDER),
            border_radius=16,
            padding=14,
            content=ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=42,
                        height=42,
                        border_radius=13,
                        bgcolor=RED_SOFT,
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=RED, size=22),
                    ),
                    ft.Column(
                        expand=True,
                        spacing=2,
                        controls=[
                            ft.Text("危險操作", size=15, color=TEXT, weight=ft.FontWeight.BOLD),
                            ft.Text("需要取消本張草稿或待審核回用料盤點單時，請從這裡作廢。", size=12, color=TEXT_MUTED),
                        ],
                    ),
                    native_outline_button(
                        "作廢盤點單",
                        ft.Icons.BLOCK,
                        RED,
                        on_click=toggle_void_form,
                        disabled=state.get("busy"),
                    ),
                ],
            ),
        )

    def build_detail_panel() -> ft.Control:
        detail = state.get("detail")

        # loading 中且沒有 detail 時顯示 loading placeholder
        if not detail and state.get("loading"):
            return ft.Container(
                bgcolor="#FFFFFF",
                border=ft.border.all(1, BORDER),
                border_radius=20,
                padding=24,
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=14,
                    controls=[
                        ft.ProgressRing(width=32, height=32, stroke_width=3, color=GREEN),
                        ft.Text(str(state.get("status_message") or "讀取中..."), size=14, color=TEXT_MUTED),
                    ],
                ),
            )

        if not detail:
            return build_counts_list()

        count = detail.get("count") or {}
        summary = detail.get("summary") or {}
        status = str(count.get("status") or "draft")
        pending_items, checked_items = split_recycled_items()
        total_all = int(summary.get("total_items") or len(pending_items) + len(checked_items))
        can_edit = status == "draft"
        can_submit = can_edit and not pending_items and total_all > 0
        can_confirm = status == "submitted" and is_super_admin()
        can_void = status in ["draft", "submitted"] and is_super_admin()

        controls: list[ft.Control] = [
            ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        expand=True,
                        spacing=3,
                        controls=[
                            ft.Text(f"盤點單：{count.get('count_no') or '-'}", size=21, color=TEXT, weight=ft.FontWeight.BOLD),
                            ft.Text(f"{count.get('count_date') or '-'}｜建立人：{count.get('created_by_name') or '-'}", size=13, color=TEXT_MUTED),
                        ],
                    ),
                    status_badge(status, count.get("status_label") or "-"),
                ],
            ),
            build_summary_cards(summary),
        ]

        if status == "submitted":
            controls.append(
                ft.Container(
                    bgcolor=ORANGE_SOFT,
                    border=ft.border.all(1, ORANGE_BORDER),
                    border_radius=14,
                    padding=14,
                    content=ft.Text("此回用料盤點單已送出待審核。第一版確認後只保留紀錄，不自動修改回用料狀態。", size=13, color="#9A4A12"),
                )
            )

        if status == "confirmed":
            controls.append(
                ft.Container(
                    bgcolor=GREEN_SOFT,
                    border=ft.border.all(1, GREEN_BORDER),
                    border_radius=14,
                    padding=14,
                    content=ft.Text("此回用料盤點單已確認。第一版只保留盤點紀錄，不自動修改回用料狀態。", size=13, color=GREEN, weight=ft.FontWeight.W_600),
                )
            )

        if status == "voided":
            controls.append(
                ft.Container(
                    bgcolor=RED_SOFT,
                    border=ft.border.all(1, RED_BORDER),
                    border_radius=14,
                    padding=14,
                    content=ft.Text(
                        f"此回用料盤點單已作廢。原因：{count.get('void_reason') or '-'}",
                        size=13,
                        color=RED,
                        weight=ft.FontWeight.W_600,
                    ),
                )
            )

        controls.append(
            ft.ResponsiveRow(
                columns=12,
                spacing=10,
                run_spacing=10,
                controls=[
                    ft.Container(
                        col={"xs": 12, "md": 6},
                        content=native_outline_button("回用料盤點單列表", ft.Icons.LIST_ALT, GREEN, on_click=lambda e: guarded_navigate("/inventory/stocktake/recycled", "正在返回回用料盤點單列表..."), expand=True, disabled=state.get("busy") or state.get("navigation_busy")),
                    ),
                ],
            )
        )

        if can_edit:
            if pending_items:
                selected_item = get_selected_pending_item(pending_items)
                selected_item_id = str((selected_item or {}).get("id") or "")
                controls.append(build_pending_item_list(pending_items, selected_item_id))
                if selected_item:
                    controls.append(
                        build_current_item_card(
                            selected_item,
                            total_pending=len(pending_items),
                            total_all=total_all,
                        )
                    )
            else:
                controls.append(
                    ft.Container(
                        bgcolor=GREEN_SOFT,
                        border=ft.border.all(1, GREEN_BORDER),
                        border_radius=16,
                        padding=14,
                        content=ft.Row(
                            spacing=10,
                            controls=[
                                ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=GREEN, size=20),
                                ft.Text("所有回用料都已核對，可以送出待審核。", size=13, color=GREEN, weight=ft.FontWeight.W_600),
                            ],
                        ),
                    )
                )

            if can_submit:
                controls.append(
                    native_button(
                        "送出待審核",
                        ft.Icons.SEND_OUTLINED,
                        ORANGE_BTN,
                        on_click=submit_recycled_count_action,
                        disabled=state.get("busy"),
                        expand=True,
                    )
                )
            else:
                controls.append(disabled_submit_hint(len(pending_items)))

        elif status == "submitted":
            if can_confirm:
                controls.append(
                    native_button(
                        "確認回用料盤點單",
                        ft.Icons.VERIFIED_OUTLINED,
                        GREEN_BTN,
                        on_click=confirm_recycled_count_action,
                        disabled=state.get("busy"),
                        expand=True,
                    )
                )

        if can_void:
            controls.append(build_void_section())

        controls.append(build_recent_checked_rows(checked_items, total_all))

        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.border.all(1, GREEN_BORDER),
            border_radius=22,
            padding=20,
            content=ft.Column(spacing=16, controls=controls),
        )

    def build_page() -> ft.Control:
        controls: list[ft.Control] = [
            build_header(),
            sync_status_banner(),
            build_detail_panel(),
            ft.Container(height=90),
        ]

        return ft.Container(
            bgcolor=BG,
            width=float("inf"),
            expand=True,
            padding=ft.padding.only(top=18, bottom=18),
            content=ft.Column(
                spacing=16,
                controls=controls,
                expand=True,
            ),
        )

    # =====================================================
    # r8：初始化改為先顯示 loading placeholder，
    # 避免 main_host.content = build_page() 與 Timer worker 的 rebuild() 重疊。
    # =====================================================
    main_host = ft.Container(
        width=float("inf"),
        expand=True,
        alignment=ft.Alignment(0, 0),
        content=ft.Column(
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.ProgressRing(width=32, height=32, stroke_width=3, color=GREEN),
                ft.Text("回用料盤點資料同步中...", size=14, color=TEXT_MUTED),
            ],
        ),
    )

    initial_count_id = parse_count_id_from_route()
    if initial_count_id:
        try:
            threading.Timer(0.2, lambda: load_detail_background(initial_count_id, show_loading=True)).start()
        except Exception:
            load_detail_background(initial_count_id, show_loading=True)
    else:
        try:
            threading.Timer(0.2, lambda: load_recycled_counts_background(show_loading=True)).start()
        except Exception:
            load_recycled_counts_background(show_loading=True)

    return main_host
