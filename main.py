# =====================================================
# KNH MMS v2
# File: main.py
# File Revision: 2026-05-15-stocktake-recycled-subpage-r1
# Status: add recycled stocktake subpage route
# Last Updated: 2026-05-15 Asia/Taipei
#
# Purpose:
# - 系統主路由、12 小時免重登恢復流程、共用 shell 與導覽
#
# Major Changes in This Revision:
# - 12 小時免重登 restore 改為背景 thread 執行，避免 Supabase 查詢阻塞主流程
# - 加入 restore watchdog timeout 與 late result guard，避免畫面永久停在登入檢查狀態
# - 保留 maintenance items / deleted 子頁路由與既有 page.go() route fallback 修正
# - 新增 /admin 系統控制中心第一階段路由與超級管理員 Drawer 入口
# - 新增 /inventory/stocktake 人工盤點功能路由
# - 新增 /inventory/stocktake/recycled 回用料逐筆盤點子頁路由
#
# Notes:
# - 本檔以 2026-05-11 auth restore guard 穩定版為基礎
# - Flet 0.84；本專案固定使用 page.go()，不可改回 page.push_route()
# - 所有時間相關業務邏輯仍由各 service 使用 Asia/Taipei 處理
# =====================================================

import flet as ft
import time
import json
import threading
from views.login import LoginView
from views.dashboard import DashboardContent
from views.inventory import InventoryContent
from views.inventory_stocktake import InventoryStocktakeContent
from views.inventory_stocktake_recycled import InventoryStocktakeRecycledContent
from views.spinneret import SpinneretContent
from views.handover import HandoverContent
from views.handover_tasks import HandoverTasksContent
from views.feed import FeedContent
from views.maintenance import MaintenanceContent
from views.maintenance_items import MaintenanceItemsContent
from views.maintenance_items_deleted import MaintenanceItemsDeletedContent
from services.auth_service import update_user_shortcuts
from services.auth_session_service import (
    cleanup_expired_user_sessions,
    restore_persistent_session,
    revoke_persistent_session,
)
from views.reports import ReportsContent
from views.admin import AdminContent
from views.admin_materials import AdminMaterialsContent
from views.admin_maintenance import AdminMaintenanceContent


