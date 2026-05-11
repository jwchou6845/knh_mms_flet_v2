# views/login.py
# KNH MMS Login - Supabase 版（Flet 0.84）
import flet as ft
import json
import threading

from services.auth_service import (
    authenticate_user,
    save_user_last_login,
    change_password_first_login,
    submit_password_reset_request,
    hash_password,
)
from services.auth_session_service import create_persistent_session


REMEMBER_EMPLOYEE_KEY = "knh_employee_id"
SESSION_TOKEN_KEY = "knh_session_token"


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

    # 手機版改用完整可視寬度，避免將表單鎖死在初次回報的固定畫布高度內。
    # 桌機版仍保留 430px 的視覺畫布，維持原本背景與表單鎖定的設計。
    canvas_width = page_w if is_mobile else 430
    canvas_height = None if is_mobile else page_h

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
        try:
            page.session_data[key] = value
        except Exception:
            pass

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
        try:
            page.session_data.pop(key, None)
        except Exception:
            pass

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

    def get_client_value(key: str, default=""):
        try:
            return page.session_data.get(key, default)
        except Exception:
            return default

    def set_client_value(key: str, value):
        browser_storage_set(key, str(value or ""))

    def remove_client_value(key: str):
        browser_storage_remove(key)

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

    def create_and_store_persistent_session(user: dict):
        try:
            result = create_persistent_session(
                user,
                user_agent=str(getattr(page, "client_user_agent", "") or ""),
                ip_address=str(getattr(page, "client_ip", "") or ""),
            )

            if not result.ok:
                print("create persistent session failed:", result.message)
                return

            data = result.data or {}
            token = str(data.get("session_token") or "").strip()
            if not token:
                print("create persistent session failed: no token")
                return

            page.session_data["session_token"] = token
            browser_storage_set(SESSION_TOKEN_KEY, token)
            print("PERSISTENT SESSION CREATED")

        except Exception as ex:
            print("create persistent session error:", repr(ex))


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

    def _button_content(label, icon_name, text_color, text_size=16, icon_size=20):
        return ft.Row(
            controls=[
                ft.Icon(icon_name, size=icon_size, color=text_color),
                ft.Text(
                    label,
                    size=text_size,
                    color=text_color,
                    weight=ft.FontWeight.BOLD,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=9,
            tight=True,
        )

    def stable_filled_button(
        label,
        icon_name,
        on_click,
        bg=None,
        fg="#FFFFFF",
        height=56,
        expand=False,
    ):
        btn = ft.Container(
            height=height,
            expand=expand,
            border_radius=12,
            bgcolor=bg or MUTED_BLUE,
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.symmetric(horizontal=14),
            ink=True,
            content=_button_content(label, icon_name, fg),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=12,
                color="#12000000",
                offset=ft.Offset(0, 4),
            ),
        )
        btn.disabled = False
        btn.data = {
            "label": label,
            "icon": icon_name,
            "bg": bg or MUTED_BLUE,
            "fg": fg,
            "height": height,
            "variant": "filled",
        }

        def handle_click(e):
            if getattr(btn, "disabled", False):
                return
            if callable(on_click):
                on_click(e)

        btn.on_click = handle_click
        return btn

    def stable_outline_button(
        label,
        icon_name,
        on_click,
        fg="#2563A9",
        border_color="#B0D0FF",
        height=52,
        expand=False,
    ):
        btn = ft.Container(
            height=height,
            expand=expand,
            border_radius=12,
            bgcolor="#FFFFFF",
            border=ft.border.all(1, border_color),
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.symmetric(horizontal=14),
            ink=True,
            content=_button_content(label, icon_name, fg, text_size=15, icon_size=19),
        )
        btn.disabled = False
        btn.data = {
            "label": label,
            "icon": icon_name,
            "bg": "#FFFFFF",
            "fg": fg,
            "border": border_color,
            "height": height,
            "variant": "outline",
        }

        def handle_click(e):
            if getattr(btn, "disabled", False):
                return
            if callable(on_click):
                on_click(e)

        btn.on_click = handle_click
        return btn

    def set_stable_button_loading(button, label="處理中...", fg="#FFFFFF"):
        button.disabled = True
        button.opacity = 0.86
        if isinstance(getattr(button, "data", None), dict):
            button.bgcolor = "#94A3B8" if button.data.get("variant") == "filled" else "#F1F5F9"
        button.content = ft.Row(
            controls=[
                ft.ProgressRing(width=18, height=18, stroke_width=2.4, color=fg),
                ft.Text(label, size=15, color=fg, weight=ft.FontWeight.BOLD),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=9,
            tight=True,
        )
        try:
            button.update()
        except Exception:
            page.update()

    def set_stable_button_normal(button):
        data = button.data if isinstance(getattr(button, "data", None), dict) else {}
        button.disabled = False
        button.opacity = 1
        button.bgcolor = data.get("bg", MUTED_BLUE)
        if data.get("variant") == "outline":
            button.border = ft.border.all(1, data.get("border", "#B0D0FF"))
        button.content = _button_content(
            data.get("label", "確認"),
            data.get("icon", ft.Icons.CHECK_CIRCLE_OUTLINE),
            data.get("fg", "#FFFFFF"),
            text_size=15 if data.get("variant") == "outline" else 16,
            icon_size=19 if data.get("variant") == "outline" else 20,
        )
        try:
            button.update()
        except Exception:
            page.update()

    def field_group(label, control, icon_name=None, required=False):
        return ft.Column(
            tight=True,
            spacing=7,
            controls=[
                label_row(icon_name or ft.Icons.EDIT_OUTLINED, label + (" *" if required else "")),
                control,
            ],
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
            create_and_store_persistent_session(user)

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
        hint_text="請說明申請原因",
        multiline=True,
        min_lines=2,
        max_lines=3,
        border_radius=12,
        border_color=BORDER,
        focused_border_color=FOCUS_BLUE,
        filled=True,
        bgcolor=INPUT_BG,
        text_size=14,
        content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
    )

    reset_state = {"submitting": False}
    reset_dialog = None
    reset_submit_btn = None

    def dialog_field(label, control, icon_name):
        return field_group(label, control, icon_name, required=True if label in ["員工編號", "員工姓名"] else False)

    def close_reset_dialog(e=None):
        nonlocal reset_dialog
        if reset_dialog:
            reset_dialog.open = False
            page.update()

    def submit_reset_request(e=None):
        nonlocal reset_submit_btn
        if reset_state["submitting"]:
            return

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

        reset_state["submitting"] = True
        if reset_submit_btn:
            set_stable_button_loading(reset_submit_btn, "送出中...")

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

        finally:
            reset_state["submitting"] = False
            if reset_submit_btn:
                set_stable_button_normal(reset_submit_btn)

    reset_submit_btn = stable_filled_button(
        "送出申請",
        ft.Icons.SEND_OUTLINED,
        submit_reset_request,
        bg=FOCUS_BLUE,
        height=50,
        expand=True,
    )

    reset_cancel_btn = stable_outline_button(
        "取消",
        ft.Icons.CLOSE,
        close_reset_dialog,
        height=50,
        expand=True,
    )

    # 手機版為 Dialog 內容保留明確可捲動高度，避免小螢幕時欄位標題被壓縮或裁掉。
    reset_dialog_content_height = min(520, max(360, page_h - 150)) if is_mobile else None

    reset_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(
            "密碼重設申請",
            weight=ft.FontWeight.BOLD,
            color=TEXT_MAIN,
        ),
        content=ft.Container(
            width=min(380, card_width),
            height=reset_dialog_content_height,
            content=ft.Column(
                controls=[
                    ft.Text(
                        "送出後會寫入資料庫「密碼重設申請表」，管理員確認後再協助重設。",
                        size=13,
                        color=TEXT_SUB,
                    ),
                    ft.Container(height=4),
                    dialog_field("員工編號", reset_employee, ft.Icons.BADGE_OUTLINED),
                    dialog_field("員工姓名", reset_name, ft.Icons.PERSON_OUTLINE),
                    dialog_field("聯絡方式", reset_contact, ft.Icons.PHONE_OUTLINED),
                    field_group("申請原因", reset_reason, ft.Icons.NOTES_OUTLINED),
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.Container(expand=True, content=reset_cancel_btn),
                            ft.Container(expand=True, content=reset_submit_btn),
                        ],
                    ),
                ],
                spacing=11,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def open_reset_dialog(e=None):
        reset_employee.value = employee_field.value or ""
        reset_name.value = ""
        reset_contact.value = ""
        reset_reason.value = "忘記密碼，申請管理員協助重設。"
        reset_state["submitting"] = False
        set_stable_button_normal(reset_submit_btn)

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
                stable_outline_button(
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
    # 手機 Web 兼容性重點：
    # 1. content_holder 明確撐滿 Stack，不讓瀏覽器 / 版面引擎自行猜測內容層尺寸。
    # 2. 手機版不再用 expand spacer 把 footer 強推到底，改成自然流式排列，
    #    讓小螢幕、系統字級放大、Chrome 可視高度變化時仍可捲動看到表單。
    # 3. SafeArea 避開瀏海、狀態列與系統侵入區。
    content_holder = ft.Container(expand=True)

    def build_page_content(main_card, footer_visible=True):
        page_controls = [
            build_header(),
            ft.Container(height=header_gap),
            main_card,
        ]

        if is_mobile:
            page_controls.append(ft.Container(height=18 if footer_visible else 1))
        else:
            page_controls.append(ft.Container(expand=True))

        page_controls.append(
            build_footer() if footer_visible else ft.Container(height=1)
        )

        return ft.SafeArea(
            expand=True,
            content=ft.Container(
                expand=True,
                padding=ft.padding.only(
                    left=horizontal_padding,
                    right=horizontal_padding,
                    top=top_padding,
                    bottom=18,
                ),
                content=ft.Column(
                    controls=page_controls,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=0,
                    scroll=ft.ScrollMode.AUTO,
                ),
            ),
        )

    # =====================================================
    # 首次登入修改密碼畫面
    # =====================================================
    def show_change_password(user: dict, current_hash: str):
        new_password = input_field(
            "至少 6 碼，請勿使用預設密碼",
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

        change_state = {"submitting": False}

        def set_change_error(message: str):
            change_error.value = message
            change_error.visible = True
            page.update()

        def clear_change_error():
            change_error.value = ""
            change_error.visible = False

        def back_to_login(e=None):
            change_state["submitting"] = False
            password_field.value = ""
            content_holder.content = build_page_content(
                login_card,
                footer_visible=True,
            )
            set_login_loading(False)
            page.update()

        def confirm_change(e=None):
            if change_state["submitting"]:
                return

            pwd1 = (new_password.value or "").strip()
            pwd2 = (confirm_password.value or "").strip()

            clear_change_error()

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

            change_state["submitting"] = True
            set_stable_button_loading(change_submit_btn, "更新中...")
            change_back_btn.disabled = True
            change_back_btn.opacity = 0.55
            page.update()

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
                create_and_store_persistent_session(updated_user)

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

            finally:
                change_state["submitting"] = False
                set_stable_button_normal(change_submit_btn)
                change_back_btn.disabled = False
                change_back_btn.opacity = 1
                try:
                    page.update()
                except Exception:
                    pass

        change_submit_btn = stable_filled_button(
            "確認修改並登入",
            ft.Icons.CHECK_CIRCLE_OUTLINE,
            confirm_change,
            bg=MUTED_BLUE,
            height=56,
            expand=True,
        )

        change_back_btn = stable_outline_button(
            "返回登入",
            ft.Icons.ARROW_BACK,
            back_to_login,
            height=52,
            expand=True,
        )

        change_card = ft.Container(
            width=card_width,
            bgcolor=CARD,
            border_radius=24,
            padding=ft.padding.symmetric(
                horizontal=24,
                vertical=24 if is_short else 28,
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
                    ft.Container(height=8),
                    field_group("新密碼", new_password, ft.Icons.LOCK_RESET_OUTLINED, required=True),
                    field_group("再次輸入新密碼", confirm_password, ft.Icons.LOCK_OUTLINE, required=True),
                    ft.Container(
                        content=change_error,
                        alignment=ft.Alignment(-1, 0),
                    ),
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.Container(expand=True, content=change_back_btn),
                            ft.Container(expand=True, content=change_submit_btn),
                        ],
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

    def load_remembered_employee_from_browser():
        def on_loaded(value):
            employee_id = _normalize_storage_value(value)
            if not employee_id:
                return

            if not (employee_field.value or "").strip():
                employee_field.value = employee_id
            remember_checkbox.value = True
            try:
                employee_field.update()
                remember_checkbox.update()
            except Exception:
                try:
                    page.update()
                except Exception:
                    pass

        browser_storage_get(REMEMBER_EMPLOYEE_KEY, on_loaded)

    try:
        threading.Timer(0.35, load_remembered_employee_from_browser).start()
    except Exception:
        pass

    # =====================================================
    # 背景與表單畫布
    # =====================================================
    # 背景圖只保留為裝飾層；即使圖片載入失敗，也先用純色背景保底，
    # 不讓登入表單的顯示依賴背景圖是否成功。
    background_layer = ft.Container(
        expand=True,
        bgcolor=BG,
        content=ft.Image(
            src=ASSET_BG,
            fit=ft.BoxFit.COVER,
            expand=True,
            error_content=ft.Container(
                expand=True,
                bgcolor=BG,
            ),
        ),
    )

    if is_mobile:
        # 手機版：不使用固定高度與 HARD_EDGE 裁切，
        # 讓內容層跟著實際可視區撐滿，表單不足時由內層 Column 負責捲動。
        locked_canvas = ft.Container(
            expand=True,
            width=canvas_width,
            bgcolor=BG,
            content=ft.Stack(
                expand=True,
                fit=ft.StackFit.EXPAND,
                controls=[
                    background_layer,
                    content_holder,
                ],
            ),
        )
    else:
        # 桌機版：保留原本 430px 的鎖定式視覺畫布，
        # 但明確指定 StackFit.EXPAND，避免內容層尺寸判斷不穩。
        locked_canvas = ft.Container(
            width=canvas_width,
            height=canvas_height,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Stack(
                expand=True,
                fit=ft.StackFit.EXPAND,
                controls=[
                    background_layer,
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