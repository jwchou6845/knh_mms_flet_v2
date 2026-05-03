from services.handover_service import (
    load_handover_form_data,
    load_open_handover_tasks,
    submit_handover_record,
)


def print_line():
    print("-" * 70)


def test_form_loader():
    result = load_handover_form_data(current_user_name="周正偉")
    print("接班人清單：", result.ok, result.message)

    if result.data:
        print("今日：", result.data.get("today"))
        print("接班人選項：", result.data.get("receiver_options", [])[:10])


def test_submit():
    confirm = input("是否測試新增一筆交接紀錄？輸入 YES 確認：").strip()

    if confirm != "YES":
        print("略過新增測試。")
        return

    result = submit_handover_record(
        handover_date="2026-05-03",
        shift="夜班",
        sender_name="周正偉",
        receiver_name="系統測試接班人",
        machine_status=[
            {"name": "S1", "status": "正常"},
            {"name": "S2", "status": "注意"},
            {"name": "空壓", "status": "正常"},
        ],
        abnormal_note="測試：S2 狀態注意，確認 Supabase 交接寫入。",
        todo_note="測試：接班人確認此項目後可標記完成。",
        created_by_user_id=None,
        created_by_name="周正偉",
    )

    print("新增結果：", result.ok, result.message)


def test_tasks():
    result = load_open_handover_tasks(
        current_user_name="周正偉",
        can_view_all_tasks=True,
    )

    print("待辦讀取：", result.ok, result.message)

    for task in (result.data or {}).get("tasks", [])[:10]:
        print(task["type"], task["severity"], task["source"], task["content"])


def main():
    test_form_loader()
    print_line()
    test_submit()
    print_line()
    test_tasks()
    print_line()
    print("測試完成。")


if __name__ == "__main__":
    main()