SESSION_TOKEN_KEY = "knh_session_token"
AUTH_RESTORE_TIMEOUT_SECONDS = 10


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

    # =====================================================
    # 12 小時免重登：瀏覽器端只保存 session token
    # =====================================================
    persistent_auth_state = {
        "checking": False,
        "checked": False,
        "target_route": "/",
        "check_seq": 0,
        "timed_out_seq": 0,
    }

    def _normalize_storage_value(value):
        if value is None:
            return ""

        text = str(value).strip()
        if text in ["", "null", "None", "undefined"]:
            return ""

        if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
            try:
                return json.loads(text)
            except Exception:
                return text.strip('"')

        return text

    def browser_storage_get(key: str, callback):
        """
        Flet 0.84 Web 持久登入讀取工具。
        優先使用 shared_preferences；若環境沒有，再退回 eval_js / run_javascript。
        回傳值透過 callback(value) 取得。
        """
        if hasattr(page, "shared_preferences") and hasattr(page, "run_task"):
            async def do_get():
                try:
                    value = await page.shared_preferences.get(key)
                except Exception as ex:
                    print("shared_preferences.get failed:", repr(ex))
                    value = None
                callback(_normalize_storage_value(value))

            try:
                page.run_task(do_get)
                return True
            except Exception as ex:
                print("page.run_task shared_preferences.get failed:", repr(ex))

        script = f"window.localStorage.getItem({json.dumps(key)})"

        if hasattr(page, "eval_js"):
            try:
                page.eval_js(
                    script,
                    result_handler=lambda e: callback(
                        _normalize_storage_value(getattr(e, "data", None))
                    ),
                )
                return True
            except TypeError:
                try:
                    value = page.eval_js(script)
                    callback(_normalize_storage_value(value))
                    return True
                except Exception as ex:
                    print("page.eval_js get failed:", repr(ex))
            except Exception as ex:
                print("page.eval_js get failed:", repr(ex))

        if hasattr(page, "run_javascript"):
            try:
                value = page.run_javascript(script)
                callback(_normalize_storage_value(value))
                return True
            except Exception as ex:
                print("page.run_javascript get failed:", repr(ex))

        callback("")
        return False

    def browser_storage_set(key: str, value: str):
        if hasattr(page, "shared_preferences") and hasattr(page, "run_task"):
            async def do_set():
                try:
                    await page.shared_preferences.set(key, value)
                except Exception as ex:
                    print("shared_preferences.set failed:", repr(ex))

            try:
                page.run_task(do_set)
                return True
            except Exception as ex:
                print("page.run_task shared_preferences.set failed:", repr(ex))

        script = f"window.localStorage.setItem({json.dumps(key)}, {json.dumps(value)});"

        if hasattr(page, "eval_js"):
            try:
                page.eval_js(script)
                return True
            except Exception as ex:
                print("page.eval_js set failed:", repr(ex))

        if hasattr(page, "run_javascript"):
            try:
                page.run_javascript(script)
                return True
            except Exception as ex:
                print("page.run_javascript set failed:", repr(ex))

        return False

    def browser_storage_remove(key: str):
        if hasattr(page, "shared_preferences") and hasattr(page, "run_task"):
            async def do_remove():
                try:
                    await page.shared_preferences.remove(key)
                except Exception as ex:
                    print("shared_preferences.remove failed:", repr(ex))

            try:
                page.run_task(do_remove)
                return True
            except Exception as ex:
                print("page.run_task shared_preferences.remove failed:", repr(ex))

        script = f"window.localStorage.removeItem({json.dumps(key)});"

        if hasattr(page, "eval_js"):
            try:
                page.eval_js(script)
                return True
            except Exception as ex:
                print("page.eval_js remove failed:", repr(ex))

        if hasattr(page, "run_javascript"):
            try:
                page.run_javascript(script)
                return True
            except Exception as ex:
                print("page.run_javascript remove failed:", repr(ex))

        return False


    page.fonts = {
        "Noto Sans TC":
        "https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap"
    }

    page.theme = ft.Theme(
        font_family="Noto Sans TC",
        color_scheme_seed="#1E293B",
    )

    # VM / 手機 Web 穩定路由：
    # 目前 VM 的 Flet page.go() 在部分情境不會穩定觸發 on_route_change，
    # 所以仍需要手動 route_change(None) 作為保險。
    # 但 route_change 內會做防重複處理，避免同一頁被連續建立兩次。
    routing_state = {"building": False, "last_route": None, "last_time": 0.0}

    def navigate(route_path):
        print(f"NAVIGATE TO: {route_path}")
        try:
            page.go(route_path)
        except Exception as ex:
            print("page.go error:", ex)

        # Flet Web / VM 環境下 page.go() 可能是非同步更新 route。
        # 若立刻手動補 route_change(None)，route_change 可能仍讀到舊的 page.route。
        # 因此在 fallback route_change 前，先強制把 page.route 設成目標路由。
        try:
            if page.route != route_path:
                page.route = route_path
        except Exception as ex:
            print("set page.route error:", ex)

        # 手機 Web / VM 登入後有時 page.go() 不會立即重建 view。
        # 這裡手動補一次；重複觸發會在 route_change 開頭被擋掉。
        try:
            route_change(None)
        except Exception as ex:
            print("manual route_change fallback error:", ex)

    page.session_data["_navigate"] = navigate

    # =====================================================
    # 共用方法
    # =====================================================
    def is_login():
        return page.session_data.get("is_logged_in", False)

    def user_name():
        return page.session_data.get("user_name", "未登入")

    def save_session_data(user: dict, session_token: str = ""):
        user_id = str(user.get("id", "")).strip()
        employee_id = str(user.get("employee_id", "")).strip()
        name = str(user.get("name", "")).strip()

        page.session_data["is_logged_in"] = True
        page.session_data["user_id"] = user_id
        page.session_data["user_record_id"] = user_id
        page.session_data["employee_id"] = employee_id
        page.session_data["user_name"] = name if name else employee_id
        page.session_data["role"] = user.get("role", "操作員")
        page.session_data["shift"] = user.get("shift", "") or ""
        page.session_data["can_view_all_tasks"] = bool(user.get("can_view_all_tasks", False))
        page.session_data["can_access_reports"] = bool(user.get("can_access_reports", False))
        page.session_data["can_access_spinneret"] = bool(user.get("can_access_spinneret", False))
        page.session_data["can_access_maintenance"] = bool(user.get("can_access_maintenance", False))
        page.session_data["quick_shortcuts"] = user.get("quick_shortcuts") or []
        if session_token:
            page.session_data["session_token"] = session_token

    def save_browser_session_token(token: str):
        token = str(token or "").strip()
        if not token:
            return False
        page.session_data["session_token"] = token
        return browser_storage_set(SESSION_TOKEN_KEY, token)

    def clear_browser_session_token():
        try:
            page.session_data.pop("session_token", None)
        except Exception:
            pass
        return browser_storage_remove(SESSION_TOKEN_KEY)

    def register_session_helpers():
        page.session_data["_navigate"] = navigate
        page.session_data["_save_login_session"] = save_session_data
        page.session_data["_save_browser_session_token"] = save_browser_session_token
        page.session_data["_save_persistent_session_token"] = save_browser_session_token
        page.session_data["_save_persistent_token"] = save_browser_session_token
        page.session_data["_set_persistent_token"] = save_browser_session_token
        page.session_data["_clear_browser_session_token"] = clear_browser_session_token
        page.session_data["_clear_persistent_session_token"] = clear_browser_session_token
        page.session_data["_browser_storage_get"] = browser_storage_get
        page.session_data["_browser_storage_set"] = browser_storage_set
        page.session_data["_browser_storage_remove"] = browser_storage_remove

    register_session_helpers()

    def start_user_session_cleanup_once():
        """
        機會式清理 12 小時免重登 user_sessions。
        使用背景 thread 執行，避免阻塞登入檢查與畫面建立。
        """
        if page.session_data.get("_user_session_cleanup_started"):
            return

        page.session_data["_user_session_cleanup_started"] = True

        def worker():
            try:
                result = cleanup_expired_user_sessions()
                if result.ok:
                    data = result.data or {}
                    print(
                        "USER_SESSION CLEANUP DONE:",
                        "expired=", data.get("expired_deleted_count", 0),
                        "revoked=", data.get("revoked_deleted_count", 0),
                        "total=", data.get("total_deleted_count", 0),
                    )
                else:
                    print("USER_SESSION CLEANUP FAILED:", result.message)
            except Exception as ex:
                print("USER_SESSION CLEANUP ERROR:", repr(ex))

        threading.Thread(target=worker, daemon=True).start()

    start_user_session_cleanup_once()

    def build_auth_check_view(message: str = "正在檢查登入狀態..."):
        return ft.View(
            route=page.route or "/",
            padding=0,
            bgcolor="#F8FAFC",
            controls=[
                ft.Container(
                    expand=True,
                    bgcolor="#F8FAFC",
                    alignment=ft.Alignment(0, 0),
                    padding=24,
                    content=ft.Container(
                        width=360,
                        bgcolor="#FFFFFF",
                        border=ft.border.all(1, "#E2E8F0"),
                        border_radius=22,
                        padding=ft.padding.symmetric(horizontal=28, vertical=32),
                        shadow=ft.BoxShadow(
                            spread_radius=0,
                            blur_radius=22,
                            color="#12000000",
                            offset=ft.Offset(0, 8),
                        ),
                        content=ft.Column(
                            tight=True,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=14,
                            controls=[
                                ft.ProgressRing(width=34, height=34, stroke_width=3, color="#4F7FB8"),
                                ft.Text(
                                    "KNH 紡黏原料管理系統",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color="#0F172A",
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                ft.Text(
                                    message,
                                    size=14,
                                    color="#64748B",
                                    text_align=ft.TextAlign.CENTER,
                                ),
                            ],
                        ),
                    ),
                )
            ],
        )

    def show_auth_check_view(message: str = "正在檢查登入狀態..."):
        try:
            page.views.clear()
            page.views.append(build_auth_check_view(message))
            page.update()
        except Exception as ex:
            print("show_auth_check_view error:", repr(ex))

    def _is_current_auth_check(check_seq: int) -> bool:
        return int(persistent_auth_state.get("check_seq") or 0) == int(check_seq)

    def start_persistent_auth_check(target_route: str | None = None, force: bool = False):
        """
        12 小時免重登恢復流程。

        重要修正：
        1. localStorage / shared_preferences 取 token 後，不在 callback 內同步查 Supabase。
        2. restore_persistent_session() 改由背景 thread 執行，避免網路慢時阻塞頁面。
        3. 以 check_seq + timeout watchdog 防止 late callback / late restore 在逾時後反向覆蓋畫面。
        4. 若整個檢查流程超過 AUTH_RESTORE_TIMEOUT_SECONDS，直接回登入頁，避免永久卡住。
        """
        if is_login():
            return False

        if persistent_auth_state.get("checking") and not force:
            return True

        route_target = target_route or page.route or "/"
        if route_target in ["", "/login"]:
            route_target = "/"

        check_seq = int(persistent_auth_state.get("check_seq") or 0) + 1
        persistent_auth_state["check_seq"] = check_seq
        persistent_auth_state["timed_out_seq"] = 0
        persistent_auth_state["target_route"] = route_target
        persistent_auth_state["checking"] = True
        persistent_auth_state["checked"] = False

        print(
            f"PERSISTENT LOGIN CHECK START: seq={check_seq}, target={route_target}",
            flush=True,
        )
        show_auth_check_view("正在檢查登入狀態...")

        def watchdog():
            time.sleep(AUTH_RESTORE_TIMEOUT_SECONDS)

            if not _is_current_auth_check(check_seq):
                return

            if not persistent_auth_state.get("checking"):
                return

            persistent_auth_state["timed_out_seq"] = check_seq
            persistent_auth_state["checking"] = False
            persistent_auth_state["checked"] = True

            print(
                f"PERSISTENT LOGIN TIMEOUT: seq={check_seq}, "
                f"timeout={AUTH_RESTORE_TIMEOUT_SECONDS}s",
                flush=True,
            )

            # 逾時不清除瀏覽器 token。
            # 若只是暫時網路慢，使用者之後重新整理仍可再次嘗試恢復；
            # 但當下必須先讓畫面離開等待狀態，避免停在 Working / 檢查中。
            try:
                navigate("/login")
            except Exception as ex:
                print("PERSISTENT LOGIN TIMEOUT NAVIGATE ERROR:", repr(ex), flush=True)

        threading.Thread(target=watchdog, daemon=True).start()

        def on_token_loaded(token):
            if not _is_current_auth_check(check_seq) or not persistent_auth_state.get("checking"):
                print(f"PERSISTENT LOGIN LATE TOKEN IGNORED: seq={check_seq}", flush=True)
                return

            token = _normalize_storage_value(token)
            print(
                f"PERSISTENT LOGIN TOKEN LOADED: seq={check_seq}, has_token={bool(token)}",
                flush=True,
            )

            if not token:
                persistent_auth_state["checking"] = False
                persistent_auth_state["checked"] = True
                print("PERSISTENT LOGIN: no token", flush=True)
                navigate("/login")
                return

            def restore_worker():
                print(f"PERSISTENT LOGIN RESTORE START: seq={check_seq}", flush=True)

                try:
                    result = restore_persistent_session(token)
                except Exception as ex:
                    result = None
                    print("PERSISTENT LOGIN exception:", repr(ex), flush=True)

                if not _is_current_auth_check(check_seq) or not persistent_auth_state.get("checking"):
                    print(f"PERSISTENT LOGIN LATE RESULT IGNORED: seq={check_seq}", flush=True)
                    return

                persistent_auth_state["checking"] = False
                persistent_auth_state["checked"] = True

                if result and result.ok:
                    data = result.data or {}
                    user = data.get("user") or {}
                    restored_token = str(data.get("session_token") or token).strip()
                    save_session_data(user, restored_token)
                    register_session_helpers()
                    save_browser_session_token(restored_token)
                    print(f"PERSISTENT LOGIN: restored seq={check_seq}", flush=True)
                    navigate(persistent_auth_state.get("target_route") or "/")
                    return

                if result:
                    print("PERSISTENT LOGIN failed:", result.message, flush=True)

                clear_browser_session_token()
                navigate("/login")

            threading.Thread(target=restore_worker, daemon=True).start()

        browser_storage_get(SESSION_TOKEN_KEY, on_token_loaded)
        return True

    def logout():
        token = str(page.session_data.get("session_token") or "").strip()
        if token:
            try:
                revoke_persistent_session(token)
            except Exception as ex:
                print("revoke persistent session failed:", repr(ex))

        clear_browser_session_token()
        page.session_data.clear()
        register_session_helpers()
        persistent_auth_state["checked"] = True
        persistent_auth_state["checking"] = False
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
        def is_super_admin_for_drawer():
            return page.session_data.get("role") == "超級管理員"

        drawer_routes = [
            "/",
            "/inventory",
            "/feed",
            "/handover",
            "/handover_tasks",
            "/spinneret",
            "/reports",
            "/maintenance",
            "/education",
        ]

        drawer_controls = [
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
        ]

        if is_super_admin_for_drawer():
            drawer_routes.append("/admin")
            drawer_controls.extend(
                [
                    ft.Divider(),
                    ft.NavigationDrawerDestination(
                        icon=ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED,
                        label="系統控制中心",
                    ),
                ]
            )

        drawer_routes.append("/logout")
        drawer_controls.append(
            ft.NavigationDrawerDestination(
                icon=ft.Icons.LOGOUT,
                label="登出",
            )
        )

        def nav(e):
            selected_index = int(e.control.selected_index or 0)
            if selected_index < 0 or selected_index >= len(drawer_routes):
                return
            route = drawer_routes[selected_index]
            logout() if route == "/logout" else navigate(route)

        return ft.NavigationDrawer(
            on_change=nav,
            controls=drawer_controls,
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
        content_padding = 0 if str(route or "").startswith(("/maintenance", "/admin")) else 20

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
    route_state = {"building": False, "last_route": None, "last_time": 0.0}

    def cleanup_route_scoped_views(next_route: str) -> None:
        """
        子頁 instance cleanup。
        目前用於 /maintenance/items，避免背景 worker 在使用者切離後仍回寫舊畫面。
        不覆蓋 page.on_route_change；只在主 router 內呼叫已註冊的 dispose callback。
        """
        route_text = str(next_route or "")
        if route_text.startswith("/maintenance/items"):
            return

        cleanup = None
        try:
            cleanup = page.session_data.get("_maintenance_items_dispose")
        except Exception:
            cleanup = None

        if callable(cleanup):
            try:
                cleanup(f"route_change to {route_text}")
            except Exception as ex:
                print("maintenance_items cleanup failed:", repr(ex))

        try:
            page.session_data.pop("_maintenance_items_dispose", None)
            page.session_data.pop("_maintenance_items_instance_id", None)
        except Exception:
            pass

    def route_change(e):
        route = page.route
        now = time.monotonic()

        cleanup_route_scoped_views(route)

        if route_state["building"]:
            print(f"ROUTE_CHANGE SKIP: already building route={route}")
            return

        if (
            route == route_state.get("last_route")
            and now - float(route_state.get("last_time") or 0) < 0.8
        ):
            print(f"ROUTE_CHANGE SKIP: duplicate route={route}")
            return

        print(f"ROUTE_CHANGE: route={route}, is_login={is_login()}, views={len(page.views)}")

        try:
            route_state["building"] = True
            # 先建立 target_view，不要一開始就清空 page.views
            target_view = None

            if persistent_auth_state.get("checking") and not is_login():
                target_view = build_auth_check_view("正在檢查登入狀態...")

            elif not is_login() and route != "/login":
                if not persistent_auth_state.get("checked"):
                    start_persistent_auth_check(target_route=route)
                    target_view = build_auth_check_view("正在檢查登入狀態...")
                else:
                    target_view = LoginView(page)

            elif route == "/login":
                if is_login():
                    target_view = shell(
                        "/",
                        "首頁儀表板",
                        DashboardContent(page),
                        0,
                    )
                else:
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

            elif str(route or "").startswith("/inventory/stocktake/recycled"):
                target_view = shell(
                    route,
                    "回用料逐筆盤點",
                    InventoryStocktakeRecycledContent(page),
                    0,
                )

            elif route == "/inventory/stocktake":
                target_view = shell(
                    "/inventory/stocktake",
                    "人工盤點",
                    InventoryStocktakeContent(page),
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

            elif route == "/maintenance/items":
                target_view = shell(
                    "/maintenance/items",
                    "保養項目管理",
                    MaintenanceItemsContent(page),
                    3,
                )

            elif route == "/maintenance/items/deleted":
                target_view = shell(
                    "/maintenance/items/deleted",
                    "已刪除保養項目",
                    MaintenanceItemsDeletedContent(page),
                    3,
                )

            elif route == "/admin":
                target_view = shell(
                    "/admin",
                    "系統控制中心",
                    AdminContent(page),
                    0,
                )

            elif route == "/admin/materials":
                target_view = shell(
                    "/admin/materials",
                    "原料與庫存設定",
                    AdminMaterialsContent(page),
                    0,
                )

            elif route == "/admin/maintenance":
                target_view = shell(
                    "/admin/maintenance",
                    "保養管理",
                    AdminMaintenanceContent(page),
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
            route_state["last_route"] = route
            route_state["last_time"] = time.monotonic()
            print(f"ROUTE_CHANGE DONE: route={route}, views={len(page.views)}")
            route_state["building"] = False

        except Exception as ex:
            route_state["building"] = False
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
                                        content=ft.Row(
                                            controls=[
                                                ft.Icon(ft.Icons.HOME_OUTLINED, size=18, color="white"),
                                                ft.Text(
                                                    "回首頁",
                                                    size=15,
                                                    color="white",
                                                    weight=ft.FontWeight.W_600,
                                                ),
                                            ],
                                            alignment=ft.MainAxisAlignment.CENTER,
                                            spacing=8,
                                            tight=True,
                                        ),
                                        bgcolor="#2563EB",
                                        color="white",
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

        finally:
            route_state["building"] = False

    # =====================================================
    # 返回鍵
    # =====================================================
    def view_pop(e):
        if len(page.views) > 1:
            page.views.pop()
            navigate(page.views[-1].route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop

    initial_route = page.route or "/"
    if is_login():
        navigate(initial_route if initial_route != "/login" else "/")
    else:
        # 先顯示檢查畫面，再讀取瀏覽器端 token。
        # 避免 Safari 先露出登入頁，等到使用者點欄位才跳回首頁。
        start_persistent_auth_check(target_route=initial_route, force=True)


if __name__ == "__main__":
    ft.run(main, assets_dir=".")