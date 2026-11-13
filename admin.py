"""管理工具：手動發兌換碼（贈送、銀行轉帳客人）、查詢兌換碼與訂單。

    python3 admin.py create-code 10        # 發一組 10 點的兌換碼
    python3 admin.py code ABCD-EFGH-JKMN   # 查兌換碼剩餘點數
    python3 admin.py orders [--all]        # 列出最近訂單（預設只列已付款）
"""

from __future__ import annotations

import argparse
from datetime import datetime

import db


def fmt_time(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "-"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-code", help="手動發兌換碼")
    p.add_argument("credits", type=int)
    p = sub.add_parser("code", help="查詢兌換碼")
    p.add_argument("code")
    p = sub.add_parser("orders", help="列出訂單")
    p.add_argument("--all", action="store_true", help="包含未付款")
    p.add_argument("-n", type=int, default=30)
    args = ap.parse_args()

    db.init()
    if args.cmd == "create-code":
        if args.credits <= 0:
            ap.error("點數必須大於 0")
        with db.connect() as c:
            print(db.create_code(c, args.credits, "manual"))
    elif args.cmd == "code":
        row = db.get_code(args.code)
        if row is None:
            print("找不到這組兌換碼")
            return
        print(f"{row['code']}  剩餘 {row['credits_left']}/{row['credits_total']} 點  "
              f"來源 {row['source']}  建立 {fmt_time(row['created_at'])}")
    elif args.cmd == "orders":
        sql = "SELECT * FROM orders" + ("" if args.all else " WHERE status='paid'") + \
              " ORDER BY created_at DESC LIMIT ?"
        with db.connect() as c:
            rows = c.execute(sql, (args.n,)).fetchall()
        for r in rows:
            print(f"{fmt_time(r['created_at'])}  {r['trade_no']}  NT${r['amount']:<4}  {r['payment']:<7}  "
                  f"{r['status']:<16}  {r['code'] or ''}  {r['email'] or ''}")
        if not rows:
            print("（沒有訂單）")


if __name__ == "__main__":
    main()
