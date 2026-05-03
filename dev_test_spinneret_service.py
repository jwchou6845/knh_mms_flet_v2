from services.spinneret_service import (
    load_spinneret_page_data,
    update_spinneret_status,
)


def print_line():
    print("-" * 70)


def test_load():
    result = load_spinneret_page_data()
    print("讀取結果：", result.ok, result.message)

    data = result.data or {}

    print("KPI：", data.get("kpi"))

    for item in data.get("items", []):
        print(
            item["set_code"],
            item["current_status"],
            item["plate_spec"],
            item["status_updated_at"],
            item["updated_by_name"],
        )


def test_update():
    result = load_spinneret_page_data()

    if not result.ok:
        return

    items = result.data.get("items", [])

    if not items:
        print("沒有資料可測試更新。")
        return

    target = items[0]

    confirm = input(f"是否測試更新 {target['set_code']}？輸入 YES 確認：").strip()

    if confirm != "YES":
        print("略過更新測試。")
        return

    result = update_spinneret_status(
        row_id=target["id"],
        current_status=target["current_status"],
        plate_spec=target["plate_spec"],
        note=target.get("note", "") or "測試更新備註",
        updated_by_user_id=None,
        updated_by_name="系統測試",
    )

    print("更新結果：", result.ok, result.message)


def main():
    test_load()
    print_line()
    test_update()
    print_line()
    test_load()
    print_line()
    print("測試完成。")


if __name__ == "__main__":
    main()
