from db.supabase_client import SUPABASE_URL, SUPABASE_KEY, supabase


def main():
    print("Supabase URL:", SUPABASE_URL)
    print("Supabase Key 前綴:", SUPABASE_KEY[:20] + "...")
    print("Supabase client 建立成功:", supabase is not None)


if __name__ == "__main__":
    main()