import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client, Client


# 讀取專案根目錄的 .env
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH)


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


if not SUPABASE_URL:
    raise RuntimeError("缺少 SUPABASE_URL，請確認 .env 是否已設定。")

if not SUPABASE_KEY:
    raise RuntimeError("缺少 SUPABASE_KEY，請確認 .env 是否已設定。")


supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)