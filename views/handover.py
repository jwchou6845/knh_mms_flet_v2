# views/handover.py
# KNH MMS 交接班表單 - Flet 0.84 + Supabase
import flet as ft
import threading

from services.handover_service import (
    load_handover_form_data,
    submit_handover_record,
    today_dash_date,
    normalize_date as service_normalize_date,
    now_taipei_iso,
)


def HandoverContent(page: ft.Page):
    # =====================================================
    # 0. 狀態
    # =====================================================
    if not hasattr(page, "session_data"):
        page.session_data = {}

    current_user = page.session_data.get("user_name", "未登入") if hasattr(page, "session_data") else "未登入"

    view_token = object()
    page.session_data["_handover_view_token"] = view_token

    def is_active_view() -> bool:
        route = str(getattr(page, "route", "") or "")
        return (
            page.session_data.get("_handover_view_token") is view_token
            and (not route or route == "/handover")
        )

    selected_shift = {"value": "早班"}
    data_loaded = {"done": False}
    submitting = {"value": False}

    users = []
    user_options_ready = {"done": False}

    machine_status = [
        {"name": "S1", "status": "正常"},
        {"name": "S2", "status": "正常"},
        {"name": "空壓", "status": "正常"},
    ]

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
    BLUE_BTN_HOVER = "#456FA3"
    BLUE_BTN_PRESS = "#3D628F"

    GREEN = "#10B981"
    GREEN_SOFT = "#ECFDF5"
    GREEN_BORDER = "#A7F3D0"

    ORANGE = "#F97316"
    ORANGE_SOFT = "#FFF7ED"
    ORANGE_BORDER = "#FDBA74"

    RED = "#DC2626"
    RED_SOFT = "#FEF2F2"
    RED_BORDER = "#FECACA"

    DISABLED = "#94A3B8"

    STATUS_STYLE = {
        "正常": (GREEN_SOFT, GREEN, GREEN_BORDER),
        "注意": (ORANGE_SOFT, ORANGE, ORANGE_BORDER),
        "異常": (RED_SOFT, RED, RED_BORDER),
    }

    # =====================================================
    # 2. 工具函式
    # =====================================================
    def safe_update(control):
        try:
            control.update()
        except Exception:
            pass

    def safe_page_update():
        try:
            page.update()
        except Exception:
            pass

    def show_msg(msg, color=BLUE):
        if not is_active_view():
            return

        snack = ft.SnackBar(
            content=ft.Text(str(msg), color="white", weight=ft.FontWeight.W_600),
            bgcolor=color,
            duration=3500,
        )
        try:
            page.overlay.append(snack)
        except Exception:
            pass
        snack.open = True
        safe_page_update()

    def today_date():
        return today_dash_date()

    def normalize_date(date_text: str):
        return service_normalize_date(date_text)

    def get_current_datetime_iso():
        return now_taipei_iso()

    def clean_text(value):
        return str(value or "").strip()

    # 保留函式，避免日後其他區塊引用；目前送出嚴重度由 service 統一處理。
    def get_machine_severity():
        statuses = [m["status"] for m in machine_status]
        if "異常" in statuses:
            return "高"
        if "注意" in statuses:
            return "中"
        return "低"

    def get_text_severity(text, default="中"):
        value = str(text or "")
        high_keywords = [
            "停機",
            "無法啟動",
            "無法運轉",
            "斷料",
            "漏料",
            "異音",
            "警報",
            "安全",
            "品質",
            "用錯料",
            "混料",
            "溫度失控",
            "壓力異常",
            "空壓異常",
        ]
        for keyword in high_keywords:
            if keyword in value:
                return "高"
        return default

    # =====================================================
    # 3. 共用 UI
    # =====================================================
    def field_label(icon_name, label, required=False):
        # 手機 Web 避免 Row(wrap=True) 造成灰色大區塊，改用固定 Row + Text expand 自然換行。
        return ft.Row(
            controls=[
                ft.Icon(icon_name, size=18, color=TEXT_SUB),
                ft.Text(
                    label + (" *" if required else ""),
                    size=14,
                    color=TEXT_MAIN,
                    weight=ft.FontWeight.W_600,
                    max_lines=2,
                    overflow=ft.TextOverflow.VISIBLE,
                    expand=True,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def make_text_field(value="", hint="", multiline=False):
        return ft.TextField(
            value=value,
            hint_text=hint,
            hint_style=ft.TextStyle(size=14, color=TEXT_SUB),
            multiline=multiline,
            min_lines=2 if multiline else 1,
            max_lines=4 if multiline else 1,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE,
            bgcolor=SOFT,
            filled=True,
            text_size=15,
            height=108 if multiline else 52,
            content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
        )

    def make_card(content, border_color=BORDER, padding=18):
        return ft.Container(
            bgcolor=CARD,
            border=ft.border.all(1, border_color),
            border_radius=18,
            padding=padding,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=12,
                color="#08000000",
                offset=ft.Offset(0, 3),
            ),
            content=content,
        )

    def title_header():
        # 手機 Web 對 Row(wrap=True) + expand 文字欄偶爾會渲染成灰色大區塊。
        # 這裡改成保守的垂直標題結構，保留同一套 icon / 主標 / 副標風格。
        return ft.Container(
            bgcolor=BG,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Container(
                        width=54,
                        height=54,
                        border_radius=16,
                        bgcolor=BLUE_SOFT,
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=30, color=BLUE),
                    ),
                    ft.Text("交接班表單", size=28, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                    ft.Text(
                        "班別、機台狀態、異常與待辦一次完成。",
                        size=14,
                        color=TEXT_SUB,
                        max_lines=3,
                        overflow=ft.TextOverflow.VISIBLE,
                    ),
                    status_badge,
                ],
            ),
        )

    # =====================================================
    # 4. 表單元件
    # =====================================================
    handover_date = make_text_field(value=today_date(), hint="YYYY-MM-DD")

    receiver = ft.Dropdown(
        options=[ft.dropdown.Option("資料載入中")],
        value="資料載入中",
        border_radius=12,
        border_color=BORDER,
        focused_border_color=BLUE,
        bgcolor=SOFT,
        filled=True,
        height=52,
        text_size=15,
        content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
    )

    abnormal_note = make_text_field(
        hint="例：S2 PET 乾燥溫度波動，已通知主管 / 幹部",
        multiline=True,
    )

    todo_note = make_text_field(
        hint="例：夜班需確認 PET-南紡剩餘包數",
        multiline=True,
    )

    status_text = ft.Text("資料同步中", size=13, color=BLUE, weight=ft.FontWeight.W_600)
    status_icon_box = ft.Container(
        content=ft.ProgressRing(width=15, height=15, stroke_width=2, color=BLUE),
    )

    status_badge = ft.Container(
        height=36,
        padding=ft.padding.symmetric(horizontal=16),
        border_radius=18,
        bgcolor=BLUE_SOFT,
        border=ft.border.all(1, BLUE_BORDER),
        visible=True,
        content=ft.Row(
            controls=[status_icon_box, status_text],
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        ),
    )

    def hide_status_later(delay_seconds=3.0):
        current_token = view_token

        def hide():
            if not is_active_view():
                return
            if page.session_data.get("_handover_view_token") is not current_token:
                return
            status_badge.visible = False
            safe_page_update()

        threading.Timer(delay_seconds, hide).start()

    def set_status(text, theme="blue", loading=False, update_now=True, auto_hide=False):
        if theme == "green":
            bg, border, fg, icon = GREEN_SOFT, GREEN_BORDER, GREEN, ft.Icons.CHECK_CIRCLE_OUTLINE
        elif theme == "red":
            bg, border, fg, icon = RED_SOFT, RED_BORDER, RED, ft.Icons.ERROR_OUTLINE
        elif theme == "orange":
            bg, border, fg, icon = ORANGE_SOFT, ORANGE_BORDER, ORANGE, ft.Icons.INFO_OUTLINE
        else:
            bg, border, fg, icon = BLUE_SOFT, BLUE_BORDER, BLUE, ft.Icons.SYNC

        status_badge.visible = True
        status_badge.bgcolor = bg
        status_badge.border = ft.border.all(1, border)
        status_text.value = text
        status_text.color = fg

        if loading:
            status_icon_box.content = ft.ProgressRing(width=15, height=15, stroke_width=2, color=fg)
        else:
            status_icon_box.content = ft.Icon(icon, size=17, color=fg)

        if update_now:
            safe_page_update()

        if auto_hide:
            hide_status_later()

    # =====================================================
    # 5. 班別按鈕
    # =====================================================
    shift_buttons = []

    def refresh_shift_buttons(update_now=True):
        for btn in shift_buttons:
            active = btn.data == selected_shift["value"]
            btn.bgcolor = BLUE_SOFT if active else SOFT
            btn.border = ft.border.all(1, BLUE_BORDER if active else BORDER)
            btn.content.color = BLUE if active else TEXT_SUB
            btn.content.weight = ft.FontWeight.BOLD if active else ft.FontWeight.W_500
            if update_now:
                safe_update(btn)

    def make_shift(label):
        def click(e):
            if submitting["value"]:
                return
            selected_shift["value"] = label
            refresh_shift_buttons(update_now=True)

        btn = ft.Container(
            data=label,
            width=96,
            height=42,
            alignment=ft.Alignment(0, 0),
            border_radius=13,
            bgcolor=SOFT,
            border=ft.border.all(1, BORDER),
            ink=True,
            content=ft.Text(label, size=15),
            on_click=click,
        )
        shift_buttons.append(btn)
        return btn

    shift_row = ft.Row(
        controls=[make_shift("早班"), make_shift("中班"), make_shift("夜班")],
        spacing=14,
        wrap=True,
    )

    # =====================================================
    # 6. 機台狀態 Chip
    # =====================================================
    def make_chip(machine):
        chip = ft.Container()

        def apply_chip_style():
            bg, color, border = STATUS_STYLE[machine["status"]]
            chip.bgcolor = bg
            chip.border = ft.border.all(1, border)
            chip.content.value = f"{machine['name']} {machine['status']}"
            chip.content.color = color

        def click(e):
            if submitting["value"]:
                return
            order = ["正常", "注意", "異常"]
            i = order.index(machine["status"])
            machine["status"] = order[(i + 1) % len(order)]
            apply_chip_style()
            safe_update(chip)

        chip.height = 42
        chip.expand = True
        chip.alignment = ft.Alignment(0, 0)
        chip.border_radius = 12
        chip.ink = True
        chip.content = ft.Text("", size=14, weight=ft.FontWeight.W_600)
        chip.on_click = click

        apply_chip_style()
        return chip

    chip_row = ft.ResponsiveRow(
        columns=12,
        spacing=14,
        run_spacing=14,
        controls=[
            ft.Container(col={"xs": 12, "sm": 4}, content=make_chip(machine_status[0])),
            ft.Container(col={"xs": 12, "sm": 4}, content=make_chip(machine_status[1])),
            ft.Container(col={"xs": 12, "sm": 4}, content=make_chip(machine_status[2])),
        ],
    )

    # =====================================================
    # 7. 送出按鈕：loading / 防重複
    # =====================================================
    submit_state = {"hover": False, "pressed": False}

    submit_icon = ft.Icon(ft.Icons.SEND_ROUNDED, color="white", size=22)
    submit_text = ft.Text("確認送出交接紀錄", color="white", size=17, weight=ft.FontWeight.BOLD)
    submit_loading = ft.ProgressRing(
        width=20,
        height=20,
        stroke_width=2.5,
        color="white",
        visible=False,
    )

    submit_box = ft.Container(
        height=58,
        border_radius=13,
        bgcolor=BLUE_BTN,
        alignment=ft.Alignment(0, 0),
        ink=True,
        content=ft.Row(
            controls=[submit_icon, submit_text, submit_loading],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
            tight=True,
        ),
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=10,
            color="#12000000",
            offset=ft.Offset(0, 4),
        ),
    )

    def refresh_submit_button(update_now=True):
        if submitting["value"]:
            submit_box.bgcolor = DISABLED
            submit_box.opacity = 0.92
            submit_icon.visible = False
            submit_loading.visible = True
            submit_text.value = "送出中..."
        elif not data_loaded["done"]:
            submit_box.bgcolor = DISABLED
            submit_box.opacity = 0.75
            submit_icon.visible = True
            submit_loading.visible = False
            submit_text.value = "資料同步中"
        else:
            submit_box.opacity = 1
            submit_icon.visible = True
            submit_loading.visible = False
            submit_text.value = "確認送出交接紀錄"

            if submit_state["pressed"]:
                submit_box.bgcolor = BLUE_BTN_PRESS
            elif submit_state["hover"]:
                submit_box.bgcolor = BLUE_BTN_HOVER
            else:
                submit_box.bgcolor = BLUE_BTN

        if update_now:
            safe_update(submit_box)

    def submit_hover(e):
        if submitting["value"] or not data_loaded["done"]:
            return
        submit_state["hover"] = e.data == "true"
        refresh_submit_button(update_now=True)

    submit_button = ft.Container(
        content=submit_box,
        on_click=lambda e: submit_feed(e),
        on_hover=submit_hover,
    )

    def set_submitting(value, update_now=True):
        submitting["value"] = value
        submit_state["pressed"] = False
        refresh_submit_button(update_now=False)
        handover_date.disabled = value
        receiver.disabled = value
        abnormal_note.disabled = value
        todo_note.disabled = value
        if update_now:
            safe_page_update()

    # =====================================================
    # 8. 資料載入：接班人從使用者權限表讀取
    # =====================================================
    def load_users_worker():
        if not is_active_view():
            return

        try:
            set_status("資料同步中", loading=True, update_now=True)
            result = load_handover_form_data(current_user_name=current_user)

            if not is_active_view():
                return

            users.clear()

            if result.ok:
                users.extend(result.data.get("users", []))
                dropdown_users = result.data.get("receiver_options", [])
                set_status("資料已同步", theme="green", update_now=False, auto_hide=True)
                user_options_ready["done"] = True
            else:
                dropdown_users = []
                set_status("接班人清單載入失敗", theme="orange", update_now=False)
                user_options_ready["done"] = False
                print("handover load users error:", result.message)

            if not dropdown_users:
                dropdown_users = ["目前無可選接班人"]

            receiver.options = [ft.dropdown.Option(u) for u in dropdown_users]
            receiver.value = None

            data_loaded["done"] = True
            refresh_submit_button(update_now=False)
            safe_page_update()

        except Exception as ex:
            if not is_active_view():
                return

            data_loaded["done"] = True
            user_options_ready["done"] = False

            receiver.options = [ft.dropdown.Option("目前無可選接班人")]
            receiver.value = None

            set_status("接班人清單載入失敗", theme="orange", update_now=False)
            refresh_submit_button(update_now=False)
            safe_page_update()
            print("handover load users error:", ex)

    def start_load_users():
        threading.Thread(target=load_users_worker, daemon=True).start()

    # =====================================================
    # 9. 送出資料：主表 + 子表
    # =====================================================
    def submit_feed(e):
        if submitting["value"]:
            return

        if not data_loaded["done"]:
            show_msg("資料尚未同步完成，請稍候再送出。", RED)
            return

        receiver_value = clean_text(receiver.value)
        abnormal_value = clean_text(abnormal_note.value)
        todo_value = clean_text(todo_note.value)
        normalized_date = normalize_date(str(handover_date.value or ""))

        if not normalized_date:
            show_msg("請輸入正確交接日期。", RED)
            return

        if not receiver_value or receiver_value in ["資料載入中", "目前無可選接班人"]:
            show_msg("請選擇接班人員。", RED)
            return

        current_user_id = None
        if hasattr(page, "session_data") and isinstance(page.session_data, dict):
            current_user_id = page.session_data.get("user_id")

        set_submitting(True)
        set_status("正在送出交接紀錄", loading=True, update_now=True)

        payload = {
            "handover_date": str(handover_date.value or ""),
            "shift": selected_shift["value"],
            "sender_name": current_user,
            "receiver_name": receiver_value,
            "machine_status": [dict(m) for m in machine_status],
            "abnormal_note": abnormal_value,
            "todo_note": todo_value,
            "created_by_user_id": current_user_id,
            "created_by_name": current_user,
        }

        def worker():
            try:
                result = submit_handover_record(**payload)

                if not is_active_view():
                    return

                if not result.ok:
                    set_submitting(False, update_now=False)
                    set_status("送出失敗", theme="red", update_now=False)
                    safe_page_update()
                    show_msg(result.message, RED)
                    return

                abnormal_note.value = ""
                todo_note.value = ""
                receiver.value = None

                # 狀態維持，但日期更新為今天，避免跨日誤送。
                handover_date.value = today_date()

                set_submitting(False, update_now=False)
                set_status("交接紀錄已送出", theme="green", update_now=False, auto_hide=True)
                safe_page_update()
                show_msg(result.message, GREEN)

            except Exception as ex:
                if not is_active_view():
                    return
                set_submitting(False, update_now=False)
                set_status("送出失敗", theme="red", update_now=False)
                safe_page_update()
                show_msg(f"送出失敗：{ex}", RED)
                print("handover submit error:", ex)

        threading.Thread(target=worker, daemon=True).start()

    # =====================================================
    # 10. 版面
    # =====================================================
    sync_card = make_card(
        padding=16,
        content=ft.Column(
            spacing=8,
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.INFO_OUTLINE, color=TEXT_SUB, size=20),
                        ft.Text(
                            "送出後會同步 Supabase，並建立交接項目明細。",
                            color=TEXT_SUB,
                            size=14,
                            max_lines=3,
                            overflow=ft.TextOverflow.VISIBLE,
                            expand=True,
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(f"填單人：{current_user}", color=TEXT_MUTED, size=13),
            ],
        ),
    )

    shift_card = make_card(
        padding=18,
        content=ft.Column(
            controls=[
                field_label(ft.Icons.SCHEDULE_OUTLINED, "班別", required=True),
                shift_row,
            ],
            spacing=12,
        ),
    )

    instruction_card = ft.Container(
        bgcolor="#F8FBFF",
        border=ft.border.all(1, BLUE_BORDER),
        border_radius=16,
        padding=16,
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, size=22, color=BLUE),
                        ft.Text(
                            "填單說明",
                            size=17,
                            weight=ft.FontWeight.BOLD,
                            color=BLUE,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(
                    "機台狀態若為「注意」或「異常」，請在異常事項補充原因。",
                    size=13,
                    color=TEXT_MAIN,
                ),
                ft.Text(
                    "異常事項：填寫本班已發生、正在發生，或已通知處理的問題。",
                    size=13,
                    color=TEXT_MAIN,
                ),
                ft.Text(
                    "待辦事項：填寫接班人需要繼續確認或完成的事項。",
                    size=13,
                    color=TEXT_MAIN,
                ),
                ft.Text(
                    "建議格式：機台 / 原料 / 問題 / 已處理狀況。例：S2 PET 乾燥溫度波動，已通知主管 / 幹部。",
                    size=13,
                    color=TEXT_SUB,
                ),
            ],
            spacing=8,
        ),
    )

    form_card = make_card(
        border_color=BLUE_BORDER,
        padding=24,
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.FACT_CHECK_OUTLINED, size=26, color=BLUE),
                        ft.Column(
                            expand=True,
                            controls=[
                                ft.Text("交接內容", size=22, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                                ft.Text(
                                    "建議以「狀態、異常、待辦」三段式填寫。",
                                    size=13,
                                    color=TEXT_SUB,
                                    max_lines=3,
                                    overflow=ft.TextOverflow.VISIBLE,
                                ),
                            ],
                            spacing=3,
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                instruction_card,
                ft.ResponsiveRow(
                    columns=12,
                    spacing=16,
                    run_spacing=16,
                    controls=[
                        ft.Container(
                            col={"xs": 12, "md": 6},
                            content=ft.Column(
                                controls=[field_label(ft.Icons.CALENDAR_MONTH_OUTLINED, "交接日期", True), handover_date],
                                spacing=7,
                            ),
                        ),
                        ft.Container(
                            col={"xs": 12, "md": 6},
                            content=ft.Column(
                                controls=[field_label(ft.Icons.PERSON_OUTLINE, "接班人員", True), receiver],
                                spacing=7,
                            ),
                        ),
                    ],
                ),
                ft.Column(
                    controls=[
                        field_label(ft.Icons.MEMORY_OUTLINED, "機台狀態（點擊可切換：正常 / 注意 / 異常）", True),
                        chip_row,
                    ],
                    spacing=10,
                ),
                ft.Column(
                    controls=[
                        field_label(ft.Icons.WARNING_AMBER_ROUNDED, "異常事項"),
                        abnormal_note,
                    ],
                    spacing=7,
                ),
                ft.Column(
                    controls=[
                        field_label(ft.Icons.TASK_ALT_OUTLINED, "待辦事項"),
                        todo_note,
                    ],
                    spacing=7,
                ),
                submit_button,
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.VERIFIED_OUTLINED, size=17, color=TEXT_MUTED),
                        ft.Text(
                            "送出後會建立交接主表與項目明細，異常 / 待辦會進入未完成追蹤。",
                            size=13,
                            color=TEXT_MUTED,
                            max_lines=3,
                            overflow=ft.TextOverflow.VISIBLE,
                            expand=True,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=16,
        ),
    )

    refresh_shift_buttons(update_now=False)
    refresh_submit_button(update_now=False)
    threading.Timer(0.25, start_load_users).start()

    return ft.Container(
        bgcolor=BG,
        content=ft.Column(
            controls=[
                title_header(),
                sync_card,
                shift_card,
                form_card,
                ft.Container(height=90),
            ],
            spacing=18,
            scroll=ft.ScrollMode.AUTO,
        ),
    )
