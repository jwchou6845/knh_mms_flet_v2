# =====================================================
# KNH MMS v2
# File: views/admin_materials.py
# File Revision: 2026-05-13-admin-materials-r8
# Status: /admin materials phase 1 implementation - inline form UX fix
# Last Updated: 2026-05-13 Asia/Taipei
#
# Purpose:
# - /admin/materials 原料與庫存設定頁。
# - 供超級管理員讀取 materials 真實清單、搜尋篩選、新增原料、編輯原料、啟用 / 停用原料。
#
# Major Changes in This Revision:
# - 編輯表單移除「啟用原料」開關，啟用 / 停用統一由原料清單按鈕處理，避免同一欄位有兩種入口造成混淆。
# - 點擊新增 / 編輯 / 停用 / 啟用後，頁面會自動捲到上方的頁內表單或確認卡，避免使用者找不到展開區。
# - 篩選區的啟用狀態 / 庫存納管選項改為較小 segmented chips，降低手機版高度占用。
# - 原料列表區補上「篩選後原料清單」標題，明確標示下方資料是目前條件篩選結果。
# - 延續 r7：不再使用浮層 modal，所有新增 / 編輯 / 啟用停用都採頁內展開式表單卡片。
#
# Notes:
# - Flet 0.84；不使用 page.push_route()。
# - Dropdown 不使用 on_change 建構子參數；篩選採「套用篩選」按鈕集中更新。
# - 新增原料只建立 materials 主檔，不直接建立初始庫存，不覆蓋正式庫存數字。
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

BLUE_BTN = "#4F7FB8"
BLUE_SOFT = "#E5F0FF"
BLUE_BORDER = "#B0D0FF"

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

MOBILE_WIDTH = 820
TABLE_WIDTH = 1260


