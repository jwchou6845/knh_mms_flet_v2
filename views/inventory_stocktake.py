# =====================================================
# KNH MMS v2
# File: views/inventory_stocktake.py
# File Revision: 2026-05-15-stocktake-recycled-subpage-entry-r1
# Status: stocktake main page routes recycled counts to subpage
# Last Updated: 2026-05-15 Asia/Taipei
#
# Purpose:
# - 人工盤點功能頁面：建立盤點單、輸入實盤數、送出待審核、超級管理員確認盤點。
#
# Major Changes in This Revision:
# - 延續 r2 寬度修正版與 r4 控制中心風格麵包屑。
# - 新增「目前進行中的盤點」區塊，草稿盤點單獨立顯示，避免混在底下盤點單列表。
# - 盤點單列表預設不重複顯示草稿盤點單，降低操作員誤點與視覺干擾。
# - 草稿明細拆成「待盤點品項」與「已盤點品項」；儲存後的品項移至已盤點收合區。
# - 全部品項完成前，送出待審核按鈕維持停用，並顯示尚未盤點數量。
# - 不修改盤點建立、明細儲存、確認盤點與 stock_adjustments 寫入邏輯。
# - r6 將作廢盤點單改為底部「危險操作」收合式區塊；未輸入作廢原因不得送出。
# - r7 新增待審核退回修改流程。
# - r8 新增盲盤模式 count_mode：草稿階段隱藏帳面庫存與差異，送出待審核後才顯示差異。
# - r9 Step 2 新增回用料盤點單建立入口與唯讀明細顯示；暫不接單筆核對儲存 UI。
# - r10 Step 3 曾新增「儲存為在庫確認」單筆核對試行版。
# - r11 將回用料逐筆核對移出本頁，改導向 /inventory/stocktake/recycled 子頁，避免本頁渲染 25 筆回用料卡片造成卡頓。
#
# Notes:
# - Flet 0.84。
# - 不使用 page.push_route()。
# - 時間與庫存調整邏輯由 services/stocktake_service.py 統一使用 Asia/Taipei。
# - 第一版新料 / 母粒正式庫存盤點已完成；回用料逐筆盤點採分階段重新導入。
# - r8 需搭配 services/stocktake_service.py r3 與 inventory_counts.count_mode 欄位。
# - r9 Step 2 需搭配已部署的 stocktake_repo.py / stocktake_service.py 回用料資料層。
# - 回用料不使用盲盤；本版保留建立回用料盤點單與在庫明細顯示。
# - 回用料逐筆核對改由 views/inventory_stocktake_recycled.py 子頁處理；本頁只保留入口與列表導向。
# =====================================================

from __future__ import annotations

import threading
import time
from typing import Any

import flet as ft

