#!/usr/bin/env python3
"""chart4report — open.mse.mn-ээс татсан БҮХ цаг үеийн ханшийн түүхийг нэг Excel файл болгоно.

    python history_excel.py                 # reports/mse_history.xlsx-ийг үүсгэнэ
    python history_excel.py --max-age 28    # файл 28 хоногоос хуучин эсвэл байхгүй бол л шинэчилнэ (өдөр бүрийн ажилд)

Хуудаснууд:
    Тайлбар · Хамрах хүрээ (компани бүрийн эхний/сүүлийн өдөр, өдрийн тоо, хамгийн урт завсар, төлөв)
    Өдрийн хаалт (огноо × 20 компани) · Сарын хаалт (сар × 20 компани) · Бүх өгөгдөл (нээлт, дээд, доод, хаалт, ширхэг, дүн)
    15%-иас их өөрчлөлт (өдрийн хязгаараас их — хуваалт эсвэл өгөгдлийн алдаа) · Багцын арилжаа · Индекс · Ногдол ашиг
Бүх тоо open.mse.mn-ийн түүхий (засваргүй) өгөгдөл. Засвар (data/adjustments.csv) зөвхөн 4 чартад хэрэглэгдэнэ.
"""
import csv
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import history_mse as H

REPORT_DIR = Path(os.environ.get("REPORT_DIR", "reports"))
OUT = REPORT_DIR / "mse_history.xlsx"
META = REPORT_DIR / "mse_history.json"
STALE_DAYS = 30          # бусдаас 30+ хоногоор хоцорсон сүүлийн өдөр → "хуучирсан"

FONT = "Arial"
F = Font(name=FONT, size=10)
FB = Font(name=FONT, size=10, bold=True)
FH = Font(name=FONT, size=10, bold=True, color="FFFFFF")
FT = Font(name=FONT, size=14, bold=True)
FL = Font(name=FONT, size=10, color="0563C1", underline="single")
HDR = PatternFill("solid", fgColor="1F4E9E")
WARN = PatternFill("solid", fgColor="FDE7C4")
BAD = PatternFill("solid", fgColor="F8D0D0")
OKF = PatternFill("solid", fgColor="DDF2E3")
THIN = Border(bottom=Side(style="thin", color="C9D3E3"))
DATE_FMT = "yyyy-mm-dd"


def keys():
    return sorted(H.KEYS + H.EXTRA)


def header(ws, row, titles, widths=None):
    for j, t in enumerate(titles, 1):
        c = ws.cell(row=row, column=j, value=t)
        c.font, c.fill = FH, HDR
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 30
    if widths:
        for j, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(j)].width = w


def style_body(ws, r0, r1, c1):
    for row in ws.iter_rows(min_row=r0, max_row=r1, max_col=c1):
        for c in row:
            if c.font != FL and not c.font.bold:
                c.font = F


def dt(s):
    return date.fromisoformat(s)


def load_all():
    data = {}
    for k in keys():
        bars = {d: b for d, b in H.read_csv(k).items() if b.get("close", 0) > 0}
        data[k] = bars
    return data


def load_blocks(k):
    p = H.HIST_DIR / "blocks" / f"{k}.csv"
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def coverage(k, bars, latest_all):
    if not bars:
        return None
    ds = sorted(bars)
    gap, g0, g1 = 0, None, None
    for a, b in zip(ds, ds[1:]):
        g = (dt(b) - dt(a)).days
        if g > gap:
            gap, g0, g1 = g, a, b
    lag = (dt(latest_all) - dt(ds[-1])).days if latest_all else 0
    return dict(first=ds[0], last=ds[-1], n=len(ds), gap=gap, g0=g0, g1=g1, last_close=bars[ds[-1]]["close"], lag=lag)


