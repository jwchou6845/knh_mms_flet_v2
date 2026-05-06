# views/handover_tasks.py
# Flet 0.84 / Python
# 交接待辦追蹤頁：Supabase + 非阻塞載入 + 手機 Web 穩定版
import threading
import flet as ft

from services.handover_service import (
    complete_handover_task,
    load_completed_handover_tasks,
    load_open_handover_tasks,
)


def HandoverTasksContent(page: ft.Page):
    # =====================================================
    # 0. 使用者狀態
    # =====================================================
    if not hasattr(page, "session_data") or not isinstance(page.session_data, dict):
        page.session_data = {}

    current_user = page.session_data.get("user_name", "未登入")
    can_view_all_tasks = bool(page.session_data.get("can_view_all_tasks", False))

    view_token = object()
    page.session_data["_handover_tasks_view_token"] = view_token

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
    BLUE_BTN = "#4F7FB8"

    GREEN = "#059669"
    GREEN_SOFT = "#ECFDF5"
    GREEN_BORDER = "#A7F3D0"

    ORANGE = "#EA580C"
    ORANGE_SOFT = "#FFF7ED"
    ORANGE_BORDER = "#FDBA74"

    RED = "#DC2626"
    RED_SOFT = "#FEF2F2"
    RED_BORDER = "#FECACA"

    # =====================================================
    # 2. Page State
    # =====================================================
    state = {
        "loading": True,
        "open_tasks": [],
        "completed_tasks": [],
        "open_error": "",
        "completed_error": "",
        "active_tab": "未完成待辦",
        "active_filter": "全部",
        "selected_task": None,
        "completing": False,
    }

    content_host = ft.Container(expand=True)

    # =====================================================
    # 3. 工具函式
    # =====================================================
    def is_active_view() -> bool:
        if page.session_data.get("_handover_tasks_view_token") is not view_token:
            return False

        route = str(getattr(page, "route", "") or "")
        if route and "handover" not in route:
            return False

        return True

    def page_update():
        try:
            if is_active_view():
                page.update()
        except Exception as ex:
            print("handover_tasks page.update error:", repr(ex))

    def get_str(value, default=""):
        if isinstance(value, list):
            return str(value[0]) if value else default
        if value is None:
            return default
        return str(value)

    def show_msg(msg, color=BLUE):
        snack = ft.SnackBar(
            content=ft.Text(str(msg), color="white", weight=ft.FontWeight.W_600),
            bgcolor=color,
            duration=3000,
        )
        page.overlay.append(snack)
        snack.open = True
        page_update()

    def card_box(content, border_color=BORDER, padding=16, bgcolor=CARD):
        return ft.Container(
            bgcolor=bgcolor,
            border=ft.border.all(1, border_color),
            border_radius=18,
            padding=padding,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=8,
                color="#06000000",
                offset=ft.Offset(0, 2),
            ),
            content=content,
        )

    def pill(text, bg, fg, border, width=None):
        return ft.Container(
            width=width,
            height=28,
            padding=ft.padding.symmetric(horizontal=10),
            border_radius=14,
            bgcolor=bg,
            border=ft.border.all(1, border),
            alignment=ft.Alignment(0, 0),
            content=ft.Text(text, size=12, color=fg, weight=ft.FontWeight.W_600),
        )

    def type_pill(task_type):
        if task_type == "異常":
            return pill("異常", RED_SOFT, RED, RED_BORDER, width=64)
        return pill("待辦", BLUE_SOFT, BLUE, BLUE_BORDER, width=64)

    def severity_pill(severity):
        if severity == "高":
            return pill("高", RED_SOFT, RED, RED_BORDER, width=46)
        if severity == "低":
            return pill("低", GREEN_SOFT, GREEN, GREEN_BORDER, width=46)
        return pill("中", ORANGE_SOFT, ORANGE, ORANGE_BORDER, width=46)

    def stable_button(
        label: str,
        icon_name,
        bgcolor: str,
        fgcolor: str,
        on_click,
        height: int = 44,
        border_color: str | None = None,
        expand: bool = True,
    ):
        return ft.Container(
            expand=expand,
            height=height,
            border_radius=12,
            bgcolor=bgcolor,
            border=ft.border.all(1, border_color or bgcolor),
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.symmetric(horizontal=12),
            on_click=on_click,
            ink=True,
            content=ft.Row(
                controls=[
                    ft.Icon(icon_name, size=18, color=fgcolor),
                    ft.Text(
                        label,
                        size=14,
                        color=fgcolor,
                        weight=ft.FontWeight.BOLD,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=7,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
        )

    def stable_outline_button(label: str, icon_name, on_click, color=BLUE_BTN, border_color=BLUE_BORDER):
        return stable_button(
            label=label,
            icon_name=icon_name,
            bgcolor="#FFFFFF",
            fgcolor=color,
            border_color=border_color,
            on_click=on_click,
            height=44,
            expand=True,
        )

    # =====================================================
    # 4. 資料載入
    # =====================================================
    def load_data_worker():
        try:
            open_result = load_open_handover_tasks(
                current_user_name=current_user,
                can_view_all_tasks=can_view_all_tasks,
            )

            completed_result = load_completed_handover_tasks(
                current_user_name=current_user,
                can_view_all_tasks=can_view_all_tasks,
                limit=100,
            )

            if not is_active_view():
                return

            state["open_tasks"] = (open_result.data or {}).get("tasks", []) if open_result.ok else []
            state["completed_tasks"] = (completed_result.data or {}).get("tasks", []) if completed_result.ok else []
            state["open_error"] = "" if open_result.ok else open_result.message
            state["completed_error"] = "" if completed_result.ok else completed_result.message
            state["loading"] = False

            rebuild(update_page=True)

        except Exception as ex:
            if not is_active_view():
                return
            state["loading"] = False
            state["open_error"] = f"讀取交接待辦失敗：{ex}"
            state["completed_error"] = ""
            rebuild(update_page=True)

    def start_load_data(e=None):
        state["loading"] = True
        rebuild(update_page=True)
        threading.Thread(target=load_data_worker, daemon=True).start()

    # =====================================================
    # 5. 篩選資料
    # =====================================================
    def current_error():
        if state["loading"]:
            return ""
        return state["open_error"] if state["active_tab"] == "未完成待辦" else state["completed_error"]

    def current_base_tasks():
        return state["open_tasks"] if state["active_tab"] == "未完成待辦" else state["completed_tasks"]

    def current_tasks():
        base_tasks = current_base_tasks()
        f = state["active_filter"]

        if f == "全部":
            return list(base_tasks)
        if f in ["異常", "待辦"]:
            return [t for t in base_tasks if t.get("type") == f]
        if f == "高":
            return [t for t in base_tasks if t.get("severity") == "高"]

        return list(base_tasks)

    # =====================================================
    # 6. Dialog：標記完成
    # =====================================================
    note_field = ft.TextField(
        hint_text="請填寫處理結果或補充說明，例如：已確認庫存，數量正常。",
        multiline=True,
        min_lines=3,
        max_lines=5,
        border_radius=12,
        border_color=BORDER,
        focused_border_color=BLUE,
        bgcolor=SOFT,
        filled=True,
        text_size=14,
    )

    complete_dialog = ft.AlertDialog(modal=True)

    def close_dialog(e=None):
        complete_dialog.open = False
        state["selected_task"] = None
        state["completing"] = False
        page_update()

    def open_complete(task):
        state["selected_task"] = task
        state["completing"] = False
        note_field.value = ""
        build_complete_dialog()
        if complete_dialog not in page.overlay:
            page.overlay.append(complete_dialog)
        complete_dialog.open = True
        page_update()

    def complete_worker(task, note):
        try:
            result = complete_handover_task(
                item_id=task.get("record_id"),
                completed_by_name=current_user,
                complete_note=note,
            )

            if not is_active_view():
                return

            if not result.ok:
                state["completing"] = False
                build_complete_dialog()
                page_update()
                show_msg(result.message, RED)
                return

            complete_dialog.open = False
            state["selected_task"] = None
            state["completing"] = False
            show_msg(result.message, GREEN)
            start_load_data()

        except Exception as ex:
            if not is_active_view():
                return
            state["completing"] = False
            build_complete_dialog()
            page_update()
            show_msg(f"標記完成失敗：{ex}", RED)

    def confirm_complete(e=None):
        task = state.get("selected_task")
        if not task or state["completing"]:
            return

        note = get_str(note_field.value, "").strip()
        state["completing"] = True
        build_complete_dialog()
        page_update()

        threading.Thread(target=complete_worker, args=(task, note), daemon=True).start()

    def build_complete_dialog():
        task = state.get("selected_task") or {}
        is_loading = state["completing"]

        title_text = f"標記完成：{task.get('type', '待辦')}"

        submit_label = "正在完成..." if is_loading else "確認完成"
        submit_lead = (
            ft.ProgressRing(width=16, height=16, stroke_width=2, color="white")
            if is_loading
            else ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=18, color="white")
        )

        submit_button = ft.Container(
            expand=True,
            height=44,
            border_radius=12,
            bgcolor="#94A3B8" if is_loading else BLUE_BTN,
            alignment=ft.Alignment(0, 0),
            on_click=None if is_loading else confirm_complete,
            content=ft.Row(
                controls=[
                    submit_lead,
                    ft.Text(submit_label, size=14, color="white", weight=ft.FontWeight.BOLD),
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
        )

        cancel_button = stable_outline_button(
            "取消",
            ft.Icons.CLOSE,
            on_click=None if is_loading else close_dialog,
            color=TEXT_SUB,
            border_color=BORDER,
        )

        complete_dialog.title = ft.Text(title_text, weight=ft.FontWeight.BOLD, color=TEXT_MAIN)
        complete_dialog.content = ft.Container(
            width=420,
            content=ft.Column(
                controls=[
                    ft.Text("完成後會把此項目更新為已完成，並記錄處理備註。", size=13, color=TEXT_SUB),
                    ft.Text("處理備註", size=13, color=TEXT_MAIN, weight=ft.FontWeight.W_600),
                    note_field,
                ],
                spacing=12,
                tight=True,
            ),
        )
        complete_dialog.actions = [
            ft.Row(
                spacing=10,
                controls=[
                    cancel_button,
                    submit_button,
                ],
            )
        ]
        complete_dialog.actions_alignment = ft.MainAxisAlignment.END

    # =====================================================
    # 7. UI 區塊
    # =====================================================
    def build_header():
        any_error = bool(state["open_error"] or state["completed_error"])
        open_count = len(state["open_tasks"])
        completed_count = len(state["completed_tasks"])

        if state["loading"]:
            status_bg = BLUE_SOFT
            status_border = BLUE_BORDER
            status_color = BLUE
            status_icon = ft.ProgressRing(width=15, height=15, stroke_width=2, color=BLUE)
            status_value = "資料讀取中"
        elif any_error:
            status_bg = RED_SOFT
            status_border = RED_BORDER
            status_color = RED
            status_icon = ft.Icon(ft.Icons.ERROR_OUTLINE, size=17, color=RED)
            status_value = "待辦資料讀取失敗"
        else:
            status_bg = GREEN_SOFT
            status_border = GREEN_BORDER
            status_color = GREEN
            status_icon = ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=17, color=GREEN)
            status_value = f"未完成 {open_count} 筆｜已完成 {completed_count} 筆"

        return ft.Column(
            spacing=12,
            controls=[
                ft.Row(
                    controls=[
                        ft.Container(
                            width=64,
                            height=64,
                            border_radius=18,
                            bgcolor=BLUE_SOFT,
                            alignment=ft.Alignment(0, 0),
                            content=ft.Icon(ft.Icons.TASK_ALT_OUTLINED, size=34, color=BLUE),
                        ),
                        ft.Column(
                            expand=True,
                            controls=[
                                ft.Text("交接待辦追蹤", size=28, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                                ft.Text(
                                    "查看未完成異常 / 待辦，並保留已完成處理紀錄。",
                                    size=14,
                                    color=TEXT_SUB,
                                    max_lines=3,
                                    overflow=ft.TextOverflow.VISIBLE,
                                ),
                            ],
                            spacing=4,
                        ),
                    ],
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(
                    height=36,
                    padding=ft.padding.symmetric(horizontal=16),
                    border_radius=18,
                    bgcolor=status_bg,
                    border=ft.border.all(1, status_border),
                    content=ft.Row(
                        controls=[
                            status_icon,
                            ft.Text(status_value, size=13, color=status_color, weight=ft.FontWeight.W_600),
                        ],
                        spacing=8,
                        alignment=ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ),
            ],
        )

    def build_info_card():
        return card_box(
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.INFO_OUTLINE, color=TEXT_SUB, size=22),
                            ft.Text("使用說明", size=15, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                        ],
                    ),
                    ft.Text(
                        "未完成項目可標記完成；已完成紀錄會保留完成人、完成時間與處理備註。",
                        size=14,
                        color=TEXT_SUB,
                    ),
                    ft.Text(f"目前使用者：{current_user}", color=TEXT_MUTED, size=13),
                ],
            )
        )

    def build_chip(label, active, on_click, width=None):
        return ft.Container(
            width=width,
            height=38,
            padding=ft.padding.symmetric(horizontal=14),
            border_radius=19,
            bgcolor=BLUE_SOFT if active else SOFT,
            border=ft.border.all(1, BLUE_BORDER if active else BORDER),
            alignment=ft.Alignment(0, 0),
            on_click=on_click,
            ink=True,
            content=ft.Text(
                label,
                size=14,
                color=BLUE if active else TEXT_SUB,
                weight=ft.FontWeight.BOLD if active else ft.FontWeight.W_500,
            ),
        )

    def build_chip_row(options, active_value, setter):
        return ft.Row(
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                build_chip(
                    label=o,
                    active=(o == active_value),
                    on_click=lambda e, value=o: setter(value),
                    width=118 if len(o) >= 5 else 88,
                )
                for o in options
            ],
        )

    def set_tab(value):
        state["active_tab"] = value
        rebuild(update_page=True)

    def set_filter(value):
        state["active_filter"] = value
        rebuild(update_page=True)

    def build_filter_card():
        shown_count = len(current_tasks())
        return card_box(
            content=ft.Column(
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.FILTER_ALT_OUTLINED, size=20, color=TEXT_SUB),
                            ft.Text("查看與篩選", size=15, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                        ],
                    ),
                    ft.Text(
                        f"目前條件：{state['active_tab']}｜{state['active_filter']}｜符合 {shown_count} 筆",
                        size=13,
                        color=TEXT_SUB,
                    ),
                    ft.Text("查看狀態", size=13, color=TEXT_MAIN, weight=ft.FontWeight.W_600),
                    build_chip_row(["未完成待辦", "已完成紀錄"], state["active_tab"], set_tab),
                    ft.Divider(height=12, color="#EEF2F7"),
                    ft.Text("篩選", size=13, color=TEXT_MAIN, weight=ft.FontWeight.W_600),
                    build_chip_row(["全部", "異常", "待辦", "高"], state["active_filter"], set_filter),
                ],
                spacing=10,
            )
        )

    def build_task_card(task):
        severity = task.get("severity", "中")
        completed_mode = state["active_tab"] == "已完成紀錄"

        left_color = RED if severity == "高" else ORANGE if severity == "中" else GREEN
        soft_bg = RED_SOFT if severity == "高" else ORANGE_SOFT if severity == "中" else GREEN_SOFT
        border_color = RED_BORDER if severity == "高" else ORANGE_BORDER if severity == "中" else GREEN_BORDER

        source_value = task.get("source") or "來源資訊未設定"
        task_type = task.get("type") or "待辦"

        body_controls = [
            ft.Row(
                controls=[
                    type_pill(task_type),
                    severity_pill(severity),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Text(source_value, size=12, color=TEXT_MUTED),
            ft.Container(
                width=float("inf"),
                bgcolor=soft_bg,
                border_radius=12,
                padding=ft.padding.symmetric(horizontal=14, vertical=12),
                content=ft.Text(
                    task.get("content") or "-",
                    size=15,
                    color=TEXT_MAIN,
                    weight=ft.FontWeight.W_600,
                ),
            ),
        ]

        if completed_mode:
            body_controls.append(
                ft.Container(
                    width=float("inf"),
                    bgcolor="#F8FAFC",
                    border=ft.border.all(1, "#E5EAF2"),
                    border_radius=12,
                    padding=ft.padding.symmetric(horizontal=14, vertical=12),
                    content=ft.Column(
                        spacing=7,
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=17, color=GREEN),
                                    ft.Text(
                                        f"完成人：{task.get('completed_by_name', '-')}",
                                        size=13,
                                        color=TEXT_MAIN,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Text(f"完成時間：{task.get('completed_at', '-')}", size=13, color=TEXT_SUB),
                            ft.Text(
                                f"處理備註：{task.get('complete_note', '無處理備註')}",
                                size=13,
                                color=TEXT_SUB,
                            ),
                        ],
                    ),
                )
            )
        else:
            body_controls.extend(
                [
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.PERSON_OUTLINE, size=16, color=TEXT_MUTED),
                            ft.Text(
                                "可處理者：填單人 / 接班人 / 管理者",
                                size=12,
                                color=TEXT_MUTED,
                            ),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    stable_button(
                        label="標記完成",
                        icon_name=ft.Icons.CHECK_CIRCLE_OUTLINE,
                        bgcolor=BLUE_BTN,
                        fgcolor="white",
                        on_click=lambda e, t=task: open_complete(t),
                        height=44,
                        expand=False,
                    ),
                ]
            )

        return ft.Container(
            width=float("inf"),
            bgcolor=GREEN if completed_mode else left_color,
            border_radius=18,
            padding=ft.padding.only(left=6),
            content=ft.Container(
                width=float("inf"),
                bgcolor=CARD,
                border=ft.border.all(1, GREEN_BORDER if completed_mode else border_color),
                border_radius=ft.border_radius.only(top_right=18, bottom_right=18),
                padding=16,
                content=ft.Column(
                    controls=body_controls,
                    spacing=12,
                ),
            ),
        )

    def build_empty_state():
        if state["active_tab"] == "已完成紀錄":
            title = "目前沒有已完成交接紀錄"
            desc = "待辦或異常被標記完成後，會保留在這裡供查詢。"
            icon = ft.Icons.INVENTORY_OUTLINED
        else:
            title = "目前沒有未完成交接待辦"
            desc = "異常與待辦完成後，這裡會自動清空。"
            icon = ft.Icons.TASK_ALT_OUTLINED

        return card_box(
            padding=28,
            content=ft.Column(
                controls=[
                    ft.Icon(icon, size=42, color=GREEN),
                    ft.Text(title, size=20, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                    ft.Text(desc, size=14, color=TEXT_SUB),
                ],
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def build_error_state(err):
        return ft.Container(
            bgcolor=RED_SOFT,
            border=ft.border.all(1, RED_BORDER),
            border_radius=16,
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Text("資料載入失敗", size=18, weight=ft.FontWeight.BOLD, color=RED),
                    ft.Text(err, size=13, color=TEXT_MAIN),
                    stable_outline_button("重新讀取", ft.Icons.REFRESH, start_load_data),
                ],
                spacing=10,
            ),
        )

    def build_loading_state():
        return card_box(
            padding=28,
            content=ft.Column(
                controls=[
                    ft.ProgressRing(width=32, height=32, stroke_width=3, color=BLUE),
                    ft.Text("正在讀取交接待辦資料...", size=14, color=TEXT_SUB),
                ],
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def build_task_list_card():
        err = current_error()

        if state["loading"]:
            body = build_loading_state()
        elif err:
            body = build_error_state(err)
        else:
            shown = current_tasks()
            if not shown:
                body = build_empty_state()
            else:
                body = ft.Column(
                    controls=[build_task_card(task) for task in shown],
                    spacing=12,
                )

        return card_box(
            content=ft.Column(
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.LIST_ALT_OUTLINED, size=20, color=TEXT_SUB),
                            ft.Text("未完成待辦 / 已完成紀錄", size=15, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                        ],
                    ),
                    body,
                ],
                spacing=14,
            )
        )

    # =====================================================
    # 8. Rebuild
    # =====================================================
    def rebuild(update_page=False):
        content_host.content = ft.Container(
            bgcolor=BG,
            padding=ft.padding.only(left=18, right=18, top=18, bottom=110),
            content=ft.Column(
                controls=[
                    build_header(),
                    build_info_card(),
                    build_filter_card(),
                    build_task_list_card(),
                    ft.Container(height=90),
                ],
                spacing=18,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

        if update_page:
            page_update()

    # =====================================================
    # 9. 初始化
    # =====================================================
    root = ft.Container(
        expand=True,
        bgcolor=BG,
        content=content_host,
    )

    rebuild(update_page=False)
    threading.Thread(target=load_data_worker, daemon=True).start()

    return root
