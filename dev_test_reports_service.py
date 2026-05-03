from services.reports_service import (
    QUICK_REPORTS,
    run_advanced_query,
    run_quick_report,
)


def print_line():
    print("-" * 70)


def show_result(title, result):
    print(title, "=>", result.ok, result.message)

    if not result.ok:
        return

    data = result.data or {}

    print("報表：", data.get("title"))
    print("摘要：", data.get("summary_text"))
    print("筆數：", data.get("count"))
    print("欄位：", data.get("columns"))

    for row in data.get("rows", [])[:5]:
        print(row)


def main():
    print("快速報表測試")
    print_line()

    for report_name in QUICK_REPORTS:
        result = run_quick_report(report_name)
        show_result(report_name, result)
        print_line()

    print("全條件篩選測試")
    result = run_advanced_query(
        data_type="打料紀錄",
        start_date="2026/05/01",
        end_date="2026/05/31",
        category="全部",
        material_name="",
        supplier="全部",
        machine="全部",
        user_name="全部",
    )
    show_result("打料紀錄", result)
    print_line()

    print("測試完成。")


if __name__ == "__main__":
    main()
