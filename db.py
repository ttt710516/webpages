"""SQLite 資料存取：訂單、兌換碼、已解鎖的轉換結果。"""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    token         TEXT PRIMARY KEY,          -- 給客人看訂單狀態用的祕密 token
    trade_no      TEXT UNIQUE NOT NULL,      -- 綠界 MerchantTradeNo
    package_id    TEXT NOT NULL,
    credits       INTEGER NOT NULL,
    amount        INTEGER NOT NULL,
    payment       TEXT NOT NULL,             -- ATM / CVS / BARCODE
    email         TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending / awaiting_payment / paid
    payment_info  TEXT,                      -- 取號資訊 JSON（虛擬帳號、繳費代碼…）
    ecpay_trade_no TEXT,
    code          TEXT,
    created_at    REAL NOT NULL,
    paid_at       REAL
);
CREATE TABLE IF NOT EXISTS codes (
    code          TEXT PRIMARY KEY,
    credits_total INTEGER NOT NULL,
    credits_left  INTEGER NOT NULL,
    source        TEXT NOT NULL,             -- order:<trade_no> 或 manual
    created_at    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS unlocks (
    job_id        TEXT PRIMARY KEY,
    code          TEXT NOT NULL,
    created_at    REAL NOT NULL
);
"""

# 去掉容易混淆的 0/O、1/I/L
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


@contextmanager
def connect():
    conn = sqlite3.connect(config.DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init() -> None:
    with connect() as c:
        c.executescript(SCHEMA)
        c.execute("PRAGMA journal_mode=WAL")


def normalize_code(code: str) -> str:
    code = "".join(ch for ch in code.upper() if ch.isalnum())
    return "-".join(code[i:i + 4] for i in range(0, len(code), 4))


def _new_code() -> str:
    return normalize_code("".join(secrets.choice(CODE_ALPHABET) for _ in range(12)))


def create_code(c: sqlite3.Connection, credits: int, source: str) -> str:
    while True:
        code = _new_code()
        try:
            c.execute(
                "INSERT INTO codes (code, credits_total, credits_left, source, created_at) VALUES (?,?,?,?,?)",
                (code, credits, credits, source, time.time()),
            )
            return code
        except sqlite3.IntegrityError:
            continue  # 極小機率撞號，重抽


# ---------- 訂單 ----------

def create_order(*, trade_no: str, package_id: str, credits: int, amount: int,
                 payment: str, email: str | None) -> str:
    token = secrets.token_urlsafe(24)
    with connect() as c:
        c.execute(
            "INSERT INTO orders (token, trade_no, package_id, credits, amount, payment, email, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (token, trade_no, package_id, credits, amount, payment, email, time.time()),
        )
    return token


def get_order_by_token(token: str):
    with connect() as c:
        return c.execute("SELECT * FROM orders WHERE token=?", (token,)).fetchone()


def get_order_by_trade_no(trade_no: str):
    with connect() as c:
        return c.execute("SELECT * FROM orders WHERE trade_no=?", (trade_no,)).fetchone()


def save_payment_info(trade_no: str, info: dict) -> None:
    with connect() as c:
        c.execute(
            "UPDATE orders SET payment_info=?, status='awaiting_payment' "
            "WHERE trade_no=? AND status='pending'",
            (json.dumps(info, ensure_ascii=False), trade_no),
        )


def mark_paid(trade_no: str, ecpay_trade_no: str):
    """把訂單標記為已付款並發兌換碼。重複通知時不會重複發碼。

    回傳 (order_row, newly_paid: bool)
    """
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        try:
            order = c.execute("SELECT * FROM orders WHERE trade_no=?", (trade_no,)).fetchone()
            if order is None:
                c.execute("ROLLBACK")
                return None, False
            if order["status"] == "paid":
                c.execute("COMMIT")
                return order, False
            code = create_code(c, order["credits"], f"order:{trade_no}")
            c.execute(
                "UPDATE orders SET status='paid', code=?, ecpay_trade_no=?, paid_at=? WHERE trade_no=?",
                (code, ecpay_trade_no, time.time(), trade_no),
            )
            order = c.execute("SELECT * FROM orders WHERE trade_no=?", (trade_no,)).fetchone()
            c.execute("COMMIT")
            return order, True
        except Exception:
            c.execute("ROLLBACK")
            raise


# ---------- 兌換碼 / 解鎖 ----------

def get_code(code: str):
    with connect() as c:
        return c.execute("SELECT * FROM codes WHERE code=?", (normalize_code(code),)).fetchone()


def is_unlocked(job_id: str) -> bool:
    with connect() as c:
        return c.execute("SELECT 1 FROM unlocks WHERE job_id=?", (job_id,)).fetchone() is not None


def unlock_job(job_id: str, code: str):
    """用兌換碼解鎖一份轉換結果，扣 1 點；同一份結果重複解鎖不再扣點。

    回傳 (status, credits_left)：status 為 ok / already / invalid / empty
    """
    code = normalize_code(code)
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        try:
            row = c.execute("SELECT credits_left FROM codes WHERE code=?", (code,)).fetchone()
            if row is None:
                c.execute("ROLLBACK")
                return "invalid", 0
            if c.execute("SELECT 1 FROM unlocks WHERE job_id=?", (job_id,)).fetchone():
                c.execute("COMMIT")
                return "already", row["credits_left"]
            if row["credits_left"] <= 0:
                c.execute("ROLLBACK")
                return "empty", 0
            c.execute("UPDATE codes SET credits_left = credits_left - 1 WHERE code=?", (code,))
            c.execute("INSERT INTO unlocks (job_id, code, created_at) VALUES (?,?,?)",
                      (job_id, code, time.time()))
            c.execute("COMMIT")
            return "ok", row["credits_left"] - 1
        except Exception:
            c.execute("ROLLBACK")
            raise


def delete_unlocks(job_ids: list[str]) -> None:
    if not job_ids:
        return
    with connect() as c:
        c.executemany("DELETE FROM unlocks WHERE job_id=?", [(j,) for j in job_ids])
