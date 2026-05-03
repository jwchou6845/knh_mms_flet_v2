# views/spinneret.py
import flet as ft
import threading
import time

from services.spinneret_service import (
    load_spinneret_page_data,
    update_spinneret_status,
)

def SpinneretContent(page: ft.Page):
    # ── 1. 同步抓取資料：Supabase ──
    print("====== [系統提示] 開始同步讀取 Supabase (噴頭組件狀態) ======")

    load_result = load_spinneret_page_data()
    page_data = load_result.data or {}

    records = page_data.get("items", [])
    kpi_data = page_data.get("kpi", {})
    status_options = page_data.get("status_options", [])
    spec_options = page_data.get("spec_options", [])

    if load_result.ok:
        print(f"====== [系統提示] 成功抓取 {len(records)} 筆資料 ======")
    else:
        print(f"讀取噴頭狀態失敗: {load_result.message}")

    # ── 2. 狀態列 (🌟 核心修復：固定元件，只改屬性，杜絕 736 報錯) ──
    status_icon = ft.Icon(ft.Icons.INFO_OUTLINE, color="#64748B", size=16)
    status_text = ft.Text("", color="#64748B", size=13, weight=ft.FontWeight.BOLD)

    status_bar = ft.Container(
        content=ft.Row([status_icon, status_text]),
        padding=ft.padding.symmetric(horizontal=16, vertical=12),
        border_radius=8,
        visible=False,
        width=float("inf")
    )

    def set_status(msg, is_error=False, is_loading=False, theme="blue"):
        status_bar.visible = True
        bg_color, border_color, text_color, icon_name = "#F8FAFC", "#E2E8F0", "#64748B", ft.Icons.INFO_OUTLINE

        if is_error:
            bg_color, border_color, text_color, icon_name = "#FEF2F2", "#FECACA", "#DC2626", ft.Icons.ERROR_OUTLINE
        elif "成功" in msg:
            icon_name = ft.Icons.CHECK_CIRCLE_OUTLINE
            bg_color, border_color, text_color = ("#F0FDF4", "#BBF7D0", "#16A34A") if theme == "green" else ("#E5F0FF", "#B0D0FF", "#2563EB")
        elif is_loading:
            icon_name = ft.Icons.SYNC
            bg_color, border_color, text_color = ("#F0FDF4", "#BBF7D0", "#16A34A") if theme == "green" else ("#E5F0FF", "#B0D0FF", "#2563EB")

        status_bar.bgcolor = bg_color
        status_bar.border = ft.border.all(1, border_color)
        
        # 🌟 只更改現有元件的屬性
        status_icon.name = icon_name
        status_icon.color = text_color
        status_text.value = msg
        status_text.color = text_color
        
        status_bar.update()

        if "成功" in msg:
            def auto_hide():
                time.sleep(3)
                status_bar.visible = False
                try: status_bar.update()
                except: pass
            threading.Thread(target=auto_hide, daemon=True).start()

    # ── 3. 頂部 KPI 統計數據 (🌟 新增：即時連動引擎) ──
    lbl_kpi_total = ft.Text("0", size=20, weight=ft.FontWeight.BOLD, color="#3B82F6")
    lbl_kpi_run = ft.Text("0", size=20, weight=ft.FontWeight.BOLD, color="#16A34A")
    lbl_kpi_clean = ft.Text("0", size=20, weight=ft.FontWeight.BOLD, color="#EA580C")
    lbl_kpi_standby = ft.Text("0", size=20, weight=ft.FontWeight.BOLD, color="#6366F1")

    def update_kpi_numbers():
        kpi_data["total"] = len(records)
        kpi_data["running"] = sum(1 for r in records if "生產" in r.get("current_status", ""))
        kpi_data["cleaning"] = sum(
            1 for r in records
            if any(x in r.get("current_status", "") for x in ["燒解", "清潔"])
        )
        kpi_data["standby"] = sum(
            1 for r in records
            if r.get("current_status", "") in ["預熱爐備用中", "組裝中", "組裝完成備用中", "尚未組裝", "待下機"]
        )

        lbl_kpi_total.value = str(kpi_data.get("total", 0))
        lbl_kpi_run.value = str(kpi_data.get("running", 0))
        lbl_kpi_clean.value = str(kpi_data.get("cleaning", 0))
        lbl_kpi_standby.value = str(kpi_data.get("standby", 0))

    update_kpi_numbers() # 頁面載入時初始化算一次

    def build_kpi_card(lbl_control, title, subtitle, bg_color):
        return ft.Container(
            padding=15, bgcolor="#FFFFFF", border_radius=12, border=ft.border.all(1, "#E2E8F0"),
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=3, color="#05000000", offset=ft.Offset(0, 1)),
            content=ft.Row([
                ft.Container(
                    width=45, height=45, bgcolor=bg_color, border_radius=8,
                    alignment=ft.Alignment(0, 0),
                    content=lbl_control
                ),
                ft.Column([
                    ft.Text(title, size=15, weight=ft.FontWeight.BOLD, color="#111827"),
                    ft.Text(subtitle, size=11, color="#64748B")
                ], spacing=2)
            ], spacing=15)
        )

    kpi_row = ft.ResponsiveRow([
        ft.Column(col={"sm": 6, "xl": 3}, controls=[build_kpi_card(lbl_kpi_total, "SET 總數", "目前系統紀錄", "#EFF6FF")]),
        ft.Column(col={"sm": 6, "xl": 3}, controls=[build_kpi_card(lbl_kpi_run, "生產中", "上機運作狀態", "#F0FDF4")]),
        ft.Column(col={"sm": 6, "xl": 3}, controls=[build_kpi_card(lbl_kpi_clean, "清潔 / 燒解", "保養維護階段", "#FFF7ED")]),
        ft.Column(col={"sm": 6, "xl": 3}, controls=[build_kpi_card(lbl_kpi_standby, "備用 / 待機", "等待上線或下機", "#EEF2FF")]),
    ], spacing=15, run_spacing=15)

    # ── 4. UI 元件與狀態配色 ──
    def ui_dropdown(label, options):
        return ft.Dropdown(
            label=label,
            options=[ft.dropdown.Option(o) for o in options],
            bgcolor="#F1F5F9", border_color="#E2E8F0", border_radius=12,
            text_size=14, content_padding=ft.padding.symmetric(horizontal=16, vertical=14),
            expand=True
        )

    def ui_button(label, icon_name, bg_color, text_color, on_click_func):
        return ft.ElevatedButton(
            content=ft.Row([
                ft.Icon(icon_name, color=text_color, size=18),
                ft.Text(label, color=text_color, weight=ft.FontWeight.BOLD, size=14)
            ], alignment=ft.MainAxisAlignment.CENTER),
            style=ft.ButtonStyle(bgcolor=bg_color, shape=ft.RoundedRectangleBorder(radius=12), padding=ft.padding.symmetric(vertical=15)),
            on_click=on_click_func, expand=True
        )

    # 選項清單由 services.spinneret_service 統一提供，對應 Airtable single select 設定。

    def get_status_style(status_val):
        if "生產" in status_val: 
            return "#F0FDF4", "#16A34A" # 綠
        elif any(keyword in status_val for keyword in ["燒解", "清潔", "組裝"]): 
            return "#FFF7ED", "#EA580C" # 橘
        else: 
            return "#E5F0FF", "#2563EB" # 藍

    def get_fixed_border_color(comp_name):
        name_upper = comp_name.upper()
        if "SET#1" in name_upper: return "#93C5FD" # 淡藍
        elif "SET#2" in name_upper: return "#86EFAC" # 淡綠
        elif "SET#3" in name_upper: return "#FDBA74" # 淡橘
        elif "SET#4" in name_upper: return "#D8B4FE" # 淡紫
        return "#E2E8F0"

    # ── 5. 卡片生成器 ──
    def create_spinneret_card(record):
        rec_id = record["id"]

        comp_name = record.get("set_code", "未知組件")
        current_status = record.get("current_status", "尚未組裝")
        current_spec = record.get("plate_spec", "無")
        time_str = record.get("status_updated_at", "尚無紀錄")
        note_value = record.get("note", "")

        bg_color, txt_color = get_status_style(current_status)
        bar_color = get_fixed_border_color(comp_name)

        lbl_status = ft.Text(current_status, color=txt_color, weight=ft.FontWeight.BOLD, size=13)
        pill_status = ft.Container(
            content=lbl_status,
            bgcolor=bg_color,
            border_radius=16,
            padding=ft.padding.symmetric(horizontal=12, vertical=4),
        )

        lbl_spec = ft.Text(f"{current_spec}", size=14, color="#111827", weight=ft.FontWeight.W_500)
        lbl_time = ft.Text(f"{time_str}", size=12, color="#64748B")

        lbl_note = ft.Text(
            note_value if note_value else "無備註",
            size=12,
            color="#64748B",
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        dd_status = ui_dropdown("更新目前狀態", status_options)
        dd_status.value = current_status if current_status in status_options else status_options[0]

        dd_spec = ui_dropdown("更新分配板規格", spec_options)
        dd_spec.value = current_spec if current_spec in spec_options else spec_options[-1]

        note_field = ft.TextField(
            label="備註",
            value=note_value,
            hint_text="例：待確認螺絲、分配板需清潔、下次上機前再確認",
            multiline=True,
            min_lines=2,
            max_lines=3,
            border_radius=12,
            border_color="#E2E8F0",
            focused_border_color="#2563EB",
            bgcolor="#F1F5F9",
            filled=True,
            text_size=14,
            content_padding=ft.padding.symmetric(horizontal=16, vertical=12),
        )

        card = ft.Container(
            border=ft.border.Border(
                top=ft.border.BorderSide(1, "#E2E8F0"),
                right=ft.border.BorderSide(1, "#E2E8F0"),
                bottom=ft.border.BorderSide(1, "#E2E8F0"),
                left=ft.border.BorderSide(6, bar_color)
            ),
            border_radius=12,
            bgcolor="#FFFFFF",
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=3, color="#05000000", offset=ft.Offset(0, 1)),
        )

        def save_changes(e):
            new_st = dd_status.value
            new_sp = dd_spec.value
            new_note = str(note_field.value or "").strip()

            set_status(f"正在更新 {comp_name}...", is_loading=True, theme="blue")

            try:
                current_user_id = None
                current_user_name = "未登入"

                if hasattr(page, "session_data") and isinstance(page.session_data, dict):
                    current_user_id = page.session_data.get("user_id")
                    current_user_name = page.session_data.get("user_name", "未登入")

                result = update_spinneret_status(
                    row_id=rec_id,
                    current_status=new_st,
                    plate_spec=new_sp,
                    note=new_note,
                    updated_by_user_id=current_user_id,
                    updated_by_name=current_user_name,
                )

                if not result.ok:
                    set_status(result.message, is_error=True)
                    return

                updated_item = result.data or {}

                # 更新本機端 records 陣列，讓 KPI 可以重新計算
                record.update(updated_item)

                update_kpi_numbers()
                kpi_row.update()

                # 局部更新卡片 UI
                lbl_status.value = updated_item.get("current_status", new_st)
                new_bg, new_txt = get_status_style(lbl_status.value)
                lbl_status.color = new_txt
                pill_status.bgcolor = new_bg

                lbl_spec.value = updated_item.get("plate_spec", new_sp)
                lbl_time.value = updated_item.get("status_updated_at", "")
                lbl_note.value = updated_item.get("note") or "無備註"

                editor_panel.expanded = False

                # 統一由父容器 card 執行 update，避免生命週期打架
                card.update()

                set_status(f"{comp_name} 更新成功！", theme="green")

            except Exception as ex:
                set_status(f"更新失敗: {ex}", is_error=True)

        btn_save = ui_button("儲存變更", ft.Icons.SAVE_OUTLINED, "#E5F0FF", "#2563EB", save_changes)

        editor_panel = ft.ExpansionTile(
            title=ft.Text("變更組件狀態、規格與備註", size=13, weight=ft.FontWeight.BOLD, color="#64748B"),
            collapsed_text_color="#94A3B8",
            text_color="#2563EB",
            controls=[
                ft.Container(
                    padding=ft.padding.only(left=15, right=15, bottom=15, top=15),
                    content=ft.Column(
                        controls=[
                            ft.Row([dd_status, dd_spec], spacing=15),
                            note_field,
                            ft.Container(height=5),
                            ft.Row([btn_save]),
                        ],
                        spacing=12,
                    ),
                )
            ],
        )

        card.content = ft.Column([
            ft.Container(
                padding=ft.padding.only(top=15, left=20, right=20, bottom=5),
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.MEMORY_OUTLINED, color="#475569", size=20),
                        ft.Text(comp_name, size=16, weight=ft.FontWeight.BOLD, color="#111827")
                    ], spacing=10),
                    ft.Divider(height=15, color="#F1F5F9"),

                    ft.Row([
                        ft.Column([
                            ft.Row([ft.Text("目前狀態：", size=13, color="#64748B", weight=ft.FontWeight.W_500), pill_status]),
                            ft.Container(height=2),
                            ft.Row([ft.Icon(ft.Icons.ACCESS_TIME, size=13, color="#94A3B8"), ft.Text("最後更新：", size=12, color="#64748B"), lbl_time]),
                            ft.Container(height=2),
                            ft.Row([ft.Icon(ft.Icons.NOTES_OUTLINED, size=13, color="#94A3B8"), ft.Text("備註：", size=12, color="#64748B"), lbl_note]),
                        ], expand=1),

                        ft.Column([
                            ft.Row([ft.Text("分配板規格：", size=13, color="#64748B", weight=ft.FontWeight.W_500), lbl_spec])
                        ], expand=1, alignment=ft.MainAxisAlignment.START)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.START)
                ], spacing=8)
            ),
            editor_panel
        ], spacing=0)

        return ft.Column(col={"sm": 12, "md": 12, "xl": 6}, controls=[card])

    # ── 6. 生成佈局 ──
    if not load_result.ok:
        set_status(load_result.message, is_error=True)

    card_elements = []
    if not records:
        card_elements = [ft.Text("⚠️ 找不到噴頭組件資料，請確認 Supabase spinneret_sets 是否已有建檔。", color="#DC2626")]
    else:
        for rec in records:
            card_elements.append(create_spinneret_card(rec))

    grid_layout = ft.ResponsiveRow(controls=card_elements, spacing=20, run_spacing=20)

    # ── 7. 最終畫面回傳 ──
    return ft.Column([
        ft.Row([
            ft.Icon(ft.Icons.MEMORY, size=24, color="#374151"),
            ft.Text("噴頭組件狀態", size=24, weight=ft.FontWeight.BOLD, color="#111827")
        ]),
        ft.Text("即時掌握各 SET 生產、待機、清潔與分配板規格", size=13, color="#64748B"),
        status_bar,
        ft.Container(height=10),
        kpi_row, 
        ft.Divider(height=20, color="#E2E8F0"),
        grid_layout,
        ft.Container(height=50)
    ], spacing=10)