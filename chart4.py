#!/usr/bin/env python3
"""chart4report — МХБ-ийн ХААЛТЫН ХАНШААР 4 чарт гаргана (хэлцлийн өгөгдөл огт ашиглахгүй).

    python chart4.py monthly|quarterly|halfyearly|yearly   # нэг чарт
    python chart4.py all                                   # 4 чартыг бүгдийг нь
    python chart4.py auto                                  # сүүлд дууссан сар (улирал, хагас жил, жил дууссан бол тэдгээрийг ч)

Оролт : data/history/<ТИКЕР>.csv (хаалтын ханш), data/history/names.json (компанийн нэр) — history_mse.py-аар open.mse.mn-ээс.
        (заавал биш) data/monthly_close.csv: symbol,month,close
Гаралт: reports/<төрөл>_<үе>.png, latest_<төрөл>.png|txt|_caption.txt
Орчны хувьсагч: DATA_DIR, REPORT_DIR, ASOF=YYYY-MM-DD (өдрөөр тооцох), TODAY (туршилт), DEMO_DATA=1 (зохиомол өгөгдлийн тэмдэг)
"""
import json
import os
import re
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import history_mse as H
import render_chart as RX

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
REPORT_DIR = Path(os.environ.get("REPORT_DIR", "reports"))
POS, NEG = (61, 220, 132), (255, 120, 120)
DISCLAIMER_SHORT = "⚠️ Хөрөнгө оруулалтын зөвлөгөө биш."


def canon(sym):
    t = str(sym)
    m = re.fullmatch(r"([A-Za-z]+)-O-\d+", t) or re.fullmatch(r"([A-Za-z]+)-\d+", t)
    return m.group(1) if m else t


def px(x):
    return f"{x:,.0f}" if x >= 1000 else f"{x:,.2f}".rstrip("0").rstrip(".")


def ub_today():
    if os.environ.get("TODAY"):
        return date.fromisoformat(os.environ["TODAY"])
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date()


def iso_label(d):
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def load_mse_names():
    """Компанийн албан ёсны нэр — mse.mn-ийн /securities жагсаалтаас (data/history/names.json)."""
    p = DATA_DIR / "history" / "names.json"
    try:
        return {canon(k): v for k, v in json.loads(p.read_text(encoding="utf-8")).items()} if p.exists() else {}
    except ValueError:
        return {}


def latest_history_date():
    best = None
    for key in H.KEYS:
        bars = H.read_csv(key)
        if bars:
            d = date.fromisoformat(max(bars))
            best = d if best is None or d > best else best
    return best


def clear_latest(kind):
    for suf in (".png", ".txt", "_caption.txt"):
        (REPORT_DIR / f"latest_{kind}{suf}").unlink(missing_ok=True)


def save_outputs(kind, label, png_writer, caption, text):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    png = REPORT_DIR / f"{kind}_{label}.png"
    png_writer(png)
    shutil.copyfile(png, REPORT_DIR / f"latest_{kind}.png")
    (REPORT_DIR / f"latest_{kind}_caption.txt").write_text(caption + "\n", encoding="utf-8")
    (REPORT_DIR / f"latest_{kind}.txt").write_text(text + "\n", encoding="utf-8")
    print(f"Зураг бэлэн: {png}")


# ================================================================== САР, УЛИРАЛ, ЖИЛИЙН ХАНШИЙН ХӨДӨЛГӨӨН (%)
MONTH_CSV = "monthly_close.csv"   # заавал биш: data/monthly_close.csv (symbol,month,close), month = YYYY-MM
COMMON_START = date.fromisoformat(os.environ.get("COMMON_START", "2023-05-01"))   # 20 компанийн нийтлэг эхлэл
GRACE_DAYS = 7    # суурь огнооноос хойш 7 хоногийн дотор түүх эхэлсэн бол бүтэн үе гэж үзнэ (жишээ нь KHAN 2023-05-01)
TOTAL_RETURN = os.environ.get("TOTAL_RETURN", "") == "1"   # 1 бол ногдол ашгийг (data/dividends.csv) өгөөжид оруулна
DIV_FILE = "dividends.csv"                                  # symbol,ex_date,amount,note — нэг хувьцаанд ногдох ₮
YEARS = int(os.environ.get("YEARS", "8"))   # жилийн тайланд харуулах жилийн тоо


