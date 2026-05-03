from services.auth_service import authenticate_user


def main():
    employee_id = input("請輸入員工編號：").strip()
    password = input("請輸入密碼：").strip()

    result = authenticate_user(employee_id, password)

    if not result.ok:
        print("登入失敗：", result.message)
        return

    user = result.data

    print("登入成功")
    print("使用者 ID：", user.get("id"))
    print("員工編號：", user.get("employee_id"))
    print("姓名：", user.get("name"))
    print("角色：", user.get("role"))
    print("是否啟用：", user.get("is_active"))
    print("必須修改密碼：", user.get("must_change_password"))
    print("快捷功能：", user.get("quick_shortcuts"))


if __name__ == "__main__":
    main()