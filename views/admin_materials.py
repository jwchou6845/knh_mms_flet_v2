# =====================================================
# KNH MMS v2
# File: views/admin_materials.py
# File Revision: 2026-05-13-admin-materials-r3
# Status: /admin materials phase 1 implementation - Dropdown compatibility fix
# Last Updated: 2026-05-13 Asia/Taipei
#
# Purpose:
# - /admin/materials 原料與庫存設定頁。
# - 供超級管理員讀取 materials 真實清單、搜尋篩選、新增原料、編輯原料、啟用 / 停用原料。
#
# Major Changes in This Revision:
# - 移除 placeholder，正式讀取 Supabase materials 與 material_stock_view。
# - 顯示啟用 / 停用、低水位、納管庫存與目前庫存狀態。
# - 新增搜尋、分類、類型、供應商、啟用狀態、納管狀態篩選。
# - 新增原料與編輯原料 Dialog，透過 services/admin_service.py 寫入。
# - 啟用 / 停用採確認 Dialog，只更新 materials.is_active，不刪除歷史紀錄。
#
# Notes:
# - Flet 0.84；不使用 page.push_route()。
# - 手機 Web 關鍵按鈕改用 Container 穩定按鈕，避免 Flet Web 按鈕參數相容性造成重建失敗。
# - 背景載入加入 watchdog 與 try/except，避免資料查詢或 UI 重建失敗時永久停在讀取中。
# - 新增原料只建立主檔，不直接建立初始庫存，不覆蓋正式庫存數字。
# - 所有時間顯示由 service 層轉為 Asia/Taipei。
# =====================================================

from __future__ import annotations

import threading
import time
from typing import Any

import flet as ft

from services.admin_service import (
    create_material_from_form,
    load_admin_materials_page_data,
    toggle_material_active,
    update_material_from_form,
)


BG = "#F6F8FB"
CARD_BG = "#FFFFFF"
TEXT = "#1E293B"
TEXT_MUTED = "#64748B"
BORDER = "#E2E8F0"

BLUE = "#2F80ED"
BLUE_BTN = "#4F7FB8"
BLUE_SOFT = "#E5F0FF"
BLUE_BORDER = "#B0D0FF"

PURPLE = "#8B5CF6"
PURPLE_BTN = "#7358B8"
PURPLE_SOFT = "#F3E8FF"
PURPLE_BORDER = "#D8B4FE"

ORANGE = "#F97316"
ORANGE_SOFT = "#FFF7ED"
ORANGE_BORDER = "#FDBA74"

GREEN = "#059669"
GREEN_SOFT = "#ECFDF5"
GREEN_BORDER = "#A7F3D0"

RED = "#DC2626"
RED_SOFT = "#FEE2E2"
RED_BORDER = "#FCA5A5"

YELLOW = "#D97706"
YELLOW_SOFT = "#FEF3C7"
YELLOW_BORDER = "#FDE68A"

MOBILE_WIDTH = 820
TABLE_WIDTH = 1180


