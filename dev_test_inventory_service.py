from services.inventory_service import (
    load_inventory_page_data,
    submit_purchase_record,
    submit_recycled_material,
    today_batch_prefix,
    today_dash_date,
)


def print_line():
    print("-" * 70)


def test_load():
    result = load_inventory_page_data()

    if not result.ok:
        print("讀取失敗：", result.message)
        return None

    data = result.data

    print("讀取成功")
    print("原料選項數量：", len(data["material_options"]))
    print("庫存列數：", len(data["stock_rows"]))
    print("最近進貨紀錄：", len(data["recent_purchase_records"]))
    print("最近回用料入庫：", len(data["recent_recycled_records"]))

    print_line()

    print("前 10 筆原料選項：")
    for name in list(data["material_options"].keys())[:10]:
        print("  ", name)

    print_line()

    print("前 10 筆即時庫存：")
    for row in data["stock_rows"][:10]:
        print(
            row["material_name"],
            "目前庫存:",
            row["current_stock_bags"],
            "包 /",
            row["current_stock_kg"],
            "KG",
            "低水位:",
            row["is_low_stock"],
        )

    return data


def test_submit_purchase(data):
    if not data["material_options"]:
        print("沒有原料資料，略過新料入庫測試。")
        return

    first_name = list(data["material_options"].keys())[0]
    first_id = data["material_options"][first_name]
    test_batch = f"{today_batch_prefix()}TEST"

    confirm = input(f"是否新增一筆進貨測試？原料：{first_name}，批號：{test_batch}，輸入 YES 確認：").strip()

    if confirm != "YES":
        print("略過進貨寫入測試。")
        return

    result = submit_purchase_record(
        purchase_batch_no=test_batch,
        purchase_date=today_dash_date(),
        material_id=first_id,
        quantity_bags=1,
        created_by_user_id=None,
        created_by_name="系統測試",
    )

    print("進貨寫入結果：", result.ok, result.message)


def test_submit_recycled():
    test_no = f"{today_batch_prefix()}TEST"

    confirm = input(f"是否新增一筆回用料測試？編號：{test_no}，輸入 YES 確認：").strip()

    if confirm != "YES":
        print("略過回用料寫入測試。")
        return

    result = submit_recycled_material(
        recycled_no=test_no,
        inbound_date=today_dash_date(),
        material_type="PET",
        source_machine="S1",
        weight_kg=1,
        supplier="系統測試",
    )

    print("回用料寫入結果：", result.ok, result.message)


def main():
    data = test_load()

    if not data:
        return

    print_line()
    test_submit_purchase(data)

    print_line()
    test_submit_recycled()

    print_line()
    print("測試完成。")


if __name__ == "__main__":
    main()