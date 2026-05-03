from repositories.maintenance_repo import get_active_maintenance_items


def main():
    items = get_active_maintenance_items()

    print(f"共讀取 {len(items)} 筆保養項目")
    print("-" * 60)

    for item in items:
        print(
            item["sort_order"],
            item["maintenance_type"],
            item["main_category"],
            item.get("sub_category") or "-",
            item["item_name"],
            item.get("machine_area") or "-",
        )


if __name__ == "__main__":
    main()