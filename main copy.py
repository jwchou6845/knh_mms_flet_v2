# main.py
import flet as ft
from views.login import LoginView # 登入
from views.dashboard import DashboardContent # 首頁
from views.inventory import InventoryContent # 原料入庫
# 🌟 現場打料模組暫時隔離中

def main(page: ft.Page):

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

    page.fonts = {
        "Noto Sans TC": "https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap"
    }
    page.theme = ft.Theme(font_family="Noto Sans TC", color_scheme_seed="#1E293B")

    # 🌟 穩定的導航
    def navigate(route_path):
        page.go(route_path)

    def is_login(): return page.session_data.get("is_logged_in", False)
    def user_name(): return page.session_data.get("user_name", "未登入")
    def logout():
        page.session_data.clear()
        navigate("/login")

    def appbar(title):
        return ft.AppBar(
            title=ft.Text(title, size=17, weight=ft.FontWeight.BOLD),
            bgcolor="#FFFFFF",
            actions=[
                ft.Container(
                    padding=10,
                    content=ft.Row([
                        ft.Text(user_name(), size=14),
                        ft.CircleAvatar(radius=15, bgcolor="#DBEAFE", content=ft.Text(user_name()[:1] if user_name() != "未登入" else "?", color="#1E3A8A", size=12)),
                    ]),
                )
            ]
        )

    def drawer():
        def nav(e):
            routes = ["/", "/inventory", "/feed", "/handover", "/reports", "/maintenance", "/logout"]
            route = routes[e.control.selected_index]
            logout() if route == "/logout" else navigate(route)

        return ft.NavigationDrawer(
            on_change=nav,
            controls=[
                ft.Container(padding=20, content=ft.Text("KNH 紡黏原料管理系統", size=18, weight=ft.FontWeight.BOLD)),
                ft.Divider(),
                ft.NavigationDrawerDestination(icon=ft.Icons.HOME_OUTLINED, label="首頁"),
                ft.NavigationDrawerDestination(icon=ft.Icons.INVENTORY_2_OUTLINED, label="原料入庫"),
                ft.NavigationDrawerDestination(icon=ft.Icons.BUILD_OUTLINED, label="現場打料"),
                ft.NavigationDrawerDestination(icon=ft.Icons.DESCRIPTION_OUTLINED, label="交接班"),
                ft.NavigationDrawerDestination(icon=ft.Icons.BAR_CHART_OUTLINED, label="報表中心"),
                ft.NavigationDrawerDestination(icon=ft.Icons.HANDYMAN_OUTLINED, label="保養紀錄"),
                ft.NavigationDrawerDestination(icon=ft.Icons.LOGOUT, label="登出"),
            ]
        )

    def bottom_nav(idx=0):
        def nav(e):
            routes = ["/", "/feed", "/handover"]
            navigate(routes[e.control.selected_index])
        return ft.NavigationBar(
            selected_index=idx, height=68,
            destinations=[
                ft.NavigationBarDestination(icon=ft.Icons.HOME_OUTLINED, selected_icon=ft.Icons.HOME, label="首頁"),
                ft.NavigationBarDestination(icon=ft.Icons.BUILD_OUTLINED, selected_icon=ft.Icons.BUILD, label="打料"),
                ft.NavigationBarDestination(icon=ft.Icons.DESCRIPTION_OUTLINED, selected_icon=ft.Icons.DESCRIPTION, label="交接"),
            ],
            on_change=nav,
        )

    def shell(route, title, body, nav_idx=0):
        # 1. 獨立的捲動視窗
        content_col = ft.Column(
            controls=[ft.Container(padding=20, content=body)],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        # 2. 向上捲動按鈕
        def scroll_to_top(e):
            async def do_scroll():
                await content_col.scroll_to(offset=0, duration=300)
            page.run_task(do_scroll)

        up_btn = ft.FloatingActionButton(
            content=ft.Icon(ft.Icons.KEYBOARD_ARROW_UP, color="#807B7B"), 
            mini=True, shape=ft.CircleBorder(), bgcolor="#EAEAEA",
            visible=False, on_click=scroll_to_top  
        )

        def handle_scroll(e: ft.OnScrollEvent):
            if e.pixels > 200:
                if not up_btn.visible:
                    up_btn.visible = True; up_btn.update()
            else:
                if up_btn.visible:
                    up_btn.visible = False; up_btn.update()

        content_col.on_scroll = handle_scroll

        # 🌟 3. 完美還原：個人化快捷鍵 (四個小方格，白色背景，統一大小)
        current_user = user_name()
        
        if current_user == "周正偉" or current_user == "admin":
            user_shortcuts = ["reports", "maintenance"]
        else:
            user_shortcuts = ["feed", "handover"]

        shortcut_templates = {
            "reports": {"icon": ft.Icons.BAR_CHART, "tooltip": "報表中心", "route": "/reports"},
            "maintenance": {"icon": ft.Icons.HANDYMAN, "tooltip": "保養紀錄", "route": "/maintenance"},
            "feed": {"icon": ft.Icons.BUILD, "tooltip": "現場打料", "route": "/feed"},
            "handover": {"icon": ft.Icons.DESCRIPTION, "tooltip": "交接班", "route": "/handover"},
        }

        fab_menu_open = False
        fab_controls = [up_btn]
        action_btns = []

        for key in user_shortcuts:
            if key in shortcut_templates:
                sc = shortcut_templates[key]
                btn = ft.FloatingActionButton(
                    mini=True, # 統一小尺寸
                    icon=sc["icon"],
                    bgcolor="#FFFFFF", # 白色背景
                    foreground_color="#1E293B",
                    tooltip=sc["tooltip"],
                    visible=False,
                    on_click=lambda e, r=sc["route"]: navigate(r)
                )
                action_btns.append(btn)

        fab_controls.extend(action_btns)

        # 展開/收起的四宮格按鈕
        main_btn = ft.FloatingActionButton(
            mini=True, # 統一小尺寸
            icon=ft.Icons.GRID_VIEW, # 四個小方格
            bgcolor="#FFFFFF", # 白色背景
            foreground_color="#1E293B",
            tooltip="個人快捷功能",
        )

        def toggle_menu(e):
            nonlocal fab_menu_open
            fab_menu_open = not fab_menu_open
            for btn in action_btns:
                btn.visible = fab_menu_open
                btn.update()
            main_btn.icon = ft.Icons.CLOSE if fab_menu_open else ft.Icons.GRID_VIEW
            main_btn.update()

        main_btn.on_click = toggle_menu
        fab_controls.append(main_btn)

        fab_group = ft.Column(
            controls=fab_controls,
            spacing=10,
            horizontal_alignment=ft.CrossAxisAlignment.END,
            alignment=ft.MainAxisAlignment.END,
            tight=True,
        )

        return ft.View(
            route=route, bgcolor="#F8FAFC",
            appbar=appbar(title), drawer=drawer(), navigation_bar=bottom_nav(nav_idx),
            floating_action_button=fab_group, # 掛載捷徑模組
            floating_action_button_location=ft.FloatingActionButtonLocation.END_FLOAT,
            padding=0, controls=[content_col]
        )

    def route_change(e):
        page.views.clear()
        route = page.route

        if not is_login() and route != "/login":
            navigate("/login")
            return

        if route == "/login":
            page.views.append(LoginView(page))

        elif route == "/":
            page.views.append(shell("/", "首頁儀表板", DashboardContent(page), 0))

        elif route == "/inventory":
            page.views.append(shell("/inventory", "原料入庫作業", InventoryContent(page), 0))
            
        elif route == "/feed":
            # 隔離 feed.py
            safe_text = ft.Container(
                content=ft.Text("⚠️ 現場打料模組暫時隔離中，請先確認系統穩定！", size=20, color="red", weight="bold"),
                padding=50, alignment=ft.Alignment(0,0)
            )
            page.views.append(shell("/feed", "現場打料作業", safe_text, 1))
        elif route == "/handover":
            page.views.append(shell("/handover", "交接班紀錄", ft.Text("交接班留言板"), 2))
        elif route == "/reports":
            page.views.append(shell("/reports", "報表中心", ft.Text("報表資料頁面\n" * 50)))
        elif route == "/maintenance":
            page.views.append(shell("/maintenance", "保養紀錄", ft.Text("設備保養頁面")))
        else:
            page.views.append(shell(route, "系統頁面", ft.Text(f"{route} 開發中")))
        page.update()

    def view_pop(e):
        if len(page.views) > 1:
            page.views.pop()
            navigate(page.views[-1].route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop

    if is_login(): navigate("/")
    else: navigate("/login")

if __name__ == "__main__":
    ft.run(main)