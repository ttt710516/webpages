"""後端：網頁、上傳轉換、浮水印預覽、兌換碼解鎖下載、綠界付款。

只用 Python 標準函式庫（圖片浮水印另外需要 Pillow）。
    python3 server.py            # 預設 http://localhost:8000
    python3 server.py --port 9000
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import shutil
import smtplib
import sys
import threading
import time
import traceback
import uuid
from collections import defaultdict, deque
from email.message import EmailMessage
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import config
import converter
import db
import ecpay
import watermark

ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".musicxml", ".xml", ".mxl"}
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def safe_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(". ")
    return name[:120] or "upload"


def cleanup_old_jobs() -> None:
    if not config.JOBS_DIR.exists():
        return
    now = time.time()
    removed = []
    for d in config.JOBS_DIR.iterdir():
        if d.is_dir() and now - d.stat().st_mtime > config.JOB_TTL_SECONDS:
            shutil.rmtree(d, ignore_errors=True)
            removed.append(d.name)
    db.delete_unlocks(removed)


def job_meta(job_id: str) -> dict | None:
    if not JOB_ID_RE.match(job_id):
        return None
    meta = config.JOBS_DIR / job_id / "meta.json"
    if not meta.is_file():
        return None
    return json.loads(meta.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 兌換碼猜測的簡易限流：每個 IP 10 分鐘內最多錯 10 次
# ---------------------------------------------------------------------------
_fail_lock = threading.Lock()
_failures: dict[str, deque] = defaultdict(deque)
FAIL_WINDOW, FAIL_LIMIT = 600, 10


def too_many_failures(ip: str) -> bool:
    with _fail_lock:
        q = _failures[ip]
        while q and time.time() - q[0] > FAIL_WINDOW:
            q.popleft()
        return len(q) >= FAIL_LIMIT


def record_failure(ip: str) -> None:
    with _fail_lock:
        _failures[ip].append(time.time())


# ---------------------------------------------------------------------------
# 寄兌換碼
# ---------------------------------------------------------------------------

def send_code_email(order) -> None:
    if not order["email"]:
        return
    body = (
        f"感謝購買簡譜轉換點數！\n\n"
        f"兌換碼：{order['code']}\n"
        f"點數：{order['credits']} 次下載\n\n"
        f"在轉換結果頁面輸入兌換碼即可下載簡譜。\n"
        f"訂單頁面：{config.PUBLIC_BASE_URL}/order.html?t={order['token']}\n"
    )
    if not config.SMTP_HOST:
        print(f"[email 未設定 SMTP，略過寄信] to={order['email']}\n{body}")
        return

    def _send():
        try:
            msg = EmailMessage()
            msg["Subject"] = "您的簡譜轉換兌換碼"
            msg["From"] = config.SMTP_FROM
            msg["To"] = order["email"]
            msg.set_content(body)
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
                s.starttls()
                if config.SMTP_USER:
                    s.login(config.SMTP_USER, config.SMTP_PASSWORD)
                s.send_message(msg)
        except Exception:
            traceback.print_exc()

    threading.Thread(target=_send, daemon=True).start()


def handle_paid_notify(params: dict) -> str:
    """處理綠界付款結果通知（ReturnURL），回傳要回給綠界的字串。"""
    if not ecpay.verify(params):
        return "0|CheckMacValue Error"
    if params.get("MerchantID") != config.ECPAY_MERCHANT_ID:
        return "0|MerchantID Error"
    order = db.get_order_by_trade_no(params.get("MerchantTradeNo", ""))
    if order is None:
        return "0|Order Not Found"
    if params.get("TradeAmt") != str(order["amount"]):
        return "0|Amount Mismatch"
    if params.get("RtnCode") != "1":
        return "1|OK"  # 付款失敗的通知，記錄即可
    if params.get("SimulatePaid") == "1" and not config.TEST_MODE:
        return "1|OK"  # 正式環境下的「模擬付款」不能出貨
    order, newly_paid = db.mark_paid(order["trade_no"], params.get("TradeNo", ""))
    if newly_paid:
        print(f"[付款完成] {order['trade_no']} NT${order['amount']} → {order['code']}")
        send_code_email(order)
    return "1|OK"


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(config.STATIC_DIR), **kwargs)

    # ---------- helpers ----------
    def client_ip(self) -> str:
        return self.client_address[0]

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, status: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, file: Path, *, download_name: str | None = None) -> None:
        data = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "private, no-store")
        if download_name:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(download_name)}")
        self.end_headers()
        self.wfile.write(data)

    def read_body(self, limit: int = 64 * 1024) -> bytes | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            return None
        return self.rfile.read(length) if length > 0 else b""

    def read_json(self) -> dict:
        raw = self.read_body()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    def read_form(self) -> dict:
        raw = (self.read_body() or b"").decode("utf-8", "replace")
        # keep_blank_values：空白欄位也要參與 CheckMacValue 計算
        return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    # ---------- routing ----------
    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/packages":
                return self.api_packages()
            m = re.fullmatch(r"/api/result/([0-9a-f]{32})/(preview|download)", path)
            if m:
                return self.api_result(m.group(1), m.group(2))
            m = re.fullmatch(r"/api/orders/([A-Za-z0-9_-]{10,64})", path)
            if m:
                return self.api_order_status(m.group(1))
            if path.startswith("/api/"):
                return self.send_json(404, {"error": "Not found"})
        except Exception:
            traceback.print_exc()
            return self.send_json(500, {"error": "伺服器錯誤"})
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        routes = {
            "/api/convert": self.api_convert,
            "/api/unlock": self.api_unlock,
            "/api/code": self.api_code_balance,
            "/api/orders": self.api_create_order,
            "/api/ecpay/return": self.ecpay_return,
            "/api/ecpay/payment-info": self.ecpay_payment_info,
        }
        try:
            if path in routes:
                return routes[path]()
            m = re.fullmatch(r"/api/dev/simulate-pay/([A-Za-z0-9_-]{10,64})", path)
            if m and config.TEST_MODE:
                return self.dev_simulate_pay(m.group(1))
            self.send_json(404, {"error": "Not found"})
        except Exception:
            traceback.print_exc()
            self.send_json(500, {"error": "伺服器錯誤"})

    # ---------- 轉換 ----------
    def api_convert(self):
        cleanup_old_jobs()

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return self.send_json(400, {"error": "沒有收到檔案"})
        if length > config.MAX_UPLOAD_BYTES:
            return self.send_json(413, {"error": "檔案太大（上限 20 MB）"})

        filename = safe_filename(unquote(self.headers.get("X-Filename", "upload")))
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXT:
            return self.send_json(400, {"error": f"不支援的檔案格式：{ext or '無副檔名'}"})

        job_id = uuid.uuid4().hex
        job_dir = config.JOBS_DIR / job_id
        out_dir = job_dir / "out"
        out_dir.mkdir(parents=True)
        input_path = job_dir / filename
        input_path.write_bytes(self.rfile.read(length))

        try:
            result = Path(converter.convert(input_path, out_dir)).resolve()
        except converter.ConversionError as e:
            return self.send_json(422, {"error": str(e)})
        except Exception:
            traceback.print_exc()
            return self.send_json(500, {"error": "轉換時發生未預期的錯誤"})

        if not result.is_file() or result.parent != out_dir.resolve():
            return self.send_json(500, {"error": "轉換器沒有產生輸出檔"})

        try:
            preview = watermark.make_preview(result, job_dir)
        except watermark.PreviewUnsupported as e:
            return self.send_json(500, {"error": str(e)})

        meta = {"result": result.name, "preview": preview.name}
        (job_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

        self.send_json(200, {
            "id": job_id,
            "filename": result.name,
            "previewUrl": f"/api/result/{job_id}/preview",
            "previewMime": mimetypes.guess_type(preview.name)[0],
        })

    def api_result(self, job_id: str, kind: str):
        meta = job_meta(job_id)
        if meta is None:
            return self.send_json(404, {"error": "結果已過期，請重新上傳"})
        job_dir = config.JOBS_DIR / job_id
        if kind == "preview":
            return self.send_file(job_dir / meta["preview"])
        if not db.is_unlocked(job_id):
            return self.send_json(402, {"error": "請先輸入兌換碼解鎖下載"})
        return self.send_file(job_dir / "out" / meta["result"], download_name=meta["result"])

    # ---------- 兌換碼 ----------
    def api_unlock(self):
        ip = self.client_ip()
        if too_many_failures(ip):
            return self.send_json(429, {"error": "嘗試次數過多，請 10 分鐘後再試"})
        data = self.read_json()
        job_id = str(data.get("jobId", ""))
        code = str(data.get("code", ""))
        if job_meta(job_id) is None:
            return self.send_json(404, {"error": "結果已過期，請重新上傳"})

        status, left = db.unlock_job(job_id, code)
        if status == "invalid":
            record_failure(ip)
            return self.send_json(400, {"error": "兌換碼不正確"})
        if status == "empty":
            return self.send_json(400, {"error": "這組兌換碼的點數已用完"})
        self.send_json(200, {
            "downloadUrl": f"/api/result/{job_id}/download",
            "creditsLeft": left,
            "charged": status == "ok",
            "code": db.normalize_code(code),
        })

    def api_code_balance(self):
        ip = self.client_ip()
        if too_many_failures(ip):
            return self.send_json(429, {"error": "嘗試次數過多，請 10 分鐘後再試"})
        row = db.get_code(str(self.read_json().get("code", "")))
        if row is None:
            record_failure(ip)
            return self.send_json(404, {"error": "兌換碼不正確"})
        self.send_json(200, {"code": row["code"], "creditsLeft": row["credits_left"],
                             "creditsTotal": row["credits_total"]})

    # ---------- 訂單 ----------
    def api_packages(self):
        self.send_json(200, {
            "packages": [{"id": k, **v} for k, v in config.PACKAGES.items()],
            "payments": [{"id": k, "name": v} for k, v in config.PAYMENT_METHODS.items()],
            "testMode": config.TEST_MODE,
        })

    def api_create_order(self):
        data = self.read_json()
        pkg_id = data.get("package")
        payment = data.get("payment")
        email = (data.get("email") or "").strip() or None
        pkg = config.PACKAGES.get(pkg_id)
        if pkg is None:
            return self.send_json(400, {"error": "請選擇方案"})
        if payment not in config.PAYMENT_METHODS:
            return self.send_json(400, {"error": "請選擇付款方式"})
        if email and (len(email) > 200 or not EMAIL_RE.match(email)):
            return self.send_json(400, {"error": "Email 格式不正確"})

        trade_no = ecpay.new_trade_no()
        token = db.create_order(trade_no=trade_no, package_id=pkg_id, credits=pkg["credits"],
                                amount=pkg["price"], payment=payment, email=email)
        checkout = ecpay.build_checkout(
            trade_no=trade_no, amount=pkg["price"],
            item_name=f"簡譜轉換點數 {pkg['name']}", payment=payment, order_token=token,
        )
        self.send_json(200, {"token": token, "orderUrl": f"/order.html?t={token}", "checkout": checkout})

    def api_order_status(self, token: str):
        order = db.get_order_by_token(token)
        if order is None:
            return self.send_json(404, {"error": "找不到訂單"})
        pkg = config.PACKAGES.get(order["package_id"], {})
        resp = {
            "tradeNo": order["trade_no"],
            "packageName": pkg.get("name", order["package_id"]),
            "credits": order["credits"],
            "amount": order["amount"],
            "payment": order["payment"],
            "paymentName": config.PAYMENT_METHODS.get(order["payment"], order["payment"]),
            "status": order["status"],
            "paymentInfo": json.loads(order["payment_info"]) if order["payment_info"] else None,
            "createdAt": order["created_at"],
            "testMode": config.TEST_MODE,
        }
        if order["status"] == "paid":
            code = db.get_code(order["code"])
            resp["code"] = order["code"]
            resp["creditsLeft"] = code["credits_left"] if code else 0
        self.send_json(200, resp)

    # ---------- 綠界通知 ----------
    def ecpay_return(self):
        params = self.read_form()
        result = handle_paid_notify(params)
        if not result.startswith("1|"):
            print(f"[綠界通知被拒] {result} {params.get('MerchantTradeNo')}")
        self.send_text(200, result)

    def ecpay_payment_info(self):
        """ATM / 超商取號結果（PaymentInfoURL）。"""
        params = self.read_form()
        if not ecpay.verify(params) or params.get("MerchantID") != config.ECPAY_MERCHANT_ID:
            return self.send_text(200, "0|CheckMacValue Error")
        if params.get("RtnCode") in ("2", "10100073"):  # ATM 取號成功 / 超商取號成功
            keys = ("BankCode", "vAccount", "PaymentNo", "Barcode1", "Barcode2", "Barcode3", "ExpireDate")
            info = {k: params[k] for k in keys if params.get(k)}
            db.save_payment_info(params.get("MerchantTradeNo", ""), info)
        self.send_text(200, "1|OK")

    def dev_simulate_pay(self, token: str):
        """測試模式專用：模擬綠界送來付款成功通知（走同一套驗證流程）。"""
        order = db.get_order_by_token(token)
        if order is None:
            return self.send_json(404, {"error": "找不到訂單"})
        params = ecpay.simulated_paid_notify(trade_no=order["trade_no"], amount=order["amount"],
                                             payment=order["payment"])
        result = handle_paid_notify(params)
        if not result.startswith("1|"):
            return self.send_json(500, {"error": result})
        self.send_json(200, {"ok": True})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    sys.stdout.reconfigure(line_buffering=True)  # 導到檔案時也即時寫出 log
    mimetypes.add_type("image/svg+xml", ".svg")
    config.JOBS_DIR.mkdir(exist_ok=True)
    db.init()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    mode = "測試環境" if config.TEST_MODE else "正式環境"
    print(f"簡譜轉換服務啟動（綠界{mode}）：http://{args.host}:{args.port}")
    print(f"綠界通知網址：{config.PUBLIC_BASE_URL}/api/ecpay/return")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
