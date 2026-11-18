#!/usr/bin/env python3
"""chart4report — ҮЦТХТ-ийн эзэмшлийн тайлангаас (uctht_concentration.xlsx) хувьцааны тоо, эзэмшлийн бүтцийг уншина.

    python shares.py update            # SHARES_URL-аас татаж data/history/shares.csv-г шинэчилнэ
    python shares.py import ФАЙЛ.xlsx  # компьютер дээрх файлаас

Эх сурвалж: Үнэт цаасны төвлөрсөн хадгаламжийн төв (ҮЦТХТ), "Тайлан YY-MM-DD" хуудсууд.
Холбох түлхүүр: "ҮЦ код" = open.mse.mn/securities/<дугаар> (history_mse.SEED_IDS / security_ids.json).
Хадгална: data/history/shares.csv — date,symbol,code,shares,big_pct,big_holders,free_float,small_holders

Ашиглалт:
  * Хуваалтын баталгаажуулалт: ханш ±15%-иас их өөрчлөгдсөн өдрийн өмнөх ба дараах тайлангийн хувьцааны тооны харьцаа.
    Хувьцааны тоо өөрчлөгдөх бүр хуваалт БИШ (жишээ нь ERDN-ийн Торонто бирж дэх хувьцааг хассан бүртгэлийн өөрчлөлт),
    тиймээс зөвхөн ханшийн үсрэлттэй давхцсан үед хэрэглэнэ.
  * Зах зээлийн үнэлгээ = хаалтын ханш × хувьцааны тоо (үнэлгээгээр жигнэсэн дундаж).
"""
import csv
import os
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

import history_mse as H

SHARES_URL = os.environ.get(
    "SHARES_URL", "https://raw.githubusercontent.com/consultingapartment/Huvitsaanii-Tuvlurul/main/data/uctht_concentration.xlsx")
SHARES_FILE = H.HIST_DIR / "shares.csv"
FIELDS = ["date", "symbol", "code", "shares", "big_pct", "big_holders", "free_float", "small_holders"]


def code_map():
    ids = dict(H.SEED_IDS)
    try:
        ids.update(H.load_ids())
    except Exception:  # noqa: BLE001
        pass
    return {int(v): k for k, v in ids.items() if k in H.KEYS}


def parse_xlsx(path):
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    cmap, out = code_map(), []
    for ws in wb.worksheets:
        m = re.match(r"Тайлан\s+(\d{2})-(\d{2})-(\d{2})", ws.title)
        if not m:
            continue
        d = date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
        for r in ws.iter_rows(min_row=3, values_only=True):
            if len(r) < 13 or not isinstance(r[1], (int, float)) or int(r[1]) not in cmap:
                continue
            shares = H.num(r[3]) if not isinstance(r[3], (int, float)) else float(r[3])
            if not shares:
                continue
            f = lambda v: (float(v) if isinstance(v, (int, float)) else H.num(v or "")) or 0.0
            out.append(dict(date=d.isoformat(), symbol=cmap[int(r[1])], code=int(r[1]), shares=int(shares),
                            big_pct=f(r[8]), big_holders=int(f(r[9])), free_float=f(r[11]), small_holders=int(f(r[12]))))
    return sorted(out, key=lambda x: (x["symbol"], x["date"]))


def write(rows):
    SHARES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SHARES_FILE, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def load():
    """→ {тикер: [(огноо, хувьцааны тоо, мөр)]} огноогоор эрэмбэлсэн."""
    if not SHARES_FILE.exists():
        return {}
    out = {}
    with open(SHARES_FILE, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                out.setdefault(r["symbol"], []).append((date.fromisoformat(r["date"]), int(float(r["shares"])), r))
            except (KeyError, ValueError):
                continue
    for v in out.values():
        v.sort(key=lambda t: t[0])
    return out


def shares_at(series, d):
    """d өдөр буюу түүнээс өмнөх сүүлийн тайлангийн хувьцааны тоо (байхгүй бол хамгийн эхний тайлан)."""
    if not series:
        return None, None
    prev = [t for t in series if t[0] <= d]
    t = prev[-1] if prev else series[0]
    return t[1], t[0]


def confirm_split(series, d, factor, tol=0.02):
    """Хуваалтыг ҮЦТХТ-ийн хувьцааны тоогоор шалгана. d = шинэ ханшаар арилжсан эхний өдөр (ISO), factor = өмнөх ханшийн үржвэр.
    → (төлөв, бүртгэлийн коэффициент): 'confirmed' | 'corrected' | 'pending' (дараах тайлан хараахан алга) |
       'contradicted' (хувьцааны тоо өөрчлөгдөөгүй) | 'nodata'."""
    if not series:
        return "nodata", None
    dd = date.fromisoformat(d)
    before = [t for t in series if t[0] < dd]
    after = [t for t in series if t[0] >= dd]
    if not before:
        return "nodata", None
    if not after:
        return "pending", None
    ratio = before[-1][1] / after[0][1]           # 1:10 хуваалт → хуучин/шинэ = 0.1
    if abs(ratio / factor - 1) <= tol:
        return "confirmed", ratio
    if abs(ratio - 1) <= 0.05:
        return "contradicted", ratio
    return "corrected", ratio


def update(path=None):
    src = path
    if not src:
        tmp = H.HIST_DIR / "_uctht.xlsx"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(SHARES_URL, headers={"User-Agent": "chart4report"})
        with urllib.request.urlopen(req, timeout=120) as r:
            tmp.write_bytes(r.read())
        src = tmp
    rows = parse_xlsx(src)
    if not rows:
        print(f"ҮЦТХТ: {src}-ээс манай 20 компанийн мөр олдсонгүй — алгасав (хуучин shares.csv хэвээр)")
        return 1
    write(rows)
    syms = sorted({r["symbol"] for r in rows})
    dates = sorted({r["date"] for r in rows})
    miss = sorted(set(H.KEYS) - set(syms))
    print(f"ҮЦТХТ: {len(rows)} мөр, {len(syms)} компани, {len(dates)} тайлан ({dates[0]} → {dates[-1]})"
          + (f" · олдоогүй: {', '.join(miss)}" if miss else ""))
    if not path:
        Path(src).unlink(missing_ok=True)
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "update":
        return update()
    if cmd == "import" and len(argv) > 2:
        return update(argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
