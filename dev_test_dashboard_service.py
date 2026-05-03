from services.dashboard_service import load_dashboard_page_data


def print_line():
    print("-" * 70)


def main():
    result = load_dashboard_page_data()

    if not result.ok:
        print("讀取失敗：", result.message)
        return

    data = result.data

    print("讀取成功")
    print("目前月份：", data["current_ym"])
    print("更新時間：", data["current_time"])
    print("新料庫存筆數：", len(data["new_stock_data"]))
    print("回用料庫存筆數：", len(data["recycled_stock_data"]))
    print("低水位項目：", len(data["alert_items"]))

    print_line()
    print("本月用量摘要：")
    for category, rows in data["usage_summary"].items():
        print(category, len(rows), "項")
        for name, item in list(rows.items())[:5]:
            print(
                "  ",
                name,
                "本月:", int(item["this_month"]), "KG",
                "上月:", int(item["last_month"]), "KG",
                "history:", [int(x) for x in item.get("history", [])],
            )

    print_line()
    maintenance = data["maintenance_summary"]
    print("保養摘要：")
    print("待追蹤：", maintenance["total"])
    print("逾期：", maintenance["overdue"])
    print("今日：", maintenance["today"])
    print("近期異常：", maintenance["abnormal"])
    print("預覽：")
    for item in maintenance["preview"]:
        print("  ", item["due_tag"], item["item_name"], item["maintenance_type"], item["machine_area"], item["next_date"])

    print_line()
    print("測試完成。")


if __name__ == "__main__":
    main()
