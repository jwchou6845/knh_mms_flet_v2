# views/reports.py
# Flet 0.84 / Python
# KNH MMS 報表中心 UI Shell v1
#
# 第一階段：UI 空殼
# - 方案 D：三步驟流程
# - 快速報表 8 項
# - 全條件篩選第一版表單
# - 結果預覽區
#
# 下一階段再接：
# - repositories/reports_repo.py
# - services/reports_service.py
# - CSV 匯出

import flet as ft

from services.reports_service import (
    build_report_filter_options,
    export_report_to_csv,
    run_advanced_query,
    run_quick_report,
)


def ReportsContent(page: ft.Page):
    # =====================================================
    # 0. 狀態
    # =====================================================
    selected_mode = {"value": "quick"}  # quick / advanced
    selected_quick_report = {"value": "本月用料摘要"}
    selected_data_type = {"value": "打料紀錄"}
    step_state = {"value": 1}
    current_report_data = {
        "title": "尚未產生報表",
        "columns": ["日期", "資料類型", "名稱", "數量", "狀態"],
        "rows": [],
        "count": 0,
        "summary_text": "請先選擇快速報表或套用篩選條件。",
    }

    filter_options_result = build_report_filter_options()
    filter_options = filter_options_result.data or {}

    # =====================================================
    # 1. 色彩設定
    # =====================================================
    BG = "#F8FAFC"
    CARD = "#FFFFFF"
    BORDER = "#DDE7F3"
    SOFT = "#F8FAFC"

    TEXT_MAIN = "#0F172A"
    TEXT_SUB = "#64748B"
    TEXT_MUTED = "#94A3B8"

    BLUE = "#2563EB"
    BLUE_SOFT = "#E5F0FF"
    BLUE_BORDER = "#BFDBFE"
    BLUE_BTN = "#2F80ED"

    GREEN = "#059669"
    GREEN_SOFT = "#ECFDF5"
    GREEN_BORDER = "#A7F3D0"

    ORANGE = "#EA580C"
    ORANGE_SOFT = "#FFF7ED"
    ORANGE_BORDER = "#FDBA74"

    RED = "#DC2626"
    RED_SOFT = "#FEF2F2"
    RED_BORDER = "#FECACA"

    PURPLE = "#7C3AED"
    PURPLE_SOFT = "#F3E8FF"
    PURPLE_BORDER = "#D8B4FE"

    # =====================================================
    # 2. 共用工具
    # =====================================================
    def safe_update(control):
        try:
            control.update()
        except Exception:
            pass

    def safe_page_update():
        try:
            page.update()
        except Exception:
            pass

    def show_msg(msg, color=BLUE):
        snack = ft.SnackBar(
            content=ft.Text(str(msg), color="white", weight=ft.FontWeight.W_600),
            bgcolor=color,
            duration=3000,
        )
        page.overlay.append(snack)
        snack.open = True
        safe_page_update()

    def card_box(content, padding=18, border_color=BORDER, bgcolor=CARD):
        return ft.Container(
            bgcolor=bgcolor,
            border=ft.border.all(1, border_color),
            border_radius=18,
            padding=padding,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=10,
                color="#06000000",
                offset=ft.Offset(0, 2),
            ),
            content=content,
        )

    def section_title(icon_name, title, subtitle=None, icon_color=BLUE):
        controls = [
            ft.Row(
                controls=[
                    ft.Container(
                        width=46,
                        height=46,
                        border_radius=14,
                        bgcolor="#FFFFFF",
                        border=ft.border.all(1, BORDER),
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(icon_name, size=25, color=icon_color),
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(title, size=21, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                            ft.Text(subtitle or "", size=13, color=TEXT_SUB, visible=bool(subtitle)),
                        ],
                        spacing=3,
                        expand=True,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        ]
        return ft.Column(controls=controls, spacing=0)

    # =====================================================
    # 3. Stepper
    # =====================================================
    step_controls = []

    def make_step(index: int, label: str):
        active = index == step_state["value"]
        done = index < step_state["value"]

        circle_bg = BLUE if active or done else "#E5E7EB"
        circle_fg = "white" if active or done else "#475569"
        text_color = BLUE if active else "#64748B"

        return ft.Column(
            controls=[
                ft.Container(
                    width=36,
                    height=36,
                    border_radius=18,
                    bgcolor=circle_bg,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Text(
                        str(index),
                        size=16,
                        color=circle_fg,
                        weight=ft.FontWeight.BOLD,
                    ),
                ),
                ft.Text(label, size=13, color=text_color, weight=ft.FontWeight.BOLD if active else ft.FontWeight.W_500),
            ],
            spacing=5,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    stepper_row = ft.Row(spacing=0)

    def refresh_stepper():
        stepper_row.controls = [
            make_step(1, "選報表方式"),
            ft.Container(expand=True, height=2, bgcolor=BLUE if step_state["value"] >= 2 else "#E5E7EB"),
            make_step(2, "設定條件"),
            ft.Container(expand=True, height=2, bgcolor=BLUE if step_state["value"] >= 3 else "#E5E7EB"),
            make_step(3, "匯出結果"),
        ]
        safe_update(stepper_row)

    stepper_card = card_box(stepper_row, padding=16)

    # =====================================================
    # 4. 報表方式選擇
    # =====================================================
    mode_cards = []

    def refresh_mode_cards():
        for card in mode_cards:
            active = card.data == selected_mode["value"]
            card.border = ft.border.all(2 if active else 1, BLUE if active else BORDER)
            card.bgcolor = BLUE_SOFT if active else CARD
            icon_box = card.content.controls[0]
            text_col = card.content.controls[1]
            check_icon = card.content.controls[2]

            icon_box.bgcolor = "#DBEAFE" if active else "#F8FAFC"
            icon_box.border = ft.border.all(1, BLUE_BORDER if active else BORDER)
            icon_box.content.color = BLUE if active else TEXT_MUTED
            text_col.controls[0].color = TEXT_MAIN
            text_col.controls[1].color = TEXT_SUB
            check_icon.visible = active

            safe_update(card)

    def make_mode_card(mode_value, title, subtitle, icon_name):
        def click(e):
            selected_mode["value"] = mode_value
            step_state["value"] = 1
            refresh_mode_cards()
            refresh_stepper()
            refresh_preview()

        card = ft.Container(
            data=mode_value,
            expand=True,
            height=94,
            border_radius=16,
            bgcolor=CARD,
            border=ft.border.all(1, BORDER),
            padding=14,
            on_click=click,
            content=ft.Row(
                controls=[
                    ft.Container(
                        width=54,
                        height=54,
                        border_radius=27,
                        bgcolor="#F8FAFC",
                        border=ft.border.all(1, BORDER),
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(icon_name, size=28, color=TEXT_MUTED),
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                            ft.Text(subtitle, size=13, color=TEXT_SUB),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color=BLUE, size=26, visible=False),
                ],
                spacing=13,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        mode_cards.append(card)
        return card

    mode_row = ft.ResponsiveRow(
        columns=12,
        spacing=14,
        run_spacing=14,
        controls=[
            ft.Container(
                col={"xs": 12, "md": 6},
                content=make_mode_card(
                    "quick",
                    "快速報表",
                    "常用報表快速產出",
                    ft.Icons.FLASH_ON_OUTLINED,
                ),
            ),
            ft.Container(
                col={"xs": 12, "md": 6},
                content=make_mode_card(
                    "advanced",
                    "全條件篩選",
                    "自訂條件彈性查詢",
                    ft.Icons.FILTER_ALT_OUTLINED,
                ),
            ),
        ],
    )

    # =====================================================
    # 5. 快速報表 8 項
    # =====================================================
    quick_cards = []

    QUICK_REPORTS = [
        ("本月用料摘要", ft.Icons.DESCRIPTION_OUTLINED, BLUE, BLUE_SOFT, BLUE_BORDER),
        ("上月用料摘要", ft.Icons.CALENDAR_MONTH_OUTLINED, BLUE, BLUE_SOFT, BLUE_BORDER),
        ("指定月份用料摘要", ft.Icons.EVENT_NOTE_OUTLINED, PURPLE, PURPLE_SOFT, PURPLE_BORDER),
        ("目前低水位清單", ft.Icons.WATER_DROP_OUTLINED, ORANGE, ORANGE_SOFT, ORANGE_BORDER),
        ("目前庫存總表", ft.Icons.INVENTORY_2_OUTLINED, GREEN, GREEN_SOFT, GREEN_BORDER),
        ("本月入庫紀錄", ft.Icons.FILE_DOWNLOAD_OUTLINED, BLUE, BLUE_SOFT, BLUE_BORDER),
        ("保養逾期清單", ft.Icons.HANDYMAN_OUTLINED, ORANGE, ORANGE_SOFT, ORANGE_BORDER),
        ("未完成交接待辦", ft.Icons.ASSIGNMENT_TURNED_IN_OUTLINED, PURPLE, PURPLE_SOFT, PURPLE_BORDER),
    ]

    def refresh_quick_cards():
        for card in quick_cards:
            active = card.data == selected_quick_report["value"]
            theme = card.extra_theme
            card.border = ft.border.all(2 if active else 1, theme["border"] if active else BORDER)
            card.bgcolor = theme["soft"] if active else CARD
            card.content.controls[2].visible = active
            safe_update(card)

    def make_quick_card(label, icon_name, color, soft, border):
        def click(e):
            selected_quick_report["value"] = label
            selected_mode["value"] = "quick"
            step_state["value"] = 2
            refresh_mode_cards()
            refresh_quick_cards()
            refresh_stepper()

            month_value = report_month.value if label == "指定月份用料摘要" else None
            result = run_quick_report(label, month_value=month_value)
            set_report_result(result)

        card = ft.Container(
            data=label,
            col={"xs": 6, "md": 3},
            height=104,
            border_radius=14,
            bgcolor=CARD,
            border=ft.border.all(1, BORDER),
            padding=12,
            on_click=click,
            content=ft.Column(
                controls=[
                    ft.Icon(icon_name, size=27, color=color),
                    ft.Text(label, size=14, color=TEXT_MAIN, weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER),
                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=20, color=color, visible=False),
                ],
                spacing=5,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        card.extra_theme = {"color": color, "soft": soft, "border": border}
        quick_cards.append(card)
        return card

    quick_grid = ft.ResponsiveRow(
        columns=12,
        spacing=12,
        run_spacing=12,
        controls=[make_quick_card(*item) for item in QUICK_REPORTS],
    )

    # =====================================================
    # 6. 條件設定
    # =====================================================
    data_type_buttons = []

    def refresh_data_type_buttons():
        for btn in data_type_buttons:
            active = btn.data == selected_data_type["value"]
            btn.bgcolor = BLUE if active else CARD
            btn.border = ft.border.all(1, BLUE if active else BORDER)
            btn.content.color = "white" if active else TEXT_SUB
            btn.content.weight = ft.FontWeight.BOLD if active else ft.FontWeight.W_500
            safe_update(btn)

    def make_data_type_button(label):
        def click(e):
            selected_data_type["value"] = label
            selected_mode["value"] = "advanced"
            step_state["value"] = 2
            refresh_mode_cards()
            refresh_data_type_buttons()
            refresh_stepper()
            refresh_preview()

        btn = ft.Container(
            data=label,
            height=42,
            border_radius=13,
            bgcolor=CARD,
            border=ft.border.all(1, BORDER),
            alignment=ft.Alignment(0, 0),
            on_click=click,
            content=ft.Text(label, size=14, color=TEXT_SUB),
        )
        data_type_buttons.append(btn)
        return btn

    data_type_row = ft.ResponsiveRow(
        columns=12,
        spacing=10,
        run_spacing=10,
        controls=[
            ft.Container(col={"xs": 6, "md": 3}, content=make_data_type_button("打料紀錄")),
            ft.Container(col={"xs": 6, "md": 3}, content=make_data_type_button("入庫紀錄")),
            ft.Container(col={"xs": 6, "md": 3}, content=make_data_type_button("保養紀錄")),
            ft.Container(col={"xs": 6, "md": 3}, content=make_data_type_button("交接紀錄")),
        ],
    )

    def make_field(label, hint="", value=""):
        return ft.TextField(
            label=label,
            value=value,
            hint_text=hint,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE,
            bgcolor=SOFT,
            filled=True,
            text_size=14,
            height=54,
            content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
        )

    def make_dropdown(label, options, value=None):
        return ft.Dropdown(
            label=label,
            options=[ft.dropdown.Option(o) for o in options],
            value=value,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE,
            bgcolor=SOFT,
            filled=True,
            height=54,
            text_size=14,
            content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
        )


    def set_dropdown_options(dropdown, options, keep_value=True):
        current = dropdown.value
        normalized = list(options or ["全部"])

        if "全部" not in normalized:
            normalized.insert(0, "全部")

        dropdown.options = [ft.dropdown.Option(o) for o in normalized]

        if keep_value and current in normalized:
            dropdown.value = current
        else:
            dropdown.value = normalized[0] if normalized else None

        safe_update(dropdown)


    date_start = make_field("日期起", "YYYY/MM/DD", "2026/05/01")
    date_end = make_field("日期迄", "YYYY/MM/DD", "2026/05/31")
    report_month = make_field("指定月份", "YYYY-MM，例如 2026-04", "2026-04")

    category_dd = make_dropdown(
        "類別",
        filter_options.get("categories", ["全部", "新料", "母粒", "回用料", "清潔", "耗材更換", "異常", "待辦"]),
        "全部",
    )
    material_field = make_dropdown(
        "原料種類",
        filter_options.get("material_families", ["全部", "PET", "PET308A", "PA6", "RPET", "母粒", "PP"]),
        "全部",
    )
    supplier_dd = make_dropdown(
        "供應商",
        filter_options.get("suppliers", ["全部"]),
        "全部",
    )
    machine_dd = make_dropdown(
        "機台 / 塔別",
        filter_options.get("machines", ["全部", "S1", "S2", "S1-PET", "S1-PA6", "S2-PET", "S2-PA6"]),
        "全部",
    )
    user_dd = make_dropdown(
        "人員",
        filter_options.get("users", ["全部"]),
        "全部",
    )

    def on_material_change(e):
        selected_family = material_field.value or "全部"
        supplier_map = filter_options.get("material_supplier_map", {}) or {}

        if selected_family != "全部" and selected_family in supplier_map:
            set_dropdown_options(supplier_dd, supplier_map.get(selected_family, ["全部"]), keep_value=False)
        else:
            set_dropdown_options(supplier_dd, filter_options.get("suppliers", ["全部"]), keep_value=True)

    material_field.on_change = on_material_change

    condition_grid = ft.ResponsiveRow(
        columns=12,
        spacing=14,
        run_spacing=12,
        controls=[
            ft.Container(col={"xs": 12, "md": 4}, content=date_start),
            ft.Container(col={"xs": 12, "md": 4}, content=date_end),
            ft.Container(col={"xs": 12, "md": 4}, content=report_month),
            ft.Container(col={"xs": 12, "md": 6}, content=category_dd),
            ft.Container(col={"xs": 12, "md": 6}, content=material_field),
            ft.Container(col={"xs": 12, "md": 6}, content=supplier_dd),
            ft.Container(col={"xs": 12, "md": 6}, content=machine_dd),
            ft.Container(col={"xs": 12}, content=user_dd),
        ],
    )

    # =====================================================
    # 7. 結果預覽
    # =====================================================
    preview_title = ft.Text("結果預覽", size=20, weight=ft.FontWeight.BOLD, color=TEXT_MAIN)
    preview_badge = ft.Container(
        height=30,
        padding=ft.padding.symmetric(horizontal=12),
        border_radius=15,
        bgcolor=BLUE_SOFT,
        border=ft.border.all(1, BLUE_BORDER),
        content=ft.Text("共 0 筆", size=13, color=BLUE, weight=ft.FontWeight.BOLD),
        alignment=ft.Alignment(0, 0),
    )

    preview_table = ft.Column(spacing=0)

    def preview_row(values, header=False):
        controls = []

        for value in values:
            controls.append(
                ft.Text(
                    str(value),
                    size=13,
                    color=TEXT_MAIN,
                    weight=ft.FontWeight.BOLD if header else ft.FontWeight.NORMAL,
                    max_lines=2 if not header else 1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    expand=1,
                )
            )

        return ft.Container(
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            bgcolor="#F8FAFC" if header else "#FFFFFF",
            border=ft.border.only(bottom=ft.border.BorderSide(1, "#E5EAF2")),
            content=ft.Row(
                controls=controls,
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def refresh_preview():
        columns = current_report_data.get("columns") or ["日期", "資料類型", "名稱", "數量", "狀態"]
        rows = current_report_data.get("rows") or []
        title = current_report_data.get("title") or "結果預覽"
        count = current_report_data.get("count", len(rows))
        summary_text = current_report_data.get("summary_text", "")

        preview_title.value = f"結果預覽｜{title}"
        preview_badge.content.value = f"共 {count} 筆"

        preview_table.controls = [preview_row(columns, header=True)]

        if rows:
            for row in rows[:5]:
                preview_table.controls.append(
                    preview_row([row.get(col, "") for col in columns], header=False)
                )
        else:
            preview_table.controls.append(
                ft.Container(
                    padding=18,
                    bgcolor="#FFFFFF",
                    content=ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.INFO_OUTLINE, size=30, color=TEXT_MUTED),
                            ft.Text("目前沒有資料", size=15, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                            ft.Text(summary_text or "請先產生報表。", size=13, color=TEXT_SUB),
                        ],
                        spacing=8,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )

        safe_update(preview_title)
        safe_update(preview_badge)
        safe_update(preview_table)

    def set_report_result(result):
        if not result.ok:
            show_msg(result.message, RED)
            return

        data = result.data or {}
        current_report_data.clear()
        current_report_data.update(
            {
                "title": data.get("title", "報表結果"),
                "columns": data.get("columns", []),
                "rows": data.get("rows", []),
                "count": data.get("count", len(data.get("rows", []))),
                "summary_text": data.get("summary_text", ""),
            }
        )
        refresh_preview()

    # =====================================================
    # 8. 動作按鈕
    # =====================================================
    def generate_quick_report(e=None):
        selected_mode["value"] = "quick"
        step_state["value"] = 2
        refresh_mode_cards()
        refresh_quick_cards()
        refresh_stepper()

        result = run_quick_report(
            selected_quick_report["value"],
            month_value=report_month.value if selected_quick_report["value"] == "指定月份用料摘要" else None,
        )
        set_report_result(result)

    def apply_conditions(e):
        if selected_mode["value"] == "quick":
            generate_quick_report(e)
            return

        selected_mode["value"] = "advanced"
        step_state["value"] = 2
        refresh_mode_cards()
        refresh_stepper()

        result = run_advanced_query(
            data_type=selected_data_type["value"],
            start_date=date_start.value,
            end_date=date_end.value,
            category=category_dd.value or "全部",
            material_name=material_field.value or "",
            supplier=supplier_dd.value or "全部",
            machine=machine_dd.value or "全部",
            user_name=user_dd.value or "全部",
        )

        set_report_result(result)

    def clear_conditions(e):
        category_dd.value = "全部"
        material_field.value = "全部"
        set_dropdown_options(supplier_dd, filter_options.get("suppliers", ["全部"]), keep_value=False)
        supplier_dd.value = "全部"
        machine_dd.value = "全部"
        user_dd.value = "全部"
        current_report_data.clear()
        current_report_data.update(
            {
                "title": "尚未產生報表",
                "columns": ["日期", "資料類型", "名稱", "數量", "狀態"],
                "rows": [],
                "count": 0,
                "summary_text": "請先選擇快速報表或套用篩選條件。",
            }
        )
        refresh_preview()
        safe_page_update()

    def export_csv(e):
        step_state["value"] = 3
        refresh_stepper()

        result = export_report_to_csv(current_report_data)

        if result.ok:
            show_msg(result.message, GREEN)
        else:
            show_msg(result.message, RED)

    report_month.on_submit = generate_quick_report

    action_row = ft.ResponsiveRow(
        columns=12,
        spacing=12,
        run_spacing=12,
        controls=[
            ft.Container(
                col={"xs": 12, "md": 4},
                content=ft.ElevatedButton(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.FILTER_ALT_OUTLINED, color=BLUE, size=20),
                            ft.Text("產生 / 套用", color=BLUE, weight=ft.FontWeight.BOLD, size=15),
                        ],
                        spacing=8,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    height=50,
                    bgcolor="#FFFFFF",
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=12),
                        side=ft.BorderSide(1, BLUE),
                        elevation=0,
                    ),
                    on_click=apply_conditions,
                ),
            ),
            ft.Container(
                col={"xs": 12, "md": 4},
                content=ft.ElevatedButton(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.REFRESH_OUTLINED, color="#475569", size=20),
                            ft.Text("清除", color="#475569", weight=ft.FontWeight.BOLD, size=15),
                        ],
                        spacing=8,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    height=50,
                    bgcolor="#FFFFFF",
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=12),
                        side=ft.BorderSide(1, BORDER),
                        elevation=0,
                    ),
                    on_click=clear_conditions,
                ),
            ),
            ft.Container(
                col={"xs": 12, "md": 4},
                content=ft.ElevatedButton(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.FILE_DOWNLOAD_OUTLINED, color="white", size=20),
                            ft.Text("匯出 CSV", color="white", weight=ft.FontWeight.BOLD, size=15),
                        ],
                        spacing=8,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    height=50,
                    bgcolor=BLUE_BTN,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=12),
                        elevation=0,
                    ),
                    on_click=export_csv,
                ),
            ),
        ],
    )

    # =====================================================
    # 9. 主版面
    # =====================================================
    header = ft.Row(
        controls=[
            ft.Container(
                width=54,
                height=54,
                border_radius=16,
                bgcolor=BLUE_SOFT,
                alignment=ft.Alignment(0, 0),
                content=ft.Icon(ft.Icons.INSERT_CHART_OUTLINED, size=30, color=BLUE),
            ),
            ft.Column(
                controls=[
                    ft.Text("報表中心", size=28, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                    ft.Text("快速匯出與全條件篩選", size=14, color=TEXT_SUB),
                ],
                spacing=4,
                expand=True,
            ),
        ],
        spacing=16,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    selector_card = card_box(
        content=ft.Column(
            controls=[
                section_title(ft.Icons.TOUCH_APP_OUTLINED, "選擇報表方式", "先選快速報表或全條件篩選", BLUE),
                mode_row,
                quick_grid,
            ],
            spacing=15,
        ),
    )

    condition_card = card_box(
        content=ft.Column(
            controls=[
                section_title(ft.Icons.TUNE_OUTLINED, "條件設定", "快速報表可直接產生，全條件篩選可自訂查詢條件", BLUE),
                data_type_row,
                condition_grid,
                action_row,
            ],
            spacing=15,
        ),
    )

    preview_card = card_box(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.TABLE_CHART_OUTLINED, size=22, color=TEXT_SUB),
                                preview_title,
                            ],
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            expand=True,
                        ),
                        preview_badge,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(
                    border=ft.border.all(1, "#E5EAF2"),
                    border_radius=12,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    content=preview_table,
                ),
                ft.Row(
                    controls=[
                        ft.Text("僅顯示前 5 筆資料", size=12, color=TEXT_MUTED),
                        ft.Container(expand=True),
                        ft.TextButton(
                            "查看全部",
                            icon=ft.Icons.CHEVRON_RIGHT,
                            on_click=lambda e: show_msg("查看全部會在下一階段接上。", BLUE),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=12,
        ),
    )

    refresh_stepper()
    refresh_mode_cards()
    refresh_quick_cards()
    refresh_data_type_buttons()
    refresh_preview()

    return ft.Container(
        bgcolor=BG,
        content=ft.Column(
            controls=[
                header,
                stepper_card,
                selector_card,
                condition_card,
                preview_card,
                ft.Container(height=90),
            ],
            spacing=18,
        ),
    )
