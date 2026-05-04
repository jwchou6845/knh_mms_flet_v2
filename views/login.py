# views/login.py
# KNH MMS Login - Supabase 版（Flet 0.84）
import json
from datetime import datetime, timedelta, timezone

import flet as ft

from services.auth_service import (
    authenticate_user,
    save_user_last_login,
    change_password_first_login,
    submit_password_reset_request,
    hash_password,
)


LOGIN_SESSION_KEY = "knh_login_session"
REMEMBER_EMPLOYEE_KEY = "knh_employee_id"


def LoginView(page: ft.Page):
    # =====================================================
    # Assets
    # =====================================================
    # VM / Web 部署：main.py 使用 assets_dir="."。
    # 因此圖片路徑統一使用 assets/...，與其他頁面 dryer icon 路徑一致。
    ASSET_LOGO = "assets/logo.png"
    ASSET_BG = "assets/login_bg.png"

    # =====================================================
    # 色彩設定
    # =====================================================
    BG = "#F8FBFF"
    CARD = "#FFFFFF"

    TEXT_MAIN = "#0F2A44"
    TEXT_SUB = "#64748B"

    MUTED_BLUE = "#5E86B8"
    MUTED_BLUE_DARK = "#4F75A3"
    MUTED_BLUE_PRESS = "#3F638E"

    BORDER = "#94A3B8"
    FOCUS_BLUE = "#2563EB"
    INPUT_BG = "#FFFFFF"

    ERROR = "#DC2626"
    SUCCESS = "#059669"

    if not hasattr(page, "session_data"):
        page.session_data = {}

    # =====================================================
    # 響應式尺寸判斷
    # =====================================================
    page_w = page.width or 430
    page_h = page.height or 820

    is_mobile = page_w <= 520
    is_short = page_h <= 740

    canvas_width = min(430, page_w) if is_mobile else 430
    canvas_height = page_h

    horizontal_padding = 18 if is_mobile else 20
    card_width = canvas_width - (horizontal_padding * 2)

    logo_size = 78 if is_short else 88
    title_size = 25 if is_short else 28
    subtitle_size = 17 if is_short else 20

    top_padding = 22 if is_short else 34
    header_gap = 12 if is_short else 18
    card_padding_y = 20 if is_short else 24

    # =====================================================
    # 工具函式
    # =====================================================
    def safe_update(control):
        try:
            control.update()
        except Exception:
            pass

    def show_snack(message: str, color: str = MUTED_BLUE):
        snack = ft.SnackBar(
            content=ft.Text(
                message,
                color="white",
                weight=ft.FontWeight.W_500,
            ),
            bgcolor=color,
            duration=3000,
        )
        page.overlay.append(snack)
        snack.open = True
        page.update()

    def get_client_value(key: str, default=""):
        try:
            value = page.client_storage.get(key)
            return value if value is not None else default
        except Exception:
            return default

    def set_client_value(key: str, value):
        try:
            page.client_storage.set(key, value)
        except Exception:
            pass

    def remove_client_value(key: str):
        try:
            page.client_storage.remove(key)
        except Exception:
            pass

    def save_persistent_login_session(user: dict):
        expires_at = datetime.now(timezone.utc) + timedelta(hours=12)

        payload = {
            "user_id": str(user.get("id", "")).strip(),
            "employee_id": str(user.get("employee_id", "")).strip(),
            "user_name": str(user.get("name", "")).strip(),
            "role": user.get("role", "操作員"),
            "shift": user.get("shift", "") or "",
            "can_view_all_tasks": bool(user.get("can_view_all_tasks", False)),
            "can_access_reports": bool(user.get("can_access_reports", False)),
            "can_access_spinneret": bool(user.get("can_access_spinneret", False)),
            "can_access_maintenance": bool(user.get("can_access_maintenance", False)),
            "quick_shortcuts": user.get("quick_shortcuts") or [],
            "expires_at": expires_at.isoformat(),
        }

        # 只保存登入狀態與權限，不保存 password / password_hash。
        set_client_value(LOGIN_SESSION_KEY, json.dumps(payload, ensure_ascii=False))

    def save_login_session(user: dict):
        user_id = str(user.get("id", "")).strip()
        employee_id = str(user.get("employee_id", "")).strip()
        user_name = str(user.get("name", "")).strip()

        page.session_data["is_logged_in"] = True
        page.session_data["user_id"] = user_id
        page.session_data["user_record_id"] = user_id
        page.session_data["employee_id"] = employee_id
        page.session_data["user_name"] = user_name if user_name else employee_id
        page.session_data["role"] = user.get("role", "操作員")
        page.session_data["shift"] = user.get("shift", "") or ""
        page.session_data["can_view_all_tasks"] = bool(user.get("can_view_all_tasks", False))
        page.session_data["can_access_reports"] = bool(user.get("can_access_reports", False))
        page.session_data["can_access_spinneret"] = bool(user.get("can_access_spinneret", False))
        page.session_data["can_access_maintenance"] = bool(user.get("can_access_maintenance", False))
        page.session_data["quick_shortcuts"] = user.get("quick_shortcuts") or []

        save_persistent_login_session(user)

    # =====================================================
    # 共用 UI 元件
    # =====================================================
    def label_row(icon_name, label):
        return ft.Row(
            controls=[
                ft.Icon(icon_name, size=19, color=TEXT_MAIN),
                ft.Text(
                    label,
                    size=15,
                    color=TEXT_MAIN,
                    weight=ft.FontWeight.BOLD,
                ),
            ],
            spacing=9,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def input_field(hint, icon_name, password=False):
        return ft.TextField(
            hint_text=hint,
            prefix_icon=icon_name,
            password=password,
            can_reveal_password=password,
            border_radius=12,
            border_color=BORDER,
            focused_border_color=FOCUS_BLUE,
            filled=True,
            bgcolor=INPUT_BG,
            height=52,
            text_size=15,
            content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
        )

    def primary_button(label, icon_name, on_click):
        return ft.ElevatedButton(
            text=label,
            icon=icon_name,
            height=56,
            bgcolor=MUTED_BLUE,
            color="white",
            on_click=on_click,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                elevation=0,
                text_style=ft.TextStyle(size=17, weight=ft.FontWeight.BOLD),
            ),
        )

    def secondary_button(label, icon_name, on_click):
        return ft.OutlinedButton(
            text=label,
            icon=icon_name,
            height=52,
            on_click=on_click,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                side=ft.BorderSide(1, "#2563A9"),
                text_style=ft.TextStyle(size=15, weight=ft.FontWeight.W_600),
            ),
        )

    # =====================================================
    # 登入欄位
    # =====================================================
    remembered_employee_id = get_client_value(REMEMBER_EMPLOYEE_KEY, "")

    employee_field = input_field(
        hint="請輸入員工編號",
        icon_name=ft.Icons.PERSON_OUTLINE,
    )
    employee_field.value = remembered_employee_id

    password_field = input_field(
        hint="請輸入密碼",
        icon_name=ft.Icons.LOCK_OUTLINE,
        password=True,
    )

    remember_checkbox = ft.Checkbox(
        label="記住員工編號",
        value=bool(remembered_employee_id),
        label_style=ft.TextStyle(
            size=15,
            color=TEXT_MAIN,
        ),
    )

    error_text = ft.Text(
        "",
        size=13,
        color=ERROR,
        visible=False,
        weight=ft.FontWeight.W_500,
    )

    # =====================================================
    # 登入按鈕：Hover / Press / Loading
    # =====================================================
    login_state = {
        "loading": False,
        "hover": False,
        "pressed": False,
    }

    login_icon = ft.Icon(
        ft.Icons.LOGIN,
        size=20,
        color="white",
    )

    login_btn_text = ft.Text(
        "登入系統",
        size=17,
        color="white",
        weight=ft.FontWeight.BOLD,
    )

    login_loading = ft.ProgressRing(
        width=20,
        height=20,
        stroke_width=2.4,
        color="white",
        visible=False,
    )

    login_btn_inner = ft.Row(
        controls=[
            login_icon,
            login_btn_text,
            login_loading,
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=10,
    )

    login_btn_box = ft.Container(
        height=56,
        border_radius=12,
        bgcolor=MUTED_BLUE,
        alignment=ft.Alignment(0, 0),
        content=login_btn_inner,
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=12,
            color="#16000000",
            offset=ft.Offset(0, 5),
        ),
    )

    def refresh_login_button():
        if login_state["loading"]:
            login_btn_box.bgcolor = "#94A3B8"
            login_btn_box.opacity = 0.92
            login_icon.visible = False
            login_btn_text.value = "驗證中..."
            login_loading.visible = True
        else:
            login_btn_box.opacity = 1
            login_icon.visible = True
            login_btn_text.value = "登入系統"
            login_loading.visible = False

            if login_state["pressed"]:
                login_btn_box.bgcolor = MUTED_BLUE_PRESS
            elif login_state["hover"]:
                login_btn_box.bgcolor = MUTED_BLUE_DARK
            else:
                login_btn_box.bgcolor = MUTED_BLUE

        safe_update(login_btn_box)

    def login_hover(e):
        if login_state["loading"]:
            return

        login_state["hover"] = e.data == "true"
        refresh_login_button()

    def login_tap_down(e):
        if login_state["loading"]:
            return

        login_state["pressed"] = True
        refresh_login_button()

    def login_tap_cancel(e):
        if login_state["loading"]:
            return

        login_state["pressed"] = False
        refresh_login_button()

    # =====================================================
    # 登入邏輯
    # =====================================================
    def set_login_loading(is_loading: bool):
        login_state["loading"] = is_loading
        login_state["pressed"] = False

        employee_field.disabled = is_loading
        password_field.disabled = is_loading
        remember_checkbox.disabled = is_loading

        refresh_login_button()

        safe_update(employee_field)
        safe_update(password_field)
        safe_update(remember_checkbox)

        page.update()

    def show_error(message: str):
        error_text.value = message
        error_text.visible = True
        safe_update(error_text)
        page.update()

    def clear_error():
        error_text.value = ""
        error_text.visible = False
        safe_update(error_text)

    def do_login(e):
        print("LOGIN CLICKED")

        if login_state["loading"]:
            print("LOGIN IGNORED: already loading")
            return

        login_state["pressed"] = False
        clear_error()

        employee_id = (employee_field.value or "").strip()
        password = (password_field.value or "").strip()

        print(f"LOGIN INPUT: employee_id={employee_id!r}, password_len={len(password)}")

        if not employee_id:
            show_error("請輸入員工編號。")
            return

        if not password:
            show_error("請輸入密碼。")
            return

        navigated = False
        set_login_loading(True)

        try:
            print("LOGIN STEP 1: authenticate_user start")
            result = authenticate_user(employee_id, password)
            print("LOGIN STEP 2: authenticate_user done", result.ok, result.message)

            if not result.ok:
                show_error(result.message)
                return

            user = result.data or {}
            stored_hash = str(user.get("password_hash") or "").strip()

            if remember_checkbox.value:
                set_client_value(REMEMBER_EMPLOYEE_KEY, employee_id)
            else:
                remove_client_value(REMEMBER_EMPLOYEE_KEY)

            if user.get("must_change_password", False):
                print("LOGIN STEP 3: must_change_password")
                show_change_password(user, current_hash=stored_hash)
                return

            print("LOGIN STEP 4: save session")
            save_login_session(user)

            print("LOGIN STEP 5: save last login")
            last_login_result = save_user_last_login(user.get("id", ""))
            if not last_login_result.ok:
                print("更新最近登入時間失敗:", last_login_result.message)

            print("LOGIN STEP 6: navigate('/')")
            navigated = True

            nav = None
            try:
                nav = page.session_data.get("_navigate")
            except Exception:
                nav = None

            if callable(nav):
                nav("/")
            else:
                page.go("/")
                try:
                    page.update()
                except Exception:
                    pass

        except Exception as ex:
            show_error(f"登入失敗：{ex}")
            print("LOGIN ERROR:", repr(ex))

        finally:
            # 手機 / Web 模式若中途出錯，避免永遠停在「驗證中」
            if not navigated:
                print("LOGIN FINALLY: reset loading")
                try:
                    set_login_loading(False)
                except Exception as ex:
                    print("LOGIN FINALLY reset error:", repr(ex))

    # VM / 手機 Web 模式：使用 on_click 比 GestureDetector.on_tap_up 穩定。
    login_button = ft.Container(
        content=login_btn_box,
        on_click=do_login,
        on_hover=login_hover,
    )

    # =====================================================
    # 忘記密碼申請 Dialog
    # =====================================================
    reset_employee = input_field("請輸入員工編號", ft.Icons.BADGE_OUTLINED)
    reset_name = input_field("請輸入姓名", ft.Icons.PERSON_OUTLINE)
    reset_contact = input_field("手機 / 分機 / Line", ft.Icons.PHONE_OUTLINED)

    reset_reason = ft.TextField(
        value="忘記密碼，申請管理員協助重設。",
        multiline=True,
        min_lines=2,
        max_lines=3,
        border_radius=12,
        border_color=BORDER,
        focused_border_color=FOCUS_BLUE,
        filled=True,
        bgcolor=INPUT_BG,
        text_size=14,
    )

    def dialog_field(label, control):
        return ft.Column(
            tight=True,
            spacing=5,
            controls=[
                ft.Text(
                    label,
                    size=13,
                    color=TEXT_MAIN,
                    weight=ft.FontWeight.W_600,
                ),
                control,
            ],
        )

    def close_reset_dialog(e=None):
        reset_dialog.open = False
        page.update()

    def submit_reset_request(e):
        emp = (reset_employee.value or "").strip()
        name = (reset_name.value or "").strip()
        contact = (reset_contact.value or "").strip()
        reason = (reset_reason.value or "").strip()

        if not emp:
            show_snack("請填寫員工編號。", ERROR)
            return

        if not name:
            show_snack("請填寫員工姓名。", ERROR)
            return

        try:
            result = submit_password_reset_request(
                employee_id=emp,
                name=name,
                contact=contact,
                reason=reason,
            )

            if not result.ok:
                show_snack(result.message, ERROR)
                return

            close_reset_dialog()
            show_snack(result.message, SUCCESS)

        except Exception as ex:
            show_snack(f"送出失敗：{ex}", ERROR)
            print("reset request error:", ex)

    reset_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(
            "密碼重設申請",
            weight=ft.FontWeight.BOLD,
        ),
        content=ft.Container(
            width=min(360, card_width),
            content=ft.Column(
                controls=[
                    ft.Text(
                        "送出後會寫入資料庫「密碼重設申請表」，管理員確認後再協助重設。",
                        size=13,
                        color=TEXT_SUB,
                    ),
                    ft.Container(height=8),
                    dialog_field("員工編號", reset_employee),
                    dialog_field("員工姓名", reset_name),
                    dialog_field("聯絡方式", reset_contact),
                    dialog_field("申請原因", reset_reason),
                ],
                spacing=10,
                tight=True,
            ),
        ),
        actions=[
            ft.TextButton("取消", on_click=close_reset_dialog),
            ft.ElevatedButton(
                text="送出申請",
                icon=ft.Icons.SEND_OUTLINED,
                bgcolor=FOCUS_BLUE,
                color="white",
                on_click=submit_reset_request,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=10),
                ),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def open_reset_dialog(e):
        reset_employee.value = employee_field.value or ""
        reset_name.value = ""
        reset_contact.value = ""
        reset_reason.value = "忘記密碼，申請管理員協助重設。"

        if reset_dialog not in page.overlay:
            page.overlay.append(reset_dialog)

        reset_dialog.open = True
        page.update()

    # =====================================================
    # 登入卡片
    # =====================================================
    login_card = ft.Container(
        width=card_width,
        bgcolor=CARD,
        border_radius=24,
        padding=ft.padding.symmetric(
            horizontal=24,
            vertical=card_padding_y,
        ),
        border=ft.border.all(1, "#E5EDF7"),
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=28,
            color="#14000000",
            offset=ft.Offset(0, 10),
        ),
        content=ft.Column(
            controls=[
                label_row(ft.Icons.PERSON_OUTLINE, "員工編號"),
                employee_field,
                ft.Container(height=4),
                label_row(ft.Icons.LOCK_OUTLINE, "密碼"),
                password_field,
                remember_checkbox,
                ft.Container(
                    content=error_text,
                    alignment=ft.Alignment(-1, 0),
                ),
                login_button,
                secondary_button(
                    "聯絡管理員 / 忘記密碼",
                    ft.Icons.HEADSET_MIC_OUTLINED,
                    open_reset_dialog,
                ),
            ],
            spacing=10 if is_short else 11,
        ),
    )

    # =====================================================
    # Header / Footer
    # =====================================================
    def build_header():
        return ft.Column(
            controls=[
                ft.Container(
                    width=logo_size,
                    height=logo_size,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Image(
                        src=ASSET_LOGO,
                        width=logo_size,
                        height=logo_size,
                        fit=ft.BoxFit.CONTAIN,
                    ),
                ),
                ft.Text(
                    "KNH Spunbond MMS",
                    size=title_size,
                    weight=ft.FontWeight.BOLD,
                    color=TEXT_MAIN,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "紡黏原料管理系統",
                    size=subtitle_size,
                    weight=ft.FontWeight.W_500,
                    color=TEXT_MAIN,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(
                    height=34,
                    padding=ft.padding.symmetric(horizontal=17),
                    border_radius=18,
                    bgcolor="#F3F8FF",
                    border=ft.border.all(1, "#DCEAF8"),
                    content=ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.VERIFIED_USER_OUTLINED,
                                size=16,
                                color="#3F72A8",
                            ),
                            ft.Text(
                                "內部系統 / 員工編號驗證登入",
                                size=14,
                                color="#3F72A8",
                                weight=ft.FontWeight.W_600,
                            ),
                        ],
                        spacing=7,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
        )

    def build_footer():
        return ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.INFO_OUTLINE,
                    size=16,
                    color="#2563A9",
                ),
                ft.Text(
                    "首次登入請使用預設密碼，登入後請盡快修改密碼",
                    size=12,
                    color="#2563A9",
                    weight=ft.FontWeight.W_500,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=6,
        )

    # =====================================================
    # 頁面內容組合
    # =====================================================
    content_holder = ft.Container()

    def build_page_content(main_card, footer_visible=True):
        return ft.Container(
            expand=True,
            padding=ft.padding.only(
                left=horizontal_padding,
                right=horizontal_padding,
                top=top_padding,
                bottom=18,
            ),
            content=ft.Column(
                controls=[
                    build_header(),
                    ft.Container(height=header_gap),
                    main_card,
                    ft.Container(expand=True),
                    build_footer() if footer_visible else ft.Container(height=1),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    # =====================================================
    # 首次登入修改密碼畫面
    # =====================================================
    def show_change_password(user: dict, current_hash: str):
        new_password = input_field(
            "請輸入新密碼",
            ft.Icons.LOCK_RESET_OUTLINED,
            password=True,
        )

        confirm_password = input_field(
            "請再次輸入新密碼",
            ft.Icons.LOCK_OUTLINE,
            password=True,
        )

        change_error = ft.Text(
            "",
            size=13,
            color=ERROR,
            visible=False,
            weight=ft.FontWeight.W_500,
        )

        def set_change_error(message: str):
            change_error.value = message
            change_error.visible = True
            safe_update(change_error)
            page.update()

        def confirm_change(e):
            pwd1 = (new_password.value or "").strip()
            pwd2 = (confirm_password.value or "").strip()

            change_error.visible = False

            if len(pwd1) < 6:
                set_change_error("新密碼至少需要 6 碼。")
                return

            if pwd1 != pwd2:
                set_change_error("兩次輸入的新密碼不一致。")
                return

            new_hash = hash_password(pwd1)

            if new_hash == current_hash:
                set_change_error("新密碼不可與預設密碼相同。")
                return

            try:
                result = change_password_first_login(
                    user_id=user.get("id", ""),
                    current_hash=current_hash,
                    new_password=pwd1,
                    confirm_password=pwd2,
                )

                if not result.ok:
                    set_change_error(result.message)
                    return

                updated_user = result.data or user
                save_login_session(updated_user)

                last_login_result = save_user_last_login(updated_user.get("id", ""))
                if not last_login_result.ok:
                    print("更新最近登入時間失敗:", last_login_result.message)

                show_snack(result.message, SUCCESS)

                nav = None
                try:
                    nav = page.session_data.get("_navigate")
                except Exception:
                    nav = None

                if callable(nav):
                    nav("/")
                else:
                    page.go("/")

            except Exception as ex:
                set_change_error(f"密碼修改失敗：{ex}")
                print("change password error:", ex)

        change_card = ft.Container(
            width=card_width,
            bgcolor=CARD,
            border_radius=24,
            padding=ft.padding.symmetric(
                horizontal=24,
                vertical=26,
            ),
            border=ft.border.all(1, "#E5EDF7"),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=28,
                color="#14000000",
                offset=ft.Offset(0, 10),
            ),
            content=ft.Column(
                controls=[
                    ft.Icon(
                        ft.Icons.LOCK_RESET_OUTLINED,
                        size=42,
                        color=MUTED_BLUE,
                    ),
                    ft.Text(
                        "首次登入請修改密碼",
                        size=22,
                        weight=ft.FontWeight.BOLD,
                        color=TEXT_MAIN,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        "為保障系統安全，請先設定個人密碼。",
                        size=13,
                        color=TEXT_SUB,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=10),
                    new_password,
                    confirm_password,
                    ft.Container(
                        content=change_error,
                        alignment=ft.Alignment(-1, 0),
                    ),
                    primary_button(
                        "確認修改並登入",
                        ft.Icons.CHECK_CIRCLE_OUTLINE,
                        confirm_change,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
        )

        content_holder.content = build_page_content(
            change_card,
            footer_visible=False,
        )

        page.update()

    content_holder.content = build_page_content(
        login_card,
        footer_visible=True,
    )

    # =====================================================
    # 背景與表單鎖定畫布
    # =====================================================
    locked_canvas = ft.Container(
        width=canvas_width,
        height=canvas_height,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Stack(
            expand=True,
            controls=[
                ft.Image(
                    src=ASSET_BG,
                    width=canvas_width,
                    height=canvas_height,
                    fit=ft.BoxFit.COVER,
                ),
                content_holder,
            ],
        ),
    )

    return ft.View(
        route="/login",
        padding=0,
        bgcolor=BG,
        controls=[
            ft.Container(
                expand=True,
                bgcolor=BG,
                alignment=ft.Alignment(0, 0),
                content=locked_canvas,
            )
        ],
    )