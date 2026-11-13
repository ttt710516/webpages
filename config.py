"""設定集中在這裡；正式上線時用環境變數覆寫，不要把正式金鑰寫進程式碼。"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
JOBS_DIR = ROOT / "jobs"
DB_PATH = Path(os.environ.get("DB_PATH", ROOT / "data.sqlite3"))

# 網站對外網址。綠界的付款通知（ReturnURL / PaymentInfoURL）會打到這裡，
# 所以正式環境必須是綠界連得到的公開網址（https）。
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")

# ---------------------------------------------------------------------------
# 綠界
# ---------------------------------------------------------------------------
ECPAY_MODE = os.environ.get("ECPAY_MODE", "test")  # "test" 或 "prod"
TEST_MODE = ECPAY_MODE != "prod"

if TEST_MODE:
    # 綠界公開的全方位金流測試帳號
    ECPAY_MERCHANT_ID = os.environ.get("ECPAY_MERCHANT_ID", "2000132")
    ECPAY_HASH_KEY = os.environ.get("ECPAY_HASH_KEY", "5294y06JbISpM5x9")
    ECPAY_HASH_IV = os.environ.get("ECPAY_HASH_IV", "v77hoKGq4kWxNNIS")
    ECPAY_CHECKOUT_URL = "https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5"
else:
    ECPAY_MERCHANT_ID = os.environ["ECPAY_MERCHANT_ID"]
    ECPAY_HASH_KEY = os.environ["ECPAY_HASH_KEY"]
    ECPAY_HASH_IV = os.environ["ECPAY_HASH_IV"]
    ECPAY_CHECKOUT_URL = "https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5"

# 可選的付款方式（不含信用卡）
PAYMENT_METHODS = {
    "ATM": "ATM 轉帳（虛擬帳號）",
    "CVS": "超商代碼繳費",
    "BARCODE": "超商條碼繳費",
}
ATM_EXPIRE_DAYS = 3

# ---------------------------------------------------------------------------
# 點數方案（id: 名稱 / 點數 / 價格 NT$）
# ---------------------------------------------------------------------------
PACKAGES = {
    "p10":  {"name": "10 次下載",  "credits": 10,  "price": 100},
    "p30":  {"name": "30 次下載",  "credits": 30,  "price": 250},
    "p100": {"name": "100 次下載", "credits": 100, "price": 700},
}

# ---------------------------------------------------------------------------
# 其他
# ---------------------------------------------------------------------------
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
JOB_TTL_SECONDS = 24 * 60 * 60  # 轉換結果保留 24 小時（含已解鎖的）
WATERMARK_TEXT = os.environ.get("WATERMARK_TEXT", "預覽版 PREVIEW")

# 寄送兌換碼的 SMTP（選填；沒設定就不寄信，只在訂單頁顯示）
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
