# config.py
import os
from dotenv import load_dotenv
from pyairtable import Api

# 載入環境變數 (.env)
load_dotenv()

# 1. 集中管理金鑰
API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")

# 2. 建立共用的 Airtable 連線引擎
airtable_api = Api(API_KEY)

# 3. 集中管理所有表格 ID (這就是你的 TABLE_MAP！)
TABLES = {
    "原料庫存表": "tblvO5KmjqTHTKF7I", # 原料庫存表
    "回用料庫存清單": "tblCUV3bAbyURU25h", # 回用料庫存清單
    "新料打料紀錄": "tbltEaIlL51PpmX8Y", # 原乾燥打料紀錄表
    "回用料打料紀錄": "tblroNGCFmn6KOrPF", # 回用料打料紀錄表
    "原料新料入庫": "tbl6F64iGNELhgb0q", # 進貨紀錄表
    "噴頭組件狀態": "tblVJYfoPmhlXaflh", # 噴頭組件狀態  
    "交接班紀錄表": "tbllZIJKYLqEkHUha", # 交接班紀錄表
    "使用者權限表": "tblrOyaE15IfRs8uY", # 使用者權限表
    "交接項目明細": "tblntcLILh4JBdKW5", # 交接項目明細
    "密碼重設申請表": "tblPIHaI6ZaBk8Pg8", # 密碼重設申請表

}