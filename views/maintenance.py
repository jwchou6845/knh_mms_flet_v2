# 第一階段完成，可進入其他頁面/已轉 Supabase
# 第二階段優化方向
# 1. 已刪除紀錄查詢 / 還原
# 2. 刪除原因手動輸入
# 3. 項目排序管理
# 4. 異常追蹤頁
# 5. 查看紀錄分頁
# 6. 保養項目搜尋
# 7. 依權限限制新增 / 編輯項目

import flet as ft
import threading
import time
from datetime import date

from services.maintenance_service import (
    load_maintenance_page_data,
    submit_maintenance_record,
    create_cleaning_item,
    create_consumable_item,
    update_item_cycle,
    load_item_records,
    delete_maintenance_record,
)


# ============================================================
# KNH MMS - 機台保養紀錄 maintenance.py v2.6 record history and super admin soft delete
# Flet 0.84 + Python + Supabase
# ============================================================


# =========================
# 色彩設定：低飽和、專業風格
# =========================

BG = "#F6F8FB"
CARD_BG = "#FFFFFF"
TEXT = "#1E293B"
TEXT_MUTED = "#64748B"
BORDER = "#E2E8F0"

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

GREEN = "#2E7D32"
GREEN_SOFT = "#E8F5E9"

RED = "#DC2626"
RED_SOFT = "#FEE2E2"

YELLOW = "#D97706"
YELLOW_SOFT = "#FEF3C7"

DISABLED = "#94A3B8"

MOBILE_WIDTH = 980


# =========================
# 通用樣式
# =========================

def primary_button_style(
    bg: str = BLUE_BTN,
    hover: str = BLUE_BTN_HOVER,
    pressed: str = BLUE_BTN_PRESS,
) -> ft.ButtonStyle:
    return ft.ButtonStyle(
        bgcolor={
            ft.ControlState.DEFAULT: bg,
            ft.ControlState.HOVERED: hover,
            ft.ControlState.PRESSED: pressed,
            ft.ControlState.DISABLED: DISABLED,
        },
        color={
            ft.ControlState.DEFAULT: "#FFFFFF",
            ft.ControlState.HOVERED: "#FFFFFF",
            ft.ControlState.PRESSED: "#FFFFFF",
            ft.ControlState.DISABLED: "#FFFFFF",
        },
        shape=ft.RoundedRectangleBorder(radius=12),
        padding=ft.padding.symmetric(horizontal=16, vertical=12),
        elevation={
            ft.ControlState.DEFAULT: 0,
            ft.ControlState.HOVERED: 2,
            ft.ControlState.PRESSED: 0,
            ft.ControlState.DISABLED: 0,
        },
    )


def outline_button_style(
    color: str = BLUE_BTN,
    hover_bg: str = BLUE_SOFT,
    border_color: str = BLUE_BORDER,
) -> ft.ButtonStyle:
    return ft.ButtonStyle(
        bgcolor={
            ft.ControlState.DEFAULT: "#FFFFFF",
            ft.ControlState.HOVERED: hover_bg,
            ft.ControlState.PRESSED: "#D8E8FF",
            ft.ControlState.DISABLED: "#F1F5F9",
        },
        color={
            ft.ControlState.DEFAULT: color,
            ft.ControlState.HOVERED: color,
            ft.ControlState.PRESSED: color,
            ft.ControlState.DISABLED: DISABLED,
        },
        side={
            ft.ControlState.DEFAULT: ft.BorderSide(1, border_color),
            ft.ControlState.HOVERED: ft.BorderSide(1, color),
            ft.ControlState.PRESSED: ft.BorderSide(1, color),
            ft.ControlState.DISABLED: ft.BorderSide(1, BORDER),
        },
        shape=ft.RoundedRectangleBorder(radius=12),
        padding=ft.padding.symmetric(horizontal=14, vertical=11),
    )


def icon_button_style() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        bgcolor={
            ft.ControlState.DEFAULT: "#FFFFFF",
            ft.ControlState.HOVERED: BLUE_SOFT,
            ft.ControlState.PRESSED: "#D8E8FF",
        },
        shape=ft.RoundedRectangleBorder(radius=12),
        side={
            ft.ControlState.DEFAULT: ft.BorderSide(1, BLUE_BORDER),
            ft.ControlState.HOVERED: ft.BorderSide(1, BLUE_BTN_HOVER),
            ft.ControlState.PRESSED: ft.BorderSide(1, BLUE_BTN_PRESS),
        },
    )



