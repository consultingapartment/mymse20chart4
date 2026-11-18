#!/usr/bin/env python3
"""chart4report — зохиомол өгөгдлөөр бүх командыг ажиллуулж шалгана (сүлжээ, Telegram ашиглахгүй).

    python tests/smoke.py

Шалгах зүйл: 4 чарт + auto, нийт өгөөжийн хувилбар, Excel, ±15% илрүүлэлт, хуваалтын засвар, мэдэгдлийн логик, индексийн задлагч.
"""
import csv
import json
import os
import random
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAIL = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def run(args, env):
    r = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:])
    return r


def make_data(data_dir):
    sys.path.insert(0, str(ROOT))
    os.environ["DATA_DIR"] = str(data_dir)
    import history_mse as H
    H.HIST_DIR.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(7)
    starts = {k: date(2015, 1, 5) for k in H.KEYS}
    starts.update(KHAN=date(2023, 5, 1), TDB=date(2023, 5, 1), QPAY=date(2024, 3, 15), ADB=date(2021, 3, 2))
    end = date(2026, 10, 30)
    for k in H.KEYS:
        px, d, bars = 200 + 900 * rnd.random(), starts[k], {}
        while d <= end:
            if d.weekday() < 5 and not (k == "INV" and date(2026, 2, 1) <= d <= date(2026, 3, 31)):
                px *= 1 + rnd.gauss(0.0003, 0.012)
                if k == "MFC" and d == date(2024, 6, 3):
                    px *= 0.1                               # бүртгэлтэй хуваалт
                if k == "SBM" and d == date(2025, 1, 6):
                    px *= 1.6                               # тайлбаргүй үсрэлт
                bars[d.isoformat()] = dict(date=d.isoformat(), open=px, high=px, low=px, close=round(px, 2), qty=100, value=px * 100)
            d += timedelta(1)
        H.write_csv(k, bars)
    (H.NAMES_FILE).write_text(json.dumps({k: f"{k} ХК" for k in H.KEYS}, ensure_ascii=False), encoding="utf-8")
    (data_dir / "adjustments.csv").write_text("symbol,date,factor,note\nMFC,2024-06-03,0.1,1:10 хуваалт\n", encoding="utf-8")
    (data_dir / "dividends.csv").write_text("symbol,ex_date,amount,note\nAPU,2026-05-15,20,жишээ\n", encoding="utf-8")
    for code, base in (("TOP20", 40000), ("MSEA", 20000), ("MSEB", 10000)):
        rows, v, d = [], base, date(2022, 1, 3)
        while d <= end:
            if d.weekday() < 5:
                v *= 1 + rnd.gauss(0.0004, 0.006)
                rows.append((d.isoformat(), f"{v:.2f}"))
            d += timedelta(1)
        with open(H.HIST_DIR / f"{code}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["date", "close"])
            w.writerows(rows)
    json.dump({"cmd": "update", "ok": H.KEYS[:-4], "failed": {k: "HTTP 503" for k in H.KEYS[-4:]}},
              open(H.STATUS_FILE, "w"), ensure_ascii=False)
    return H


def main():
    tmp = Path(tempfile.mkdtemp(prefix="c4r_"))
    data, rep = tmp / "data", tmp / "reports"
    H = make_data(data)
    env = dict(os.environ, DATA_DIR=str(data), REPORT_DIR=str(rep), DEMO_DATA="1", TELEGRAM_BOT_TOKEN="", TELEGRAM_ADMIN_CHAT_ID="",
               INDEX_ROWS="TOP20,MSEA,MSEB")

    r = run(["chart4.py", "all"], env)
    check(r.returncode == 0, "chart4.py all ажиллав")
    for k in ("monthly", "quarterly", "halfyearly", "yearly"):
        png, txt = rep / f"latest_{k}.png", rep / f"latest_{k}.txt"
        check(png.exists() and png.stat().st_size > 50_000, f"{k}: PNG үүссэн")
        if txt.exists():
            body = txt.read_text(encoding="utf-8")
            tick = [ln.split(" ")[0] for ln in body.split("\n\n", 1)[-1].splitlines() if ln[:1].isupper()]
            check(tick == sorted(tick) and len(tick) == 20, f"{k}: 20 компани үсгийн дарааллаар")
    yearly = (rep / "latest_yearly.txt").read_text(encoding="utf-8")
    check("KHAN (2023.05-аас)" in yearly, "жил: компани бүрийн түүх эхэлсэн сар")
    check(len(yearly.split("\n\n", 1)[-1].splitlines()[0].split("|")[0].split()) - 2 == 8, "жил: 8 жилийн багана")

    import importlib
    sys.path.insert(0, str(ROOT))
    os.environ.update(DATA_DIR=str(data), ASOF="2026-10-30", INDEX_ROWS="TOP20,MSEA,MSEB")
    c4 = importlib.import_module("chart4")
    label, ctx, cap, text = c4.build_periods("halfyearly")
    check(ctx["total_label"].startswith("Нийт\n2023.05"), "хагас жил: Нийт 2023.05-аас")
    khan = next(x for x in ctx["rows"] if x["key"] == "KHAN")
    check(khan["total_mark"] == "", "KHAN (2023-05-01 эхэлсэн) нийт баганад † тэмдэггүй")
    qpay = next(x for x in ctx["rows"] if x["key"] == "QPAY")
    check(qpay["total_mark"] == "†", "QPAY (2024 эхэлсэн) нийт баганад † тэмдэгтэй")
    check(len(ctx["indices"]) == 3, "индексийн 3 мөр")
    label, ctx, cap, text = c4.build_periods("monthly")
    inv = next(x for x in ctx["rows"] if x["key"] == "INV")
    check("nt" in inv["marks"], "INV: арилжаагүй сар таньсан")
    check(any("SBM" in n for n in ctx["notes"]), "SBM: тайлбаргүй ±15% анхааруулга")
    check(not any("хязгаар" in n and "MFC" in n for n in ctx["notes"]), "MFC: бүртгэлтэй хуваалт анхааруулгагүй")

    r = run(["chart4.py", "all"], dict(env, REPORT_DIR=str(tmp / "total"), TOTAL_RETURN="1"))
    check(r.returncode == 0 and (tmp / "total" / "latest_yearly.png").exists(), "нийт өгөөжийн хувилбар")

    r = run(["history_excel.py"], env)
    check(r.returncode == 0 and (rep / "mse_history.xlsx").exists(), "Excel үүссэн")
    from openpyxl import load_workbook
    wb = load_workbook(rep / "mse_history.xlsx", read_only=True)
    for sh in ("Хамрах хүрээ", "Өдрийн хаалт", "Сарын хаалт", "Бүх өгөгдөл", "15%-иас их өөрчлөлт", "Индекс", "Ногдол ашиг"):
        check(sh in wb.sheetnames, f"Excel: '{sh}' хуудас")
    r = run(["history_excel.py", "--max-age", "28"], env)
    check("шаардлагагүй" in r.stdout, "Excel: 28 хоногийн дотор дахин үүсгэхгүй")

    r = run(["alert.py", "--check-status"], env)
    check("4 компанийн" in r.stdout and "SBM" in r.stdout, "мэдэгдэл: татах алдаа + шинэ ±15%")
    r = run(["alert.py", "--check-status"], env)
    check("SBM 2025" not in r.stdout, "мэдэгдэл: ижил ±15%-ийг давтахгүй")
    json.dump({"cmd": "update", "ok": ["APU"], "failed": {k: "хуудаснаас ханшийн мөр олдсонгүй" for k in H.KEYS[1:]}},
              open(H.STATUS_FILE, "w"), ensure_ascii=False)
    r = run(["alert.py", "--check-status"], env)
    check("бүтэц өөрчлөгдсөн" in r.stdout, "мэдэгдэл: сайтын бүтцийн өөрчлөлт")

    im = importlib.import_module("index_mse")
    t = '0:{"a":"$@1"}\n1:{"data":[{"tradeDate":"2025-01-02","closePrice":"48,120.55"},{"tradeDate":"2025-01-03","closePrice":48200}]}\n' \
        '2:[[1735776000000,48120.5],[1735862400000,48200.1],[1735948800000,48300.0]]'
    best = max((im.extract_series(v) for v in im._rsc_values(t)), key=len)
    check(len(best) == 3 and best[0][0] == date(2025, 1, 2), "индексийн RSC задлагч")

    print(f"\n{'АМЖИЛТТАЙ' if not FAIL else f'{len(FAIL)} АЛДАА'} — {tmp}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
