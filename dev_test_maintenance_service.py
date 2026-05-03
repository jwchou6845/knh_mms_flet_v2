from services.maintenance_service import load_maintenance_page_data


def main():
    result = load_maintenance_page_data()

    if not result.ok:
        print("讀取失敗：", result.message)
        return

    data = result.data

    print("保養項目總數：", len(data["items"]))
    print("清潔項目數：", len(data["items_by_type"]["清潔"]))
    print("耗材更換項目數：", len(data["items_by_type"]["耗材更換"]))
    print("今日待辦數：", len(data["today_tasks"]))
    print("最近紀錄數：", len(data["recent_records"]))
    print("摘要：", data["summary"])

    print("\n前 5 筆保養項目：")
    for item in data["items"][:5]:
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


if __name__ == "__main__":
    main()