def month_end(y, m):
    return date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)


def load_daily(asof):
    """Тикер -> [(огноо, хаалт, ширхэг|None)] огноогоор эрэмбэлсэн. Эх сурвалж: ЗӨВХӨН data/history/*.csv (open.mse.mn)
    ба заавал биш data/monthly_close.csv (сарын эцсийн огноотой, ширхэг тодорхойгүй). Компани бүр өөрийн огнооноос эхэлнэ."""
    import csv as _csv
    daily, flags = {}, set()
    for key in H.KEYS:
        bars = H.read_csv(key)
        rows = [(date.fromisoformat(d), b["close"], b.get("qty")) for d, b in bars.items()
                if date.fromisoformat(d) <= asof and b["close"] > 0]
        if rows:
            daily[key] = sorted(rows)
    p = DATA_DIR / MONTH_CSV
    if p.exists():
        with open(p, newline="", encoding="utf-8") as fh:
            for r in _csv.DictReader(fh):
                try:
                    y, m = map(int, r["month"].strip()[:7].split("-"))
                    key, d = r["symbol"].strip(), month_end(y, m)
                    if d > asof:
                        continue
                    have = {x[0].year * 12 + x[0].month for x in daily.get(key, [])}
                    if y * 12 + m not in have:                 # өдрийн өгөгдөл давамгайлна
                        daily.setdefault(key, []).append((d, float(r["close"]), None))
                except (KeyError, ValueError):
                    continue
        for key in daily:
            daily[key].sort()
    # гараар бүртгэсэн засвар (data/adjustments.csv), дараа нь ±15%-иас их тайлбаргүй өөрчлөлтийг ⚠-ээр тэмдэглэнэ
    adj, applied = H.load_adjustments(), {}
    for key, rows in daily.items():
        if adj.get(key):
            closes = H.adjust({d.isoformat(): c for d, c, _ in rows}, adj[key])
            daily[key] = [(d, closes[d.isoformat()], q) for d, _, q in rows]
            applied[key] = adj[key]
        if H.limit_breaks({d.isoformat(): c for d, c, _ in daily[key]}):
            flags.add(key)
    return daily, flags, applied


def load_dividends(applied):
    """data/dividends.csv → {тикер: [(эрх тогтох огноо, ₮/хувьцаа)]}. Хуваалтын засвар хийсэн бол дүнг мөн засна."""
    import csv as _csv
    p = DATA_DIR / DIV_FILE
    out = {}
    if not p.exists():
        return out
    with open(p, newline="", encoding="utf-8") as fh:
        for r in _csv.DictReader(fh):
            try:
                k, d, a = r["symbol"].strip().upper(), date.fromisoformat(r["ex_date"].strip()[:10]), float(r["amount"])
            except (KeyError, ValueError, AttributeError):
                continue
            for d0, f, _ in applied.get(k, []):
                if d.isoformat() < d0:
                    a *= f
            if a > 0:
                out.setdefault(k, []).append((d, a))
    return out


class Series:
    def __init__(self, rows, divs=None):
        self.divs = sorted(divs or [])
        self.rows = rows
        self.dates = [r[0] for r in rows]
        self.first = rows[0][0]

    def close_at(self, d):
        """d өдөр буюу түүнээс өмнөх сүүлийн хаалт."""
        import bisect
        i = bisect.bisect_right(self.dates, d) - 1
        return self.rows[i][1] if i >= 0 else None

    def traded(self, d0, d1):
        """(d0, d1] хооронд арилжаа болсон эсэх. Ширхэг тодорхойгүй (сарын CSV) бол True гэж үзнэ."""
        import bisect
        i, j = bisect.bisect_right(self.dates, d0), bisect.bisect_right(self.dates, d1)
        seg = self.rows[i:j]
        if not seg:
            return False
        return any(q is None or q > 0 for _, _, q in seg)

    def change(self, base_d, end_d):
        """(утга %, тэмдэг): тэмдэг '' = бүтэн үе, '†' = үеийн дундаас түүх эхэлсэн (өөрийн эхний хаалтаас),
        'nt' = үеийн турш арилжаагүй (ханш өөрчлөгдөөгүй). (None, '') = өгөгдөлгүй."""
        if self.first > end_d:
            return None, ""
        end = self.close_at(end_d)
        base = self.close_at(base_d)
        mark = ""
        if base is None:
            base = self.rows[0][1]
            if (self.first - base_d).days > GRACE_DAYS:
                mark = "†"
        if not base or end is None:
            return None, ""
        b_eff = base_d if not mark else self.first - timedelta(days=1)
        div = sum(a for d, a in self.divs if b_eff < d <= end_d) if TOTAL_RETURN else 0.0
        if not mark and not div and not self.traded(max(base_d, self.first - timedelta(days=1)), end_d):
            return 0.0, "nt"
        return ((end + div) / base - 1) * 100, mark


