from services.dryer_status_service import (
    load_dryer_status,
    save_dryer_status,
)


def print_line():
    print("-" * 70)


def test_load():
    result = load_dryer_status()

    if not result.ok:
        print("讀取失敗：", result.message)
        return

    print("讀取成功")
    print("最新更新：", result.data["latest_updated"])

    for item in result.data["items"]:
        print(
            item["tower_code"],
            item["tower_type"],
            item["material"],
            f'{item["percent"]}%',
            item["note"],
            item["updated_at"],
            item["updated_by_name"],
        )


def test_save():
    confirm = input("是否測試更新 S1-PET？輸入 YES 確認：").strip()

    if confirm != "YES":
        print("略過寫入測試。")
        return

    result = save_dryer_status(
        tower_code="S1-PET",
        material="PET308A-南紡",
        percent=65,
        note="測試寫入，確認後可再改回實際狀態。",
        updated_by_user_id=None,
        updated_by_name="系統測試",
    )

    print("寫入結果：", result.ok, result.message)


def main():
    test_load()
    print_line()
    test_save()
    print_line()
    test_load()


if __name__ == "__main__":
    main()