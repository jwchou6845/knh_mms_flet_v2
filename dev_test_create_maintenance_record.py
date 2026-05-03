from services.maintenance_service import (
    load_maintenance_page_data,
    submit_maintenance_record,
)


def main():
    # 先讀取目前保養項目
    page_result = load_maintenance_page_data()

    if not page_result.ok:
        print("讀取保養資料失敗：", page_result.message)
        return

    data = page_result.data
    items = data["items"]

    if not items:
        print("目前沒有任何保養項目，請先確認 maintenance_items 是否有資料。")
        return

    # 取第一筆保養項目做測試
    first_item = items[0]

    print("準備新增測試保養紀錄")
    print("項目 ID：", first_item["id"])
    print("項目名稱：", first_item["item_name"])
    print("保養類型：", first_item["maintenance_type"])
    print("-" * 60)

    # 新增一筆保養紀錄
    submit_result = submit_maintenance_record(
        maintenance_item_id=first_item["id"],
        executed_date="2026-05-01",
        operator_name="測試人員",
        result="正常",
        note="這是 Supabase 寫入測試資料",
        created_by_user_id=None,
        created_by_name="系統測試",
    )

    if not submit_result.ok:
        print("新增失敗：", submit_result.message)
        return

    print("新增成功：", submit_result.message)
    print("新增資料：", submit_result.data)
    print("-" * 60)

    # 重新讀取，確認 service 計算是否更新
    reload_result = load_maintenance_page_data()

    if not reload_result.ok:
        print("重新讀取失敗：", reload_result.message)
        return

    reload_data = reload_result.data

    print("重新讀取成功")
    print("保養項目總數：", len(reload_data["items"]))
    print("最近紀錄數：", len(reload_data["recent_records"]))
    print("摘要：", reload_data["summary"])
    print("-" * 60)

    print("前 3 筆保養項目狀態：")
    for item in reload_data["items"][:3]:
        print(
            item["maintenance_type"],
            item["item_name"],
            "最近：",
            item["last_date"],
            "下次：",
            item["next_date"],
            "狀態：",
            item["status"],
        )

    print("-" * 60)
    print("最近保養紀錄：")
    for record in reload_data["recent_records"][:5]:
        print(
            record["date_short"],
            record["maintenance_type"],
            record["item_name"],
            record["result"],
            record["operator_name"],
        )


if __name__ == "__main__":
    main()