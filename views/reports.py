# views/reports.py
# Flet 0.84 / Python
# KNH MMS 報表中心 - Supabase 版
#
# 本版重點：
# - 快速報表一鍵產生；只有「指定月份用料摘要」需要月份條件
# - 全條件篩選才顯示日期起訖與篩選欄位
# - 結果預覽顯示前 10 筆，查看全部改為頁內展開
# - CSV 匯出入口與目前查詢結果一致
# - 手機 Web 關鍵按鈕使用 Container + Icon + Text，避免 Button 渲染異常
# - 查詢與 CSV 匯出採背景 thread，避免手機 Web 阻塞

from __future__ import annotations

import threading
from datetime import date, datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import flet as ft

from services.reports_service import (
    build_report_filter_options,
    export_report_to_csv,
    run_advanced_query,
    run_quick_report,
)


TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def ReportsContent(page: ft.Page):
    # =====================================================
    # 0. 基本狀態
    # =====================================================
    def now_taipei() -> datetime:
        return datetime.now(TAIPEI_TZ)

    def month_start_string() -> str:
        today = now_taipei().date()
        return today.replace(day=1).strftime("%Y/%m/%d")

    def today_string() -> str:
        return now_taipei().date().strftime("%Y/%m/%d")

    def add_months(target: date, months: int) -> date:
        year = target.year + ((target.month - 1 + months) // 12)
        month = ((target.month - 1 + months) % 12) + 1
        return date(year, month, 1)

    def default_report_month() -> str:
        # 指定月份用料摘要預設使用上個月，符合一般「月報」查詢習慣。
        return add_months(now_taipei().date().replace(day=1), -1).strftime("%Y-%m")

    selected_mode = {"value": "quick"}  # quick / advanced
    selected_quick_report = {"value": "本月用料摘要"}
    selected_data_type = {"value": "打料紀錄"}
    step_state = {"value": 1}
    show_all_rows = {"value": False}
    loading_state = {"value": False, "message": ""}
    status_state = {"message": "正在載入篩選條件", "theme": "blue", "visible": True}

    filter_values = {
        "start_date": month_start_string(),
        "end_date": today_string(),
        "report_month": default_report_month(),
        "category": "全部",
        "material": "全部",
        "supplier": "全部",
        "machine": "全部",
        "user": "全部",
    }

    current_report_data = {
        "title": "尚未產生報表",
        "columns": ["日期", "資料類型", "名稱", "數量", "狀態"],
        "rows": [],
        "count": 0,
        "summary_text": "請先選擇快速報表，或切換到全條件篩選後套用條件。",
    }

    export_state = {
        "path": "",
        "filename": "",
        "url": "",
        "message": "",
    }

    default_filter_options = {
        "categories": ["全部", "新料", "母粒", "回用料", "清潔", "耗材更換", "異常", "待辦"],
        "material_families": ["全部", "PET", "PET308A", "PA6", "RPET", "母粒"],
        "suppliers": ["全部"],
        "machines": ["全部", "S1", "S2", "S1-PET", "S1-PA6", "S2-PET", "S2-PA6"],
        "users": ["全部"],
        "material_supplier_map": {},
    }
    filter_options = dict(default_filter_options)
    filter_options_state = {
        "loading": True,
        "loaded": False,
        "error": "",
    }

    if not hasattr(page, "session_data"):
        page.session_data = {}

    view_token = object()
    page.session_data["_reports_view_token"] = view_token

    def is_active_view() -> bool:
        route = str(getattr(page, "route", "") or "")
        return (
            page.session_data.get("_reports_view_token") is view_token
            and (not route or route == "/reports" or "reports" in route)
        )

    def make_download_url(filename: str) -> str:
        """
        產生手機 Web 可開啟的 CSV 下載 URL。

        Flet 的 page.launch_url() 在部分手機瀏覽器 / WebView 裡，
        使用相對路徑例如 /exports/xxx.csv 可能不會有明顯反應。
        這裡優先依 page.url 組成絕對 URL，失敗時才退回相對路徑。
        """
        clean_name = str(filename or "").strip().lstrip("/")
        if not clean_name:
            return ""

        export_path = f"exports/{clean_name}"

        page_url = str(getattr(page, "url", "") or "").strip()
        if page_url.startswith("http://") or page_url.startswith("https://"):
            parsed = urlparse(page_url)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}/{export_path}"

        return f"/{export_path}"


    # =====================================================
    # 1. 色彩設定
    # =====================================================
    BG = "#F8FAFC"
    CARD = "#FFFFFF"
    BORDER = "#DDE7F3"
    SOFT = "#F8FAFC"
    INPUT_BG = "#F8FAFC"

    TEXT_MAIN = "#0F172A"
    TEXT_SUB = "#64748B"
    TEXT_MUTED = "#94A3B8"

    BLUE = "#2563EB"
    BLUE_SOFT = "#E5F0FF"
    BLUE_BORDER = "#BFDBFE"
    BLUE_BTN = "#2F80ED"
    BLUE_DARK = "#1D4ED8"

    GREEN = "#10B981"
    GREEN_SOFT = "#ECFDF5"
    GREEN_BORDER = "#A7F3D0"

    ORANGE = "#F97316"
    ORANGE_SOFT = "#FFF7ED"
    ORANGE_BORDER = "#FDBA74"

    RED = "#DC2626"
    RED_SOFT = "#FEF2F2"
    RED_BORDER = "#FECACA"

    PURPLE = "#7C3AED"
    PURPLE_SOFT = "#F3E8FF"
    PURPLE_BORDER = "#D8B4FE"

    # =====================================================
    # 2. Root 與共用工具
    # =====================================================
    main_host = ft.Container(expand=True)

    def page_update():
        try:
            page.update()
        except Exception as ex:
            print("reports page.update failed:", ex)

    def show_msg(msg: str, color: str = BLUE):
        snack = ft.SnackBar(
            content=ft.Text(str(msg), color="white", weight=ft.FontWeight.W_600),
            bgcolor=color,
            duration=3200,
        )
        page.overlay.append(snack)
        snack.open = True
        page_update()

    def card_box(content, padding: int = 18, border_color: str = BORDER, bgcolor: str = CARD):
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

    def stable_button(
        label: str,
        icon_name,
        on_click,
        bg: str = BLUE_BTN,
        fg: str = "#FFFFFF",
        border: str | None = None,
        height: int = 50,
        expand: bool = True,
        disabled: bool = False,
    ) -> ft.Container:
        if disabled:
            bg = "#CBD5E1"
            fg = "#FFFFFF"
            border = "#CBD5E1"

        def handle_click(e):
            if disabled or loading_state["value"]:
                return
            if callable(on_click):
                on_click(e)

        return ft.Container(
            expand=expand,
            height=height,
            border_radius=12,
            bgcolor=bg,
            border=ft.border.all(1, border or bg),
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.symmetric(horizontal=12),
            ink=True,
            on_click=handle_click,
            content=ft.Row(
                controls=[
                    ft.Icon(icon_name, size=19, color=fg),
                    ft.Text(
                        label,
                        size=15,
                        color=fg,
                        weight=ft.FontWeight.BOLD,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
        )

    def outline_button(label: str, icon_name, on_click, color: str = BLUE, height: int = 48, expand: bool = True):
        return stable_button(
            label=label,
            icon_name=icon_name,
            on_click=on_click,
            bg="#FFFFFF",
            fg=color,
            border=BLUE_BORDER if color == BLUE else BORDER,
            height=height,
            expand=expand,
        )

    def header_block():
        return ft.Column(
            spacing=10,
            controls=[
                ft.Row(
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
                            expand=True,
                            spacing=4,
                            controls=[
                                ft.Text("報表中心", size=28, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                                ft.Text(
                                    "快速報表一鍵產生，全條件篩選可自訂查詢並匯出 CSV。",
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
                ),
            ],
        )

    def status_badge():
        if not status_state.get("visible"):
            return ft.Container(height=0)

        theme = status_state.get("theme", "blue")
        if theme == "green":
            bg, border, fg, icon = GREEN_SOFT, GREEN_BORDER, GREEN, ft.Icons.CHECK_CIRCLE_OUTLINE
        elif theme == "red":
            bg, border, fg, icon = RED_SOFT, RED_BORDER, RED, ft.Icons.ERROR_OUTLINE
        elif theme == "orange":
            bg, border, fg, icon = ORANGE_SOFT, ORANGE_BORDER, ORANGE, ft.Icons.INFO_OUTLINE
        else:
            bg, border, fg, icon = BLUE_SOFT, BLUE_BORDER, BLUE, ft.Icons.SYNC

        is_busy = bool(loading_state["value"] or filter_options_state.get("loading"))
        leading = ft.ProgressRing(width=15, height=15, stroke_width=2, color=fg) if is_busy else ft.Icon(icon, size=17, color=fg)
        return ft.Container(
            height=36,
            padding=ft.padding.symmetric(horizontal=16),
            border_radius=18,
            bgcolor=bg,
            border=ft.border.all(1, border),
            content=ft.Row(
                controls=[leading, ft.Text(status_state.get("message") or "", size=13, color=fg, weight=ft.FontWeight.W_600)],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def section_title(icon_name, title: str, subtitle: str | None = None, icon_color: str = BLUE):
        return ft.Row(
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
                        ft.Text(subtitle or "", size=13, color=TEXT_SUB, visible=bool(subtitle), max_lines=3),
                    ],
                    spacing=3,
                    expand=True,
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # =====================================================
    # 3. Stepper
    # =====================================================
    def make_step(index: int, label: str):
        active = index == step_state["value"]
        done = index < step_state["value"]
        circle_bg = BLUE if active or done else "#E5E7EB"
        circle_fg = "white" if active or done else "#475569"
        text_color = BLUE if active else "#64748B"

        return ft.Column(
            controls=[
                ft.Container(
                    width=34,
                    height=34,
                    border_radius=17,
                    bgcolor=circle_bg,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Text(str(index), size=15, color=circle_fg, weight=ft.FontWeight.BOLD),
                ),
                ft.Text(label, size=12, color=text_color, weight=ft.FontWeight.BOLD if active else ft.FontWeight.W_500, text_align=ft.TextAlign.CENTER),
            ],
            spacing=5,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def build_stepper():
        return card_box(
            padding=14,
            content=ft.Row(
                spacing=0,
                controls=[
                    make_step(1, "選報表"),
                    ft.Container(expand=True, height=2, bgcolor=BLUE if step_state["value"] >= 2 else "#E5E7EB"),
                    make_step(2, "產生結果"),
                    ft.Container(expand=True, height=2, bgcolor=BLUE if step_state["value"] >= 3 else "#E5E7EB"),
                    make_step(3, "匯出 CSV"),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    # =====================================================
    # 4. 報表模式與快速報表
    # =====================================================
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

    def run_job(kind: str, work_fn):
        if loading_state["value"]:
            return

        loading_state["value"] = True
        loading_state["message"] = kind
        status_state["visible"] = True
        status_state["message"] = kind
        status_state["theme"] = "blue"
        rebuild()

        def worker():
            try:
                result = work_fn()
                if not is_active_view():
                    return

                loading_state["value"] = False

                if not result.ok:
                    status_state["visible"] = True
                    status_state["message"] = result.message or "報表產生失敗"
                    status_state["theme"] = "red"
                    rebuild()
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
                export_state.update({"path": "", "filename": "", "url": "", "message": ""})
                show_all_rows["value"] = False
                step_state["value"] = 2
                status_state["visible"] = True
                status_state["message"] = "報表已產生"
                status_state["theme"] = "green"
                rebuild()

            except Exception as ex:
                if not is_active_view():
                    return
                loading_state["value"] = False
                status_state["visible"] = True
                status_state["message"] = f"報表產生失敗：{ex}"
                status_state["theme"] = "red"
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def select_mode(mode_value: str):
        selected_mode["value"] = mode_value
        step_state["value"] = 1
        show_all_rows["value"] = False
        rebuild()

    def mode_card(mode_value, title, subtitle, icon_name):
        active = selected_mode["value"] == mode_value
        return ft.Container(
            height=90,
            border_radius=16,
            bgcolor=BLUE_SOFT if active else CARD,
            border=ft.border.all(2 if active else 1, BLUE if active else BORDER),
            padding=14,
            ink=True,
            on_click=lambda e, m=mode_value: select_mode(m),
            content=ft.Row(
                controls=[
                    ft.Container(
                        width=50,
                        height=50,
                        border_radius=25,
                        bgcolor="#DBEAFE" if active else "#F8FAFC",
                        border=ft.border.all(1, BLUE_BORDER if active else BORDER),
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(icon_name, size=27, color=BLUE if active else TEXT_MUTED),
                    ),
                    ft.Column(
                        expand=True,
                        spacing=2,
                        controls=[
                            ft.Text(title, size=17, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                            ft.Text(subtitle, size=13, color=TEXT_SUB, max_lines=2),
                        ],
                    ),
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color=BLUE, size=24, visible=active),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def build_mode_row():
        return ft.ResponsiveRow(
            columns=12,
            spacing=12,
            run_spacing=12,
            controls=[
                ft.Container(col={"xs": 12, "md": 6}, content=mode_card("quick", "快速報表", "點選報表後直接產生", ft.Icons.FLASH_ON_OUTLINED)),
                ft.Container(col={"xs": 12, "md": 6}, content=mode_card("advanced", "全條件篩選", "自訂條件彈性查詢", ft.Icons.FILTER_ALT_OUTLINED)),
            ],
        )

    def generate_quick_report(report_name: str):
        selected_mode["value"] = "quick"
        selected_quick_report["value"] = report_name
        step_state["value"] = 2

        if report_name == "指定月份用料摘要":
            # 指定月份需要使用者確認月份，不在點選卡片時立即查詢。
            rebuild()
            return

        run_job(
            f"正在產生：{report_name}",
            lambda: run_quick_report(report_name, month_value=None),
        )

    def quick_card(label, icon_name, color, soft, border):
        active = selected_mode["value"] == "quick" and selected_quick_report["value"] == label
        return ft.Container(
            col={"xs": 6, "md": 3},
            height=106,
            border_radius=14,
            bgcolor=soft if active else CARD,
            border=ft.border.all(2 if active else 1, border if active else BORDER),
            padding=11,
            ink=True,
            on_click=lambda e, name=label: generate_quick_report(name),
            content=ft.Column(
                controls=[
                    ft.Icon(icon_name, size=27, color=color),
                    ft.Text(label, size=13, color=TEXT_MAIN, weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER, max_lines=2),
                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=19, color=color, visible=active),
                ],
                spacing=4,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def build_quick_grid():
        return ft.ResponsiveRow(
            columns=12,
            spacing=12,
            run_spacing=12,
            controls=[quick_card(*item) for item in QUICK_REPORTS],
        )

    def set_filter_value(key: str, value):
        filter_values[key] = value or ""

    def text_field(value_key: str, hint: str, multiline: bool = False):
        return ft.TextField(
            value=filter_values.get(value_key, ""),
            hint_text=hint,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE,
            bgcolor=INPUT_BG,
            filled=True,
            text_size=14,
            min_lines=2 if multiline else 1,
            max_lines=3 if multiline else 1,
            height=86 if multiline else 54,
            content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
            on_change=lambda e, key=value_key: set_filter_value(key, e.control.value),
        )

    def dropdown_field(value_key: str, options: list[str]):
        normalized = list(options or ["全部"])
        if "全部" not in normalized:
            normalized.insert(0, "全部")
        current = filter_values.get(value_key, "全部")
        if current not in normalized:
            current = "全部"
            filter_values[value_key] = current
        control = ft.Dropdown(
            value=current,
            options=[ft.dropdown.Option(o) for o in normalized],
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE,
            bgcolor=INPUT_BG,
            filled=True,
            height=54,
            text_size=14,
            content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
        )
        # Flet 0.84 在目前 VM 環境中 Dropdown 建構子不接受 on_change 參數，
        # 必須先建立控制項再指定事件，避免進頁時直接報錯。
        control.on_change = lambda e, key=value_key: on_dropdown_change(key, e.control.value)
        return control

    def field_label(label: str, icon_name=None, required: bool = False):
        controls = []
        if icon_name:
            controls.append(ft.Icon(icon_name, size=17, color=TEXT_SUB))
        controls.append(ft.Text(label + (" *" if required else ""), size=14, color=TEXT_MAIN, weight=ft.FontWeight.W_600))
        return ft.Row(controls=controls, spacing=7, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def labeled_control(label: str, control: ft.Control, icon_name=None, required: bool = False):
        return ft.Column(spacing=7, controls=[field_label(label, icon_name, required), control])

    def on_dropdown_change(key: str, value):
        filter_values[key] = value or "全部"
        if key == "material":
            selected_family = filter_values.get("material") or "全部"
            supplier_map = filter_options.get("material_supplier_map", {}) or {}
            if selected_family != "全部" and selected_family in supplier_map:
                available = list(supplier_map.get(selected_family, ["全部"]))
                if "全部" not in available:
                    available.insert(0, "全部")
                if filter_values.get("supplier") not in available:
                    filter_values["supplier"] = "全部"
            else:
                if not filter_values.get("supplier"):
                    filter_values["supplier"] = "全部"
            rebuild()

    def build_quick_month_panel():
        if not (selected_mode["value"] == "quick" and selected_quick_report["value"] == "指定月份用料摘要"):
            return ft.Container(height=0)

        def submit_month(e=None):
            run_job(
                "正在產生：指定月份用料摘要",
                lambda: run_quick_report("指定月份用料摘要", month_value=filter_values.get("report_month")),
            )

        return card_box(
            padding=14,
            border_color=PURPLE_BORDER,
            bgcolor="#FFFFFF",
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.EVENT_NOTE_OUTLINED, size=22, color=PURPLE),
                            ft.Column(
                                expand=True,
                                spacing=2,
                                controls=[
                                    ft.Text("指定月份條件", size=16, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                                    ft.Text("請輸入月份後產生報表。格式：YYYY-MM，例如 2026-04。", size=12, color=TEXT_SUB),
                                ],
                            ),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    labeled_control("月份", text_field("report_month", "YYYY-MM，例如 2026-04"), ft.Icons.CALENDAR_MONTH_OUTLINED, True),
                    stable_button("產生指定月份報表", ft.Icons.PLAY_ARROW_ROUNDED, submit_month, bg=PURPLE, fg="white"),
                ],
            ),
        )

    def build_selector_card():
        controls = [
            section_title(ft.Icons.TOUCH_APP_OUTLINED, "選擇報表方式", "快速報表可一鍵產生；全條件篩選可自訂查詢。", BLUE),
            build_mode_row(),
        ]
        if selected_mode["value"] == "quick":
            controls.extend([
                ft.Text("快速報表", size=15, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                build_quick_grid(),
                build_quick_month_panel(),
            ])
        return card_box(content=ft.Column(controls=controls, spacing=15))

    # =====================================================
    # 5. 全條件篩選
    # =====================================================
    DATA_TYPES = ["打料紀錄", "入庫紀錄", "保養紀錄", "交接紀錄"]

    def select_data_type(label: str):
        selected_mode["value"] = "advanced"
        selected_data_type["value"] = label
        step_state["value"] = 2
        rebuild()

    def data_type_chip(label: str):
        active = selected_mode["value"] == "advanced" and selected_data_type["value"] == label
        return ft.Container(
            height=44,
            border_radius=13,
            bgcolor=BLUE if active else CARD,
            border=ft.border.all(1, BLUE if active else BORDER),
            alignment=ft.Alignment(0, 0),
            ink=True,
            on_click=lambda e, value=label: select_data_type(value),
            content=ft.Text(label, size=14, color="white" if active else TEXT_SUB, weight=ft.FontWeight.BOLD if active else ft.FontWeight.W_500),
        )

    def build_data_type_row():
        return ft.ResponsiveRow(
            columns=12,
            spacing=10,
            run_spacing=10,
            controls=[ft.Container(col={"xs": 6, "md": 3}, content=data_type_chip(label)) for label in DATA_TYPES],
        )

    def build_filter_options_notice():
        if filter_options_state.get("loading"):
            return ft.Container(
                bgcolor=BLUE_SOFT,
                border=ft.border.all(1, BLUE_BORDER),
                border_radius=12,
                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                content=ft.Row(
                    controls=[
                        ft.ProgressRing(width=16, height=16, stroke_width=2, color=BLUE),
                        ft.Text("正在載入篩選選項；快速報表可先直接產生。", size=12, color=BLUE, weight=ft.FontWeight.W_600),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True,
                ),
            )

        if filter_options_state.get("error"):
            return ft.Container(
                bgcolor=RED_SOFT,
                border=ft.border.all(1, RED_BORDER),
                border_radius=12,
                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.ERROR_OUTLINE, size=17, color=RED),
                        ft.Text(
                            f"篩選選項載入失敗：{filter_options_state.get('error')}。目前先使用預設選項。",
                            size=12,
                            color=RED,
                            weight=ft.FontWeight.W_600,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True,
                ),
            )

        return ft.Container(height=0)

    def build_advanced_condition_card():
        if selected_mode["value"] != "advanced":
            return ft.Container(height=0)

        supplier_options = filter_options.get("suppliers", ["全部"])
        selected_family = filter_values.get("material") or "全部"
        supplier_map = filter_options.get("material_supplier_map", {}) or {}
        if selected_family != "全部" and selected_family in supplier_map:
            supplier_options = supplier_map.get(selected_family, ["全部"])

        condition_grid = ft.ResponsiveRow(
            columns=12,
            spacing=14,
            run_spacing=14,
            controls=[
                ft.Container(col={"xs": 12, "md": 6}, content=labeled_control("日期起", text_field("start_date", "YYYY/MM/DD"), ft.Icons.CALENDAR_MONTH_OUTLINED, True)),
                ft.Container(col={"xs": 12, "md": 6}, content=labeled_control("日期迄", text_field("end_date", "YYYY/MM/DD"), ft.Icons.EVENT_OUTLINED, True)),
                ft.Container(col={"xs": 12, "md": 6}, content=labeled_control("類別", dropdown_field("category", filter_options.get("categories", ["全部", "新料", "母粒", "回用料", "清潔", "耗材更換", "異常", "待辦"])), ft.Icons.CATEGORY_OUTLINED)),
                ft.Container(col={"xs": 12, "md": 6}, content=labeled_control("原料種類", dropdown_field("material", filter_options.get("material_families", ["全部", "PET", "PET308A", "PA6", "RPET", "母粒"])), ft.Icons.SCIENCE_OUTLINED)),
                ft.Container(col={"xs": 12, "md": 6}, content=labeled_control("供應商", dropdown_field("supplier", supplier_options), ft.Icons.BUSINESS_OUTLINED)),
                ft.Container(col={"xs": 12, "md": 6}, content=labeled_control("機台 / 塔別", dropdown_field("machine", filter_options.get("machines", ["全部", "S1", "S2", "S1-PET", "S1-PA6", "S2-PET", "S2-PA6"])), ft.Icons.PRECISION_MANUFACTURING_OUTLINED)),
                ft.Container(col={"xs": 12}, content=labeled_control("人員", dropdown_field("user", filter_options.get("users", ["全部"])), ft.Icons.PERSON_OUTLINE)),
            ],
        )

        return card_box(
            content=ft.Column(
                spacing=15,
                controls=[
                    section_title(ft.Icons.TUNE_OUTLINED, "條件設定", "全條件篩選才需要日期、類別、供應商、機台與人員條件。", BLUE),
                    build_filter_options_notice(),
                    build_data_type_row(),
                    condition_grid,
                    ft.ResponsiveRow(
                        columns=12,
                        spacing=12,
                        run_spacing=12,
                        controls=[
                            ft.Container(col={"xs": 12, "md": 6}, content=outline_button("清除條件", ft.Icons.REFRESH_OUTLINED, clear_conditions, color="#475569")),
                            ft.Container(col={"xs": 12, "md": 6}, content=stable_button("產生查詢結果", ft.Icons.FILTER_ALT_OUTLINED, apply_advanced_query, bg=BLUE_BTN, fg="white")),
                        ],
                    ),
                ],
            ),
        )

    # =====================================================
    # 6. 報表執行 / 匯出
    # =====================================================
    def apply_advanced_query(e=None):
        selected_mode["value"] = "advanced"
        step_state["value"] = 2
        run_job(
            f"正在查詢：{selected_data_type['value']}",
            lambda: run_advanced_query(
                data_type=selected_data_type["value"],
                start_date=filter_values.get("start_date"),
                end_date=filter_values.get("end_date"),
                category=filter_values.get("category") or "全部",
                material_name=filter_values.get("material") or "全部",
                supplier=filter_values.get("supplier") or "全部",
                machine=filter_values.get("machine") or "全部",
                user_name=filter_values.get("user") or "全部",
            ),
        )

    def clear_conditions(e=None):
        filter_values.update(
            {
                "start_date": month_start_string(),
                "end_date": today_string(),
                "category": "全部",
                "material": "全部",
                "supplier": "全部",
                "machine": "全部",
                "user": "全部",
            }
        )
        current_report_data.clear()
        current_report_data.update(
            {
                "title": "尚未產生報表",
                "columns": ["日期", "資料類型", "名稱", "數量", "狀態"],
                "rows": [],
                "count": 0,
                "summary_text": "請先選擇快速報表，或切換到全條件篩選後套用條件。",
            }
        )
        export_state.update({"path": "", "filename": "", "url": "", "message": ""})
        show_all_rows["value"] = False
        step_state["value"] = 1
        status_state["visible"] = False
        rebuild()

    def export_csv(e=None):
        rows = current_report_data.get("rows") or []
        if not rows:
            show_msg("目前沒有可匯出的資料。", ORANGE)
            return

        if loading_state["value"]:
            return

        loading_state["value"] = True
        loading_state["message"] = "正在匯出 CSV"
        status_state["visible"] = True
        status_state["message"] = "正在匯出 CSV"
        status_state["theme"] = "blue"
        step_state["value"] = 3
        rebuild()

        def worker():
            try:
                result = export_report_to_csv(current_report_data)
                if not is_active_view():
                    return

                loading_state["value"] = False

                if result.ok:
                    data = result.data or {}
                    filename = str(data.get("filename") or "").strip()
                    path = str(data.get("path") or "").strip()
                    # ft.run(main, assets_dir=".") 時，專案根目錄下的 exports/ 可被瀏覽器讀取；
                    # 手機 WebView 對相對 URL 反應不穩，因此這裡改成優先使用絕對 URL。
                    download_url = make_download_url(filename) if filename else ""
                    export_state.update(
                        {
                            "path": path,
                            "filename": filename,
                            "url": download_url,
                            "message": result.message or "CSV 已匯出。",
                        }
                    )
                    status_state["visible"] = True
                    status_state["message"] = "CSV 已匯出，可點擊下載" if download_url else "CSV 已匯出"
                    status_state["theme"] = "green"
                    rebuild()
                    show_msg(result.message, GREEN)
                else:
                    status_state["visible"] = True
                    status_state["message"] = result.message or "CSV 匯出失敗"
                    status_state["theme"] = "red"
                    rebuild()

            except Exception as ex:
                if not is_active_view():
                    return
                loading_state["value"] = False
                status_state["visible"] = True
                status_state["message"] = f"CSV 匯出失敗：{ex}"
                status_state["theme"] = "red"
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    # =====================================================
    # 7. 結果預覽 / 查看全部
    # =====================================================
    def column_width(column: str) -> int:
        text = str(column)
        if text in ["日期", "月份", "班別", "類型", "類別", "單位", "狀態", "結果", "嚴重度"]:
            return 105
        if text in ["數量", "目前庫存", "安全庫存"]:
            return 105
        if text in ["名稱", "原料名稱", "項目", "供應商", "機台/塔別", "機台/區域", "區域"]:
            return 150
        if text in ["內容", "處理備註", "備註"]:
            return 260
        return 135

    def table_row(columns: list[str], row_data: dict | None = None, header: bool = False):
        widths = [column_width(col) for col in columns]
        controls = []
        for idx, col in enumerate(columns):
            value = col if header else (row_data or {}).get(col, "")
            controls.append(
                ft.Text(
                    str(value),
                    width=widths[idx],
                    size=13,
                    color=TEXT_MAIN,
                    weight=ft.FontWeight.BOLD if header else ft.FontWeight.NORMAL,
                    max_lines=1 if header else 2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                )
            )

        return ft.Container(
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            bgcolor="#F8FAFC" if header else "#FFFFFF",
            border=ft.border.only(bottom=ft.border.BorderSide(1, "#E5EAF2")),
            content=ft.Row(controls=controls, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )

    def build_result_table():
        columns = current_report_data.get("columns") or ["日期", "資料類型", "名稱", "數量", "狀態"]
        rows = current_report_data.get("rows") or []
        total_width = max(760, sum(column_width(col) for col in columns) + (len(columns) * 8) + 24)

        if rows:
            visible_rows = rows if show_all_rows["value"] else rows[:10]
            row_controls = [table_row(columns, header=True)]
            row_controls.extend([table_row(columns, row, header=False) for row in visible_rows])
        else:
            row_controls = [
                ft.Container(
                    width=total_width,
                    padding=22,
                    bgcolor="#FFFFFF",
                    content=ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.INFO_OUTLINE, size=30, color=TEXT_MUTED),
                            ft.Text("目前沒有資料", size=15, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                            ft.Text(current_report_data.get("summary_text") or "請先產生報表。", size=13, color=TEXT_SUB, text_align=ft.TextAlign.CENTER),
                        ],
                        spacing=8,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            ]

        return ft.Container(
            border=ft.border.all(1, "#E5EAF2"),
            border_radius=12,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Row(
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Container(
                        width=total_width,
                        content=ft.Column(spacing=0, controls=row_controls),
                    )
                ],
            ),
        )

    def toggle_show_all(e=None):
        if not current_report_data.get("rows"):
            show_msg("目前沒有可查看的資料。", ORANGE)
            return
        show_all_rows["value"] = not show_all_rows["value"]
        rebuild()

    def open_export_file(e=None):
        url = export_state.get("url") or make_download_url(export_state.get("filename") or "")
        if not url:
            show_msg("尚未產生可下載的 CSV。", ORANGE)
            return
        try:
            page.launch_url(url)
        except Exception as ex:
            show_msg(f"無法開啟下載連結：{ex}", RED)

    def copy_export_link(e=None):
        url = export_state.get("url") or make_download_url(export_state.get("filename") or "")
        if not url:
            show_msg("尚未產生可複製的 CSV 連結。", ORANGE)
            return
        try:
            page.set_clipboard(url)
            show_msg("CSV 下載連結已複製。若手機沒有自動開啟，請貼到瀏覽器網址列。", GREEN)
        except Exception as ex:
            show_msg(f"複製連結失敗：{ex}", RED)

    def build_export_download_panel():
        if not export_state.get("url"):
            return ft.Container(height=0)

        filename = export_state.get("filename") or "report.csv"
        url = export_state.get("url") or make_download_url(filename)
        return ft.Container(
            bgcolor=GREEN_SOFT,
            border=ft.border.all(1, GREEN_BORDER),
            border_radius=14,
            padding=ft.padding.symmetric(horizontal=12, vertical=12),
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=19, color=GREEN),
                            ft.Column(
                                expand=True,
                                spacing=2,
                                controls=[
                                    ft.Text("CSV 已產生", size=14, color=GREEN, weight=ft.FontWeight.BOLD),
                                    ft.Text(filename, size=12, color=TEXT_SUB, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                    ft.Text(url, size=11, color=TEXT_MUTED, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                ],
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.ResponsiveRow(
                        columns=12,
                        spacing=10,
                        run_spacing=10,
                        controls=[
                            ft.Container(
                                col={"xs": 12, "md": 6},
                                content=stable_button(
                                    "下載 CSV",
                                    ft.Icons.DOWNLOAD_OUTLINED,
                                    open_export_file,
                                    bg=GREEN,
                                    fg="white",
                                ),
                            ),
                            ft.Container(
                                col={"xs": 12, "md": 6},
                                content=outline_button(
                                    "複製連結",
                                    ft.Icons.CONTENT_COPY_OUTLINED,
                                    copy_export_link,
                                    color=GREEN,
                                ),
                            ),
                        ],
                    ),
                ],
            ),
        )

    def build_preview_card():
        title = current_report_data.get("title") or "結果預覽"
        rows = current_report_data.get("rows") or []
        count = current_report_data.get("count", len(rows))
        shown_count = len(rows) if show_all_rows["value"] else min(10, len(rows))
        note = f"顯示全部 {len(rows)} 筆資料" if show_all_rows["value"] else f"僅顯示前 {shown_count} 筆資料"

        title_block = ft.Column(
            expand=True,
            spacing=4,
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.TABLE_CHART_OUTLINED, size=22, color=TEXT_SUB),
                        ft.Text("結果預覽", size=20, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=TEXT_MAIN, max_lines=2, overflow=ft.TextOverflow.VISIBLE),
                ft.Text(current_report_data.get("summary_text") or "", size=13, color=TEXT_SUB, max_lines=3, visible=bool(current_report_data.get("summary_text"))),
            ],
        )

        badge = ft.Container(
            height=30,
            padding=ft.padding.symmetric(horizontal=12),
            border_radius=15,
            bgcolor=BLUE_SOFT,
            border=ft.border.all(1, BLUE_BORDER),
            content=ft.Text(f"共 {count} 筆", size=13, color=BLUE, weight=ft.FontWeight.BOLD),
            alignment=ft.Alignment(0, 0),
        )

        return card_box(
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        controls=[title_block, badge],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    build_result_table(),
                    ft.Row(
                        controls=[
                            ft.Text(note, size=12, color=TEXT_MUTED),
                            ft.Container(expand=True),
                            outline_button("收合" if show_all_rows["value"] else "查看全部", ft.Icons.KEYBOARD_ARROW_UP if show_all_rows["value"] else ft.Icons.VISIBILITY_OUTLINED, toggle_show_all, color=BLUE, height=42, expand=False),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.ResponsiveRow(
                        columns=12,
                        spacing=12,
                        run_spacing=12,
                        controls=[
                            ft.Container(col={"xs": 12, "md": 6}, content=stable_button("匯出 CSV", ft.Icons.FILE_DOWNLOAD_OUTLINED, export_csv, bg=BLUE_BTN, fg="white", disabled=not bool(rows))),
                            ft.Container(col={"xs": 12, "md": 6}, content=outline_button("清除結果", ft.Icons.REFRESH_OUTLINED, clear_conditions, color="#475569")),
                        ],
                    ),
                    build_export_download_panel(),
                ],
            ),
        )

    # =====================================================
    # 8. 篩選選項背景載入
    # =====================================================
    def load_filter_options_in_background():
        def worker():
            try:
                result = build_report_filter_options()

                if not is_active_view():
                    return

                filter_options_state["loading"] = False
                filter_options_state["loaded"] = bool(result.ok)

                if result.ok:
                    filter_options_state["error"] = ""
                    loaded_options = result.data or {}
                    filter_options.clear()
                    filter_options.update(default_filter_options)
                    filter_options.update(loaded_options)

                    if status_state.get("message") == "正在載入篩選條件":
                        status_state["visible"] = True
                        status_state["message"] = "篩選條件已載入"
                        status_state["theme"] = "green"
                else:
                    filter_options_state["error"] = result.message or "未知錯誤"
                    if status_state.get("message") == "正在載入篩選條件":
                        status_state["visible"] = True
                        status_state["message"] = "篩選條件載入失敗"
                        status_state["theme"] = "red"

                rebuild()

            except Exception as ex:
                if not is_active_view():
                    return

                filter_options_state["loading"] = False
                filter_options_state["loaded"] = False
                filter_options_state["error"] = str(ex)

                if status_state.get("message") == "正在載入篩選條件":
                    status_state["visible"] = True
                    status_state["message"] = "篩選條件載入失敗"
                    status_state["theme"] = "red"

                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    # =====================================================
    # 9. 主畫面
    # =====================================================
    def build_layout():
        controls = [
            header_block(),
            status_badge(),
            build_stepper(),
            build_selector_card(),
        ]

        if selected_mode["value"] == "advanced":
            controls.append(build_advanced_condition_card())

        controls.extend([
            build_preview_card(),
            ft.Container(height=90),
        ])

        return ft.Container(
            bgcolor=BG,
            content=ft.Column(
                controls=controls,
                spacing=18,
            ),
        )

    def rebuild():
        main_host.content = build_layout()
        page_update()

    main_host.content = build_layout()
    load_filter_options_in_background()
    return main_host
