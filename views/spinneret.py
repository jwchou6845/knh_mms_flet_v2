# views/spinneret.py
# KNH MMS - 噴頭組件狀態
# Flet 0.84 + Supabase
# 本版重點：非阻塞背景載入、離頁保護、集中 page.update()、手機 Web 穩定按鈕；狀態膠囊 slot 隱藏修正。

import flet as ft
import threading
import time

from services.spinneret_service import (
    load_spinneret_page_data,
    update_spinneret_status,
)


def SpinneretContent(page: ft.Page):
    # =====================================================
    # 0. 狀態資料
    # =====================================================
    records = []
    status_options = []
    spec_options = []

    data_loaded = {"done": False}
    loading_state = {"value": True}
    saving_ids = set()

    if not hasattr(page, "session_data") or not isinstance(page.session_data, dict):
        page.session_data = {}

    view_token = object()
    page.session_data["_spinneret_view_token"] = view_token

    def is_view_active(token=None) -> bool:
        if token is not None and page.session_data.get("_spinneret_view_token") is not token:
            return False

        current_route = getattr(page, "route", None)
        if current_route and current_route != "/spinneret":
            return False

        return True

    def page_update():
        try:
            page.update()
        except Exception as ex:
            print("spinneret page update skipped:", repr(ex))

    def get_session_value(key: str, default=None):
        try:
            if hasattr(page, "session_data") and isinstance(page.session_data, dict):
                return page.session_data.get(key, default)
        except Exception:
            pass
        return default

    # =====================================================
    # 1. 色彩設定
    # =====================================================
    TEXT_MAIN = "#111827"
    TEXT_SUB = "#64748B"
    BORDER = "#E2E8F0"
    INPUT_BG = "#F8FAFC"

    BLUE = "#2F80ED"
    BLUE_SOFT = "#E5F0FF"
    BLUE_BORDER = "#B0D0FF"
    BLUE_BTN = "#4F7FB8"

    GREEN = "#10B981"
    GREEN_SOFT = "#ECFDF5"
    GREEN_BORDER = "#A7F3D0"

    ORANGE = "#F97316"
    ORANGE_SOFT = "#FFF7ED"
    ORANGE_BORDER = "#FDBA74"

    PURPLE = "#8B5CF6"
    PURPLE_SOFT = "#F3E8FF"
    PURPLE_BORDER = "#D8B4FE"

    RED = "#DC2626"
    RED_SOFT = "#FEF2F2"
    RED_BORDER = "#FECACA"

    DISABLED = "#94A3B8"

    # =====================================================
    # 2. 共用 UI 元件
    # =====================================================
    def button_content(label: str, icon_name, color: str, loading: bool = False) -> ft.Row:
        controls = []

        if loading:
            controls.append(ft.ProgressRing(width=18, height=18, stroke_width=2, color=color))
        else:
            controls.append(ft.Icon(icon_name, color=color, size=18))

        controls.append(
            ft.Text(
                label,
                color=color,
                weight=ft.FontWeight.BOLD,
                size=14,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )

        return ft.Row(
            controls=controls,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
            tight=True,
        )

    def stable_button(
        label: str,
        icon_name,
        bg_color: str,
        text_color: str,
        on_click_func,
        height: int = 46,
        border_color: str | None = None,
    ) -> ft.Container:
        btn = ft.Container(
            height=height,
            expand=True,
            border_radius=12,
            bgcolor=bg_color,
            border=ft.border.all(1, border_color or bg_color),
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.symmetric(horizontal=12),
            ink=True,
            content=button_content(label, icon_name, text_color),
        )
        btn.disabled = False
        btn.data = {
            "label": label,
            "icon": icon_name,
            "bg": bg_color,
            "text_color": text_color,
            "border": border_color or bg_color,
        }

        def handle_click(e):
            if getattr(btn, "disabled", False):
                return
            if callable(on_click_func):
                on_click_func(e)

        btn.on_click = handle_click
        return btn

    def set_button_loading(button: ft.Container, label: str = "寫入中..."):
        data = button.data if isinstance(getattr(button, "data", None), dict) else {}
        button.disabled = True
        button.bgcolor = DISABLED
        button.border = ft.border.all(1, DISABLED)
        button.content = button_content(label, data.get("icon", ft.Icons.SYNC), "#FFFFFF", loading=True)

    def set_button_normal(button: ft.Container):
        data = button.data if isinstance(getattr(button, "data", None), dict) else {}
        button.disabled = False
        button.bgcolor = data.get("bg", BLUE_SOFT)
        button.border = ft.border.all(1, data.get("border", data.get("bg", BLUE_BORDER)))
        button.content = button_content(
            data.get("label", "確認"),
            data.get("icon", ft.Icons.CHECK),
            data.get("text_color", BLUE),
            loading=False,
        )

    def field_label(label: str, required: bool = False) -> ft.Text:
        return ft.Text(
            label + (" *" if required else ""),
            size=13,
            color=TEXT_MAIN,
            weight=ft.FontWeight.W_600,
        )

    def dropdown_field(label: str, options: list[str], value: str | None = None) -> ft.Dropdown:
        safe_options = list(options or [])
        if not safe_options:
            safe_options = ["無可用選項"]

        dd = ft.Dropdown(
            label=label,
            value=value if value in safe_options else safe_options[0],
            options=[ft.dropdown.Option(o) for o in safe_options],
            bgcolor=INPUT_BG,
            border_color=BORDER,
            focused_border_color=BLUE,
            border_radius=12,
            text_size=14,
            content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
            expand=True,
            disabled=(safe_options == ["無可用選項"]),
        )
        return dd

    def get_status_style(status_val: str):
        status_text = str(status_val or "")
        if "生產" in status_text:
            return GREEN_SOFT, GREEN
        if any(keyword in status_text for keyword in ["燒解", "清潔", "組裝"]):
            return ORANGE_SOFT, ORANGE
        return BLUE_SOFT, BLUE

    def get_fixed_border_color(comp_name: str):
        name_upper = str(comp_name or "").upper()
        if "SET#1" in name_upper:
            return "#93C5FD"
        if "SET#2" in name_upper:
            return "#86EFAC"
        if "SET#3" in name_upper:
            return "#FDBA74"
        if "SET#4" in name_upper:
            return "#D8B4FE"
        return BORDER

    # =====================================================
    # 3. 頁首與狀態膠囊
    # =====================================================
    status_badge = ft.Container(
        height=36,
        padding=ft.padding.symmetric(horizontal=16),
        border_radius=18,
        bgcolor=BLUE_SOFT,
        border=ft.border.all(1, BLUE_BORDER),
        visible=True,
        content=ft.Row(
            controls=[
                ft.ProgressRing(width=15, height=15, stroke_width=2, color=BLUE),
                ft.Text("資料同步中", size=13, color=BLUE, weight=ft.FontWeight.W_600),
            ],
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    # 外層 slot 控制狀態膠囊是否參與版面。
    # 只隱藏 status_badge 時，手機 Web 可能仍留下 title_column 內的 padding/spacing。
    status_slot = ft.Container(
        padding=ft.padding.only(top=6),
        alignment=ft.Alignment(-1, 0),
        content=status_badge,
        visible=True,
    )

    status_hide_guard = {"token": object()}

    def cancel_status_auto_hide():
        status_hide_guard["token"] = object()

    def schedule_status_auto_hide(seconds: float = 3.0):
        current_token = object()
        status_hide_guard["token"] = current_token
        local_view_token = view_token

        def worker():
            time.sleep(seconds)

            if status_hide_guard.get("token") is not current_token:
                return

            if not is_view_active(local_view_token):
                return

            status_badge.visible = False
            status_slot.visible = False
            page_update()

        threading.Thread(target=worker, daemon=True).start()

    def _apply_status(text: str, theme: str = "blue", loading: bool = False):
        cancel_status_auto_hide()
        status_badge.visible = True
        status_slot.visible = True
        if theme == "green":
            bg = GREEN_SOFT
            border = GREEN_BORDER
            fg = GREEN
            icon = ft.Icons.CHECK_CIRCLE_OUTLINE
        elif theme == "red":
            bg = RED_SOFT
            border = RED_BORDER
            fg = RED
            icon = ft.Icons.ERROR_OUTLINE
        elif theme == "orange":
            bg = ORANGE_SOFT
            border = ORANGE_BORDER
            fg = ORANGE
            icon = ft.Icons.INFO_OUTLINE
        else:
            bg = BLUE_SOFT
            border = BLUE_BORDER
            fg = BLUE
            icon = ft.Icons.SYNC

        status_badge.bgcolor = bg
        status_badge.border = ft.border.all(1, border)

        lead = (
            ft.ProgressRing(width=15, height=15, stroke_width=2, color=fg)
            if loading
            else ft.Icon(icon, size=17, color=fg)
        )

        status_badge.content = ft.Row(
            controls=[lead, ft.Text(text, size=13, color=fg, weight=ft.FontWeight.W_600)],
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def build_header() -> ft.Control:
        page_w = page.width or 430
        is_mobile = page_w <= 520

        title_column = ft.Column(
            controls=[
                ft.Text(
                    "噴頭組件狀態",
                    size=25 if is_mobile else 26,
                    weight=ft.FontWeight.BOLD,
                    color=TEXT_MAIN,
                ),
                ft.Text(
                    "即時掌握各 SET 生產、待機、清潔與分配板規格。",
                    size=13 if is_mobile else 14,
                    color=TEXT_SUB,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                status_slot,
            ],
            spacing=4,
            expand=True,
        )

        return ft.Row(
            controls=[
                ft.Container(
                    width=54,
                    height=54,
                    border_radius=16,
                    bgcolor="#EFF6FF",
                    alignment=ft.Alignment(0, 0),
                    content=ft.Icon(ft.Icons.MEMORY, size=30, color="#334155"),
                ),
                title_column,
            ],
            spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.START,
            expand=True,
        )

    # =====================================================
    # 4. KPI
    # =====================================================
    lbl_kpi_total = ft.Text("0", size=20, weight=ft.FontWeight.BOLD, color=BLUE)
    lbl_kpi_run = ft.Text("0", size=20, weight=ft.FontWeight.BOLD, color=GREEN)
    lbl_kpi_clean = ft.Text("0", size=20, weight=ft.FontWeight.BOLD, color=ORANGE)
    lbl_kpi_standby = ft.Text("0", size=20, weight=ft.FontWeight.BOLD, color=PURPLE)

    def _apply_kpi_numbers():
        total = len(records)
        running = sum(1 for r in records if "生產" in str(r.get("current_status", "")))
        cleaning = sum(
            1 for r in records
            if any(x in str(r.get("current_status", "")) for x in ["燒解", "清潔"])
        )
        standby = sum(
            1 for r in records
            if str(r.get("current_status", "")) in [
                "預熱爐備用中",
                "組裝中",
                "組裝完成備用中",
                "尚未組裝",
                "待下機",
            ]
        )

        lbl_kpi_total.value = str(total)
        lbl_kpi_run.value = str(running)
        lbl_kpi_clean.value = str(cleaning)
        lbl_kpi_standby.value = str(standby)

    def build_kpi_card(lbl_control, title: str, subtitle: str, bg_color: str, icon_name, icon_color: str):
        return ft.Container(
            bgcolor="#FFFFFF",
            border_radius=16,
            border=ft.border.all(1, BORDER),
            padding=14,
            content=ft.Row(
                controls=[
                    ft.Container(
                        width=50,
                        height=50,
                        bgcolor=bg_color,
                        border_radius=14,
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(icon_name, color=icon_color, size=25),
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(title, size=13, color=TEXT_SUB),
                            lbl_control,
                            ft.Text(subtitle, size=11, color="#94A3B8"),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    kpi_row = ft.ResponsiveRow(
        controls=[
            ft.Container(col={"xs": 6, "sm": 6, "xl": 3}, content=build_kpi_card(lbl_kpi_total, "SET 總數", "目前系統紀錄", BLUE_SOFT, ft.Icons.APPS, BLUE)),
            ft.Container(col={"xs": 6, "sm": 6, "xl": 3}, content=build_kpi_card(lbl_kpi_run, "生產中", "上機運作狀態", GREEN_SOFT, ft.Icons.PLAY_CIRCLE_OUTLINE, GREEN)),
            ft.Container(col={"xs": 6, "sm": 6, "xl": 3}, content=build_kpi_card(lbl_kpi_clean, "清潔 / 燒解", "保養維護階段", ORANGE_SOFT, ft.Icons.LOCAL_FIRE_DEPARTMENT_OUTLINED, ORANGE)),
            ft.Container(col={"xs": 6, "sm": 6, "xl": 3}, content=build_kpi_card(lbl_kpi_standby, "備用 / 待機", "等待上線或下機", PURPLE_SOFT, ft.Icons.SCHEDULE_OUTLINED, PURPLE)),
        ],
        spacing=12,
        run_spacing=12,
    )

    # =====================================================
    # 5. 噴頭卡片
    # =====================================================
    grid_layout = ft.ResponsiveRow(spacing=16, run_spacing=16)

    def update_record_locally(rec_id: str, updated_item: dict):
        for index, item in enumerate(records):
            if item.get("id") == rec_id:
                merged = dict(item)
                merged.update(updated_item or {})
                records[index] = merged
                return

    def create_spinneret_card(record: dict) -> ft.Control:
        rec_id = record.get("id", "")
        comp_name = record.get("set_code", "未知組件")
        current_status = record.get("current_status", "尚未組裝")
        current_spec = record.get("plate_spec", "無")
        time_str = record.get("status_updated_at", "尚無紀錄")
        note_value = record.get("note", "")
        updated_by_text = str(
            record.get("updated_by_name")
            or record.get("updated_by")
            or record.get("last_updated_by_name")
            or "-"
        )
        is_saving = rec_id in saving_ids

        bg_color, txt_color = get_status_style(current_status)
        bar_color = get_fixed_border_color(comp_name)

        pill_status = ft.Container(
            bgcolor=bg_color,
            border_radius=16,
            padding=ft.padding.symmetric(horizontal=12, vertical=4),
            content=ft.Text(current_status, color=txt_color, weight=ft.FontWeight.BOLD, size=13),
        )

        dd_status = dropdown_field("更新目前狀態", status_options, current_status)
        dd_spec = dropdown_field("更新分配板規格", spec_options, current_spec)

        note_field = ft.TextField(
            label="備註",
            value=str(note_value or ""),
            hint_text="例：待確認螺絲、分配板需清潔、下次上機前再確認",
            hint_style=ft.TextStyle(size=13, color=TEXT_SUB),
            multiline=True,
            min_lines=2,
            max_lines=3,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE,
            bgcolor=INPUT_BG,
            filled=True,
            text_size=14,
            content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
        )

        def start_save(e=None):
            if rec_id in saving_ids:
                return

            new_st = dd_status.value or current_status
            new_sp = dd_spec.value or current_spec
            new_note = str(note_field.value or "").strip()

            if new_st == "無可用選項" or new_sp == "無可用選項":
                _apply_status("狀態或規格選項尚未載入完成。", theme="red")
                page_update()
                return

            saving_ids.add(rec_id)
            set_button_loading(btn_save, "寫入中...")
            _apply_status(f"正在更新 {comp_name}...", theme="blue", loading=True)
            page_update()

            def worker():
                try:
                    result = update_spinneret_status(
                        row_id=rec_id,
                        current_status=new_st,
                        plate_spec=new_sp,
                        note=new_note,
                        updated_by_user_id=get_session_value("user_id"),
                        updated_by_name=get_session_value("user_name", "未登入"),
                    )

                    if not is_view_active(view_token):
                        return

                    if not result.ok:
                        saving_ids.discard(rec_id)
                        set_button_normal(btn_save)
                        _apply_status(result.message or "更新失敗。", theme="red")
                        page_update()
                        return

                    updated_item = result.data or {}
                    if not updated_item.get("updated_by_name"):
                        updated_item["updated_by_name"] = get_session_value("user_name", "未登入")
                    update_record_locally(rec_id, updated_item)
                    saving_ids.discard(rec_id)

                    _apply_kpi_numbers()
                    _apply_grid()
                    _apply_status(f"{comp_name} 更新成功", theme="green")
                    schedule_status_auto_hide()
                    page_update()

                except Exception as ex:
                    if not is_view_active(view_token):
                        return
                    saving_ids.discard(rec_id)
                    set_button_normal(btn_save)
                    _apply_status(f"更新失敗：{ex}", theme="red")
                    page_update()
                    print("spinneret save error:", repr(ex))

            threading.Thread(target=worker, daemon=True).start()

        btn_save = stable_button(
            "寫入中..." if is_saving else "儲存變更",
            ft.Icons.SAVE_OUTLINED,
            DISABLED if is_saving else BLUE_SOFT,
            "#FFFFFF" if is_saving else BLUE,
            start_save,
            height=46,
            border_color=DISABLED if is_saving else BLUE_BORDER,
        )

        if is_saving:
            set_button_loading(btn_save, "寫入中...")

        editor_panel = ft.ExpansionTile(
            title=ft.Text("變更組件狀態、規格與備註", size=13, weight=ft.FontWeight.BOLD, color=TEXT_SUB),
            collapsed_text_color="#94A3B8",
            text_color=BLUE,
            controls=[
                ft.Container(
                    padding=ft.padding.only(left=14, right=14, bottom=14, top=12),
                    content=ft.Column(
                        controls=[
                            ft.ResponsiveRow(
                                columns=12,
                                spacing=12,
                                run_spacing=12,
                                controls=[
                                    ft.Container(col={"xs": 12, "md": 6}, content=dd_status),
                                    ft.Container(col={"xs": 12, "md": 6}, content=dd_spec),
                                ],
                            ),
                            note_field,
                            btn_save,
                        ],
                        spacing=12,
                    ),
                )
            ],
        )

        return ft.Container(
            col={"xs": 12, "md": 12, "xl": 6},
            content=ft.Container(
                border=ft.border.Border(
                    top=ft.border.BorderSide(1, BORDER),
                    right=ft.border.BorderSide(1, BORDER),
                    bottom=ft.border.BorderSide(1, BORDER),
                    left=ft.border.BorderSide(6, bar_color),
                ),
                border_radius=16,
                bgcolor="#FFFFFF",
                shadow=ft.BoxShadow(spread_radius=0, blur_radius=8, color="#07000000", offset=ft.Offset(0, 2)),
                content=ft.Column(
                    controls=[
                        ft.Container(
                            padding=ft.padding.only(top=16, left=18, right=18, bottom=8),
                            content=ft.Column(
                                controls=[
                                    ft.Row(
                                        controls=[
                                            ft.Icon(ft.Icons.MEMORY_OUTLINED, color="#475569", size=21),
                                            ft.Text(comp_name, size=17, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                                        ],
                                        spacing=10,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    ),
                                    ft.Divider(height=16, color="#F1F5F9"),
                                    ft.Column(
                                        controls=[
                                            ft.Row(
                                                controls=[
                                                    ft.Text("目前狀態：", size=13, color=TEXT_SUB, weight=ft.FontWeight.W_500),
                                                    pill_status,
                                                ],
                                                spacing=8,
                                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                            ),
                                            ft.Row(
                                                controls=[
                                                    ft.Icon(ft.Icons.VIEW_MODULE_OUTLINED, size=14, color="#94A3B8"),
                                                    ft.Text("分配板規格：", size=12, color=TEXT_SUB),
                                                    ft.Text(str(current_spec or "-"), size=13, color=TEXT_MAIN, weight=ft.FontWeight.W_500),
                                                ],
                                                spacing=5,
                                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                            ),
                                            ft.Row(
                                                controls=[
                                                    ft.Icon(ft.Icons.ACCESS_TIME, size=14, color="#94A3B8"),
                                                    ft.Text("最後更新：", size=12, color=TEXT_SUB),
                                                    ft.Text(str(time_str or "-"), size=12, color=TEXT_SUB),
                                                ],
                                                spacing=5,
                                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                            ),
                                            ft.Row(
                                                controls=[
                                                    ft.Icon(ft.Icons.PERSON_OUTLINE, size=14, color="#94A3B8"),
                                                    ft.Text("更新人員：", size=12, color=TEXT_SUB),
                                                    ft.Text(updated_by_text, size=12, color=TEXT_SUB),
                                                ],
                                                spacing=5,
                                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                            ),
                                            ft.Row(
                                                controls=[
                                                    ft.Icon(ft.Icons.NOTES_OUTLINED, size=14, color="#94A3B8"),
                                                    ft.Text("備註：", size=12, color=TEXT_SUB),
                                                    ft.Text(
                                                        str(note_value or "無備註"),
                                                        size=12,
                                                        color=TEXT_SUB,
                                                        expand=True,
                                                        max_lines=2,
                                                        overflow=ft.TextOverflow.ELLIPSIS,
                                                    ),
                                                ],
                                                spacing=5,
                                                vertical_alignment=ft.CrossAxisAlignment.START,
                                            ),
                                        ],
                                        spacing=7,
                                    ),
                                ],
                                spacing=8,
                            ),
                        ),
                        editor_panel,
                    ],
                    spacing=0,
                ),
            ),
        )

    def _apply_grid():
        grid_layout.controls = []

        if loading_state["value"]:
            grid_layout.controls.append(
                ft.Container(
                    col={"xs": 12},
                    bgcolor="#FFFFFF",
                    border=ft.border.all(1, BORDER),
                    border_radius=16,
                    padding=20,
                    content=ft.Row(
                        controls=[
                            ft.ProgressRing(width=18, height=18, stroke_width=2, color=BLUE),
                            ft.Text("正在讀取噴頭組件資料...", size=14, color=TEXT_SUB),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )
            return

        if not records:
            grid_layout.controls.append(
                ft.Container(
                    col={"xs": 12},
                    bgcolor=RED_SOFT,
                    border=ft.border.all(1, RED_BORDER),
                    border_radius=16,
                    padding=18,
                    content=ft.Text(
                        "找不到噴頭組件資料，請確認 Supabase spinneret_sets 是否已有建檔。",
                        color=RED,
                        size=14,
                        weight=ft.FontWeight.W_600,
                    ),
                )
            )
            return

        for rec in records:
            grid_layout.controls.append(create_spinneret_card(rec))

    def _apply_loaded_data(data: dict):
        records.clear()
        records.extend(data.get("items", []) or [])

        status_options.clear()
        status_options.extend(data.get("status_options", []) or [])

        spec_options.clear()
        spec_options.extend(data.get("spec_options", []) or [])

        data_loaded["done"] = True
        loading_state["value"] = False

    def load_initial_data_once():
        current_token = view_token

        def worker():
            try:
                print("====== [系統提示] 背景讀取 Supabase (噴頭組件狀態) ======")
                result = load_spinneret_page_data()

                if not is_view_active(current_token):
                    return

                if not result.ok:
                    data_loaded["done"] = False
                    loading_state["value"] = False
                    _apply_status(result.message or "資料同步失敗", theme="red")
                    _apply_grid()
                    page_update()
                    print("讀取噴頭狀態失敗:", result.message)
                    return

                _apply_loaded_data(result.data or {})
                _apply_kpi_numbers()
                _apply_grid()
                _apply_status("資料已同步", theme="green")
                schedule_status_auto_hide()
                page_update()

                print(f"====== [系統提示] 成功抓取 {len(records)} 筆噴頭組件資料 ======")

            except Exception as ex:
                if not is_view_active(current_token):
                    return
                data_loaded["done"] = False
                loading_state["value"] = False
                _apply_status(f"資料同步失敗：{ex}", theme="red")
                _apply_grid()
                page_update()
                print("spinneret initial load error:", repr(ex))

        threading.Thread(target=worker, daemon=True).start()

    # =====================================================
    # 6. 初始 UI
    # =====================================================
    _apply_status("資料同步中", theme="blue", loading=True)
    _apply_kpi_numbers()
    _apply_grid()
    load_initial_data_once()

    return ft.Column(
        controls=[
            build_header(),
            kpi_row,
            ft.Divider(height=18, color=BORDER),
            grid_layout,
            ft.Container(height=90),
        ],
        spacing=16,
    )