def AdminMaterialsContent(page: ft.Page) -> ft.Control:
    if not hasattr(page, "session_data"):
        page.session_data = {}

    state: dict[str, Any] = {
        "loading": True,
        "sync_status": "loading",
        "sync_message": "資料同步中",
        "sync_badge_visible": True,
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
        "load_seq": 0,
        "modal_open": False,
        "active_form": None,
        "editing_material": None,
        "confirm_material": None,
        "scroll_to_top_pending": False,
    }

    ui_lock = threading.RLock()
    action_lock = threading.Lock()

    main_host = ft.Container(expand=True)
    root_stack = ft.Stack(expand=True, controls=[main_host])
    root = ft.Container(expand=True, bgcolor=BG, content=root_stack)
    modal_ref: dict[str, ft.Control | None] = {"control": None}
    layout_scroll_ref: dict[str, ft.Control | None] = {"control": None}

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
            print("admin_materials page.update failed:", repr(exc), flush=True)

    def request_scroll_to_top() -> None:
        """
        新增 / 編輯 / 啟用停用皆在頁面上方展開卡片。
        若使用者從原料清單很下方點擊操作，下一次 rebuild 後自動捲回頂部，
        避免第一次使用者找不到展開的表單或確認卡。
        """
        state["scroll_to_top_pending"] = True

    def run_pending_scroll_to_top() -> None:
        if not state.get("scroll_to_top_pending"):
            return
        state["scroll_to_top_pending"] = False
        target = layout_scroll_ref.get("control")
        if not target:
            return

        async def do_scroll():
            try:
                await target.scroll_to(offset=0, duration=320)
            except Exception as exc:
                print("admin_materials scroll_to_top failed:", repr(exc), flush=True)

        try:
            page.run_task(do_scroll)
        except Exception as exc:
            print("admin_materials run_task scroll failed:", repr(exc), flush=True)

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
        disabled: bool = False,
    ) -> ft.Container:
        bg = color if filled else "#FFFFFF"
        fg = "#FFFFFF" if filled else color
        br = color if filled else (border_color or BLUE_BORDER)

        btn = ft.Container(
            expand=expand,
            height=height,
            width=min_width,
            border_radius=12,
            bgcolor="#F1F5F9" if disabled else bg,
            border=ft.border.all(1, BORDER if disabled else br),
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.symmetric(horizontal=13),
            ink=not disabled,
            content=stable_button_content(label, icon, TEXT_MUTED if disabled else fg),
            opacity=0.72 if disabled else 1,
        )
        btn.disabled = bool(disabled)
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
    # Custom modal
    # =====================================================
    def close_dialog(_=None) -> None:
        modal_layer = modal_ref.get("control")
        if modal_layer and modal_layer in root_stack.controls:
            root_stack.controls.remove(modal_layer)
        modal_ref["control"] = None
        state["modal_open"] = False
        safe_update()

    def open_dialog(title: str, content: ft.Control, actions: list[ft.Control], width: int = 560) -> None:
        """
        本頁自製 modal。

        r6 修正：
        - 不讓內容捲動區吃掉整張 modal 高度，避免底部出現大灰框。
        - actions 固定在 modal 底部且一定可見。
        - 手機寬度下表單區可捲動，但底部取消 / 儲存按鈕不被擠出。
        """
        close_dialog()

        page_width = page.width or 420
        page_height = page.height or 760
        is_mobile_modal = page_width < MOBILE_WIDTH

        card_width = min(width, max(310, page_width - 36))

        if is_mobile_modal:
            # 手機 Web 的 page.height 可能偏大或偏小，取保守高度，確保底部按鈕露出。
            max_card_height = min(max(500, page_height - 150), 680)
            content_height = max(260, max_card_height - 205)
            modal_padding = ft.padding.symmetric(horizontal=18, vertical=24)
        else:
            max_card_height = min(max(520, page_height - 120), 720)
            content_height = max(300, max_card_height - 180)
            modal_padding = ft.padding.all(18)

        action_row = ft.Container(
            bgcolor="#FFFFFF",
            padding=ft.padding.only(top=10),
            border=ft.border.only(top=ft.BorderSide(1, BORDER)),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.END,
                spacing=10,
                wrap=True,
                controls=actions,
            ),
        )

        modal_card = ft.Container(
            width=card_width,
            height=max_card_height,
            bgcolor="#FFFFFF",
            border_radius=22,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            padding=18,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Text(title, size=20 if is_mobile_modal else 18, color=TEXT, weight=ft.FontWeight.BOLD),
                    ft.Container(
                        height=content_height,
                        bgcolor="#FFFFFF",
                        content=ft.Column(
                            scroll=ft.ScrollMode.AUTO,
                            spacing=0,
                            controls=[content],
                        ),
                    ),
                    action_row,
                ],
            ),
        )

        modal_layer = ft.Container(
            expand=True,
            bgcolor="#99000000",
            alignment=ft.Alignment(0, 0),
            padding=modal_padding,
            content=modal_card,
        )

        modal_ref["control"] = modal_layer
        state["modal_open"] = True
        root_stack.controls.append(modal_layer)
        safe_update()

    # =====================================================
    # Data load / filtering
    # =====================================================
    def set_sync(status: str, message: str, visible: bool = True) -> None:
        state["sync_status"] = status
        state["sync_message"] = message
        state["sync_badge_visible"] = visible
        state["loading"] = status == "loading"

    def hide_sync_badge_later(delay_seconds: float = 3.0) -> None:
        def worker():
            time.sleep(delay_seconds)
            if state.get("sync_status") == "success":
                state["sync_badge_visible"] = False
                rebuild()
        threading.Thread(target=worker, daemon=True).start()

    def apply_data(data: dict[str, Any]) -> None:
        state["materials"] = data.get("materials") or []
        state["summary"] = data.get("summary") or state["summary"]
        state["filter_options"] = data.get("filter_options") or state["filter_options"]
        state["generated_at"] = data.get("generated_at") or "-"

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
                set_sync("success", "資料已同步", visible=True)
            elif result:
                apply_data(result.data or {})
                state["error_message"] = result.message or "讀取資料失敗。"
                set_sync("error", "資料同步失敗")
            else:
                state["error_message"] = "原料設定資料讀取失敗，背景載入發生未預期錯誤。"
                set_sync("error", "資料同步失敗")

            rebuild()
            if result and result.ok:
                hide_sync_badge_later(3.0)

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
    def make_field(
        label: str,
        value: Any = "",
        hint: str = "",
        multiline: bool = False,
        keyboard_type=None,
    ) -> ft.TextField:
        # 欄位標題由 field_block / compact_filter_field 顯示；TextField 本身不放 label，
        # 避免手機 Web 浮動 label 不顯示或被遮住。
        return ft.TextField(
            value="" if value is None else str(value),
            hint_text=hint or label,
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
            height=None if multiline else 54,
            width=float("inf"),
            content_padding=ft.padding.symmetric(horizontal=12, vertical=11),
        )


    def field_block(label: str, field: ft.Control) -> ft.Control:
        """
        手機 Web 穩定顯示欄位標題。
        Flet TextField label 在部分 Web/手機環境不一定穩定浮出，
        因此表單一律在 TextField 外層顯示明確標題。
        """
        return ft.Column(
            tight=True,
            spacing=6,
            controls=[
                ft.Text(label, size=13, color=TEXT, weight=ft.FontWeight.W_600),
                field,
            ],
        )

    def switch_block(label: str, switch: ft.Switch) -> ft.Control:
        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.border.all(1, BORDER),
            border_radius=12,
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[switch, ft.Text(label, size=14, color=TEXT, weight=ft.FontWeight.W_500)],
            ),
        )

    def close_inline_panel(_=None) -> None:
        state["active_form"] = None
        state["editing_material"] = None
        state["confirm_material"] = None
        rebuild()

    def open_material_dialog(material: dict[str, Any] | None = None) -> None:
        # r7：不再開浮層 modal，改為頁內展開式表單卡片。
        # 這樣可以避開手機 Web 遮罩灰框、底部按鈕被底部導覽列壓住的問題。
        state["active_form"] = "edit" if material else "create"
        state["editing_material"] = material or None
        state["confirm_material"] = None
        request_scroll_to_top()
        rebuild()

    def build_material_form_panel() -> ft.Control:
        editing = state.get("active_form") == "edit"
        material = state.get("editing_material") or {}
        raw = material.get("raw") if isinstance(material, dict) else {}
        raw = raw or {}

        name_tf = make_field("原料名稱 *", material.get("material_name") if editing else "", "例如：PET-南紡")
        category_tf = make_field("主分類 *", material.get("main_category") if editing else "", "例如：PET、PA6、輔助母粒、PP")
        type_tf = make_field("原料類型 *", material.get("material_type") if editing else "", "例如：未結晶、已結晶、N/A")
        supplier_tf = make_field("供應商", material.get("supplier") if editing and material.get("supplier") != "-" else "", "例如：南紡、台塑、中國儀征")
        bag_tf = make_field("包重 KG *", raw.get("bag_weight_kg") if editing else "", "例如：25、950、1000", keyboard_type=ft.KeyboardType.NUMBER)
        threshold_tf = make_field("低水位門檻（包）*", raw.get("low_stock_threshold_bags") if editing else "3", "例如：3", keyboard_type=ft.KeyboardType.NUMBER)
        note_tf = make_field("備註", raw.get("note") if editing else "", "例如：庫存安全、暫停進貨原因等", multiline=True)
        managed_sw = ft.Switch(value=bool(material.get("is_stock_managed", True)) if editing else True)

        saving = {"value": False}
        submit_button_ref: dict[str, Any] = {"control": None}

        def collect_form() -> dict[str, Any]:
            return {
                "material_name": name_tf.value,
                "main_category": category_tf.value,
                "material_type": type_tf.value,
                "supplier": supplier_tf.value,
                "bag_weight_kg": bag_tf.value,
                "low_stock_threshold_bags": threshold_tf.value,
                # 啟用 / 停用統一由原料清單上的按鈕處理。
                # 編輯表單不再顯示「啟用原料」開關，避免與「停用 / 啟用」操作重複。
                "is_active": bool(material.get("is_active", True)) if editing else True,
                "is_stock_managed": managed_sw.value,
                "note": note_tf.value,
            }

        def set_submit_loading(value: bool) -> None:
            saving["value"] = value
            set_stable_button_loading(
                submit_button_ref["control"],
                value,
                "更新原料" if editing else "新增原料",
                ft.Icons.SAVE_OUTLINED,
            )

        def submit(_=None):
            if saving["value"]:
                return
            if not action_lock.acquire(blocking=False):
                show_snack("資料寫入中，請稍候。", success=False)
                return

            set_submit_loading(True)

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
                        state["active_form"] = None
                        state["editing_material"] = None
                        state["confirm_material"] = None
                        show_snack(result.message, success=True)
                        load_data(show_loading=False)
                    else:
                        show_snack(result.message, success=False)
                        set_submit_loading(False)
                except Exception as exc:
                    show_snack(f"寫入原料失敗：{exc}", success=False)
                    set_submit_loading(False)
                finally:
                    try:
                        action_lock.release()
                    except Exception:
                        pass

            threading.Thread(target=worker, daemon=True).start()

        submit_button = stable_button(
            "更新原料" if editing else "新增原料",
            icon=ft.Icons.SAVE_OUTLINED,
            filled=True,
            color=BLUE_BTN,
            on_click=submit,
            height=48,
            expand=True,
        )
        submit_button_ref["control"] = submit_button

        title = f"編輯原料：{material.get('material_name') or '-'}" if editing else "新增原料"
        subtitle = "編輯主檔不會改變啟用狀態；若需停用或啟用，請使用原料清單上的狀態按鈕。" if editing else "新增 materials 主檔，不直接增加或覆蓋正式庫存。"

        return card(
            padding=18,
            border_color=BLUE_BORDER,
            bgcolor="#FFFFFF",
            content=ft.Column(
                spacing=14,
                controls=[
                    ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        spacing=12,
                        controls=[
                            ft.Container(
                                width=48,
                                height=48,
                                border_radius=14,
                                bgcolor=BLUE_SOFT,
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(ft.Icons.EDIT_NOTE_OUTLINED if editing else ft.Icons.ADD_BOX_OUTLINED, size=25, color=BLUE_BTN),
                            ),
                            ft.Column(
                                expand=True,
                                spacing=3,
                                controls=[
                                    ft.Text(title, size=22, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ft.Text(subtitle, size=13, color=TEXT_MUTED, max_lines=3),
                                ],
                            ),
                        ],
                    ),
                    ft.Container(
                        bgcolor=BLUE_SOFT,
                        border=ft.border.all(1, BLUE_BORDER),
                        border_radius=12,
                        padding=12,
                        content=ft.Text(
                            "若需建立初始庫存，後續應透過盤點或庫存調整流程處理。停用原料不會刪除歷史紀錄。",
                            size=12,
                            color=BLUE_BTN,
                        ),
                    ),
                    ft.ResponsiveRow(
                        columns=12,
                        spacing=12,
                        run_spacing=12,
                        controls=[
                            ft.Container(col={"xs": 12, "md": 6}, content=field_block("原料名稱 *", name_tf)),
                            ft.Container(col={"xs": 6, "md": 3}, content=field_block("主分類 *", category_tf)),
                            ft.Container(col={"xs": 6, "md": 3}, content=field_block("原料類型 *", type_tf)),
                            ft.Container(col={"xs": 12, "md": 4}, content=field_block("供應商", supplier_tf)),
                            ft.Container(col={"xs": 6, "md": 4}, content=field_block("包重 KG *", bag_tf)),
                            ft.Container(col={"xs": 6, "md": 4}, content=field_block("低水位門檻（包）*", threshold_tf)),
                        ],
                    ),
                    ft.Container(
                        content=switch_block("納管庫存", managed_sw),
                    ),
                    field_block("備註", note_tf),
                    ft.ResponsiveRow(
                        columns=12,
                        spacing=10,
                        run_spacing=10,
                        controls=[
                            ft.Container(col={"xs": 6, "md": 6}, content=stable_button("取消", icon=ft.Icons.CLOSE, color=TEXT_MUTED, border_color=BORDER, on_click=close_inline_panel, height=48, expand=True)),
                            ft.Container(col={"xs": 6, "md": 6}, content=submit_button),
                        ],
                    ),
                ],
            ),
        )

    def open_toggle_active_dialog(material: dict[str, Any]) -> None:
        # r7：啟用 / 停用確認也改為頁內確認卡。
        state["active_form"] = "toggle"
        state["confirm_material"] = material
        state["editing_material"] = None
        request_scroll_to_top()
        rebuild()

    def build_toggle_active_panel() -> ft.Control:
        material = state.get("confirm_material") or {}
        current_active = bool(material.get("is_active"))
        next_active = not current_active
        action_text = "啟用" if next_active else "停用"
        action_color = GREEN if next_active else RED
        action_bg = GREEN_SOFT if next_active else RED_SOFT
        action_border = GREEN_BORDER if next_active else RED_BORDER
        busy = {"value": False}
        confirm_ref: dict[str, Any] = {"control": None}

        def submit(_=None):
            if busy["value"]:
                return
            if not action_lock.acquire(blocking=False):
                show_snack("資料寫入中，請稍候。", success=False)
                return

            busy["value"] = True
            set_stable_button_loading(confirm_ref["control"], True, f"確認{action_text}", ft.Icons.CHECK_CIRCLE_OUTLINE)

            def worker():
                try:
                    result = toggle_material_active(
                        material_id=str(material.get("id") or ""),
                        is_active=next_active,
                        current_user=current_user(),
                    )
                    if result.ok:
                        state["active_form"] = None
                        state["confirm_material"] = None
                        show_snack(result.message, success=True)
                        load_data(show_loading=False)
                    else:
                        show_snack(result.message, success=False)
                        busy["value"] = False
                        set_stable_button_loading(confirm_ref["control"], False, f"確認{action_text}", ft.Icons.CHECK_CIRCLE_OUTLINE)
                except Exception as exc:
                    show_snack(f"更新原料啟用狀態失敗：{exc}", success=False)
                    busy["value"] = False
                    set_stable_button_loading(confirm_ref["control"], False, f"確認{action_text}", ft.Icons.CHECK_CIRCLE_OUTLINE)
                finally:
                    try:
                        action_lock.release()
                    except Exception:
                        pass

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
            height=46,
            expand=True,
        )
        confirm_ref["control"] = confirm_btn

        return card(
            padding=18,
            border_color=action_border,
            bgcolor="#FFFFFF",
            content=ft.Column(
                spacing=14,
                controls=[
                    ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Container(
                                width=48,
                                height=48,
                                border_radius=14,
                                bgcolor=action_bg,
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE if next_active else ft.Icons.PAUSE_CIRCLE_OUTLINE, size=25, color=action_color),
                            ),
                            ft.Column(
                                expand=True,
                                spacing=4,
                                controls=[
                                    ft.Text(f"確認{action_text}原料", size=22, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ft.Text(material.get("material_name") or "-", size=16, color=TEXT, weight=ft.FontWeight.W_600),
                                    ft.Text(message, size=13, color=TEXT_MUTED, max_lines=4),
                                ],
                            ),
                        ],
                    ),
                    ft.ResponsiveRow(
                        columns=12,
                        spacing=10,
                        run_spacing=10,
                        controls=[
                            ft.Container(col={"xs": 6, "md": 6}, content=stable_button("取消", icon=ft.Icons.CLOSE, color=TEXT_MUTED, border_color=BORDER, on_click=close_inline_panel, height=46, expand=True)),
                            ft.Container(col={"xs": 6, "md": 6}, content=confirm_btn),
                        ],
                    ),
                ],
            ),
        )

    def build_active_inline_panel() -> ft.Control:
        mode = state.get("active_form")
        if mode in ["create", "edit"]:
            return build_material_form_panel()
        if mode == "toggle":
            return build_toggle_active_panel()
        return ft.Container(height=0)

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
                        ft.Text("此頁面僅限超級管理員使用。", size=14, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                        stable_button("返回首頁", icon=ft.Icons.HOME_OUTLINED, filled=True, color=BLUE_BTN, on_click=lambda _: navigate("/"), height=44, min_width=120),
                    ],
                ),
            ),
        )

    def build_header(is_mobile: bool) -> ft.Control:
        status = state.get("sync_status") or "success"
        if status == "loading":
            status_color, status_bg, status_border = BLUE_BTN, BLUE_SOFT, BLUE_BORDER
            status_icon = ft.ProgressRing(width=15, height=15, stroke_width=2, color=status_color)
        elif status == "success":
            status_color, status_bg, status_border = GREEN, GREEN_SOFT, GREEN_BORDER
            status_icon = ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=17, color=status_color)
        else:
            status_color, status_bg, status_border = RED, RED_SOFT, RED_BORDER
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
            visible=(status != "success" or bool(state.get("sync_badge_visible", True))),
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

        controls: list[ft.Control] = [breadcrumb(), title_row]
        if status_badge.visible:
            controls.append(status_badge)
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

    def make_filter_dropdown(label: str, value: str, values: list[str]) -> ft.Dropdown:
        options = [ft.dropdown.Option("全部")] + [ft.dropdown.Option(v) for v in values]
        current_value = value if value in ["全部"] + values else "全部"
        return ft.Dropdown(
            value=current_value,
            options=options,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE_BTN,
            bgcolor="#E5E7EF",
            filled=True,
            height=54,
            width=float("inf"),
            text_size=14,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=12),
        )

    def compact_filter_field(label: str, control: ft.Control, icon=None) -> ft.Control:
        title_controls = []
        if icon:
            title_controls.append(ft.Icon(icon, size=17, color=TEXT_MUTED))
        title_controls.append(
            ft.Text(
                label,
                size=14,
                color=TEXT,
                weight=ft.FontWeight.BOLD,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )
        return ft.Column(
            spacing=7,
            controls=[
                ft.Row(spacing=7, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=title_controls),
                ft.Container(width=float("inf"), content=control),
            ],
        )

    def build_filter_bar(is_mobile: bool) -> ft.Control:
        """
        r6：手機篩選不使用水平橫滑。
        - 主分類 / 原料類型：兩欄排列。
        - 供應商：獨立一列。
        - 搜尋：獨立下一列。
        - 套用 / 清除：兩欄排列。
        - chips 使用 wrap，自然換行。
        """
        options = state["filter_options"]

        keyword_tf = make_field(
            "搜尋",
            state.get("keyword", ""),
            "原料名稱、供應商、備註",
        )
        category_dd = make_filter_dropdown("主分類", state["filter_category"], options.get("main_categories", []))
        type_dd = make_filter_dropdown("原料類型", state["filter_type"], options.get("material_types", []))
        supplier_dd = make_filter_dropdown("供應商", state["filter_supplier"], options.get("suppliers", []))

        def apply_filters(_=None):
            state["keyword"] = str(keyword_tf.value or "").strip()
            state["filter_category"] = category_dd.value or "全部"
            state["filter_type"] = type_dd.value or "全部"
            state["filter_supplier"] = supplier_dd.value or "全部"
            rebuild()

        def set_active_filter(value: str):
            state["filter_active"] = value
            rebuild()

        def set_managed_filter(value: str):
            state["filter_managed"] = value
            rebuild()

        def filter_chip(label: str, active: bool, on_click, color: str = BLUE_BTN, bg: str = BLUE_SOFT):
            return ft.Container(
                height=32,
                border_radius=16,
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
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            )

        result_count = len(filtered_materials())
        total_count = len(state.get("materials") or [])

        fields_grid = ft.ResponsiveRow(
            columns=12,
            spacing=12,
            run_spacing=14,
            controls=[
                ft.Container(col={"xs": 6, "md": 3}, content=compact_filter_field("主分類", category_dd, ft.Icons.CATEGORY_OUTLINED)),
                ft.Container(col={"xs": 6, "md": 3}, content=compact_filter_field("原料類型", type_dd, ft.Icons.SCIENCE_OUTLINED)),
                ft.Container(col={"xs": 12, "md": 3}, content=compact_filter_field("供應商", supplier_dd, ft.Icons.DOMAIN_OUTLINED)),
                ft.Container(col={"xs": 12, "md": 3}, content=compact_filter_field("搜尋", keyword_tf, ft.Icons.SEARCH)),
            ],
        )

        buttons_grid = ft.ResponsiveRow(
            columns=12,
            spacing=10,
            run_spacing=10,
            controls=[
                ft.Container(col={"xs": 6, "md": 3}, content=stable_button("套用篩選", icon=ft.Icons.SEARCH, filled=True, color=BLUE_BTN, on_click=apply_filters, height=42, expand=True)),
                ft.Container(col={"xs": 6, "md": 3}, content=stable_button("清除條件", icon=ft.Icons.CLOSE, color=RED, border_color=RED_BORDER, on_click=clear_filters, height=42, expand=True)),
            ],
        )

        def segmented_filter_row(title: str, controls: list[ft.Control]) -> ft.Control:
            return ft.Column(
                spacing=7,
                controls=[
                    ft.Text(title, size=12, color=TEXT_MUTED, weight=ft.FontWeight.W_600),
                    ft.Row(wrap=True, spacing=8, run_spacing=8, controls=controls),
                ],
            )

        chips_wrap = ft.ResponsiveRow(
            columns=12,
            spacing=12,
            run_spacing=10,
            controls=[
                ft.Container(
                    col={"xs": 12, "md": 6},
                    content=segmented_filter_row(
                        "啟用狀態",
                        [
                            filter_chip("全部", state["filter_active"] == "全部", lambda _: set_active_filter("全部")),
                            filter_chip("啟用", state["filter_active"] == "啟用", lambda _: set_active_filter("啟用"), GREEN, GREEN_SOFT),
                            filter_chip("停用", state["filter_active"] == "停用", lambda _: set_active_filter("停用"), ORANGE, ORANGE_SOFT),
                        ],
                    ),
                ),
                ft.Container(
                    col={"xs": 12, "md": 6},
                    content=segmented_filter_row(
                        "庫存納管",
                        [
                            filter_chip("全部", state["filter_managed"] == "全部", lambda _: set_managed_filter("全部")),
                            filter_chip("納管", state["filter_managed"] == "納管", lambda _: set_managed_filter("納管"), BLUE_BTN, BLUE_SOFT),
                            filter_chip("未納管", state["filter_managed"] == "未納管", lambda _: set_managed_filter("未納管"), PURPLE_BTN, PURPLE_SOFT),
                        ],
                    ),
                ),
            ],
        )

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
                        ],
                    ),
                    fields_grid,
                    buttons_grid,
                    chips_wrap,
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
            width=220,
            content=ft.Row(
                spacing=8,
                controls=[
                    stable_button("編輯", icon=ft.Icons.EDIT_OUTLINED, color=BLUE_BTN, border_color=BLUE_BORDER, on_click=lambda _, current=row: open_material_dialog(current), height=40, min_width=86),
                    stable_button("停用" if row.get("is_active") else "啟用", icon=ft.Icons.PAUSE_CIRCLE_OUTLINE if row.get("is_active") else ft.Icons.CHECK_CIRCLE_OUTLINE, color=RED if row.get("is_active") else GREEN, border_color=RED_BORDER if row.get("is_active") else GREEN_BORDER, on_click=lambda _, current=row: open_toggle_active_dialog(current), height=40, min_width=92),
                ],
            ),
        )

    def table_row(row: dict[str, Any] | None = None, header: bool = False) -> ft.Container:
        row = row or {}
        bg = "#F8FAFC" if header else "#FFFFFF"
        text_color = TEXT_MUTED if header else TEXT
        weight = ft.FontWeight.W_700 if header else None
        border = None if header else ft.border.only(bottom=ft.BorderSide(1, "#EEF2F7"))

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
                table_cell("操作", 220, text_color, weight),
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
                                        ft.Text("篩選後原料清單", size=18, color=TEXT, weight=ft.FontWeight.BOLD),
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
                            ft.Container(expand=True, content=stable_button("編輯", icon=ft.Icons.EDIT_OUTLINED, color=BLUE_BTN, border_color=BLUE_BORDER, on_click=lambda _, current=row: open_material_dialog(current), height=40, expand=True)),
                            ft.Container(expand=True, content=stable_button("停用" if row.get("is_active") else "啟用", icon=ft.Icons.PAUSE_CIRCLE_OUTLINE if row.get("is_active") else ft.Icons.CHECK_CIRCLE_OUTLINE, color=RED if row.get("is_active") else GREEN, border_color=RED_BORDER if row.get("is_active") else GREEN_BORDER, on_click=lambda _, current=row: open_toggle_active_dialog(current), height=40, expand=True)),
                        ],
                    ),
                ],
            ),
        )

    def build_mobile_list(rows: list[dict[str, Any]]) -> ft.Control:
        list_body: ft.Control
        if not rows:
            list_body = card(padding=18, content=ft.Text("目前沒有符合條件的原料資料。", size=14, color=TEXT_MUTED))
        else:
            list_body = ft.Column(spacing=12, controls=[build_mobile_card(row) for row in rows])

        return ft.Column(
            spacing=10,
            controls=[
                card(
                    padding=14,
                    content=ft.Row(
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.FORMAT_LIST_BULLETED, size=22, color=BLUE_BTN),
                            ft.Column(
                                expand=True,
                                spacing=2,
                                controls=[
                                    ft.Text("篩選後原料清單", size=18, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ft.Text(f"依目前條件顯示 {len(rows)} 筆原料。", size=12, color=TEXT_MUTED),
                                ],
                            ),
                        ],
                    ),
                ),
                list_body,
            ],
        )

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

        layout_col = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            controls=[
                build_header(is_mobile),
                build_active_inline_panel(),
                build_summary_cards(is_mobile),
                build_filter_bar(is_mobile),
                build_materials_content(is_mobile),
                ft.Container(height=90),
            ],
        )
        layout_scroll_ref["control"] = layout_col

        return ft.Container(
            expand=True,
            bgcolor=BG,
            padding=ft.padding.only(left=20 if is_mobile else 24, right=20 if is_mobile else 24, top=18, bottom=18),
            content=layout_col,
        )

    def rebuild() -> None:
        try:
            with ui_lock:
                main_host.content = build_layout()
                try:
                    main_host.update()
                except Exception:
                    page.update()
                run_pending_scroll_to_top()
        except Exception as exc:
            state["error_message"] = f"原料設定畫面重建失敗：{exc}"
            print("admin_materials rebuild failed:", repr(exc), flush=True)
            try:
                main_host.content = ft.Container(
                    expand=True,
                    bgcolor=BG,
                    padding=22,
                    content=card(
                        border_color=RED_BORDER,
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                ft.Icon(ft.Icons.ERROR_OUTLINE, color=RED, size=40),
                                ft.Text("原料設定畫面重建失敗", size=20, color=TEXT, weight=ft.FontWeight.BOLD),
                                ft.Text(str(exc), size=13, color=TEXT_MUTED),
                                stable_button("重新整理", icon=ft.Icons.REFRESH, filled=True, color=BLUE_BTN, on_click=lambda _: load_data(show_loading=True), height=42, min_width=112),
                            ],
                        ),
                    ),
                )
                page.update()
            except Exception:
                pass

    # 初始畫面與背景載入
    main_host.content = build_layout()
    if is_super_admin():
        load_data(show_loading=False)

    return root
