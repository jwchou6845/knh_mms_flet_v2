# views/inventory.py
# KNH MMS - 原料入庫作業 Supabase 版 v1.3
# 修正：回用料最近入庫列表日期補正、排序與顯示格式
# Flet 0.84 + Python + Supabase

import flet as ft
import threading
import time

from services.inventory_service import (
    load_inventory_page_data,
    submit_purchase_record,
    submit_recycled_material,
    today_batch_prefix,
    today_dash_date,
)


def InventoryContent(page: ft.Page):
    # =====================================================
    # 0. 狀態資料
    # =====================================================
    material_dict = {}
    stock_rows = []
    recent_purchase_records = []
    recent_recycled_records = []

    data_loaded = {"done": False}
    submitting_new = {"value": False}
    submitting_rec = {"value": False}

    def session_get(key: str, default=None):
        if hasattr(page, "session_data") and isinstance(page.session_data, dict):
            return page.session_data.get(key, default)
        return default

    if not hasattr(page, "session_data") or not isinstance(page.session_data, dict):
        page.session_data = {}

    view_token = object()
    page.session_data["_inventory_view_token"] = view_token

    def is_active_view() -> bool:
        route = str(getattr(page, "route", "") or "")
        return (
            page.session_data.get("_inventory_view_token") is view_token
            and (not route or route == "/inventory" or "inventory" in route)
        )

    # =====================================================
    # 1. 色彩設定
    # =====================================================
    TEXT_MAIN = "#111827"
    TEXT_SUB = "#64748B"
    BORDER = "#E2E8F0"
    INPUT_BG = "#F8FAFC"

    BLUE = "#2563EB"
    BLUE_BG = "#E5F0FF"
    BLUE_BORDER = "#B0D0FF"
    BLUE_BAR = "#93C5FD"
    BLUE_BTN = "#4F7FB8"
    BLUE_BTN_HOVER = "#456FA3"
    BLUE_BTN_PRESS = "#3D628F"

    GREEN = "#16A34A"
    GREEN_BG = "#F0FDF4"
    GREEN_BORDER = "#BBF7D0"
    GREEN_BAR = "#86EFAC"
    GREEN_BTN = "#3F8F5A"
    GREEN_BTN_HOVER = "#347A4B"
    GREEN_BTN_PRESS = "#2A663D"

    RED = "#DC2626"
    RED_BG = "#FEF2F2"
    RED_BORDER = "#FECACA"

    GRAY_BG = "#F8FAFC"
    GRAY_BORDER = "#E2E8F0"
    GRAY_TEXT = "#64748B"
    DISABLED = "#94A3B8"

    # =====================================================
    # 2. 安全更新工具
    # =====================================================
    def safe_update(control):
        if not is_active_view():
            return
        try:
            control.update()
        except Exception as ex:
            print("inventory control.update failed:", repr(ex))

    def safe_page_update():
        if not is_active_view():
            return
        try:
            page.update()
        except Exception as ex:
            print("inventory page.update failed:", repr(ex))

    def show_snack(message: str, success: bool = True):
        if not is_active_view():
            return
        snack = ft.SnackBar(
            content=ft.Text(message, color="#FFFFFF", weight=ft.FontWeight.W_600),
            bgcolor=GREEN if success else RED,
            duration=3200,
        )
        try:
            page.overlay.append(snack)
        except Exception:
            pass
        snack.open = True
        safe_page_update()

    # =====================================================
    # 3. 狀態列
    # =====================================================
    status_bar = ft.Container(
        content=ft.Row(
            controls=[
                ft.ProgressRing(width=16, height=16, stroke_width=2, color=BLUE),
                ft.Text(
                    "背景同步 Supabase 資料...",
                    color=BLUE,
                    size=13,
                    weight=ft.FontWeight.W_500,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.padding.symmetric(horizontal=16, vertical=12),
        bgcolor=BLUE_BG,
        border_radius=10,
        border=ft.border.all(1, BLUE_BORDER),
        visible=True,
        width=float("inf"),
    )

    # 用外層 slot 控制狀態膠囊是否參與版面。
    # 只把 status_bar.visible=False 時，手機 Web 仍可能留下 Column spacing；
    # 因此隱藏時同步隱藏 status_slot，避免頁首與下方區塊間距過大。
    status_slot = ft.Container(content=status_bar, visible=True)

    def set_status(msg, is_error=False, theme="blue", auto_hide=False, loading=False):
        if not is_active_view():
            return
        if is_error:
            bg_color = RED_BG
            border_color = RED_BORDER
            text_color = RED
            icon_name = ft.Icons.ERROR_OUTLINE
        elif theme == "green":
            bg_color = GREEN_BG
            border_color = GREEN_BORDER
            text_color = GREEN
            icon_name = ft.Icons.CHECK_CIRCLE_OUTLINE if "成功" in msg or "完成" in msg else ft.Icons.INFO_OUTLINE
        elif theme == "blue":
            bg_color = BLUE_BG
            border_color = BLUE_BORDER
            text_color = BLUE
            icon_name = ft.Icons.CHECK_CIRCLE_OUTLINE if "成功" in msg or "完成" in msg else ft.Icons.INFO_OUTLINE
        else:
            bg_color = GRAY_BG
            border_color = GRAY_BORDER
            text_color = GRAY_TEXT
            icon_name = ft.Icons.INFO_OUTLINE

        status_slot.visible = True
        status_bar.visible = True
        status_bar.bgcolor = bg_color
        status_bar.border = ft.border.all(1, border_color)

        lead = (
            ft.ProgressRing(width=16, height=16, stroke_width=2, color=text_color)
            if loading
            else ft.Icon(icon_name, color=text_color, size=16)
        )

        status_bar.content = ft.Row(
            controls=[
                lead,
                ft.Text(
                    msg,
                    color=text_color,
                    size=13,
                    weight=ft.FontWeight.W_600,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        safe_update(status_bar)
        safe_update(status_slot)

        if auto_hide:
            def hide_later():
                time.sleep(3)
                if not is_active_view():
                    return
                status_bar.visible = False
                status_slot.visible = False
                safe_update(status_slot)

            threading.Thread(target=hide_later, daemon=True).start()

    # =====================================================
    # 4. UI 元件工廠
    # =====================================================
    def ui_input(label, val="", hint="", is_number=False):
        # 手機 Web 上 TextField 的 label 在有值時容易不顯示，
        # 因此欄位標題改由外層 field_group 固定顯示。
        return ft.TextField(
            label=None,
            value=val,
            hint_text=hint or label,
            hint_style=ft.TextStyle(size=14, color="#94A3B8"),
            bgcolor=INPUT_BG,
            border_color=BORDER,
            focused_border_color=BLUE,
            border_radius=12,
            text_size=14,
            height=58,
            content_padding=ft.padding.symmetric(horizontal=16, vertical=14),
            keyboard_type=ft.KeyboardType.NUMBER if is_number else ft.KeyboardType.TEXT,
            expand=True,
        )

    def ui_dropdown(label, options):
        opts = [ft.dropdown.Option(o) for o in options] if options else [ft.dropdown.Option("載入中...")]
        return ft.Dropdown(
            label=None,
            hint_text=label,
            options=opts,
            bgcolor=INPUT_BG,
            border_color=BORDER,
            focused_border_color=BLUE,
            border_radius=12,
            text_size=14,
            height=58,
            content_padding=ft.padding.symmetric(horizontal=16, vertical=14),
            expand=True,
        )

    def field_group(label, control, required=False):
        # 固定外部欄位標題，避免 iOS / Flet Web 上 TextField label 消失。
        return ft.Column(
            controls=[
                ft.Text(
                    label + (" *" if required else ""),
                    size=13,
                    color=TEXT_SUB,
                    weight=ft.FontWeight.W_600,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                control,
            ],
            spacing=6,
            expand=True,
        )

    def form_field(label, control, required=False):
        return ft.Container(
            col={"xs": 12, "md": 6},
            content=field_group(label, control, required=required),
        )

    def form_grid(items):
        return ft.ResponsiveRow(
            columns=12,
            spacing=16,
            run_spacing=14,
            controls=[form_field(label, control, required) for label, control, required in items],
        )

    def title_block():
        return ft.Row(
            controls=[
                ft.Container(
                    width=58,
                    height=58,
                    border_radius=18,
                    bgcolor=BLUE_BG,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Icon(ft.Icons.INVENTORY_2, size=31, color=BLUE),
                ),
                ft.Column(
                    expand=True,
                    spacing=4,
                    controls=[
                        ft.Text("原料入庫作業", size=28, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                        ft.Text(
                            "記錄供應商新料與廠內回用料入庫，維持庫存帳準確。",
                            size=14,
                            color=TEXT_SUB,
                            max_lines=3,
                            overflow=ft.TextOverflow.VISIBLE,
                        ),
                    ],
                ),
            ],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def button_style(bg_color, hover_color, press_color, text_color):
        return ft.ButtonStyle(
            bgcolor={
                ft.ControlState.DEFAULT: bg_color,
                ft.ControlState.HOVERED: hover_color,
                ft.ControlState.PRESSED: press_color,
                ft.ControlState.DISABLED: DISABLED,
            },
            color={
                ft.ControlState.DEFAULT: text_color,
                ft.ControlState.HOVERED: text_color,
                ft.ControlState.PRESSED: text_color,
                ft.ControlState.DISABLED: "#FFFFFF",
            },
            shape=ft.RoundedRectangleBorder(radius=12),
            padding=ft.padding.symmetric(vertical=20),
            elevation={
                ft.ControlState.DEFAULT: 0,
                ft.ControlState.HOVERED: 2,
                ft.ControlState.PRESSED: 0,
                ft.ControlState.DISABLED: 0,
            },
        )

    def _button_inner(label, icon_name, text_color):
        return ft.Row(
            controls=[
                ft.Icon(icon_name, color=text_color, size=18),
                ft.Text(
                    label,
                    color=text_color,
                    weight=ft.FontWeight.BOLD,
                    size=15,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
            tight=True,
        )

    def ui_button(label, icon_name, bg_color, hover_color, press_color, text_color, on_click_func):
        """
        VM / 手機 Web 穩定版按鈕。
        目前 VM 的 Flet Button 不支援 text=/icon= kwargs，且手機 Web 對
        ElevatedButton(content=Row(...)) 偶發文字 / 圖示不渲染。
        因此確認送出類按鈕改用 Container + Row，並用 disabled/opacity 控制狀態。
        """
        btn_ref = {"control": None}

        def handle_click(e):
            btn = btn_ref.get("control")
            if btn is not None and getattr(btn, "disabled", False):
                return
            on_click_func(e)

        btn = ft.Container(
            height=58,
            border_radius=12,
            bgcolor=bg_color,
            alignment=ft.Alignment(0, 0),
            content=_button_inner(label, icon_name, text_color),
            on_click=handle_click,
            expand=True,
            opacity=0.55,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=10,
                color="#10000000",
                offset=ft.Offset(0, 3),
            ),
        )
        btn.disabled = True
        btn.data = {
            "label": label,
            "icon": icon_name,
            "bg": bg_color,
            "hover": hover_color,
            "press": press_color,
            "text_color": text_color,
        }
        btn_ref["control"] = btn
        return btn

    def apply_button_enabled_state(button):
        info = button.data if isinstance(button.data, dict) else {}
        button.bgcolor = info.get("bg", BLUE_BTN)
        button.opacity = 0.55 if getattr(button, "disabled", False) else 1

    def set_button_loading(button, text: str):
        button.disabled = True
        button.bgcolor = DISABLED
        button.opacity = 0.92
        button.content = ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
            tight=True,
            controls=[
                ft.ProgressRing(width=18, height=18, stroke_width=2, color="#FFFFFF"),
                ft.Text(text, color="#FFFFFF", weight=ft.FontWeight.BOLD, size=15),
            ],
        )
        safe_update(button)

    def set_button_normal(button, label: str, icon_name, text_color: str):
        button.disabled = False
        if isinstance(button.data, dict):
            button.data["label"] = label
            button.data["icon"] = icon_name
            button.data["text_color"] = text_color
        button.content = _button_inner(label, icon_name, text_color)
        apply_button_enabled_state(button)
        safe_update(button)

    def section_card(title, icon_name, icon_color, bar_color, content_controls):
        return ft.Container(
            border=ft.border.all(1, BORDER),
            border_radius=16,
            bgcolor=bar_color,
            padding=ft.padding.only(left=6),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=8,
                color="#08000000",
                offset=ft.Offset(0, 3),
            ),
            content=ft.Container(
                bgcolor="#FFFFFF",
                border_radius=ft.border_radius.only(top_right=15, bottom_right=15),
                padding=24,
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(icon_name, color=icon_color, size=24),
                                ft.Text(
                                    title,
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color=TEXT_MAIN,
                                ),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Divider(height=18, color="#F1F5F9"),
                        *content_controls,
                    ],
                    spacing=15,
                ),
            ),
        )

    # =====================================================
    # 5. 日期預設：Asia/Taipei 由 service 提供
    # =====================================================
    today_batch = today_batch_prefix()
    today_date = today_dash_date()

    # =====================================================
    # 6. 供應商新料入庫表單
    # =====================================================
    n_batch = ui_input("進貨批號（需補齊流水號）", val=today_batch)
    n_date = ui_input("進貨日期", val=today_date)
    n_mat = ui_dropdown("關聯原料", [])
    n_qty = ui_input("進貨數量（包）", val="1", is_number=True)

    def check_new_batch(e=None, do_update=True):
        """
        按鈕策略：
        - 資料尚未同步完成：不可送出。
        - 資料同步完成後：按鈕保持可點擊。
        - 欄位缺漏或格式錯誤：由 submit_new() 顯示明確錯誤訊息。

        這樣現場操作員點按鈕時會有回饋，不會以為系統壞掉。
        """
        val = (n_batch.value or "").strip()

        if not data_loaded["done"]:
            btn_new.disabled = True
            n_batch.error_text = None
        else:
            btn_new.disabled = False
            n_batch.error_text = None if val else "請輸入進貨批號"

        apply_button_enabled_state(btn_new)

        if do_update:
            safe_update(n_batch)
            safe_update(btn_new)

    def submit_new(e):
        if submitting_new["value"]:
            return

        if not data_loaded["done"]:
            set_status("資料尚未同步完成，請稍候。", is_error=True)
            return

        if not n_mat.value or n_mat.value in ["載入中...", "無可用原料"]:
            set_status("請先選擇關聯原料。", is_error=True)
            return

        qty_text = (n_qty.value or "").strip()
        if not qty_text.isdigit() or int(qty_text) <= 0:
            set_status("請輸入正確的進貨數量。", is_error=True)
            return

        batch_text = (n_batch.value or "").strip()
        if not batch_text:
            set_status("請輸入進貨批號。", is_error=True)
            return

        material_id = material_dict.get(n_mat.value)
        if not material_id:
            set_status("找不到此原料對應的 Supabase material_id。", is_error=True)
            return

        purchase_date = str(n_date.value or "")
        quantity_bags = int(qty_text)
        created_by_user_id = session_get("user_id")
        created_by_name = session_get("user_name")

        submitting_new["value"] = True
        set_button_loading(btn_new, "寫入中...")
        set_status("正在寫入新料入庫資料...", theme="blue", loading=True)

        def worker():
            try:
                result = submit_purchase_record(
                    purchase_batch_no=batch_text,
                    purchase_date=purchase_date,
                    material_id=material_id,
                    quantity_bags=quantity_bags,
                    created_by_user_id=created_by_user_id,
                    created_by_name=created_by_name,
                )

                if not is_active_view():
                    return

                if not result.ok:
                    set_status(result.message, is_error=True)
                    show_snack(result.message, success=False)
                    return

                n_batch.value = today_batch_prefix()
                n_date.value = today_dash_date()
                n_qty.value = "1"
                check_new_batch(None, do_update=False)

                safe_update(n_batch)
                safe_update(n_date)
                safe_update(n_qty)

                set_status(result.message, theme="blue", auto_hide=True)
                show_snack(result.message, success=True)

                refresh_from_service(silent=True)

            except Exception as ex:
                if not is_active_view():
                    return
                set_status(f"寫入失敗：{ex}", is_error=True)
                show_snack(f"寫入失敗：{ex}", success=False)

            finally:
                if not is_active_view():
                    return
                submitting_new["value"] = False
                set_button_normal(
                    btn_new,
                    "確認送出新料入庫",
                    ft.Icons.CLOUD_UPLOAD_OUTLINED,
                    "#FFFFFF",
                )
                check_new_batch(None, do_update=True)

        threading.Thread(target=worker, daemon=True).start()


    btn_new = ui_button(
        "確認送出新料入庫",
        ft.Icons.CLOUD_UPLOAD_OUTLINED,
        BLUE_BTN,
        BLUE_BTN_HOVER,
        BLUE_BTN_PRESS,
        "#FFFFFF",
        submit_new,
    )

    n_batch.on_change = check_new_batch
    n_mat.on_change = check_new_batch

    form_new = section_card(
        title="供應商新料入庫表單",
        icon_name=ft.Icons.BUSINESS,
        icon_color=BLUE,
        bar_color=BLUE_BAR,
        content_controls=[
            form_grid([
                ("進貨批號（需補齊流水號）", n_batch, True),
                ("關聯原料", n_mat, True),
                ("進貨日期", n_date, True),
                ("進貨數量（包）", n_qty, True),
            ]),
            ft.Container(height=4),
            ft.Row([btn_new]),
        ],
    )

    # =====================================================
    # 7. 廠內回用料入庫表單
    # =====================================================
    r_id = ui_input("原料編號（需補齊流水號）", val=today_batch)
    r_date = ui_input("入庫日期", val=today_date)
    r_type = ui_dropdown("原料種類", ["PET", "RPET", "PET-308A", "PA6"])
    r_machine = ui_dropdown("來源機台", ["S1", "S2"])
    r_weight = ui_input("重量（KG）", val="", is_number=True)
    r_vendor = ui_dropdown(
        "供應商",
        [
            "南紡",
            "南紡308A",
            "南亞",
            "遠東",
            "遠東RPET",
            "集盛",
            "力鵬",
            "中國岳化",
            "中國儀征",
        ],
    )

    r_type.value = "PET"
    r_machine.value = "S1"
    r_vendor.value = "南紡"

    def check_rec_batch(e=None, do_update=True):
        """
        按鈕策略：
        - 資料尚未同步完成：不可送出。
        - 資料同步完成後：按鈕保持可點擊。
        - 編號未補齊流水號：由 submit_rec() 顯示明確錯誤訊息。
        """
        val = (r_id.value or "").strip()

        if not data_loaded["done"]:
            btn_rec.disabled = True
            r_id.error_text = None
        else:
            btn_rec.disabled = False
            r_id.error_text = None if val and val != today_batch_prefix() else "請補齊流水號"

        apply_button_enabled_state(btn_rec)

        if do_update:
            safe_update(r_id)
            safe_update(btn_rec)

    def submit_rec(e):
        if submitting_rec["value"]:
            return

        if not data_loaded["done"]:
            set_status("資料尚未同步完成，請稍候。", is_error=True)
            return

        rec_id_text = (r_id.value or "").strip()
        weight_text = (r_weight.value or "").strip()

        if not rec_id_text or rec_id_text == today_batch_prefix():
            set_status("請完整填寫「原料編號」的流水號。", is_error=True)
            return

        try:
            weight_val = float(weight_text)
            if weight_val <= 0:
                raise ValueError()
        except Exception:
            set_status("請輸入正確的「重量」。", is_error=True)
            return

        inbound_date = str(r_date.value or "")
        material_type = str(r_type.value or "")
        source_machine = str(r_machine.value or "")
        supplier = str(r_vendor.value or "")

        submitting_rec["value"] = True
        set_button_loading(btn_rec, "寫入中...")
        set_status("正在寫入回用料入庫資料...", theme="green", loading=True)

        def worker():
            try:
                result = submit_recycled_material(
                    recycled_no=rec_id_text,
                    inbound_date=inbound_date,
                    material_type=material_type,
                    source_machine=source_machine,
                    weight_kg=weight_val,
                    supplier=supplier,
                )

                if not is_active_view():
                    return

                if not result.ok:
                    set_status(result.message, is_error=True)
                    show_snack(result.message, success=False)
                    return

                r_id.value = today_batch_prefix()
                r_date.value = today_dash_date()
                r_weight.value = ""
                check_rec_batch(None, do_update=False)

                safe_update(r_id)
                safe_update(r_date)
                safe_update(r_weight)

                set_status(result.message, theme="green", auto_hide=True)
                show_snack(result.message, success=True)

                refresh_from_service(silent=True)

            except Exception as ex:
                if not is_active_view():
                    return
                set_status(f"寫入失敗：{ex}", is_error=True)
                show_snack(f"寫入失敗：{ex}", success=False)

            finally:
                if not is_active_view():
                    return
                submitting_rec["value"] = False
                set_button_normal(
                    btn_rec,
                    "確認送出回用料紀錄",
                    ft.Icons.RECYCLING,
                    "#FFFFFF",
                )
                check_rec_batch(None, do_update=True)

        threading.Thread(target=worker, daemon=True).start()


    btn_rec = ui_button(
        "確認送出回用料紀錄",
        ft.Icons.RECYCLING,
        GREEN_BTN,
        GREEN_BTN_HOVER,
        GREEN_BTN_PRESS,
        "#FFFFFF",
        submit_rec,
    )

    r_id.on_change = check_rec_batch

    form_rec = section_card(
        title="廠內回用料入庫表單",
        icon_name=ft.Icons.FACTORY_OUTLINED,
        icon_color=GREEN,
        bar_color=GREEN_BAR,
        content_controls=[
            form_grid([
                ("原料編號（需補齊流水號）", r_id, True),
                ("入庫日期", r_date, True),
                ("原料種類", r_type, True),
                ("重量（KG）", r_weight, True),
                ("來源機台", r_machine, True),
                ("供應商", r_vendor, True),
            ]),
            ft.Container(height=4),
            ft.Row([btn_rec]),
        ],
    )


    # =====================================================
    # 8. 最近紀錄列表
    # =====================================================
    recent_purchase_list = ft.Column(spacing=0)
    recent_recycled_list = ft.Column(spacing=0)

    def recent_record_shell(title, subtitle, icon_name, icon_color, border_color, list_control):
        return ft.Container(
            border=ft.border.all(1, border_color),
            border_radius=16,
            bgcolor="#FFFFFF",
            padding=18,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=8,
                color="#08000000",
                offset=ft.Offset(0, 3),
            ),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Icon(icon_name, color=icon_color, size=23),
                                    ft.Column(
                                        controls=[
                                            ft.Text(title, size=17, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                                            ft.Text(subtitle, size=12, color=TEXT_SUB),
                                        ],
                                        spacing=2,
                                    ),
                                ],
                                spacing=10,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Container(
                                padding=ft.padding.symmetric(horizontal=10, vertical=5),
                                border_radius=14,
                                bgcolor=GRAY_BG,
                                content=ft.Text("最近 10 筆", size=12, color=TEXT_SUB, weight=ft.FontWeight.W_600),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(height=16, color="#F1F5F9"),
                    list_control,
                ],
                spacing=8,
            ),
        )

    def empty_recent_row(message: str):
        return ft.Container(
            padding=ft.padding.symmetric(horizontal=12, vertical=14),
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=TEXT_SUB),
                    ft.Text(message, size=13, color=TEXT_SUB),
                ],
                spacing=8,
            ),
        )

    def refresh_recent_purchase_panel():
        recent_purchase_list.controls = []

        if not recent_purchase_records:
            recent_purchase_list.controls.append(empty_recent_row("目前尚無最近進貨紀錄。"))
        else:
            for record in recent_purchase_records[:10]:
                qty_bags = record.get("quantity_bags", 0)
                qty_kg = record.get("quantity_kg", 0)
                recent_purchase_list.controls.append(
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=12, vertical=12),
                        border=ft.border.only(bottom=ft.BorderSide(1, "#F1F5F9")),
                        content=ft.ResponsiveRow(
                            columns=12,
                            spacing=8,
                            run_spacing=4,
                            controls=[
                                ft.Container(
                                    col={"xs": 3, "md": 2},
                                    content=ft.Column(
                                        controls=[
                                            ft.Text(record.get("date", "-"), size=13, color=TEXT_MAIN, weight=ft.FontWeight.W_600),
                                            ft.Text("日期", size=11, color=TEXT_SUB),
                                        ],
                                        spacing=2,
                                    ),
                                ),
                                ft.Container(
                                    col={"xs": 9, "md": 4},
                                    content=ft.Column(
                                        controls=[
                                            ft.Text(record.get("material_name", "-"), size=13, color=TEXT_MAIN, weight=ft.FontWeight.W_600, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                            ft.Text(f"批號：{record.get('batch_no', '-')}", size=11, color=TEXT_SUB, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                        ],
                                        spacing=2,
                                    ),
                                ),
                                ft.Container(
                                    col={"xs": 6, "md": 3},
                                    content=ft.Text(record.get("supplier", "-"), size=12, color=TEXT_SUB, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                ),
                                ft.Container(
                                    col={"xs": 6, "md": 3},
                                    alignment=ft.Alignment(1, 0),
                                    content=ft.Text(f"{qty_bags} 包 / {qty_kg:g} KG", size=13, color=BLUE, weight=ft.FontWeight.BOLD),
                                ),
                            ],
                        ),
                    )
                )

        safe_update(recent_purchase_list)

    def _recycled_date_label(record: dict) -> str:
        """
        回用料舊資料有些 inbound_date 可能是空值。
        若 service 回傳 date 為 '-'，則用回用料編號前 8 碼推回日期。
        例如：2026021206 -> 2026/02/12。
        """
        date_text = str(record.get("date") or "").strip()
        if date_text and date_text != "-":
            return date_text

        recycled_no = str(record.get("recycled_no") or "").strip()
        if len(recycled_no) >= 8 and recycled_no[:8].isdigit():
            return f"{recycled_no[:4]}/{recycled_no[4:6]}/{recycled_no[6:8]}"

        return "-"

    def _recycled_sort_key(record: dict) -> str:
        label = _recycled_date_label(record)
        if label != "-":
            return label.replace("/", "")

        recycled_no = str(record.get("recycled_no") or "").strip()
        return recycled_no[:8] if recycled_no[:8].isdigit() else "00000000"

    def refresh_recent_recycled_panel():
        recent_recycled_list.controls = []

        if not recent_recycled_records:
            recent_recycled_list.controls.append(empty_recent_row("目前尚無最近回用料入庫紀錄。"))
        else:
            sorted_records = sorted(
                recent_recycled_records,
                key=_recycled_sort_key,
                reverse=True,
            )

            for record in sorted_records[:10]:
                weight = record.get("weight_kg", 0)
                status = record.get("usage_status", "-")
                supplier = str(record.get("supplier") or "-").strip()
                material_type = str(record.get("material_type") or "-").strip()
                supplier_material = f"{supplier} | {material_type}"

                recent_recycled_list.controls.append(
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=12, vertical=12),
                        border=ft.border.only(bottom=ft.BorderSide(1, "#F1F5F9")),
                        content=ft.ResponsiveRow(
                            columns=12,
                            spacing=8,
                            run_spacing=4,
                            controls=[
                                ft.Container(
                                    col={"xs": 4, "md": 3},
                                    content=ft.Column(
                                        controls=[
                                            ft.Text(_recycled_date_label(record), size=13, color=TEXT_MAIN, weight=ft.FontWeight.W_600),
                                            ft.Text("日期", size=11, color=TEXT_SUB),
                                        ],
                                        spacing=2,
                                    ),
                                ),
                                ft.Container(
                                    col={"xs": 5, "md": 5},
                                    content=ft.Column(
                                        controls=[
                                            ft.Text(record.get("recycled_no", "-"), size=13, color=TEXT_MAIN, weight=ft.FontWeight.W_600, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                            ft.Text(supplier_material, size=11, color=TEXT_SUB, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                        ],
                                        spacing=2,
                                    ),
                                ),
                                ft.Container(
                                    col={"xs": 3, "md": 4},
                                    alignment=ft.Alignment(1, 0),
                                    content=ft.Row(
                                        controls=[
                                            ft.Container(
                                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                                border_radius=12,
                                                bgcolor=GREEN_BG if status == "在庫" else GRAY_BG,
                                                content=ft.Text(status, size=12, color=GREEN if status == "在庫" else TEXT_SUB, weight=ft.FontWeight.W_600),
                                            ),
                                            ft.Text(f"{weight:g} KG", size=13, color=GREEN, weight=ft.FontWeight.BOLD),
                                        ],
                                        alignment=ft.MainAxisAlignment.END,
                                        spacing=8,
                                    ),
                                ),
                            ],
                        ),
                    )
                )

        safe_update(recent_recycled_list)

    recent_purchase_panel = recent_record_shell(
        "最近進貨紀錄",
        "顯示最近建立的供應商新料入庫紀錄。",
        ft.Icons.RECEIPT_LONG_OUTLINED,
        BLUE,
        BLUE_BORDER,
        recent_purchase_list,
    )

    recent_recycled_panel = recent_record_shell(
        "最近回用料入庫紀錄",
        "顯示最近建立的廠內回用料入庫紀錄。",
        ft.Icons.RECYCLING,
        GREEN,
        GREEN_BORDER,
        recent_recycled_list,
    )

    refresh_recent_purchase_panel()
    refresh_recent_recycled_panel()

    new_tab_content = ft.Column(
        controls=[form_new, recent_purchase_panel],
        spacing=16,
    )

    rec_tab_content = ft.Column(
        controls=[form_rec, recent_recycled_panel],
        spacing=16,
    )

    # =====================================================
    # 9. Tab 切換
    # =====================================================
    content_area = ft.Container(content=new_tab_content)

    def tab_inner(label, icon_name, color):
        return ft.Row(
            controls=[
                ft.Icon(icon_name, size=18, color=color),
                ft.Text(
                    label,
                    weight=ft.FontWeight.BOLD,
                    size=14,
                    color=color,
                ),
            ],
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        )

    def make_tab_button(label, icon_name, active_color, active_bg, active_border, is_active=False):
        color = active_color if is_active else TEXT_SUB
        return ft.Container(
            height=48,
            padding=ft.padding.symmetric(horizontal=18),
            border_radius=12,
            bgcolor=active_bg if is_active else "#F1F5F9",
            border=ft.border.all(1, active_border if is_active else GRAY_BORDER),
            alignment=ft.Alignment(0, 0),
            content=tab_inner(label, icon_name, color),
        )

    def set_tab_visual(tab, label, icon_name, theme="blue", active=False):
        if theme == "blue":
            color = BLUE
            bg = BLUE_BG
            border = BLUE_BORDER
        else:
            color = GREEN
            bg = GREEN_BG
            border = GREEN_BORDER

        tab.bgcolor = bg if active else "#F1F5F9"
        tab.border = ft.border.all(1, border if active else GRAY_BORDER)
        tab.content = tab_inner(label, icon_name, color if active else TEXT_SUB)

    tab_btn_new = make_tab_button(
        "供應商新料",
        ft.Icons.BUSINESS,
        BLUE,
        BLUE_BG,
        BLUE_BORDER,
        is_active=True,
    )

    tab_btn_rec = make_tab_button(
        "廠內回用料",
        ft.Icons.FACTORY,
        GREEN,
        GREEN_BG,
        GREEN_BORDER,
        is_active=False,
    )

    def switch_tab(tab_name):
        status_bar.visible = False
        status_slot.visible = False

        if tab_name == "new":
            set_tab_visual(tab_btn_new, "供應商新料", ft.Icons.BUSINESS, "blue", True)
            set_tab_visual(tab_btn_rec, "廠內回用料", ft.Icons.FACTORY, "green", False)
            content_area.content = new_tab_content
        else:
            set_tab_visual(tab_btn_new, "供應商新料", ft.Icons.BUSINESS, "blue", False)
            set_tab_visual(tab_btn_rec, "廠內回用料", ft.Icons.FACTORY, "green", True)
            content_area.content = rec_tab_content

        safe_update(tab_btn_new)
        safe_update(tab_btn_rec)
        safe_update(content_area)
        safe_update(status_slot)

    tab_btn_new.on_click = lambda e: switch_tab("new")
    tab_btn_rec.on_click = lambda e: switch_tab("rec")

    # =====================================================
    # 10. Supabase 資料載入
    # =====================================================
    def refresh_material_dropdown():
        if material_dict:
            n_mat.options = [ft.dropdown.Option(o) for o in sorted(material_dict.keys())]
            if n_mat.value not in material_dict:
                n_mat.value = None
        else:
            n_mat.options = [ft.dropdown.Option("無可用原料")]
            n_mat.value = "無可用原料"

        safe_update(n_mat)

    def refresh_from_service(silent: bool = False):
        if not is_active_view():
            return

        result = load_inventory_page_data()

        if not is_active_view():
            return

        if not result.ok:
            data_loaded["done"] = False
            set_status(result.message, is_error=True)
            return

        data = result.data or {}

        material_dict.clear()
        material_dict.update(data.get("material_options", {}))

        stock_rows.clear()
        stock_rows.extend(data.get("stock_rows", []))

        recent_purchase_records.clear()
        recent_purchase_records.extend(data.get("recent_purchase_records", []))

        recent_recycled_records.clear()
        recent_recycled_records.extend(data.get("recent_recycled_records", []))

        refresh_recent_purchase_panel()
        refresh_recent_recycled_panel()
        refresh_material_dropdown()

        data_loaded["done"] = True
        check_new_batch(None, do_update=False)
        check_rec_batch(None, do_update=False)

        safe_update(n_batch)
        safe_update(r_id)
        safe_update(btn_new)
        safe_update(btn_rec)

        if not silent:
            set_status("Supabase 資料同步完成，可開始作業。", theme="green", auto_hide=True)


    def load_bg_data():
        try:
            time.sleep(0.6)
            if not is_active_view():
                return
            set_status("背景同步 Supabase 資料...", theme="blue", loading=True)
            refresh_from_service(silent=False)

        except Exception as ex:
            if not is_active_view():
                return
            data_loaded["done"] = False
            print(f"背景載入失敗: {ex}")
            set_status(f"背景載入失敗：{ex}", is_error=True)


    def start_bg_load():
        threading.Thread(target=load_bg_data, daemon=True).start()

    threading.Timer(0.3, start_bg_load).start()

    # =====================================================
    # 11. 初始狀態
    # =====================================================
    check_new_batch(None, do_update=False)
    check_rec_batch(None, do_update=False)

    # =====================================================
    # 12. 最終畫面
    # =====================================================
    return ft.Container(
        bgcolor="#F8FAFC",
        content=ft.Column(
            controls=[
                title_block(),
                status_slot,
                ft.Row(
                    controls=[tab_btn_new, tab_btn_rec],
                    spacing=15,
                    scroll=ft.ScrollMode.AUTO,
                ),
                ft.Divider(height=22, color=BORDER),
                content_area,
                ft.Container(height=70),
            ],
            spacing=10,
        ),
    )
