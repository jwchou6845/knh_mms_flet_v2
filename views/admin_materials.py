# =====================================================
# KNH MMS v2
# File: views/admin_materials.py
# File Revision: 2026-05-13-admin-materials-button-compat-r2
# Status: phase 1 placeholder compatibility fix
# Last Updated: 2026-05-12 Asia/Taipei
#
# Purpose:
# - /admin/materials 原料與庫存設定頁第一階段入口。
# - 此版先放明確 placeholder，下一輪再實作清單、新增、編輯、啟用 / 停用。
#
# Major Changes in This Revision:
# - 建立可導向的 /admin/materials 頁，避免控制中心點擊後落入通用開發中頁。
# - 顯示已確認的 materials schema 欄位與下一階段功能範圍。
# - r2 修正 Flet 0.84 Button 不支援 text= 關鍵字參數造成頁面載入失敗。
#
# Notes:
# - Flet 0.84；不使用 page.push_route()。
# - 這不是假資料；此頁只顯示下一階段實作說明，不寫入 Supabase。
# =====================================================

from __future__ import annotations

import flet as ft


BG = "#F6F8FB"
CARD_BG = "#FFFFFF"
TEXT = "#1E293B"
TEXT_MUTED = "#64748B"
BORDER = "#E2E8F0"
BLUE_BTN = "#4F7FB8"
BLUE_SOFT = "#E5F0FF"
BLUE_BORDER = "#B0D0FF"
GREEN = "#059669"
GREEN_SOFT = "#ECFDF5"
GREEN_BORDER = "#A7F3D0"
RED = "#DC2626"
RED_BORDER = "#FCA5A5"


def AdminMaterialsContent(page: ft.Page) -> ft.Control:
    if not hasattr(page, "session_data"):
        page.session_data = {}

    def session_get(key: str, default=None):
        try:
            return page.session_data.get(key, default)
        except Exception:
            return default

    def is_super_admin() -> bool:
        return session_get("role") == "超級管理員"

    def navigate(route: str):
        nav = session_get("_navigate")
        if callable(nav):
            nav(route)
        else:
            page.go(route)

    def card(content: ft.Control, padding: int = 18, border_color: str = BORDER, bgcolor: str = CARD_BG) -> ft.Container:
        return ft.Container(
            width=float("inf"),
            bgcolor=bgcolor,
            border=ft.border.all(1, border_color),
            border_radius=18,
            padding=padding,
            content=content,
        )

    def breadcrumb() -> ft.Control:
        def crumb(label: str, route: str | None, active: bool = False):
            return ft.Container(
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                border_radius=8,
                bgcolor=BLUE_SOFT if active else "transparent",
                ink=bool(route),
                on_click=(lambda _: navigate(route)) if route else None,
                content=ft.Text(label, size=12, color=BLUE_BTN if route or active else TEXT_MUTED, weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_500),
            )
        return ft.Row(wrap=True, spacing=2, run_spacing=4, controls=[crumb("控制中心", "/admin"), ft.Text(">", size=12, color=TEXT_MUTED), crumb("原料與庫存設定", None, active=True)])

    if not is_super_admin():
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
                        ft.ElevatedButton("返回首頁", icon=ft.Icons.HOME_OUTLINED, bgcolor=BLUE_BTN, color="#FFFFFF", on_click=lambda _: navigate("/")),
                    ],
                ),
            ),
        )

    fields = [
        "id", "material_name", "main_category", "material_type", "supplier",
        "bag_weight_kg", "low_stock_threshold_bags", "is_stock_managed",
        "is_active", "note", "created_at", "updated_at",
    ]

    field_chips = [
        ft.Container(
            border_radius=14,
            bgcolor=BLUE_SOFT,
            border=ft.border.all(1, BLUE_BORDER),
            padding=ft.padding.symmetric(horizontal=11, vertical=6),
            content=ft.Text(name, size=12, color=BLUE_BTN, weight=ft.FontWeight.W_600),
        )
        for name in fields
    ]

    return ft.Container(
        expand=True,
        bgcolor=BG,
        padding=ft.padding.only(left=24, right=24, top=22, bottom=18),
        content=ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=18,
            controls=[
                breadcrumb(),
                ft.Row(
                    spacing=14,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Container(width=58, height=58, border_radius=16, bgcolor=BLUE_SOFT, alignment=ft.Alignment(0, 0), content=ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, size=31, color=BLUE_BTN)),
                        ft.Column(expand=True, spacing=5, controls=[
                            ft.Text("原料與庫存設定", size=26, weight=ft.FontWeight.BOLD, color=TEXT, max_lines=2),
                            ft.Text("下一輪將實作原料清單、新增、編輯、啟用 / 停用與庫存納管設定。", size=14, color=TEXT_MUTED, max_lines=3),
                        ]),
                    ],
                ),
                card(
                    padding=18,
                    border_color=GREEN_BORDER,
                    bgcolor=GREEN_SOFT,
                    content=ft.Row(
                        spacing=10,
                        controls=[
                            ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=22, color=GREEN),
                            ft.Text("materials 欄位已確認，下一輪可正式進入 /admin/materials 實作。", size=14, color=GREEN, weight=ft.FontWeight.W_600, expand=True),
                        ],
                    ),
                ),
                card(
                    padding=18,
                    content=ft.Column(
                        spacing=12,
                        controls=[
                            ft.Text("已確認欄位", size=18, weight=ft.FontWeight.BOLD, color=TEXT),
                            ft.Row(wrap=True, spacing=8, run_spacing=8, controls=field_chips),
                        ],
                    ),
                ),
                card(
                    padding=18,
                    content=ft.Column(
                        spacing=12,
                        controls=[
                            ft.Text("下一輪功能", size=18, weight=ft.FontWeight.BOLD, color=TEXT),
                            ft.Text("1. 原料清單與搜尋 / 篩選\n2. 新增原料 Dialog\n3. 編輯原料 Dialog\n4. 啟用 / 停用原料\n5. 是否納管庫存與低水位門檻設定", size=14, color=TEXT_MUTED),
                            ft.ElevatedButton("返回控制中心", icon=ft.Icons.ARROW_BACK, bgcolor=BLUE_BTN, color="#FFFFFF", on_click=lambda _: navigate("/admin")),
                        ],
                    ),
                ),
                ft.Container(height=90),
            ],
        ),
    )
