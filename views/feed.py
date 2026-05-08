# views/feed.py
import flet as ft
import threading

from services.feed_service import (
    load_feed_page_data,
    submit_material_feed_record,
    submit_recycled_feed_record,
    today_slash_date as service_today_slash_date,
    today_dash_date as service_today_dash_date,
    parse_feed_date_to_taipei_iso,
    format_feed_datetime,
    now_taipei,
)

from services.dryer_status_service import (
    load_dryer_status,
    save_dryer_status,
)


def FeedContent(page: ft.Page):
    # =====================================================
    # 0. 基本資料狀態
    # =====================================================
    new_materials = {}
    aux_materials = {}
    rec_materials = {}
    low_stock_items = []  # feed_service 仍會回傳低水位，但本頁不再顯示
    recent_records = []

    dryer_status_items = []
    dryer_latest_updated = {"value": "-"}

    data_loaded = {"done": False}
    active_mode = {"value": "new"}  # new / aux / rec
    submitting = {"value": False}

    submit_state = {
        "hover": False,
        "pressed": False,
    }

    # 背景載入保護：避免切離 /feed 或重建頁面後，舊 thread 回來更新舊控制項。
    is_alive = {"value": True}
    view_token = object()
    load_guard = {"token": view_token}

    session_data = page.session_data if hasattr(page, "session_data") and isinstance(page.session_data, dict) else {}
    if session_data is not None:
        session_data["_feed_view_token"] = view_token

    current_user_name = str(session_data.get("user_name") or "").strip()
    current_user_id = session_data.get("user_id")

    page_w = page.width or 430
    is_mobile_page = page_w <= 520

    # =====================================================
    # 1. 色彩設定
    # =====================================================
    CARD = "#FFFFFF"
    TEXT_MAIN = "#111827"
    TEXT_SUB = "#64748B"
    BORDER = "#E2E8F0"
    INPUT_BG = "#F8FAFC"

    BLUE = "#2F80ED"
    BLUE_SOFT = "#E5F0FF"
    BLUE_BORDER = "#B0D0FF"
    BLUE_BTN = "#4F7FB8"
    BLUE_BTN_HOVER = "#456FA3"
    BLUE_BTN_PRESS = "#3D628F"

    PURPLE = "#8B5CF6"
    PURPLE_SOFT = "#F3E8FF"
    PURPLE_BORDER = "#D8B4FE"
    PURPLE_BTN = "#7358B8"
    PURPLE_BTN_HOVER = "#654BA4"
    PURPLE_BTN_PRESS = "#573F8F"

    ORANGE = "#F97316"
    ORANGE_SOFT = "#FFF7ED"
    ORANGE_BORDER = "#FDBA74"
    ORANGE_BTN = "#C96D32"
    ORANGE_BTN_HOVER = "#B8602C"
    ORANGE_BTN_PRESS = "#A55427"

    DISABLED = "#94A3B8"

    GREEN = "#10B981"
    GREEN_SOFT = "#ECFDF5"
    GREEN_BORDER = "#A7F3D0"

    RED = "#EF4444"
    RED_SOFT = "#FEF2F2"
    RED_BORDER = "#FECACA"

    # =====================================================
    # 2. 更新與工具
    # =====================================================
    def update_page():
        """
        集中更新頁面。
        一般互動流程只在最後呼叫一次 page.update()；
        背景 thread 不逐一 control.update()，避免手機 Web 產生大量 WebSocket/render 訊號。
        """
        page.update()

    def is_current_feed_view(token=None) -> bool:
        if not is_alive.get("value", False):
            return False

        if token is not None and load_guard.get("token") is not token:
            return False

        if hasattr(page, "session_data") and isinstance(page.session_data, dict):
            if page.session_data.get("_feed_view_token") is not view_token:
                return False

        # 現行 main.py 以 route 切頁；此條件保留，但不作為唯一保護。
        current_route = getattr(page, "route", None)
        if current_route and current_route != "/feed":
            return False

        return True

    def show_snack(message: str, color: str):
        snack = ft.SnackBar(
            content=ft.Text(message, color="white", weight=ft.FontWeight.W_600),
            bgcolor=color,
            duration=3200,
        )
        page.overlay.append(snack)
        snack.open = True
        update_page()

    def get_str(value, default=""):
        if isinstance(value, list):
            return str(value[0]) if value else default
        if value is None:
            return default
        return str(value)

    def get_num(value, default=0):
        if isinstance(value, list):
            value = value[0] if value else default
        try:
            return float(value)
        except Exception:
            return default

    def parse_percent_1_decimal(value, default=0.0):
        text = str(value if value is not None else "").strip().replace("％", "%")
        text = text.replace("%", "")

        if not text:
            return float(default)

        try:
            number = float(text)
        except Exception:
            raise ValueError("內存比例請輸入數字，例如 62.6")

        if number < 0 or number > 100:
            raise ValueError("內存比例需介於 0.0 到 100.0 之間")

        return round(number, 1)

    def normalize_dryer_status_item(item):
        row = dict(item or {})
        try:
            row["percent"] = parse_percent_1_decimal(row.get("percent", 0), 0.0)
        except Exception:
            row["percent"] = 0.0
        return row

    def today_slash_date():
        return service_today_slash_date()

    def today_dash_date():
        return service_today_dash_date()

    def now_datetime_string(date_text: str):
        return parse_feed_date_to_taipei_iso(date_text)

    def aux_batch_prefix():
        """
        輔助母粒領用批號前綴。
        操作員需在此日期前綴後補流水號，例如 MB2026050801。
        """
        return f"MB{now_taipei().strftime('%Y%m%d')}"

    def aux_batch_example():
        return f"{aux_batch_prefix()}01"

    def validate_aux_batch_no(value):
        """
        輔助母粒批號必須為：MB + 8 碼日期 + 至少 2 碼流水號。
        例如：MB2026050801。
        """
        text_value = str(value or "").strip().upper()

        if not text_value:
            return False, f"請輸入母粒批號，例如 {aux_batch_example()}。"

        if not text_value.startswith("MB"):
            return False, f"母粒批號格式需為 MB + 日期 + 流水號，例如 {aux_batch_example()}。"

        number_part = text_value[2:]
        if not number_part.isdigit():
            return False, f"母粒批號只能使用 MB 加數字，例如 {aux_batch_example()}。"

        if len(number_part) < 10:
            return False, f"請補齊母粒批號流水號，例如 {aux_batch_example()}。"

        date_part = number_part[:8]
        serial_part = number_part[8:]

        if len(date_part) != 8 or len(serial_part) < 2:
            return False, f"請補齊母粒批號流水號，例如 {aux_batch_example()}。"

        return True, ""

    def format_datetime_local(dt_text: str):
        return format_feed_datetime(dt_text)

    def get_operator_options():
        # 已建立登入系統後，填單人直接使用目前登入者，不再使用寫死名單。
        if current_user_name:
            return [current_user_name]
        return ["未登入使用者"]
    
    def parse_rec_material_display(display_text: str):
        """
        將下拉選單文字：
        【力鵬】 2025121007 ｜ PA6 ｜ 340 KG

        轉成：
        material = [力鵬] PA6
        qty = 340 KG
        """
        text = str(display_text or "").strip()

        supplier = ""
        mat_type = ""
        weight = ""

        try:
            parts = [p.strip() for p in text.split("｜")]

            # parts[0] = 【力鵬】 2025121007
            # parts[1] = PA6
            # parts[2] = 340 KG
            if len(parts) >= 1:
                first = parts[0]

                if first.startswith("【") and "】" in first:
                    supplier = first.split("】")[0].replace("【", "").strip()

            if len(parts) >= 2:
                mat_type = parts[1].strip()

            if len(parts) >= 3:
                weight = parts[2].strip()

            material_text = f"[{supplier}] {mat_type}".strip()

            if material_text == "[]":
                material_text = text

            return material_text, weight if weight else "1 筆"

        except Exception:
            return text, "1 筆"

    # =====================================================
    # 3. 狀態列
    # =====================================================
    status_badge = ft.Container(
        height=36,
        padding=ft.padding.symmetric(horizontal=16),
        border_radius=18,
        bgcolor=BLUE_SOFT,
        border=ft.border.all(1, BLUE_BORDER),
        content=ft.Row(
            controls=[
                ft.ProgressRing(width=15, height=15, stroke_width=2, color=BLUE),
                ft.Text(
                    "資料同步中",
                    size=13,
                    color=BLUE,
                    weight=ft.FontWeight.W_600,
                ),
            ],
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    # 手機 Web：用外層容器控制顯示 / 隱藏，讓隱藏後不保留空白高度。
    status_badge_area = ft.Container(
        alignment=ft.Alignment(-1, 0),
        content=status_badge,
    )
    status_hide_guard = {"version": 0}

    def schedule_status_auto_hide(version: int, delay_seconds: float = 3.0):
        def _hide():
            if status_hide_guard.get("version") != version:
                return

            if not is_current_feed_view():
                return

            status_badge_area.visible = False

            try:
                update_page()
            except Exception as ex:
                print("feed status auto hide error:", ex)

        timer = threading.Timer(delay_seconds, _hide)
        timer.daemon = True
        timer.start()

    def set_status(text, theme="blue", loading=False, update_now=True):
        if theme == "green":
            bg = GREEN_SOFT
            border = GREEN_BORDER
            fg = GREEN
            icon = ft.Icons.CHECK_CIRCLE_OUTLINE
        elif theme == "red":
            bg = RED_SOFT
            border = RED_BORDER
            fg = RED
            icon = ft.Icons.ERROR_OUTLINE
        elif theme == "orange":
            bg = ORANGE_SOFT
            border = ORANGE_BORDER
            fg = ORANGE
            icon = ft.Icons.INFO_OUTLINE
        else:
            bg = BLUE_SOFT
            border = BLUE_BORDER
            fg = BLUE
            icon = ft.Icons.SYNC

        status_hide_guard["version"] += 1
        current_status_version = status_hide_guard["version"]

        status_badge_area.visible = True
        status_badge.bgcolor = bg
        status_badge.border = ft.border.all(1, border)

        if loading:
            lead = ft.ProgressRing(width=15, height=15, stroke_width=2, color=fg)
        else:
            lead = ft.Icon(icon, size=17, color=fg)

        status_badge.content = ft.Row(
            controls=[
                lead,
                ft.Text(text, size=13, color=fg, weight=ft.FontWeight.W_600),
            ],
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        if update_now:
            update_page()

        if theme == "green" and not loading:
            schedule_status_auto_hide(current_status_version, delay_seconds=3.0)

    # =====================================================
    # 4. 共用 UI 元件
    # =====================================================
    def field_label(icon_name, label, color="#64748B", required=False):
        return ft.Row(
            controls=[
                ft.Icon(icon_name, size=18, color=color),
                ft.Text(
                    label + (" *" if required else ""),
                    size=14,
                    color=TEXT_MAIN,
                    weight=ft.FontWeight.W_600,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def text_input(label, icon_name, value=None, hint="", required=False, multiline=False):
        # 不傳 value=None，避免 Flet Web 把空值視為已有值而讓 hint_text 不顯示。
        field_kwargs = dict(
            hint_text=hint,
            hint_style=ft.TextStyle(size=14, color="#64748B"),
            multiline=multiline,
            min_lines=2 if multiline else 1,
            max_lines=3 if multiline else 1,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE,
            bgcolor=INPUT_BG,
            filled=True,
            text_size=15,
            height=94 if multiline else 52,
            content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
        )

        # Flet 0.84 / 手機 Web：部分情境 hint_text 仍可能不顯示。
        # 加上 label 作為欄位內提示備援，避免空白欄位看不到輸入提示。
        if hint:
            field_kwargs["label"] = hint
            field_kwargs["label_style"] = ft.TextStyle(size=14, color="#64748B")

        if value not in ("", None):
            field_kwargs["value"] = value

        return ft.Column(
            controls=[
                field_label(icon_name, label, required=required),
                ft.TextField(**field_kwargs),
            ],
            spacing=7,
            expand=True,
        )

    def dropdown_input(label, icon_name, options, required=False):
        opts = [ft.dropdown.Option(o) for o in options] if options else [ft.dropdown.Option("資料載入中")]
        return ft.Column(
            controls=[
                field_label(icon_name, label, required=required),
                ft.Dropdown(
                    options=opts,
                    border_radius=12,
                    border_color=BORDER,
                    focused_border_color=BLUE,
                    bgcolor=INPUT_BG,
                    filled=True,
                    height=52,
                    text_size=15,
                    content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
                ),
            ],
            spacing=7,
            expand=True,
        )

    def info_card(title, lines, theme="blue"):
        if theme == "red":
            color = RED
            bg = RED_SOFT
            border = RED_BORDER
            icon = ft.Icons.WARNING_AMBER_ROUNDED
        elif theme == "purple":
            color = PURPLE
            bg = "#FBF7FF"
            border = PURPLE_BORDER
            icon = ft.Icons.HISTORY
        else:
            color = BLUE
            bg = "#F8FBFF"
            border = BLUE_BORDER
            icon = ft.Icons.LIGHTBULB_OUTLINE

        return ft.Container(
            bgcolor=bg,
            border=ft.border.all(1, border),
            border_radius=16,
            padding=18,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(icon, size=24, color=color),
                            ft.Text(title, size=18, color=color, weight=ft.FontWeight.BOLD),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Container(width=8, height=8, bgcolor=color, border_radius=4),
                                    ft.Text(line, size=14, color=TEXT_MAIN),
                                ],
                                spacing=10,
                            )
                            for line in lines
                        ],
                        spacing=10,
                    ),
                ],
                spacing=14,
            ),
        )

    # =====================================================
    # 5. Header
    # =====================================================
    header_title_block = ft.Row(
        controls=[
            ft.Container(
                width=54,
                height=54,
                border_radius=16,
                bgcolor="#EFF6FF",
                alignment=ft.Alignment(0, 0),
                content=ft.Icon(
                    ft.Icons.FACTORY_OUTLINED,
                    size=30,
                    color="#334155",
                ),
            ),
            ft.Column(
                controls=[
                    ft.Text(
                        "現場打料作業",
                        size=25 if is_mobile_page else 26,
                        weight=ft.FontWeight.BOLD,
                        color=TEXT_MAIN,
                    ),
                    ft.Text(
                        "記錄原料領用與配料資訊，確保生產流程順暢與庫存準確。",
                        size=13 if is_mobile_page else 14,
                        color=TEXT_SUB,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=4,
                expand=True,
            ),
        ],
        spacing=14,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True,
    )

    header = ft.Container(
        padding=ft.padding.only(bottom=8),
        content=(
            ft.Column(
                controls=[
                    header_title_block,
                    status_badge_area,
                ],
                spacing=10,
            )
            if is_mobile_page
            else ft.Row(
                controls=[
                    header_title_block,
                    status_badge_area,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        ),
    )

    # =====================================================
    # 6. 乾燥塔內存備忘：取代低水位警示
    # =====================================================
    dryer_status_grid = ft.ResponsiveRow(
        columns=12,
        spacing=12,
        run_spacing=12,
    )

    dryer_memo_panel = ft.Container(
        bgcolor="#FFFFFF",
        border=ft.border.all(1, BORDER),
        border_radius=18,
        padding=18,
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=10,
            color="#06000000",
            offset=ft.Offset(0, 2),
        ),
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Container(
                                    width=46,
                                    height=46,
                                    border_radius=14,
                                    bgcolor="#F8FAFC",
                                    alignment=ft.Alignment(0, 0),
                                    content=ft.Icon(
                                        ft.Icons.LOCAL_FIRE_DEPARTMENT_OUTLINED,
                                        size=25,
                                        color="#334155",
                                    ),
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "乾燥塔內存備忘",
                                            size=18,
                                            weight=ft.FontWeight.BOLD,
                                            color=TEXT_MAIN,
                                        ),
                                        ft.Text(
                                            "此區為人工備忘，不影響正式原料庫存。",
                                            size=13,
                                            color=TEXT_SUB,
                                        ),
                                    ],
                                    spacing=2,
                                ),
                            ],
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                dryer_status_grid,
            ],
            spacing=14,
        ),
    )

    def dryer_theme(tower_type: str):
        if str(tower_type).upper() == "PA6":
            return {
                "color": ORANGE,
                "soft": ORANGE_SOFT,
                "border": ORANGE_BORDER,
                "button": ORANGE_BTN,
                "track": "#FED7AA",
            }

        return {
            "color": BLUE,
            "soft": BLUE_SOFT,
            "border": BLUE_BORDER,
            "button": BLUE_BTN,
            "track": "#BFDBFE",
        }

    def dryer_icon_box(tower_type: str):
        theme = dryer_theme(tower_type)
        icon_src = "assets/dryer_pa6_icon.png" if str(tower_type).upper() == "PA6" else "assets/dryer_pet_icon.png"

        # 使用使用者提供的 PET / PA6 乾燥塔圖片。
        # 圖片文字保留；實際塔內原料由卡片欄位顯示。
        return ft.Container(
            width=64,
            height=64,
            border_radius=18,
            bgcolor=theme["soft"],
            border=ft.border.all(1, theme["border"]),
            alignment=ft.Alignment(0, 0),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Image(
                src=icon_src,
                width=56,
                height=56,
            ),
        )

    def open_dryer_edit_dialog(item: dict):
        tower_code = item.get("tower_code", "")
        tower_type = item.get("tower_type", "")

        material_field = ft.TextField(
            label="目前塔內原料",
            value="" if item.get("material") == "未填寫" else item.get("material", ""),
            hint_text="例如：PET308A-南紡",
            hint_style=ft.TextStyle(size=14, color="#64748B"),
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE,
            bgcolor=INPUT_BG,
            filled=True,
        )

        percent_field = ft.TextField(
            label="內存比例 %",
            value=f"{parse_percent_1_decimal(item.get('percent', 0), 0.0):.1f}",
            hint_text="0.0 ~ 100.0",
            hint_style=ft.TextStyle(size=14, color="#64748B"),
            keyboard_type=ft.KeyboardType.TEXT,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE,
            bgcolor=INPUT_BG,
            filled=True,
        )

        note_field_dialog = ft.TextField(
            label="備註",
            value="" if item.get("note") == "無備註" else item.get("note", ""),
            hint_text="例如：停機前未清空",
            hint_style=ft.TextStyle(size=14, color="#64748B"),
            multiline=True,
            min_lines=2,
            max_lines=3,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=BLUE,
            bgcolor=INPUT_BG,
            filled=True,
        )

        saving = {"value": False}

        def close_dlg(e=None):
            dlg.open = False
            update_page()

        def save_dlg(e=None):
            if saving["value"]:
                return

            saving["value"] = True

            try:
                try:
                    percent_value = parse_percent_1_decimal(percent_field.value, 0.0)
                except ValueError as ex:
                    show_snack(str(ex), RED)
                    return

                result = save_dryer_status(
                    tower_code=tower_code,
                    material=str(material_field.value or "").strip(),
                    percent=percent_value,
                    note=str(note_field_dialog.value or "").strip(),
                    updated_by_user_id=current_user_id,
                    updated_by_name=current_user_name,
                )

                if not result.ok:
                    show_snack(result.message, RED)
                    return

                reload_dryer_status_data()
                refresh_dryer_status_panel()
                close_dlg()
                show_snack(result.message, GREEN)

            except Exception as ex:
                show_snack(f"儲存失敗：{ex}", RED)

            finally:
                saving["value"] = False

        theme = dryer_theme(tower_type)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    dryer_icon_box(tower_type),
                    ft.Column(
                        controls=[
                            ft.Text(f"編輯 {tower_code}", size=18, weight=ft.FontWeight.BOLD),
                            ft.Text("人工備忘，不影響正式庫存。", size=12, color=TEXT_SUB),
                        ],
                        spacing=2,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            content=ft.Container(
                width=430,
                content=ft.Column(
                    controls=[
                        material_field,
                        percent_field,
                        note_field_dialog,
                    ],
                    spacing=14,
                    tight=True,
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=close_dlg),
                ft.Container(
                    width=96,
                    height=42,
                    border_radius=10,
                    bgcolor=theme["button"],
                    alignment=ft.Alignment(0, 0),
                    on_click=save_dlg,
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.SAVE_OUTLINED, size=18, color="white"),
                            ft.Text("儲存", size=14, color="white", weight=ft.FontWeight.W_600),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=7,
                        tight=True,
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        page.overlay.append(dlg)
        dlg.open = True
        update_page()

    def dryer_status_card(item: dict):
        tower_code = item.get("tower_code", "-")
        tower_type = item.get("tower_type", "PET")
        material = item.get("material", "未填寫")
        note = item.get("note", "無備註")
        try:
            percent = parse_percent_1_decimal(item.get("percent", 0), 0.0)
        except Exception:
            percent = 0.0
        updated_at = item.get("updated_at", "-")
        updated_by = item.get("updated_by_name", "-")
        theme = dryer_theme(tower_type)

        return ft.Container(
            col={"xs": 12, "sm": 6, "md": 6, "lg": 3},
            content=ft.Container(
                bgcolor="#FFFFFF",
                border=ft.border.all(1, theme["border"]),
                border_radius=16,
                padding=14,
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                dryer_icon_box(tower_type),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            tower_code,
                                            size=17,
                                            weight=ft.FontWeight.BOLD,
                                            color=TEXT_MAIN,
                                        ),
                                        ft.Text(
                                            f"更新：{updated_at}",
                                            size=12,
                                            color=TEXT_SUB,
                                        ),
                                    ],
                                    spacing=3,
                                    expand=True,
                                ),
                            ],
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Container(
                            padding=ft.padding.symmetric(horizontal=11, vertical=9),
                            bgcolor="#F8FAFC",
                            border_radius=12,
                            border=ft.border.all(1, "#E5EAF2"),
                            content=ft.Column(
                                controls=[
                                    ft.Text("目前塔內原料", size=12, color=TEXT_SUB),
                                    ft.Text(
                                        material,
                                        size=15,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXT_MAIN,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                ],
                                spacing=2,
                            ),
                        ),
                        ft.Column(
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Text(
                                            f"{percent:.1f}%",
                                            size=16,
                                            weight=ft.FontWeight.BOLD,
                                            color=theme["color"],
                                            width=48,
                                        ),
                                        ft.Container(
                                            expand=True,
                                            content=ft.ProgressBar(
                                                value=max(0, min(100, percent)) / 100,
                                                color=theme["color"],
                                                bgcolor=theme["track"],
                                                height=8,
                                            ),
                                        ),
                                    ],
                                    spacing=8,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                ft.Text(
                                    f"備註：{note}",
                                    size=12,
                                    color=TEXT_SUB,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text(
                                    f"更新人員：{updated_by}",
                                    size=12,
                                    color="#94A3B8",
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                            spacing=5,
                        ),
                        ft.Container(
                            height=36,
                            border_radius=18,
                            bgcolor=theme["soft"],
                            border=ft.border.all(1, theme["border"]),
                            alignment=ft.Alignment(0, 0),
                            on_click=lambda e, it=item: open_dryer_edit_dialog(it),
                            content=ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.EDIT_OUTLINED, size=16, color=theme["color"]),
                                    ft.Text("編輯", size=13, color=theme["color"], weight=ft.FontWeight.W_600),
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=6,
                                tight=True,
                            ),
                        ),
                    ],
                    spacing=11,
                ),
            ),
        )

    def _apply_dryer_status_panel():
        dryer_status_grid.controls = []

        if not dryer_status_items:
            dryer_status_grid.controls.append(
                ft.Container(
                    col={"xs": 12},
                    bgcolor="#F8FAFC",
                    border_radius=14,
                    padding=16,
                    content=ft.Text(
                        "目前尚未讀取到乾燥塔內存備忘。",
                        size=13,
                        color=TEXT_SUB,
                    ),
                )
            )
        else:
            for item in dryer_status_items:
                dryer_status_grid.controls.append(dryer_status_card(item))


    def refresh_dryer_status_panel(update_now=True):
        _apply_dryer_status_panel()
        if update_now:
            update_page()

    # =====================================================
    # 7. 打料類型選擇卡
    # =====================================================
    mode_cards_row = ft.ResponsiveRow(spacing=14, run_spacing=14)

    def mode_card(mode, title, desc, icon_name, color, soft, border):
        selected = active_mode["value"] == mode

        return ft.Container(
            col={"xs": 12, "sm": 4, "md": 4, "lg": 4},
            content=ft.GestureDetector(
                mouse_cursor=ft.MouseCursor.CLICK,
                on_tap=lambda e, m=mode: switch_mode(m),
                content=ft.Container(
                    height=112,
                    border_radius=18,
                    padding=18,
                    bgcolor=soft if selected else "#FFFFFF",
                    border=ft.border.all(2 if selected else 1, color if selected else BORDER),
                    shadow=ft.BoxShadow(
                        spread_radius=0,
                        blur_radius=10,
                        color="#08000000",
                        offset=ft.Offset(0, 3),
                    ),
                    content=ft.Row(
                        controls=[
                            ft.Container(
                                width=52,
                                height=52,
                                border_radius=14,
                                bgcolor=soft,
                                alignment=ft.Alignment(0, 0),
                                content=ft.Icon(icon_name, size=28, color=color),
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(
                                        title,
                                        size=18,
                                        color=TEXT_MAIN,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(desc, size=13, color=TEXT_SUB),
                                ],
                                spacing=4,
                                expand=True,
                            ),
                            ft.Icon(
                                ft.Icons.CHECK_CIRCLE if selected else ft.Icons.RADIO_BUTTON_UNCHECKED,
                                size=24,
                                color=color if selected else "#94A3B8",
                            ),
                        ],
                        spacing=14,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ),
            ),
        )

    def _apply_mode_cards():
        mode_cards_row.controls = [
            mode_card(
                "new",
                "領用新料",
                "領用全新原料進行生產",
                ft.Icons.INVENTORY_2_OUTLINED,
                BLUE,
                BLUE_SOFT,
                BLUE_BORDER,
            ),
            mode_card(
                "aux",
                "輔助母粒",
                "領用母粒進行功能添加",
                ft.Icons.PALETTE_OUTLINED,
                PURPLE,
                PURPLE_SOFT,
                PURPLE_BORDER,
            ),
            mode_card(
                "rec",
                "領用回用料",
                "領用回用料再次利用",
                ft.Icons.RECYCLING,
                ORANGE,
                ORANGE_SOFT,
                ORANGE_BORDER,
            ),
        ]

    def rebuild_mode_cards(update_now=True):
        _apply_mode_cards()
        if update_now:
            update_page()

    # =====================================================
    # 8. 表單控制項
    # =====================================================
    batch_input_group = text_input(
        "原料批號",
        ft.Icons.NUMBERS_OUTLINED,
        hint="輸入原料包裝上之批號",
        required=True,
    )
    batch_field = batch_input_group.controls[1]

    date_input_group = text_input(
        "日期",
        ft.Icons.CALENDAR_MONTH_OUTLINED,
        value=today_slash_date(),
        required=True,
    )
    date_field = date_input_group.controls[1]

    material_input_group = dropdown_input(
        "領用新料",
        ft.Icons.CATEGORY_OUTLINED,
        [],
        required=True,
    )
    material_dropdown = material_input_group.controls[1]

    machine_input_group = dropdown_input(
        "選擇乾燥塔",
        ft.Icons.SETTINGS_OUTLINED,
        ["S1-PET", "S1-PA6", "S2-PET", "S2-PA6"],
        required=True,
    )
    machine_dropdown = machine_input_group.controls[1]
    machine_dropdown.value = "S1-PET"

    qty_value = ft.Text("1", size=16, color=TEXT_MAIN, weight=ft.FontWeight.BOLD)

    def change_qty(delta):
        try:
            current = int(qty_value.value)
        except Exception:
            current = 1

        current = max(1, current + delta)
        qty_value.value = str(current)
        update_page()

    qty_control = ft.Column(
        controls=[
            field_label(ft.Icons.INVENTORY_OUTLINED, "領用數量（包）", required=True),
            ft.Container(
                height=52,
                border_radius=12,
                border=ft.border.all(1, BORDER),
                bgcolor=INPUT_BG,
                content=ft.Row(
                    controls=[
                        ft.IconButton(
                            icon=ft.Icons.REMOVE,
                            icon_color=TEXT_MAIN,
                            on_click=lambda e: change_qty(-1),
                        ),
                        ft.Container(
                            expand=True,
                            alignment=ft.Alignment(0, 0),
                            content=qty_value,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ADD,
                            icon_color=TEXT_MAIN,
                            on_click=lambda e: change_qty(1),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ),
        ],
        spacing=7,
        expand=True,
    )

    operator_input_group = dropdown_input(
        "填單人",
        ft.Icons.PERSON_OUTLINE,
        [],
        required=True,
    )
    operator_dropdown = operator_input_group.controls[1]

    note_input_group = text_input(
        "備註（選填）",
        ft.Icons.NOTES_OUTLINED,
        hint="輸入備註...",
        multiline=True,
    )
    note_field = note_input_group.controls[1]

    def get_submit_colors():
        mode = active_mode["value"]

        if mode == "new":
            return BLUE_BTN, BLUE_BTN_HOVER, BLUE_BTN_PRESS

        if mode == "aux":
            return PURPLE_BTN, PURPLE_BTN_HOVER, PURPLE_BTN_PRESS

        return ORANGE_BTN, ORANGE_BTN_HOVER, ORANGE_BTN_PRESS

    def submit_button_label():
        if submitting["value"]:
            return "寫入中..."

        if active_mode["value"] == "new":
            return "送出新料紀錄"
        if active_mode["value"] == "aux":
            return "送出母粒紀錄"
        return "送出回用料紀錄"

    submit_button_icon = ft.Icon(ft.Icons.SEND_ROUNDED, color="white", size=22)
    submit_button_text = ft.Text(
        "送出新料紀錄",
        color="white",
        size=17,
        weight=ft.FontWeight.BOLD,
    )

    submit_button = ft.Container(
        height=58,
        border_radius=12,
        bgcolor=DISABLED,
        opacity=0.75,
        alignment=ft.Alignment(0, 0),
        on_click=None,
        content=ft.Row(
            controls=[submit_button_icon, submit_button_text],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        ),
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=10,
            color="#12000000",
            offset=ft.Offset(0, 4),
        ),
    )

    def refresh_submit_button(update_now=False):
        base, hover, press = get_submit_colors()

        disabled = submitting["value"] or not data_loaded["done"]
        submit_button_text.value = submit_button_label()
        submit_button_icon.name = ft.Icons.HOURGLASS_TOP if submitting["value"] else ft.Icons.SEND_ROUNDED

        if disabled:
            bg = DISABLED
            submit_button.opacity = 0.78
            submit_button.on_click = None
        elif submit_state["pressed"]:
            bg = press
            submit_button.opacity = 1
            submit_button.on_click = lambda e: submit_feed(e)
        elif submit_state["hover"]:
            bg = hover
            submit_button.opacity = 1
            submit_button.on_click = lambda e: submit_feed(e)
        else:
            bg = base
            submit_button.opacity = 1
            submit_button.on_click = lambda e: submit_feed(e)

        submit_button.bgcolor = bg

        if update_now:
            update_page()

    def submit_hover(e):
        if submitting["value"] or not data_loaded["done"]:
            return

        submit_state["hover"] = e.data == "true"
        refresh_submit_button(update_now=True)

    def submit_tap_down(e):
        if submitting["value"] or not data_loaded["done"]:
            return

        submit_state["pressed"] = True
        refresh_submit_button(update_now=True)

    def submit_tap_cancel(e):
        if submitting["value"] or not data_loaded["done"]:
            return

        submit_state["pressed"] = False
        refresh_submit_button(update_now=True)

    submit_button.on_hover = submit_hover

    form_title_icon = ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, size=26, color=BLUE)
    form_title_text = ft.Text("領用新料作業", size=20, color=TEXT_MAIN, weight=ft.FontWeight.BOLD)
    form_subtitle = ft.Text(
        "填寫領用資訊，系統將自動寫入並同步紀錄。",
        size=13,
        color=TEXT_SUB,
        max_lines=2,
        overflow=ft.TextOverflow.ELLIPSIS,
    )

    form_fields_area = ft.Column(spacing=18)

    form_card = ft.Container(
        bgcolor="#FFFFFF",
        border=ft.border.all(1, BLUE_BORDER),
        border_radius=18,
        padding=22,
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=12,
            color="#08000000",
            offset=ft.Offset(0, 3),
        ),
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        form_title_icon,
                        ft.Column(
                            controls=[form_title_text, form_subtitle],
                            spacing=3,
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(height=20, color="#EEF2F7"),
                form_fields_area,
                submit_button,
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.VERIFIED_OUTLINED, size=17, color="#94A3B8"),
                        ft.Text(
                            "送出後會同步更新庫存與打料紀錄，請確認資訊正確無誤。",
                            size=13,
                            color="#94A3B8",
                        ),
                    ],
                    spacing=8,
                ),
            ],
            spacing=16,
        ),
    )

    # =====================================================
    # 9. 右側輔助區塊：手機時會自然往下
    # =====================================================
    operation_reminder = info_card(
        "操作提醒",
        [
            "請確認原料批號與包裝標示一致。",
            "領用數量單位為「包」，請正確輸入。",
            "送出後將同步更新庫存與使用量統計。",
            "如遇異常狀況，請聯繫當班主管處理。",
        ],
        "blue",
    )

    recent_table = ft.Column(spacing=0)
    recent_show_all = {"value": False}

    recent_toggle_text = ft.Text(
        "查看全部",
        size=14,
        color=PURPLE,
        weight=ft.FontWeight.W_600,
    )
    recent_toggle_icon = ft.Icon(ft.Icons.OPEN_IN_NEW, size=17, color=PURPLE)

    RECENT_TABLE_WIDTH = 980

    def recent_machine_text(item: dict):
        return (
            item.get("machine")
            or item.get("machine_code")
            or item.get("tower")
            or item.get("dryer")
            or "-"
        )

    def recent_table_cell(
        text,
        width,
        color=TEXT_MAIN,
        weight=None,
        align=ft.TextAlign.LEFT,
        max_lines=1,
    ):
        return ft.Container(
            width=width,
            padding=ft.padding.only(right=8),
            alignment=ft.Alignment(1, 0) if align == ft.TextAlign.RIGHT else ft.Alignment(-1, 0),
            content=ft.Text(
                str(text if text not in (None, "") else "-"),
                size=13,
                color=color,
                weight=weight,
                text_align=align,
                max_lines=max_lines,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        )

    def recent_type_badge(item: dict, is_header=False):
        if is_header:
            return recent_table_cell("類型", 76, color=TEXT_SUB, weight=ft.FontWeight.W_600)

        return ft.Container(
            width=76,
            padding=ft.padding.only(right=8),
            alignment=ft.Alignment(-1, 0),
            content=ft.Container(
                height=26,
                width=58,
                border_radius=13,
                bgcolor=item.get("tag_bg", BLUE_SOFT),
                alignment=ft.Alignment(0, 0),
                content=ft.Text(
                    item.get("type", "-"),
                    size=12,
                    color=item.get("tag_color", BLUE),
                    weight=ft.FontWeight.W_600,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ),
        )

    def recent_table_row(item: dict, is_header=False):
        bg = "#FAFAFB" if is_header else "#FFFFFF"
        text_color = TEXT_SUB if is_header else TEXT_MAIN
        weight = ft.FontWeight.W_600 if is_header else None
        border = None if is_header else ft.border.only(bottom=ft.BorderSide(1, "#EEF2F7"))

        if is_header:
            date_text = "日期"
            time_text = "時間"
            machine_text = "機台/塔別"
            material_text = "原料"
            qty_text = "數量"
            operator_text = "人員"
            note_text = "備註"
        else:
            date_text = item.get("date", "-")
            time_text = item.get("time", "-")
            machine_text = recent_machine_text(item)
            material_text = item.get("material", "-")
            qty_text = item.get("qty", "-")
            operator_text = item.get("operator", "-")
            note_text = item.get("note", "-")

        return ft.Container(
            width=RECENT_TABLE_WIDTH,
            bgcolor=bg,
            padding=ft.padding.symmetric(horizontal=12, vertical=11),
            border=border,
            content=ft.Row(
                controls=[
                    recent_table_cell(date_text, 96, color=text_color, weight=weight),
                    recent_table_cell(time_text, 66, color=text_color, weight=weight),
                    recent_type_badge(item, is_header=is_header),
                    recent_table_cell(machine_text, 92, color=text_color, weight=weight),
                    recent_table_cell(material_text, 350, color=text_color, weight=weight, max_lines=1),
                    recent_table_cell(qty_text, 82, color=text_color, weight=weight, align=ft.TextAlign.RIGHT),
                    recent_table_cell(operator_text, 106, color=text_color, weight=weight),
                    recent_table_cell(note_text, 112, color=text_color, weight=weight),
                ],
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def recent_table_view(limit=5):
        actual_limit = min(limit, len(recent_records))
        rows = [recent_table_row({}, is_header=True)]

        if recent_records:
            for item in recent_records[:limit]:
                rows.append(recent_table_row(item))
        else:
            rows.append(
                ft.Container(
                    width=RECENT_TABLE_WIDTH,
                    padding=16,
                    content=ft.Text("尚無打料紀錄", size=13, color=TEXT_SUB),
                )
            )

        info_text = (
            f"顯示最近 {actual_limit} 筆紀錄，左右滑動可查看右側欄位。"
            if recent_records
            else "資料同步後會顯示最近打料紀錄。"
        )

        return ft.Container(
            bgcolor="#FFFFFF",
            border_radius=12,
            border=ft.border.all(1, "#EEF2F7"),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Column(
                controls=[
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=12, vertical=9),
                        bgcolor="#FAFAFB",
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=TEXT_SUB),
                                ft.Text(
                                    info_text,
                                    size=12,
                                    color=TEXT_SUB,
                                    weight=ft.FontWeight.W_600,
                                    expand=True,
                                ),
                            ],
                            spacing=6,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ),
                    ft.Row(
                        scroll=ft.ScrollMode.AUTO,
                        controls=[
                            ft.Container(
                                width=RECENT_TABLE_WIDTH,
                                content=ft.Column(
                                    controls=rows,
                                    spacing=0,
                                ),
                            )
                        ],
                    ),
                ],
                spacing=0,
            ),
        )

    def _apply_recent_panel():
        if recent_show_all["value"]:
            recent_toggle_text.value = "收合"
            recent_toggle_icon.name = ft.Icons.EXPAND_LESS
            recent_table.controls = [recent_table_view(20)]
            return

        recent_toggle_text.value = "查看全部"
        recent_toggle_icon.name = ft.Icons.OPEN_IN_NEW
        recent_table.controls = [recent_table_view(5)]

    def refresh_recent_panel(update_now=True):
        _apply_recent_panel()
        if update_now:
            update_page()

    def toggle_all_recent(e=None):
        recent_show_all["value"] = not recent_show_all["value"]
        refresh_recent_panel(update_now=True)

    recent_panel = ft.Container(
        bgcolor="#FBF7FF",
        border=ft.border.all(1, PURPLE_BORDER),
        border_radius=18,
        padding=18,
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.HISTORY, size=24, color=PURPLE),
                                ft.Text("最近打料紀錄", size=18, color=PURPLE, weight=ft.FontWeight.BOLD),
                            ],
                            spacing=10,
                        ),
                        ft.Container(
                            height=36,
                            padding=ft.padding.symmetric(horizontal=12),
                            border_radius=18,
                            bgcolor="#FFFFFF",
                            border=ft.border.all(1, PURPLE_BORDER),
                            alignment=ft.Alignment(0, 0),
                            on_click=toggle_all_recent,
                            content=ft.Row(
                                controls=[recent_toggle_text, recent_toggle_icon],
                                spacing=5,
                                alignment=ft.MainAxisAlignment.CENTER,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                tight=True,
                            ),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                recent_table,
            ],
            spacing=12,
        ),
    )

    side_column = ft.Column(
        controls=[
            operation_reminder,
            recent_panel,
        ],
        spacing=16,
    )

    # =====================================================
    # 10. 主內容 responsive
    # =====================================================
    main_grid = ft.ResponsiveRow(
        columns=12,
        spacing=18,
        run_spacing=18,
        controls=[
            ft.Container(col={"xs": 12, "md": 7, "lg": 7}, content=form_card),
            ft.Container(col={"xs": 12, "md": 5, "lg": 5}, content=side_column),
        ],
    )

    # =====================================================
    # 11. 表單欄位配置
    # =====================================================
    form_fields_area.controls = [
        ft.ResponsiveRow(
            columns=12,
            spacing=16,
            run_spacing=16,
            controls=[
                ft.Container(col={"xs": 12, "md": 6}, content=batch_input_group),
                ft.Container(col={"xs": 12, "md": 6}, content=material_input_group),
                ft.Container(col={"xs": 12, "md": 6}, content=date_input_group),
                ft.Container(col={"xs": 12, "md": 6}, content=qty_control),
                ft.Container(col={"xs": 12, "md": 6}, content=machine_input_group),
                ft.Container(col={"xs": 12, "md": 6}, content=operator_input_group),
                ft.Container(col={"xs": 12}, content=note_input_group),
            ],
        )
    ]

    # =====================================================
    # 12. 依模式刷新表單
    # =====================================================
    def switch_mode(mode):
        active_mode["value"] = mode
        rebuild_mode_cards(update_now=False)
        refresh_form_by_mode(update_now=True)

    def refresh_form_by_mode(update_now=True):
        mode = active_mode["value"]

        batch_input_group.visible = mode != "rec"
        qty_control.visible = mode != "rec"
        note_input_group.visible = mode != "rec"
        operator_input_group.visible = mode == "rec"

        if mode == "new":
            form_title_icon.name = ft.Icons.INVENTORY_2_OUTLINED
            form_title_icon.color = BLUE
            form_title_text.value = "領用新料作業"
            material_input_group.controls[0].controls[1].value = "領用新料 *"
            batch_input_group.controls[0].controls[1].value = "原料批號 *"
            batch_field.hint_text = "輸入原料包裝上之批號"
            batch_field.label = "輸入原料包裝上之批號"
            batch_field.error_text = None

            # 從母粒切回新料時，清掉母粒自動帶入的批號，讓新料恢復 hint 狀態
            if str(batch_field.value or "").startswith("MB"):
                batch_field.value = ""

            if new_materials:
                keys = sorted(new_materials.keys())
                material_dropdown.options = [ft.dropdown.Option(k) for k in keys]
                material_dropdown.value = keys[0]
            else:
                material_dropdown.options = [ft.dropdown.Option("無新料資料")]
                material_dropdown.value = "無新料資料"

            machine_dropdown.options = [
                ft.dropdown.Option(x)
                for x in ["S1-PET", "S1-PA6", "S2-PET", "S2-PA6"]
            ]

            if machine_dropdown.value not in ["S1-PET", "S1-PA6", "S2-PET", "S2-PA6"]:
                machine_dropdown.value = "S1-PET"

            form_card.border = ft.border.all(1, BLUE_BORDER)

        elif mode == "aux":
            form_title_icon.name = ft.Icons.PALETTE_OUTLINED
            form_title_icon.color = PURPLE
            form_title_text.value = "輔助母粒作業"
            material_input_group.controls[0].controls[1].value = "領用母粒 *"
            batch_input_group.controls[0].controls[1].value = "母粒批號（請補齊流水號） *"
            batch_field.hint_text = f"例如：{aux_batch_example()}"
            batch_field.label = f"例如：{aux_batch_example()}"
            batch_field.error_text = None

            if aux_materials:
                keys = sorted(aux_materials.keys())
                material_dropdown.options = [ft.dropdown.Option(k) for k in keys]
                material_dropdown.value = keys[0]
            else:
                material_dropdown.options = [ft.dropdown.Option("無母粒資料")]
                material_dropdown.value = "無母粒資料"

            machine_dropdown.options = [
                ft.dropdown.Option(x)
                for x in ["S1-PET", "S2-PET"]
            ]
            machine_dropdown.value = "S1-PET"

            batch_field.value = aux_batch_prefix()
            form_card.border = ft.border.all(1, PURPLE_BORDER)

        else:
            form_title_icon.name = ft.Icons.RECYCLING
            form_title_icon.color = ORANGE
            form_title_text.value = "領用回用料作業"
            material_input_group.controls[0].controls[1].value = "領用回用料 *"
            batch_field.error_text = None

            if rec_materials:
                keys = list(rec_materials.keys())
                material_dropdown.options = [ft.dropdown.Option(k) for k in keys]
                material_dropdown.value = keys[0]
            else:
                material_dropdown.options = [ft.dropdown.Option("目前無在庫回用料")]
                material_dropdown.value = "目前無在庫回用料"

            machine_dropdown.options = [
                ft.dropdown.Option(x)
                for x in ["S1-PET", "S1-PA6", "S2-PET", "S2-PA6"]
            ]

            if machine_dropdown.value not in ["S1-PET", "S1-PA6", "S2-PET", "S2-PA6"]:
                machine_dropdown.value = "S1-PET"

            operator_dropdown.options = [ft.dropdown.Option(x) for x in get_operator_options()]
            operator_dropdown.value = current_user_name
            form_card.border = ft.border.all(1, ORANGE_BORDER)

        refresh_submit_button(update_now=False)

        if update_now:
            update_page()

    # =====================================================
    # 13. 送出邏輯
    # =====================================================
    def set_submitting(value: bool):
        submitting["value"] = value
        submit_state["pressed"] = False
        refresh_submit_button(update_now=False)
        update_page()

    def validate_common():
        if not data_loaded["done"]:
            show_snack("資料尚未同步完成，請稍候再送出。", RED)
            return False

        if not date_field.value:
            show_snack("請填寫日期。", RED)
            return False

        if not machine_dropdown.value:
            show_snack("請選擇乾燥塔。", RED)
            return False

        if not current_user_name:
            show_snack("無法取得目前登入者，請重新登入後再送出。", RED)
            return False

        return True

    def submit_feed(e):
        if submitting["value"]:
            return

        submit_state["pressed"] = False
        refresh_submit_button(update_now=True)

        mode = active_mode["value"]

        if not validate_common():
            return

        set_submitting(True)

        try:
            # =====================================================
            # A. 新料 / 母粒
            # Supabase：materials -> feed_records
            # =====================================================
            if mode in ["new", "aux"]:
                batch_no = str(batch_field.value or "").strip()
                batch_field.error_text = None

                if not batch_no:
                    batch_field.error_text = "請輸入原料批號。"
                    show_snack("請輸入原料批號。", RED)
                    update_page()
                    return

                if mode == "aux":
                    ok, message = validate_aux_batch_no(batch_no)
                    if not ok:
                        batch_field.error_text = message
                        show_snack(message, RED)
                        update_page()
                        return
                    batch_no = batch_no.upper()

                invalid_values = ["無新料資料", "無母粒資料", "資料載入中"]
                if not material_dropdown.value or material_dropdown.value in invalid_values:
                    show_snack("請選擇領用原料。", RED)
                    return

                material_map = new_materials if mode == "new" else aux_materials
                material_id = material_map.get(material_dropdown.value)

                if not material_id:
                    show_snack("找不到此原料資料，請重新整理。", RED)
                    return

                qty = int(qty_value.value or "1")

                result = submit_material_feed_record(
                    feed_type=mode,
                    material_id=material_id,
                    batch_no=batch_no,
                    feed_date=str(date_field.value or ""),
                    machine_code=str(machine_dropdown.value or ""),
                    quantity_bags=qty,
                    operator_name=current_user_name,
                    note=str(note_field.value or ""),
                    created_by_user_id=current_user_id,
                    created_by_name=current_user_name,
                )

                if not result.ok:
                    show_snack(result.message, RED)
                    return

                show_snack(result.message, GREEN)

                if mode == "new":
                    batch_field.value = ""
                else:
                    batch_field.value = aux_batch_prefix()

                qty_value.value = "1"
                note_field.value = ""

                update_page()

            # =====================================================
            # B. 回用料
            # Supabase：recycled_materials -> feed_records，成功後標記已領用
            # =====================================================
            else:
                if not rec_materials:
                    show_snack("目前沒有在庫的回用料。", RED)
                    return

                if not material_dropdown.value or material_dropdown.value == "目前無在庫回用料":
                    show_snack("請選擇領用回用料。", RED)
                    return

                if not operator_dropdown.value:
                    show_snack("請選擇填單人。", RED)
                    return

                recycled_material_id = rec_materials.get(material_dropdown.value)

                if not recycled_material_id:
                    show_snack("找不到此回用料資料，請重新整理。", RED)
                    return

                result = submit_recycled_feed_record(
                    recycled_material_id=recycled_material_id,
                    feed_date=str(date_field.value or ""),
                    machine_code=str(machine_dropdown.value or ""),
                    operator_name=str(operator_dropdown.value or current_user_name),
                    created_by_user_id=current_user_id,
                    created_by_name=current_user_name,
                )

                if not result.ok:
                    show_snack(result.message, RED)
                    return

                show_snack(result.message, GREEN)

                # 從目前畫面選單移除，避免連續重複領用
                if material_dropdown.value in rec_materials:
                    rec_materials.pop(material_dropdown.value)

            reload_feed_data_after_submit()
            refresh_form_by_mode(update_now=False)
            refresh_recent_panel(update_now=False)
            refresh_dryer_status_panel(update_now=False)
            update_page()

        except Exception as ex:
            show_snack(f"寫入失敗：{ex}", RED)
            print("feed submit error:", ex)

        finally:
            set_submitting(False)

    # =====================================================
    # 14. 背景資料載入
    # =====================================================
    def apply_dryer_status_data(data: dict):
        dryer_status_items.clear()
        dryer_status_items.extend([
            normalize_dryer_status_item(item)
            for item in data.get("items", [])
        ])
        dryer_latest_updated["value"] = data.get("latest_updated", "-")

    def reload_dryer_status_data():
        result = load_dryer_status()
        if result.ok:
            apply_dryer_status_data(result.data)
        else:
            show_snack(result.message, RED)

    def apply_feed_data(data: dict):
        new_materials.clear()
        aux_materials.clear()
        rec_materials.clear()
        low_stock_items.clear()
        recent_records.clear()

        new_materials.update(data.get("new_materials", {}))
        aux_materials.update(data.get("aux_materials", {}))
        rec_materials.update(data.get("rec_materials", {}))
        low_stock_items.extend(data.get("low_stock_items", []))
        recent_records.extend(data.get("recent_records", []))

    def reload_feed_data_after_submit():
        result = load_feed_page_data()
        if result.ok:
            apply_feed_data(result.data)
        else:
            show_snack(result.message, RED)

    def load_initial_data_once():
        """
        非阻塞背景載入版：
        - FeedContent 建構時不阻塞 UI。
        - 背景 thread 只讀 Supabase 資料。
        - 套用 UI 前檢查 token / route / alive。
        - 控制項屬性集中修改，最後只呼叫一次 page.update()。
        """
        current_token = object()
        load_guard["token"] = current_token

        if hasattr(page, "session_data") and isinstance(page.session_data, dict):
            page.session_data["_feed_view_token"] = view_token

        def _run():
            try:
                feed_result = load_feed_page_data()
                dryer_result = load_dryer_status()

                if not is_current_feed_view(current_token):
                    return

                if feed_result.ok:
                    apply_feed_data(feed_result.data)
                    data_loaded["done"] = True
                else:
                    data_loaded["done"] = False
                    print("feed load data error:", feed_result.message)

                if dryer_result.ok:
                    apply_dryer_status_data(dryer_result.data)
                else:
                    print("dryer status load error:", dryer_result.message)

                refresh_dryer_status_panel(update_now=False)
                rebuild_mode_cards(update_now=False)
                refresh_form_by_mode(update_now=False)
                refresh_recent_panel(update_now=False)
                set_status(
                    "資料已同步" if data_loaded["done"] else "資料同步失敗",
                    theme="green" if data_loaded["done"] else "red",
                    update_now=False,
                )

                if is_current_feed_view(current_token):
                    update_page()

            except Exception as ex:
                data_loaded["done"] = False
                print("feed initial load error:", ex)

                if is_current_feed_view(current_token):
                    set_status("資料同步失敗", theme="red", update_now=False)
                    refresh_submit_button(update_now=False)
                    update_page()

        threading.Thread(target=_run, daemon=True).start()

    # 初始 UI：先用空資料渲染，避免 Supabase 查詢阻塞主 UI thread。
    rebuild_mode_cards(update_now=False)
    refresh_recent_panel(update_now=False)
    refresh_dryer_status_panel(update_now=False)
    refresh_form_by_mode(update_now=False)
    set_status("資料同步中", loading=True, update_now=False)
    load_initial_data_once()

    # =====================================================
    # 15. 最終畫面
    # =====================================================
    root = ft.Column(
        controls=[
            header,
            dryer_memo_panel,
            mode_cards_row,
            main_grid,
            ft.Container(height=90),
        ],
        spacing=18,
    )

    # 目前以 token + session + route 三重檢查避免舊 thread 更新。
    # 若未來 main.py / shell 增加顯式離頁 hook，可在切離 /feed 時把 is_alive["value"] 設為 False。
    root.data = {"view": "feed", "token": str(id(view_token))}
    return root
