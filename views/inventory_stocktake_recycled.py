# =====================================================
# KNH MMS v2
# File: views/inventory_stocktake_recycled.py
# File Revision: 2026-05-15-recycled-subpage-r6
# Status: recycled stocktake selectable workflow UI stability fix
# Last Updated: 2026-05-15 Asia/Taipei
#
# Purpose:
# - 回用料逐筆盤點子頁。
# - 採待核對輕量清單 + 單筆核對卡片模式，避免一次渲染大量完整卡片造成 Flet Web 卡頓。
#
# Major Changes in This Revision:
# - 新增 /inventory/stocktake/recycled 子頁內容。
# - 麵包屑路徑：原料入庫作業 > 人工盤點 > 回用料逐筆盤點 > 盤點單號。
# - 回用料採逐筆核對，不使用盲盤。
# - 待核對回用料以輕量清單呈現，操作員可依現場實際排列自行選擇要盤點的那一包。
# - 支援五種核對結果：在庫確認、找不到實物、已領用未登錄、需報廢、資料異常。
# - 單筆儲存後該筆從待核對清單消失，底部僅顯示最近已核對 5 筆極簡摘要。
# - r2 修正手機 Web 按鈕文字被裁切問題，將關鍵導覽按鈕改為可換行的 ResponsiveRow。
# - r2 修正最近已核對比例，改為 已核對 / 總筆數，例如 2 / 25 筆。
# - r3 改為「待核對輕量清單選取模式」，不再強迫依系統順序逐筆下一筆。
# - r3 移除「返回人工盤點」大按鈕，因上方麵包屑已可返回人工盤點。
# - r3 加強「回用料盤點單列表」與儲存按鈕外框，提升手機 Web 可辨識度。
# - r4 修正手機 Web 上 OutlinedButton 外框不明顯問題，改用外層 Container 強制顯示外框。
# - r4 調整單筆儲存流程，不再於送出前整頁 rebuild 與全頁 busy，避免儲存期間所有按鈕卡住。
# - r5 取消「先選 chip 再儲存」流程，改為直接點選結果膠囊即儲存，避免 chip 切換造成整頁 rebuild 卡頓。
# - r5 導覽與送審按鈕改為自製輕量膠囊按鈕，修正手機 Web 文字被遮蔽與 disabled 色塊過重問題。
# - r6 修正盤點結果區大灰框問題：結果按鈕改為固定尺寸卡片式動作列，備註欄位改為白底低高度。
# - r6 修正未核對提示色塊過重問題，改為輕量提示卡，不再像 disabled 大按鈕。
#
# Notes:
# - Flet 0.84。
# - 不使用 page.push_route()，導頁一律使用 page.go() 或 main.py 提供的 _navigate。
# - 時間與資料寫入邏輯由 services/stocktake_service.py 統一使用 Asia/Taipei。
# - 第一版不自動修改 recycled_materials 狀態，只保留盤點紀錄。
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
        "creating": False,
        "show_create_form": False,
        "selected_recycled_item_id": "",
        "saving_recycled_item_ids": set(),
    }

    ui_lock = threading.RLock()

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

    def parse_count_id_from_route() -> str:
        route = str(getattr(page, "route", "") or "")
        try:
            parsed = urlparse(route)
            query = parse_qs(parsed.query or "")
            count_id = (query.get("count_id") or [""])[0]
            if count_id:
                return str(count_id).strip()
        except Exception:
            pass
        return str(session_get("_stocktake_recycled_count_id", "") or "").strip()

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
        """
        手機 Web 專用輕量膠囊按鈕。

        Flet 0.84 的 OutlinedButton / TextButton 在 iPhone Web 上曾出現外框不明顯、
        文字被裁切或 disabled 色塊過重的問題。此子頁的回用料盤點操作改用
        Container + ink 繪製固定高度膠囊，減少原生 Button 巢狀渲染成本。
        """
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

    def result_action_button(
        label: str,
        icon,
        color: str,
        soft: str,
        border: str,
        on_click=None,
        disabled: bool = False,
    ) -> ft.Control:
        """
        r6：盤點結果用固定尺寸卡片式按鈕。

        r5 的膠囊按鈕在部分手機 Web 上出現大灰框渲染問題。
        這裡改用外層 Container 固定高度與邊框，不使用 ink ripple，降低 Flet Web
        對 Material/Ink 層的重繪負擔。
        """
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
        """尚未可送審時的提示卡。

        r5 的橘色 disabled 大按鈕在手機 Web 上容易像一塊色塊；r6 改為
        左對齊提示卡，避免誤認為可點擊按鈕，也降低視覺重量。
        """
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
            bg, fg, border = RED_SOFT if status != "data_abnormal" else ORANGE_SOFT, RED if status != "data_abnormal" else ORANGE, RED_BORDER if status != "data_abnormal" else ORANGE_BORDER
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
        if state.get("busy"):
            return
        state["selected_recycled_item_id"] = str(item_id or "").strip()
        rebuild()

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
        if show_loading:
            state["loading"] = True
            set_status("正在讀取回用料盤點單", "blue", True)
            rebuild()

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

                rebuild()
            except Exception as ex:
                if not is_active_view():
                    return
                state["counts"] = []
                state["loading"] = False
                set_status(f"讀取回用料盤點單失敗：{ex}", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def load_detail_background(count_id: str, show_loading: bool = True) -> None:
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
            rebuild()

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
                rebuild()

            except Exception as ex:
                if not is_active_view():
                    return
                state["detail"] = None
                state["loading"] = False
                set_status(f"讀取回用料明細失敗：{ex}", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    create_note_field = text_field(hint="例如：月盤、臨時盤點、回用料複查", multiline=True)

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

                if count_id:
                    navigate(f"/inventory/stocktake/recycled?count_id={count_id}")
                    return

                set_status(result.message, "green", True)
                rebuild()

            except Exception as ex:
                state["busy"] = False
                if not is_active_view():
                    return
                set_status(f"建立回用料盤點單失敗：{ex}", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def save_current_item_action(item: dict[str, Any], note_field: ft.TextField, check_status: str = "confirmed") -> None:
        """
        回用料單筆儲存專用流程。

        r4 重點：
        - 不使用全頁 state["busy"]，避免一筆儲存期間整頁按鈕全部失效。
        - 不在送出前先 rebuild()，避免手機 Web 在建立大量待核對清單時卡住。
        - 僅用 saving_recycled_item_ids 防重複送出；成功後才單次 rebuild()。
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

        saving_ids.add(item_id)
        set_status(f"正在儲存：{STATUS_LABELS.get(selected_status, '核對結果')}", "blue", True)

        def worker():
            try:
                result = update_count_recycled_item_check(
                    item_id=item_id,
                    check_status=selected_status,
                    actual_weight_kg="",
                    actual_supplier="",
                    actual_status="",
                    note=str(note_field.value or ""),
                    checked_by_user_id=current_user_id(),
                    checked_by_name=current_user_name(),
                )

                saving_ids.discard(item_id)

                if not is_active_view():
                    return

                if not result.ok:
                    set_status(result.message, "red", True)
                    rebuild()
                    return

                updated_item = (result.data or {}).get("item") or {}
                replace_recycled_item_in_state(updated_item)
                if str(state.get("selected_recycled_item_id") or "") == item_id:
                    state["selected_recycled_item_id"] = ""
                set_status(f"已儲存：{STATUS_LABELS.get(selected_status, '核對結果')}", "green", True)
                rebuild()

            except Exception as ex:
                saving_ids.discard(item_id)
                if not is_active_view():
                    return
                set_status(f"回用料核對失敗：{ex}", "red", True)
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

    def build_result_action_buttons(item: dict[str, Any], note_field: ft.TextField, saving: bool) -> ft.Control:
        """
        r6：結果按鈕改為 ResponsiveRow。

        每顆按鈕有明確欄寬，手機版兩欄排列，避免 Row wrap 在 Safari / Flet Web
        上偶發產生大灰色占位區。點擊仍直接儲存，不再有 chip 切換重建頁面的流程。
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
                        on_click=lambda e, it=item, nf=note_field, status_value=value: save_current_item_action(it, nf, status_value),
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
        status = str(self_item.get("check_status") or "unchecked")
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
                                ft.Text("目前選取" if selected else to_text(self_item.get("supplier")), size=13, color=GREEN if selected else TEXT_MUTED, weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_500),
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
        note_field = ft.TextField(
            value=str(item.get("note") or ""),
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
                            build_result_action_buttons(item, note_field, saving_current),
                        ],
                    ),
                    note_field,
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

        if not counts:
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
                                native_button(
                                    "進入逐筆盤點",
                                    ft.Icons.ARROW_FORWARD,
                                    GREEN_BTN,
                                    on_click=lambda e, cid=count_id: navigate(f"/inventory/stocktake/recycled?count_id={cid}"),
                                    expand=True,
                                ),
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

    def build_detail_panel() -> ft.Control:
        detail = state.get("detail")
        if not detail:
            return build_counts_list()

        count = detail.get("count") or {}
        summary = detail.get("summary") or {}
        status = str(count.get("status") or "draft")
        pending_items, checked_items = split_recycled_items()
        total_all = int(summary.get("total_items") or len(pending_items) + len(checked_items))
        current_index = len(checked_items) + 1 if pending_items else total_all
        can_edit = status == "draft"
        can_submit = can_edit and not pending_items and total_all > 0
        can_confirm = status == "submitted" and is_super_admin()

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

        controls.append(
            ft.ResponsiveRow(
                columns=12,
                spacing=10,
                run_spacing=10,
                controls=[
                    ft.Container(
                        col={"xs": 12, "md": 6},
                        content=native_outline_button("回用料盤點單列表", ft.Icons.LIST_ALT, GREEN, on_click=lambda e: navigate("/inventory/stocktake/recycled"), expand=True, disabled=state.get("busy")),
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

    main_host = ft.Container(width=float("inf"), expand=True, content=ft.Container())

    # =====================================================
    # 初始化
    # =====================================================
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

    main_host.content = build_page()
    return main_host
