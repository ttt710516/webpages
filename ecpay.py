"""綠界全方位金流（AIO）：建立訂單參數、計算與驗證 CheckMacValue。"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import config

TAIPEI = timezone(timedelta(hours=8))

# 綠界的 CheckMacValue 以 .NET 的 UrlEncode 為準，和 Python 的 quote_plus 有幾個字元不同
_DOTNET_FIXES = {"%21": "!", "%2a": "*", "%28": "(", "%29": ")", "~": "%7e"}


def check_mac_value(params: dict) -> str:
    items = sorted(
        ((k, v) for k, v in params.items() if k != "CheckMacValue"),
        key=lambda kv: kv[0].lower(),
    )
    raw = "&".join(f"{k}={v}" for k, v in items)
    raw = f"HashKey={config.ECPAY_HASH_KEY}&{raw}&HashIV={config.ECPAY_HASH_IV}"
    encoded = quote_plus(raw).lower()
    for src, dst in _DOTNET_FIXES.items():
        encoded = encoded.replace(src, dst)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest().upper()


def verify(params: dict) -> bool:
    given = params.get("CheckMacValue", "")
    return bool(given) and hmac.compare_digest(given.upper(), check_mac_value(params))


def new_trade_no() -> str:
    """MerchantTradeNo：最多 20 碼英數字，不可重複。"""
    stamp = datetime.now(TAIPEI).strftime("%y%m%d%H%M%S")
    rand = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    return f"MC{stamp}{rand}"


def build_checkout(*, trade_no: str, amount: int, item_name: str,
                   payment: str, order_token: str) -> dict:
    """回傳 {action, fields}，由前端組成 form 送到綠界。"""
    base = config.PUBLIC_BASE_URL
    params = {
        "MerchantID": config.ECPAY_MERCHANT_ID,
        "MerchantTradeNo": trade_no,
        "MerchantTradeDate": datetime.now(TAIPEI).strftime("%Y/%m/%d %H:%M:%S"),
        "PaymentType": "aio",
        "TotalAmount": str(amount),
        "TradeDesc": "簡譜轉換點數",
        "ItemName": item_name,
        "ReturnURL": f"{base}/api/ecpay/return",
        "PaymentInfoURL": f"{base}/api/ecpay/payment-info",
        "ClientBackURL": f"{base}/order.html?t={order_token}",
        "ChoosePayment": payment,
        "EncryptType": "1",
        "NeedExtraPaidInfo": "N",
    }
    if payment == "ATM":
        params["ExpireDate"] = str(config.ATM_EXPIRE_DAYS)
    params["CheckMacValue"] = check_mac_value(params)
    return {"action": config.ECPAY_CHECKOUT_URL, "fields": params}


def simulated_paid_notify(*, trade_no: str, amount: int, payment: str) -> dict:
    """（僅測試模式）產生一份跟綠界付款成功通知一樣格式、已簽章的資料。"""
    now = datetime.now(TAIPEI).strftime("%Y/%m/%d %H:%M:%S")
    params = {
        "MerchantID": config.ECPAY_MERCHANT_ID,
        "MerchantTradeNo": trade_no,
        "StoreID": "",
        "RtnCode": "1",
        "RtnMsg": "交易成功",
        "TradeNo": "SIM" + secrets.token_hex(6).upper(),
        "TradeAmt": str(amount),
        "PaymentDate": now,
        "PaymentType": f"{payment}_SIM",
        "PaymentTypeChargeFee": "0",
        "TradeDate": now,
        "SimulatePaid": "1",
        "CustomField1": "", "CustomField2": "", "CustomField3": "", "CustomField4": "",
    }
    params["CheckMacValue"] = check_mac_value(params)
    return params
