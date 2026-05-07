# views/reports.py
# KNH MMS 報表中心 - Flet 0.84 + Supabase
# 重點：快速報表一鍵產生、全條件篩選、查看全部、CSV 匯出與內容顯示
# 注意：目前 VM / Flet Web 尚未打通正式 CSV 下載；先以頁面文字框顯示 CSV 內容作為穩定收尾。

from __future__ import annotations

import base64
import csv
import os
import re
import threading
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

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
    # 0. 狀態
    # =====================================================
    selected_mode = {"value": "quick"}  # quick / advanced
    selected_quick_report = {"value": "本月用料摘要"}
    selected_data_type = {"value": "打料紀錄"}
    show_all_rows = {"value": False}

    current_report_data: dict[str, Any] = {
        "title": "尚未產生報表",
        "columns": ["日期", "資料類型", "名稱", "數量", "狀態"],
        "rows": [],
        "count": 0,
        "summary_text": "請先選擇快速報表或套用篩選條件。",
    }

    default_filter_options = {
        "categories": ["全部", "新料", "母粒", "回用料", "清潔", "耗材更換", "異常", "待辦"],
        "material_families": ["全部", "PET", "PET308A", "PA6", "RPET", "母粒", "PP"],
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

    loading_state = {
        "active": False,
        "message": "",
    }

    status_state = {
        "visible": False,
        "message": "",
        "theme": "blue",  # blue / green / red / orange
    }

    export_state = {
        "filename": "",
        "path": "",
        "url_path": "",
        "url": "",
        "csv_content": "",
        "expires_after_days": None,
        "cleanup": {},
    }

    # 手機 Web 原生 Dropdown 選單會展開成過大的全螢幕選單。
    # 改用頁面內自製選項面板，避免遮住整個畫面。
    select_panel_state = {"key": ""}

    class SelectValue:
        def __init__(self, value: str = "全部"):
            self.value = value

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
    # 2. 共用工具
    # =====================================================
    def today_text() -> str:
        return datetime.now(TAIPEI_TZ).strftime("%Y/%m/%d")

    def month_start_text() -> str:
        now = datetime.now(TAIPEI_TZ)
        return f"{now.year:04d}/{now.month:02d}/01"

    def month_text(delta_months: int = 0) -> str:
        now = datetime.now(TAIPEI_TZ)
        y = now.year
        m = now.month + delta_months
        while m <= 0:
            y -= 1
            m += 12
        while m > 12:
            y += 1
            m -= 12
        return f"{y:04d}-{m:02d}"

    def safe_page_update() -> None:
        try:
            page.update()
        except Exception as ex:
            print("reports page.update failed:", repr(ex))

    def show_msg(msg: str, color: str = BLUE) -> None:
        snack = ft.SnackBar(
            content=ft.Text(str(msg), color="white", weight=ft.FontWeight.W_600),
            bgcolor=color,
            duration=3000,
        )
        try:
            page.overlay.append(snack)
        except Exception:
            pass
        snack.open = True
        safe_page_update()

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

    def title_block(icon_name, title: str, subtitle: str, icon_color: str = BLUE):
        return ft.Row(
            controls=[
                ft.Container(
                    width=58,
                    height=58,
                    border_radius=18,
                    bgcolor=BLUE_SOFT,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Icon(icon_name, size=31, color=icon_color),
                ),
                ft.Column(
                    expand=True,
                    spacing=4,
                    controls=[
                        ft.Text(title, size=28, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                        ft.Text(subtitle, size=14, color=TEXT_SUB, max_lines=3, overflow=ft.TextOverflow.VISIBLE),
                    ],
                ),
            ],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def section_header(icon_name, title: str, subtitle: str | None = None, icon_color: str = BLUE):
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
                    expand=True,
                    spacing=3,
                    controls=[
                        ft.Text(title, size=22, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                        ft.Text(subtitle or "", size=13, color=TEXT_SUB, visible=bool(subtitle), max_lines=3, overflow=ft.TextOverflow.VISIBLE),
                    ],
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def stable_content(label: str, icon_name, fg: str, text_size: int = 15):
        return ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
            tight=True,
            controls=[
                ft.Icon(icon_name, size=20, color=fg),
                ft.Text(label, size=text_size, color=fg, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ],
        )

    def stable_button(label: str, icon_name, on_click, bg: str = BLUE_BTN, fg: str = "white", height: int = 52, disabled: bool = False):
        btn = ft.Container(
            height=height,
            border_radius=14,
            bgcolor="#CBD5E1" if disabled else bg,
            border=ft.border.all(1, "#CBD5E1" if disabled else bg),
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.symmetric(horizontal=12),
            opacity=0.72 if disabled else 1,
            ink=not disabled,
            content=stable_content(label, icon_name, fg),
        )
        btn.disabled = disabled

        def handle_click(e):
            if getattr(btn, "disabled", False):
                return
            if callable(on_click):
                on_click(e)

        btn.on_click = handle_click
        return btn

    def outline_button(label: str, icon_name, on_click, color: str = BLUE, height: int = 52, disabled: bool = False):
        btn = ft.Container(
            height=height,
            border_radius=14,
            bgcolor="#FFFFFF",
            border=ft.border.all(1, "#CBD5E1" if disabled else BLUE_BORDER),
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.symmetric(horizontal=12),
            opacity=0.65 if disabled else 1,
            ink=not disabled,
            content=stable_content(label, icon_name, "#94A3B8" if disabled else color),
        )
        btn.disabled = disabled

        def handle_click(e):
            if getattr(btn, "disabled", False):
                return
            if callable(on_click):
                on_click(e)

        btn.on_click = handle_click
        return btn

    def labeled_textfield(label: str, control: ft.Control, icon_name=None, required: bool = False):
        title_controls = []
        if icon_name:
            title_controls.append(ft.Icon(icon_name, size=18, color=TEXT_SUB))
        title_controls.append(ft.Text(f"{label}{' *' if required else ''}", size=14, color=TEXT_MAIN, weight=ft.FontWeight.BOLD))
        return ft.Column(
            spacing=8,
            controls=[
                ft.Row(controls=title_controls, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                control,
            ],
        )

    def make_field(hint: str = "", value: str = ""):
        return ft.TextField(
            value=value,
            hint_text=hint,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE,
            bgcolor=INPUT_BG,
            filled=True,
            text_size=14,
            height=54,
            width=float("inf"),
            content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
        )

    def make_dropdown(options, value="全部"):
        opts = list(options or ["全部"])
        if "全部" not in opts:
            opts.insert(0, "全部")
        return ft.Dropdown(
            options=[ft.dropdown.Option(o) for o in opts],
            value=value if value in opts else opts[0],
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE,
            bgcolor=INPUT_BG,
            filled=True,
            height=54,
            width=float("inf"),
            text_size=14,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=12),
        )

    def set_status(message: str, theme: str = "blue", visible: bool = True):
        status_state["message"] = message
        status_state["theme"] = theme
        status_state["visible"] = visible

    def status_banner():
        if not status_state.get("visible"):
            return ft.Container(height=0)

        theme = status_state.get("theme")
        if theme == "green":
            bg, border, fg, icon = GREEN_SOFT, GREEN_BORDER, GREEN, ft.Icons.CHECK_CIRCLE_OUTLINE
        elif theme == "red":
            bg, border, fg, icon = RED_SOFT, RED_BORDER, RED, ft.Icons.ERROR_OUTLINE
        elif theme == "orange":
            bg, border, fg, icon = ORANGE_SOFT, ORANGE_BORDER, ORANGE, ft.Icons.INFO_OUTLINE
        else:
            bg, border, fg, icon = BLUE_SOFT, BLUE_BORDER, BLUE, ft.Icons.SYNC

        return ft.Container(
            height=36,
            padding=ft.padding.symmetric(horizontal=14),
            border_radius=18,
            bgcolor=bg,
            border=ft.border.all(1, border),
            alignment=ft.Alignment(0, 0),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
                controls=[
                    ft.Icon(icon, size=17, color=fg),
                    ft.Text(status_state.get("message") or "", size=13, color=fg, weight=ft.FontWeight.W_600),
                ],
            ),
        )

    def normalize_export_url_path(value: str, filename: str = "") -> str:
        """
        Flet 以 ft.run(main, assets_dir=".") 啟動時，專案根目錄下的 exports/
        應以 /assets/exports/... 對外讀取，而不是 /exports/...。
        """
        raw = str(value or "").strip()

        if raw.startswith("http://") or raw.startswith("https://"):
            return raw

        if raw.startswith("/assets/exports/"):
            return raw

        if raw.startswith("assets/exports/"):
            return "/" + raw

        if raw.startswith("/exports/"):
            return "/assets" + raw

        if raw.startswith("exports/"):
            return "/assets/" + raw

        if filename:
            return f"/assets/exports/{quote(filename)}"

        return raw if raw.startswith("/") else f"/{raw}" if raw else ""

    def get_public_base_url() -> str:
        """
        優先使用環境變數，方便日後改走 80 port 或正式網域。
        未設定時，先用目前 Google VM 測試網址作為 fallback。
        """
        for key in ["KNH_PUBLIC_BASE_URL", "PUBLIC_BASE_URL", "FLET_PUBLIC_URL"]:
            value = str(os.getenv(key, "") or "").strip().rstrip("/")
            if value.startswith("http://") or value.startswith("https://"):
                return value

        page_url = str(getattr(page, "url", "") or "")
        if page_url.startswith("http://") or page_url.startswith("https://"):
            parts = urlsplit(page_url)
            if parts.scheme and parts.netloc:
                return f"{parts.scheme}://{parts.netloc}"

        return "http://104.198.146.124:8502"

    def build_absolute_url(url_path: str) -> str:
        path = str(url_path or "").strip()
        if not path:
            return ""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{get_public_base_url()}{path}"

    def open_url(url: str) -> None:
        if not url:
            show_msg("尚未產生可下載的 CSV。", ORANGE)
            return
        try:
            if hasattr(page, "launch_url"):
                page.launch_url(url)
                return
        except Exception as ex:
            show_msg(f"無法自動開啟下載連結：{ex}", RED)
            return
        show_msg("目前環境不支援自動開啟，請使用下方 CSV 內容文字框手動複製。", ORANGE)

    def build_csv_text_from_report(report_data: dict[str, Any]) -> str:
        columns = report_data.get("columns") or []
        rows = report_data.get("rows") or []
        if not columns:
            return ""

        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})
        return buffer.getvalue()

    def read_export_csv_text(path_value: str, fallback_report_data: dict[str, Any]) -> str:
        path_text = str(path_value or "").strip()
        if path_text:
            try:
                return Path(path_text).read_text(encoding="utf-8-sig")
            except Exception as ex:
                print("read exported csv failed:", repr(ex))

        return build_csv_text_from_report(fallback_report_data)

    # =====================================================
    # 3. 控制項宣告
    # =====================================================
    date_start = make_field("YYYY/MM/DD", month_start_text())
    date_end = make_field("YYYY/MM/DD", today_text())
    report_month = make_field("YYYY-MM，例如 2026-04", month_text(-1))

    category_dd = SelectValue("全部")
    material_dd = SelectValue("全部")
    supplier_dd = SelectValue("全部")
    machine_dd = SelectValue("全部")
    user_dd = SelectValue("全部")

    # =====================================================
    # 4. 狀態與選項更新
    # =====================================================
    main_host = ft.Container(expand=True)

    def update_dropdown_options(control: ft.Dropdown, options, keep_value: bool = True):
        current = control.value
        opts = list(options or ["全部"])
        if "全部" not in opts:
            opts.insert(0, "全部")
        control.options = [ft.dropdown.Option(o) for o in opts]
        if keep_value and current in opts:
            control.value = current
        else:
            control.value = opts[0]

    def get_select_options(key: str) -> list[str]:
        if key == "category":
            return list(filter_options.get("categories", ["全部"]) or ["全部"])
        if key == "material":
            return list(filter_options.get("material_families", ["全部"]) or ["全部"])
        if key == "supplier":
            selected_family = material_dd.value or "全部"
            supplier_map = filter_options.get("material_supplier_map", {}) or {}
            if selected_family != "全部" and selected_family in supplier_map:
                return list(supplier_map.get(selected_family, ["全部"]) or ["全部"])
            return list(filter_options.get("suppliers", ["全部"]) or ["全部"])
        if key == "machine":
            return list(filter_options.get("machines", ["全部"]) or ["全部"])
        if key == "user":
            return list(filter_options.get("users", ["全部"]) or ["全部"])
        return ["全部"]

    def ensure_select_value(control: SelectValue, options: list[str]) -> None:
        opts = list(options or ["全部"])
        if "全部" not in opts:
            opts.insert(0, "全部")
        if control.value not in opts:
            control.value = "全部" if "全部" in opts else opts[0]

    def apply_filter_options_to_controls():
        ensure_select_value(category_dd, get_select_options("category"))
        ensure_select_value(material_dd, get_select_options("material"))
        ensure_select_value(supplier_dd, get_select_options("supplier"))
        ensure_select_value(machine_dd, get_select_options("machine"))
        ensure_select_value(user_dd, get_select_options("user"))

    # =====================================================
    # 5. 背景任務
    # =====================================================
    def start_filter_options_load():
        def worker():
            try:
                result = build_report_filter_options()
                if not is_active_view():
                    return
                if result.ok:
                    filter_options.clear()
                    filter_options.update(result.data or default_filter_options)
                    filter_options_state["loaded"] = True
                    filter_options_state["error"] = ""
                else:
                    filter_options.clear()
                    filter_options.update(result.data or default_filter_options)
                    filter_options_state["loaded"] = False
                    filter_options_state["error"] = result.message or "報表篩選選項載入失敗"
                filter_options_state["loading"] = False
                apply_filter_options_to_controls()
                rebuild()
            except Exception as ex:
                if not is_active_view():
                    return
                filter_options_state["loading"] = False
                filter_options_state["loaded"] = False
                filter_options_state["error"] = f"報表篩選選項載入失敗：{ex}"
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def run_report_background(task_name: str, runner):
        if loading_state.get("active"):
            show_msg("報表仍在處理中，請稍候。", ORANGE)
            return

        loading_state["active"] = True
        loading_state["message"] = task_name
        set_status(task_name, "blue", True)
        rebuild()

        def worker():
            try:
                result = runner()
                if not is_active_view():
                    return
                loading_state["active"] = False
                if result.ok:
                    set_report_result(result, update_now=False)
                    set_status("報表已產生", "green", True)
                else:
                    set_status(result.message or "報表產生失敗", "red", True)
                rebuild()
            except Exception as ex:
                if not is_active_view():
                    return
                loading_state["active"] = False
                set_status(f"報表產生失敗：{ex}", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def export_csv_background(e=None):
        rows = current_report_data.get("rows") or []
        if not rows:
            show_msg("目前沒有可匯出的資料。", ORANGE)
            return
        if loading_state.get("active"):
            show_msg("報表仍在處理中，請稍候。", ORANGE)
            return

        loading_state["active"] = True
        loading_state["message"] = "正在匯出 CSV"
        set_status("正在匯出 CSV", "blue", True)
        rebuild()

        def worker():
            try:
                result = export_report_to_csv(current_report_data)
                if not is_active_view():
                    return
                loading_state["active"] = False
                if result.ok:
                    data = result.data or {}
                    filename = str(data.get("filename") or "")
                    path_text = str(data.get("path") or "")
                    raw_url_path = str(data.get("url_path") or data.get("asset_url_path") or "")
                    url_path = normalize_export_url_path(raw_url_path, filename)
                    url = str(data.get("url") or data.get("download_url") or "")
                    if not url:
                        url = build_absolute_url(url_path)

                    csv_content = str(data.get("csv_text") or "") or read_export_csv_text(path_text, current_report_data)

                    export_state.update(
                        {
                            "filename": filename,
                            "path": path_text,
                            "url_path": url_path,
                            "url": url,
                            "csv_content": csv_content,
                            "expires_after_days": data.get("expires_after_days"),
                            "cleanup": data.get("cleanup") or {},
                        }
                    )
                    set_status("CSV 已匯出，內容已顯示於下方文字框", "green", True)
                    rebuild()
                else:
                    set_status(result.message or "CSV 匯出失敗", "red", True)
                    rebuild()
            except Exception as ex:
                if not is_active_view():
                    return
                loading_state["active"] = False
                set_status(f"CSV 匯出失敗：{ex}", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    # =====================================================
    # 6. 報表動作
    # =====================================================
    def set_report_result(result, update_now: bool = True):
        if not result.ok:
            set_status(result.message or "報表產生失敗", "red", True)
            if update_now:
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
        export_state.update({"filename": "", "path": "", "url_path": "", "url": "", "csv_content": "", "expires_after_days": None, "cleanup": {}})
        show_all_rows["value"] = False
        if update_now:
            rebuild()

    def generate_quick_report(label: str | None = None):
        if label:
            selected_quick_report["value"] = label
        selected_mode["value"] = "quick"
        report_name = selected_quick_report["value"]
        month_value = report_month.value if report_name == "指定月份用料摘要" else None
        run_report_background(
            f"正在產生 {report_name}",
            lambda: run_quick_report(report_name, month_value=month_value),
        )

    def apply_advanced_conditions(e=None):
        selected_mode["value"] = "advanced"
        run_report_background(
            "正在產生查詢結果",
            lambda: run_advanced_query(
                data_type=selected_data_type["value"],
                start_date=date_start.value,
                end_date=date_end.value,
                category=category_dd.value or "全部",
                material_name=material_dd.value or "全部",
                supplier=supplier_dd.value or "全部",
                machine=machine_dd.value or "全部",
                user_name=user_dd.value or "全部",
            ),
        )

    def clear_conditions(e=None):
        selected_mode["value"] = "quick"
        selected_quick_report["value"] = "本月用料摘要"
        selected_data_type["value"] = "打料紀錄"
        show_all_rows["value"] = False
        date_start.value = month_start_text()
        date_end.value = today_text()
        report_month.value = month_text(-1)
        category_dd.value = "全部"
        material_dd.value = "全部"
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
        export_state.update({"filename": "", "path": "", "url_path": "", "url": "", "csv_content": "", "expires_after_days": None, "cleanup": {}})
        set_status("", "blue", False)
        rebuild()

    def toggle_show_all(e=None):
        if not current_report_data.get("rows"):
            show_msg("目前沒有可查看的資料。", ORANGE)
            return
        show_all_rows["value"] = not show_all_rows["value"]
        rebuild()

    # =====================================================
    # 7. UI 建構
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

    def quick_card(label: str, icon_name, color: str, soft: str, border: str):
        active = selected_mode["value"] == "quick" and selected_quick_report["value"] == label
        return ft.Container(
            col={"xs": 6, "md": 3},
            height=105,
            border_radius=14,
            bgcolor=soft if active else CARD,
            border=ft.border.all(2 if active else 1, border if active else BORDER),
            padding=12,
            ink=True,
            on_click=lambda e, selected_label=label: generate_quick_report(selected_label),
            content=ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=5,
                controls=[
                    ft.Icon(icon_name, size=27, color=color),
                    ft.Text(label, size=14, color=TEXT_MAIN, weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER, max_lines=2),
                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=20, color=color, visible=active),
                ],
            ),
        )

    def build_mode_selector():
        def mode_button(mode_value: str, label: str, icon_name):
            active = selected_mode["value"] == mode_value
            return ft.Container(
                expand=True,
                height=54,
                border_radius=14,
                bgcolor=BLUE if active else CARD,
                border=ft.border.all(1, BLUE if active else BORDER),
                alignment=ft.Alignment(0, 0),
                ink=True,
                on_click=lambda e: set_mode(mode_value),
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                    controls=[
                        ft.Icon(icon_name, size=20, color="white" if active else TEXT_SUB),
                        ft.Text(label, size=15, color="white" if active else TEXT_SUB, weight=ft.FontWeight.BOLD),
                    ],
                ),
            )

        def set_mode(mode_value: str):
            selected_mode["value"] = mode_value
            set_status("", "blue", False)
            rebuild()

        return ft.Row(
            spacing=12,
            controls=[
                mode_button("quick", "快速報表", ft.Icons.FLASH_ON_OUTLINED),
                mode_button("advanced", "全條件篩選", ft.Icons.FILTER_ALT_OUTLINED),
            ],
        )

    def build_quick_report_area():
        controls = [
            section_header(ft.Icons.FLASH_ON_OUTLINED, "快速報表", "點選報表即可產生；只有指定月份用料摘要需要月份條件。", BLUE),
            ft.ResponsiveRow(
                columns=12,
                spacing=12,
                run_spacing=12,
                controls=[quick_card(*item) for item in QUICK_REPORTS],
            ),
        ]

        if selected_quick_report["value"] == "指定月份用料摘要":
            controls.append(
                card_box(
                    padding=14,
                    border_color=PURPLE_BORDER,
                    bgcolor="#FFFFFF",
                    content=ft.Column(
                        spacing=12,
                        controls=[
                            labeled_textfield("指定月份", report_month, ft.Icons.EVENT_NOTE_OUTLINED, required=True),
                            stable_button("產生指定月份報表", ft.Icons.PLAY_ARROW_OUTLINED, lambda e: generate_quick_report("指定月份用料摘要"), bg=PURPLE, fg="white"),
                        ],
                    ),
                )
            )

        return card_box(content=ft.Column(spacing=15, controls=controls))

    def data_type_button(label: str):
        active = selected_data_type["value"] == label
        return ft.Container(
            col={"xs": 6, "md": 3},
            height=46,
            border_radius=14,
            bgcolor=BLUE if active else CARD,
            border=ft.border.all(1, BLUE if active else BORDER),
            alignment=ft.Alignment(0, 0),
            ink=True,
            on_click=lambda e, v=label: set_data_type(v),
            content=ft.Text(label, size=14, color="white" if active else TEXT_SUB, weight=ft.FontWeight.BOLD if active else ft.FontWeight.W_500),
        )

    def set_data_type(value: str):
        selected_data_type["value"] = value
        selected_mode["value"] = "advanced"
        rebuild()

    def build_filter_options_status():
        if filter_options_state["loading"]:
            return ft.Container(
                bgcolor=BLUE_SOFT,
                border=ft.border.all(1, BLUE_BORDER),
                border_radius=12,
                padding=10,
                content=ft.Row(
                    spacing=8,
                    controls=[ft.ProgressRing(width=16, height=16, stroke_width=2, color=BLUE), ft.Text("篩選選項載入中...", size=13, color=BLUE, weight=ft.FontWeight.W_600)],
                ),
            )
        if filter_options_state["error"]:
            return ft.Container(
                bgcolor=ORANGE_SOFT,
                border=ft.border.all(1, ORANGE_BORDER),
                border_radius=12,
                padding=10,
                content=ft.Text(filter_options_state["error"], size=13, color=ORANGE, weight=ft.FontWeight.W_600),
            )
        return ft.Container(height=0)

    def compact_field(label: str, control: ft.Control, icon_name=None, required: bool = False):
        """
        報表中心手機版欄位容器。
        目的：避免欄位全部直排且控制項只佔左側，造成右側大面積空白。
        """
        title_controls = []
        if icon_name:
            title_controls.append(ft.Icon(icon_name, size=17, color=TEXT_SUB))
        title_controls.append(
            ft.Text(
                f"{label}{' *' if required else ''}",
                size=14,
                color=TEXT_MAIN,
                weight=ft.FontWeight.BOLD,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )

        return ft.Container(
            content=ft.Column(
                spacing=7,
                controls=[
                    ft.Row(
                        spacing=7,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=title_controls,
                    ),
                    ft.Container(width=float("inf"), content=control),
                ],
            )
        )


    SELECT_META = {
        "category": {"label": "類別", "icon": ft.Icons.CATEGORY_OUTLINED, "control": category_dd},
        "material": {"label": "原料種類", "icon": ft.Icons.SCIENCE_OUTLINED, "control": material_dd},
        "supplier": {"label": "供應商", "icon": ft.Icons.DOMAIN_OUTLINED, "control": supplier_dd},
        "machine": {"label": "機台 / 塔別", "icon": ft.Icons.PRECISION_MANUFACTURING_OUTLINED, "control": machine_dd},
        "user": {"label": "人員", "icon": ft.Icons.PERSON_OUTLINE, "control": user_dd},
    }

    def compact_select_field(key: str):
        meta = SELECT_META[key]
        control = meta["control"]
        active = select_panel_state.get("key") == key
        label = meta["label"]
        icon_name = meta["icon"]

        def toggle_panel(e=None):
            select_panel_state["key"] = "" if active else key
            rebuild()

        return ft.Container(
            content=ft.Column(
                spacing=7,
                controls=[
                    ft.Row(
                        spacing=7,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(icon_name, size=17, color=TEXT_SUB),
                            ft.Text(label, size=14, color=TEXT_MAIN, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                    ),
                    ft.Container(
                        height=54,
                        width=float("inf"),
                        border_radius=12,
                        bgcolor="#E5E7EF" if not active else BLUE_SOFT,
                        border=ft.border.all(1, BLUE_BORDER if active else BORDER),
                        padding=ft.padding.symmetric(horizontal=12),
                        alignment=ft.Alignment(0, 0),
                        ink=True,
                        on_click=toggle_panel,
                        content=ft.Row(
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Text(str(control.value or "全部"), size=14, color=TEXT_MAIN, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                ft.Icon(ft.Icons.KEYBOARD_ARROW_UP if active else ft.Icons.KEYBOARD_ARROW_DOWN, size=22, color="#475569"),
                            ],
                        ),
                    ),
                ],
            )
        )

    def build_select_panel():
        key = select_panel_state.get("key") or ""
        if not key:
            return ft.Container(height=0)

        meta = SELECT_META.get(key)
        if not meta:
            return ft.Container(height=0)

        control = meta["control"]
        options = get_select_options(key)
        if "全部" not in options:
            options = ["全部"] + options

        def choose(value: str):
            def handler(e=None):
                control.value = value
                if key == "material":
                    ensure_select_value(supplier_dd, get_select_options("supplier"))
                select_panel_state["key"] = ""
                rebuild()
            return handler

        option_controls = []
        for option in options:
            selected = option == control.value
            option_controls.append(
                ft.Container(
                    height=42,
                    border_radius=10,
                    bgcolor=BLUE_SOFT if selected else "#FFFFFF",
                    border=ft.border.all(1, BLUE_BORDER if selected else "#E5EAF2"),
                    padding=ft.padding.symmetric(horizontal=12),
                    margin=ft.margin.only(bottom=6),
                    alignment=ft.Alignment(-1, 0),
                    ink=True,
                    on_click=choose(option),
                    content=ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(option, size=14, color=BLUE if selected else TEXT_MAIN, weight=ft.FontWeight.BOLD if selected else ft.FontWeight.W_500, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Icon(ft.Icons.CHECK_CIRCLE, size=18, color=BLUE, visible=selected),
                        ],
                    ),
                )
            )

        panel_height = min(250, max(90, len(options) * 48))
        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.border.all(1, BLUE_BORDER),
            border_radius=14,
            padding=12,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(meta["icon"], size=18, color=BLUE),
                            ft.Text(f"選擇{meta['label']}", size=14, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                            ft.Container(expand=True),
                            ft.Container(
                                width=34,
                                height=30,
                                border_radius=10,
                                bgcolor=SOFT,
                                alignment=ft.Alignment(0, 0),
                                ink=True,
                                on_click=lambda e: (select_panel_state.update({"key": ""}), rebuild()),
                                content=ft.Icon(ft.Icons.CLOSE, size=17, color=TEXT_SUB),
                            ),
                        ],
                    ),
                    ft.Container(
                        height=panel_height,
                        content=ft.Column(
                            spacing=0,
                            scroll=ft.ScrollMode.AUTO,
                            controls=option_controls,
                        ),
                    ),
                ],
            ),
        )

    def build_advanced_filter_area():
        """
        全條件篩選區。
        手機版採 2 欄緊湊排列，避免欄位全部直排且右側留白；
        桌機版自然延伸為 3 欄。欄位標題仍在外側，維持現場可讀性。
        """
        return card_box(
            content=ft.Column(
                spacing=15,
                controls=[
                    section_header(ft.Icons.TUNE_OUTLINED, "全條件篩選", "選擇資料類型與查詢條件後產生結果。", BLUE),
                    build_filter_options_status(),
                    ft.ResponsiveRow(
                        columns=12,
                        spacing=10,
                        run_spacing=10,
                        controls=[
                            data_type_button("打料紀錄"),
                            data_type_button("入庫紀錄"),
                            data_type_button("保養紀錄"),
                            data_type_button("交接紀錄"),
                        ],
                    ),
                    ft.Container(
                        bgcolor="#FFFFFF",
                        border=ft.border.all(1, "#E5EAF2"),
                        border_radius=16,
                        padding=ft.padding.symmetric(horizontal=12, vertical=14),
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                ft.Row(
                                    spacing=8,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=[
                                        ft.Icon(ft.Icons.FILTER_ALT_OUTLINED, size=20, color=TEXT_SUB),
                                        ft.Text("查詢條件", size=15, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                                        ft.Text("手機版採雙欄排列", size=12, color=TEXT_MUTED),
                                    ],
                                ),
                                ft.ResponsiveRow(
                                    columns=12,
                                    spacing=12,
                                    run_spacing=14,
                                    controls=[
                                        ft.Container(col={"xs": 6, "md": 4}, content=compact_field("日期起", date_start, ft.Icons.CALENDAR_MONTH_OUTLINED, required=True)),
                                        ft.Container(col={"xs": 6, "md": 4}, content=compact_field("日期迄", date_end, ft.Icons.EVENT_AVAILABLE_OUTLINED, required=True)),
                                        ft.Container(col={"xs": 6, "md": 4}, content=compact_select_field("category")),
                                        ft.Container(col={"xs": 6, "md": 4}, content=compact_select_field("material")),
                                        ft.Container(col={"xs": 6, "md": 4}, content=compact_select_field("supplier")),
                                        ft.Container(col={"xs": 6, "md": 4}, content=compact_select_field("machine")),
                                        ft.Container(col={"xs": 6, "md": 4}, content=compact_select_field("user")),
                                    ],
                                ),
                                build_select_panel(),
                            ],
                        ),
                    ),
                    ft.ResponsiveRow(
                        columns=12,
                        spacing=12,
                        run_spacing=12,
                        controls=[
                            ft.Container(col={"xs": 6, "md": 6}, content=outline_button("清除條件", ft.Icons.REFRESH_OUTLINED, clear_conditions, color="#475569")),
                            ft.Container(col={"xs": 6, "md": 6}, content=stable_button("產生查詢結果", ft.Icons.FILTER_ALT_OUTLINED, apply_advanced_conditions, bg=BLUE_BTN, fg="white")),
                        ],
                    ),
                ],
            ),
        )

    def build_result_table():
        columns = current_report_data.get("columns") or []
        rows = current_report_data.get("rows") or []
        if not columns:
            columns = ["日期", "資料類型", "名稱", "數量", "狀態"]

        display_rows = rows if show_all_rows["value"] else rows[:10]
        col_width = 150
        table_width = max(720, col_width * len(columns))

        def row_control(values, header: bool = False):
            return ft.Container(
                width=table_width,
                bgcolor="#F8FAFC" if header else "#FFFFFF",
                border=ft.border.only(bottom=ft.BorderSide(1, "#E5EAF2")),
                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                content=ft.Row(
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=col_width,
                            padding=ft.padding.only(right=10),
                            content=ft.Text(
                                str(v),
                                size=13,
                                color=TEXT_MAIN,
                                weight=ft.FontWeight.BOLD if header else ft.FontWeight.NORMAL,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        )
                        for v in values
                    ],
                ),
            )

        if not rows:
            body = ft.Container(
                padding=24,
                alignment=ft.Alignment(0, 0),
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.INFO_OUTLINE, size=32, color=TEXT_MUTED),
                        ft.Text("目前沒有資料", size=16, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                        ft.Text(current_report_data.get("summary_text") or "請先產生報表。", size=13, color=TEXT_SUB, text_align=ft.TextAlign.CENTER),
                    ],
                ),
            )
        else:
            body = ft.Column(spacing=0, controls=[row_control(columns, True)] + [row_control([row.get(col, "") for col in columns]) for row in display_rows])

        return ft.Container(
            border=ft.border.all(1, "#E5EAF2"),
            border_radius=12,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Row(
                scroll=ft.ScrollMode.AUTO,
                controls=[ft.Container(width=table_width, content=body)],
            ),
        )

    def build_export_download_panel():
        if not export_state.get("filename") and not export_state.get("csv_content"):
            return ft.Container(height=0)

        filename = export_state.get("filename") or "report.csv"
        keep_days = export_state.get("expires_after_days")
        cleanup = export_state.get("cleanup") or {}
        deleted_count = cleanup.get("deleted_count") or 0
        csv_content = export_state.get("csv_content") or ""
        path_text = export_state.get("path") or ""

        keep_text = f"此 CSV 為暫存檔，VM 上約保留 {keep_days} 天。" if keep_days else "此 CSV 為暫存檔。"
        cleanup_text = f"本次已清理 {deleted_count} 個舊 CSV。" if deleted_count else ""

        if not csv_content:
            csv_content = "CSV 檔案已產生，但目前無法讀取文字內容。請稍後再試，或由管理者至 VM exports 資料夾查看。"

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
                            ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=22, color=GREEN),
                            ft.Column(
                                expand=True,
                                spacing=4,
                                controls=[
                                    ft.Text("CSV 已產生", size=16, color=GREEN, weight=ft.FontWeight.BOLD),
                                    ft.Text(filename, size=12, color=TEXT_SUB, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                    ft.Text(keep_text, size=12, color=TEXT_MUTED),
                                    ft.Text(cleanup_text, size=12, color=TEXT_MUTED, visible=bool(cleanup_text)),
                                    ft.Text(f"VM 檔案位置：{path_text}", size=11, color=TEXT_MUTED, visible=bool(path_text), max_lines=2, overflow=ft.TextOverflow.VISIBLE),
                                ],
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        bgcolor="#FFFFFF",
                        border=ft.border.all(1, GREEN_BORDER),
                        border_radius=12,
                        padding=12,
                        content=ft.Column(
                            spacing=8,
                            controls=[
                                ft.Text(
                                    "CSV 已產生；目前 VM / Flet Web 尚未打通穩定下載路徑，因此先顯示 CSV 內容供備援使用。",
                                    size=12,
                                    color=TEXT_SUB,
                                ),
                                ft.Text(
                                    "正式下載功能將在之後改走 80 port / Nginx，打通 /exports/ 靜態下載路徑後再啟用。",
                                    size=12,
                                    color=TEXT_SUB,
                                ),
                                ft.Text(
                                    "桌機操作建議：點進文字框 → Ctrl+A 全選 → Ctrl+C 複製 → 貼到記事本或 Excel；另存時副檔名使用 .csv。手機使用者若不易全選，請先以頁面查看報表為主。",
                                    size=12,
                                    color=TEXT_SUB,
                                ),
                                ft.TextField(
                                    value=csv_content,
                                    read_only=True,
                                    multiline=True,
                                    min_lines=8,
                                    max_lines=14,
                                    border_radius=10,
                                    border_color=GREEN_BORDER,
                                    focused_border_color=GREEN,
                                    text_size=12,
                                    bgcolor="#FFFFFF",
                                    content_padding=ft.padding.symmetric(horizontal=10, vertical=10),
                                ),
                            ],
                        ),
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

        badge = ft.Container(
            height=30,
            padding=ft.padding.symmetric(horizontal=12),
            border_radius=15,
            bgcolor=BLUE_SOFT,
            border=ft.border.all(1, BLUE_BORDER),
            alignment=ft.Alignment(0, 0),
            content=ft.Text(f"共 {count} 筆", size=13, color=BLUE, weight=ft.FontWeight.BOLD),
        )

        return card_box(
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Column(
                        spacing=4,
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.TABLE_CHART_OUTLINED, size=22, color=TEXT_SUB),
                                    ft.Text("結果預覽", size=21, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                                    badge,
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                wrap=True,
                            ),
                            ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=TEXT_MAIN, max_lines=3, overflow=ft.TextOverflow.VISIBLE),
                            ft.Text(current_report_data.get("summary_text") or "", size=13, color=TEXT_SUB, max_lines=3, visible=bool(current_report_data.get("summary_text"))),
                        ],
                    ),
                    build_result_table(),
                    ft.Row(
                        controls=[
                            ft.Text(note, size=12, color=TEXT_MUTED),
                            ft.Container(expand=True),
                            outline_button("收合" if show_all_rows["value"] else "查看全部", ft.Icons.KEYBOARD_ARROW_UP if show_all_rows["value"] else ft.Icons.VISIBILITY_OUTLINED, toggle_show_all, color=BLUE, height=42),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.ResponsiveRow(
                        columns=12,
                        spacing=12,
                        run_spacing=12,
                        controls=[
                            ft.Container(col={"xs": 12, "md": 6}, content=stable_button("匯出 CSV", ft.Icons.FILE_DOWNLOAD_OUTLINED, export_csv_background, bg=BLUE_BTN, fg="white", disabled=not bool(rows))),
                            ft.Container(col={"xs": 12, "md": 6}, content=outline_button("清除結果", ft.Icons.REFRESH_OUTLINED, clear_conditions, color="#475569")),
                        ],
                    ),
                    build_export_download_panel(),
                ],
            ),
        )

    def build_content():
        page.bgcolor = BG
        controls = [
            title_block(ft.Icons.INSERT_CHART_OUTLINED, "報表中心", "快速報表一鍵產生，全條件篩選可自訂查詢並匯出 CSV。", BLUE),
            status_banner(),
            card_box(
                content=ft.Column(
                    spacing=15,
                    controls=[
                        section_header(ft.Icons.TOUCH_APP_OUTLINED, "選擇報表方式", "快速報表直接產生；全條件篩選才需要設定查詢條件。", BLUE),
                        build_mode_selector(),
                    ],
                )
            ),
        ]

        if selected_mode["value"] == "quick":
            controls.append(build_quick_report_area())
        else:
            controls.append(build_advanced_filter_area())

        if loading_state.get("active"):
            controls.append(
                ft.Container(
                    bgcolor=BLUE_SOFT,
                    border=ft.border.all(1, BLUE_BORDER),
                    border_radius=14,
                    padding=12,
                    content=ft.Row(
                        spacing=10,
                        controls=[ft.ProgressRing(width=18, height=18, stroke_width=2, color=BLUE), ft.Text(loading_state.get("message") or "處理中...", size=14, color=BLUE, weight=ft.FontWeight.BOLD)],
                    ),
                )
            )

        controls.extend([build_preview_card(), ft.Container(height=90)])

        return ft.Container(
            bgcolor=BG,
            padding=ft.padding.only(left=18, right=18, top=18),
            content=ft.Column(
                spacing=18,
                scroll=ft.ScrollMode.AUTO,
                controls=controls,
            ),
        )

    def rebuild():
        main_host.content = build_content()
        safe_page_update()

    # =====================================================
    # 8. 初始化
    # =====================================================
    main_host.content = build_content()
    start_filter_options_load()

    return main_host