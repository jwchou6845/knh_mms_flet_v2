# views/handover_tasks.py
# Flet 0.84 / Python
# 交接待辦追蹤頁：Supabase + 非阻塞載入 + 手機 Web 穩定版
import flet as ft
import threading

from services.handover_service import (
    complete_handover_task,
    load_completed_handover_tasks,
    load_open_handover_tasks,
)


print("===== 正在載入 handover_tasks.py：nonblocking-stable =====")


def HandoverTasksContent(page: ft.Page):
    print("===== HandoverTasksContent nonblocking-stable 已執行 =====")

    # =====================================================
    # 0. 使用者狀態
    # =====================================================
    if hasattr(page, "session_data") and isinstance(page.session_data, dict):
        current_user = page.session_data.get("user_name", "未登入")
        can_view_all_tasks = bool(page.session_data.get("can_view_all_tasks", False))
    else:
        page.session_data = {}
        current_user = "未登入"
        can_view_all_tasks = False

    view_token = object()
    page.session_data["_handover_tasks_view_token"] = view_token

    def is_view_active() -> bool:
        if page.session_data.get("_handover_tasks_view_token") is not view_token:
            return False

        route = str(getattr(page, "route", "") or "")
        # main.py 的實際 route 可能是 /handover_tasks、/handover-tasks 或掛在 /handover 底下。
        # 這裡不只靠 route；token 才是主要保護，route 只是額外防線。
        if route and "handover" not in route:
            return False

        return True

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
    BLUE_BTN_DARK = "#456FA3"

    GREEN = "#10B981"
    GREEN_DARK = "#059669"
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

    DISABLED = "#94A3B8"

    # =====================================================
    # 2. 頁面狀態
    # =====================================================
    state = {
        "loading": True,
        "completing": False,
        "open_tasks": [],
        "completed_tasks": [],
        "open_error": "",
        "completed_error": "",
        "active_tab": "未完成待辦",       # 未完成待辦 / 已完成紀錄
        "active_filter": "全部",          # 全部 / 異常 / 待辦 / 高
        "selected_id": None,
        "selected_type": "",
    }

    main_host = ft.Container(expand=True)

    # =====================================================
    # 3. 工具函式
    # =====================================================
    def get_str(value, default=""):
        if isinstance(value, list):
            return str(value[0]) if value else default
        if value is None:
            return default
        return str(value)

    def safe_page_update():
        try:
            page.update()
        except Exception as ex:
            print("handover_tasks page.update error:", repr(ex))

    def show_msg(msg, color=BLUE):
        if not is_view_active():
            return

        snack = ft.SnackBar(
            content=ft.Text(str(msg), color="white", weight=ft.FontWeight.W_600),
            bgcolor=color,
            duration=3000,
        )
        page.overlay.append(snack)
        snack.open = True
        safe_page_update()

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
            return pill("低", GREEN_SOFT, GREEN_DARK, GREEN_BORDER, width=46)
        return pill("中", ORANGE_SOFT, ORANGE, ORANGE_BORDER, width=46)

    def stable_action_button(
        label,
        icon_name,
        bgcolor,
        fgcolor,
        on_click,
        width=None,
        height=42,
        border_color=None,
        expand=False,
        disabled=False,
    ):
        """
        Flet Web / 手機版穩定按鈕。
        避免 ElevatedButton / OutlinedButton 在部分手機瀏覽器中出現可點擊但不渲染。
        """
        real_bg = DISABLED if disabled else bgcolor
        real_fg = "#FFFFFF" if disabled and bgcolor != "#FFFFFF" else fgcolor
        real_border = border_color if border_color else real_bg

        btn = ft.Container(
            width=width,
            height=height,
            expand=expand,
            border_radius=12,
            bgcolor=real_bg,
            border=ft.border.all(1, real_border),
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.symmetric(horizontal=12),
            ink=not disabled,
            content=ft.Row(
                controls=[
                    ft.Icon(icon_name, size=17, color=real_fg),
                    ft.Text(
                        label,
                        size=13,
                        color=real_fg,
                        weight=ft.FontWeight.BOLD,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
        )

        def click(e):
            if disabled:
                return
            if callable(on_click):
                on_click(e)

        btn.on_click = click
        return btn

    def loading_button(label="處理中..."):
        return ft.Container(
            height=42,
            border_radius=12,
            bgcolor=DISABLED,
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.symmetric(horizontal=12),
            content=ft.Row(
                controls=[
                    ft.ProgressRing(width=16, height=16, stroke_width=2, color="white"),
                    ft.Text(label, size=13, color="white", weight=ft.FontWeight.BOLD),
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
        )

    # =====================================================
    # 4. 資料讀取 / 套用
    # =====================================================
    def _apply_loaded_results(open_result, completed_result):
        state["open_tasks"] = (open_result.data or {}).get("tasks", []) if open_result.ok else []
        state["completed_tasks"] = (completed_result.data or {}).get("tasks", []) if completed_result.ok else []
        state["open_error"] = "" if open_result.ok else open_result.message
        state["completed_error"] = "" if completed_result.ok else completed_result.message
        state["loading"] = False

    def load_data_background():
        def worker():
            print("handover_tasks: background load start")

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
            except Exception as ex:
                print("handover_tasks load error:", repr(ex))

                class _Result:
                    ok = False
                    data = {"tasks": []}
                    message = f"資料載入失敗：{ex}"

                open_result = _Result()
                completed_result = _Result()

            if not is_view_active():
                print("handover_tasks: view inactive, skip apply")
                return

            _apply_loaded_results(open_result, completed_result)
            rebuild()

        threading.Thread(target=worker, daemon=True).start()

    # =====================================================
    # 5. 資料篩選
    # =====================================================
    def current_error():
        return state["open_error"] if state["active_tab"] == "未完成待辦" else state["completed_error"]

    def current_base_tasks():
        return state["open_tasks"] if state["active_tab"] == "未完成待辦" else state["completed_tasks"]

    def current_tasks():
        base_tasks = current_base_tasks()
        f = state["active_filter"]

        if f == "全部":
            return list(base_tasks)
        if f in ["異常", "待辦"]:
            return [t for t in base_tasks if get_str(t.get("type")) == f]
        if f == "高":
            return [t for t in base_tasks if get_str(t.get("severity")) == "高"]

        return list(base_tasks)

    def tab_count(label: str) -> int:
        if label == "未完成待辦":
            return len(state["open_tasks"])
        return len(state["completed_tasks"])

    def filtered_count() -> int:
        return len(current_tasks())

    # =====================================================
    # 6. 完成 Dialog
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

    dialog_title = ft.Text("標記完成", weight=ft.FontWeight.BOLD, color=TEXT_MAIN)

    def close_dialog(e=None):
        complete_dialog.open = False
        safe_page_update()

    def confirm_complete(e=None):
        if state["completing"]:
            return

        record_id = state["selected_id"]
        note = get_str(note_field.value, "").strip()

        if not record_id:
            show_msg("找不到要完成的待辦項目。", RED)
            return

        state["completing"] = True
        complete_dialog.actions = [loading_button("正在完成...")]
        safe_page_update()

        def worker():
            try:
                result = complete_handover_task(
                    item_id=record_id,
                    completed_by_name=current_user,
                    complete_note=note,
                )
            except Exception as ex:
                class _Result:
                    ok = False
                    data = None
                    message = f"標記完成失敗：{ex}"
                result = _Result()

            if not is_view_active():
                return

            state["completing"] = False

            if not result.ok:
                complete_dialog.actions = build_dialog_actions()
                safe_page_update()
                show_msg(result.message, RED)
                return

            # 完成後重新讀取兩個清單，確保已完成紀錄也同步更新。
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
                _apply_loaded_results(open_result, completed_result)
            except Exception:
                state["open_tasks"] = [
                    t for t in state["open_tasks"]
                    if t.get("record_id") != record_id
                ]

            complete_dialog.open = False
            complete_dialog.actions = build_dialog_actions()
            rebuild()
            show_msg(result.message, GREEN_DARK)

        threading.Thread(target=worker, daemon=True).start()

    def build_dialog_actions():
        return [
            stable_action_button(
                "取消",
                ft.Icons.CLOSE,
                "#FFFFFF",
                BLUE_BTN,
                close_dialog,
                width=96,
                height=40,
                border_color=BLUE_BORDER,
            ),
            stable_action_button(
                "確認完成",
                ft.Icons.CHECK_CIRCLE_OUTLINE,
                BLUE_BTN,
                "white",
                confirm_complete,
                width=128,
                height=40,
            ),
        ]

    complete_dialog = ft.AlertDialog(
        modal=True,
        title=dialog_title,
        content=ft.Container(
            width=420,
            content=ft.Column(
                controls=[
                    ft.Text("完成後會把此項目更新為已完成，並記錄處理備註。", size=13, color=TEXT_SUB),
                    ft.Text("處理備註", size=13, color=TEXT_MAIN, weight=ft.FontWeight.W_600),
                    note_field,
                ],
                spacing=10,
                tight=True,
            ),
        ),
        actions=build_dialog_actions(),
        actions_alignment=ft.MainAxisAlignment.END,
    )

    if complete_dialog not in page.overlay:
        page.overlay.append(complete_dialog)

    def open_complete(task):
        state["selected_id"] = task.get("record_id")
        state["selected_type"] = task.get("type") or "待辦"
        note_field.value = ""
        dialog_title.value = f"標記完成：{state['selected_type']}"
        complete_dialog.actions = build_dialog_actions()
        complete_dialog.open = True
        safe_page_update()

    # =====================================================
    # 7. UI 區塊
    # =====================================================
    def build_header():
        any_error = bool(state["open_error"] or state["completed_error"])

        if state["loading"]:
            status_bg = BLUE_SOFT
            status_border = BLUE_BORDER
            status_color = BLUE
            status_icon = ft.Icons.SYNC
            status_value = "資料讀取中"
        elif any_error:
            status_bg = RED_SOFT
            status_border = RED_BORDER
            status_color = RED
            status_icon = ft.Icons.ERROR_OUTLINE
            status_value = "資料載入異常"
        else:
            status_bg = GREEN_SOFT
            status_border = GREEN_BORDER
            status_color = GREEN_DARK
            status_icon = ft.Icons.CHECK_CIRCLE_OUTLINE
            status_value = f"未完成 {len(state['open_tasks'])} 筆｜已完成 {len(state['completed_tasks'])} 筆"

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
                            content=ft.Icon(ft.Icons.TASK_ALT_OUTLINED, size=30, color=BLUE),
                        ),
                        ft.Column(
                            controls=[
                                ft.Text("交接待辦追蹤", size=26, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                                ft.Text(
                                    "查看未完成異常 / 待辦，並保留已完成處理紀錄。",
                                    size=14,
                                    color=TEXT_SUB,
                                    max_lines=3,
                                    overflow=ft.TextOverflow.VISIBLE,
                                ),
                            ],
                            spacing=4,
                            expand=True,
                        ),
                    ],
                    spacing=14,
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
                            ft.Icon(status_icon, size=17, color=status_color),
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
        # 手機 Web 修正：避免 Row(wrap=True) + Text(expand=True) 在部分瀏覽器中
        # 被渲染成大面積灰色區塊。改成 Column 結構，文字自然換行。
        return card_box(
            padding=14,
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.INFO_OUTLINE, color=TEXT_SUB, size=21),
                            ft.Text(
                                "使用說明",
                                size=14,
                                color=TEXT_MAIN,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        "未完成項目可標記完成；已完成紀錄會保留完成人、完成時間與處理備註。",
                        color=TEXT_SUB,
                        size=13,
                        max_lines=3,
                        overflow=ft.TextOverflow.VISIBLE,
                    ),
                    ft.Text(
                        f"目前使用者：{current_user}",
                        color=TEXT_MUTED,
                        size=12,
                    ),
                ],
            ),
        )

    def chip_button(label, is_active, on_click, width=None):
        return ft.Container(
            width=width,
            height=38,
            padding=ft.padding.symmetric(horizontal=14),
            border_radius=19,
            bgcolor=BLUE_SOFT if is_active else "#FFFFFF",
            border=ft.border.all(1, BLUE_BORDER if is_active else BORDER),
            alignment=ft.Alignment(0, 0),
            ink=True,
            on_click=on_click,
            content=ft.Text(
                label,
                size=14,
                color=BLUE if is_active else TEXT_SUB,
                weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.W_500,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        )

    def set_tab(label):
        state["active_tab"] = label
        rebuild()

    def set_filter(label):
        state["active_filter"] = label
        rebuild()

    def build_filter_card():
        tab_label = state["active_tab"]
        filter_label = state["active_filter"]
        count_label = "讀取中" if state["loading"] else f"符合 {filtered_count()} 筆"

        return card_box(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.FILTER_ALT_OUTLINED, size=20, color=TEXT_SUB),
                            ft.Column(
                                spacing=2,
                                expand=True,
                                controls=[
                                    ft.Text("查看與篩選", size=15, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                                    ft.Text(
                                        f"目前條件：{tab_label}｜篩選 {filter_label}｜{count_label}",
                                        size=12,
                                        color=TEXT_SUB,
                                    ),
                                ],
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        controls=[
                            chip_button(f"未完成待辦 {tab_count('未完成待辦')}", tab_label == "未完成待辦", lambda e: set_tab("未完成待辦")),
                            chip_button(f"已完成紀錄 {tab_count('已完成紀錄')}", tab_label == "已完成紀錄", lambda e: set_tab("已完成紀錄")),
                        ],
                        spacing=10,
                        wrap=True,
                    ),
                    ft.Divider(height=10, color="#EEF2F7"),
                    ft.Row(
                        controls=[
                            chip_button("全部", filter_label == "全部", lambda e: set_filter("全部"), width=78),
                            chip_button("異常", filter_label == "異常", lambda e: set_filter("異常"), width=78),
                            chip_button("待辦", filter_label == "待辦", lambda e: set_filter("待辦"), width=78),
                            chip_button("高", filter_label == "高", lambda e: set_filter("高"), width=64),
                        ],
                        spacing=10,
                        wrap=True,
                    ),
                ],
                spacing=12,
            )
        )

    def completed_info_box(task):
        return ft.Container(
            width=float("inf"),
            bgcolor="#F8FAFC",
            border=ft.border.all(1, "#E5EAF2"),
            border_radius=12,
            padding=ft.padding.symmetric(horizontal=14, vertical=12),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=17, color=GREEN_DARK),
                            ft.Text(
                                f"完成人：{task.get('completed_by_name', '-')}",
                                size=13,
                                color=TEXT_MAIN,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                f"完成時間：{task.get('completed_at', '-')}",
                                size=13,
                                color=TEXT_SUB,
                            ),
                        ],
                        spacing=10,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        f"處理備註：{task.get('complete_note') or '無處理備註'}",
                        size=13,
                        color=TEXT_SUB,
                    ),
                ],
                spacing=7,
            ),
        )

    def task_card(task):
        severity = task.get("severity") or "中"
        completed_mode = state["active_tab"] == "已完成紀錄"

        left_color = RED if severity == "高" else ORANGE if severity == "中" else GREEN_DARK
        soft_bg = RED_SOFT if severity == "高" else ORANGE_SOFT if severity == "中" else GREEN_SOFT
        border_color = RED_BORDER if severity == "高" else ORANGE_BORDER if severity == "中" else GREEN_BORDER
        source_value = task.get("source") if task.get("source") else "來源資訊未設定"

        body_controls = [
            ft.Row(
                controls=[
                    type_pill(task.get("type") or "待辦"),
                    severity_pill(severity),
                    ft.Text(source_value, size=12, color=TEXT_MUTED),
                ],
                spacing=8,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
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
            body_controls.append(completed_info_box(task))
        else:
            body_controls.append(
                ft.Container(
                    width=float("inf"),
                    content=ft.Row(
                        controls=[
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
                                wrap=True,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            stable_action_button(
                                label="標記完成",
                                icon_name=ft.Icons.CHECK_CIRCLE_OUTLINE,
                                bgcolor=BLUE_BTN,
                                fgcolor="white",
                                on_click=lambda e, t=task: open_complete(t),
                                width=128,
                                height=40,
                            ),
                        ],
                        spacing=12,
                        wrap=True,
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )

        return ft.Container(
            width=float("inf"),
            bgcolor=GREEN_DARK if completed_mode else left_color,
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

    def empty_state():
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
                    ft.Icon(icon, size=42, color=GREEN_DARK),
                    ft.Text(title, size=20, color=TEXT_MAIN, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                    ft.Text(desc, size=14, color=TEXT_SUB, text_align=ft.TextAlign.CENTER),
                ],
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def loading_state():
        return card_box(
            padding=28,
            content=ft.Column(
                controls=[
                    ft.ProgressRing(width=32, height=32, stroke_width=3, color=BLUE),
                    ft.Text("正在讀取交接待辦資料...", size=15, color=TEXT_SUB),
                ],
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def error_state(err):
        return ft.Container(
            bgcolor=RED_SOFT,
            border=ft.border.all(1, RED_BORDER),
            border_radius=16,
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Text("資料載入失敗", size=18, weight=ft.FontWeight.BOLD, color=RED),
                    ft.Text(err, size=13, color=TEXT_MAIN),
                    stable_action_button(
                        "重新讀取",
                        ft.Icons.REFRESH,
                        RED,
                        "white",
                        lambda e: reload_data(),
                        width=128,
                        height=40,
                    ),
                ],
                spacing=10,
            ),
        )

    def build_task_list():
        if state["loading"]:
            body = loading_state()
        else:
            err = current_error()
            if err:
                body = error_state(err)
            else:
                shown = current_tasks()
                if not shown:
                    body = empty_state()
                else:
                    body = ft.Column(
                        spacing=12,
                        controls=[task_card(task) for task in shown],
                    )

        return card_box(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.LIST_ALT_OUTLINED, size=20, color=TEXT_SUB),
                            ft.Text("未完成待辦 / 已完成紀錄", size=15, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    body,
                ],
                spacing=14,
            )
        )

    def build_layout():
        return ft.Container(
            bgcolor=BG,
            padding=ft.padding.only(left=16, right=16, top=18, bottom=90),
            content=ft.Column(
                controls=[
                    build_header(),
                    build_info_card(),
                    build_filter_card(),
                    build_task_list(),
                    ft.Container(height=20),
                ],
                spacing=18,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    def rebuild():
        if not is_view_active():
            return
        main_host.content = build_layout()
        safe_page_update()

    def reload_data():
        state["loading"] = True
        state["open_error"] = ""
        state["completed_error"] = ""
        rebuild()
        load_data_background()

    # =====================================================
    # 8. 初始化
    # =====================================================
    main_host.content = build_layout()
    load_data_background()

    return main_host
