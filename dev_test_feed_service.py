from services.feed_service import (
    load_feed_page_data,
    submit_material_feed_record,
    submit_recycled_feed_record,
    today_slash_date,
)


def print_line():
    print("-" * 70)


def test_load():
    result = load_feed_page_data()

    if not result.ok:
        print("讀取失敗：", result.message)
        return None

    data = result.data

    print("讀取成功")
    print("新料數量：", len(data["new_materials"]))
    print("母粒數量：", len(data["aux_materials"]))
    print("在庫回用料數量：", len(data["rec_materials"]))
    print("低水位數量：", len(data["low_stock_items"]))
    print("最近紀錄數量：", len(data["recent_records"]))

    print_line()

    print("前 5 筆新料：")
    for name in list(data["new_materials"].keys())[:5]:
        print("  ", name)

    print_line()

    print("前 5 筆母粒：")
    for name in list(data["aux_materials"].keys())[:5]:
        print("  ", name)

    print_line()

    print("前 5 筆回用料：")
    for name in list(data["rec_materials"].keys())[:5]:
        print("  ", name)

    print_line()

    print("最近 5 筆紀錄：")
    for record in data["recent_records"][:5]:
        print(
            record["date"],
            record["time"],
            record["type"],
            record["material"],
            record["qty"],
        )

    return data


def test_submit_new_material(data):
    if not data["new_materials"]:
        print("沒有新料資料，略過新料寫入測試。")
        return

    first_name = list(data["new_materials"].keys())[0]
    first_id = data["new_materials"][first_name]

    confirm = input(f"是否新增一筆新料測試紀錄？原料：{first_name}，輸入 YES 確認：").strip()

    if confirm != "YES":
        print("略過新料寫入測試。")
        return

    result = submit_material_feed_record(
        feed_type="new",
        material_id=first_id,
        batch_no="TEST-BATCH",
        feed_date=today_slash_date(),
        machine_code="S1-PET",
        quantity_bags=1,
        operator_name="系統測試",
        note="dev_test_feed_service.py 測試",
        created_by_user_id=None,
        created_by_name="系統測試",
    )

    print("新料寫入結果：", result.ok, result.message)


def test_submit_recycled(data):
    if not data["rec_materials"]:
        print("沒有在庫回用料，略過回用料寫入測試。")
        return

    first_name = list(data["rec_materials"].keys())[0]
    first_id = data["rec_materials"][first_name]

    confirm = input(
        f"是否新增一筆回用料測試紀錄？此動作會把該回用料標記為已領用：{first_name}，輸入 YES 確認："
    ).strip()

    if confirm != "YES":
        print("略過回用料寫入測試。")
        return

    result = submit_recycled_feed_record(
        recycled_material_id=first_id,
        feed_date=today_slash_date(),
        machine_code="S1-PET",
        operator_name="系統測試",
        created_by_user_id=None,
        created_by_name="系統測試",
    )

    print("回用料寫入結果：", result.ok, result.message)


def main():
    data = test_load()

    if not data:
        return

    print_line()
    test_submit_new_material(data)

    print_line()
    test_submit_recycled(data)

    print_line()
    print("測試完成。")


if __name__ == "__main__":
    main()