def build():
    data = load_all()
    try:
        names = json.loads(H.NAMES_FILE.read_text(encoding="utf-8")) if H.NAMES_FILE.exists() else {}
    except ValueError:
        names = {}
    ids = H.load_ids()
    manual = H.load_adjustments()
    status = {}
    if H.STATUS_FILE.exists():
        try:
            status = json.loads(H.STATUS_FILE.read_text(encoding="utf-8"))
        except ValueError:
            status = {}
    failed = status.get("failed", {})
    ks = keys()
    latest_all = max((max(b) for b in data.values() if b), default=None)
    breaks = {k: H.limit_breaks({d: b["close"] for d, b in data[k].items()}) for k in ks}
    adj = {k: H.effective_adjustments(k, {d: b["close"] for d, b in data[k].items()}, manual.get(k, [])) for k in ks}

    wb = Workbook()
    wb.calculation.fullCalcOnLoad = True

    # ---------------------------------------------------------------- Тайлбар
    ws = wb.active
    ws.title = "Тайлбар"
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 110
    ws["A1"] = "МХБ — 20 компанийн бүх цаг үеийн ханшийн түүх"
    ws["A1"].font = FT
    gen = datetime.now(timezone(timedelta(hours=8)))
    info = [
        ("Эх сурвалж", f"{H.BASE}/securities/<дугаар>/tab/tradeinfo — компани бүрийн хуудас (түүхий өгөгдөл, засваргүй)"),
        ("Үүсгэсэн", gen.strftime("%Y-%m-%d %H:%M (Улаанбаатар)")),
        ("Сүүлийн арилжааны өдөр", latest_all or "—"),
        ("Компани", f"{sum(1 for k in ks if data[k])} / {len(ks)} компанийн өгөгдөлтэй"),
        ("Хаалт", "МХБ-ийн албан ёсны хаалтын ханш (сайтад нийтлэгдсэнээр)."),
        ("Өдрийн хязгаар", f"Өдрийн ханшийн өөрчлөлтийн хязгаар ±{H.DAILY_LIMIT * 100:g}%. Үүнээс их өөрчлөлт (+1 ₮ алхмын зөрүүтэй) "
                           "ердийн арилжаагаар гарахгүй тул хувьцаа хуваалт, нэгтгэл эсвэл өгөгдлийн алдаа гэж үзэж "
                           "\"15%-иас их өөрчлөлт\" хуудсанд жагсаав."),
        ("Хуваалт", "±15%-иас их өөрчлөлтийн харьцаа хуваалтын коэффициенттэй (1:2, 1:10 г.м.) таарвал автоматаар хуваалт гэж "
                    "засна. Буруу бол data/adjustments.csv-д тэр өдрийг factor=1 гэж бичиж цуцална."),
        ("Засвар", "Автоматаар танигдаагүй хуваалтыг data/adjustments.csv файлд мөр нэмж бүртгэнэ: symbol,date,factor,note "
                   "(жишээ: MSE,2024-05-02,0.1,1:10 хуваалт — тэр өдрөөс өмнөх ханш ×0.1). Засвар зөвхөн 4 чартад хэрэглэгдэнэ, "
                   "энэ файлын тоо түүхий хэвээр."),
        ("Төлөв", f"OK · Өгөгдөлгүй · Татаж чадсангүй · Хуучирсан (сүүлийн өдөр бусдаас {STALE_DAYS}+ хоног хоцорсон) · "
                  "Шалгах (15%-иас их, засваргүй өөрчлөлттэй)"),
        ("Хамгийн урт завсар", "Дараалсан хоёр арилжааны өдрийн хоорондох хамгийн их хуанлийн хоног (арилжаа зогссон эсвэл өгөгдөл дутуу)."),
        ("Анхааруулга", "Хөрөнгө оруулалтын зөвлөгөө биш. Ногдол ашиг тусгаагүй."),
    ]
    for i, (a, b) in enumerate(info, 3):
        ws.cell(row=i, column=1, value=a).font = FB
        c = ws.cell(row=i, column=2, value=b)
        c.font, c.alignment = F, Alignment(wrap_text=True, vertical="top")
        ws.cell(row=i, column=1).alignment = Alignment(vertical="top")

    # ---------------------------------------------------------------- Хамрах хүрээ
    ws = wb.create_sheet("Хамрах хүрээ")
    titles = ["№", "Тикер", "Компани", "open.mse.mn хаяг", "Эхний өдөр", "Сүүлийн өдөр", "Арилжааны өдөр",
              "Хамгийн урт завсар (хоног)", "Завсрын эхлэл", "Завсрын төгсгөл", "Сүүлийн хаалт",
              "Сүүлийн арилжаанаас хойш (хоног)", "15%-иас их өөрчлөлт", "Хуваалтын засвар", "Төлөв"]
    header(ws, 1, titles, [5, 9, 34, 38, 12, 12, 11, 13, 13, 13, 13, 14, 12, 26, 26])
    for i, k in enumerate(ks, 1):
        r = i + 1
        cov = coverage(k, data[k], latest_all)
        sid = ids.get(k)
        ws.cell(row=r, column=1, value=i)
        ws.cell(row=r, column=2, value=k).font = FB
        ws.cell(row=r, column=3, value=names.get(k, ""))
        if sid:
            c = ws.cell(row=r, column=4, value=f"{H.BASE}/securities/{sid}")
            c.hyperlink, c.font = f"{H.BASE}/securities/{sid}", FL
        nb = len(breaks[k])
        adj_txt = "; ".join(f"{d} ×{f:g}" + (" (автомат)" if t.startswith("автомат") else "") for d, f, t in adj.get(k, []))
        unexplained = [b for b in breaks[k] if not any(b["date"] == d for d, _, _ in adj.get(k, []))]
        if k in failed and not cov:
            st, fill = f"Татаж чадсангүй: {failed[k]}"[:60], BAD
        elif not cov:
            st, fill = "Өгөгдөлгүй", BAD
        elif cov["lag"] > STALE_DAYS:
            st, fill = f"Хуучирсан ({cov['lag']} хоног)", WARN
        elif unexplained:
            st, fill = f"Шалгах ({len(unexplained)} өөрчлөлт)", WARN
        else:
            st, fill = "OK", OKF
        if k in failed and cov:
            st += " · сүүлийн татахад алдаа"
        if cov:
            for j, v in ((5, dt(cov["first"])), (6, dt(cov["last"])), (9, dt(cov["g0"]) if cov["g0"] else None),
                         (10, dt(cov["g1"]) if cov["g1"] else None)):
                c = ws.cell(row=r, column=j, value=v)
                c.number_format = DATE_FMT
            ws.cell(row=r, column=7, value=cov["n"]).number_format = "#,##0"
            ws.cell(row=r, column=8, value=cov["gap"])
            ws.cell(row=r, column=11, value=cov["last_close"]).number_format = "#,##0.00"
            ws.cell(row=r, column=12, value=cov["lag"])
        ws.cell(row=r, column=13, value=nb)
        ws.cell(row=r, column=14, value=adj_txt or None)
        c = ws.cell(row=r, column=15, value=st)
        c.fill = fill
    style_body(ws, 2, len(ks) + 1, len(titles))
    for r in range(2, len(ks) + 2):
        ws.cell(row=r, column=2).font = FB
        if ws.cell(row=r, column=4).hyperlink:
            ws.cell(row=r, column=4).font = FL
    tr = len(ks) + 2
    ws.cell(row=tr, column=3, value="Нийт").font = FB
    ws.cell(row=tr, column=7, value=f"=SUM(G2:G{tr - 1})").number_format = "#,##0"
    ws.cell(row=tr, column=13, value=f"=SUM(M2:M{tr - 1})")
    for col in (7, 13):
        ws.cell(row=tr, column=col).font = FB
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(titles))}{len(ks) + 1}"

    # ---------------------------------------------------------------- Өдрийн хаалт
    ws = wb.create_sheet("Өдрийн хаалт")
    all_days = sorted({d for k in ks for d in data[k]})
    header(ws, 1, ["Огноо"] + ks, [12] + [10] * len(ks))
    for i, d in enumerate(all_days, 2):
        c = ws.cell(row=i, column=1, value=dt(d))
        c.number_format, c.font = DATE_FMT, F
        for j, k in enumerate(ks, 2):
            b = data[k].get(d)
            if b:
                c = ws.cell(row=i, column=j, value=b["close"])
                c.number_format, c.font = "#,##0.00", F
    ws.freeze_panes = "B2"

    # ---------------------------------------------------------------- Сарын хаалт
    ws = wb.create_sheet("Сарын хаалт")
    months = sorted({d[:7] for d in all_days})
    header(ws, 1, ["Сар"] + ks, [10] + [10] * len(ks))
    last_in_month = {k: {} for k in ks}
    for k in ks:
        for d in sorted(data[k]):
            last_in_month[k][d[:7]] = data[k][d]["close"]
    for i, m in enumerate(months, 2):
        ws.cell(row=i, column=1, value=m).font = F
        for j, k in enumerate(ks, 2):
            v = last_in_month[k].get(m)
            if v is not None:
                c = ws.cell(row=i, column=j, value=v)
                c.number_format, c.font = "#,##0.00", F
    note_r = len(months) + 3
    ws.cell(row=note_r, column=1, value="Сарын сүүлийн арилжааны өдрийн хаалт. Тухайн сард арилжаагүй бол хоосон.").font = Font(name=FONT, size=9, italic=True)
    ws.freeze_panes = "B2"

    # ---------------------------------------------------------------- Бүх өгөгдөл
    ws = wb.create_sheet("Бүх өгөгдөл")
    header(ws, 1, ["Тикер", "Огноо", "Нээлт", "Дээд", "Доод", "Хаалт", "Ширхэг", "Дүн (₮)"], [9, 12, 11, 11, 11, 11, 13, 17])
    r = 2
    for k in ks:
        for d in sorted(data[k]):
            b = data[k][d]
            vals = [k, dt(d), b.get("open") or None, b.get("high") or None, b.get("low") or None, b["close"],
                    b.get("qty") or None, b.get("value") or None]
            fmts = [None, DATE_FMT, "#,##0.00", "#,##0.00", "#,##0.00", "#,##0.00", "#,##0", "#,##0"]
            for j, (v, fm) in enumerate(zip(vals, fmts), 1):
                if v is None:
                    continue
                c = ws.cell(row=r, column=j, value=v)
                c.font = F
                if fm:
                    c.number_format = fm
            r += 1
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:H{max(r - 1, 1)}"

    # ---------------------------------------------------------------- 15%-иас их өөрчлөлт
    ws = wb.create_sheet("15%-иас их өөрчлөлт")
    header(ws, 1, ["Тикер", "Өмнөх өдөр", "Өдөр", "Өмнөх хаалт", "Хаалт", "Өөрчлөлт", "Засвар бүртгэгдсэн", "Тайлбар"],
           [9, 12, 12, 13, 13, 11, 18, 40])
    r = 2
    for k in ks:
        for b in breaks[k]:
            hit = [(d, f, t) for d, f, t in adj.get(k, []) if d == b["date"]]
            row = [k, dt(b["prev_date"]), dt(b["date"]), b["prev_close"], b["close"], f"=E{r}/D{r}-1",
                   ((f"Автомат (×{hit[0][1]:g})" if hit[0][2].startswith("автомат") else f"Тийм (×{hit[0][1]:g})") if hit else "Үгүй"),
                   (hit[0][2] if hit else None)]
            fmts = [None, DATE_FMT, DATE_FMT, "#,##0.00", "#,##0.00", "0.0%;-0.0%;0.0%", None, None]
            for j, (v, fm) in enumerate(zip(row, fmts), 1):
                if v is None:
                    continue
                c = ws.cell(row=r, column=j, value=v)
                c.font = F
                if fm:
                    c.number_format = fm
            ws.cell(row=r, column=7).fill = OKF if hit else WARN
            r += 1
    if r == 2:
        ws.cell(row=2, column=1, value=f"±{H.DAILY_LIMIT * 100:g}%-иас их өөрчлөлт олдсонгүй.").font = F
    ws.freeze_panes = "A2"

    # ---------------------------------------------------------------- Багцын арилжаа
    ws = wb.create_sheet("Багцын арилжаа")
    header(ws, 1, ["Тикер", "Огноо", "Доод ханш", "Дээд ханш", "Ширхэг", "Дүн (₮)"], [9, 12, 12, 12, 14, 17])
    r = 2
    for k in ks:
        for b in load_blocks(k):
            d = H.parse_date(b.get("date", ""))
            row = [k, d, H.num(b.get("low", "")), H.num(b.get("high", "")), H.num(b.get("qty", "")), H.num(b.get("value", ""))]
            fmts = [None, DATE_FMT, "#,##0.00", "#,##0.00", "#,##0", "#,##0"]
            for j, (v, fm) in enumerate(zip(row, fmts), 1):
                if v is None:
                    continue
                c = ws.cell(row=r, column=j, value=v)
                c.font = F
                if fm:
                    c.number_format = fm
            r += 1
    if r == 2:
        ws.cell(row=2, column=1, value="Багцын арилжааны бүртгэл алга.").font = F

    # ---------------------------------------------------------------- ҮЦТХТ: хувьцаа ба эзэмшил, зах зээлийн үнэлгээ
    try:
        import shares as S
        shs = S.load()
    except Exception:  # noqa: BLE001
        S, shs = None, {}
    if shs:
        ws = wb.create_sheet("Хувьцаа ба эзэмшил")
        rdates = sorted({t[0] for v in shs.values() for t in v})
        last = rdates[-1]
        header(ws, 1, ["Тикер", "Компани", f"Хувьцааны тоо ({last})", "5%+ эзэмшигчдийн хувь", "5%+ эзэмшигчид",
                       "Чөлөөт эргэлт", "Олон нийтийн эзэмшигчид", ""] + [d.isoformat() for d in rdates],
               [9, 30, 17, 13, 11, 12, 14, 3] + [14] * len(rdates))
        for i, k in enumerate(ks, 2):
            ser = shs.get(k)
            ws.cell(row=i, column=1, value=k).font = FB
            ws.cell(row=i, column=2, value=names.get(k, "")).font = F
            if not ser:
                ws.cell(row=i, column=3, value="ҮЦТХТ-ийн тайланд алга").font = F
                continue
            r_ = ser[-1][2]
            for j, (v, fm) in enumerate(((int(float(r_["shares"])), "#,##0"), (float(r_["big_pct"]), "0.00%"), (int(float(r_["big_holders"])), "#,##0"),
                                         (float(r_["free_float"]), "0.00%"), (int(float(r_["small_holders"])), "#,##0")), 3):
                c = ws.cell(row=i, column=j, value=v)
                c.number_format, c.font = fm, F
            byd = {t[0]: t[1] for t in ser}
            for j, d in enumerate(rdates, 9):
                if d in byd:
                    c = ws.cell(row=i, column=j, value=byd[d])
                    c.number_format, c.font = "#,##0", F
        ws.cell(row=len(ks) + 3, column=1, value="Эх сурвалж: ҮЦТХТ-ийн эзэмшлийн тайлан (uctht_concentration.xlsx). "
                "Хувьцааны тооны өөрчлөлт бүр хуваалт биш (жишээ нь бүртгэлээс хассан хувьцаа).").font = Font(name=FONT, size=9, italic=True)
        ws.freeze_panes = "C2"

        ws = wb.create_sheet("Зах зээлийн үнэлгээ")
        header(ws, 1, ["Сар"] + ks + ["Нийт"], [10] + [14] * (len(ks) + 1))
        for i, m in enumerate(months, 2):
            ws.cell(row=i, column=1, value=m).font = F
            y, mo = map(int, m.split("-"))
            mend = date(y + (mo == 12), mo % 12 + 1, 1) - timedelta(days=1)
            for j, k in enumerate(ks, 2):
                px, ser = last_in_month[k].get(m), shs.get(k)
                if px is None or not ser or ser[0][0] > mend + timedelta(days=92):
                    continue
                n, _ = S.shares_at(ser, mend)
                c = ws.cell(row=i, column=j, value=f"={px}*{n}")
                c.number_format, c.font = "#,##0", F
            c = ws.cell(row=i, column=len(ks) + 2, value=f"=SUM(B{i}:{get_column_letter(len(ks) + 1)}{i})")
            c.number_format, c.font = "#,##0", FB
        ws.cell(row=len(months) + 3, column=1, value="₮. Сарын сүүлийн хаалт × тухайн өдрийн буюу өмнөх ҮЦТХТ-ийн тайлангийн хувьцааны тоо "
                "(2023-12-31-ний тайлангаас 3 сарын өмнөхөөс эхэлнэ). Хуваалтын сард тайлан хоцорсон бол тухайн сарын үнэлгээ зөрж болно.").font = Font(name=FONT, size=9, italic=True)
        ws.freeze_panes = "B2"

    # ---------------------------------------------------------------- Индекс (ТОП-20, MSE A, MSE B)
    idx = {}
    for code in ("TOP20", "MSEA", "MSEB"):
        p = H.HIST_DIR / f"{code}.csv"
        if p.exists():
            with open(p, newline="", encoding="utf-8") as fh:
                idx[code] = {r_["date"]: float(r_["close"]) for r_ in csv.DictReader(fh) if r_.get("close")}
    if idx:
        ws = wb.create_sheet("Индекс")
        codes = list(idx)
        label = {"TOP20": "ТОП-20", "MSEA": "MSE A", "MSEB": "MSE B"}
        header(ws, 1, ["Огноо"] + [label[c] for c in codes], [12] + [14] * len(codes))
        days = sorted(set().union(*[set(v) for v in idx.values()]))
        for i, d in enumerate(days, 2):
            c = ws.cell(row=i, column=1, value=dt(d))
            c.number_format, c.font = DATE_FMT, F
            for j, code in enumerate(codes, 2):
                v = idx[code].get(d)
                if v is not None:
                    c = ws.cell(row=i, column=j, value=v)
                    c.number_format, c.font = "#,##0.00", F
        ws.cell(row=len(days) + 3, column=1,
                value="Эх сурвалж: https://mse.mn/mse-index (нөөц: members.mse.mn, гараар data/index_top20.csv).").font = Font(name=FONT, size=9, italic=True)
        ws.freeze_panes = "B2"

    # ---------------------------------------------------------------- Ногдол ашиг
    dp = H.DATA_DIR / "dividends.csv"
    if dp.exists():
        ws = wb.create_sheet("Ногдол ашиг")
        header(ws, 1, ["Тикер", "Эрх тогтох өдөр", "₮ / хувьцаа", "Тайлбар"], [9, 15, 13, 40])
        with open(dp, newline="", encoding="utf-8") as fh:
            drows = sorted(csv.DictReader(fh), key=lambda r_: (r_.get("symbol", ""), r_.get("ex_date", "")))
        for i, r_ in enumerate(drows, 2):
            d = H.parse_date(r_.get("ex_date", ""))
            for j, (v, fm) in enumerate(((r_.get("symbol", "").upper(), None), (d, DATE_FMT), (H.num(r_.get("amount", "")), "#,##0.00"),
                                         (r_.get("note") or None, None)), 1):
                if v is None:
                    continue
                c = ws.cell(row=i, column=j, value=v)
                c.font = F
                if fm:
                    c.number_format = fm

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    META.write_text(json.dumps({"generated": gen.isoformat(timespec="seconds"), "latest": latest_all,
                                "rows": sum(len(b) for b in data.values())}, ensure_ascii=False), encoding="utf-8")
    print(f"Excel бэлэн: {OUT} — {sum(1 for k in ks if data[k])} компани, {sum(len(b) for b in data.values()):,} мөр, "
          f"{sum(len(v) for v in breaks.values())} өөрчлөлт ±{H.DAILY_LIMIT * 100:g}%-иас их")
    return 0


def main(argv):
    if "--max-age" in argv:
        days = int(argv[argv.index("--max-age") + 1])
        if META.exists():                    # Excel өөрөө git-д хадгалагдахгүй тул зөвхөн META-аар шалгана
            try:
                g = datetime.fromisoformat(json.loads(META.read_text(encoding="utf-8"))["generated"])
                age = (datetime.now(g.tzinfo) - g).days
                if age < days:
                    print(f"Excel {age} хоногийн өмнө үүссэн — шинэчлэх шаардлагагүй (босго {days})")
                    return 0
            except (ValueError, KeyError):
                pass
    return build()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
