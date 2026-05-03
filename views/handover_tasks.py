# views/handover_tasks.py
# Flet 0.84 / Python
# 交接待辦追蹤頁 V9：Supabase + 未完成 / 已完成紀錄
import flet as ft

from services.handover_service import (
    complete_handover_task,
    load_completed_handover_tasks,
    load_open_handover_tasks,
)

print("===== 正在載入 handover_tasks.py：V9 supabase-completed-records =====")


def HandoverTasksContent(page: ft.Page):
    print("===== HandoverTasksContent V9 supabase-completed-records 已執行 =====")

    # =====================================================
    # 0. 使用者狀態
    # =====================================================
    current_user = page.session_data.get("user_name", "未登入") if hasattr(page, "session_data") else "未登入"
    can_view_all_tasks = bool(page.session_data.get("can_view_all_tasks", False)) if hasattr(page, "session_data") else False

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

    PURPLE = "#7C3AED"
    PURPLE_SOFT = "#F3E8FF"
    PURPLE_BORDER = "#D8B4FE"

    # =====================================================
    # 2. 工具函式
    # =====================================================
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
        page.update()

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

    # =====================================================
    # 3. 資料讀取
    # =====================================================
    open_result = load_open_handover_tasks(
        current_user_name=current_user,
        can_view_all_tasks=can_view_all_tasks,
    )

    completed_result = load_completed_handover_tasks(
        current_user_name=current_user,
        can_view_all_tasks=can_view_all_tasks,
        limit=100,
    )

    open_tasks = (open_result.data or {}).get("tasks", []) if open_result.ok else []
    completed_tasks = (completed_result.data or {}).get("tasks", []) if completed_result.ok else []

    open_error = "" if open_result.ok else open_result.message
    completed_error = "" if completed_result.ok else completed_result.message

    active_tab = {"value": "未完成待辦"}  # 未完成待辦 / 已完成紀錄
    active_filter = {"value": "全部"}      # 全部 / 異常 / 待辦 / 高

    # =====================================================
    # 4. 篩選按鈕
    # =====================================================
    tab_buttons = []
    filter_buttons = []

    def refresh_tab_buttons():
        for btn in tab_buttons:
            is_active = btn.data == active_tab["value"]
            btn.bgcolor = BLUE_SOFT if is_active else SOFT
            btn.border = ft.border.all(1, BLUE_BORDER if is_active else BORDER)
            btn.content.color = BLUE if is_active else TEXT_SUB
            btn.content.weight = ft.FontWeight.BOLD if is_active else ft.FontWeight.W_500
            try:
                btn.update()
            except Exception:
                pass

    def refresh_filter_buttons():
        for btn in filter_buttons:
            is_active = btn.data == active_filter["value"]
            btn.bgcolor = BLUE_SOFT if is_active else SOFT
            btn.border = ft.border.all(1, BLUE_BORDER if is_active else BORDER)
            btn.content.color = BLUE if is_active else TEXT_SUB
            btn.content.weight = ft.FontWeight.BOLD if is_active else ft.FontWeight.W_500
            try:
                btn.update()
            except Exception:
                pass

    def tab_button(label):
        def click(e):
            active_tab["value"] = label
            rebuild_task_list()
            refresh_tab_buttons()
            page.update()

        btn = ft.Container(
            data=label,
            height=40,
            padding=ft.padding.symmetric(horizontal=16),
            border_radius=20,
            bgcolor=SOFT,
            border=ft.border.all(1, BORDER),
            alignment=ft.Alignment(0, 0),
            content=ft.Text(label, size=14, color=TEXT_SUB, weight=ft.FontWeight.W_500),
            on_click=click,
        )
        tab_buttons.append(btn)
        return btn

    def filter_button(label):
        def click(e):
            active_filter["value"] = label
            rebuild_task_list()
            refresh_filter_buttons()
            page.update()

        btn = ft.Container(
            data=label,
            width=88,
            height=38,
            border_radius=19,
            bgcolor=SOFT,
            border=ft.border.all(1, BORDER),
            alignment=ft.Alignment(0, 0),
            content=ft.Text(label, size=14, color=TEXT_SUB, weight=ft.FontWeight.W_500),
            on_click=click,
        )
        filter_buttons.append(btn)
        return btn

    tab_row = ft.Row(
        controls=[
            tab_button("未完成待辦"),
            tab_button("已完成紀錄"),
        ],
        spacing=10,
        wrap=True,
    )

    filter_row = ft.Row(
        controls=[
            filter_button("全部"),
            filter_button("異常"),
            filter_button("待辦"),
            filter_button("高"),
        ],
        spacing=10,
        wrap=True,
    )

    # =====================================================
    # 5. 完成 Dialog
    # =====================================================
    selected = {"id": None}

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

    dialog_title = ft.Text("標記完成", weight=ft.FontWeight.BOLD)

    def close_dialog(e=None):
        complete_dialog.open = False
        page.update()

    def confirm_complete(e):
        record_id = selected["id"]
        note = get_str(note_field.value, "").strip()

        result = complete_handover_task(
            item_id=record_id,
            completed_by_name=current_user,
            complete_note=note,
        )

        if not result.ok:
            show_msg(result.message, RED)
            return

        # 直接從未完成清單移除。已完成紀錄頁重新進入頁面時會讀到完整資料。
        open_tasks[:] = [t for t in open_tasks if t["record_id"] != record_id]
        close_dialog()
        rebuild_task_list()
        refresh_tab_buttons()
        refresh_filter_buttons()
        page.update()
        show_msg(result.message, GREEN)

    complete_dialog = ft.AlertDialog(
        modal=True,
        title=dialog_title,
        content=ft.Container(
            width=420,
            content=ft.Column(
                controls=[
                    ft.Text("完成後會把此項目更新為已完成，並記錄處理備註。", size=13, color=TEXT_SUB),
                    note_field,
                ],
                spacing=12,
                tight=True,
            ),
        ),
        actions=[
            ft.TextButton("取消", on_click=close_dialog),
            ft.TextButton("確認完成", on_click=confirm_complete),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    if complete_dialog not in page.overlay:
        page.overlay.append(complete_dialog)

    # =====================================================
    # 6. 任務清單
    # =====================================================
    task_list = ft.Column(spacing=12)

    def current_error():
        return open_error if active_tab["value"] == "未完成待辦" else completed_error

    def current_tasks():
        base_tasks = open_tasks if active_tab["value"] == "未完成待辦" else completed_tasks
        f = active_filter["value"]

        if f == "全部":
            return list(base_tasks)
        if f in ["異常", "待辦"]:
            return [t for t in base_tasks if t["type"] == f]
        if f == "高":
            return [t for t in base_tasks if t["severity"] == "高"]

        return list(base_tasks)

    def open_complete(task):
        selected["id"] = task["record_id"]
        note_field.value = ""
        dialog_title.value = f"標記完成：{task['type']}"
        complete_dialog.open = True
        page.update()

    def task_card(task):
        severity = task["severity"]
        completed_mode = active_tab["value"] == "已完成紀錄"

        left_color = RED if severity == "高" else ORANGE if severity == "中" else GREEN
        soft_bg = RED_SOFT if severity == "高" else ORANGE_SOFT if severity == "中" else GREEN_SOFT
        border_color = RED_BORDER if severity == "高" else ORANGE_BORDER if severity == "中" else GREEN_BORDER

        source_value = task["source"] if task["source"] else "來源資訊未設定"

        body_controls = [
            ft.Row(
                controls=[
                    type_pill(task["type"]),
                    severity_pill(task["severity"]),
                    ft.Text(
                        source_value,
                        size=12,
                        color=TEXT_MUTED,
                    ),
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
                    task["content"],
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
                                f"處理備註：{task.get('complete_note', '無處理備註')}",
                                size=13,
                                color=TEXT_SUB,
                            ),
                        ],
                        spacing=7,
                    ),
                )
            )
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
                            ft.ElevatedButton(
                                content=ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=17, color="white"),
                                        ft.Text("標記完成", size=13, color="white", weight=ft.FontWeight.BOLD),
                                    ],
                                    spacing=6,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    tight=True,
                                ),
                                height=38,
                                bgcolor=BLUE_BTN,
                                color="white",
                                style=ft.ButtonStyle(
                                    shape=ft.RoundedRectangleBorder(radius=12),
                                    elevation=0,
                                ),
                                on_click=lambda e, t=task: open_complete(t),
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

    def empty_state():
        if active_tab["value"] == "已完成紀錄":
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
                ],
                spacing=8,
            ),
        )

    def rebuild_task_list():
        task_list.controls.clear()

        err = current_error()
        if err:
            task_list.controls.append(error_state(err))
        else:
            shown = current_tasks()
            if not shown:
                task_list.controls.append(empty_state())
            else:
                for task in shown:
                    task_list.controls.append(task_card(task))

        try:
            task_list.update()
        except Exception:
            pass

    refresh_tab_buttons()
    refresh_filter_buttons()
    rebuild_task_list()

    # =====================================================
    # 7. 主畫面
    # =====================================================
    any_error = bool(open_error or completed_error)
    total_visible = len(open_tasks) if active_tab["value"] == "未完成待辦" else len(completed_tasks)

    status_bg = RED_SOFT if any_error else GREEN_SOFT
    status_border = RED_BORDER if any_error else GREEN_BORDER
    status_color = RED if any_error else GREEN
    status_icon = ft.Icons.ERROR_OUTLINE if any_error else ft.Icons.CHECK_CIRCLE_OUTLINE
    status_value = "資料同步失敗" if any_error else f"未完成 {len(open_tasks)} 筆｜已完成 {len(completed_tasks)} 筆"

    header = ft.Column(
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
                            ft.Text("交接待辦追蹤", size=28, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                            ft.Text("查看未完成的異常 / 待辦，並保留已完成處理紀錄。", size=14, color=TEXT_SUB),
                        ],
                        spacing=4,
                    ),
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                wrap=True,
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
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
        ],
        spacing=12,
    )

    info_card = card_box(
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.INFO_OUTLINE, color=TEXT_SUB),
                ft.Text("未完成項目可標記完成；已完成紀錄會保留完成人、完成時間與處理備註。", color=TEXT_SUB, size=14),
                ft.Text(f"目前使用者：{current_user}", color=TEXT_MUTED, size=13),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
        )
    )

    filter_card = card_box(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.FILTER_ALT_OUTLINED, size=20, color=TEXT_SUB),
                        ft.Text("查看狀態", size=15, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                tab_row,
                ft.Divider(height=10, color="#EEF2F7"),
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.TUNE_OUTLINED, size=20, color=TEXT_SUB),
                        ft.Text("篩選", size=15, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                filter_row,
            ],
            spacing=12,
        )
    )

    content_card = card_box(
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
                task_list,
            ],
            spacing=14,
        )
    )

    return ft.Container(
        bgcolor=BG,
        content=ft.Column(
            controls=[
                header,
                info_card,
                filter_card,
                content_card,
                ft.Container(height=90),
            ],
            spacing=18,
        ),
    )