INDEX_TOL_DAYS = 7     # индексийн утга суурь/эцсийн огнооноос 7 хоногийн дотор байх ёстой


INDEX_NAMES = {"TOP20": "ТОП-20 индекс (МХБ)", "MSEA": "MSE A индекс", "MSEB": "MSE B индекс"}
INDEX_ROWS = [c.strip().upper() for c in os.environ.get("INDEX_ROWS", "TOP20").split(",") if c.strip().upper() in INDEX_NAMES]


def load_index(asof, code="TOP20"):
    """data/history/<code>.csv (index_mse.py) → [(огноо, утга)] эсвэл None."""
    import csv as _csv
    p = H.HIST_DIR / f"{code}.csv"
    if not p.exists():
        return None
    with open(p, newline="", encoding="utf-8") as fh:
        rows = sorted((date.fromisoformat(r["date"]), float(r["close"])) for r in _csv.DictReader(fh) if r.get("close"))
    rows = [r for r in rows if r[0] <= asof]
    return rows or None


def index_change(rows, base_d, end_d):
    """Индексийн өөрчлөлт %: суурь ба эцсийн утга тус бүр огнооноосоо 7 хоногийн дотор мэдэгдэж байх ёстой."""
    import bisect
    ds = [d for d, _ in rows]

    def at(d):
        i = bisect.bisect_right(ds, d) - 1
        if i < 0 or (d - ds[i]).days > INDEX_TOL_DAYS:
            return None
        return rows[i]
    b, e = at(base_d), at(end_d)
    if not b or not e or e[0] <= b[0]:
        return None
    return (e[1] / b[1] - 1) * 100