def _stable_button_content(
    text: str,
    icon,
    text_color: str,
    icon_size: int = 20,
    text_size: int = 15,
) -> ft.Row:
    return ft.Row(
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=8,
        tight=True,
        controls=[
            ft.Icon(icon, size=icon_size, color=text_color),
            ft.Text(
                text,
                size=text_size,
                weight=ft.FontWeight.BOLD,
                color=text_color,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        ],
    )


def stable_filled_button(
    text: str,
    icon,
    bg: str = BLUE_BTN,
    on_click=None,
    height: int = 46,
    expand: bool = True,
    text_color: str = "#FFFFFF",
) -> ft.Container:
    btn = ft.Container(
        expand=expand,
        height=height,
        border_radius=12,
        bgcolor=bg,
        alignment=ft.Alignment(0, 0),
        padding=ft.padding.symmetric(horizontal=12),
        ink=True,
        content=_stable_button_content(text, icon, text_color),
    )
    btn.disabled = False
    btn.data = {
        "stable_label": text,
        "stable_icon": icon,
        "stable_bg": bg,
        "stable_text_color": text_color,
    }

    def handle_click(e):
        if getattr(btn, "disabled", False):
            return
        if callable(on_click):
            on_click(e)

    btn.on_click = handle_click
    return btn


def stable_outline_button(
    text: str,
    icon=None,
    color: str = BLUE_BTN,
    border_color: str = BLUE_BORDER,
    hover_bg: str = BLUE_SOFT,
    on_click=None,
    height: int = 46,
    expand: bool = True,
) -> ft.Container:
    btn = ft.Container(
        expand=expand,
        height=height,
        border_radius=12,
        bgcolor="#FFFFFF",
        border=ft.border.all(1, border_color),
        alignment=ft.Alignment(0, 0),
        padding=ft.padding.symmetric(horizontal=12),
        ink=True,
        content=(
            _stable_button_content(text, icon, color, icon_size=18, text_size=14)
            if icon
            else ft.Text(
                text,
                size=14,
                weight=ft.FontWeight.BOLD,
                color=color,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        ),
    )
    btn.disabled = False
    btn.data = {
        "stable_label": text,
        "stable_icon": icon,
        "stable_bg": "#FFFFFF",
        "stable_text_color": color,
        "stable_border_color": border_color,
        "stable_hover_bg": hover_bg,
    }

    def handle_click(e):
        if getattr(btn, "disabled", False):
            return
        if callable(on_click):
            on_click(e)

    btn.on_click = handle_click
    return btn


def card(content, padding: int = 16, expand: bool = False) -> ft.Container:
    return ft.Container(
        expand=expand,
        bgcolor=CARD_BG,
        border=ft.border.all(1, BORDER),
        border_radius=16,
        padding=padding,
        content=content,
    )


def section_title(title: str, subtitle: str | None = None) -> ft.Column:
    controls = [
        ft.Text(title, size=20, weight=ft.FontWeight.BOLD, color=TEXT),
    ]

    if subtitle:
        controls.append(ft.Text(subtitle, size=13, color=TEXT_MUTED))

    return ft.Column(spacing=3, controls=controls)


def today_string() -> str:
    return date.today().strftime("%Y-%m-%d")


def to_int(value: str, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def item_display_name(item: dict) -> str:
    maintenance_type = item.get("maintenance_type") or ""
    sub_category = item.get("sub_category") or ""
    item_name = item.get("item_name") or ""

    if maintenance_type == "耗材更換" and sub_category:
        return f"{sub_category}-{item_name}"

    return item_name


def status_colors(status: str):
    if status == "正常":
        return GREEN, GREEN_SOFT
    if status == "提醒":
        return ORANGE, ORANGE_SOFT
    if status == "逾期":
        return RED, RED_SOFT
    if status == "未建立紀錄":
        return TEXT_MUTED, "#F1F5F9"
    if status == "異常":
        return RED, RED_SOFT
    return TEXT_MUTED, "#F1F5F9"


def task_tag_colors(tag: str):
    if tag == "逾期":
        return RED, RED_SOFT
    if tag == "今日":
        return ORANGE, ORANGE_SOFT
    if tag == "明日":
        return BLUE_BTN, BLUE_SOFT
    if tag in ["2天內", "3天內"]:
        return YELLOW, YELLOW_SOFT
    if tag == "未建立":
        return TEXT_MUTED, "#F1F5F9"
    return TEXT_MUTED, "#F1F5F9"


def set_button_loading(
    page: ft.Page,
    button,
    text: str = "寫入中...",
) -> None:
    button.disabled = True
    button.content = ft.Row(
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=10,
        tight=True,
        controls=[
            ft.ProgressRing(width=18, height=18, stroke_width=2, color="#FFFFFF"),
            ft.Text(text, size=15, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
        ],
    )
    try:
        button.update()
    except Exception:
        page.update()


def set_button_normal(
    page: ft.Page,
    button,
    text: str,
    icon,
) -> None:
    button.disabled = False
    data = button.data if isinstance(getattr(button, "data", None), dict) else {}
    text_color = data.get("stable_text_color", "#FFFFFF")
    button.content = _stable_button_content(text, icon, text_color)
    try:
        button.update()
    except Exception:
        page.update()


# ============================================================
# Main Content
# ============================================================

def MaintenanceContent(page: ft.Page) -> ft.Control:
    """
    給 main.py / shell() 呼叫：
        MaintenanceContent(page)

    這個 view 不直接呼叫 Supabase。
    所有資料讀寫都透過 services/maintenance_service.py。
    """

    state = {
        "selected_type": "清潔",
        "filter_type": "全部",
        "filter_status": "全部",
        "filter_machine": "全部",
        "data": {
            "items": [],
            "items_by_type": {"清潔": [], "耗材更換": []},
            "recent_records": [],
            "today_tasks": [],
            "summary": {
                "clean_count": 0,
                "material_count": 0,
                "due_count": 0,
                "abnormal_count": 0,
            },
        },
        "loading": True,
        "sync_status": "loading",
        "sync_message": "資料同步中",
        "sync_badge_visible": True,
        "error_message": "",
        "active_extension_form": None,
        "inline_record_item_id": None,
        "open_records_item_id": None,
        "item_records_cache": {},
        "item_records_loading": set(),
        "delete_confirm_record_id": None,
        # v2.5：手機 UX 收合狀態
        "items_expanded": True,
        "recent_expanded": False,
        "extension_expanded": False,
    }
    
    def session_get(key: str, default=None):
        if hasattr(page, "session_data") and isinstance(page.session_data, dict):
            return page.session_data.get(key, default)
        return default
    
    def is_super_admin() -> bool:
        return session_get("role") == "超級管理員"
    
    # 主內容與自製 Modal 層。
    # 採「動態加入 / 移除遮罩」方式，避免隱藏中的遮罩仍攔截點擊。
    main_host = ft.Container(expand=True)
    root_stack = ft.Stack(
        expand=True,
        controls=[main_host],
    )
    root = ft.Container(
        expand=True,
        bgcolor=BG,
        content=root_stack,
    )
    modal_ref = {"control": None}
    ui_lock = threading.RLock()

    # 基礎離頁保護：背景 thread 回來時，如果使用者已切離 /maintenance，就不再更新舊畫面。
    view_token = f"maintenance-{time.time_ns()}"
    if hasattr(page, "session_data") and isinstance(page.session_data, dict):
        page.session_data["_maintenance_view_token"] = view_token

    def is_active_view() -> bool:
        if hasattr(page, "session_data") and isinstance(page.session_data, dict):
            if page.session_data.get("_maintenance_view_token") != view_token:
                return False

        route = str(getattr(page, "route", "") or "")
        if route and route != "/maintenance":
            return False

        return True

    def safe_page_update() -> None:
        if not is_active_view():
            return
        try:
            with ui_lock:
                if is_active_view():
                    page.update()
        except Exception:
            pass

    def set_sync_state(status: str, message: str, visible: bool = True) -> None:
        state["sync_status"] = status
        state["sync_message"] = message
        state["sync_badge_visible"] = visible
        state["loading"] = status == "loading"

    def hide_sync_badge_later(delay_seconds: float = 3.0) -> None:
        def worker():
            time.sleep(delay_seconds)
            if not is_active_view():
                return
            if state.get("sync_status") == "success":
                state["sync_badge_visible"] = False
                rebuild()

        threading.Thread(target=worker, daemon=True).start()

    # =========================
    # 資料載入 / 重建畫面
    # =========================

    def open_dialog(dialog: ft.AlertDialog):
        """
        自製 Dialog 開窗方式。
        不使用 page.open/page.close/page.dialog。
        每次開窗時把遮罩動態加入 root_stack；關閉時完全移除，避免隱藏遮罩攔截點擊。
        """
        close_dialog()

        width = page.width or 420
        card_width = min(560, max(300, width - 36))

        title_control = dialog.title if dialog.title else ft.Container(height=0)
        content_control = dialog.content if dialog.content else ft.Container(height=0)
        action_controls = dialog.actions or []

        modal_card = ft.Container(
            width=card_width,
            bgcolor="#FFFFFF",
            border_radius=22,
            padding=ft.padding.all(22),
            content=ft.Column(
                tight=True,
                spacing=16,
                controls=[
                    title_control,
                    content_control,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        spacing=10,
                        controls=action_controls,
                    ),
                ],
            ),
        )

        modal_layer = ft.Container(
            expand=True,
            bgcolor="#99000000",
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.all(18),
            content=modal_card,
        )

        modal_ref["control"] = modal_layer
        root_stack.controls.append(modal_layer)
        safe_page_update()

    def close_dialog(dialog: ft.AlertDialog | None = None):
        """
        關閉自製 Dialog。
        直接從 Stack 移除遮罩，避免遮罩殘留或攔截按鈕點擊。
        """
        modal_layer = modal_ref.get("control")

        if modal_layer and modal_layer in root_stack.controls:
            root_stack.controls.remove(modal_layer)

        modal_ref["control"] = None

        safe_page_update()

    def show_snack(message: str, success: bool = True):
        """
        Flet 0.84 相容 SnackBar 顯示方式。
        """
        snack = ft.SnackBar(
            content=ft.Text(message, color="#FFFFFF"),
            bgcolor=BLUE_BTN if success else RED,
        )
        try:
            page.overlay.append(snack)
        except Exception:
            pass
        snack.open = True
        safe_page_update()

    def is_super_admin() -> bool:
        return session_get("role") == "超級管理員"

    def reload_item_records(item_id: str) -> bool:
        result = load_item_records(item_id=item_id, limit=20)

        if result.ok:
            state["item_records_cache"][item_id] = result.data or []
            return True

        state["item_records_cache"][item_id] = []
        show_snack(result.message or "讀取保養紀錄失敗。", success=False)
        return False

    def load_data(update_sync_state: bool = True) -> bool:
        result = load_maintenance_page_data()
        data = result.data if isinstance(result.data, dict) else None

        if result.ok:
            if data is not None:
                state["data"] = data
            state["error_message"] = ""
            if update_sync_state:
                set_sync_state("success", "資料已同步", visible=True)
            return True

        if data is not None:
            state["data"] = data
        state["error_message"] = result.message
        if update_sync_state:
            set_sync_state("error", "資料同步失敗", visible=True)
        return False

    def rebuild():
        if not is_active_view():
            return

        try:
            with ui_lock:
                if not is_active_view():
                    return

                width = page.width or 390

                if width < MOBILE_WIDTH:
                    main_host.content = build_mobile_layout()
                else:
                    main_host.content = build_desktop_layout()

                try:
                    main_host.update()
                except Exception:
                    page.update()
        except Exception:
            pass

    def start_background_load(show_loading: bool = True, render_loading: bool = True):
        if show_loading:
            set_sync_state("loading", "資料同步中", visible=True)
            if render_loading and is_active_view():
                rebuild()

        def worker():
            ok = load_data(update_sync_state=True)
            if not is_active_view():
                return

            rebuild()
            if ok:
                hide_sync_badge_later(3.0)

        threading.Thread(target=worker, daemon=True).start()

    def refresh():
        start_background_load(show_loading=True, render_loading=True)

    # =========================
    # 表單共用選項
    # =========================

    def get_all_items() -> list[dict]:
        return state["data"].get("items", [])

    def get_item_options(maintenance_type: str | None = None):
        items = get_all_items()

        if maintenance_type and maintenance_type != "全部":
            items = [
                item for item in items
                if item.get("maintenance_type") == maintenance_type
            ]

        return [
            ft.dropdown.Option(
                key=item.get("id"),
                text=f"{item_display_name(item)}｜{item.get('machine_area') or '-'}",
            )
            for item in items
        ]

    def get_machine_options():
        machines = set()

        for item in get_all_items():
            machine = item.get("machine_area")
            if machine:
                machines.add(machine)

        options = [ft.dropdown.Option("全部")]

        for machine in sorted(machines):
            options.append(ft.dropdown.Option(machine))

        return options

    # =========================
    # Dialog：篩選
    # =========================

    def open_filter_dialog(e=None):
        type_dd = ft.Dropdown(
            label="保養類型",
            value=state["filter_type"],
            options=[
                ft.dropdown.Option("全部"),
                ft.dropdown.Option("清潔"),
                ft.dropdown.Option("耗材更換"),
            ],
        )

        status_dd = ft.Dropdown(
            label="狀態",
            value=state["filter_status"],
            options=[
                ft.dropdown.Option("全部"),
                ft.dropdown.Option("正常"),
                ft.dropdown.Option("提醒"),
                ft.dropdown.Option("逾期"),
                ft.dropdown.Option("未建立紀錄"),
            ],
        )

        machine_dd = ft.Dropdown(
            label="機台 / 區位",
            value=state["filter_machine"],
            options=get_machine_options(),
        )

        def apply_filter(_):
            state["filter_type"] = type_dd.value or "全部"
            state["filter_status"] = status_dd.value or "全部"
            state["filter_machine"] = machine_dd.value or "全部"
            close_dialog(dialog)
            rebuild()

        def clear_filter(_):
            state["filter_type"] = "全部"
            state["filter_status"] = "全部"
            state["filter_machine"] = "全部"
            close_dialog(dialog)
            rebuild()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("篩選保養項目", size=18, weight=ft.FontWeight.BOLD, color=TEXT),
            content=ft.Container(
                width=380,
                content=ft.Column(
                    tight=True,
                    spacing=14,
                    controls=[
                        type_dd,
                        status_dd,
                        machine_dd,
                    ],
                ),
            ),
            actions=[
                ft.TextButton("清除條件", on_click=clear_filter),
                ft.ElevatedButton("套用篩選", style=primary_button_style(), on_click=apply_filter),
            ],
        )

        open_dialog(dialog)

    # =========================
    # Dialog：新增保養紀錄
    # =========================

    def open_record_dialog(e=None, preset_item_id: str | None = None):
        """
        新增保養紀錄。
        v2.3 修正：不再用 Dropdown 切換保養類型，改成兩顆明確的切換按鈕。
        這樣在 Flet 0.84 中比較穩定，點「清潔」只顯示清潔項目，點「耗材更換」只顯示耗材項目。
        """
        selected_type = state["selected_type"]

        preset_item_type = selected_type
        if preset_item_id:
            for _item in get_all_items():
                if _item.get("id") == preset_item_id:
                    preset_item_type = _item.get("maintenance_type") or selected_type
                    break

        form_state = {
            "type": preset_item_type,
            "item_id": preset_item_id if preset_item_id else None,
        }

        item_list_col = ft.Column(spacing=8)
        type_buttons_row = ft.Row(spacing=8)

        def build_type_button(label: str) -> ft.Container:
            active = form_state["type"] == label
            color = BLUE_BTN if label == "清潔" else ORANGE_BTN
            soft = BLUE_SOFT if label == "清潔" else ORANGE_SOFT
            border_color = color if active else BORDER
            bg = soft if active else "#FFFFFF"

            def choose_type(_):
                form_state["type"] = label
                form_state["item_id"] = None
                refresh_type_buttons()
                rebuild_item_options()

            return ft.Container(
                expand=True,
                ink=True,
                on_click=choose_type,
                bgcolor=bg,
                border=ft.border.all(1, border_color),
                border_radius=12,
                padding=ft.padding.symmetric(horizontal=12, vertical=12),
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=8,
                    controls=[
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE if active else ft.Icons.CIRCLE_OUTLINED,
                            size=18,
                            color=color if active else TEXT_MUTED,
                        ),
                        ft.Text(
                            label,
                            size=14,
                            color=color if active else TEXT_MUTED,
                            weight=ft.FontWeight.BOLD if active else ft.FontWeight.NORMAL,
                        ),
                    ],
                ),
            )

        def refresh_type_buttons():
            type_buttons_row.controls = [
                build_type_button("清潔"),
                build_type_button("耗材更換"),
            ]
            try:
                type_buttons_row.update()
            except Exception:
                pass

        def build_item_option(item: dict) -> ft.Container:
            item_id = item.get("id")
            is_selected = form_state.get("item_id") == item_id
            border_color = BLUE_BTN if is_selected else BORDER
            bg_color = BLUE_SOFT if is_selected else "#FFFFFF"
            text_color = BLUE_BTN if is_selected else TEXT

            def choose_item(_):
                form_state["item_id"] = item_id
                rebuild_item_options()

            return ft.Container(
                bgcolor=bg_color,
                border=ft.border.all(1, border_color),
                border_radius=12,
                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                ink=True,
                on_click=choose_item,
                content=ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE if is_selected else ft.Icons.CIRCLE_OUTLINED,
                            size=18,
                            color=BLUE_BTN if is_selected else TEXT_MUTED,
                        ),
                        ft.Column(
                            expand=True,
                            spacing=2,
                            controls=[
                                ft.Text(
                                    item_display_name(item),
                                    size=14,
                                    color=text_color,
                                    weight=ft.FontWeight.W_600 if is_selected else ft.FontWeight.NORMAL,
                                ),
                                ft.Text(
                                    f"{item.get('main_category') or '-'}｜{item.get('machine_area') or '-'}",
                                    size=12,
                                    color=TEXT_MUTED,
                                ),
                            ],
                        ),
                    ],
                ),
            )

        def rebuild_item_options():
            current_type = form_state["type"]
            items = [
                item for item in get_all_items()
                if item.get("maintenance_type") == current_type
            ]

            if not items:
                item_list_col.controls = [
                    ft.Container(
                        padding=12,
                        border=ft.border.all(1, BORDER),
                        border_radius=12,
                        bgcolor="#FFFFFF",
                        content=ft.Text("目前沒有此類型的保養項目。", size=13, color=TEXT_MUTED),
                    )
                ]
            else:
                item_list_col.controls = [build_item_option(item) for item in items]

            try:
                item_list_col.update()
            except Exception:
                pass

        refresh_type_buttons()
        rebuild_item_options()

        date_tf = ft.TextField(
            label="執行日期",
            value=today_string(),
            hint_text="YYYY-MM-DD",
        )

        operator_tf = ft.TextField(
            label="執行人員",
            value=session_get("user_name") or "",
            hint_text="請輸入執行人員",
        )

        result_dd = ft.Dropdown(
            label="結果",
            value="正常",
            options=[
                ft.dropdown.Option("正常"),
                ft.dropdown.Option("待確認"),
                ft.dropdown.Option("異常"),
            ],
        )

        note_tf = ft.TextField(
            label="備註",
            hint_text="可輸入保養說明、異常狀況或補充資訊",
            multiline=True,
            min_lines=3,
            max_lines=4,
        )

        submit_btn = stable_filled_button(
            "送出紀錄",
            ft.Icons.SAVE_OUTLINED,
            bg=BLUE_BTN,
            on_click=lambda e: on_submit(e),
            height=48,
        )

        def on_submit(_):
            if submit_btn.disabled:
                return

            set_button_loading(page, submit_btn)

            payload = {
                "maintenance_item_id": form_state.get("item_id") or "",
                "executed_date": date_tf.value or "",
                "operator_name": operator_tf.value or "",
                "result": result_dd.value or "",
                "note": note_tf.value or "",
                "created_by_user_id": session_get("user_id"),
                "created_by_name": session_get("user_name"),
            }

            def worker():
                result = submit_maintenance_record(**payload)
                if not is_active_view():
                    return
                if result.ok:
                    close_dialog(dialog)
                    try:
                        load_data(update_sync_state=True)
                        rebuild()
                        hide_sync_badge_later(3.0)
                        show_snack(result.message, success=True)
                    except Exception as ex:
                        show_snack(f"資料已寫入，但重新整理失敗：{ex}", success=False)
                else:
                    set_button_normal(page, submit_btn, "送出紀錄", ft.Icons.SAVE_OUTLINED)
                    show_snack(result.message, success=False)

            threading.Thread(target=worker, daemon=True).start()

        submit_btn.on_click = on_submit

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("新增保養紀錄", size=18, weight=ft.FontWeight.BOLD, color=TEXT),
            content=ft.Container(
                width=460,
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        ft.Text("保養類型", size=13, color=TEXT_MUTED),
                        type_buttons_row,
                        ft.Text("保養項目", size=13, color=TEXT_MUTED),
                        ft.Container(
                            height=260,
                            border=ft.border.all(1, BORDER),
                            border_radius=14,
                            padding=10,
                            bgcolor="#F8FAFC",
                            content=ft.Column(
                                scroll=ft.ScrollMode.AUTO,
                                controls=[item_list_col],
                            ),
                        ),
                        date_tf,
                        operator_tf,
                        result_dd,
                        note_tf,
                    ],
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _: close_dialog(dialog)),
                submit_btn,
            ],
        )

        open_dialog(dialog)

    # =========================
    # Inline Panel：新增清潔項目
    # =========================

    def open_create_cleaning_dialog(e=None):
        if state.get("loading"):
            show_snack("資料同步中，請稍候再操作。", success=False)
            return
        state["active_extension_form"] = None if state.get("active_extension_form") == "clean" else "clean"
        state["extension_expanded"] = True
        rebuild()

    # =========================
    # Inline Panel：新增耗材項目
    # =========================

    def open_create_consumable_dialog(e=None):
        if state.get("loading"):
            show_snack("資料同步中，請稍候再操作。", success=False)
            return
        state["active_extension_form"] = None if state.get("active_extension_form") == "material" else "material"
        state["extension_expanded"] = True
        rebuild()

    # =========================
    # Inline Panel：編輯週期
    # =========================

    def open_update_cycle_dialog(e=None):
        if state.get("loading"):
            show_snack("資料同步中，請稍候再操作。", success=False)
            return
        state["active_extension_form"] = None if state.get("active_extension_form") == "period" else "period"
        state["extension_expanded"] = True
        rebuild()

    # =========================
    # Header
    # =========================

    def build_header() -> ft.Control:
        """
        內容區頁首。
        版型對齊目前各頁：圖示 + 主標題 + 副標題，下方顯示資料同步膠囊。
        同步完成後膠囊會自動隱藏，避免標題區與後續內容間距過大。
        """
        sync_status = str(state.get("sync_status") or "success")
        sync_message = str(state.get("sync_message") or "資料已同步")
        show_badge = bool(state.get("sync_badge_visible"))

        if sync_status == "loading":
            status_color = BLUE_BTN
            status_bg = BLUE_SOFT
            status_border = BLUE_BORDER
            status_icon_control = ft.ProgressRing(width=15, height=15, stroke_width=2, color=status_color)
        elif sync_status == "error" or bool(state.get("error_message")):
            status_color = RED
            status_bg = RED_SOFT
            status_border = "#FCA5A5"
            status_icon_control = ft.Icon(ft.Icons.ERROR_OUTLINE, size=17, color=status_color)
            sync_message = "資料同步失敗"
            show_badge = True
        else:
            status_color = "#10B981"
            status_bg = "#ECFDF5"
            status_border = "#A7F3D0"
            status_icon_control = ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=17, color=status_color)

        title_row = ft.Row(
            spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Container(
                    width=58,
                    height=58,
                    border_radius=16,
                    bgcolor=BLUE_SOFT,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Icon(
                        ft.Icons.CLEANING_SERVICES_OUTLINED,
                        size=31,
                        color="#334155",
                    ),
                ),
                ft.Column(
                    expand=True,
                    spacing=5,
                    controls=[
                        ft.Text(
                            "機台保養紀錄",
                            size=26,
                            weight=ft.FontWeight.BOLD,
                            color=TEXT,
                            max_lines=2,
                        ),
                        ft.Text(
                            "記錄清潔、耗材更換與保養週期設定，協助追蹤設備維護狀態。",
                            size=14,
                            color=TEXT_MUTED,
                            max_lines=3,
                        ),
                    ],
                ),
            ],
        )

        controls = [title_row]

        if show_badge:
            status_badge = ft.Container(
                height=34,
                border_radius=17,
                bgcolor=status_bg,
                border=ft.border.all(1, status_border),
                alignment=ft.Alignment(0, 0),
                content=ft.Row(
                    spacing=7,
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        status_icon_control,
                        ft.Text(
                            sync_message,
                            size=12,
                            color=status_color,
                            weight=ft.FontWeight.W_600,
                        ),
                    ],
                ),
            )
            controls.append(ft.Container(content=status_badge))

        return ft.Column(
            spacing=10 if show_badge else 0,
            controls=controls,
        )

    # =========================
    # Summary Cards
    # =========================

    def build_summary_card(title: str, value: str, icon, color: str, bg: str) -> ft.Control:
        return card(
            padding=14,
            content=ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=50,
                        height=50,
                        border_radius=25,
                        bgcolor=bg,
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(icon, color=color, size=26),
                    ),
                    ft.Column(
                        spacing=2,
                        controls=[
                            ft.Text(title, size=13, color=TEXT_MUTED),
                            ft.Text(value, size=26, weight=ft.FontWeight.BOLD, color=TEXT),
                        ],
                    ),
                ],
            ),
        )

    def build_summary_cards(is_mobile: bool) -> ft.Control:
        summary = state["data"].get("summary", {})

        cards = [
            build_summary_card(
                "本月清潔",
                str(summary.get("clean_count", 0)),
                ft.Icons.CLEANING_SERVICES_OUTLINED,
                BLUE_BTN,
                BLUE_SOFT,
            ),
            build_summary_card(
                "本月耗材",
                str(summary.get("material_count", 0)),
                ft.Icons.INVENTORY_2_OUTLINED,
                ORANGE,
                ORANGE_SOFT,
            ),
            build_summary_card(
                "待保養",
                str(summary.get("due_count", 0)),
                ft.Icons.SCHEDULE_OUTLINED,
                YELLOW,
                YELLOW_SOFT,
            ),
            build_summary_card(
                "近期異常",
                str(summary.get("abnormal_count", 0)),
                ft.Icons.WARNING_AMBER_ROUNDED,
                RED,
                RED_SOFT,
            ),
        ]

        if is_mobile:
            return ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        spacing=12,
                        controls=[
                            ft.Container(expand=True, content=cards[0]),
                            ft.Container(expand=True, content=cards[1]),
                        ],
                    ),
                    ft.Row(
                        spacing=12,
                        controls=[
                            ft.Container(expand=True, content=cards[2]),
                            ft.Container(expand=True, content=cards[3]),
                        ],
                    ),
                ],
            )

        return ft.Row(
            spacing=12,
            controls=[ft.Container(expand=True, content=c) for c in cards],
        )

    # =========================
    # Type Tabs
    # =========================

    def build_type_tabs() -> ft.Control:
        selected = state["selected_type"]

        def set_type(value: str):
            state["selected_type"] = value
            rebuild()

        def tab(label: str) -> ft.Container:
            active = selected == label

            return ft.Container(
                expand=True,
                bgcolor=BLUE_SOFT if active else "#FFFFFF",
                padding=ft.padding.symmetric(vertical=12),
                border=ft.border.only(
                    bottom=ft.BorderSide(2, BLUE_BTN if active else BORDER)
                ),
                alignment=ft.Alignment(0, 0),
                on_click=lambda _: set_type(label),
                content=ft.Text(
                    label,
                    size=15,
                    color=BLUE_BTN if active else TEXT_MUTED,
                    weight=ft.FontWeight.BOLD if active else ft.FontWeight.NORMAL,
                ),
            )

        return ft.Container(
            border=ft.border.all(1, BORDER),
            border_radius=12,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Row(
                spacing=0,
                controls=[
                    tab("清潔"),
                    tab("耗材更換"),
                ],
            ),
        )

    # =========================
    # Today Tasks
    # =========================

    def build_today_tasks() -> ft.Control:
        tasks = state["data"].get("today_tasks", [])

        if not tasks:
            body = ft.Container(
                padding=18,
                alignment=ft.Alignment(0, 0),
                content=ft.Text("目前沒有待保養提醒。", size=14, color=TEXT_MUTED),
            )
        else:
            rows = []

            for task in tasks:
                tag = task.get("due_tag") or ""
                tag_color, tag_bg = task_tag_colors(tag)

                rows.append(
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=4, vertical=9),
                        content=ft.Row(
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Container(
                                    width=8,
                                    height=8,
                                    border_radius=4,
                                    bgcolor=tag_color,
                                ),
                                ft.Text(
                                    task.get("item_name") or "-",
                                    expand=True,
                                    size=14,
                                    color=TEXT,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Container(
                                    padding=ft.padding.symmetric(horizontal=10, vertical=4),
                                    border_radius=8,
                                    bgcolor=tag_bg,
                                    content=ft.Text(
                                        tag,
                                        size=12,
                                        color=tag_color,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                ),
                            ],
                        ),
                    )
                )

            body = ft.Column(spacing=0, controls=rows)

        return ft.Column(
            spacing=10,
            controls=[
                section_title("今日待辦", "顯示逾期、今日、明日與 3 天內需處理項目"),
                card(content=body, padding=12),
            ],
        )

    # =========================
    # Item Cards
    # =========================

    def get_filtered_items() -> list[dict]:
        selected_type = state["selected_type"]
        items = state["data"].get("items_by_type", {}).get(selected_type, [])

        filter_status = state["filter_status"]
        filter_machine = state["filter_machine"]

        if filter_status != "全部":
            items = [
                item for item in items
                if item.get("status") == filter_status
            ]

        if filter_machine != "全部":
            items = [
                item for item in items
                if item.get("machine_area") == filter_machine
            ]

        return items

    def build_inline_record_form(item: dict) -> ft.Control:
        """
        v2.5：項目卡片下方快速新增保養紀錄。
        點項目卡片中的「新增紀錄」後，表單直接出現在該卡片下方，
        避免使用者還要手動滑回頁面最上方。
        """
        date_tf = ft.TextField(
            label="執行日期",
            value=today_string(),
            hint_text="YYYY-MM-DD",
        )

        operator_tf = ft.TextField(
            label="執行人員",
            value=session_get("user_name") or "",
            hint_text="請輸入執行人員",
        )

        result_dd = ft.Dropdown(
            label="結果",
            value="正常",
            options=[
                ft.dropdown.Option("正常"),
                ft.dropdown.Option("待確認"),
                ft.dropdown.Option("異常"),
            ],
        )

        note_tf = ft.TextField(
            label="備註",
            hint_text="可輸入保養說明、異常狀況或補充資訊",
            multiline=True,
            min_lines=2,
            max_lines=4,
        )

        submit_btn = stable_filled_button(
            "送出紀錄",
            ft.Icons.SAVE_OUTLINED,
            bg=BLUE_BTN,
            on_click=lambda e: on_submit(e),
            height=46,
        )

        def close_inline_record_form(_=None):
            state["inline_record_item_id"] = None
            rebuild()

        def on_submit(_):
            if submit_btn.disabled:
                return

            set_button_loading(page, submit_btn)

            payload = {
                "maintenance_item_id": item.get("id") or "",
                "executed_date": date_tf.value or "",
                "operator_name": operator_tf.value or "",
                "result": result_dd.value or "",
                "note": note_tf.value or "",
                "created_by_user_id": session_get("user_id"),
                "created_by_name": session_get("user_name"),
            }

            def worker():
                result = submit_maintenance_record(**payload)
                if not is_active_view():
                    return
                if result.ok:
                    state["inline_record_item_id"] = None
                    load_data(update_sync_state=True)
                    rebuild()
                    hide_sync_badge_later(3.0)
                    show_snack(result.message, success=True)
                else:
                    set_button_normal(page, submit_btn, "送出紀錄", ft.Icons.SAVE_OUTLINED)
                    show_snack(result.message, success=False)

            threading.Thread(target=worker, daemon=True).start()

        submit_btn.on_click = on_submit

        return ft.Container(
            bgcolor="#F8FAFC",
            border=ft.border.all(1, BLUE_BORDER),
            border_radius=14,
            padding=14,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.EDIT_NOTE_OUTLINED, color=BLUE_BTN, size=22),
                            ft.Column(
                                expand=True,
                                spacing=2,
                                controls=[
                                    ft.Text("新增此項目保養紀錄", size=15, weight=ft.FontWeight.BOLD, color=TEXT),
                                    ft.Text(item_display_name(item), size=12, color=TEXT_MUTED),
                                ],
                            ),
                        ],
                    ),
                    date_tf,
                    operator_tf,
                    result_dd,
                    note_tf,
                    ft.Row(
                        spacing=10,
                        controls=[
                            stable_outline_button(
                                "取消",
                                ft.Icons.CLOSE,
                                on_click=close_inline_record_form,
                                height=46,
                            ),
                            ft.Container(expand=True, content=submit_btn),
                        ],
                    ),
                ],
            ),
        )

    def toggle_item_records(item: dict):
        item_id = item.get("id")

        if state.get("open_records_item_id") == item_id:
            state["open_records_item_id"] = None
            state["delete_confirm_record_id"] = None
            state.get("item_records_loading", set()).discard(item_id)
            rebuild()
            return

        state["open_records_item_id"] = item_id
        state["delete_confirm_record_id"] = None
        state.setdefault("item_records_loading", set()).add(item_id)
        rebuild()

        def worker():
            reload_item_records(item_id)
            if not is_active_view():
                return
            state.setdefault("item_records_loading", set()).discard(item_id)
            rebuild()

        threading.Thread(target=worker, daemon=True).start()

    def build_record_result_badge(result_text: str) -> ft.Container:
        color, bg = status_colors(result_text)
        return ft.Container(
            padding=ft.padding.symmetric(horizontal=9, vertical=4),
            border_radius=8,
            bgcolor=bg,
            content=ft.Text(
                result_text or "-",
                size=12,
                color=color,
                weight=ft.FontWeight.BOLD,
            ),
        )

    def build_item_records_panel(item: dict) -> ft.Control:
        item_id = item.get("id")
        records = state.get("item_records_cache", {}).get(item_id, [])
        loading_records = item_id in state.get("item_records_loading", set())
        admin = is_super_admin()

        def close_records(_=None):
            state["open_records_item_id"] = None
            state["delete_confirm_record_id"] = None
            rebuild()

        if loading_records:
            body = ft.Container(
                padding=14,
                border=ft.border.all(1, BLUE_BORDER),
                border_radius=12,
                bgcolor=BLUE_SOFT,
                content=ft.Row(
                    spacing=10,
                    controls=[
                        ft.ProgressRing(width=16, height=16, stroke_width=2, color=BLUE_BTN),
                        ft.Text("正在讀取此項目保養紀錄...", size=13, color=BLUE_BTN, weight=ft.FontWeight.W_600),
                    ],
                ),
            )
        elif not records:
            body = ft.Container(
                padding=14,
                border=ft.border.all(1, BORDER),
                border_radius=12,
                bgcolor="#FFFFFF",
                content=ft.Text("此項目目前沒有保養紀錄。", size=13, color=TEXT_MUTED),
            )
        else:
            rows = []

            for record in records:
                record_id = record.get("id")
                is_confirm = state.get("delete_confirm_record_id") == record_id

                def ask_delete(_, rid=record_id):
                    state["delete_confirm_record_id"] = rid
                    rebuild()

                def cancel_delete(_=None):
                    state["delete_confirm_record_id"] = None
                    rebuild()

                def confirm_delete(_, rid=record_id):
                    def worker():
                        result = delete_maintenance_record(
                            record_id=rid or "",
                            deleted_by_user_id=session_get("user_id"),
                            deleted_by_name=session_get("user_name"),
                            delete_reason="超級管理員於保養紀錄頁面刪除",
                            role=session_get("role"),
                        )
                        if not is_active_view():
                            return
                        if result.ok:
                            state["delete_confirm_record_id"] = None
                            reload_item_records(item_id)
                            load_data(update_sync_state=True)
                            rebuild()
                            hide_sync_badge_later(3.0)
                            show_snack(result.message, success=True)
                        else:
                            show_snack(result.message, success=False)

                    threading.Thread(target=worker, daemon=True).start()

                action_controls = []

                if admin:
                    if is_confirm:
                        action_controls = [
                            ft.Container(
                                expand=True,
                                content=ft.Text(
                                    "確認刪除此筆紀錄？",
                                    size=12,
                                    color=RED,
                                    weight=ft.FontWeight.W_600,
                                ),
                            ),
                            ft.OutlinedButton(
                                "取消",
                                style=outline_button_style(),
                                on_click=cancel_delete,
                            ),
                            ft.ElevatedButton(
                                "確認刪除",
                                height=38,
                                style=primary_button_style(bg=RED, hover="#B91C1C", pressed="#991B1B"),
                                on_click=confirm_delete,
                            ),
                        ]
                    else:
                        action_controls = [
                            ft.Container(expand=True),
                            ft.OutlinedButton(
                                "刪除",
                                style=outline_button_style(color=RED, hover_bg=RED_SOFT, border_color="#FCA5A5"),
                                on_click=ask_delete,
                            ),
                        ]

                row_controls = [
                    ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Container(
                                width=64,
                                content=ft.Column(
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=2,
                                    controls=[
                                        ft.Text(record.get("date_short") or "-", size=14, color=TEXT),
                                        build_record_result_badge(record.get("result") or "-"),
                                    ],
                                ),
                            ),
                            ft.Container(width=1, height=52, bgcolor=BORDER),
                            ft.Column(
                                expand=True,
                                spacing=5,
                                controls=[
                                    ft.Text(
                                        f"執行人員：{record.get('operator_name') or '-'}",
                                        size=13,
                                        color=TEXT,
                                        weight=ft.FontWeight.W_500,
                                    ),
                                    ft.Text(
                                        f"執行日期：{record.get('executed_date') or '-'}",
                                        size=12,
                                        color=TEXT_MUTED,
                                    ),
                                    ft.Text(
                                        record.get("note") or "無備註",
                                        size=12,
                                        color=TEXT_MUTED,
                                    ),
                                ],
                            ),
                        ],
                    ),
                ]

                if action_controls:
                    row_controls.append(
                        ft.Row(
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=action_controls,
                        )
                    )

                rows.append(
                    ft.Container(
                        bgcolor="#FFFFFF",
                        border=ft.border.all(1, BORDER),
                        border_radius=12,
                        padding=12,
                        content=ft.Column(spacing=10, controls=row_controls),
                    )
                )

            body = ft.Column(spacing=10, controls=rows)

        return ft.Container(
            bgcolor="#F8FAFC",
            border=ft.border.all(1, PURPLE_BORDER),
            border_radius=14,
            padding=14,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.HISTORY_OUTLINED, color=PURPLE_BTN, size=22),
                            ft.Column(
                                expand=True,
                                spacing=2,
                                controls=[
                                    ft.Text("此項目保養紀錄", size=15, weight=ft.FontWeight.BOLD, color=TEXT),
                                    ft.Text(item_display_name(item), size=12, color=TEXT_MUTED),
                                ],
                            ),
                            ft.OutlinedButton("收起", style=outline_button_style(), on_click=close_records),
                        ],
                    ),
                    ft.Text(
                        "軟刪除僅限超級管理員；刪除後不會從資料庫實體移除。" if admin else "僅顯示未刪除紀錄。",
                        size=12,
                        color=TEXT_MUTED,
                        visible=is_super_admin(),
                    ),
                    body,
                ],
            ),
        )

    def build_item_card(item: dict) -> ft.Control:
        status = item.get("status") or ""
        status_color, status_bg = status_colors(status)

        icon = (
            ft.Icons.CLEANING_SERVICES_OUTLINED
            if item.get("maintenance_type") == "清潔"
            else ft.Icons.INVENTORY_2_OUTLINED
        )

        icon_color = BLUE_BTN if item.get("maintenance_type") == "清潔" else ORANGE
        is_form_open = state.get("inline_record_item_id") == item.get("id")

        def toggle_inline_record_form(_=None):
            if state.get("inline_record_item_id") == item.get("id"):
                state["inline_record_item_id"] = None
            else:
                state["inline_record_item_id"] = item.get("id")
            rebuild()

        controls = [
            ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Container(
                        width=50,
                        height=50,
                        border_radius=25,
                        bgcolor="#F1F5F9",
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(icon, color=icon_color, size=25),
                    ),
                    ft.Column(
                        expand=True,
                        spacing=6,
                        controls=[
                            ft.Row(
                                vertical_alignment=ft.CrossAxisAlignment.START,
                                controls=[
                                    ft.Column(
                                        expand=True,
                                        spacing=3,
                                        controls=[
                                            ft.Text(
                                                item_display_name(item),
                                                size=16,
                                                weight=ft.FontWeight.BOLD,
                                                color=TEXT,
                                            ),
                                            ft.Text(
                                                f"{item.get('main_category') or '-'}｜{item.get('machine_area') or '-'}",
                                                size=12,
                                                color=TEXT_MUTED,
                                            ),
                                        ],
                                    ),
                                    ft.Container(
                                        padding=ft.padding.symmetric(horizontal=10, vertical=5),
                                        border_radius=8,
                                        bgcolor=status_bg,
                                        content=ft.Text(
                                            status,
                                            size=12,
                                            color=status_color,
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                    ),
                                ],
                            ),
                            ft.Row(
                                spacing=14,
                                controls=[
                                    ft.Column(
                                        spacing=2,
                                        controls=[
                                            ft.Text("最近保養日", size=11, color=TEXT_MUTED),
                                            ft.Text(item.get("last_date") or "-", size=13, color=TEXT),
                                        ],
                                    ),
                                    ft.Container(width=1, height=36, bgcolor=BORDER),
                                    ft.Column(
                                        spacing=2,
                                        controls=[
                                            ft.Text("下次建議日期", size=11, color=TEXT_MUTED),
                                            ft.Text(item.get("next_date") or "-", size=13, color=TEXT),
                                        ],
                                    ),
                                    ft.Container(width=1, height=36, bgcolor=BORDER),
                                    ft.Column(
                                        spacing=2,
                                        controls=[
                                            ft.Text("週期", size=11, color=TEXT_MUTED),
                                            ft.Text(f"{item.get('cycle_days') or 0} 天", size=13, color=TEXT),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            ft.ResponsiveRow(
                columns=12,
                spacing=10,
                run_spacing=10,
                controls=[
                    ft.Container(
                        col={"xs": 12, "sm": 6},
                        content=stable_outline_button(
                            "收起紀錄" if state.get("open_records_item_id") == item.get("id") else "查看紀錄",
                            ft.Icons.HISTORY_OUTLINED,
                            color=PURPLE_BTN if state.get("open_records_item_id") == item.get("id") else BLUE_BTN,
                            border_color=PURPLE_BORDER if state.get("open_records_item_id") == item.get("id") else BLUE_BORDER,
                            hover_bg=PURPLE_SOFT if state.get("open_records_item_id") == item.get("id") else BLUE_SOFT,
                            on_click=lambda _, current_item=item: toggle_item_records(current_item),
                            height=44,
                        ),
                    ),
                    ft.Container(
                        col={"xs": 12, "sm": 6},
                        content=stable_filled_button(
                            "收起表單" if is_form_open else "新增紀錄",
                            ft.Icons.KEYBOARD_ARROW_UP if is_form_open else ft.Icons.ADD_CIRCLE_OUTLINE,
                            bg=PURPLE_BTN if is_form_open else BLUE_BTN,
                            on_click=toggle_inline_record_form,
                            height=44,
                        ),
                    ),
                ],
            ),
        ]

        if is_form_open:
            controls.append(build_inline_record_form(item))

        if state.get("open_records_item_id") == item.get("id"):
            controls.append(build_item_records_panel(item))

        return card(
            padding=14,
            content=ft.Column(
                spacing=12,
                controls=controls,
            ),
        )

    def build_filter_bar() -> ft.Control:
        """
        v2.5：頁面內篩選列。
        不再使用彈出式篩選視窗；保養類型由外層「清潔 / 耗材更換」切換控制。
        此處只篩選狀態與機台 / 區位，避免彈窗與外層 label 狀態互相干擾。
        """
        status_text = state.get("filter_status", "全部")
        machine_text = state.get("filter_machine", "全部")
        active_filter = status_text != "全部" or machine_text != "全部"

        status_dd = ft.Dropdown(
            label="狀態",
            value=status_text,
            dense=True,
            options=[
                ft.dropdown.Option("全部"),
                ft.dropdown.Option("正常"),
                ft.dropdown.Option("提醒"),
                ft.dropdown.Option("逾期"),
                ft.dropdown.Option("未建立紀錄"),
            ],
        )

        machine_dd = ft.Dropdown(
            label="機台 / 區位",
            value=machine_text,
            dense=True,
            options=get_machine_options(),
        )

        def apply_inline_filter(_=None):
            state["filter_status"] = status_dd.value or "全部"
            state["filter_machine"] = machine_dd.value or "全部"
            rebuild()

        def clear_inline_filter(_=None):
            state["filter_status"] = "全部"
            state["filter_machine"] = "全部"
            rebuild()

        status_dd.on_change = apply_inline_filter
        machine_dd.on_change = apply_inline_filter

        clear_btn = ft.OutlinedButton(
            "清除",
            visible=active_filter,
            style=outline_button_style(),
            on_click=clear_inline_filter,
        )

        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.border.all(1, BLUE_BORDER if active_filter else BORDER),
            border_radius=14,
            padding=12,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(
                                ft.Icons.FILTER_ALT_OUTLINED,
                                size=20,
                                color=BLUE_BTN if active_filter else TEXT_MUTED,
                            ),
                            ft.Column(
                                expand=True,
                                spacing=2,
                                controls=[
                                    ft.Text("頁面內篩選", size=13, color=TEXT, weight=ft.FontWeight.W_600),
                                    ft.Text(
                                        f"目前條件：狀態 {status_text}｜區位 {machine_text}",
                                        size=12,
                                        color=TEXT_MUTED,
                                    ),
                                ],
                            ),
                            clear_btn,
                        ],
                    ),
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.Container(expand=True, content=status_dd),
                            ft.Container(expand=True, content=machine_dd),
                        ],
                    ),
                ],
            ),
        )

    def build_collapsible_section(
        title: str,
        subtitle: str,
        expanded_key: str,
        body: ft.Control,
        badge_text: str | None = None,
        default_expanded: bool = True,
    ) -> ft.Control:
        expanded = state.get(expanded_key, default_expanded)

        def toggle(_):
            state[expanded_key] = not state.get(expanded_key, default_expanded)
            rebuild()

        controls = [
            ft.Container(
                ink=True,
                on_click=toggle,
                content=ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            expand=True,
                            spacing=3,
                            controls=[
                                ft.Row(
                                    spacing=8,
                                    controls=[
                                        ft.Text(title, size=20, weight=ft.FontWeight.BOLD, color=TEXT),
                                        ft.Container(
                                            visible=bool(badge_text),
                                            padding=ft.padding.symmetric(horizontal=8, vertical=3),
                                            border_radius=8,
                                            bgcolor="#F1F5F9",
                                            content=ft.Text(badge_text or "", size=12, color=TEXT_MUTED, weight=ft.FontWeight.BOLD),
                                        ),
                                    ],
                                ),
                                ft.Text(subtitle, size=13, color=TEXT_MUTED),
                            ],
                        ),
                        ft.Container(
                            width=38,
                            height=38,
                            border_radius=19,
                            bgcolor=BLUE_SOFT if expanded else "#FFFFFF",
                            border=ft.border.all(1, BLUE_BORDER if expanded else BORDER),
                            alignment=ft.Alignment(0, 0),
                            content=ft.Icon(
                                ft.Icons.KEYBOARD_ARROW_UP if expanded else ft.Icons.KEYBOARD_ARROW_DOWN,
                                color=BLUE_BTN if expanded else TEXT_MUTED,
                                size=24,
                            ),
                        ),
                    ],
                ),
            ),
        ]

        if expanded:
            controls.append(body)

        return ft.Column(spacing=10, controls=controls)

    def build_item_list() -> ft.Control:
        selected_type = state["selected_type"]
        items = get_filtered_items()

        title = "清潔項目" if selected_type == "清潔" else "耗材更換項目"

        if not items:
            body = card(
                padding=22,
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.SEARCH_OFF_OUTLINED, size=34, color=TEXT_MUTED),
                        ft.Text("沒有符合條件的保養項目。", size=14, color=TEXT_MUTED),
                    ],
                ),
            )
        else:
            body = ft.Column(
                spacing=10,
                controls=[build_item_card(item) for item in items],
            )

        return build_collapsible_section(
            title=title,
            subtitle="點擊標題可收合；點項目卡片中的新增紀錄會直接開啟表單。",
            expanded_key="items_expanded",
            body=body,
            badge_text=f"{len(items)} 筆",
            default_expanded=True,
        )

    # =========================
    # Recent Records
    # =========================

    def build_recent_records() -> ft.Control:
        records = state["data"].get("recent_records", [])

        if not records:
            body = ft.Container(
                padding=18,
                alignment=ft.Alignment(0, 0),
                content=ft.Text("目前尚無保養紀錄。", size=14, color=TEXT_MUTED),
            )
        else:
            rows = []

            for record in records:
                m_type = record.get("maintenance_type") or "-"
                color = BLUE_BTN if m_type == "清潔" else ORANGE

                rows.append(
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=8, vertical=11),
                        border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
                        content=ft.Row(
                            controls=[
                                ft.Container(
                                    width=64,
                                    content=ft.Column(
                                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                        spacing=2,
                                        controls=[
                                            ft.Text(record.get("date_short") or "-", size=14, color=TEXT),
                                            ft.Text(m_type, size=12, color=color, weight=ft.FontWeight.BOLD),
                                        ],
                                    ),
                                ),
                                ft.Container(width=1, height=42, bgcolor=BORDER),
                                ft.Column(
                                    expand=True,
                                    spacing=3,
                                    controls=[
                                        ft.Text(
                                            record.get("item_name") or "-",
                                            size=14,
                                            weight=ft.FontWeight.W_500,
                                            color=TEXT,
                                        ),
                                        ft.Text(
                                            f"結果：{record.get('result') or '-'} / 執行人員：{record.get('operator_name') or '-'}",
                                            size=12,
                                            color=TEXT_MUTED,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    )
                )

            body = card(content=ft.Column(spacing=0, controls=rows), padding=0)

        return build_collapsible_section(
            title="最近保養紀錄",
            subtitle="顯示最近送出的保養紀錄",
            expanded_key="recent_expanded",
            body=body,
            badge_text=f"{len(records)} 筆",
            default_expanded=False,
        )

    # =========================
    # Extension Settings：改為頁面內展開式表單，不使用 Dialog
    # =========================

    def build_extension_settings() -> ft.Control:
        def close_inline_form(_=None):
            state["active_extension_form"] = None
            rebuild()

        def form_label(label: str, required: bool = False) -> ft.Row:
            return ft.Row(
                spacing=4,
                controls=[
                    ft.Text(
                        label + (" *" if required else ""),
                        size=13,
                        color=TEXT,
                        weight=ft.FontWeight.W_600,
                    )
                ],
            )

        def form_text_field(
            label: str,
            hint: str = "",
            value: str = "",
            required: bool = False,
            multiline: bool = False,
            keyboard_type=None,
        ) -> tuple[ft.Column, ft.TextField]:
            field = ft.TextField(
                value=value,
                hint_text=hint,
                hint_style=ft.TextStyle(size=14, color=TEXT_MUTED),
                multiline=multiline,
                min_lines=2 if multiline else 1,
                max_lines=4 if multiline else 1,
                keyboard_type=keyboard_type,
                border_radius=12,
                border_color=BORDER,
                focused_border_color=BLUE_BTN,
                bgcolor="#FFFFFF",
                filled=True,
                text_size=15,
                content_padding=ft.padding.symmetric(horizontal=12, vertical=11),
            )
            return (
                ft.Column(
                    spacing=6,
                    controls=[form_label(label, required), field],
                ),
                field,
            )

        def extension_action_button(label: str, icon, color: str, soft_bg: str, handler):
            """手機 Web 穩定版：不用 OutlinedButton，改成 Container + Column。"""
            return ft.Container(
                height=78,
                bgcolor="#FFFFFF",
                border=ft.border.all(1, color),
                border_radius=14,
                padding=ft.padding.symmetric(horizontal=6, vertical=8),
                alignment=ft.Alignment(0, 0),
                ink=True,
                on_click=handler,
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=5,
                    controls=[
                        ft.Container(
                            width=38,
                            height=38,
                            border_radius=19,
                            bgcolor=soft_bg,
                            alignment=ft.Alignment(0, 0),
                            content=ft.Icon(icon, color=color, size=22),
                        ),
                        ft.Text(
                            label,
                            size=11,
                            color=TEXT,
                            weight=ft.FontWeight.W_600,
                            text_align=ft.TextAlign.CENTER,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                ),
            )

        def guided_hint(text: str) -> ft.Container:
            return ft.Container(
                bgcolor="#F8FAFC",
                border=ft.border.all(1, BORDER),
                border_radius=12,
                padding=ft.padding.symmetric(horizontal=12, vertical=9),
                content=ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=TEXT_MUTED),
                        ft.Text(text, size=12, color=TEXT_MUTED, expand=True),
                    ],
                ),
            )

        def option_chip(
            label: str,
            on_click,
            color: str = BLUE_BTN,
        ) -> ft.Container:
            return ft.Container(
                height=34,
                border_radius=17,
                bgcolor="#FFFFFF",
                border=ft.border.all(1, BORDER),
                padding=ft.padding.symmetric(horizontal=11),
                alignment=ft.Alignment(0, 0),
                ink=True,
                on_click=on_click,
                content=ft.Text(
                    label,
                    size=12,
                    color=color,
                    weight=ft.FontWeight.W_600,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            )

        def unique_values(values: list[str]) -> list[str]:
            result = []
            for value in values:
                text = str(value or "").strip()
                if text and text not in result:
                    result.append(text)
            return result

        def summary_line(label: str, value: str) -> ft.Control:
            return ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Container(
                        width=105,
                        content=ft.Text(label, size=13, color=TEXT_MUTED),
                    ),
                    ft.Text(
                        value or "-",
                        size=13,
                        color=TEXT,
                        weight=ft.FontWeight.W_600,
                        expand=True,
                    ),
                ],
            )

        def build_clean_form():
            clean_areas = unique_values([
                item.get("machine_area")
                for item in get_all_items()
                if item.get("maintenance_type") == "清潔"
            ])
            clean_suggestions = unique_values([
                item.get("item_name")
                for item in get_all_items()
                if item.get("maintenance_type") == "清潔"
            ])[:10]

            area_group, area_tf = form_text_field(
                "設備 / 區域",
                "可選既有區域，或輸入新設備 / 新區域，例如：S1線、燒解爐、超音波區",
                required=True,
            )
            item_name_group, item_name_tf = form_text_field(
                "清潔項目名稱",
                "例如：S1-旋風分離器、燒解爐廢料槽",
                required=True,
            )
            location_group, location_tf = form_text_field(
                "適用位置",
                "例如：S1線、S2線、燒解爐；若與設備 / 區域相同可填同一個名稱",
                required=True,
            )
            cycle_group, cycle_tf = form_text_field(
                "建議清潔週期",
                "例如：7、14、30",
                value="30",
                required=True,
                keyboard_type=ft.KeyboardType.NUMBER,
            )
            desc_group, desc_tf = form_text_field(
                "備註 / 注意事項",
                "可輸入清潔方式、注意事項或判定基準",
                multiline=True,
            )

            def choose_area(value: str):
                area_tf.value = value
                if not str(location_tf.value or "").strip():
                    location_tf.value = value
                try:
                    area_tf.update()
                    location_tf.update()
                except Exception:
                    page.update()

            def choose_clean_item(value: str):
                item_name_tf.value = value
                try:
                    item_name_tf.update()
                except Exception:
                    page.update()

            existing_area_controls = [
                option_chip(value, lambda _, v=value: choose_area(v), color=BLUE_BTN)
                for value in clean_areas
            ]
            existing_item_controls = [
                option_chip(value, lambda _, v=value: choose_clean_item(v), color=BLUE_BTN)
                for value in clean_suggestions
            ]

            submit_btn = stable_filled_button(
                "新增清潔項目",
                ft.Icons.ADD_OUTLINED,
                bg=BLUE_BTN,
                on_click=lambda e: on_prepare_submit(e),
                height=46,
            )

            def validate_payload() -> tuple[bool, str, dict]:
                area = str(area_tf.value or "").strip()
                item_name = str(item_name_tf.value or "").strip()
                location = str(location_tf.value or "").strip()
                cycle_days = to_int(cycle_tf.value, 0)
                note = str(desc_tf.value or "").strip()

                if not area:
                    return False, "請輸入或選擇設備 / 區域。", {}
                if not item_name:
                    return False, "請輸入清潔項目名稱。", {}
                if not location:
                    return False, "請輸入適用位置。", {}
                if cycle_days <= 0:
                    return False, "建議清潔週期需為大於 0 的整數。", {}

                description_parts = []
                if area and area != location:
                    description_parts.append(f"設備 / 區域：{area}")
                if note:
                    description_parts.append(note)

                return True, "", {
                    "area": area,
                    "item_name": item_name,
                    "machine_area": location,
                    "cycle_days": cycle_days,
                    "description": "\n".join(description_parts),
                    "note": note,
                }

            def run_create(payload: dict):
                result = create_cleaning_item(
                    item_name=payload["item_name"],
                    machine_area=payload["machine_area"],
                    cycle_days=payload["cycle_days"],
                    sort_order=999,
                    description=payload.get("description") or "",
                )

                if result.ok:
                    if not is_active_view():
                        return
                    state["active_extension_form"] = None
                    load_data(update_sync_state=True)
                    rebuild()
                    hide_sync_badge_later(3.0)
                    show_snack(result.message, success=True)
                else:
                    set_button_normal(page, submit_btn, "新增清潔項目", ft.Icons.ADD_OUTLINED)
                    show_snack(result.message, success=False)

            def open_confirm(payload: dict):
                confirm_btn = stable_filled_button(
                    "確認新增",
                    ft.Icons.CHECK_CIRCLE_OUTLINE,
                    bg=BLUE_BTN,
                    height=44,
                    expand=False,
                    on_click=lambda e: confirm_create(e),
                )

                def confirm_create(_):
                    if confirm_btn.disabled:
                        return
                    close_dialog(confirm_dialog)
                    set_button_loading(page, submit_btn, "寫入中...")
                    threading.Thread(target=lambda: run_create(payload), daemon=True).start()

                confirm_dialog = ft.AlertDialog(
                    modal=True,
                    title=ft.Text("確認新增清潔項目", size=18, weight=ft.FontWeight.BOLD, color=TEXT),
                    content=ft.Container(
                        width=430,
                        content=ft.Column(
                            tight=True,
                            spacing=10,
                            controls=[
                                ft.Text("請確認以下內容，確認後會新增到保養項目清單。", size=13, color=TEXT_MUTED),
                                ft.Divider(height=8),
                                summary_line("類型", "清潔"),
                                summary_line("設備 / 區域", payload.get("area") or "-"),
                                summary_line("清潔項目名稱", payload.get("item_name") or "-"),
                                summary_line("適用位置", payload.get("machine_area") or "-"),
                                summary_line("建議清潔週期", f"{payload.get('cycle_days')} 天"),
                                summary_line("備註", payload.get("note") or "無"),
                            ],
                        ),
                    ),
                    actions=[
                        ft.TextButton("返回修改", on_click=lambda _: close_dialog(confirm_dialog)),
                        confirm_btn,
                    ],
                )
                open_dialog(confirm_dialog)

            def on_prepare_submit(_):
                if submit_btn.disabled:
                    return
                ok, message, payload = validate_payload()
                if not ok:
                    show_snack(message, success=False)
                    return
                open_confirm(payload)

            submit_btn.on_click = on_prepare_submit

            controls = [
                section_title("新增清潔項目", "依現場設備 / 區域引導填寫，避免直接面對空白欄位。"),
                guided_hint("可先點選既有設備 / 區域；如果這次是全新設備或新區域，直接在欄位中輸入即可。"),
            ]

            if existing_area_controls:
                controls.append(
                    ft.Column(
                        spacing=7,
                        controls=[
                            ft.Text("既有設備 / 區域", size=12, color=TEXT_MUTED, weight=ft.FontWeight.W_600),
                            ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8, controls=existing_area_controls),
                        ],
                    )
                )

            controls.extend([area_group])

            if existing_item_controls:
                controls.append(
                    ft.Column(
                        spacing=7,
                        controls=[
                            ft.Text("既有清潔項目可參考", size=12, color=TEXT_MUTED, weight=ft.FontWeight.W_600),
                            ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8, controls=existing_item_controls),
                        ],
                    )
                )

            controls.extend([
                item_name_group,
                location_group,
                cycle_group,
                desc_group,
                ft.Row(
                    spacing=10,
                    controls=[
                        stable_outline_button(
                            "取消",
                            ft.Icons.CLOSE,
                            on_click=close_inline_form,
                            height=46,
                        ),
                        ft.Container(expand=True, content=submit_btn),
                    ],
                ),
            ])

            return card(
                padding=16,
                content=ft.Column(spacing=12, controls=controls),
            )

        def build_material_form():
            existing_systems = unique_values([
                item.get("main_category")
                for item in get_all_items()
                if item.get("maintenance_type") == "耗材更換"
            ])
            existing_sub_categories = unique_values([
                item.get("sub_category")
                for item in get_all_items()
                if item.get("maintenance_type") == "耗材更換"
            ])
            existing_material_names = unique_values([
                item.get("item_name")
                for item in get_all_items()
                if item.get("maintenance_type") == "耗材更換"
            ])[:10]

            common_sub_categories = unique_values(existing_sub_categories + ["A管", "B管", "冷卻水濾芯", "清洗藥水", "濾芯", "藥水"])

            system_group, system_tf = form_text_field(
                "設備 / 系統",
                "可選既有設備，或輸入新設備 / 系統，例如：除濕機、燒解爐、超音波",
                required=True,
            )
            sub_group, sub_tf = form_text_field(
                "耗材類型 / 區段",
                "例如：A管、B管、冷卻水濾芯、清洗藥水；可空白",
            )
            item_name_group, item_name_tf = form_text_field(
                "耗材名稱",
                "例如：除油濾芯、冷卻水濾芯-5um-20吋、Deconex FID 2000 清洗藥水",
                required=True,
            )
            machine_group, machine_tf = form_text_field(
                "適用位置",
                "例如：除濕機A管、燒解爐、超音波機",
                required=True,
            )
            cycle_group, cycle_tf = form_text_field(
                "建議更換週期",
                "例如：30、90、180",
                value="30",
                required=True,
                keyboard_type=ft.KeyboardType.NUMBER,
            )
            desc_group, desc_tf = form_text_field(
                "備註 / 注意事項",
                "可輸入規格、廠牌、使用濃度、更換基準或注意事項",
                multiline=True,
            )

            def choose_system(value: str):
                system_tf.value = value
                if not str(machine_tf.value or "").strip():
                    machine_tf.value = value
                try:
                    system_tf.update()
                    machine_tf.update()
                except Exception:
                    page.update()

            def choose_sub(value: str):
                sub_tf.value = value
                try:
                    sub_tf.update()
                except Exception:
                    page.update()

            def choose_material_name(value: str):
                item_name_tf.value = value
                try:
                    item_name_tf.update()
                except Exception:
                    page.update()

            existing_system_controls = [
                option_chip(value, lambda _, v=value: choose_system(v), color=ORANGE_BTN)
                for value in existing_systems
            ]
            sub_controls = [
                option_chip(value, lambda _, v=value: choose_sub(v), color=ORANGE_BTN)
                for value in common_sub_categories
            ]
            material_name_controls = [
                option_chip(value, lambda _, v=value: choose_material_name(v), color=ORANGE_BTN)
                for value in existing_material_names
            ]

            submit_btn = stable_filled_button(
                "新增耗材項目",
                ft.Icons.ADD_OUTLINED,
                bg=ORANGE_BTN,
                on_click=lambda e: on_prepare_submit(e),
                height=46,
            )

            def validate_payload() -> tuple[bool, str, dict]:
                system = str(system_tf.value or "").strip()
                sub_category = str(sub_tf.value or "").strip()
                item_name = str(item_name_tf.value or "").strip()
                machine_area = str(machine_tf.value or "").strip()
                cycle_days = to_int(cycle_tf.value, 0)
                note = str(desc_tf.value or "").strip()

                if not system:
                    return False, "請輸入或選擇設備 / 系統。", {}
                if not item_name:
                    return False, "請輸入耗材名稱。", {}
                if not machine_area:
                    return False, "請輸入適用位置。", {}
                if cycle_days <= 0:
                    return False, "建議更換週期需為大於 0 的整數。", {}

                return True, "", {
                    "main_category": system,
                    "sub_category": sub_category,
                    "item_name": item_name,
                    "machine_area": machine_area,
                    "cycle_days": cycle_days,
                    "description": note,
                    "note": note,
                }

            def run_create(payload: dict):
                result = create_consumable_item(
                    main_category=payload["main_category"],
                    sub_category=payload.get("sub_category") or "",
                    item_name=payload["item_name"],
                    machine_area=payload["machine_area"],
                    cycle_days=payload["cycle_days"],
                    sort_order=999,
                    description=payload.get("description") or "",
                )

                if result.ok:
                    if not is_active_view():
                        return
                    state["active_extension_form"] = None
                    load_data(update_sync_state=True)
                    rebuild()
                    hide_sync_badge_later(3.0)
                    show_snack(result.message, success=True)
                else:
                    set_button_normal(page, submit_btn, "新增耗材項目", ft.Icons.ADD_OUTLINED)
                    show_snack(result.message, success=False)

            def open_confirm(payload: dict):
                confirm_btn = stable_filled_button(
                    "確認新增",
                    ft.Icons.CHECK_CIRCLE_OUTLINE,
                    bg=ORANGE_BTN,
                    height=44,
                    expand=False,
                    on_click=lambda e: confirm_create(e),
                )

                def confirm_create(_):
                    if confirm_btn.disabled:
                        return
                    close_dialog(confirm_dialog)
                    set_button_loading(page, submit_btn, "寫入中...")
                    threading.Thread(target=lambda: run_create(payload), daemon=True).start()

                confirm_dialog = ft.AlertDialog(
                    modal=True,
                    title=ft.Text("確認新增耗材項目", size=18, weight=ft.FontWeight.BOLD, color=TEXT),
                    content=ft.Container(
                        width=430,
                        content=ft.Column(
                            tight=True,
                            spacing=10,
                            controls=[
                                ft.Text("請確認以下內容，確認後會新增到保養項目清單。", size=13, color=TEXT_MUTED),
                                ft.Divider(height=8),
                                summary_line("類型", "耗材更換"),
                                summary_line("設備 / 系統", payload.get("main_category") or "-"),
                                summary_line("耗材類型 / 區段", payload.get("sub_category") or "-"),
                                summary_line("耗材名稱", payload.get("item_name") or "-"),
                                summary_line("適用位置", payload.get("machine_area") or "-"),
                                summary_line("建議更換週期", f"{payload.get('cycle_days')} 天"),
                                summary_line("備註", payload.get("note") or "無"),
                            ],
                        ),
                    ),
                    actions=[
                        ft.TextButton("返回修改", on_click=lambda _: close_dialog(confirm_dialog)),
                        confirm_btn,
                    ],
                )
                open_dialog(confirm_dialog)

            def on_prepare_submit(_):
                if submit_btn.disabled:
                    return
                ok, message, payload = validate_payload()
                if not ok:
                    show_snack(message, success=False)
                    return
                open_confirm(payload)

            submit_btn.on_click = on_prepare_submit

            controls = [
                section_title("新增耗材項目", "依設備 / 系統引導填寫；既有設備可直接點選，第一次建立的新設備也可直接輸入。"),
                guided_hint("如果像超音波清洗藥水這種全新項目，請直接在設備 / 系統輸入「超音波」，再填耗材類型與耗材名稱。"),
            ]

            if existing_system_controls:
                controls.append(
                    ft.Column(
                        spacing=7,
                        controls=[
                            ft.Text("既有設備 / 系統", size=12, color=TEXT_MUTED, weight=ft.FontWeight.W_600),
                            ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8, controls=existing_system_controls),
                        ],
                    )
                )

            controls.append(system_group)

            if sub_controls:
                controls.append(
                    ft.Column(
                        spacing=7,
                        controls=[
                            ft.Text("常用耗材類型 / 區段", size=12, color=TEXT_MUTED, weight=ft.FontWeight.W_600),
                            ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8, controls=sub_controls),
                        ],
                    )
                )

            controls.extend([sub_group])

            if material_name_controls:
                controls.append(
                    ft.Column(
                        spacing=7,
                        controls=[
                            ft.Text("既有耗材名稱可參考", size=12, color=TEXT_MUTED, weight=ft.FontWeight.W_600),
                            ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8, controls=material_name_controls),
                        ],
                    )
                )

            controls.extend([
                item_name_group,
                machine_group,
                cycle_group,
                desc_group,
                ft.Row(
                    spacing=10,
                    controls=[
                        stable_outline_button(
                            "取消",
                            ft.Icons.CLOSE,
                            on_click=close_inline_form,
                            height=46,
                        ),
                        ft.Container(expand=True, content=submit_btn),
                    ],
                ),
            ])

            return card(
                padding=16,
                content=ft.Column(spacing=12, controls=controls),
            )

        def build_period_form():
            all_items = get_all_items()
            initial_item = all_items[0] if all_items else None
            period_state = {
                "item_id": initial_item.get("id") if initial_item else "",
            }
            initial_cycle = str(initial_item.get("cycle_days") or 30) if initial_item else ""

            cycle_group, cycle_tf = form_text_field(
                "新的週期天數",
                "請先選擇保養項目",
                value=initial_cycle,
                required=True,
                keyboard_type=ft.KeyboardType.NUMBER,
            )
            active_dd = ft.Dropdown(
                value="啟用",
                options=[ft.dropdown.Option("啟用"), ft.dropdown.Option("停用")],
                border_radius=12,
                border_color=BORDER,
                focused_border_color=PURPLE_BTN,
                bgcolor="#FFFFFF",
                filled=True,
            )
            item_list_col = ft.Column(spacing=8)
            selected_hint = ft.Text(
                "尚無可編輯的保養項目。" if not initial_item else f"目前選擇：{item_display_name(initial_item)}｜目前週期 {initial_cycle} 天",
                size=12,
                color=TEXT_MUTED,
            )

            def refresh_item_list():
                rows = []
                for item in all_items:
                    item_id = item.get("id") or ""
                    selected = period_state.get("item_id") == item_id
                    color = PURPLE_BTN if selected else TEXT_MUTED
                    bg = PURPLE_SOFT if selected else "#FFFFFF"
                    border_color = PURPLE_BTN if selected else BORDER

                    def choose_item(_, current=item):
                        period_state["item_id"] = current.get("id") or ""
                        current_cycle = str(current.get("cycle_days") or 30)
                        cycle_tf.value = current_cycle
                        selected_hint.value = f"目前選擇：{item_display_name(current)}｜目前週期 {current_cycle} 天"
                        refresh_item_list()
                        try:
                            cycle_tf.update()
                            selected_hint.update()
                        except Exception:
                            safe_page_update()

                    rows.append(
                        ft.Container(
                            bgcolor=bg,
                            border=ft.border.all(1, border_color),
                            border_radius=12,
                            padding=ft.padding.symmetric(horizontal=12, vertical=10),
                            ink=True,
                            on_click=choose_item,
                            content=ft.Row(
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Icon(
                                        ft.Icons.CHECK_CIRCLE if selected else ft.Icons.CIRCLE_OUTLINED,
                                        size=18,
                                        color=color,
                                    ),
                                    ft.Column(
                                        expand=True,
                                        spacing=2,
                                        controls=[
                                            ft.Text(
                                                item_display_name(item),
                                                size=13,
                                                color=TEXT,
                                                weight=ft.FontWeight.W_600,
                                                max_lines=1,
                                                overflow=ft.TextOverflow.ELLIPSIS,
                                            ),
                                            ft.Text(
                                                f"{item.get('machine_area') or '-'}｜目前週期 {item.get('cycle_days') or 0} 天",
                                                size=12,
                                                color=TEXT_MUTED,
                                                max_lines=1,
                                                overflow=ft.TextOverflow.ELLIPSIS,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        )
                    )

                if not rows:
                    rows = [
                        ft.Container(
                            padding=12,
                            border=ft.border.all(1, BORDER),
                            border_radius=12,
                            content=ft.Text("目前沒有可編輯的保養項目。", size=13, color=TEXT_MUTED),
                        )
                    ]

                item_list_col.controls = rows
                try:
                    item_list_col.update()
                except Exception:
                    pass

            refresh_item_list()

            submit_btn = stable_filled_button(
                "更新週期",
                ft.Icons.SAVE_OUTLINED,
                bg=PURPLE_BTN,
                on_click=lambda e: on_submit(e),
                height=46,
            )

            def on_submit(_):
                if submit_btn.disabled:
                    return

                if not period_state.get("item_id"):
                    show_snack("請先選擇要編輯週期的保養項目。", success=False)
                    return

                cycle_days = to_int(cycle_tf.value, 0)
                if cycle_days <= 0:
                    show_snack("週期天數需為大於 0 的整數。", success=False)
                    return

                set_button_loading(page, submit_btn)

                payload = {
                    "item_id": period_state.get("item_id") or "",
                    "cycle_days": cycle_days,
                    "sort_order": None,
                    "is_active": (active_dd.value == "啟用"),
                }

                def worker():
                    result = update_item_cycle(**payload)
                    if not is_active_view():
                        return
                    if result.ok:
                        state["active_extension_form"] = None
                        load_data(update_sync_state=True)
                        rebuild()
                        hide_sync_badge_later(3.0)
                        show_snack(result.message, success=True)
                    else:
                        set_button_normal(page, submit_btn, "更新週期", ft.Icons.SAVE_OUTLINED)
                        show_snack(result.message, success=False)

                threading.Thread(target=worker, daemon=True).start()

            submit_btn.on_click = on_submit

            return card(
                padding=16,
                content=ft.Column(
                    spacing=12,
                    controls=[
                        section_title("編輯週期", "選取項目後會立即帶入目前週期天數，可再手動修改後儲存。"),
                        ft.Column(
                            spacing=6,
                            controls=[
                                form_label("保養項目", required=True),
                                selected_hint,
                                ft.Container(
                                    height=220,
                                    border=ft.border.all(1, BORDER),
                                    border_radius=14,
                                    padding=10,
                                    bgcolor="#F8FAFC",
                                    content=ft.Column(
                                        scroll=ft.ScrollMode.AUTO,
                                        controls=[item_list_col],
                                    ),
                                ),
                            ],
                        ),
                        cycle_group,
                        ft.Column(spacing=6, controls=[form_label("是否啟用"), active_dd]),
                        ft.Row(
                            spacing=10,
                            controls=[
                                stable_outline_button(
                                    "取消",
                                    ft.Icons.CLOSE,
                                    on_click=close_inline_form,
                                    height=46,
                                ),
                                ft.Container(expand=True, content=submit_btn),
                            ],
                        ),
                    ],
                ),
            )

        controls = [
            ft.ResponsiveRow(
                columns=12,
                spacing=10,
                run_spacing=10,
                controls=[
                    ft.Container(
                        col={"xs": 4, "sm": 4},
                        content=extension_action_button("新增清潔", ft.Icons.CLEANING_SERVICES_OUTLINED, BLUE_BTN, BLUE_SOFT, open_create_cleaning_dialog),
                    ),
                    ft.Container(
                        col={"xs": 4, "sm": 4},
                        content=extension_action_button("新增耗材", ft.Icons.INVENTORY_2_OUTLINED, ORANGE, ORANGE_SOFT, open_create_consumable_dialog),
                    ),
                    ft.Container(
                        col={"xs": 4, "sm": 4},
                        content=extension_action_button("編輯週期", ft.Icons.EVENT_REPEAT_OUTLINED, PURPLE_BTN, PURPLE_SOFT, open_update_cycle_dialog),
                    ),
                ],
            ),
        ]

        active_form = state.get("active_extension_form")
        if active_form == "clean":
            controls.append(build_clean_form())
        elif active_form == "material":
            controls.append(build_material_form())
        elif active_form == "period":
            controls.append(build_period_form())

        return ft.Column(
            spacing=10,
            controls=[
                section_title("擴充設定", "管理保養項目與週期設定"),
                ft.Column(spacing=12, controls=controls),
            ],
        )

    # =========================
    # Desktop Record Form
    # =========================

    def build_desktop_record_form() -> ft.Control:
        form_state = {
            "type": state["selected_type"],
            "item_id": None,
        }

        item_list_col = ft.Column(spacing=8)
        type_buttons_row = ft.Row(spacing=8)

        def build_type_button(label: str) -> ft.Container:
            active = form_state["type"] == label
            color = BLUE_BTN if label == "清潔" else ORANGE_BTN
            soft = BLUE_SOFT if label == "清潔" else ORANGE_SOFT
            border_color = color if active else BORDER
            bg = soft if active else "#FFFFFF"

            def choose_type(_):
                form_state["type"] = label
                form_state["item_id"] = None
                refresh_type_buttons()
                rebuild_item_options()

            return ft.Container(
                expand=True,
                ink=True,
                on_click=choose_type,
                bgcolor=bg,
                border=ft.border.all(1, border_color),
                border_radius=12,
                padding=ft.padding.symmetric(horizontal=10, vertical=11),
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=6,
                    controls=[
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE if active else ft.Icons.CIRCLE_OUTLINED,
                            size=17,
                            color=color if active else TEXT_MUTED,
                        ),
                        ft.Text(
                            label,
                            size=13,
                            color=color if active else TEXT_MUTED,
                            weight=ft.FontWeight.BOLD if active else ft.FontWeight.NORMAL,
                        ),
                    ],
                ),
            )

        def refresh_type_buttons():
            type_buttons_row.controls = [
                build_type_button("清潔"),
                build_type_button("耗材更換"),
            ]
            try:
                type_buttons_row.update()
            except Exception:
                pass

        def build_item_option(item: dict) -> ft.Container:
            item_id = item.get("id")
            is_selected = form_state.get("item_id") == item_id
            border_color = BLUE_BTN if is_selected else BORDER
            bg_color = BLUE_SOFT if is_selected else "#FFFFFF"
            text_color = BLUE_BTN if is_selected else TEXT

            def choose_item(_):
                form_state["item_id"] = item_id
                rebuild_item_options()

            return ft.Container(
                bgcolor=bg_color,
                border=ft.border.all(1, border_color),
                border_radius=12,
                padding=ft.padding.symmetric(horizontal=10, vertical=8),
                ink=True,
                on_click=choose_item,
                content=ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE if is_selected else ft.Icons.CIRCLE_OUTLINED,
                            size=17,
                            color=BLUE_BTN if is_selected else TEXT_MUTED,
                        ),
                        ft.Column(
                            expand=True,
                            spacing=2,
                            controls=[
                                ft.Text(
                                    item_display_name(item),
                                    size=13,
                                    color=text_color,
                                    weight=ft.FontWeight.W_600 if is_selected else ft.FontWeight.NORMAL,
                                ),
                                ft.Text(
                                    f"{item.get('main_category') or '-'}｜{item.get('machine_area') or '-'}",
                                    size=11,
                                    color=TEXT_MUTED,
                                ),
                            ],
                        ),
                    ],
                ),
            )

        def rebuild_item_options():
            current_type = form_state["type"]
            items = [
                item for item in get_all_items()
                if item.get("maintenance_type") == current_type
            ]

            if not items:
                item_list_col.controls = [
                    ft.Container(
                        padding=12,
                        border=ft.border.all(1, BORDER),
                        border_radius=12,
                        bgcolor="#FFFFFF",
                        content=ft.Text("目前沒有此類型的保養項目。", size=13, color=TEXT_MUTED),
                    )
                ]
            else:
                item_list_col.controls = [build_item_option(item) for item in items]

            try:
                item_list_col.update()
            except Exception:
                pass

        refresh_type_buttons()
        rebuild_item_options()

        date_tf = ft.TextField(label="執行日期", value=today_string(), hint_text="YYYY-MM-DD")
        operator_tf = ft.TextField(
            label="執行人員",
            value=session_get("user_name") or "",
            hint_text="請輸入執行人員",
        )

        result_dd = ft.Dropdown(
            label="結果",
            value="正常",
            options=[
                ft.dropdown.Option("正常"),
                ft.dropdown.Option("待確認"),
                ft.dropdown.Option("異常"),
            ],
        )

        note_tf = ft.TextField(
            label="備註",
            hint_text="可輸入保養說明",
            multiline=True,
            min_lines=3,
            max_lines=4,
        )

        submit_btn = stable_filled_button(
            "送出紀錄",
            ft.Icons.SAVE_OUTLINED,
            bg=BLUE_BTN,
            on_click=lambda e: on_submit(e),
            height=50,
        )

        def clear_form(_=None):
            form_state["item_id"] = None
            date_tf.value = today_string()
            operator_tf.value = session_get("user_name") or ""
            result_dd.value = "正常"
            note_tf.value = ""
            rebuild_item_options()
            date_tf.update()
            operator_tf.update()
            result_dd.update()
            note_tf.update()

        def on_submit(_):
            if submit_btn.disabled:
                return

            set_button_loading(page, submit_btn)
            payload = {
                "maintenance_item_id": form_state.get("item_id") or "",
                "executed_date": date_tf.value or "",
                "operator_name": operator_tf.value or "",
                "result": result_dd.value or "",
                "note": note_tf.value or "",
                "created_by_user_id": session_get("user_id"),
                "created_by_name": session_get("user_name"),
            }

            def worker():
                result = submit_maintenance_record(**payload)
                if not is_active_view():
                    return
                if result.ok:
                    load_data(update_sync_state=True)
                    clear_form()
                    rebuild()
                    hide_sync_badge_later(3.0)
                    show_snack(result.message, success=True)
                else:
                    set_button_normal(page, submit_btn, "送出紀錄", ft.Icons.SAVE_OUTLINED)
                    show_snack(result.message, success=False)

            threading.Thread(target=worker, daemon=True).start()

        submit_btn.on_click = on_submit

        return card(
            padding=18,
            content=ft.Column(
                spacing=14,
                controls=[
                    section_title("新增保養紀錄", "桌機版可直接在右側完成填寫"),
                    ft.Text("保養類型", size=13, color=TEXT_MUTED),
                    type_buttons_row,
                    ft.Text("保養項目", size=13, color=TEXT_MUTED),
                    ft.Container(
                        height=240,
                        border=ft.border.all(1, BORDER),
                        border_radius=14,
                        padding=10,
                        bgcolor="#F8FAFC",
                        content=ft.Column(
                            scroll=ft.ScrollMode.AUTO,
                            controls=[item_list_col],
                        ),
                    ),
                    date_tf,
                    operator_tf,
                    result_dd,
                    note_tf,
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.OutlinedButton(
                                "清除",
                                expand=True,
                                style=outline_button_style(),
                                on_click=clear_form,
                            ),
                            ft.Container(expand=True, content=submit_btn),
                        ],
                    ),
                ],
            ),
        )

    # =========================
    # Bottom Mobile Button
    # =========================

    def build_bottom_submit_button() -> ft.Control:
        return ft.Container(
            bgcolor="#FFFFFF",
            padding=ft.padding.only(left=16, right=16, top=10, bottom=18),
            border=ft.border.only(top=ft.BorderSide(1, BORDER)),
            content=ft.ElevatedButton(
                height=54,
                style=primary_button_style(),
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, size=22, color="#FFFFFF"),
                        ft.Text("新增保養紀錄", size=16, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                    ],
                ),
                on_click=open_record_dialog,
            ),
        )

    # =========================
    # Error Banner
    # =========================

    def build_error_banner() -> ft.Control:
        if not state["error_message"]:
            return ft.Container(height=0)

        return ft.Container(
            bgcolor=RED_SOFT,
            border=ft.border.all(1, "#FCA5A5"),
            border_radius=12,
            padding=12,
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.ERROR_OUTLINE, color=RED, size=22),
                    ft.Text(state["error_message"], expand=True, size=13, color=RED),
                    ft.TextButton("重試", on_click=lambda _: refresh()),
                ],
            ),
        )

    # =========================
    # Layout：手機
    # =========================

    def build_mobile_layout() -> ft.Control:
        page.bgcolor = BG

        body = ft.Container(
            padding=ft.padding.only(left=16, right=16, top=18, bottom=24),
            content=ft.Column(
                spacing=18,
                controls=[
                    build_header(),
                    build_error_banner(),
                    build_summary_cards(is_mobile=True),
                    ft.Container(
                        content=stable_filled_button(
                            "新增保養紀錄",
                            ft.Icons.ADD_CIRCLE_OUTLINE,
                            bg=BLUE_BTN,
                            on_click=open_record_dialog,
                            height=54,
                        ),
                    ),
                    build_type_tabs(),
                    build_filter_bar(),
                    build_today_tasks(),
                    build_item_list(),
                    build_recent_records(),
                    build_extension_settings(),
                    ft.Container(height=72),
                ],
            ),
        )

        return ft.Container(
            expand=True,
            content=ft.Column(
                expand=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[body],
            ),
        )

    # =========================
    # Layout：桌機
    # =========================

    def build_desktop_layout() -> ft.Control:
        page.bgcolor = BG

        left_content = ft.Container(
            expand=True,
            padding=ft.padding.only(left=24, top=24, right=18, bottom=24),
            content=ft.Column(
                expand=True,
                scroll=ft.ScrollMode.AUTO,
                spacing=18,
                controls=[
                    build_header(),
                    build_error_banner(),
                    build_summary_cards(is_mobile=False),
                    build_type_tabs(),
                    build_filter_bar(),
                    build_today_tasks(),
                    build_item_list(),
                    build_recent_records(),
                ],
            ),
        )

        right_panel = ft.Container(
            width=380,
            padding=ft.padding.only(top=24, right=24, bottom=24),
            content=ft.Column(
                expand=True,
                scroll=ft.ScrollMode.AUTO,
                spacing=18,
                controls=[
                    build_desktop_record_form(),
                    card(
                        padding=18,
                        content=build_extension_settings(),
                    ),
                ],
            ),
        )

        return ft.Row(
            expand=True,
            spacing=0,
            controls=[
                left_content,
                right_panel,
            ],
        )

    # =========================
    # 初始化
    # =========================

    width = page.width or 390
    main_host.content = build_mobile_layout() if width < MOBILE_WIDTH else build_desktop_layout()
    start_background_load(show_loading=True, render_loading=False)

    return root