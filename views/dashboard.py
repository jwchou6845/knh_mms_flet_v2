# =====================================================
# KNH MMS v2
# File: views/dashboard.py
# File Revision: 2026-05-12-dashboard-summary-bar-r1
# Status: current working version
# Last Updated: 2026-05-12 Asia/Taipei
#
# Purpose:
# - 首頁儀表板 UI。
# - 顯示交接待辦、保養待辦、低水位、本月用量與即時庫存圖表。
#
# Major Changes in This Revision:
# - 即時庫存 / 即時回用料庫存長條圖改為窄螢幕自適應。
# - 長條圖採左側名稱欄 / 中間長條欄 / 右側數值欄三段式。
# - 保留原本漸層長條視覺，不改成純色或重設計。
#
# Notes:
# - Flet 0.84。
# - 不使用 page.push_route()。
# - 本次不修改 reports.py、CSV/PDF 下載機制或 Supabase schema。
# =====================================================

import flet as ft
import base64
import threading
import time

from services.dashboard_service import load_dashboard_page_data
from services.handover_service import (
    load_completed_outgoing_handover_summary,
    load_open_handover_tasks,
)


def DashboardContent(page: ft.Page):
    """
    KNH MMS Dashboard
    Flet 0.84 + Python + Supabase

    已轉 Supabase：
    - 即時新料庫存
    - 即時回用料庫存
    - 低水位警示
    - 本月新料 / 母粒 / 回用料用量
    - 保養待辦摘要
    - 交接待辦摘要
    """

    # =====================================================
    # View lifecycle / 非阻塞載入狀態
    # =====================================================
    if not hasattr(page, "session_data"):
        page.session_data = {}

    view_token = object()
    page.session_data["_dashboard_view_token"] = view_token

    DEFAULT_USAGE_SUMMARY = {"新料": {}, "母粒": {}, "回用料": {}}
    DEFAULT_MAINTENANCE_SUMMARY = {
        "total": 0,
        "overdue": 0,
        "today": 0,
        "abnormal": 0,
        "preview": [],
        "error": "",
    }
    DEFAULT_HANDOVER_SUMMARY = {
        "total": 0,
        "high": 0,
        "abnormal": 0,
        "todo": 0,
        "completed_outgoing": 0,
        "completed_preview": [],
        "preview": [],
        "error": "",
    }

    def default_dashboard_data():
        return {
            "current_ym": "同步中",
            "current_time": "同步中",
            "new_stock_data": [],
            "recycled_stock_data": [],
            "alert_items": [],
            "usage_summary": {"新料": {}, "母粒": {}, "回用料": {}},
            "maintenance_summary": dict(DEFAULT_MAINTENANCE_SUMMARY),
        }

    state = {
        "loading": True,
        "loaded": False,
        "dashboard_error": "",
        "sync_visible": True,
        "sync_theme": "blue",
        "sync_message": "首頁資料同步中",
        "dashboard_data": default_dashboard_data(),
        "handover_summary": dict(DEFAULT_HANDOVER_SUMMARY),
    }

    def is_active_view():
        route = str(getattr(page, "route", "") or "")
        return (
            page.session_data.get("_dashboard_view_token") is view_token
            and (not route or route == "/" or route == "/dashboard" or "dashboard" in route)
        )

    def safe_page_update():
        try:
            page.update()
        except Exception as ex:
            print("dashboard page.update failed:", repr(ex))

    def get_dashboard_data():
        return state.get("dashboard_data") or default_dashboard_data()

    def get_usage_summary():
        return get_dashboard_data().get("usage_summary") or DEFAULT_USAGE_SUMMARY

    def set_sync_status(message: str, theme: str = "blue", visible: bool = True):
        state["sync_message"] = message
        state["sync_theme"] = theme
        state["sync_visible"] = visible

    def schedule_sync_hide(delay_seconds: int = 3):
        def worker():
            time.sleep(delay_seconds)
            if not is_active_view():
                return
            if state.get("sync_theme") == "green":
                state["sync_visible"] = False
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    # =====================================================
    # 交接待辦摘要：Supabase
    # =====================================================
    def get_user_name():
        if hasattr(page, "session_data"):
            return str(page.session_data.get("user_name", "") or "")
        return ""

    def can_view_all_handover_tasks():
        if hasattr(page, "session_data"):
            return bool(page.session_data.get("can_view_all_tasks", False))
        return False

    def load_handover_task_summary():
        summary = {
            "total": 0,
            "high": 0,
            "abnormal": 0,
            "todo": 0,
            "completed_outgoing": 0,
            "completed_preview": [],
            "preview": [],
            "error": "",
        }

        result = load_open_handover_tasks(
            current_user_name=get_user_name(),
            can_view_all_tasks=can_view_all_handover_tasks(),
        )

        if not result.ok:
            summary["error"] = result.message
            print("交接待辦摘要讀取失敗:", result.message)
            return summary

        tasks = (result.data or {}).get("tasks", [])

        for task in tasks:
            task_type = str(task.get("type") or "待辦")
            severity = str(task.get("severity") or "中")
            content = str(task.get("content") or "").strip()

            summary["total"] += 1

            if severity == "高":
                summary["high"] += 1

            if task_type == "異常":
                summary["abnormal"] += 1
            elif task_type == "待辦":
                summary["todo"] += 1

            if len(summary["preview"]) < 3:
                summary["preview"].append(
                    {
                        "type": task_type,
                        "severity": severity,
                        "content": content if content else "(無內容)",
                    }
                )

        completed_result = load_completed_outgoing_handover_summary(
            current_user_name=get_user_name(),
            limit=50,
        )

        if completed_result.ok:
            completed_data = completed_result.data or {}
            summary["completed_outgoing"] = int(completed_data.get("total", 0) or 0)
            summary["completed_preview"] = completed_data.get("preview", []) or []
        else:
            print("已完成交接提示讀取失敗:", completed_result.message)

        return summary

    # =====================================================
    # 摘要卡共用樣式
    # =====================================================
    def metric_box(label, value, color):
        return ft.Container(
            width=102,
            padding=ft.padding.symmetric(horizontal=10, vertical=9),
            bgcolor="#F8FAFC",
            border_radius=14,
            border=ft.border.all(1, "#E5EAF2"),
            content=ft.Column(
                controls=[
                    ft.Text(str(value), size=21, weight=ft.FontWeight.BOLD, color=color),
                    ft.Text(label, size=12, color="#64748B"),
                ],
                spacing=1,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def summary_shell_card(
        title: str,
        subtitle: str,
        icon,
        theme_color: str,
        theme_border: str,
        metrics: list[ft.Control],
        preview_controls: list[ft.Control],
        open_label: str,
        open_route: str,
        empty_text: str,
        has_error: bool = False,
    ):
        is_open = {"value": False}

        if not preview_controls and not has_error:
            preview_controls = [
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=12, vertical=10),
                    bgcolor="#F8FAFC",
                    border=ft.border.all(1, "#E5EAF2"),
                    border_radius=12,
                    content=ft.Text(empty_text, size=13, color="#64748B"),
                )
            ]

        preview_panel = ft.Column(
            controls=preview_controls,
            spacing=8,
            visible=False,
        )

        toggle_icon = ft.Icon(ft.Icons.EXPAND_MORE, size=18, color="#64748B")
        toggle_text = ft.Text(
            "展開事項",
            size=13,
            color="#475569",
            weight=ft.FontWeight.W_600,
        )

        def toggle_preview(e):
            is_open["value"] = not is_open["value"]
            preview_panel.visible = is_open["value"]
            toggle_icon.name = ft.Icons.EXPAND_LESS if is_open["value"] else ft.Icons.EXPAND_MORE
            toggle_text.value = "收起事項" if is_open["value"] else "展開事項"
            page.update()

        toggle_button = ft.Container(
            height=36,
            padding=ft.padding.symmetric(horizontal=12),
            border_radius=18,
            bgcolor="#F8FAFC",
            border=ft.border.all(1, "#E2E8F0"),
            on_click=toggle_preview,
            content=ft.Row(
                controls=[toggle_icon, toggle_text],
                spacing=5,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
        )

        open_link = ft.Container(
            height=36,
            padding=ft.padding.symmetric(horizontal=10),
            border_radius=18,
            on_click=lambda e: page.go(open_route),
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.OPEN_IN_NEW, size=16, color="#4F7FB8"),
                    ft.Text(open_label, size=13, color="#4F7FB8", weight=ft.FontWeight.W_600),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
        )

        return ft.Container(
            padding=20,
            bgcolor="#FFFFFF",
            border_radius=22,
            border=ft.border.all(1, theme_border),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=5,
                color="#05000000",
                offset=ft.Offset(0, 1),
            ),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Container(
                                width=50,
                                height=50,
                                bgcolor="#F8FAFC",
                                border_radius=14,
                                content=ft.Icon(icon, color=theme_color, size=26),
                                alignment=ft.Alignment(0, 0),
                                shadow=ft.BoxShadow(
                                    spread_radius=0,
                                    blur_radius=3,
                                    color="#0A000000",
                                    offset=ft.Offset(0, 1),
                                ),
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color="#111827"),
                                    ft.Text(
                                        subtitle,
                                        size=13,
                                        color="#64748B",
                                        max_lines=3,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                        ],
                        spacing=15,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        controls=metrics,
                        spacing=10,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    ft.Row(
                        controls=[
                            toggle_button,
                            open_link,
                        ],
                        spacing=8,
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    preview_panel,
                ],
                spacing=14,
            ),
        )

    def handover_summary_card(summary):
        has_error = bool(summary.get("error"))
        total = int(summary.get("total", 0))
        high = int(summary.get("high", 0))
        abnormal = int(summary.get("abnormal", 0))
        todo = int(summary.get("todo", 0))
        completed_outgoing = int(summary.get("completed_outgoing", 0))

        if has_error:
            theme_border = "#FECACA"
            theme_color = "#DC2626"
            title = "交接待辦摘要載入失敗"
            subtitle = summary.get("error", "未知錯誤")
            icon = ft.Icons.ERROR_OUTLINE
        elif total > 0:
            theme_border = "#FECACA" if high > 0 else "#FDBA74"
            theme_color = "#DC2626" if high > 0 else "#EA580C"
            title = "交接待辦摘要"

            if completed_outgoing > 0:
                subtitle = (
                    f"目前有 {total} 筆尚未完成項目；"
                    f"你交出的待辦已有 {completed_outgoing} 筆完成，請至交接待辦追蹤查看。"
                )
            else:
                subtitle = f"目前有 {total} 筆尚未完成項目，需要追蹤處理。"

            icon = ft.Icons.TASK_ALT_OUTLINED
        elif completed_outgoing > 0:
            theme_border = "#BFDBFE"
            theme_color = "#2563EB"
            title = "交接完成提示"
            subtitle = f"你交出的待辦已有 {completed_outgoing} 筆完成，請至交接待辦追蹤查看。"
            icon = ft.Icons.MARK_EMAIL_READ_OUTLINED
        else:
            theme_border = "#A7F3D0"
            theme_color = "#059669"
            title = "交接待辦摘要"
            subtitle = "目前沒有尚未完成的異常或待辦。"
            icon = ft.Icons.CHECK_CIRCLE_OUTLINE

        preview_controls = []
        for item in summary.get("preview", []):
            task_type = item["type"]
            severity = item["severity"]
            content = item["content"]

            tag_color = "#DC2626" if task_type == "異常" else "#2563EB"
            severity_color = "#DC2626" if severity == "高" else "#EA580C" if severity == "中" else "#059669"

            preview_controls.append(
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=12, vertical=10),
                    bgcolor="#F8FAFC",
                    border=ft.border.all(1, "#E5EAF2"),
                    border_radius=12,
                    content=ft.Row(
                        controls=[
                            ft.Text(task_type, size=12, color=tag_color, weight=ft.FontWeight.BOLD),
                            ft.Text(severity, size=12, color=severity_color, weight=ft.FontWeight.BOLD),
                            ft.Text(content, size=13, color="#334155", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )

        if completed_outgoing > 0:
            for item in summary.get("completed_preview", [])[:2]:
                completed_by = item.get("completed_by_name", "-")
                completed_at = item.get("completed_at", "-")
                content = item.get("content", "(無內容)")

                preview_controls.append(
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=12, vertical=10),
                        bgcolor="#EFF6FF",
                        border=ft.border.all(1, "#BFDBFE"),
                        border_radius=12,
                        content=ft.Row(
                            controls=[
                                ft.Text("已完成", size=12, color="#2563EB", weight=ft.FontWeight.BOLD),
                                ft.Text(completed_at, size=12, color="#64748B"),
                                ft.Text(f"{completed_by}：{content}", size=13, color="#334155", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    )
                )

        return summary_shell_card(
            title=title,
            subtitle=subtitle,
            icon=icon,
            theme_color=theme_color,
            theme_border=theme_border,
            metrics=[
                metric_box("未完成", total, theme_color),
                metric_box("高嚴重度", high, "#DC2626"),
                metric_box("異常", abnormal, "#EA580C"),
                metric_box("待辦", todo, "#2563EB"),
                metric_box("已完成", completed_outgoing, "#059669"),
            ],
            preview_controls=preview_controls,
            open_label="查看交接待辦",
            open_route="/handover_tasks",
            empty_text="交接狀態正常，沒有待追蹤項目。",
            has_error=has_error,
        )

    def resolve_handover_summary_border(summary):
        """
        首頁兩張待辦摘要卡的外框顏色以交接待辦摘要為基準。
        這裡只統一外框視覺層級；保養卡本身的 icon / 數字色仍保留保養語意。
        """
        if bool(summary.get("error")):
            return "#FECACA"

        total = int(summary.get("total", 0) or 0)
        high = int(summary.get("high", 0) or 0)
        completed_outgoing = int(summary.get("completed_outgoing", 0) or 0)

        if total > 0:
            return "#FECACA" if high > 0 else "#FDBA74"

        if completed_outgoing > 0:
            return "#BFDBFE"

        return "#A7F3D0"

    def maintenance_summary_card(summary):
        has_error = bool(summary.get("error"))
        total = int(summary.get("total", 0))
        overdue = int(summary.get("overdue", 0))
        today = int(summary.get("today", 0))
        abnormal = int(summary.get("abnormal", 0))

        if has_error:
            theme_border = "#FECACA"
            theme_color = "#DC2626"
            title = "保養待辦摘要載入失敗"
            subtitle = summary.get("error", "未知錯誤")
            icon = ft.Icons.ERROR_OUTLINE
        elif total > 0:
            theme_border = "#FECACA" if overdue > 0 else "#FDBA74"
            theme_color = "#DC2626" if overdue > 0 else "#EA580C"
            title = "保養待辦摘要"
            subtitle = f"目前有 {total} 筆保養項目需要追蹤處理。"
            icon = ft.Icons.HANDYMAN_OUTLINED
        else:
            theme_border = "#A7F3D0"
            theme_color = "#059669"
            title = "保養待辦摘要"
            subtitle = "目前沒有需要立即處理的保養項目。"
            icon = ft.Icons.CHECK_CIRCLE_OUTLINE

        if not has_error:
            # 與交接待辦摘要外框顏色保持一致，避免首頁兩張摘要卡視覺層級不一致。
            theme_border = resolve_handover_summary_border(state.get("handover_summary") or DEFAULT_HANDOVER_SUMMARY)

        preview_controls = []
        for item in summary.get("preview", []):
            due_tag = item.get("due_tag", "-")
            item_name = item.get("item_name", "-")
            maintenance_type = item.get("maintenance_type", "-")
            machine_area = item.get("machine_area", "-")

            tag_color = "#DC2626" if due_tag == "逾期" else "#EA580C" if due_tag in ["今日", "明日"] else "#2563EB"
            type_color = "#4F7FB8" if maintenance_type == "清潔" else "#C96D32"

            preview_controls.append(
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=12, vertical=10),
                    bgcolor="#F8FAFC",
                    border=ft.border.all(1, "#E5EAF2"),
                    border_radius=12,
                    content=ft.Row(
                        controls=[
                            ft.Text(due_tag, size=12, color=tag_color, weight=ft.FontWeight.BOLD),
                            ft.Text(maintenance_type, size=12, color=type_color, weight=ft.FontWeight.BOLD),
                            ft.Text(item_name, size=13, color="#334155", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                            ft.Text(machine_area, size=12, color="#64748B"),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )

        return summary_shell_card(
            title=title,
            subtitle=subtitle,
            icon=icon,
            theme_color=theme_color,
            theme_border=theme_border,
            metrics=[
                metric_box("待保養", total, theme_color),
                metric_box("逾期", overdue, "#DC2626"),
                metric_box("今日", today, "#EA580C"),
                metric_box("近期異常", abnormal, "#7C3AED"),
            ],
            preview_controls=preview_controls,
            open_label="查看保養紀錄",
            open_route="/maintenance",
            empty_text="保養狀態正常，沒有待追蹤項目。",
            has_error=has_error,
        )

    # =====================================================
    # SVG Sparkline：保留折線視覺，但不使用 flet_charts
    # 目的：避免部分 Flet 0.84 / Desktop 環境將 chart canvas 渲染成大片灰色區塊
    # =====================================================
    def _hex_to_rgba(hex_color: str, alpha: float = 0.16) -> str:
        color = str(hex_color or "#2F80ED").replace("#", "")
        if len(color) != 6:
            return f"rgba(47,128,237,{alpha})"

        try:
            r = int(color[0:2], 16)
            g = int(color[2:4], 16)
            b = int(color[4:6], 16)
            return f"rgba({r},{g},{b},{alpha})"
        except Exception:
            return f"rgba(47,128,237,{alpha})"

    def sparkline_image(history_data, theme_color="#2F80ED"):
        values = []
        for item in history_data or []:
            try:
                values.append(float(item))
            except Exception:
                values.append(0.0)

        if len(values) < 2:
            values = [0, 0, 0, 0, 0, 0, 0]

        width = 132
        height = 42
        pad_x = 6
        pad_y = 7

        min_v = min(values)
        max_v = max(values)

        if max_v == min_v:
            # 全部一樣時，畫成中間的穩定線，不要硬拉出鋸齒
            min_v -= 1
            max_v += 1

        points = []
        for idx, value in enumerate(values):
            x = pad_x + (idx / max(1, len(values) - 1)) * (width - pad_x * 2)
            normalized = (value - min_v) / (max_v - min_v)
            y = height - pad_y - normalized * (height - pad_y * 2)
            points.append((x, y))

        def line_path(points):
            if not points:
                return ""

            if len(points) == 1:
                return f"M {points[0][0]:.1f} {points[0][1]:.1f}"

            d = f"M {points[0][0]:.1f} {points[0][1]:.1f}"
            for i in range(1, len(points)):
                x0, y0 = points[i - 1]
                x1, y1 = points[i]
                mid_x = (x0 + x1) / 2
                d += f" C {mid_x:.1f} {y0:.1f}, {mid_x:.1f} {y1:.1f}, {x1:.1f} {y1:.1f}"
            return d

        path_d = line_path(points)
        base_y = height - pad_y
        area_d = f"{path_d} L {points[-1][0]:.1f} {base_y:.1f} L {points[0][0]:.1f} {base_y:.1f} Z"

        fill_color = _hex_to_rgba(theme_color, 0.11)

        # 加一條非常淡的底線，讓線圖不會浮在空中
        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
            <line x1="{pad_x}" y1="{base_y}" x2="{width - pad_x}" y2="{base_y}" stroke="#E5EAF2" stroke-width="1"/>
            <path d="{area_d}" fill="{fill_color}"/>
            <path d="{path_d}" fill="none" stroke="{theme_color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        """

        encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")

        return ft.Image(
            src=f"data:image/svg+xml;base64,{encoded}",
            width=132,
            height=42,
        )

    # =====================================================
    # KPI 數據小卡
    # =====================================================
    def stat_card(title, value, unit, trend, is_up=True, theme_color="#2F80ED", history_data=None):
        if not history_data or len(history_data) < 2:
            history_data = [0, 0, 0, 0, 0, 0, 0]

        mini_sparkline = sparkline_image(history_data, theme_color)

        return ft.Container(
            width=160,
            bgcolor="#FFFFFF",
            border_radius=18,
            padding=18,
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=5, color="#05000000", offset=ft.Offset(0, 1)),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Container(width=10, height=10, bgcolor=theme_color, border_radius=5),
                            ft.Text(title, size=14, color="#4B5563", weight=ft.FontWeight.W_500, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        controls=[
                            ft.Text(value, size=26, weight=ft.FontWeight.BOLD, color="#111827"),
                            ft.Container(
                                content=ft.Text(unit, size=11, color="#9CA3AF", weight=ft.FontWeight.NORMAL),
                                padding=ft.padding.only(bottom=4),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.END,
                        spacing=3,
                    ),
                    ft.Container(height=45, content=mini_sparkline),
                    ft.Row(
                        controls=[
                            ft.Text("較上月", size=12, color="#9CA3AF"),
                            ft.Text(
                                trend,
                                size=12,
                                weight=ft.FontWeight.BOLD,
                                color="#10B981" if is_up else "#EF4444",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                spacing=8,
            ),
        )

    def usage_section(icon, title, bg_color, border_color, theme_color, cards, current_month):
        return ft.Container(
            padding=20,
            bgcolor=bg_color,
            border_radius=22,
            border=ft.border.all(1, border_color),
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=5, color="#05000000", offset=ft.Offset(0, 1)),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                width=50,
                                height=50,
                                bgcolor="#FFFFFF",
                                border_radius=14,
                                content=ft.Icon(icon, color=theme_color, size=24),
                                alignment=ft.Alignment(0, 0),
                                shadow=ft.BoxShadow(
                                    spread_radius=0,
                                    blur_radius=3,
                                    color="#0A000000",
                                    offset=ft.Offset(0, 1),
                                ),
                            ),
                            ft.Column(
                                [
                                    ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color="#111827"),
                                    ft.Text(f"{current_month} 累計", size=13, color="#6B7280"),
                                ],
                                spacing=2,
                            ),
                        ],
                        spacing=15,
                    ),
                    ft.Container(height=5),
                    ft.Row(scroll=ft.ScrollMode.AUTO, spacing=12, controls=cards),
                ],
                spacing=10,
            ),
        )

    def custom_ui_bar_chart(title, data_list, max_val, legend_items, update_time, unit=""):
        """
        自製長條圖。

        r1 修正重點：
        - 左側名稱欄、中間長條欄、右側數值欄三段式。
        - 中間長條欄依 page.width 自適應，但設最大寬度上限。
        - 保留原本漸層 LinearGradient 視覺，不改成純色。
        - 目的：避免 HTC 等窄螢幕手機上最大值列把右側數字擠出或遮蔽。
        """
        bars = []
        sorted_data = sorted(data_list, key=lambda x: x[1], reverse=True)

        screen_width = page.width or 390

        # 寬度配置原則：
        # 1. 手機窄螢幕時縮短名稱欄與 bar 欄，保留數值欄。
        # 2. 桌機寬螢幕時 bar 欄最多不超過上限，避免長條圖無限制拉滿。
        # 3. 「包」數值較短，「KG」可能出現 8,000 KG 以上，右側欄給較寬。
        if screen_width < 390:
            name_width = 82
            bar_max_width = 76
        elif screen_width < 520:
            name_width = 94
            bar_max_width = 96
        elif screen_width < 760:
            name_width = 110
            bar_max_width = 130
        elif screen_width < 1100:
            name_width = 120
            bar_max_width = 170
        else:
            name_width = 130
            bar_max_width = 220

        value_width = 104 if str(unit).upper() == "KG" else 76

        # 整列寬度固定為三欄加 spacing，外層保留橫向捲動能力。
        # 手機會優先縮 bar，不讓數字欄被擠掉。
        row_width = name_width + bar_max_width + value_width + 20

        for name, val, color_top, color_bottom in sorted_data:
            safe_max = max_val if max_val > 0 else 1
            bar_width = (val / safe_max) * bar_max_width
            if val > 0:
                bar_width = max(4, min(bar_max_width, bar_width))
            else:
                bar_width = 0

            bars.append(
                ft.Container(
                    width=row_width,
                    content=ft.Row(
                        [
                            ft.Container(
                                width=name_width,
                                alignment=ft.Alignment(1, 0),
                                content=ft.Text(
                                    name,
                                    size=13,
                                    color="#4B5563",
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                    text_align=ft.TextAlign.RIGHT,
                                ),
                            ),
                            ft.Container(
                                width=bar_max_width,
                                height=14,
                                alignment=ft.Alignment(-1, 0),
                                content=ft.Container(
                                    width=bar_width,
                                    height=14,
                                    border_radius=4,
                                    gradient=ft.LinearGradient(
                                        begin=ft.Alignment(-1, 0),
                                        end=ft.Alignment(1, 0),
                                        colors=[color_top, color_bottom],
                                    ) if bar_width > 0 else None,
                                    bgcolor="#EEF2F7" if bar_width <= 0 else None,
                                ),
                            ),
                            ft.Container(
                                width=value_width,
                                alignment=ft.Alignment(1, 0),
                                content=ft.Text(
                                    f"{val:,} {unit}",
                                    size=13,
                                    color="#111827",
                                    weight=ft.FontWeight.BOLD,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                    text_align=ft.TextAlign.RIGHT,
                                ),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                )
            )

        if not bars:
            bars.append(
                ft.Container(
                    padding=16,
                    content=ft.Text("目前沒有資料。", size=13, color="#64748B"),
                )
            )

        legends = [
            ft.Row(
                [
                    ft.Container(width=10, height=10, border_radius=5, bgcolor=color),
                    ft.Text(label, size=12, color="#6B7280"),
                ],
                spacing=5,
            )
            for label, color in legend_items
        ]

        return ft.Container(
            padding=20,
            bgcolor="#FFFFFF",
            border_radius=22,
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=10, color="#0A000000", offset=ft.Offset(0, 4)),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.FORMAT_LIST_BULLETED_ROUNDED, color="#374151", size=22),
                                    ft.Text(title, size=16, weight=ft.FontWeight.BOLD, color="#111827"),
                                ],
                                spacing=10,
                            ),
                            ft.Text(f"{update_time} 更新", size=12, color="#9CA3AF"),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=10, color="#F3F4F6"),
                    ft.Container(
                        height=220,
                        content=ft.Row(
                            scroll=ft.ScrollMode.AUTO,
                            controls=[
                                ft.Container(
                                    width=row_width,
                                    content=ft.Column(bars, spacing=12, scroll=ft.ScrollMode.AUTO),
                                )
                            ],
                        ),
                    ),
                    ft.Divider(height=10, color="#F3F4F6"),
                    ft.Container(
                        content=ft.Row(
                            legends,
                            alignment=ft.MainAxisAlignment.START,
                            spacing=15,
                            scroll=ft.ScrollMode.AUTO,
                        )
                    ),
                ]
            ),
        )

    def build_cards(category, theme_color):
        cards = []

        for name, data in get_usage_summary().get(category, {}).items():
            this_m = float(data.get("this_month", 0))
            last_m = float(data.get("last_month", 0))

            if this_m == 0 and last_m == 0:
                continue

            if last_m > 0:
                growth_rate = ((this_m - last_m) / last_m) * 100
            else:
                growth_rate = 100.0 if this_m > 0 else 0.0

            is_up = growth_rate >= 0
            trend_str = f"▲ {abs(growth_rate):.1f}%" if is_up else f"▼ {abs(growth_rate):.1f}%"

            if last_m == 0 and this_m > 0:
                trend_str = "▲ 新啟用"
            elif last_m > 0 and this_m == 0:
                trend_str = "▼ 本月未用"

            history = data.get("history", [])
            if not history:
                history = [last_m, this_m]

            cards.append(
                stat_card(
                    title=name,
                    value=f"{int(this_m):,}",
                    unit="KG",
                    trend=trend_str,
                    is_up=is_up,
                    theme_color=theme_color,
                    history_data=history,
                )
            )

        if not cards:
            cards.append(stat_card(f"本月無{category}紀錄", "0", "KG", "-", True, theme_color))

        return cards

    def sync_status_banner():
        if not state.get("sync_visible"):
            return ft.Container(height=0)

        theme = state.get("sync_theme", "blue")
        if theme == "green":
            bg, border, fg, icon = "#ECFDF5", "#A7F3D0", "#10B981", ft.Icons.CHECK_CIRCLE_OUTLINE
        elif theme == "red":
            bg, border, fg, icon = "#FEF2F2", "#FECACA", "#DC2626", ft.Icons.ERROR_OUTLINE
        else:
            bg, border, fg, icon = "#E5F0FF", "#BFDBFE", "#2563EB", ft.Icons.SYNC

        return ft.Container(
            height=36,
            padding=ft.padding.symmetric(horizontal=14),
            border_radius=18,
            bgcolor=bg,
            border=ft.border.all(1, border),
            alignment=ft.Alignment(0, 0),
            content=ft.Row(
                controls=[
                    ft.Icon(icon, size=17, color=fg),
                    ft.Text(str(state.get("sync_message") or ""), size=13, color=fg, weight=ft.FontWeight.W_600),
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def build_dashboard_controls():
        dashboard_data = get_dashboard_data()
        current_ym = dashboard_data.get("current_ym", "")
        current_time_str = dashboard_data.get("current_time", "")
        new_stock_data = dashboard_data.get("new_stock_data", []) or []
        recycled_stock_data = dashboard_data.get("recycled_stock_data", []) or []
        alert_items = dashboard_data.get("alert_items", []) or []
        maintenance_summary = dashboard_data.get("maintenance_summary") or dict(DEFAULT_MAINTENANCE_SUMMARY)
        handover_summary = state.get("handover_summary") or dict(DEFAULT_HANDOVER_SUMMARY)

        cards_new = build_cards("新料", "#2F80ED")
        cards_mb = build_cards("母粒", "#9C27B0")
        cards_recyc = build_cards("回用料", "#10B981")

        # 用實際最大值計算長條比例；不再先乘 1.2，避免最大值長條永遠只到約 83%。
        max_new_stock = max([item[1] for item in new_stock_data]) if new_stock_data else 20
        max_recycled_stock = max([item[1] for item in recycled_stock_data]) if recycled_stock_data else 9000

        alert_count = len(alert_items)
        alert_controls = [
            ft.Row(
                [
                    ft.Container(
                        width=50,
                        height=50,
                        bgcolor="#FFFFFF",
                        border_radius=14,
                        shadow=ft.BoxShadow(spread_radius=0, blur_radius=3, color="#0A000000", offset=ft.Offset(0, 1)),
                        content=ft.Icon(
                            ft.Icons.NOTIFICATIONS_ACTIVE,
                            color="#EF4444" if alert_count > 0 else "#10B981",
                        ),
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                "低水位警示" if alert_count > 0 else "庫存安全",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color="#111827",
                            ),
                            ft.Text(
                                f"目前有 {alert_count} 項原料低於安全庫存"
                                if alert_count > 0
                                else "所有原料皆在安全水位之上",
                                size=13,
                                color="#6B7280",
                            ),
                        ],
                        spacing=2,
                    ),
                ],
                spacing=15,
            ),
            ft.Container(height=5),
        ]

        if alert_count > 0:
            for item in alert_items:
                alert_controls.append(
                    ft.Container(
                        padding=14,
                        bgcolor="#FFFFFF",
                        border_radius=12,
                        content=ft.Row(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.CIRCLE, size=8, color="#EF4444"),
                                        ft.Text(item["name"], size=15),
                                    ]
                                ),
                                ft.Text(f"{item['qty']} 包", weight="bold", color="#EF4444", size=15),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    )
                )

        alert_section = ft.Container(
            padding=20,
            bgcolor="#FEF2F2" if alert_count > 0 else "#F0FDF4",
            border_radius=22,
            border=ft.border.all(1, "#FECACA" if alert_count > 0 else "#BBF7D0"),
            content=ft.Column(alert_controls, spacing=12),
        )

        error_banner = None
        dashboard_error = str(state.get("dashboard_error") or "").strip()
        if dashboard_error:
            error_banner = ft.Container(
                padding=14,
                bgcolor="#FEF2F2",
                border=ft.border.all(1, "#FECACA"),
                border_radius=14,
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.ERROR_OUTLINE, color="#DC2626", size=20),
                        ft.Text(dashboard_error, color="#DC2626", size=13, expand=True),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )

        controls = []

        controls.append(sync_status_banner())

        if error_banner:
            controls.append(error_banner)
            controls.append(ft.Container(height=10))

        controls.extend(
            [
                handover_summary_card(handover_summary),
                ft.Container(height=10),
                maintenance_summary_card(maintenance_summary),
                ft.Container(height=10),
                alert_section,
                ft.Container(height=10),
                usage_section(
                    icon=ft.Icons.QUERY_STATS,
                    title="本月新料用量",
                    bg_color="#E5F0FF",
                    border_color="#B0D0FF",
                    theme_color="#2F80ED",
                    current_month=current_ym,
                    cards=cards_new,
                ),
                ft.Container(height=10),
                usage_section(
                    icon=ft.Icons.COLOR_LENS_OUTLINED,
                    title="本月母粒用量",
                    bg_color="#F0E5FF",
                    border_color="#D3B0FF",
                    theme_color="#9C27B0",
                    current_month=current_ym,
                    cards=cards_mb,
                ),
                ft.Container(height=10),
                usage_section(
                    icon=ft.Icons.RECYCLING,
                    title="本月回用料用量",
                    bg_color="#F0FDF4",
                    border_color="#BBF7D0",
                    theme_color="#10B981",
                    current_month=current_ym,
                    cards=cards_recyc,
                ),
                ft.Container(height=20),
                custom_ui_bar_chart(
                    title="即時庫存",
                    data_list=new_stock_data,
                    max_val=max_new_stock,
                    legend_items=[
                        ("未結晶", "#3B82F6"),
                        ("N/A", "#10B981"),
                        ("已結晶", "#F59E0B"),
                        ("警示", "#EF4444"),
                    ],
                    update_time=current_time_str,
                    unit="包",
                ),
                ft.Container(height=15),
                custom_ui_bar_chart(
                    title="即時回用料庫存",
                    data_list=recycled_stock_data,
                    max_val=max_recycled_stock,
                    legend_items=[
                        ("PET", "#2563EB"),
                        ("PA6", "#38BDF8"),
                        ("PET-308A", "#EF4444"),
                        ("RPET", "#F472B6"),
                    ],
                    update_time=current_time_str,
                    unit="KG",
                ),
                ft.Container(height=80),
            ]
        )

        return ft.Column(controls, spacing=0)

    main_host = ft.Container(content=build_dashboard_controls())

    def rebuild():
        main_host.content = build_dashboard_controls()
        safe_page_update()

    def start_dashboard_load():
        def worker():
            try:
                dashboard_result = load_dashboard_page_data()
                loaded_dashboard_data = dashboard_result.data or default_dashboard_data()
                dashboard_error = "" if dashboard_result.ok else dashboard_result.message

                loaded_handover_summary = load_handover_task_summary()

                if not is_active_view():
                    return

                state["dashboard_data"] = loaded_dashboard_data
                state["handover_summary"] = loaded_handover_summary
                state["dashboard_error"] = dashboard_error
                state["loading"] = False
                state["loaded"] = bool(dashboard_result.ok)

                if dashboard_error:
                    set_sync_status("首頁資料同步失敗", "red", True)
                else:
                    set_sync_status("首頁資料已同步", "green", True)

                rebuild()

                if not dashboard_error:
                    schedule_sync_hide(3)

            except Exception as ex:
                if not is_active_view():
                    return
                state["dashboard_error"] = f"首頁資料載入失敗：{ex}"
                state["loading"] = False
                state["loaded"] = False
                set_sync_status("首頁資料同步失敗", "red", True)
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    start_dashboard_load()

    return main_host