def build_periods(kind, asof=None):
    if not asof:
        if os.environ.get("ASOF"):
            asof = date.fromisoformat(os.environ["ASOF"])
        else:
            asof = latest_history_date() or date.today()
    daily, flags, applied = load_daily(asof)
    divs = load_dividends(applied) if TOTAL_RETURN else {}
    ser = {k: Series(v, divs.get(k)) for k, v in daily.items() if len(v) >= 2}
    if len(ser) < 3:
        return None
    names = load_mse_names()
    lw = month_end(asof.year, asof.month)
    while lw.weekday() > 4:                                  # сарын сүүлийн ажлын өдөр
        lw -= timedelta(days=1)
    month_complete = asof >= lw
    partial = not month_complete
    cs_base = COMMON_START - timedelta(days=1)               # нийтлэг эхлэлийн суурь = 2023-05-01-ний өмнөх өдрийн хаалт
    cs_lab = f"{COMMON_START:%Y.%m}"
    # үе бүр: (шошго, эцсийн огноо, суурь огноо)
    if kind == "monthly":
        y = asof.year
        periods = [(f"{y}.{m:02d}", month_end(y, m) if m < asof.month else asof, month_end(y, m - 1) if m > 1 else date(y - 1, 12, 31))
                   for m in range(1, asof.month + 1)]
        total_label, total_base = "Жилийн\nэхнээс", date(y - 1, 12, 31)
        title, card_title = "Сарын ханшийн хөдөлгөөн", "Сар бүрийн хаалтын ханшийн өөрчлөлт, %"
        sub = "Сар бүрийн сүүлийн арилжааны өдрийн хаалтыг өмнөх сарын хаалттай харьцуулав."
        cap, label = 15.0, f"{y}-{asof.month:02d}"
    elif kind in ("quarterly", "halfyearly"):
        step = 3 if kind == "quarterly" else 6
        cur = (asof.month - 1) // step + 1
        ps, y, q = [], asof.year, cur
        for _ in range(8):
            ps.append((y, q))
            q -= 1
            if q == 0:
                y, q = y - 1, 12 // step
        ps.reverse()
        tag = "Q" if kind == "quarterly" else "H"
        periods = []
        for y, q in ps:
            end = asof if (y, q) == ps[-1] else month_end(y, step * q)
            base = month_end(y, step * (q - 1)) if q > 1 else date(y - 1, 12, 31)
            periods.append((f"{y}.{tag}{q}", end, base))
        partial = not (asof.month % step == 0 and month_complete)
        if kind == "quarterly":
            title, card_title = "Улирлын ханшийн хөдөлгөөн", "Улирал бүрийн хаалтын ханшийн өөрчлөлт, %"
            sub, cap = "Улирал бүрийн сүүлийн сарын хаалтыг өмнөх улирлын хаалттай харьцуулав.", 30.0
        else:
            title, card_title = "Хагас жилийн ханшийн хөдөлгөөн", "Хагас жил бүрийн хаалтын ханшийн өөрчлөлт, %"
            sub, cap = "Хагас жил бүрийн сүүлийн сарын хаалтыг өмнөх хагас жилийн хаалттай харьцуулав.", 40.0
        label = f"{asof.year}-{tag}{cur}"
        total_label, total_base = None, None                 # доор харагдах үеэс тодорхойлно
    else:
        first_year = min(s.first.year for s in ser.values())
        years = list(range(max(first_year, asof.year - YEARS + 1), asof.year + 1))
        periods = [(str(y), date(y, 12, 31) if y < asof.year else asof, date(y - 1, 12, 31)) for y in years]
        partial = not (asof.month == 12 and month_complete)
        total_label, total_base = f"Нийт\n{cs_lab}-аас", cs_base
        title, card_title = "Жилийн ханшийн хөдөлгөөн", "Жил бүрийн хаалтын ханшийн өөрчлөлт, %"
        sub = "Жил бүрийн 12-р сарын хаалтыг өмнөх жилийн хаалттай харьцуулав."
        cap, label = 60.0, str(asof.year)
    if TOTAL_RETURN:
        title = title.replace("ханшийн хөдөлгөөн", "нийт өгөөж (ханш + ногдол ашиг)")
        card_title = card_title.replace("хаалтын ханшийн өөрчлөлт", "нийт өгөөж (ханш + ногдол ашиг)")
    # компани бүрийн утга
    rows = []
    for key, s in ser.items():
        cells = [s.change(b, e) for _, e, b in periods]
        if all(v is None for v, _ in cells):
            continue
        rows.append(dict(key=key, name=names.get(key, ""), flag=key in flags, start=f"{s.first:%Y.%m}", s=s,
                         vals=[v for v, _ in cells], marks=[m for _, m in cells]))
    if len(rows) < 3:
        return None
    first_i = next((i for i in range(len(periods)) if any(r["vals"][i] is not None for r in rows)), None)
    if first_i is None:
        return None
    periods = periods[first_i:]                              # өгөгдөлгүй эхний багануудыг хасна
    for r in rows:
        r["vals"], r["marks"] = r["vals"][first_i:], r["marks"][first_i:]
    if kind in ("quarterly", "halfyearly"):
        # нийт = харагдах эхний үеэс, гэхдээ 20 компанийн нийтлэг эхлэлээс (2023-05-01) өмнө биш
        total_base = max(periods[0][2], cs_base)
        unit = "улирал" if kind == "quarterly" else "хагас жил"
        total_label = f"Нийт\n{cs_lab}-аас" if total_base == cs_base else f"Нийт\n{len(periods)} {unit}"
    for r in rows:
        v, m = r["s"].change(total_base, periods[-1][1])
        r["total"], r["total_mark"] = v, m
        del r["s"]
    index_rows = []
    for code in INDEX_ROWS:
        idx_rows = load_index(asof, code)
        if not idx_rows:
            continue
        iv = [index_change(idx_rows, b, e) for _, e, b in periods]
        it = index_change(idx_rows, total_base, periods[-1][1])
        if any(v is not None for v in iv + [it]):
            index_rows.append(dict(code=code, name=INDEX_NAMES[code], vals=iv, total=it))
    index_row = next((x for x in index_rows if x["code"] == "TOP20"), None)
    n = len(periods)
    full = lambda r, i: r["vals"][i] is not None and r["marks"][i] != "†"     # дундаж, тоололд зөвхөн бүтэн үе
    avg, ns, counts = [], [], []
    for i in range(n):
        vv = [r["vals"][i] for r in rows if full(r, i)]
        avg.append(sum(vv) / len(vv) if vv else None)
        ns.append(len(vv))
        counts.append((sum(1 for v in vv if v > 0), sum(1 for v in vv if v < 0)))
    tv = [r["total"] for r in rows if r["total"] is not None and r["total_mark"] != "†"]
    avg_total = sum(tv) / len(tv) if tv else None
    ns.append(len(tv))
    counts.append((sum(1 for v in tv if v > 0), sum(1 for v in tv if v < 0)))
    rows.sort(key=lambda r: r["key"])                       # бүх 4 тайланд тикерийн үсгийн дарааллаар (AARD → XAC)
    last_vals = [(r["key"], r["vals"][-1]) for r in rows if full(r, n - 1)]
    if not last_vals:
        return None
    best, worst = max(last_vals, key=lambda t: t[1]), min(last_vals, key=lambda t: t[1])
    plabel = periods[-1][0] + ("*" if partial else "")
    any_dag = any("†" in r["marks"] or r["total_mark"] == "†" for r in rows)
    any_nt = any("nt" in r["marks"] for r in rows)
    notes = ["Хаалт = МХБ-ийн албан ёсны хаалтын ханш (open.mse.mn). Өөрчлөлт = үеийн эцсийн хаалт ÷ өмнөх үеийн эцсийн хаалт − 1."
             + (" * = үе дуусаагүй (сүүлийн мэдэгдэж буй хаалтаар)." if partial else ""),
             f"\"Нийт\" баганын суурь бүх компанид ижил{' (' + cs_lab + '-ын өмнөх сүүлийн хаалт)' if total_base == cs_base else ''}. "
             "Компани бүрийн түүх эхэлсэн сар нь тикерийн баруун талд. — = тухайн үед өгөгдөлгүй.",
             ("Нийт өгөөж = ханшийн өөрчлөлт + тухайн үед эрх тогтсон ногдол ашиг (data/dividends.csv, дахин хөрөнгө оруулаагүй)."
              if TOTAL_RETURN else "Ногдол ашиг тусгаагүй (зөвхөн ханшийн өөрчлөлт).")]
    if any_dag:
        notes.append("† = үеийн дундаас түүх эхэлсэн тул өөрийн эхний хаалтаас тооцсон (бүтэн үе биш) — дундаж, өссөн/унасан тоонд ороогүй.")
    if any_nt:
        notes.append("\"арилжаагүй\" = тухайн үед нэг ч арилжаа болоогүй, хаалт өмнөхөөрөө (өөрчлөлт 0). Дундажид 0%-иар орсон.")
    if index_rows:
        notes.append("Индекс = МХБ-ийн албан ёсны индекс (mse.mn), харьцуулах зорилгоор. Жин нь зах зээлийн үнэлгээгээр тул "
                     "дээрх тэнцүү жинтэй дунджаас ялгаатай. — = тухайн үеийн индексийн утга хадгалагдаагүй.")
    if applied:
        notes.append("Засвар хийсэн (хуваалт г.м., data/adjustments.csv): " + "; ".join(
            f"{k} {d} ×{f:g}" + (f" ({t})" if t else "") for k in sorted(applied) for d, f, t in applied[k]))
    if flags:
        hit = sorted(k for k in flags if k in {r["key"] for r in rows})
        if hit:
            notes.append(f"Анхаар: өдрийн хязгаар (±{H.DAILY_LIMIT * 100:g}%)-аас их өөрчлөлттэй, засвар бүртгэгдээгүй компани — "
                         "хувьцаа хуваалт эсвэл өгөгдлийн алдаа байж болзошгүй: " + ", ".join(hit))
    ctx = dict(title=title, card_title=card_title, subtitle=sub, range=f"{periods[0][0]} → {plabel}", cols=[p[0] for p in periods],
               partial_last=partial, total_label=total_label, rows=rows, avg=avg, avg_total=avg_total, counts=counts, ns=ns,
               n_rows=len(rows), cap=cap, notes=notes, indices=index_rows,
               kpis=[(f"{avg[-1]:+.1f}%" if avg[-1] is not None else "—", f"{plabel}: дундаж (тэнцүү жин)", POS if (avg[-1] or 0) >= 0 else NEG),
                     (str(counts[n - 1][0]), f"өссөн ({plabel})", POS), (str(counts[n - 1][1]), f"унасан ({plabel})", NEG),
                     (f"{best[0]} {best[1]:+.1f}%", "хамгийн их өссөн", POS), (f"{worst[0]} {worst[1]:+.1f}%", "хамгийн их унасан", NEG)])
    fmt = lambda v, m: "—" if v is None else ("арилжаагүй" if m == "nt" else f"{v:+.1f}%{m}")
    cap_txt = ", ".join(f"{k} {v:+.1f}%" for k, v in sorted(last_vals, key=lambda t: -t[1])[:3])
    low_txt = ", ".join(f"{k} {v:+.1f}%" for k, v in sorted(last_vals, key=lambda t: t[1])[:3])
    caption = (f"📊 {title} ({ctx['range']})\n{plabel}: дундаж {avg[-1]:+.1f}% · өссөн {counts[n - 1][0]} · унасан {counts[n - 1][1]}"
               f" · {ns[n - 1]} компани"
               + (f"\nТОП-20 индекс (МХБ): {index_row['vals'][-1]:+.1f}%" if index_row and index_row["vals"][-1] is not None else "")
               + f"\nТэргүүлэгч: {cap_txt}\nХоцрогч: {low_txt}\n{DISCLAIMER_SHORT}")
    text = caption + "\n\n" + "\n".join(f"{r['key']} ({r['start']}-аас): " + " ".join(fmt(v, m) for v, m in zip(r["vals"], r["marks"]))
                                         + f" | нийт {fmt(r['total'], r['total_mark'])}" for r in rows)
    return label, ctx, caption, text