from services.stocktake_service import (
    confirm_inventory_count,
    create_new_inventory_count,
    load_inventory_count_detail,
    load_inventory_counts,
    now_taipei,
    return_inventory_count,
    submit_inventory_count,
    update_count_item_actual_stock,
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

MOBILE_WIDTH = 620


# ============================================================
# Main View
# ============================================================
def InventoryStocktakeContent(page: ft.Page) -> ft.Control:
    """
    給 main.py / shell() 呼叫：
        InventoryStocktakeContent(page)

    這個 view 不直接操作 Supabase，所有資料讀寫都透過 services/stocktake_service.py。
    """

    if not hasattr(page, "session_data") or not isinstance(page.session_data, dict):
        page.session_data = {}

    view_token = object()
    page.session_data["_stocktake_view_token"] = view_token

    state: dict[str, Any] = {
        "alive": True,
        "loading": True,
        "busy": False,
        "status_visible": True,
        "status_theme": "blue",
        "status_message": "盤點資料同步中",
        "error_message": "",
        "counts": [],
        "summary": {},
        "detail": None,
        "active_count_id": "",
        "show_create_form": False,
        "create_count_type": "all",
        "create_count_mode": "normal",
        "void_reason": "",
        "show_entered_items": False,
        "show_void_form": False,
        "show_return_form": False,
        "show_checked_recycled_items": False,
        "recycled_saving_ids": set(),
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
            and page.session_data.get("_stocktake_view_token") is view_token
            and (not route or route == "/inventory/stocktake" or "stocktake" in route)
        )

    def safe_page_update() -> None:
        if not is_active_view():
            return
        try:
            page.update()
        except Exception as ex:
            print("stocktake page.update failed:", repr(ex), flush=True)

    def navigate(route: str) -> None:
        nav = session_get("_navigate")
        if callable(nav):
            nav(route)
            return
        page.go(route)

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

    def set_status(message: str, theme: str = "blue", visible: bool = True, auto_hide: bool = False) -> None:
        state["status_message"] = str(message or "")
        state["status_theme"] = theme
        state["status_visible"] = visible

        if auto_hide:
            version = time.time()
            state["status_hide_version"] = version

            def worker():
                time.sleep(3)
                if not is_active_view():
                    return
                if state.get("status_hide_version") != version:
                    return
                state["status_visible"] = False
                rebuild()

            threading.Thread(target=worker, daemon=True).start()

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

    def run_action(action, loading_message: str = "處理中...") -> None:
        if state.get("busy"):
            show_snack("系統正在處理上一個動作，請稍候。", success=False)
            return

        state["busy"] = True
        set_status(loading_message, "blue", True)
        rebuild()

        def worker():
            try:
                action()
            except Exception as ex:
                if not is_active_view():
                    return
                set_status(f"操作失敗：{ex}", "red", True)
                show_snack(f"操作失敗：{ex}", success=False)
            finally:
                if not is_active_view():
                    return
                state["busy"] = False
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

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

    def stable_button(
        label: str,
        icon,
        bg: str,
        fg: str = "#FFFFFF",
        border: str | None = None,
        on_click=None,
        height: int = 46,
        expand: bool = False,
        disabled: bool = False,
    ) -> ft.Container:
        btn = ft.Container(
            height=height,
            expand=expand,
            border_radius=12,
            bgcolor=DISABLED if disabled else bg,
            border=ft.border.all(1, border or (DISABLED if disabled else bg)),
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.symmetric(horizontal=14),
            opacity=0.65 if disabled else 1,
            ink=not disabled,
            content=ft.Row(
                tight=True,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
                controls=[
                    ft.Icon(icon, size=18, color=fg),
                    ft.Text(label, size=14, color=fg, weight=ft.FontWeight.BOLD, max_lines=1),
                ],
            ),
        )
        btn.disabled = disabled

        def handle(e):
            if getattr(btn, "disabled", False):
                return
            if callable(on_click):
                on_click(e)

        btn.on_click = handle
        return btn

    def outline_button(label: str, icon, color: str, on_click=None, expand: bool = False, disabled: bool = False):
        return stable_button(
            label=label,
            icon=icon,
            bg="#FFFFFF",
            fg=color if not disabled else DISABLED,
            border=color if not disabled else "#CBD5E1",
            on_click=on_click,
            expand=expand,
            disabled=disabled,
        )

    def field_group(label: str, control: ft.Control, required: bool = False) -> ft.Column:
        return ft.Column(
            expand=True,
            spacing=7,
            controls=[
                ft.Text(
                    label + (" *" if required else ""),
                    size=13,
                    color=TEXT,
                    weight=ft.FontWeight.W_600,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                control,
            ],
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
            height=94 if multiline else 56,
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

    def count_type_badge(label: str) -> ft.Container:
        return ft.Container(
            height=28,
            padding=ft.padding.symmetric(horizontal=10),
            border_radius=14,
            bgcolor=PURPLE_SOFT,
            border=ft.border.all(1, PURPLE_BORDER),
            alignment=ft.Alignment(0, 0),
            content=ft.Text(label, size=12, color=PURPLE, weight=ft.FontWeight.W_600),
        )

    def count_mode_badge(mode: str, label: str) -> ft.Container:
        is_blind = str(mode or "normal") == "blind"
        bg = ORANGE_SOFT if is_blind else BLUE_SOFT
        fg = ORANGE if is_blind else BLUE
        border = ORANGE_BORDER if is_blind else BLUE_BORDER
        return ft.Container(
            height=28,
            padding=ft.padding.symmetric(horizontal=10),
            border_radius=14,
            bgcolor=bg,
            border=ft.border.all(1, border),
            alignment=ft.Alignment(0, 0),
            content=ft.Text(label, size=12, color=fg, weight=ft.FontWeight.W_600),
        )

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

    def type_chip(value: str, label: str) -> ft.Container:
        selected = state.get("create_count_type") == value
        return ft.Container(
            height=38,
            padding=ft.padding.symmetric(horizontal=14),
            border_radius=19,
            bgcolor=BLUE_SOFT if selected else "#FFFFFF",
            border=ft.border.all(1, BLUE if selected else BORDER),
            ink=True,
            on_click=lambda e, v=value: set_create_count_type(v),
            content=ft.Row(
                tight=True,
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE if selected else ft.Icons.RADIO_BUTTON_UNCHECKED, size=16, color=BLUE if selected else TEXT_MUTED),
                    ft.Text(label, size=13, color=BLUE if selected else TEXT_MUTED, weight=ft.FontWeight.W_600),
                ],
            ),
        )

    def set_create_count_type(value: str):
        state["create_count_type"] = value
        if value == "recycled":
            # 回用料採逐筆核對，不使用一般盤點 / 盲盤模式。
            state["create_count_mode"] = "normal"
        rebuild()

    def mode_chip(value: str, label: str, subtitle: str = "") -> ft.Container:
        selected = state.get("create_count_mode") == value
        color = ORANGE if value == "blind" else BLUE
        soft = ORANGE_SOFT if value == "blind" else BLUE_SOFT
        border = ORANGE_BORDER if value == "blind" else BLUE_BORDER
        return ft.Container(
            padding=ft.padding.symmetric(horizontal=13, vertical=10),
            border_radius=16,
            bgcolor=soft if selected else "#FFFFFF",
            border=ft.border.all(1, color if selected else BORDER),
            ink=True,
            on_click=lambda e, v=value: set_create_count_mode(v),
            content=ft.Row(
                tight=True,
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE if selected else ft.Icons.RADIO_BUTTON_UNCHECKED, size=17, color=color if selected else TEXT_MUTED),
                    ft.Column(
                        tight=True,
                        spacing=1,
                        controls=[
                            ft.Text(label, size=13, color=color if selected else TEXT_MUTED, weight=ft.FontWeight.W_700),
                            ft.Text(subtitle, size=11, color=TEXT_MUTED, visible=bool(subtitle)),
                        ],
                    ),
                ],
            ),
        )

    def set_create_count_mode(value: str):
        state["create_count_mode"] = "blind" if value == "blind" else "normal"
        rebuild()

    def is_blind_draft(count: dict[str, Any]) -> bool:
        return str(count.get("count_mode") or "normal") == "blind" and str(count.get("status") or "draft") == "draft"

    def is_recycled_count(count: dict[str, Any]) -> bool:
        return str(count.get("count_type") or "") == "recycled"

    def toggle_entered_items(e=None):
        state["show_entered_items"] = not bool(state.get("show_entered_items"))
        rebuild()

    def toggle_checked_recycled_items(e=None):
        state["show_checked_recycled_items"] = not bool(state.get("show_checked_recycled_items"))
        rebuild()

    def toggle_void_form(e=None):
        state["show_void_form"] = not bool(state.get("show_void_form"))
        rebuild()

    def close_void_form(e=None):
        state["show_void_form"] = False
        try:
            void_reason_field.value = ""
            state["show_void_form"] = False
        except Exception:
            pass
        rebuild()

    def toggle_return_form(e=None):
        state["show_return_form"] = not bool(state.get("show_return_form"))
        if state.get("show_return_form"):
            state["show_void_form"] = False
        rebuild()

    def close_return_form(e=None):
        state["show_return_form"] = False
        try:
            return_reason_field.value = ""
        except Exception:
            pass
        rebuild()

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
    # 資料載入與操作
    # =====================================================
    def apply_counts_result(result) -> None:
        if result.ok:
            data = result.data or {}
            state["counts"] = data.get("counts", []) or []
            state["summary"] = data.get("summary", {}) or {}
            state["error_message"] = ""
            state["loading"] = False
            set_status("盤點資料已同步", "green", True, auto_hide=True)
        else:
            state["counts"] = []
            state["summary"] = {}
            state["error_message"] = result.message
            state["loading"] = False
            set_status("盤點資料同步失敗", "red", True)

    def refresh_counts(silent: bool = False) -> None:
        result = load_inventory_counts(limit=60)
        apply_counts_result(result)
        if silent and result.ok:
            state["status_visible"] = False

    def load_counts_background(show_loading: bool = True) -> None:
        if show_loading:
            state["loading"] = True
            set_status("盤點資料同步中", "blue", True)
            rebuild()

        def worker():
            try:
                result = load_inventory_counts(limit=60)
                if not is_active_view():
                    return
                apply_counts_result(result)
                rebuild()
            except Exception as ex:
                if not is_active_view():
                    return
                state["loading"] = False
                state["error_message"] = str(ex)
                set_status(f"盤點資料同步失敗：{ex}", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def load_detail(count_id: str, show_status: bool = True) -> None:
        state["active_count_id"] = count_id
        state["show_void_form"] = False
        state["show_return_form"] = False
        if show_status:
            set_status("正在讀取盤點明細", "blue", True)
            rebuild()

        def worker():
            try:
                result = load_inventory_count_detail(count_id)
                if not is_active_view():
                    return
                if result.ok:
                    state["detail"] = result.data or {}
                    set_status("盤點明細已同步", "green", True, auto_hide=True)
                else:
                    state["detail"] = None
                    set_status(result.message, "red", True)
                    show_snack(result.message, success=False)
                rebuild()
            except Exception as ex:
                if not is_active_view():
                    return
                state["detail"] = None
                set_status(f"讀取盤點明細失敗：{ex}", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def close_detail(e=None) -> None:
        state["active_count_id"] = ""
        state["detail"] = None
        state["show_void_form"] = False
        state["show_return_form"] = False
        rebuild()

    def open_create_form(e=None) -> None:
        state["show_create_form"] = True
        state["create_count_type"] = "all"
        state["create_count_mode"] = "normal"
        state["show_void_form"] = False
        state["show_return_form"] = False
        rebuild()

    def close_create_form(e=None) -> None:
        state["show_create_form"] = False
        rebuild()

    def open_recycled_stocktake_page(count_id: str | None = None) -> None:
        count_id = str(count_id or "").strip()
        if count_id:
            navigate(f"/inventory/stocktake/recycled?count_id={count_id}")
        else:
            navigate("/inventory/stocktake/recycled")

    # create form controls are created once to preserve input values while rebuilding.
    count_date_field = text_field(value=today_text(), hint="YYYY-MM-DD")
    create_note_field = text_field(hint="例如：月盤、臨時盤點、低水位複查", multiline=True)

    def create_count_action(e=None) -> None:
        def action():
            result = create_new_inventory_count(
                count_date=str(count_date_field.value or ""),
                count_type=str(state.get("create_count_type") or "all"),
                count_mode=str(state.get("create_count_mode") or "normal"),
                note=str(create_note_field.value or ""),
                created_by_user_id=current_user_id(),
                created_by_name=current_user_name(),
            )
            if not is_active_view():
                return
            if not result.ok:
                set_status(result.message, "red", True)
                show_snack(result.message, success=False)
                return

            data = result.data or {}
            count = data.get("count") or {}
            count_id = str(count.get("id") or "")
            state["show_create_form"] = False
            state["show_return_form"] = False
            create_note_field.value = ""
            count_date_field.value = today_text()
            refresh_counts(silent=True)
            set_status(result.message, "green", True, auto_hide=True)
            show_snack(result.message, success=True)

            if str(state.get("create_count_type") or "") == "recycled":
                if count_id:
                    open_recycled_stocktake_page(count_id)
                return

            if count_id:
                detail_result = load_inventory_count_detail(count_id)
                if detail_result.ok:
                    state["active_count_id"] = count_id
                    state["detail"] = detail_result.data or {}

        run_action(action, "正在建立盤點單...")

    def save_item_action(item: dict[str, Any], qty_field: ft.TextField, note_field: ft.TextField):
        def action():
            result = update_count_item_actual_stock(
                item_id=str(item.get("id") or ""),
                actual_stock_bags=str(qty_field.value or ""),
                note=str(note_field.value or ""),
            )
            if not is_active_view():
                return
            if not result.ok:
                set_status(result.message, "red", True)
                show_snack(result.message, success=False)
                return

            active_id = str(state.get("active_count_id") or "")
            if active_id:
                detail_result = load_inventory_count_detail(active_id)
                if detail_result.ok:
                    state["detail"] = detail_result.data or {}
            set_status(result.message, "green", True, auto_hide=True)
            show_snack(result.message, success=True)

        run_action(action, "正在更新實盤數...")

    def recalc_recycled_summary_from_state(items: list[dict[str, Any]]) -> dict[str, Any]:
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
        detail["summary"] = recalc_recycled_summary_from_state(items)
        state["detail"] = detail

    def save_recycled_confirmed_action(item: dict[str, Any]) -> None:
        item_id = str(item.get("id") or "")
        if not item_id:
            set_status("找不到回用料盤點明細。", "red", True)
            rebuild()
            return

        saving_ids = state.setdefault("recycled_saving_ids", set())
        if item_id in saving_ids:
            return

        saving_ids.add(item_id)

        def worker():
            try:
                result = update_count_recycled_item_check(
                    item_id=item_id,
                    check_status="confirmed",
                    actual_weight_kg="",
                    actual_supplier="",
                    actual_status="",
                    note="",
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

                data = result.data or {}
                replace_recycled_item_in_state(data.get("item") or {})
                set_status("回用料已儲存為在庫確認。", "green", True)
                rebuild()

            except Exception as ex:
                saving_ids.discard(item_id)
                if not is_active_view():
                    return
                set_status(f"回用料核對失敗：{ex}", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def submit_count_action(e=None):
        detail = state.get("detail") or {}
        count = detail.get("count") or {}
        count_id = str(count.get("id") or "")

        def action():
            result = submit_inventory_count(
                count_id=count_id,
                submitted_by_user_id=current_user_id(),
                submitted_by_name=current_user_name(),
            )
            if not is_active_view():
                return
            if not result.ok:
                set_status(result.message, "red", True)
                show_snack(result.message, success=False)
                return

            refresh_counts(silent=True)
            detail_result = load_inventory_count_detail(count_id)
            if detail_result.ok:
                state["detail"] = detail_result.data or {}
            set_status(result.message, "green", True, auto_hide=True)
            show_snack(result.message, success=True)

        run_action(action, "正在送出盤點單...")

    def confirm_count_action(e=None):
        if not is_super_admin():
            show_snack("只有超級管理員可以確認盤點。", success=False)
            return

        detail = state.get("detail") or {}
        count = detail.get("count") or {}
        count_id = str(count.get("id") or "")

        def action():
            result = confirm_inventory_count(
                count_id=count_id,
                confirmed_by_user_id=current_user_id(),
                confirmed_by_name=current_user_name(),
            )
            if not is_active_view():
                return
            if not result.ok:
                set_status(result.message, "red", True)
                show_snack(result.message, success=False)
                return

            refresh_counts(silent=True)
            detail_result = load_inventory_count_detail(count_id)
            if detail_result.ok:
                state["detail"] = detail_result.data or {}
            set_status(result.message, "green", True, auto_hide=True)
            show_snack(result.message, success=True)

        run_action(action, "正在確認盤點並寫入庫存調整...")

    return_reason_field = text_field(hint="請輸入退回原因", multiline=True)

    def return_count_action(e=None):
        if not is_super_admin():
            show_snack("只有超級管理員可以退回盤點單。", success=False)
            return

        reason = str(return_reason_field.value or "").strip()
        if not reason:
            set_status("請輸入退回原因。", "red", True)
            show_snack("請輸入退回原因。", success=False)
            return

        detail = state.get("detail") or {}
        count = detail.get("count") or {}
        count_id = str(count.get("id") or "")

        def action():
            result = return_inventory_count(
                count_id=count_id,
                return_reason=reason,
                returned_by_user_id=current_user_id(),
                returned_by_name=current_user_name(),
            )
            if not is_active_view():
                return
            if not result.ok:
                set_status(result.message, "red", True)
                show_snack(result.message, success=False)
                return

            return_reason_field.value = ""
            state["show_return_form"] = False
            refresh_counts(silent=True)
            detail_result = load_inventory_count_detail(count_id)
            if detail_result.ok:
                state["detail"] = detail_result.data or {}
            set_status(result.message, "green", True, auto_hide=True)
            show_snack(result.message, success=True)

        run_action(action, "正在退回盤點單...")

    void_reason_field = text_field(hint="請輸入作廢原因", multiline=True)

    def void_count_action(e=None):
        if not is_super_admin():
            show_snack("只有超級管理員可以作廢盤點單。", success=False)
            return

        reason = str(void_reason_field.value or "").strip()
        if not reason:
            set_status("請輸入作廢原因。", "red", True)
            show_snack("請輸入作廢原因。", success=False)
            return

        detail = state.get("detail") or {}
        count = detail.get("count") or {}
        count_id = str(count.get("id") or "")

        def action():
            result = void_inventory_count(
                count_id=count_id,
                void_reason=reason,
                voided_by_user_id=current_user_id(),
                voided_by_name=current_user_name(),
            )
            if not is_active_view():
                return
            if not result.ok:
                set_status(result.message, "red", True)
                show_snack(result.message, success=False)
                return

            void_reason_field.value = ""
            state["show_void_form"] = False
            state["show_return_form"] = False
            refresh_counts(silent=True)
            detail_result = load_inventory_count_detail(count_id)
            if detail_result.ok:
                state["detail"] = detail_result.data or {}
            set_status(result.message, "green", True, auto_hide=True)
            show_snack(result.message, success=True)

        run_action(action, "正在作廢盤點單...")

    # =====================================================
    # 畫面區塊
    # =====================================================
    def breadcrumb_item(label: str, route: str | None = None, active: bool = False) -> ft.Control:
        """
        對齊控制中心的輕量麵包屑樣式。

        r3 使用外框膠囊，在手機 Web 上會被渲染成整列按鈕並換行，
        造成「原料入庫作業 / > / 人工盤點」各自佔一列。
        r4 改為透明文字連結 + 小型 active 底色，避免破壞版面。
        """
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
            breadcrumb_item("人工盤點", route=None if not count_no else "/inventory/stocktake", active=not bool(count_no)),
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
                                bgcolor=BLUE_SOFT,
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(ft.Icons.FACT_CHECK_OUTLINED, size=31, color=BLUE),
                            ),
                            ft.Column(
                                expand=True,
                                spacing=4,
                                controls=[
                                    ft.Text("人工盤點", size=28, weight=ft.FontWeight.BOLD, color=TEXT),
                                    ft.Text(
                                        "建立盤點單，比對帳面庫存與現場實盤數；確認後才會寫入正式庫存調整。",
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

    def build_summary_cards() -> ft.Control:
        summary = state.get("summary") or {}
        return ft.ResponsiveRow(
            columns=12,
            spacing=12,
            run_spacing=12,
            controls=[
                metric_card("草稿", summary.get("draft", 0), BLUE, ft.Icons.EDIT_NOTE),
                metric_card("待審核", summary.get("submitted", 0), ORANGE, ft.Icons.PENDING_ACTIONS),
                metric_card("已確認", summary.get("confirmed", 0), GREEN, ft.Icons.CHECK_CIRCLE_OUTLINE),
                metric_card("已作廢", summary.get("voided", 0), RED, ft.Icons.BLOCK),
            ],
        )

    def build_create_mode_control() -> ft.Control:
        if state.get("create_count_type") == "recycled":
            return ft.Container(
                col={"xs": 12},
                bgcolor=ORANGE_SOFT,
                border=ft.border.all(1, ORANGE_BORDER),
                border_radius=14,
                padding=14,
                content=ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.INFO_OUTLINE, color=ORANGE, size=20),
                        ft.Text(
                            "回用料採逐筆核對，不使用盲盤模式；建立後會進入「回用料逐筆盤點」子頁。",
                            size=13,
                            color="#9A4A12",
                            weight=ft.FontWeight.W_600,
                            expand=True,
                        ),
                    ],
                ),
            )

        return ft.Container(
            col={"xs": 12},
            content=ft.Column(
                spacing=7,
                controls=[
                    ft.Text("盤點模式 *", size=13, color=TEXT, weight=ft.FontWeight.W_600),
                    ft.Row(
                        wrap=True,
                        spacing=10,
                        run_spacing=10,
                        controls=[
                            mode_chip("normal", "一般盤點", "盤點中顯示帳面與差異"),
                            mode_chip("blind", "盲盤", "草稿盤點中隱藏帳面與差異"),
                        ],
                    ),
                ],
            ),
        )

    def build_create_form() -> ft.Control:
        if not state.get("show_create_form"):
            return ft.Container(height=0)

        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.border.all(1, BLUE_BORDER),
            border_radius=20,
            padding=20,
            content=ft.Column(
                spacing=16,
                controls=[
                    ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.ADD_TASK, size=26, color=BLUE),
                            section_title("新增盤點單", "系統會依目前啟用且納管的帳面庫存建立盤點明細。"),
                        ],
                    ),
                    ft.Container(
                        bgcolor=BLUE_SOFT,
                        border=ft.border.all(1, BLUE_BORDER),
                        border_radius=14,
                        padding=14,
                        content=ft.Text(
                            "第一版支援新料 / 母粒盤點；回用料逐筆盤點已拆到獨立子頁，建立後會自動進入逐筆核對流程。盲盤模式在草稿階段不顯示帳面庫存與差異，送出待審核後才顯示盤盈盤虧。",
                            size=13,
                            color="#315F9A",
                        ),
                    ),
                    ft.ResponsiveRow(
                        columns=12,
                        spacing=14,
                        run_spacing=14,
                        controls=[
                            ft.Container(col={"xs": 12, "md": 6}, content=field_group("盤點日期", count_date_field, True)),
                            ft.Container(
                                col={"xs": 12, "md": 6},
                                content=ft.Column(
                                    spacing=7,
                                    controls=[
                                        ft.Text("盤點類型 *", size=13, color=TEXT, weight=ft.FontWeight.W_600),
                                        ft.Row(
                                            wrap=True,
                                            spacing=8,
                                            run_spacing=8,
                                            controls=[
                                                type_chip("all", "全部"),
                                                type_chip("new", "新料"),
                                                type_chip("aux", "母粒"),
                                                type_chip("recycled", "回用料"),
                                            ],
                                        ),
                                    ],
                                ),
                            ),
                            build_create_mode_control(),
                            ft.Container(col={"xs": 12}, content=field_group("備註", create_note_field, False)),
                        ],
                    ),
                    ft.Row(
                        spacing=12,
                        controls=[
                            outline_button("取消", ft.Icons.CLOSE, TEXT_MUTED, close_create_form, expand=True),
                            stable_button("建立盤點單", ft.Icons.SAVE_OUTLINED, BLUE_BTN, on_click=create_count_action, expand=True, disabled=state.get("busy")),
                        ],
                    ),
                ],
            ),
        )

    def build_top_actions() -> ft.Control:
        return ft.Row(
            spacing=12,
            controls=[
                stable_button("新增盤點單", ft.Icons.ADD, BLUE_BTN, on_click=open_create_form, expand=True, disabled=state.get("busy")),
                outline_button("重新整理", ft.Icons.REFRESH, BLUE, lambda e: load_counts_background(True), expand=True, disabled=state.get("busy")),
            ],
        )

    def build_in_progress_section() -> ft.Control:
        counts = state.get("counts") or []
        active_id = str(state.get("active_count_id") or "")
        drafts = [
            count
            for count in counts
            if str(count.get("status") or "") == "draft"
            and str(count.get("id") or "") != active_id
        ]

        if not drafts:
            return ft.Container(height=0)

        controls: list[ft.Control] = [
            ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.PLAYLIST_ADD_CHECK_OUTLINED, size=25, color=BLUE),
                    section_title(
                        "目前進行中的盤點",
                        "草稿盤點單可從這裡繼續盤點或作廢；不再混在下方盤點單列表中。",
                    ),
                ],
            )
        ]

        for count in drafts:
            controls.append(build_count_card(count, action_label="繼續盤點", highlight=True))

        return ft.Container(
            bgcolor=BLUE_SOFT,
            border=ft.border.all(1, BLUE_BORDER),
            border_radius=20,
            padding=18,
            content=ft.Column(spacing=14, controls=controls),
        )

    def build_count_card(count: dict[str, Any], action_label: str = "查看明細", highlight: bool = False) -> ft.Control:
        is_recycled = str(count.get("count_type") or "") == "recycled"
        display_action_label = "逐筆核對" if is_recycled else action_label
        action_icon = ft.Icons.RECYCLING_OUTLINED if is_recycled else ft.Icons.VISIBILITY_OUTLINED

        def open_action(e=None, cid=count.get("id")):
            if is_recycled:
                open_recycled_stocktake_page(str(cid or ""))
                return
            load_detail(str(cid or ""))

        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.border.all(1, BLUE_BORDER if highlight else BORDER),
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
                                bgcolor=GREEN_SOFT if is_recycled else "#F8FAFC",
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(ft.Icons.RECYCLING_OUTLINED if is_recycled else ft.Icons.ASSIGNMENT_OUTLINED, color=GREEN if is_recycled else BLUE, size=25),
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
                        ],
                    ),
                    ft.Row(
                        wrap=True,
                        spacing=8,
                        run_spacing=8,
                        controls=[
                            status_badge(count.get("status"), count.get("status_label") or "-"),
                            count_type_badge(count.get("count_type_label") or "全部"),
                            count_mode_badge(count.get("count_mode") or "normal", count.get("count_mode_label") or "一般盤點"),
                        ],
                    ),
                    ft.Row(
                        spacing=10,
                        controls=[
                            outline_button(display_action_label, action_icon, GREEN if is_recycled else BLUE, open_action, expand=True),
                        ],
                    ),
                ],
            ),
        )


    def build_count_list() -> ft.Control:
        all_counts = state.get("counts") or []
        # 草稿盤點單移到「目前進行中的盤點」區塊，避免剛建立的盤點單又出現在底下列表。
        counts = [count for count in all_counts if str(count.get("status") or "") != "draft"]

        controls: list[ft.Control] = [
            ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.LIST_ALT, size=25, color=TEXT_MUTED),
                    section_title("盤點單列表", f"顯示待審核、已確認與已作廢盤點單，共 {len(counts)} 張。"),
                ],
            )
        ]

        if not counts:
            controls.append(
                ft.Container(
                    bgcolor="#FFFFFF",
                    border=ft.border.all(1, BORDER),
                    border_radius=16,
                    padding=18,
                    content=ft.Row(
                        spacing=10,
                        controls=[
                            ft.Icon(ft.Icons.INFO_OUTLINE, color=TEXT_MUTED, size=20),
                            ft.Text("目前尚無待審核、已確認或已作廢的盤點單。", size=14, color=TEXT_MUTED),
                        ],
                    ),
                )
            )
        else:
            for count in counts:
                controls.append(build_count_card(count))

        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.border.all(1, BORDER),
            border_radius=20,
            padding=18,
            content=ft.Column(spacing=14, controls=controls),
        )

    def build_detail_summary(summary: dict[str, Any], blind_draft: bool = False) -> ft.Control:
        if blind_draft:
            controls = [
                metric_card("總項目", summary.get("total_items", 0), BLUE, ft.Icons.INVENTORY_2_OUTLINED),
                metric_card("已輸入", summary.get("entered_items", 0), GREEN, ft.Icons.CHECK_CIRCLE_OUTLINE),
                metric_card("未輸入", summary.get("not_entered_items", 0), RED, ft.Icons.ERROR_OUTLINE),
                metric_card("盤點模式", "盲盤", ORANGE, ft.Icons.VISIBILITY_OFF_OUTLINED),
            ]
        else:
            controls = [
                metric_card("總項目", summary.get("total_items", 0), BLUE, ft.Icons.INVENTORY_2_OUTLINED),
                metric_card("已輸入", summary.get("entered_items", 0), GREEN, ft.Icons.CHECK_CIRCLE_OUTLINE),
                metric_card("有差異", summary.get("difference_items", 0), ORANGE, ft.Icons.COMPARE_ARROWS),
                metric_card("未輸入", summary.get("not_entered_items", 0), RED, ft.Icons.ERROR_OUTLINE),
            ]

        return ft.ResponsiveRow(
            columns=12,
            spacing=12,
            run_spacing=12,
            controls=controls,
        )

    def build_recycled_detail_summary(summary: dict[str, Any]) -> ft.Control:
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

    def diff_color(item: dict[str, Any]) -> tuple[str, str, str]:
        diff = float(item.get("difference_bags") or 0)
        if not item.get("has_actual"):
            return GRAY_SOFT, TEXT_MUTED, BORDER
        if diff > 0:
            return GREEN_SOFT, GREEN, GREEN_BORDER
        if diff < 0:
            return RED_SOFT, RED, RED_BORDER
        return GRAY_SOFT, TEXT_MUTED, BORDER

    def build_item_card(item: dict[str, Any], editable: bool, hide_system_values: bool = False) -> ft.Control:
        bg, fg, border = diff_color(item)
        actual_value = item.get("actual_stock_bags")
        qty_field = text_field(
            value="" if actual_value is None else fmt_num(actual_value),
            hint="輸入實盤包數",
            number=True,
        )
        note_field = text_field(
            value=item.get("note") or "",
            hint="此品項備註",
            multiline=True,
        )

        if hide_system_values:
            details = [
                ft.Container(
                    bgcolor=ORANGE_SOFT,
                    border=ft.border.all(1, ORANGE_BORDER),
                    border_radius=12,
                    padding=12,
                    content=ft.ResponsiveRow(
                        columns=12,
                        spacing=8,
                        run_spacing=8,
                        controls=[
                            ft.Container(
                                col={"xs": 6, "md": 4},
                                content=ft.Column(
                                    spacing=2,
                                    controls=[
                                        ft.Text("包重", size=12, color=TEXT_MUTED),
                                        ft.Text(fmt_num(item.get("bag_weight_kg"), " KG"), size=15, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ],
                                ),
                            ),
                            ft.Container(
                                col={"xs": 6, "md": 4},
                                content=ft.Column(
                                    spacing=2,
                                    controls=[
                                        ft.Text("實盤", size=12, color=TEXT_MUTED),
                                        ft.Text("未輸入" if actual_value is None else fmt_num(actual_value, " 包"), size=15, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ],
                                ),
                            ),
                            ft.Container(
                                col={"xs": 12, "md": 4},
                                content=ft.Container(
                                    height=34,
                                    border_radius=17,
                                    bgcolor=ORANGE_SOFT,
                                    border=ft.border.all(1, ORANGE_BORDER),
                                    alignment=ft.Alignment(0, 0),
                                    content=ft.Text("盲盤中：帳面與差異已隱藏", size=13, color=ORANGE, weight=ft.FontWeight.BOLD),
                                ),
                            ),
                        ],
                    ),
                )
            ]
        else:
            details = [
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
                                col={"xs": 4, "md": 3},
                                content=ft.Column(
                                    spacing=2,
                                    controls=[
                                        ft.Text("帳面", size=12, color=TEXT_MUTED),
                                        ft.Text(fmt_num(item.get("system_stock_bags"), " 包"), size=15, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ],
                                ),
                            ),
                            ft.Container(
                                col={"xs": 4, "md": 3},
                                content=ft.Column(
                                    spacing=2,
                                    controls=[
                                        ft.Text("實盤", size=12, color=TEXT_MUTED),
                                        ft.Text("未輸入" if actual_value is None else fmt_num(actual_value, " 包"), size=15, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ],
                                ),
                            ),
                            ft.Container(
                                col={"xs": 4, "md": 3},
                                content=ft.Column(
                                    spacing=2,
                                    controls=[
                                        ft.Text("包重", size=12, color=TEXT_MUTED),
                                        ft.Text(fmt_num(item.get("bag_weight_kg"), " KG"), size=15, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ],
                                ),
                            ),
                            ft.Container(
                                col={"xs": 12, "md": 3},
                                content=ft.Container(
                                    height=34,
                                    border_radius=17,
                                    bgcolor=bg,
                                    border=ft.border.all(1, border),
                                    alignment=ft.Alignment(0, 0),
                                    content=ft.Text(item.get("difference_label") or "未輸入", size=13, color=fg, weight=ft.FontWeight.BOLD),
                                ),
                            ),
                        ],
                    ),
                )
            ]

        if editable:
            details.extend(
                [
                    ft.ResponsiveRow(
                        columns=12,
                        spacing=14,
                        run_spacing=14,
                        controls=[
                            ft.Container(col={"xs": 12, "md": 4}, content=field_group("實盤包數", qty_field, True)),
                            ft.Container(col={"xs": 12, "md": 8}, content=field_group("備註", note_field, False)),
                        ],
                    ),
                    ft.Row(
                        controls=[
                            stable_button(
                                "儲存此品項",
                                ft.Icons.SAVE_OUTLINED,
                                BLUE_BTN,
                                on_click=lambda e, it=item, q=qty_field, n=note_field: save_item_action(it, q, n),
                                expand=True,
                                disabled=state.get("busy"),
                            )
                        ]
                    ),
                ]
            )

        return ft.Container(
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
                                bgcolor=BLUE_SOFT,
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, color=BLUE, size=25),
                            ),
                            ft.Column(
                                expand=True,
                                spacing=3,
                                controls=[
                                    ft.Text(item.get("material_name") or "-", size=18, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ft.Text(
                                        f"{item.get('main_category') or '-'}｜{item.get('material_type') or '-'}｜{item.get('supplier') or '-'}",
                                        size=13,
                                        color=TEXT_MUTED,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    *details,
                ],
            ),
        )

    def recycled_status_badge(item: dict[str, Any]) -> ft.Container:
        status = str(item.get("check_status") or "unchecked")
        label = str(item.get("check_status_label") or "未核對")
        if status == "confirmed":
            bg, fg, border = GREEN_SOFT, GREEN, GREEN_BORDER
        elif status in ["missing", "used_not_recorded", "scrap_required", "data_abnormal"]:
            bg, fg, border = RED_SOFT, RED, RED_BORDER
        else:
            bg, fg, border = GRAY_SOFT, TEXT_MUTED, BORDER

        return ft.Container(
            height=30,
            padding=ft.padding.symmetric(horizontal=10),
            border_radius=15,
            bgcolor=bg,
            border=ft.border.all(1, border),
            alignment=ft.Alignment(0, 0),
            content=ft.Text(label, size=12, color=fg, weight=ft.FontWeight.W_600),
        )

    def build_recycled_readonly_item_card(item: dict[str, Any]) -> ft.Control:
        return ft.Container(
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
                                    ft.Text(item.get("recycled_no") or "-", size=18, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ft.Text(
                                        f"{item.get('material_type') or '-'}｜{item.get('supplier') or '-'}｜{fmt_num(item.get('weight_kg'), ' KG')}",
                                        size=13,
                                        color=TEXT_MUTED,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                ],
                            ),
                            recycled_status_badge(item),
                        ],
                    ),
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
                                    col={"xs": 6, "md": 3},
                                    content=ft.Column(
                                        spacing=2,
                                        controls=[
                                            ft.Text("重量", size=12, color=TEXT_MUTED),
                                            ft.Text(fmt_num(item.get("weight_kg"), " KG"), size=15, color=TEXT, weight=ft.FontWeight.BOLD),
                                        ],
                                    ),
                                ),
                                ft.Container(
                                    col={"xs": 6, "md": 3},
                                    content=ft.Column(
                                        spacing=2,
                                        controls=[
                                            ft.Text("供應商", size=12, color=TEXT_MUTED),
                                            ft.Text(to_text(item.get("supplier")), size=15, color=TEXT, weight=ft.FontWeight.BOLD),
                                        ],
                                    ),
                                ),
                                ft.Container(
                                    col={"xs": 12, "md": 6},
                                    content=ft.Column(
                                        spacing=2,
                                        controls=[
                                            ft.Text("目前狀態", size=12, color=TEXT_MUTED),
                                            ft.Text(to_text(item.get("usage_status")), size=15, color=TEXT, weight=ft.FontWeight.BOLD),
                                        ],
                                    ),
                                ),
                            ],
                        ),
                    ),
                    ft.Container(
                        bgcolor=BLUE_SOFT,
                        border=ft.border.all(1, BLUE_BORDER),
                        border_radius=12,
                        padding=12,
                        content=ft.Text(
                            "此階段先顯示回用料逐筆明細；單筆核對與儲存按鈕將於下一步接上。",
                            size=12,
                            color="#315F9A",
                        ),
                    ),
                ],
            ),
        )

    def build_recycled_pending_item_card(item: dict[str, Any], editable: bool) -> ft.Control:
        card = build_recycled_readonly_item_card(item)
        if not editable:
            return card

        item_id = str(item.get("id") or "")
        saving_ids = state.get("recycled_saving_ids") or set()
        saving = item_id in saving_ids

        action_box = ft.Container(
            bgcolor=GREEN_SOFT,
            border=ft.border.all(1, GREEN_BORDER),
            border_radius=12,
            padding=12,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Text(
                        "盤點結果",
                        size=13,
                        color=TEXT,
                        weight=ft.FontWeight.W_600,
                    ),
                    ft.Text(
                        "此版先開放最常用的「在庫確認」。儲存成功後，該筆會移到下方已核對收合區。",
                        size=12,
                        color=TEXT_MUTED,
                    ),
                    stable_button(
                        "正在儲存..." if saving else "儲存為在庫確認",
                        ft.Icons.CHECK_CIRCLE_OUTLINE,
                        GREEN_BTN,
                        on_click=lambda e, it=item: save_recycled_confirmed_action(it),
                        expand=True,
                        disabled=saving,
                    ),
                ],
            ),
        )

        try:
            card.content.controls[-1] = action_box
        except Exception:
            pass
        return card

    def build_detail_panel() -> ft.Control:
        detail = state.get("detail")
        if not detail:
            return ft.Container(height=0)

        count = detail.get("count") or {}
        items = detail.get("items") or []
        recycled_items = detail.get("recycled_items") or []
        summary = detail.get("summary") or {}
        status = count.get("status") or "draft"
        recycled_count = is_recycled_count(count)
        editable = status == "draft"
        blind_draft = is_blind_draft(count)
        remaining_items = int(summary.get("not_entered_items", 0) or 0)
        # Step 2 先只顯示回用料明細，不開放單筆核對與送出待審核。
        can_submit = editable and remaining_items == 0 and not recycled_count
        can_confirm = status == "submitted" and is_super_admin()
        can_void = status in ["draft", "submitted"] and is_super_admin()

        controls: list[ft.Control] = [
            ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.FACT_CHECK_OUTLINED, size=27, color=BLUE),
                    ft.Column(
                        expand=True,
                        spacing=3,
                        controls=[
                            ft.Text(f"盤點明細：{count.get('count_no') or '-'}", size=21, color=TEXT, weight=ft.FontWeight.BOLD),
                            ft.Text(f"{count.get('count_date') or '-'}｜{count.get('count_type_label') or '-'}｜建立人：{count.get('created_by_name') or '-'}", size=13, color=TEXT_MUTED),
                        ],
                    ),
                    status_badge(status, count.get("status_label") or "-"),
                    count_mode_badge(count.get("count_mode") or "normal", count.get("count_mode_label") or "一般盤點"),
                ],
            ),
            build_recycled_detail_summary(summary) if recycled_count else build_detail_summary(summary, blind_draft=blind_draft),
        ]

        if status == "submitted":
            controls.append(
                ft.Container(
                    bgcolor=ORANGE_SOFT,
                    border=ft.border.all(1, ORANGE_BORDER),
                    border_radius=14,
                    padding=14,
                    content=ft.Text(
                        "此盤點單已送出待審核。退回可修改；確認將依差異值影響首頁庫存與低水位。",
                        size=13,
                        color="#9A4A12",
                    ),
                )
            )

        if status == "confirmed":
            controls.append(
                ft.Container(
                    bgcolor=GREEN_SOFT,
                    border=ft.border.all(1, GREEN_BORDER),
                    border_radius=14,
                    padding=14,
                    content=ft.Text(
                        f"此盤點單已確認。調整批號：{count.get('adjustment_batch_no') or '-'}",
                        size=13,
                        color=GREEN,
                        weight=ft.FontWeight.W_600,
                    ),
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
                        f"此盤點單已作廢。原因：{count.get('void_reason') or '-'}",
                        size=13,
                        color=RED,
                        weight=ft.FontWeight.W_600,
                    ),
                )
            )

        if blind_draft:
            controls.append(
                ft.Container(
                    bgcolor=ORANGE_SOFT,
                    border=ft.border.all(1, ORANGE_BORDER),
                    border_radius=14,
                    padding=14,
                    content=ft.Row(
                        spacing=10,
                        controls=[
                            ft.Icon(ft.Icons.VISIBILITY_OFF_OUTLINED, color=ORANGE, size=20),
                            ft.Text(
                                "盲盤草稿中：帳面庫存與盤盈盤虧已隱藏；送出待審核後才會顯示差異。",
                                size=13,
                                color="#9A4A12",
                                weight=ft.FontWeight.W_600,
                                expand=True,
                            ),
                        ],
                    ),
                )
            )

        if status == "draft" and str(count.get("return_reason") or "").strip():
            controls.append(
                ft.Container(
                    bgcolor=ORANGE_SOFT,
                    border=ft.border.all(1, ORANGE_BORDER),
                    border_radius=14,
                    padding=14,
                    content=ft.Column(
                        spacing=4,
                        controls=[
                            ft.Text(
                                f"此盤點單曾由 {count.get('returned_by_name') or '-'} 退回修改。",
                                size=13,
                                color=ORANGE,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                f"退回原因：{count.get('return_reason') or '-'}",
                                size=13,
                                color="#9A4A12",
                            ),
                        ],
                    ),
                )
            )

        action_buttons: list[ft.Control] = [
            outline_button("關閉", ft.Icons.CLOSE, TEXT_MUTED, close_detail, expand=True),
        ]

        if editable:
            if recycled_count:
                action_buttons.append(
                    stable_button(
                        "前往回用料逐筆盤點",
                        ft.Icons.RECYCLING_OUTLINED,
                        GREEN_BTN,
                        on_click=lambda e, cid=count.get("id"): open_recycled_stocktake_page(str(cid or "")),
                        expand=True,
                        disabled=False,
                    )
                )
            else:
                action_buttons.append(
                    stable_button(
                        "送出待審核" if can_submit else f"尚有 {remaining_items} 筆未盤",
                        ft.Icons.SEND_OUTLINED,
                        ORANGE_BTN,
                        on_click=submit_count_action,
                        expand=True,
                        disabled=state.get("busy") or not can_submit,
                    )
                )

        if can_confirm:
            action_buttons.append(
                outline_button("退回", ft.Icons.REPLY_OUTLINED, ORANGE, toggle_return_form, expand=True, disabled=state.get("busy"))
            )
            action_buttons.append(
                stable_button("確認", ft.Icons.VERIFIED_OUTLINED, GREEN_BTN, on_click=confirm_count_action, expand=True, disabled=state.get("busy"))
            )

        controls.append(ft.Row(spacing=10, controls=action_buttons))

        if can_confirm and state.get("show_return_form"):
            controls.append(
                ft.Container(
                    bgcolor=ORANGE_SOFT,
                    border=ft.border.all(1, ORANGE_BORDER),
                    border_radius=16,
                    padding=14,
                    content=ft.Column(
                        spacing=12,
                        controls=[
                            ft.Row(
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Icon(ft.Icons.REPLY_OUTLINED, color=ORANGE, size=22),
                                    ft.Column(
                                        expand=True,
                                        spacing=2,
                                        controls=[
                                            ft.Text("退回修改", size=16, color=ORANGE, weight=ft.FontWeight.BOLD),
                                            ft.Text("退回後盤點單會回到草稿狀態，可重新修改實盤數；此動作不會影響正式庫存。", size=12, color=TEXT_MUTED),
                                        ],
                                    ),
                                ],
                            ),
                            field_group("退回原因", return_reason_field, True),
                            ft.Row(
                                spacing=10,
                                controls=[
                                    outline_button("取消退回", ft.Icons.CLOSE, TEXT_MUTED, close_return_form, expand=True, disabled=state.get("busy")),
                                    stable_button("確認退回", ft.Icons.REPLY_OUTLINED, ORANGE_BTN, on_click=return_count_action, expand=True, disabled=state.get("busy")),
                                ],
                            ),
                        ],
                    ),
                )
            )

        controls.append(ft.Divider(height=18, color="#EEF2F7"))

        if recycled_count:
            pending_recycled_items = [item for item in recycled_items if not bool(item.get("has_checked"))]
            checked_recycled_items = [item for item in recycled_items if bool(item.get("has_checked"))]

            controls.append(
                section_title(
                    "待核對回用料",
                    f"剩餘 {len(pending_recycled_items)} 筆尚未核對；回用料逐筆核對已移至獨立子頁；請點上方「前往回用料逐筆盤點」。",
                )
            )
            if not recycled_items:
                controls.append(ft.Text("此回用料盤點單沒有明細。", size=14, color=TEXT_MUTED))
            elif not pending_recycled_items:
                controls.append(
                    ft.Container(
                        bgcolor=GREEN_SOFT,
                        border=ft.border.all(1, GREEN_BORDER),
                        border_radius=14,
                        padding=14,
                        content=ft.Row(
                            spacing=10,
                            controls=[
                                ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=GREEN, size=20),
                                ft.Text("所有回用料都已核對。", size=13, color=GREEN, weight=ft.FontWeight.W_600),
                            ],
                        ),
                    )
                )
            else:
                for item in pending_recycled_items:
                    controls.append(build_recycled_pending_item_card(item, editable=editable))

            checked_visible = bool(state.get("show_checked_recycled_items"))
            controls.append(
                ft.Container(
                    bgcolor="#FFFFFF",
                    border=ft.border.all(1, BORDER),
                    border_radius=16,
                    padding=14,
                    content=ft.Column(
                        spacing=12,
                        controls=[
                            ft.Row(
                                spacing=10,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Icon(ft.Icons.DONE_ALL_OUTLINED, size=23, color=GREEN),
                                    ft.Column(
                                        expand=True,
                                        spacing=2,
                                        controls=[
                                            ft.Text(f"已核對回用料：{len(checked_recycled_items)} 筆", size=17, color=TEXT, weight=ft.FontWeight.BOLD),
                                            ft.Text("預設收合，避免已完成項目佔滿畫面。", size=12, color=TEXT_MUTED),
                                        ],
                                    ),
                                    ft.Container(
                                        height=36,
                                        padding=ft.padding.symmetric(horizontal=12),
                                        border_radius=18,
                                        bgcolor=GREEN_SOFT if checked_visible else "#FFFFFF",
                                        border=ft.border.all(1, GREEN_BORDER),
                                        ink=True,
                                        on_click=toggle_checked_recycled_items,
                                        content=ft.Row(
                                            tight=True,
                                            spacing=6,
                                            alignment=ft.MainAxisAlignment.CENTER,
                                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                            controls=[
                                                ft.Icon(ft.Icons.EXPAND_LESS if checked_visible else ft.Icons.EXPAND_MORE, size=17, color=GREEN),
                                                ft.Text("收合" if checked_visible else "顯示", size=13, color=GREEN, weight=ft.FontWeight.W_600),
                                            ],
                                        ),
                                    ),
                                ],
                            ),
                            *(
                                [build_recycled_readonly_item_card(item) for item in checked_recycled_items]
                                if checked_visible
                                else []
                            ),
                        ],
                    ),
                )
            )
        elif not items:
            controls.append(section_title("盤點項目", "此盤點單沒有明細。"))
            controls.append(ft.Text("此盤點單沒有明細。", size=14, color=TEXT_MUTED))
        elif editable:
            pending_items = [item for item in items if not bool(item.get("has_actual"))]
            entered_items = [item for item in items if bool(item.get("has_actual"))]

            controls.append(
                section_title(
                    "待盤點品項",
                    (f"剩餘 {len(pending_items)} 筆尚未輸入實盤包數；盲盤中不顯示帳面與差異。" if blind_draft else f"剩餘 {len(pending_items)} 筆尚未輸入實盤包數；儲存後會移到下方已盤點區。"),
                )
            )

            if not pending_items:
                controls.append(
                    ft.Container(
                        bgcolor=GREEN_SOFT,
                        border=ft.border.all(1, GREEN_BORDER),
                        border_radius=14,
                        padding=14,
                        content=ft.Row(
                            spacing=10,
                            controls=[
                                ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=GREEN, size=20),
                                ft.Text("所有品項都已輸入實盤數，可以送出待審核。", size=13, color=GREEN, weight=ft.FontWeight.W_600),
                            ],
                        ),
                    )
                )
            else:
                for item in pending_items:
                    controls.append(build_item_card(item, editable=not state.get("busy"), hide_system_values=blind_draft))

            entered_visible = bool(state.get("show_entered_items"))
            controls.append(
                ft.Container(
                    bgcolor="#FFFFFF",
                    border=ft.border.all(1, BORDER),
                    border_radius=16,
                    padding=14,
                    content=ft.Column(
                        spacing=12,
                        controls=[
                            ft.Row(
                                spacing=10,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Icon(ft.Icons.DONE_ALL_OUTLINED, size=23, color=GREEN),
                                    ft.Column(
                                        expand=True,
                                        spacing=2,
                                        controls=[
                                            ft.Text(f"已盤點品項：{len(entered_items)} 筆", size=17, color=TEXT, weight=ft.FontWeight.BOLD),
                                            ft.Text("預設收合，避免已完成品項佔滿畫面；草稿狀態仍可展開修改。", size=12, color=TEXT_MUTED),
                                        ],
                                    ),
                                    ft.Container(
                                        height=36,
                                        padding=ft.padding.symmetric(horizontal=12),
                                        border_radius=18,
                                        bgcolor=GREEN_SOFT if entered_visible else "#FFFFFF",
                                        border=ft.border.all(1, GREEN_BORDER),
                                        ink=True,
                                        on_click=toggle_entered_items,
                                        content=ft.Row(
                                            tight=True,
                                            spacing=6,
                                            alignment=ft.MainAxisAlignment.CENTER,
                                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                            controls=[
                                                ft.Icon(ft.Icons.EXPAND_LESS if entered_visible else ft.Icons.EXPAND_MORE, size=17, color=GREEN),
                                                ft.Text("收合" if entered_visible else "顯示", size=13, color=GREEN, weight=ft.FontWeight.W_600),
                                            ],
                                        ),
                                    ),
                                ],
                            ),
                            *(
                                [build_item_card(item, editable=not state.get("busy"), hide_system_values=blind_draft) for item in entered_items]
                                if entered_visible
                                else []
                            ),
                        ],
                    ),
                )
            )
        else:
            controls.append(section_title("盤點項目", "此盤點單已送出或鎖定，以下為完整盤點明細。"))
            for item in items:
                controls.append(build_item_card(item, editable=False))

        if can_void:
            controls.append(ft.Divider(height=18, color="#EEF2F7"))
            if state.get("show_void_form"):
                controls.append(
                    ft.Container(
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
                                                ft.Text("危險操作：作廢盤點單", size=16, color=RED, weight=ft.FontWeight.BOLD),
                                                ft.Text("作廢後不會影響正式庫存，但會保留稽核紀錄；請務必填寫原因。", size=12, color=TEXT_MUTED),
                                            ],
                                        ),
                                    ],
                                ),
                                field_group("作廢原因", void_reason_field, True),
                                ft.Row(
                                    spacing=10,
                                    controls=[
                                        outline_button("取消作廢", ft.Icons.CLOSE, TEXT_MUTED, close_void_form, expand=True, disabled=state.get("busy")),
                                        stable_button("確認作廢", ft.Icons.BLOCK, RED_BTN, on_click=void_count_action, expand=True, disabled=state.get("busy")),
                                    ],
                                ),
                            ],
                        ),
                    )
                )
            else:
                controls.append(
                    ft.Container(
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
                                        ft.Text("需要取消本張草稿或待審核盤點單時，請從這裡作廢。", size=12, color=TEXT_MUTED),
                                    ],
                                ),
                                outline_button("作廢盤點單", ft.Icons.BLOCK, RED, toggle_void_form, disabled=state.get("busy")),
                            ],
                        ),
                    )
                )

        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.border.all(1, BLUE_BORDER),
            border_radius=22,
            padding=20,
            content=ft.Column(spacing=16, controls=controls),
        )

    def build_error_banner() -> ft.Control:
        message = str(state.get("error_message") or "").strip()
        if not message:
            return ft.Container(height=0)
        return ft.Container(
            bgcolor=RED_SOFT,
            border=ft.border.all(1, RED_BORDER),
            border_radius=14,
            padding=14,
            content=ft.Row(
                spacing=10,
                controls=[
                    ft.Icon(ft.Icons.ERROR_OUTLINE, color=RED, size=20),
                    ft.Text(message, size=13, color=RED, expand=True),
                ],
            ),
        )

    def build_page() -> ft.Control:
        controls: list[ft.Control] = [
            build_header(),
            sync_status_banner(),
            build_error_banner(),
            build_summary_cards(),
            build_top_actions(),
            build_create_form(),
            build_in_progress_section(),
            build_detail_panel(),
            build_count_list(),
            ft.Container(height=90),
        ]

        return ft.Container(
            bgcolor=BG,
            width=float("inf"),
            expand=True,
            # main.py shell 已有主要左右留白；此頁不再額外加 left/right padding，
            # 避免像 reports.py 早期版本一樣比其他頁面窄。
            padding=ft.padding.only(top=18, bottom=18),
            content=ft.Column(
                spacing=16,
                controls=controls,
                expand=True,
            ),
        )

    main_host = ft.Container(width=float("inf"), expand=True, content=build_page())

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
            print("stocktake rebuild failed:", repr(ex), flush=True)

    # =====================================================
    # 初始化
    # =====================================================
    try:
        threading.Timer(0.25, lambda: load_counts_background(show_loading=True)).start()
    except Exception:
        load_counts_background(show_loading=True)

    return main_host
