# main.py
# KNH MMS v4.5 穩定版（Flet 0.84）

import json
from datetime import datetime, timezone

import flet as ft
from views.login import LoginView
from views.dashboard import DashboardContent
from views.inventory import InventoryContent
from views.spinneret import SpinneretContent
from views.handover import HandoverContent
from views.handover_tasks import HandoverTasksContent
from views.feed import FeedContent
from views.maintenance import MaintenanceContent
from services.auth_service import update_user_shortcuts
from views.reports import ReportsContent


LOGIN_SESSION_KEY = "knh_login_session"


def main(page: ft.Page):

    # =====================================================
    # 基本設定
    # =====================================================
    page.title = "KNH 紡黏原料管理系統"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#F8FAFC"
    page.padding = 0
    page.spacing = 0
    page.adaptive = True
    page.window_width = 1600
    page.window_height = 900

    if not hasattr(page, "session_data"):
        page.session_data = {}

    def get_client_value(key, default=None):
        try:
            value = page.client_storage.get(key)
            return value if value is not None else default
        except Exception as ex:
            print(f"client_storage get error: {key}", ex)
            return default

    def set_client_value(key, value):
        try:
            page.client_storage.set(key, value)
        except Exception as ex:
            print(f"client_storage set error: {key}", ex)

    def remove_client_value(key):
        try:
            page.client_storage.remove(key)
        except Exception as ex:
            print(f"client_storage remove error: {key}", ex)

    def _parse_expires_at(value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    def restore_login_session():
        if page.session_data.get("is_logged_in"):
            return True

        raw = get_client_value(LOGIN_SESSION_KEY)
        if not raw:
            return False

        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as ex:
            print("PERSISTENT LOGIN RESTORE JSON ERROR:", ex)
            remove_client_value(LOGIN_SESSION_KEY)
            return False

        if not isinstance(data, dict):
            remove_client_value(LOGIN_SESSION_KEY)
            return False

        expires_at = _parse_expires_at(data.get("expires_at"))
        now_utc = datetime.now(timezone.utc)

        if not expires_at or expires_at <= now_utc:
            print("PERSISTENT LOGIN EXPIRED")
            remove_client_value(LOGIN_SESSION_KEY)
            return False

        page.session_data["is_logged_in"] = True
        page.session_data["user_id"] = data.get("user_id", "")
        page.session_data["user_record_id"] = data.get("user_id", "")
        page.session_data["employee_id"] = data.get("employee_id", "")
        page.session_data["user_name"] = data.get("user_name") or data.get("employee_id") or "使用者"
        page.session_data["role"] = data.get("role", "操作員")
        page.session_data["shift"] = data.get("shift", "") or ""
        page.session_data["can_view_all_tasks"] = bool(data.get("can_view_all_tasks", False))
        page.session_data["can_access_reports"] = bool(data.get("can_access_reports", False))
        page.session_data["can_access_spinneret"] = bool(data.get("can_access_spinneret", False))
        page.session_data["can_access_maintenance"] = bool(data.get("can_access_maintenance", False))
        page.session_data["quick_shortcuts"] = data.get("quick_shortcuts") or []

        print("PERSISTENT LOGIN RESTORED", page.session_data.get("employee_id"))
        return True

    page.fonts = {
        "Noto Sans TC":
        "https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap"
    }

    page.theme = ft.Theme(
        font_family="Noto Sans TC",
        color_scheme_seed="#1E293B",
    )

    # VM / 手機 Web 穩定路由：
    # page.go() 在部分手機瀏覽器可能已更新 route 但未即時重建 view，
    # 因此 navigate() 會在 page.go() 後主動呼叫 route_change(None)。
    routing_state = {"manual": False}

    def navigate(route_path):
        print(f"NAVIGATE TO: {route_path}")
        try:
            page.go(route_path)
        except Exception as ex:
            print("page.go error:", ex)

        try:
            if page.route != route_path:
                page.route = route_path
        except Exception as ex:
            print("set page.route error:", ex)

        try:
            if not routing_state["manual"]:
                routing_state["manual"] = True
                route_change(None)
        except NameError:
            pass
        except Exception as ex:
            print("manual route_change error:", ex)
        finally:
            routing_state["manual"] = False

    page.session_data["_navigate"] = navigate

    # =====================================================
    # 共用方法
    # =====================================================
    def is_login():
        return page.session_data.get("is_logged_in", False)

    def user_name():
        return page.session_data.get("user_name", "未登入")

    def logout():
        remove_client_value(LOGIN_SESSION_KEY)
        page.session_data.clear()
        page.session_data["_navigate"] = navigate
        navigate("/login")

    # =====================================================
    # AppBar
    # =====================================================
    def appbar(title):
        def open_drawer(e):
            async def do_open():
                try:
                    current_view = page.views[-1] if page.views else None
                    if current_view:
                        await current_view.show_drawer()
                except Exception as ex:
                    print("show_drawer error:", ex)

            page.run_task(do_open)

        return ft.AppBar(
            leading=ft.IconButton(
                icon=ft.Icons.MENU,
                tooltip="開啟選單",
                on_click=open_drawer,
            ),
            title=ft.Text(title, size=17, weight=ft.FontWeight.BOLD),
            bgcolor="#FFFFFF",
            actions=[
                ft.Container(
                    padding=10,
                    content=ft.Row(
                        controls=[
                            ft.Text(user_name(), size=14),
                            ft.CircleAvatar(
                                radius=15,
                                bgcolor="#DBEAFE",
                                content=ft.Text(
                                    user_name()[:1] if user_name() != "未登入" else "?",
                                    color="#1E3A8A",
                                    size=12,
                                ),
                            ),
                        ]
                    ),
                )
            ]
        )

    # =====================================================
    # Drawer（左側抽屜選單）
    # =====================================================
    def drawer():
        def nav(e):
            routes = [
                "/",
                "/inventory",
                "/feed",
                "/handover",
                "/handover_tasks",
                "/spinneret",
                "/reports",
                "/maintenance",
                "/education",
                "/logout",
            ]
            route = routes[e.control.selected_index]
            logout() if route == "/logout" else navigate(route)

        return ft.NavigationDrawer(
            on_change=nav,
            controls=[
                ft.Container(
                    padding=20,
                    content=ft.Text(
                        "KNH 紡黏原料管理系統",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                    ),
                ),
                ft.Divider(),
                ft.NavigationDrawerDestination(
                    icon=ft.Icons.HOME_OUTLINED,
                    label="首頁",
                ),
                ft.NavigationDrawerDestination(
                    icon=ft.Icons.INVENTORY_2_OUTLINED,
                    label="原料入庫",
                ),
                ft.NavigationDrawerDestination(
                    icon=ft.Icons.BUILD_OUTLINED,
                    label="現場打料",
                ),
                ft.NavigationDrawerDestination(
                    icon=ft.Icons.DESCRIPTION_OUTLINED,
                    label="交接班作業",
                ),
                ft.NavigationDrawerDestination(
                    icon=ft.Icons.TASK_ALT_OUTLINED,
                    label="交接待辦",
                ),
                ft.NavigationDrawerDestination(
                    icon=ft.Icons.MEMORY_OUTLINED,
                    label="噴頭組件狀態",
                ),
                ft.NavigationDrawerDestination(
                    icon=ft.Icons.BAR_CHART_OUTLINED,
                    label="報表中心",
                ),
                ft.NavigationDrawerDestination(
                    icon=ft.Icons.HANDYMAN_OUTLINED,
                    label="保養紀錄",
                ),
                ft.NavigationDrawerDestination(
                    icon=ft.Icons.SCHOOL_OUTLINED,
                    label="教育資源",
                ),
                ft.NavigationDrawerDestination(
                    icon=ft.Icons.LOGOUT,
                    label="登出",
                ),
            ]
        )

    # =====================================================
    # Bottom Navigation
    # =====================================================
    def bottom_nav(idx=0):
        def nav(e):
            routes = ["/", "/feed", "/handover", "/maintenance"]
            navigate(routes[e.control.selected_index])

        return ft.NavigationBar(
            selected_index=idx,
            height=68,
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icons.HOME_OUTLINED,
                    selected_icon=ft.Icons.HOME,
                    label="首頁",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.BUILD_OUTLINED,
                    selected_icon=ft.Icons.BUILD,
                    label="打料",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.DESCRIPTION_OUTLINED,
                    selected_icon=ft.Icons.DESCRIPTION,
                    label="交接",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.HANDYMAN_OUTLINED,
                    selected_icon=ft.Icons.HANDYMAN,
                    label="保養",
                ),
            ],
            on_change=nav,
        )

    # =====================================================
    # View Template（整合捲動雷達與個人化 FAB）
    # =====================================================
    def shell(route, title, body, nav_idx=0):
        content_padding = 0 if route == "/maintenance" else 20

        content_col = ft.Column(
            controls=[
                ft.Container(
                    padding=content_padding,
                    content=body,
                )
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        def scroll_to_top(e):
            async def do_scroll():
                await content_col.scroll_to(offset=0, duration=300)
            page.run_task(do_scroll)

        up_btn = ft.FloatingActionButton(
            content=ft.Icon(ft.Icons.KEYBOARD_ARROW_UP, color="#807B7B"),
            mini=True,
            shape=ft.CircleBorder(),
            bgcolor="#EAEAEA",
            visible=False,
            on_click=scroll_to_top,
        )

        def handle_scroll(e: ft.OnScrollEvent):
            if e.pixels > 200:
                if not up_btn.visible:
                    up_btn.visible = True
                    up_btn.update()
            else:
                if up_btn.visible:
                    up_btn.visible = False
                    up_btn.update()

        content_col.on_scroll = handle_scroll

        # 動態個人化 FAB：角色預設 2 個 + 個人自訂最多 2 個
        current_role = page.session_data.get("role", "操作員")

        role_default_shortcuts = {
            "超級管理員": ["交接待辦", "現場打料"],
            "部門主管": ["交接待辦", "報表中心"],
            "組長/副組長": ["交接待辦", "噴頭組件狀態"],
            "操作員": ["原料入庫", "噴頭組件狀態"],
            "部門外成員": ["報表中心", "教育資源"],
        }

        allowed_custom_shortcuts = {
            "超級管理員": [
                "首頁", "原料入庫", "現場打料", "交接班作業", "交接待辦",
                "噴頭組件狀態", "報表中心", "保養紀錄", "教育資源",
            ],
            "部門主管": [
                "首頁", "原料入庫", "現場打料", "交接班作業", "交接待辦",
                "噴頭組件狀態", "報表中心", "保養紀錄", "教育資源",
            ],
            "組長/副組長": [
                "首頁", "原料入庫", "現場打料", "交接班作業", "交接待辦",
                "噴頭組件狀態", "報表中心", "保養紀錄", "教育資源",
            ],
            "操作員": [
                "首頁", "原料入庫", "現場打料", "交接班作業",
                "噴頭組件狀態", "報表中心", "保養紀錄", "教育資源",
            ],
            "部門外成員": [
                "首頁", "原料入庫", "現場打料", "交接班作業", "報表中心", "教育資源",
            ],
        }

        shortcut_templates = {
            "首頁": {
                "icon": ft.Icons.HOME,
                "tooltip": "首頁",
                "route": "/",
            },
            "原料入庫": {
                "icon": ft.Icons.INVENTORY_2,
                "tooltip": "原料入庫",
                "route": "/inventory",
            },
            "現場打料": {
                "icon": ft.Icons.BUILD,
                "tooltip": "現場打料",
                "route": "/feed",
            },
            "交接班作業": {
                "icon": ft.Icons.DESCRIPTION,
                "tooltip": "交接班作業",
                "route": "/handover",
            },
            "交接待辦": {
                "icon": ft.Icons.TASK_ALT,
                "tooltip": "交接待辦",
                "route": "/handover_tasks",
            },
            "噴頭組件狀態": {
                "icon": ft.Icons.MEMORY,
                "tooltip": "噴頭組件狀態",
                "route": "/spinneret",
            },
            "報表中心": {
                "icon": ft.Icons.BAR_CHART,
                "tooltip": "報表中心",
                "route": "/reports",
            },
            "保養紀錄": {
                "icon": ft.Icons.HANDYMAN,
                "tooltip": "保養紀錄",
                "route": "/maintenance",
            },
            "教育資源": {
                "icon": ft.Icons.SCHOOL,
                "tooltip": "教育資源",
                "route": "/education",
            },
        }

        defaults = role_default_shortcuts.get(current_role, ["現場打料", "交接班作業"])
        allowed_all = allowed_custom_shortcuts.get(current_role, list(shortcut_templates.keys()))

        # 自訂選項不包含角色預設項目，避免使用者以為可以移除預設捷徑
        allowed_custom_only = [
            item for item in allowed_all
            if item not in defaults and item in shortcut_templates
        ]

        def normalize_custom_shortcuts(values):
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, list):
                values = []

            result = []
            for item in values:
                if item in allowed_custom_only and item not in result:
                    result.append(item)
                if len(result) >= 2:
                    break
            return result

        def get_custom_shortcuts():
            return normalize_custom_shortcuts(page.session_data.get("quick_shortcuts", []))

        def build_user_shortcuts():
            result = []

            for item in defaults[:2]:
                if item in shortcut_templates and item not in result:
                    result.append(item)

            for item in get_custom_shortcuts():
                if item in shortcut_templates and item not in result:
                    result.append(item)
                if len(result) >= 4:
                    break

            if not result:
                result = ["現場打料", "交接班作業"]

            return result

        fab_menu_open = False
        action_btns = []
        custom_dialog_ref = {"dialog": None}
        checkbox_controls = {}

        def show_snack(message, color="#2563EB"):
            snack = ft.SnackBar(
                content=ft.Text(str(message), color="white", weight=ft.FontWeight.W_600),
                bgcolor=color,
                duration=3000,
            )
            page.overlay.append(snack)
            snack.open = True
            page.update()

        def close_shortcut_dialog(e=None):
            dialog = custom_dialog_ref.get("dialog")
            if dialog:
                dialog.open = False
                page.update()

        def create_action_button(shortcut_name):
            sc = shortcut_templates[shortcut_name]
            return ft.FloatingActionButton(
                mini=True,
                icon=sc["icon"],
                bgcolor="#FFFFFF",
                foreground_color="#1E293B",
                tooltip=sc["tooltip"],
                visible=fab_menu_open,
                on_click=lambda e, r=sc["route"]: navigate(r),
            )

        def rebuild_fab_layout():
            # 固定順序：
            # 1. 回到頂端按鈕永遠最上方
            # 2. 個人快捷功能在中間
            # 3. 自訂快捷在 FAB 開關上一個
            # 4. FAB 開關永遠最下方
            fab_group.controls = [up_btn] + action_btns + [customize_btn, main_btn]

        def rebuild_fab_actions():
            action_btns.clear()

            for shortcut_name in build_user_shortcuts():
                if shortcut_name not in shortcut_templates:
                    continue

                btn = create_action_button(shortcut_name)
                action_btns.append(btn)

            rebuild_fab_layout()

            try:
                page.update()
            except Exception:
                pass

        def refresh_shortcut_checkboxes():
            selected_count = 0
            for cb in checkbox_controls.values():
                if cb.value:
                    selected_count += 1

            for cb in checkbox_controls.values():
                cb.disabled = (not cb.value and selected_count >= 2)

            try:
                page.update()
            except Exception:
                pass

        def on_shortcut_check(e):
            refresh_shortcut_checkboxes()

        def save_shortcuts(e):
            selected = []
            for name in allowed_custom_only:
                cb = checkbox_controls.get(name)
                if cb and cb.value:
                    selected.append(name)

            if len(selected) > 2:
                show_snack("自訂快捷功能最多只能選 2 個。", "#DC2626")
                return

            user_id = page.session_data.get("user_id", "")

            if not user_id:
                show_snack("無法取得使用者資料，請重新登入後再試。", "#DC2626")
                return

            try:
                result = update_user_shortcuts(user_id=user_id, shortcuts=selected)

                if not result.ok:
                    show_snack(result.message or "快捷功能更新失敗。", "#DC2626")
                    return

                page.session_data["quick_shortcuts"] = selected
                close_shortcut_dialog()

                nonlocal fab_menu_open
                fab_menu_open = True
                customize_btn.visible = True
                main_btn.icon = ft.Icons.CLOSE

                rebuild_fab_actions()
                show_snack(result.message or "快捷功能已更新。", "#059669")

            except Exception as ex:
                show_snack(f"快捷功能更新失敗：{ex}", "#DC2626")
                print("update shortcuts error:", ex)

        def open_shortcut_dialog(e):
            checkbox_controls.clear()

            current_values = set(get_custom_shortcuts())
            option_controls = []

            for name in allowed_custom_only:
                cb = ft.Checkbox(
                    label=name,
                    value=name in current_values,
                    on_change=on_shortcut_check,
                    label_style=ft.TextStyle(size=14, color="#0F172A"),
                )
                checkbox_controls[name] = cb
                option_controls.append(cb)

            if not option_controls:
                option_controls.append(
                    ft.Text("此角色目前沒有可自訂的快捷功能。", size=14, color="#64748B")
                )

            option_list = ft.Column(
                controls=option_controls,
                spacing=2,
                scroll=ft.ScrollMode.AUTO,
                height=310,
            )

            default_text = "、".join(defaults[:2]) if defaults else "未設定"
            allowed_text = f"角色預設：{default_text}\n可另外選 0～2 個自訂捷徑。取消勾選即可刪除或更換。"

            dialog = custom_dialog_ref.get("dialog")
            if dialog and dialog in page.overlay:
                page.overlay.remove(dialog)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("自訂快捷功能", weight=ft.FontWeight.BOLD),
                content=ft.Container(
                    width=360,
                    content=ft.Column(
                        controls=[
                            ft.Text(allowed_text, size=13, color="#64748B"),
                            ft.Container(height=6),
                            option_list,
                        ],
                        spacing=8,
                        tight=True,
                    ),
                ),
                actions=[
                    ft.TextButton("取消", on_click=close_shortcut_dialog),
                    ft.TextButton("儲存", on_click=save_shortcuts),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )

            custom_dialog_ref["dialog"] = dialog
            page.overlay.append(dialog)

            dialog.open = True
            refresh_shortcut_checkboxes()
            page.update()

        for key in build_user_shortcuts():
            if key in shortcut_templates:
                btn = create_action_button(key)
                btn.visible = False
                action_btns.append(btn)

        customize_btn = ft.FloatingActionButton(
            mini=True,
            icon=ft.Icons.ADD,
            bgcolor="#FFFFFF",
            foreground_color="#1E293B",
            tooltip="新增 / 自訂快捷功能",
            visible=False,
            on_click=open_shortcut_dialog,
        )

        main_btn = ft.FloatingActionButton(
            mini=True,
            icon=ft.Icons.GRID_VIEW,
            bgcolor="#FFFFFF",
            foreground_color="#1E293B",
            tooltip="個人快捷功能",
        )

        def toggle_menu(e):
            nonlocal fab_menu_open
            fab_menu_open = not fab_menu_open

            for btn in action_btns:
                btn.visible = fab_menu_open

            customize_btn.visible = fab_menu_open
            main_btn.icon = ft.Icons.CLOSE if fab_menu_open else ft.Icons.GRID_VIEW

            # 每次開關都強制重排，避免新增/更換捷徑後順序跑掉
            rebuild_fab_layout()
            page.update()

        main_btn.on_click = toggle_menu

        fab_group = ft.Column(
            controls=[],
            spacing=10,
            horizontal_alignment=ft.CrossAxisAlignment.END,
            alignment=ft.MainAxisAlignment.END,
            tight=True,
        )
        rebuild_fab_layout()

        return ft.View(
            route=route,
            bgcolor="#F8FAFC",
            appbar=appbar(title),
            drawer=drawer(),
            navigation_bar=bottom_nav(nav_idx),
            floating_action_button=fab_group,
            floating_action_button_location=ft.FloatingActionButtonLocation.END_FLOAT,
            padding=0,
            controls=[content_col],
        )

    # =====================================================
    # Route Change
    # =====================================================
    def route_change(e):
        route = page.route
        print(f"ROUTE_CHANGE: route={route}, is_login={is_login()}, views={len(page.views)}")

        try:
            # 先建立 target_view，不要一開始就清空 page.views
            target_view = None

            if not is_login() and route != "/login":
                restore_login_session()

            if not is_login() and route != "/login":
                target_view = LoginView(page)

            elif route == "/login":
                target_view = LoginView(page)

            elif route == "/":
                target_view = shell(
                    "/",
                    "首頁儀表板",
                    DashboardContent(page),
                    0,
                )

            elif route == "/inventory":
                target_view = shell(
                    "/inventory",
                    "原料入庫作業",
                    InventoryContent(page),
                    0,
                )

            elif route == "/spinneret":
                target_view = shell(
                    "/spinneret",
                    "噴頭組件狀態",
                    SpinneretContent(page),
                    0,
                )

            elif route == "/feed":
                target_view = shell(
                    "/feed",
                    "現場打料作業",
                    FeedContent(page),
                    1,
                )

            elif route == "/handover":
                target_view = shell(
                    "/handover",
                    "交接班紀錄",
                    HandoverContent(page),
                    2,
                )

            elif route == "/handover_tasks":
                target_view = shell(
                    "/handover_tasks",
                    "交接待辦追蹤",
                    HandoverTasksContent(page),
                    2,
                )

            elif route == "/reports":
                target_view = shell(
                    "/reports",
                    "報表中心",
                    ReportsContent(page),
                    0,
                )
                

            elif route == "/maintenance":
                target_view = shell(
                    "/maintenance",
                    "機台保養紀錄",
                    MaintenanceContent(page),
                    3,
                )

            elif route == "/education":
                target_view = shell(
                    "/education",
                    "教育資源",
                    ft.Text("教育資源頁面開發中：可放 SOP、原料知識、設備知識與新人訓練資料。"),
                    0,
                )

            else:
                target_view = shell(
                    route,
                    "系統頁面",
                    ft.Text(f"{route} 開發中"),
                    0,
                )

            page.views.clear()
            page.views.append(target_view)
            page.update()
            print(f"ROUTE_CHANGE DONE: route={route}, views={len(page.views)}")

        except Exception as ex:
            print("route_change error:", ex)

            error_view = ft.View(
                route=route,
                bgcolor="#F8FAFC",
                controls=[
                    ft.Container(
                        expand=True,
                        alignment=ft.Alignment(0, 0),
                        padding=30,
                        content=ft.Container(
                            width=560,
                            bgcolor="#FFFFFF",
                            border=ft.border.all(1, "#FECACA"),
                            border_radius=16,
                            padding=24,
                            content=ft.Column(
                                tight=True,
                                spacing=12,
                                controls=[
                                    ft.Icon(
                                        ft.Icons.ERROR_OUTLINE,
                                        color="#DC2626",
                                        size=42,
                                    ),
                                    ft.Text(
                                        "頁面載入失敗",
                                        size=22,
                                        weight=ft.FontWeight.BOLD,
                                        color="#1E293B",
                                    ),
                                    ft.Text(
                                        str(ex),
                                        size=14,
                                        color="#64748B",
                                        selectable=True,
                                    ),
                                    ft.ElevatedButton(
                                        "回首頁",
                                        icon=ft.Icons.HOME_OUTLINED,
                                        on_click=lambda _: navigate("/"),
                                    ),
                                ],
                            ),
                        ),
                    )
                ],
            )

            page.views.clear()
            page.views.append(error_view)
            page.update()

    # =====================================================
    # 返回鍵
    # =====================================================
    def view_pop(e):
        if len(page.views) > 1:
            page.views.pop()
            navigate(page.views[-1].route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop

    restore_login_session()

    if is_login():
        navigate("/")
    else:
        navigate("/login")


if __name__ == "__main__":
    ft.run(main, assets_dir=".")