def cmd_periods(kind):
    kinds = {"monthly": "Сар", "quarterly": "Улирал", "halfyearly": "Хагас жил", "yearly": "Жил"}
    clear_latest(kind)
    res = build_periods(kind)
    if not res:
        print("data/history/-д хангалттай түүх алга. Эхлээд `history_mse.py backfill` (эсвэл data/monthly_close.csv) бэлдэнэ үү.")
        return 0
    label, ctx, caption, text = res
    save_outputs(kind, label, lambda p: RX.render_periods(ctx, p), caption, text)
    print(f"{kinds[kind]}: {len(ctx['rows'])} компани, {len(ctx['cols'])} үе")
    return 0


def cmd_periods_auto():
    """Сүүлд дууссан сар (мөн улирлын/жилийн эцэс бол улирал, жил)-ын хүснэгтийг гаргана.
    Өдөр бүр ажиллуулахад ижил зураг давтан илгээгдэхгүй (send_telegram.py агуулгаар нь шалгана)."""
    today = ub_today()
    asof = today.replace(day=1) - timedelta(days=1)
    os.environ["ASOF"] = asof.isoformat()
    for k in ("monthly", "quarterly", "halfyearly", "yearly"):
        clear_latest(k)
    made = []
    for kind, ok in (("monthly", True), ("quarterly", asof.month in (3, 6, 9, 12)), ("halfyearly", asof.month in (6, 12)),
                     ("yearly", asof.month == 12)):
        if ok:
            cmd_periods(kind)
            if (REPORT_DIR / f"latest_{kind}.png").exists():
                made.append(kind)
    print("Үүссэн:", made or "байхгүй")
    return 0


def cmd_all():
    for k in KINDS:
        cmd_periods(k)
    return 0


KINDS = ("monthly", "quarterly", "halfyearly", "yearly")
COMMANDS = {"monthly": lambda: cmd_periods("monthly"), "quarterly": lambda: cmd_periods("quarterly"),
            "halfyearly": lambda: cmd_periods("halfyearly"), "yearly": lambda: cmd_periods("yearly"),
            "all": cmd_all, "auto": cmd_periods_auto, "periods-auto": cmd_periods_auto}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    sys.exit(COMMANDS[cmd]() or 0)