def AdminMaterialsContent(page: ft.Page) -> ft.Control:
    if not hasattr(page, "session_data"):
        page.session_data = {}

    state: dict[str, Any] = {
        "loading": True,
        "sync_status": "loading",
        "sync_message": "資料同步中",
        "error_message": "",
        "materials": [],
        "summary": {
            "active_material_count": 0,
            "inactive_material_count": 0,
            "stock_managed_count": 0,
            "low_stock_count": 0,
        },
        "filter_options": {
            "main_categories": [],
            "material_types": [],
            "suppliers": [],
        },
        "generated_at": "-",
        "keyword": "",
        "filter_category": "全部",
        "filter_type": "全部",
        "filter_supplier": "全部",
        "filter_active": "全部",
        "filter_managed": "全部",
        "action_busy": False,
        "load_seq": 0,
    }

    ui_lock = threading.RLock()
    main_host = ft.Container(expand=True)
    root = ft.Container(expand=True, bgcolor=BG, content=main_host)

    # =====================================================
    # Session / navigation / basics
    # =====================================================
    def session_get(key: str, default=None):
        try:
            return page.session_data.get(key, default)
        except Exception:
            return default

    def is_super_admin() -> bool:
        return session_get("role") == "超級管理員"

    def current_user() -> dict[str, Any]:
        return {
            "user_id": session_get("user_id"),
            "user_name": session_get("user_name"),
            "role": session_get("role"),
        }

    def navigate(route: str):
        nav = session_get("_navigate")
        if callable(nav):
            nav(route)
        else:
            page.go(route)

    def safe_update() -> None:
        try:
            with ui_lock:
                page.update()
        except Exception as exc:
            print("admin_materials page.update failed:", repr(exc))

    def show_snack(message: str, success: bool = True) -> None:
        snack = ft.SnackBar(
            content=ft.Text(str(message), color="#FFFFFF", weight=ft.FontWeight.W_600),
            bgcolor=GREEN if success else RED,
            duration=3200,
        )
        try:
            page.overlay.append(snack)
        except Exception:
            pass
        snack.open = True
        safe_update()

    def card(
        content: ft.Control,
        padding: int = 18,
        border_color: str = BORDER,
        bgcolor: str = CARD_BG,
    ) -> ft.Container:
        return ft.Container(
            width=float("inf"),
            bgcolor=bgcolor,
            border=ft.border.all(1, border_color),
            border_radius=18,
            padding=padding,
            content=content,
        )

    def chip(label: str, color: str, bg: str, border: str | None = None) -> ft.Container:
        return ft.Container(
            border_radius=12,
            bgcolor=bg,
            border=ft.border.all(1, border or bg),
            padding=ft.padding.symmetric(horizontal=9, vertical=4),
            content=ft.Text(
                str(label),
                size=12,
                color=color,
                weight=ft.FontWeight.W_600,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        )

    def primary_style(bg: str = BLUE_BTN) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            bgcolor={
                ft.ControlState.DEFAULT: bg,
                ft.ControlState.HOVERED: bg,
                ft.ControlState.PRESSED: bg,
            },
            color={
                ft.ControlState.DEFAULT: "#FFFFFF",
                ft.ControlState.HOVERED: "#FFFFFF",
                ft.ControlState.PRESSED: "#FFFFFF",
            },
            shape=ft.RoundedRectangleBorder(radius=12),
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
            elevation=0,
        )

    def outline_style(color: str = BLUE_BTN, border_color: str = BLUE_BORDER) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            bgcolor={
                ft.ControlState.DEFAULT: "#FFFFFF",
                ft.ControlState.HOVERED: "#F8FAFC",
                ft.ControlState.PRESSED: "#F1F5F9",
            },
            color={
                ft.ControlState.DEFAULT: color,
                ft.ControlState.HOVERED: color,
                ft.ControlState.PRESSED: color,
            },
            side={
                ft.ControlState.DEFAULT: ft.BorderSide(1, border_color),
                ft.ControlState.HOVERED: ft.BorderSide(1, color),
                ft.ControlState.PRESSED: ft.BorderSide(1, color),
            },
            shape=ft.RoundedRectangleBorder(radius=12),
            padding=ft.padding.symmetric(horizontal=14, vertical=11),
        )

    def stable_button_content(
        label: str,
        icon=None,
        text_color: str = BLUE_BTN,
        text_size: int = 14,
        bold: bool = True,
    ) -> ft.Control:
        if icon:
            return ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=7,
                tight=True,
                controls=[
                    ft.Icon(icon, size=18, color=text_color),
                    ft.Text(
                        label,
                        size=text_size,
                        color=text_color,
                        weight=ft.FontWeight.BOLD if bold else ft.FontWeight.W_500,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
            )
        return ft.Text(
            label,
            size=text_size,
            color=text_color,
            weight=ft.FontWeight.BOLD if bold else ft.FontWeight.W_500,
            text_align=ft.TextAlign.CENTER,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

    def stable_button(
        label: str,
        icon=None,
        filled: bool = False,
        color: str = BLUE_BTN,
        border_color: str | None = None,
        on_click=None,
        height: int = 42,
        expand: bool = False,
        min_width: int | None = None,
    ) -> ft.Container:
        bg = color if filled else "#FFFFFF"
        fg = "#FFFFFF" if filled else color
        br = color if filled else (border_color or BLUE_BORDER)

        btn = ft.Container(
            expand=expand,
            height=height,
            width=min_width,
            border_radius=12,
            bgcolor=bg,
            border=ft.border.all(1, br),
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.symmetric(horizontal=13),
            ink=True,
            content=stable_button_content(label, icon, fg),
        )
        btn.disabled = False
        btn.data = {
            "label": label,
            "icon": icon,
            "filled": filled,
            "color": color,
            "border_color": br,
        }

        def handle_click(e):
            if getattr(btn, "disabled", False):
                return
            if callable(on_click):
                on_click(e)

        btn.on_click = handle_click
        return btn

    def set_stable_button_loading(btn, loading: bool, normal_label: str, normal_icon=None) -> None:
        if not btn:
            return
        btn.disabled = bool(loading)
        data = btn.data if isinstance(getattr(btn, "data", None), dict) else {}
        filled = bool(data.get("filled", False))
        color = data.get("color", BLUE_BTN)
        text_color = "#FFFFFF" if filled else color
        if loading:
            btn.content = ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
                tight=True,
                controls=[
                    ft.ProgressRing(width=16, height=16, stroke_width=2, color=text_color),
                    ft.Text("寫入中...", size=14, color=text_color, weight=ft.FontWeight.BOLD),
                ],
            )
            btn.opacity = 0.78
        else:
            btn.content = stable_button_content(normal_label, normal_icon, text_color)
            btn.opacity = 1
        try:
            btn.update()
        except Exception:
            safe_update()

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
            controls=[
                crumb("控制中心", "/admin"),
                ft.Text(">", size=12, color=TEXT_MUTED),
                crumb("原料與庫存設定", None, active=True),
            ],
        )

    # =====================================================
    # Data load / filtering
    # =====================================================
    def set_sync(status: str, message: str) -> None:
        state["sync_status"] = status
        state["sync_message"] = message
        state["loading"] = status == "loading"

    def apply_data(data: dict[str, Any]) -> None:
        state["materials"] = data.get("materials") or []
        state["summary"] = data.get("summary") or state["summary"]
        state["filter_options"] = data.get("filter_options") or state["filter_options"]
        state["generated_at"] = data.get("generated_at") or "-"

        # 若資料異動後原本選項不存在，回到「全部」。
        options = state["filter_options"]
        if state["filter_category"] != "全部" and state["filter_category"] not in options.get("main_categories", []):
            state["filter_category"] = "全部"
        if state["filter_type"] != "全部" and state["filter_type"] not in options.get("material_types", []):
            state["filter_type"] = "全部"
        if state["filter_supplier"] != "全部" and state["filter_supplier"] not in options.get("suppliers", []):
            state["filter_supplier"] = "全部"

    def load_data(show_loading: bool = True) -> None:
        state["load_seq"] = int(state.get("load_seq") or 0) + 1
        current_seq = state["load_seq"]

        if show_loading:
            set_sync("loading", "資料同步中")
            rebuild()

        def watchdog():
            time.sleep(12)
            if state.get("load_seq") != current_seq:
                return
            if not state.get("loading"):
                return
            state["error_message"] = "原料設定資料讀取逾時，請先按重試；若持續發生，請檢查 VM journalctl。"
            set_sync("error", "資料同步逾時")
            rebuild()

        def worker():
            try:
                result = load_admin_materials_page_data()
            except Exception as exc:
                result = None
                print("admin_materials load worker exception:", repr(exc), flush=True)

            if state.get("load_seq") != current_seq:
                return

            if result and result.ok:
                apply_data(result.data or {})
                state["error_message"] = ""
                set_sync("success", "資料已同步")
            elif result:
                apply_data(result.data or {})
                state["error_message"] = result.message or "讀取資料失敗。"
                set_sync("error", "資料同步失敗")
            else:
                state["error_message"] = "原料設定資料讀取失敗，背景載入發生未預期錯誤。"
                set_sync("error", "資料同步失敗")

            rebuild()

        threading.Thread(target=watchdog, daemon=True).start()
        threading.Thread(target=worker, daemon=True).start()

    def material_matches(row: dict[str, Any]) -> bool:
        keyword = str(state.get("keyword") or "").strip().casefold()
        if keyword:
            haystack = " ".join(
                [
                    str(row.get("material_name") or ""),
                    str(row.get("main_category") or ""),
                    str(row.get("material_type") or ""),
                    str(row.get("supplier") or ""),
                    str(row.get("note") or ""),
                ]
            ).casefold()
            if keyword not in haystack:
                return False

        if state["filter_category"] != "全部" and row.get("main_category") != state["filter_category"]:
            return False
        if state["filter_type"] != "全部" and row.get("material_type") != state["filter_type"]:
            return False
        if state["filter_supplier"] != "全部" and row.get("supplier") != state["filter_supplier"]:
            return False

        if state["filter_active"] == "啟用" and not row.get("is_active"):
            return False
        if state["filter_active"] == "停用" and row.get("is_active"):
            return False

        if state["filter_managed"] == "納管" and not row.get("is_stock_managed"):
            return False
        if state["filter_managed"] == "未納管" and row.get("is_stock_managed"):
            return False

        return True

    def filtered_materials() -> list[dict[str, Any]]:
        return [row for row in state["materials"] if material_matches(row)]

    def clear_filters(_=None) -> None:
        state["keyword"] = ""
        state["filter_category"] = "全部"
        state["filter_type"] = "全部"
        state["filter_supplier"] = "全部"
        state["filter_active"] = "全部"
        state["filter_managed"] = "全部"
        rebuild()

    # =====================================================
    # Dialogs / write actions
    # =====================================================
    def close_dialog(dialog: ft.AlertDialog | None = None) -> None:
        if dialog:
            dialog.open = False
        safe_update()

    def open_material_dialog(material: dict[str, Any] | None = None) -> None:
        editing = bool(material)
        raw = material.get("raw") if isinstance(material, dict) else {}
        raw = raw or {}

        name_tf = ft.TextField(
            label="原料名稱 *",
            value=str(material.get("material_name") or "") if editing else "",
            hint_text="例如：PET-南紡",
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE_BTN,
            bgcolor="#FFFFFF",
            filled=True,
        )
        category_tf = ft.TextField(
            label="主分類 *",
            value=str(material.get("main_category") or "") if editing else "",
            hint_text="例如：PET、PA6、輔助母粒、PP",
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE_BTN,
            bgcolor="#FFFFFF",
            filled=True,
        )
        type_tf = ft.TextField(
            label="原料類型 *",
            value=str(material.get("material_type") or "") if editing else "",
            hint_text="例如：未結晶、已結晶、N/A",
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE_BTN,
            bgcolor="#FFFFFF",
            filled=True,
        )
        supplier_tf = ft.TextField(
            label="供應商",
            value=str(material.get("supplier") or "") if editing and material.get("supplier") != "-" else "",
            hint_text="例如：南紡、台塑、中國儀征",
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE_BTN,
            bgcolor="#FFFFFF",
            filled=True,
        )
        bag_tf = ft.TextField(
            label="包重 KG *",
            value=str(raw.get("bag_weight_kg") if editing else ""),
            hint_text="例如：25、950、1000",
            keyboard_type=ft.KeyboardType.NUMBER,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE_BTN,
            bgcolor="#FFFFFF",
            filled=True,
        )
        threshold_tf = ft.TextField(
            label="低水位門檻（包）*",
            value=str(raw.get("low_stock_threshold_bags") if editing else "3"),
            hint_text="例如：3",
            keyboard_type=ft.KeyboardType.NUMBER,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE_BTN,
            bgcolor="#FFFFFF",
            filled=True,
        )
        note_tf = ft.TextField(
            label="備註",
            value=str(raw.get("note") or "") if editing else "",
            hint_text="例如：庫存安全、暫停進貨原因等",
            multiline=True,
            min_lines=2,
            max_lines=4,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE_BTN,
            bgcolor="#FFFFFF",
            filled=True,
        )
        active_sw = ft.Switch(value=bool(material.get("is_active", True)) if editing else True)
        managed_sw = ft.Switch(value=bool(material.get("is_stock_managed", True)) if editing else True)

        saving = {"value": False}

        def collect_form() -> dict[str, Any]:
            return {
                "material_name": name_tf.value,
                "main_category": category_tf.value,
                "material_type": type_tf.value,
                "supplier": supplier_tf.value,
                "bag_weight_kg": bag_tf.value,
                "low_stock_threshold_bags": threshold_tf.value,
                "is_active": active_sw.value,
                "is_stock_managed": managed_sw.value,
                "note": note_tf.value,
            }

        def set_submit_loading(btn, value: bool) -> None:
            saving["value"] = value
            set_stable_button_loading(
                btn,
                value,
                "更新原料" if editing else "新增原料",
                ft.Icons.SAVE_OUTLINED,
            )

        def submit(_=None):
            if saving["value"]:
                return

            submit_btn = submit_button_ref["control"]
            set_submit_loading(submit_btn, True)

            def worker():
                try:
                    if editing:
                        result = update_material_from_form(
                            material_id=str(material.get("id") or ""),
                            form_data=collect_form(),
                            current_user=current_user(),
                        )
                    else:
                        result = create_material_from_form(
                            form_data=collect_form(),
                            current_user=current_user(),
                        )

                    if result.ok:
                        close_dialog(dialog)
                        show_snack(result.message, success=True)
                        load_data(show_loading=False)
                    else:
                        show_snack(result.message, success=False)
                finally:
                    set_submit_loading(submit_btn, False)

            threading.Thread(target=worker, daemon=True).start()

        submit_button_ref: dict[str, Any] = {"control": None}
        submit_button = stable_button(
            "更新原料" if editing else "新增原料",
            icon=ft.Icons.SAVE_OUTLINED,
            filled=True,
            color=BLUE_BTN,
            on_click=submit,
            height=44,
            min_width=118,
        )
        submit_button_ref["control"] = submit_button

        form = ft.Container(
            width=560,
            content=ft.Column(
                tight=True,
                spacing=12,
                controls=[
                    ft.Container(
                        bgcolor=BLUE_SOFT,
                        border=ft.border.all(1, BLUE_BORDER),
                        border_radius=12,
                        padding=12,
                        content=ft.Text(
                            "新增或編輯原料只會更新 materials 主檔，不會直接增加或覆蓋正式庫存。若需建立初始庫存，後續應透過盤點或庫存調整流程處理。",
                            size=12,
                            color=BLUE_BTN,
                        ),
                    ),
                    name_tf,
                    ft.ResponsiveRow(
                        columns=12,
                        spacing=12,
                        run_spacing=12,
                        controls=[
                            ft.Container(col={"xs": 12, "md": 6}, content=category_tf),
                            ft.Container(col={"xs": 12, "md": 6}, content=type_tf),
                            ft.Container(col={"xs": 12, "md": 6}, content=supplier_tf),
                            ft.Container(col={"xs": 12, "md": 6}, content=bag_tf),
                            ft.Container(col={"xs": 12, "md": 6}, content=threshold_tf),
                        ],
                    ),
                    ft.Row(
                        spacing=16,
                        controls=[
                            ft.Row(spacing=6, controls=[active_sw, ft.Text("啟用原料", size=13, color=TEXT)]),
                            ft.Row(spacing=6, controls=[managed_sw, ft.Text("納管庫存", size=13, color=TEXT)]),
                        ],
                    ),
                    note_tf,
                ],
            ),
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("編輯原料" if editing else "新增原料", size=18, color=TEXT, weight=ft.FontWeight.BOLD),
            content=form,
            actions=[
                stable_button("取消", color=TEXT_MUTED, border_color=BORDER, on_click=lambda _: close_dialog(dialog), height=42, min_width=88),
                submit_button,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.overlay.append(dialog)
        dialog.open = True
        safe_update()

    def open_toggle_active_dialog(material: dict[str, Any]) -> None:
        current_active = bool(material.get("is_active"))
        next_active = not current_active
        action_text = "啟用" if next_active else "停用"
        action_color = GREEN if next_active else RED

        busy = {"value": False}

        def submit(_=None):
            if busy["value"]:
                return
            busy["value"] = True
            set_stable_button_loading(confirm_btn, True, f"確認{action_text}", ft.Icons.CHECK_CIRCLE_OUTLINE)

            def worker():
                result = toggle_material_active(
                    material_id=str(material.get("id") or ""),
                    is_active=next_active,
                    current_user=current_user(),
                )
                if result.ok:
                    close_dialog(dialog)
                    show_snack(result.message, success=True)
                    load_data(show_loading=False)
                else:
                    show_snack(result.message, success=False)
                    busy["value"] = False
                    set_stable_button_loading(confirm_btn, False, f"確認{action_text}", ft.Icons.CHECK_CIRCLE_OUTLINE)

            threading.Thread(target=worker, daemon=True).start()

        message = (
            "啟用後，此原料會依納管設定重新出現在日常操作與庫存相關畫面。"
            if next_active
            else "停用後，該原料不會出現在日常打料、入庫與低水位警示中；既有歷史紀錄與報表仍會保留。"
        )

        confirm_btn = stable_button(
            f"確認{action_text}",
            icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
            filled=True,
            color=action_color,
            on_click=submit,
            height=42,
            min_width=116,
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"確定要{action_text}此原料？", size=18, weight=ft.FontWeight.BOLD, color=TEXT),
            content=ft.Container(
                width=420,
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        ft.Text(material.get("material_name") or "-", size=16, color=TEXT, weight=ft.FontWeight.BOLD),
                        ft.Text(message, size=13, color=TEXT_MUTED),
                    ],
                ),
            ),
            actions=[
                stable_button("取消", color=TEXT_MUTED, border_color=BORDER, on_click=lambda _: close_dialog(dialog), height=42, min_width=88),
                confirm_btn,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.overlay.append(dialog)
        dialog.open = True
        safe_update()

    # =====================================================
    # UI blocks
    # =====================================================
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
                        stable_button("返回首頁", icon=ft.Icons.HOME_OUTLINED, filled=True, color=BLUE_BTN, on_click=lambda _: navigate("/"), height=44, min_width=118),
                    ],
                ),
            ),
        )

    def build_header(is_mobile: bool) -> ft.Control:
        status_color = BLUE_BTN
        status_bg = BLUE_SOFT
        status_border = BLUE_BORDER
        status_icon = ft.ProgressRing(width=15, height=15, stroke_width=2, color=status_color)

        if state["sync_status"] == "success":
            status_color = GREEN
            status_bg = GREEN_SOFT
            status_border = GREEN_BORDER
            status_icon = ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=17, color=status_color)
        elif state["sync_status"] == "error":
            status_color = RED
            status_bg = RED_SOFT
            status_border = RED_BORDER
            status_icon = ft.Icon(ft.Icons.ERROR_OUTLINE, size=17, color=status_color)

        title_row = ft.Row(
            spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Container(
                    width=58,
                    height=58,
                    border_radius=16,
                    bgcolor=BLUE_SOFT,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, size=31, color=BLUE_BTN),
                ),
                ft.Column(
                    expand=True,
                    spacing=5,
                    controls=[
                        ft.Text("原料與庫存設定", size=26, weight=ft.FontWeight.BOLD, color=TEXT, max_lines=2),
                        ft.Text("新增、編輯、停用原料，管理低水位、包重與庫存納管設定。", size=14, color=TEXT_MUTED, max_lines=3),
                    ],
                ),
                stable_button(
                    "新增原料",
                    icon=ft.Icons.ADD,
                    filled=True,
                    color=BLUE_BTN,
                    on_click=lambda _: open_material_dialog(),
                    height=44,
                    min_width=118,
                ) if not is_mobile else ft.Container(),
            ],
        )

        status_badge = ft.Container(
            height=34,
            border_radius=17,
            bgcolor=status_bg,
            border=ft.border.all(1, status_border),
            alignment=ft.Alignment(0, 0),
            content=ft.Row(
                spacing=7,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    status_icon,
                    ft.Text(state["sync_message"], size=12, color=status_color, weight=ft.FontWeight.W_600),
                ],
            ),
        )

        controls = [breadcrumb(), title_row, status_badge]
        if state.get("error_message"):
            controls.append(
                card(
                    padding=12,
                    border_color=RED_BORDER,
                    bgcolor=RED_SOFT,
                    content=ft.Text(state["error_message"], size=13, color=RED, weight=ft.FontWeight.W_600),
                )
            )

        if is_mobile:
            controls.append(
                stable_button(
                    "新增原料",
                    icon=ft.Icons.ADD,
                    filled=True,
                    color=BLUE_BTN,
                    on_click=lambda _: open_material_dialog(),
                    height=44,
                    expand=True,
                )
            )

        return ft.Column(spacing=12, controls=controls)

    def build_summary_card(title: str, value: str, icon, color: str, bg: str, border: str) -> ft.Control:
        return card(
            padding=15,
            border_color=border,
            content=ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=48,
                        height=48,
                        border_radius=14,
                        bgcolor=bg,
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(icon, color=color, size=25),
                    ),
                    ft.Column(
                        spacing=2,
                        controls=[
                            ft.Text(title, size=12, color=TEXT_MUTED),
                            ft.Text(value, size=24, color=TEXT, weight=ft.FontWeight.BOLD),
                        ],
                    ),
                ],
            ),
        )

    def build_summary_cards(is_mobile: bool) -> ft.Control:
        summary = state["summary"] or {}
        cards = [
            build_summary_card("啟用原料", str(summary.get("active_material_count", 0)), ft.Icons.CHECK_CIRCLE_OUTLINE, BLUE_BTN, BLUE_SOFT, BLUE_BORDER),
            build_summary_card("停用原料", str(summary.get("inactive_material_count", 0)), ft.Icons.PAUSE_CIRCLE_OUTLINE, ORANGE, ORANGE_SOFT, ORANGE_BORDER),
            build_summary_card("低水位品項", str(summary.get("low_stock_count", 0)), ft.Icons.WARNING_AMBER_ROUNDED, RED, RED_SOFT, RED_BORDER),
            build_summary_card("納管庫存", str(summary.get("stock_managed_count", 0)), ft.Icons.VERIFIED_OUTLINED, GREEN, GREEN_SOFT, GREEN_BORDER),
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

    def dropdown_filter(label: str, value_key: str, values: list[str], icon) -> ft.Control:
        options = [ft.dropdown.Option("全部")] + [ft.dropdown.Option(v) for v in values]
        current_value = state.get(value_key, "全部")
        if current_value not in ["全部"] + values:
            current_value = "全部"

        def on_change(e):
            state[value_key] = e.control.value or "全部"
            rebuild()

        # Flet 0.84 VM 相容性：
        # 目前部署環境的 ft.Dropdown.__init__() 不接受 on_change 關鍵字參數，
        # 必須先建立控制項，再指定 dd.on_change，否則頁面重建會失敗並停在讀取中。
        dd = ft.Dropdown(
            label=label,
            value=current_value,
            options=options,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE_BTN,
            bgcolor="#FFFFFF",
            filled=True,
            text_size=13,
        )
        dd.on_change = on_change
        return dd

    def build_filter_bar(is_mobile: bool) -> ft.Control:
        options = state["filter_options"]

        keyword_tf = ft.TextField(
            label="搜尋",
            value=state.get("keyword", ""),
            hint_text="搜尋原料名稱、供應商、備註...",
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE_BTN,
            bgcolor="#FFFFFF",
            filled=True,
            on_change=lambda e: set_keyword(e.control.value),
        )

        def set_active_filter(value: str):
            state["filter_active"] = value
            rebuild()

        def set_managed_filter(value: str):
            state["filter_managed"] = value
            rebuild()

        def filter_chip(label: str, active: bool, on_click, color: str = BLUE_BTN, bg: str = BLUE_SOFT):
            return ft.Container(
                height=36,
                border_radius=18,
                bgcolor=bg if active else "#FFFFFF",
                border=ft.border.all(1, color if active else BORDER),
                padding=ft.padding.symmetric(horizontal=12),
                alignment=ft.Alignment(0, 0),
                ink=True,
                on_click=on_click,
                content=ft.Text(
                    label,
                    size=12,
                    color=color if active else TEXT_MUTED,
                    weight=ft.FontWeight.BOLD if active else ft.FontWeight.W_500,
                ),
            )

        def set_keyword(value: str):
            state["keyword"] = value or ""
            rebuild()

        filter_controls = [
            ft.Container(col={"xs": 12, "md": 3}, content=dropdown_filter("主分類", "filter_category", options.get("main_categories", []), ft.Icons.CATEGORY_OUTLINED)),
            ft.Container(col={"xs": 12, "md": 3}, content=dropdown_filter("原料類型", "filter_type", options.get("material_types", []), ft.Icons.LABEL_OUTLINE)),
            ft.Container(col={"xs": 12, "md": 3}, content=dropdown_filter("供應商", "filter_supplier", options.get("suppliers", []), ft.Icons.BUSINESS_OUTLINED)),
            ft.Container(col={"xs": 12, "md": 3}, content=keyword_tf),
        ]

        result_count = len(filtered_materials())
        total_count = len(state.get("materials") or [])

        return card(
            padding=16,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.FILTER_ALT_OUTLINED, size=22, color=BLUE_BTN),
                            ft.Column(
                                expand=True,
                                spacing=2,
                                controls=[
                                    ft.Text("搜尋與篩選", size=16, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ft.Text(f"目前顯示 {result_count} / {total_count} 筆。", size=12, color=TEXT_MUTED),
                                ],
                            ),
                            stable_button("清除條件", icon=ft.Icons.CLOSE, color=RED, border_color=RED_BORDER, on_click=clear_filters, height=40, min_width=108),
                        ],
                    ),
                    ft.ResponsiveRow(columns=12, spacing=10, run_spacing=10, controls=filter_controls),
                    ft.Column(
                        spacing=8,
                        controls=[
                            ft.Text("啟用狀態", size=12, color=TEXT_MUTED, weight=ft.FontWeight.W_600),
                            ft.Row(
                                scroll=ft.ScrollMode.AUTO,
                                spacing=8,
                                controls=[
                                    filter_chip("全部", state["filter_active"] == "全部", lambda _: set_active_filter("全部")),
                                    filter_chip("啟用", state["filter_active"] == "啟用", lambda _: set_active_filter("啟用"), GREEN, GREEN_SOFT),
                                    filter_chip("停用", state["filter_active"] == "停用", lambda _: set_active_filter("停用"), ORANGE, ORANGE_SOFT),
                                ],
                            ),
                            ft.Text("庫存納管", size=12, color=TEXT_MUTED, weight=ft.FontWeight.W_600),
                            ft.Row(
                                scroll=ft.ScrollMode.AUTO,
                                spacing=8,
                                controls=[
                                    filter_chip("全部", state["filter_managed"] == "全部", lambda _: set_managed_filter("全部")),
                                    filter_chip("納管", state["filter_managed"] == "納管", lambda _: set_managed_filter("納管"), BLUE_BTN, BLUE_SOFT),
                                    filter_chip("未納管", state["filter_managed"] == "未納管", lambda _: set_managed_filter("未納管"), PURPLE_BTN, PURPLE_SOFT),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

    def status_badges(row: dict[str, Any]) -> ft.Control:
        active_badge = chip(
            row.get("active_label") or "-",
            GREEN if row.get("is_active") else ORANGE,
            GREEN_SOFT if row.get("is_active") else ORANGE_SOFT,
            GREEN_BORDER if row.get("is_active") else ORANGE_BORDER,
        )
        managed_badge = chip(
            row.get("stock_managed_label") or "-",
            BLUE_BTN if row.get("is_stock_managed") else TEXT_MUTED,
            BLUE_SOFT if row.get("is_stock_managed") else "#F1F5F9",
            BLUE_BORDER if row.get("is_stock_managed") else BORDER,
        )
        low_badge = chip(
            row.get("low_stock_label") or "-",
            RED if row.get("is_low_stock") else GREEN,
            RED_SOFT if row.get("is_low_stock") else GREEN_SOFT,
            RED_BORDER if row.get("is_low_stock") else GREEN_BORDER,
        )
        return ft.Row(wrap=True, spacing=6, run_spacing=6, controls=[active_badge, managed_badge, low_badge])

    def table_cell(text: Any, width: int, color: str = TEXT, weight=None, align: ft.TextAlign = ft.TextAlign.LEFT, max_lines: int = 1) -> ft.Container:
        return ft.Container(
            width=width,
            padding=ft.padding.only(right=8),
            alignment=ft.Alignment(1, 0) if align == ft.TextAlign.RIGHT else ft.Alignment(-1, 0),
            content=ft.Text(
                str(text if text not in [None, ""] else "-"),
                size=13,
                color=color,
                weight=weight,
                text_align=align,
                max_lines=max_lines,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        )

    def table_status_cell(row: dict[str, Any]) -> ft.Container:
        return ft.Container(width=240, padding=ft.padding.only(right=8), content=status_badges(row))

    def table_action_cell(row: dict[str, Any]) -> ft.Container:
        return ft.Container(
            width=170,
            content=ft.Row(
                spacing=8,
                controls=[
                    stable_button("編輯", icon=ft.Icons.EDIT_OUTLINED, color=BLUE_BTN, border_color=BLUE_BORDER, on_click=lambda _, current=row: open_material_dialog(current), height=40, min_width=74),
                    stable_button("停用" if row.get("is_active") else "啟用", color=RED if row.get("is_active") else GREEN, border_color=RED_BORDER if row.get("is_active") else GREEN_BORDER, on_click=lambda _, current=row: open_toggle_active_dialog(current), height=40, min_width=70),
                ],
            ),
        )

    def table_row(row: dict[str, Any] | None = None, header: bool = False) -> ft.Container:
        row = row or {}
        bg = "#F8FAFC" if header else "#FFFFFF"
        text_color = TEXT_MUTED if header else TEXT
        weight = ft.FontWeight.W_700 if header else None
        border = None if header else ft.border.only(bottom=ft.BorderSide(1, "#EEF2F7"))

        controls: list[ft.Control]
        if header:
            controls = [
                table_cell("原料名稱", 190, text_color, weight),
                table_cell("分類", 90, text_color, weight),
                table_cell("類型", 90, text_color, weight),
                table_cell("供應商", 100, text_color, weight),
                table_cell("包重", 90, text_color, weight, ft.TextAlign.RIGHT),
                table_cell("低水位", 90, text_color, weight, ft.TextAlign.RIGHT),
                table_cell("目前庫存", 110, text_color, weight, ft.TextAlign.RIGHT),
                table_cell("狀態", 240, text_color, weight),
                table_cell("最後更新", 130, text_color, weight),
                table_cell("操作", 170, text_color, weight),
            ]
        else:
            controls = [
                table_cell(row.get("material_name"), 190, TEXT, ft.FontWeight.W_600),
                table_cell(row.get("main_category"), 90),
                table_cell(row.get("material_type"), 90),
                table_cell(row.get("supplier"), 100),
                table_cell(row.get("bag_weight_label"), 90, align=ft.TextAlign.RIGHT),
                table_cell(row.get("low_stock_threshold_label"), 90, align=ft.TextAlign.RIGHT),
                table_cell(row.get("stock_label"), 110, RED if row.get("is_low_stock") else TEXT, align=ft.TextAlign.RIGHT),
                table_status_cell(row),
                table_cell(row.get("updated_at_label"), 130, TEXT_MUTED),
                table_action_cell(row),
            ]

        return ft.Container(
            width=TABLE_WIDTH,
            bgcolor=bg,
            border=border,
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            content=ft.Row(spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=controls),
        )

    def build_desktop_table(rows: list[dict[str, Any]]) -> ft.Control:
        table_rows: list[ft.Control] = [table_row(header=True)]
        if rows:
            table_rows.extend([table_row(row) for row in rows])
        else:
            table_rows.append(
                ft.Container(
                    width=TABLE_WIDTH,
                    padding=24,
                    content=ft.Text("目前沒有符合條件的原料資料。", size=14, color=TEXT_MUTED),
                )
            )

        return card(
            padding=0,
            content=ft.Column(
                spacing=0,
                controls=[
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=18, vertical=14),
                        content=ft.Row(
                            controls=[
                                ft.Column(
                                    expand=True,
                                    spacing=3,
                                    controls=[
                                        ft.Text("原料清單", size=18, color=TEXT, weight=ft.FontWeight.BOLD),
                                        ft.Text("左右滑動可查看完整欄位與操作。", size=12, color=TEXT_MUTED),
                                    ],
                                ),
                                ft.Text(f"更新：{state.get('generated_at') or '-'}", size=12, color=TEXT_MUTED),
                            ],
                        ),
                    ),
                    ft.Row(
                        scroll=ft.ScrollMode.AUTO,
                        controls=[ft.Container(width=TABLE_WIDTH, content=ft.Column(spacing=0, controls=table_rows))],
                    ),
                ],
            ),
        )

    def build_mobile_card(row: dict[str, Any]) -> ft.Control:
        return card(
            padding=14,
            border_color=RED_BORDER if row.get("is_low_stock") else BORDER,
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
                                border_radius=14,
                                bgcolor=BLUE_SOFT if row.get("is_active") else "#F1F5F9",
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, color=BLUE_BTN if row.get("is_active") else TEXT_MUTED, size=23),
                            ),
                            ft.Column(
                                expand=True,
                                spacing=3,
                                controls=[
                                    ft.Text(row.get("material_name") or "-", size=16, color=TEXT, weight=ft.FontWeight.BOLD, max_lines=2),
                                    ft.Text(f"{row.get('main_category') or '-'}｜{row.get('material_type') or '-'}｜{row.get('supplier') or '-'}", size=12, color=TEXT_MUTED, max_lines=2),
                                ],
                            ),
                        ],
                    ),
                    status_badges(row),
                    ft.Row(
                        spacing=14,
                        controls=[
                            ft.Column(spacing=2, controls=[ft.Text("包重", size=11, color=TEXT_MUTED), ft.Text(row.get("bag_weight_label") or "-", size=13, color=TEXT)]),
                            ft.Column(spacing=2, controls=[ft.Text("低水位", size=11, color=TEXT_MUTED), ft.Text(row.get("low_stock_threshold_label") or "-", size=13, color=TEXT)]),
                            ft.Column(spacing=2, controls=[ft.Text("目前庫存", size=11, color=TEXT_MUTED), ft.Text(row.get("stock_label") or "-", size=13, color=RED if row.get("is_low_stock") else TEXT)]),
                        ],
                    ),
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.Container(expand=True, content=stable_button("編輯", icon=ft.Icons.EDIT_OUTLINED, color=BLUE_BTN, border_color=BLUE_BORDER, on_click=lambda _, current=row: open_material_dialog(current), height=40, min_width=74)),
                            ft.Container(expand=True, content=stable_button("停用" if row.get("is_active") else "啟用", color=RED if row.get("is_active") else GREEN, border_color=RED_BORDER if row.get("is_active") else GREEN_BORDER, on_click=lambda _, current=row: open_toggle_active_dialog(current), height=40, min_width=70)),
                        ],
                    ),
                ],
            ),
        )

    def build_mobile_list(rows: list[dict[str, Any]]) -> ft.Control:
        if not rows:
            return card(padding=18, content=ft.Text("目前沒有符合條件的原料資料。", size=14, color=TEXT_MUTED))
        return ft.Column(spacing=12, controls=[build_mobile_card(row) for row in rows])

    def build_materials_content(is_mobile: bool) -> ft.Control:
        rows = filtered_materials()
        if is_mobile:
            return build_mobile_list(rows)
        return build_desktop_table(rows)

    def build_loading() -> ft.Control:
        return ft.Container(
            expand=True,
            alignment=ft.Alignment(0, 0),
            content=ft.Column(
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
                controls=[
                    ft.ProgressRing(width=34, height=34, stroke_width=3, color=BLUE_BTN),
                    ft.Text("正在讀取原料設定...", size=14, color=TEXT_MUTED),
                ],
            ),
        )

    def build_layout() -> ft.Control:
        if not is_super_admin():
            return build_access_denied()

        width = page.width or 430
        is_mobile = width < MOBILE_WIDTH

        if state["loading"] and not state.get("materials"):
            return ft.Container(
                expand=True,
                bgcolor=BG,
                padding=ft.padding.only(left=20, right=20, top=18, bottom=18),
                content=ft.Column(spacing=16, controls=[breadcrumb(), build_loading()]),
            )

        return ft.Container(
            expand=True,
            bgcolor=BG,
            padding=ft.padding.only(left=20 if is_mobile else 24, right=20 if is_mobile else 24, top=18, bottom=18),
            content=ft.Column(
                expand=True,
                scroll=ft.ScrollMode.AUTO,
                spacing=16,
                controls=[
                    build_header(is_mobile),
                    build_summary_cards(is_mobile),
                    build_filter_bar(is_mobile),
                    build_materials_content(is_mobile),
                    ft.Container(height=90),
                ],
            ),
        )

    def rebuild() -> None:
        try:
            with ui_lock:
                main_host.content = build_layout()
                try:
                    main_host.update()
                except Exception:
                    page.update()
        except Exception as exc:
            print("admin_materials rebuild failed:", repr(exc))

    # 初始畫面與背景載入
    main_host.content = build_layout()
    if is_super_admin():
        load_data(show_loading=False)

    return root
