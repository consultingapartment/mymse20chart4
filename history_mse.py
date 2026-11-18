#!/usr/bin/env python3
"""open.mse.mn-ээс бүх цаг үеийн хаалтын ханшийг татаж data/history/<ТИКЕР>.csv-д хадгална.

    python history_mse.py discover             # тикер -> open.mse.mn дахь дугаарыг олж security_ids.json-д хадгална
    python history_mse.py probe-list           # /securities жагсаалтын хуудасны бүтцийг шалгана (түүхий HTML хадгална)
    python history_mse.py probe [ТИКЕР]        # нэг тикерийн арилжааны мэдээллийн хуудасны бүтцийг шалгана
    python history_mse.py backfill [ТИКЕР...]  # бүх түүхийг жилээр хэсэглэж татна
    python history_mse.py update               # сүүлийн 60 өдрийг татаж нэгтгэнэ

Хаяг: https://open.mse.mn/securities/{дугаар}/tab/tradeinfo?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD
(`url_for`, HTML-ээс нүд задлах санааг өмнөх mse_analysis.live кодоос авсан).
Орчны хувьсагч: DATA_DIR, MSE_BASE (туршилтад), HISTORY_START (анхдагч 1996), HISTORY_SLEEP (хүсэлт хоорондын хором).
"""
import csv
import json
import os
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

BASE = os.environ.get("MSE_BASE", "https://open.mse.mn").rstrip("/")
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
HIST_DIR = DATA_DIR / "history"
PROBE_DIR = HIST_DIR / "_probe"
IDS_FILE = HIST_DIR / "security_ids.json"
NAMES_FILE = HIST_DIR / "names.json"      # компанийн нэр — mse.mn-ийн /securities жагсаалтаас
SLEEP = float(os.environ.get("HISTORY_SLEEP", "0.7"))
START_YEAR = int(os.environ.get("HISTORY_START", "1996"))
MAX_PAGES = 80
FIELDS = ["date", "open", "high", "low", "close", "qty", "value"]

# Өмнөх кодоос авсан мэдэгдэж буй дугааруудын үр
# open.mse.mn/securities/<дугаар> — 20 компани бүгд баталгаажсан (discover-ийн үр дүн ба хэрэглэгчийн өгсөн хаягуудтай таарсан)
SEED_IDS = {"AARD": 326, "ADB": 550, "APU": 90, "CUMN": 557, "GLMT": 562, "INV": 553, "KHAN": 563, "LEND": 545, "MFC": 551,
            "MNDL": 547, "MSE": 510, "QPAY": 570, "SBM": 564, "TDB": 567, "TTL": 458, "TUM": 549, "XAC": 568, "ERDN": 546,
            "GAZR": 565, "MFG": 997}

# Тайлан дахь 20 компани. ERDN-ийн арилжаа ERDN-O-0001 дээр гардаг тул тэр бүртгэлийг сонгоно.
SYMBOL_OVERRIDE = {"ERDN": "ERDN-O-0001"}
KEYS = ["AARD", "ADB", "APU", "CUMN", "GLMT", "INV", "KHAN", "LEND", "MFC", "MNDL", "MSE", "QPAY", "SBM", "TDB", "TTL",
        "TUM", "XAC", "ERDN", "GAZR", "MFG"]
EXTRA = [k for k in os.environ.get("HISTORY_TICKERS", "").replace(" ", "").split(",") if k]   # жишээ: SUU,MGLA,MLG,GOV,UID


def symbol_pattern(key):
    """Жагсаалтаас тухайн тикерийг таних хэв: ERDN -> ERDN-O-0001, бусад -> TICKER эсвэл TICKER-O-0000."""
    if key in SYMBOL_OVERRIDE:
        return re.compile(rf"(?<![A-Z0-9-]){re.escape(SYMBOL_OVERRIDE[key])}(?![A-Z0-9-])")
    return re.compile(rf"(?<![A-Z0-9-]){key}(?:-O-0000)?(?![A-Z0-9-])")


# ------------------------------------------------------------------ сүлжээ
def fetch(url, retries=3, timeout=45):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MSE-history", "Accept-Language": "mn,en;q=0.8"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            time.sleep(SLEEP)
            return body.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url}: {last!r}")


def url_for(sid, start=None, end=None, page=None):
    u = f"{BASE}/securities/{sid}/tab/tradeinfo"
    q = []
    if start and end:
        q += [f"startDate={start}", f"endDate={end}"]
    if page and page > 1:
        q.append(f"page={page}")
    return u + ("?" + "&".join(q) if q else "")


# ------------------------------------------------------------------ HTML задлах
class _Tables(HTMLParser):
    """<tr> бүрийн нүдний текст, холбоос (href), толгой мөр эсэхийг цуглуулна."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = {"cells": [], "hrefs": [], "head": False}
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            if tag == "th":
                self._row["head"] = True
        elif tag == "a" and self._row is not None:
            h = dict(attrs).get("href")
            if h:
                self._row["hrefs"].append(h)

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row["cells"].append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row["cells"]:
                self.rows.append(self._row)
            self._row = None


def parse_rows(html):
    p = _Tables()
    p.feed(html)
    return p.rows


def num(s):
    s = str(s).replace(",", "").replace("\xa0", "").replace(" ", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


_ISO = re.compile(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})")
_DMY = re.compile(r"(\d{1,2})[-./](\d{1,2})[-./](\d{4})")


def parse_date(s):
    s = str(s).strip()
    m = _ISO.search(s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = _DMY.search(s)
        if not m:
            return None
        d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


KEYWORDS = {"date": ("огноо", "date"), "open": ("нээлт",), "high": ("дээд",), "low": ("доод",), "range": ("хязгаар",),
            "close": ("хаалт",), "qty": ("ширхэг", "хэмжээ", "тоо"), "value": ("дүн",)}


def map_columns(cells):
    """Толгой мөрийн нүднээс багана -> индекс. 'өмнөх' (өмнөх хаалт) багануудыг алгасна."""
    out = {}
    for i, c in enumerate(cells):
        low = c.lower()
        if "өмнөх" in low or "prev" in low:
            continue
        for key, kws in KEYWORDS.items():
            if key not in out and any(k in low for k in kws):
                out[key] = i
                break
    return out


def _range(text):
    parts = [num(p) for p in re.split(r"\s[-–]\s", str(text)) if num(p) is not None]
    return (min(parts), max(parts)) if len(parts) == 2 else (None, None)


def _history_table(html):
    """Бодит хуудсанд өдрийн түүх id="trading_history_table" хүснэгтэд байна (багцын арилжаа тусдаа хүснэгт)."""
    m = re.search(r'<table[^>]*id="trading_history_table".*?</table>', html, re.S | re.I)
    return m.group(0) if m else html


def parse_history(html):
    """Өдрийн түүхийн хүснэгт: № | Огноо | Нээлтийн ханш | Хаалтын ханш | Өдрийн хязгаар (доод - дээд) | Арилжигдсан ширхэг | Арилжааны үнийн дүн | Хэлцлийн тоо."""
    bars, header = {}, None
    for r in parse_rows(_history_table(html)):
        cells = r["cells"]
        m = map_columns(cells)
        if "date" in m and "close" in m and all(parse_date(c) is None for c in cells):
            header = m                                   # толгой мөр
            continue
        if not header or len(cells) <= max(header.values()):
            continue
        d = parse_date(cells[header["date"]])
        cl = num(cells[header["close"]])
        if not d or not cl or cl <= 0:                   # хаалтгүй (0.00) мөрийг алгасна
            continue
        g = lambda k: num(cells[header[k]]) if k in header else None
        lo = hi = None
        if "range" in header:
            lo, hi = _range(cells[header["range"]])
        op = g("open") or cl
        hi = hi or g("high") or max(op, cl)
        lo = lo or g("low") or min(op, cl)
        bars[d] = dict(date=d.isoformat(), open=op, high=max(hi, op, cl), low=min(lo, op, cl), close=cl,
                       qty=g("qty") or 0.0, value=g("value") or 0.0)
    return [bars[d] for d in sorted(bars)]


def parse_blocks(html):
    """Багцын арилжааны түүх (id="block_history_table", эхний нь хэлцлийн хүснэгт): огноо, үнийн завсар, ширхэг, дүн, хэлцлийн тоо."""
    out = []
    for m in re.finditer(r'<table[^>]*id="block_history_table".*?</table>', html, re.S | re.I):
        header = None
        for r in parse_rows(m.group(0)):
            cells = r["cells"]
            mc = map_columns(cells)
            if "date" in mc and "qty" in mc and all(parse_date(c) is None for c in cells):
                header = mc
                continue
            if not header or "range" not in header or len(cells) <= max(header.values()):
                continue
            d = parse_date(cells[header["date"]])
            lo, hi = _range(cells[header["range"]])
            if d and lo:
                out.append(dict(date=d.isoformat(), low=lo, high=hi, qty=num(cells[header["qty"]]) or 0.0,
                                value=num(cells[header["value"]]) or 0.0))
        if out:
            break
    return sorted(out, key=lambda x: x["date"])


def parse_latest(html, today=None):
    """Нэр | утга хэлбэрийн 2 баганатай хүснэгтээс сүүлийн арилжааны өдрийн ханшийг задлана (нөөц арга)."""
    today = today or date.today()
    info, day = {}, None
    for r in parse_rows(html):
        c = r["cells"]
        if len(c) < 2:
            continue
        k, v = c[0].strip().lower(), num(c[1])
        if v is not None:
            info[k] = v
        elif day is None and "огноо" in k and parse_date(c[1]):
            d = parse_date(c[1])
            day = d if d <= today else None

    def find(*keys, skip=("өмнөх",)):
        for k, v in info.items():
            if any(x in k for x in keys) and not any(x in k for x in skip):
                return v
        return None
    cl = find("хаалтын ханш")
    if not cl or cl <= 0:
        return []
    op = find("нээлтийн ханш") or cl
    hi, lo = find("дээд ханш") or max(op, cl), find("доод ханш") or min(op, cl)
    return [dict(date=(day or today).isoformat(), open=op, high=max(hi, op, cl), low=min(lo, op, cl), close=cl,
                 qty=find("хэлцлийн тоо", "арилжаалагдсан", "тоо ширхэг") or 0.0, value=find("үнийн дүн", "арилжааны дүн") or 0.0)]


def page_numbers(html):
    return sorted({int(m.group(1)) for m in re.finditer(r"[?&;]page=(\d+)", html)})


# ------------------------------------------------------------------ дугаар олох
def load_ids():
    ids = dict(SEED_IDS)
    if IDS_FILE.exists():
        try:
            ids.update({k: int(v) for k, v in json.loads(IDS_FILE.read_text(encoding="utf-8")).items()})
        except ValueError:
            pass
    return ids


def save_ids(ids):
    HIST_DIR.mkdir(parents=True, exist_ok=True)
    IDS_FILE.write_text(json.dumps(dict(sorted(ids.items())), ensure_ascii=False, indent=1), encoding="utf-8")


def parse_listing(html, keys):
    """open.mse.mn/securities жагсаалтын мөр: № | КОД | Нэр. Буцаах: ({тикер: дугаар}, {тикер: нэр})."""
    ids, names = {}, {}
    entries = []
    for r in parse_rows(html):
        m = next((re.search(r"/securities/(\d+)", h) for h in r["hrefs"] if re.search(r"/securities/(\d+)", h)), None)
        if m:
            entries.append((int(m.group(1)), r["cells"]))
    for sid, cells in entries:
        code = cells[1].strip().upper() if len(cells) > 1 else ""
        name = cells[2].strip() if len(cells) > 2 else ""
        text = " ".join(cells).upper()
        for k in keys:
            if k in names:
                continue
            if code == k or code == k.split("-")[0] and k in SYMBOL_OVERRIDE or symbol_pattern(k).search(text):
                names[k] = name
                ids.setdefault(k, sid)
    return ids, names


def discover(keys):
    """/securities жагсаалтаас тикер бүрийн дугаар, нэрийг олно (ERDN зэрэг гараар өгсөн дугаарыг дарахгүй)."""
    ids = load_ids()
    found, names = {}, {}
    for page in range(1, 41):
        html = fetch(f"{BASE}/securities" + (f"?page={page}" if page > 1 else ""))
        f, n = parse_listing(html, keys)
        for k, v in f.items():
            found.setdefault(k, v)
        for k, v in n.items():
            names.setdefault(k, v)
        for m in re.finditer(r'<a[^>]+href="[^"]*?/securities/(\d+)[^"]*"[^>]*>(.*?)</a>', html, re.S | re.I):
            text = re.sub(r"<[^>]+>", " ", m.group(2)).upper()
            for k in keys:
                if k not in found and symbol_pattern(k).search(text):
                    found[k] = int(m.group(1))
        if not parse_rows(html) or page >= max(page_numbers(html) or [1]):
            break
    for k, v in found.items():
        if k in SYMBOL_OVERRIDE and k in ids:      # гараар өгсөн дугаар (жишээ нь ERDN 546)-ыг хэвээр үлдээнэ
            continue
        ids[k] = v
    save_ids(ids)
    if names:
        HIST_DIR.mkdir(parents=True, exist_ok=True)
        old = json.loads(NAMES_FILE.read_text(encoding="utf-8")) if NAMES_FILE.exists() else {}
        old.update(names)
        NAMES_FILE.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
    missing = [k for k in keys if k not in ids]
    print(f"Олдсон: {len(found)} · нэр: {len(names)} · хадгалсан нийт: {len(ids)} · дугааргүй: {missing or 'байхгүй'}")
    return ids


# ------------------------------------------------------------------ CSV
def read_csv(key):
    p = HIST_DIR / f"{key}.csv"
    if not p.exists():
        return {}
    with open(p, newline="", encoding="utf-8") as fh:
        return {r["date"]: {k: (float(r[k]) if k != "date" else r[k]) for k in FIELDS} for r in csv.DictReader(fh)}


def write_csv(key, bars):
    HIST_DIR.mkdir(parents=True, exist_ok=True)
    with open(HIST_DIR / f"{key}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for d in sorted(bars):
            b = bars[d]
            w.writerow({k: (b[k] if k == "date" else f"{b[k]:g}") for k in FIELDS})


def merge(key, new):
    cur = read_csv(key)
    added = 0
    for b in new:
        if b["date"] not in cur:
            added += 1
        old = cur.get(b["date"])
        if old and not b["qty"] and not b["value"]:
            b = dict(b, qty=old["qty"], value=old["value"])
        cur[b["date"]] = b
    write_csv(key, cur)
    return added, len(cur)


# ------------------------------------------------------------------ өдрийн хязгаар (±15%) ба засвар
DAILY_LIMIT = float(os.environ.get("DAILY_LIMIT", "0.15"))     # МХБ-ийн өдрийн ханшийн хэлбэлзлийн хязгаар
ADJ_FILE = DATA_DIR / "adjustments.csv"                           # гараар: symbol,date,factor,note
STATUS_FILE = HIST_DIR / "status.json"


def limit_breaks(closes):
    """closes: {огноо: хаалт}. Дараалсан хоёр арилжааны өдрийн хаалтын өөрчлөлт ±15%-иас (+1 ₮ алхмын зөрүү) их бол
    жагсаана. Хязгаараас их өөрчлөлт ердийн арилжаагаар гарах боломжгүй тул хувьцаа хуваалт, нэгтгэл зэрэг
    корпорацийн үйл ажиллагаа эсвэл өгөгдлийн алдаа гэж үзнэ."""
    out, prev = [], None
    for d in sorted(closes):
        c = closes[d]
        if not c or c <= 0:
            continue
        if prev:
            pd_, pc = prev
            chg = c / pc - 1
            if abs(chg) > DAILY_LIMIT + max(0.002, 1.0 / pc):
                out.append(dict(prev_date=pd_, date=d, prev_close=pc, close=c, change=chg))
        prev = (d, c)
    return out


def load_adjustments():
    """data/adjustments.csv → {тикер: [(огноо, коэффициент, тайлбар)]}. Огнооноос ӨМНӨХ бүх ханшийг коэффициентоор үржүүлнэ.
    Жишээ: 1:10 хуваалт 2024-05-02-нд → MSE,2024-05-02,0.1,1:10 хуваалт"""
    out = {}
    if not ADJ_FILE.exists():
        return out
    with open(ADJ_FILE, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                k, d, f = r["symbol"].strip().upper(), r["date"].strip()[:10], float(r["factor"])
                date.fromisoformat(d)
            except (KeyError, ValueError, AttributeError):
                continue
            if f > 0:
                out.setdefault(k, []).append((d, f, (r.get("note") or "").strip()))
    return out


# Хуваалт (1:N) ба нэгтгэл (N:1)-ийн түгээмэл коэффициент. Хязгаараас (±15%) их өөрчлөлтийн харьцаа эдгээрийн аль нэгтэй
# өдрийн хязгаарын дотор таарвал хуваалт гэж автоматаар засна.
SPLIT_FACTORS = [1 / n for n in (2, 3, 4, 5, 8, 10, 20, 25, 50, 100)] + [2, 3, 4, 5, 10, 20, 50, 100]
AUTO_SPLIT = os.environ.get("AUTO_SPLIT", "1") != "0"


def detect_splits(closes):
    """closes: {огноо: хаалт} → [(огноо, коэффициент, тайлбар)]. Коэффициент = шинэ/хуучин хувьцааны тооны урвуу
    (1:10 хуваалт → 0.1): тэр өдрөөс өмнөх ханшийг үржүүлбэл шинэ ханштай харьцуулах боломжтой болно."""
    out = []
    for b in limit_breaks(closes):
        ratio = b["close"] / b["prev_close"]
        cands = [f for f in SPLIT_FACTORS if (1 - DAILY_LIMIT) <= ratio / f <= (1 + DAILY_LIMIT)]
        if len(cands) != 1:
            continue
        f = cands[0]
        note = f"автомат: 1:{round(1 / f)} хуваалт" if f < 1 else f"автомат: {round(f)}:1 нэгтгэл"
        out.append((b["date"], f, note))
    return out


def effective_adjustments(key, closes, manual=None):
    """Гараар бүртгэсэн засвар (data/adjustments.csv) + бүртгэгдээгүй өдрүүдийн автомат хуваалт.
    adjustments.csv-д factor=1 гэж бичвэл тэр өдрийн автомат засварыг цуцална (жинхэнэ ханшийн өөрчлөлт гэж үзнэ)."""
    manual = list(manual if manual is not None else load_adjustments().get(key, []))
    if not AUTO_SPLIT:
        return manual
    have = {d for d, _, _ in manual}
    return sorted(manual + [x for x in detect_splits(closes) if x[0] not in have])


def adjust(closes, adj_list):
    """Засварын жагсаалтыг хаалтуудад хэрэглэнэ (огнооноос өмнөх ханш × коэффициент)."""
    if not adj_list:
        return dict(closes)
    out = {}
    for d, c in closes.items():
        f = 1.0
        for d0, k, _ in adj_list:
            if d < d0:
                f *= k
        out[d] = c * f
    return out


# ------------------------------------------------------------------ татах
def write_blocks(key, blocks):
    if not blocks:
        return
    d = HIST_DIR / "blocks"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{key}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "low", "high", "qty", "value"])
        w.writeheader()
        w.writerows(blocks)


def backfill(key, sid, today=None):
    """open.mse.mn-ийн хуудас нэг хүсэлтээр БҮХ өдрийн түүхийг (одоогоор 2023-05-01-ээс) буцаадаг — огнооны параметр шаардлагагүй."""
    today = today or date.today()
    html = fetch(url_for(sid))
    bars = parse_history(html) or parse_latest(html, today)
    write_blocks(key, parse_blocks(html))
    added, total = merge(key, bars)
    print(f"{key}: +{added} өдөр, нийт {total}" + (f" ({bars[0]['date']} → {bars[-1]['date']})" if bars else " — өгөгдөл олдсонгүй"))
    if not bars:
        raise RuntimeError("хуудаснаас ханшийн мөр олдсонгүй")
    return total


def update(key, sid, days=60):
    backfill(key, sid)


# ------------------------------------------------------------------ оношилгоо
def probe_list():
    html = fetch(f"{BASE}/securities")
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    (PROBE_DIR / "securities_list.html").write_text(html[:2_000_000], encoding="utf-8")
    rows = parse_rows(html)
    with_id = [r for r in rows if any("/securities/" in h for h in r["hrefs"])]
    print(f"/securities: {len(html):,} тэмдэгт, мөр {len(rows)}, /securities/<дугаар> холбоостой мөр {len(with_id)}, хуудас {page_numbers(html)}")
    for r in with_id[:5]:
        print("  ", r["cells"][:6], r["hrefs"][:2])
    _scripts(html)


def _scripts(html):
    api = sorted(set(re.findall(r"""["'`]((?:https?:)?//[^"'`\s]+/api/[^"'`\s]*|/api/[^"'`\s]*)""", html)))[:15]
    print("  JS дотор олдсон /api/ хаягууд:", api or "олдсонгүй")
    print("  <script> тоо:", len(re.findall(r"<script", html, re.I)), "| __NEXT_DATA__:", "__NEXT_DATA__" in html)


def probe(key="APU"):
    ids = load_ids()
    if key not in ids:
        print(f"{key}-ийн дугаар олдсонгүй. Эхлээд `discover` ажиллуулна уу.")
        return
    today = date.today()
    html = fetch(url_for(ids[key]))
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    (PROBE_DIR / f"{key}_tradeinfo.html").write_text(html[:2_000_000], encoding="utf-8")
    rows = parse_rows(html)
    hist, latest, blocks = parse_history(html), parse_latest(html, today), parse_blocks(html)
    print(f"{key} (id={ids[key]}): {len(html):,} тэмдэгт, <tr> {len(rows)}, хуудас {page_numbers(html)}")
    print(f"  Түүхийн мөр задарсан: {len(hist)} · багцын арилжаа: {len(blocks)} · сүүлийн өдрийн нөөц задлалт: {len(latest)}")
    for r in rows[:6]:
        print("   мөр:", r["cells"][:9])
    for b in hist[:3] + hist[-2:]:
        print("   задарсан:", b)
    _scripts(html)


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    keys = KEYS + EXTRA
    if cmd == "discover":
        discover(keys)
    elif cmd == "probe-list":
        probe_list()
    elif cmd == "probe":
        probe(argv[2] if len(argv) > 2 else "APU")
    elif cmd in ("backfill", "update"):
        ids = load_ids()
        ok, failed = [], {}
        for key in (argv[2:] or keys):
            if key not in ids:
                print(f"{key}: дугаар олдсонгүй — алгасав (`discover` ажиллуулна уу)")
                failed[key] = "дугаар олдсонгүй"
                continue
            try:
                backfill(key, ids[key]) if cmd == "backfill" else update(key, ids[key])
                ok.append(key)
            except Exception as e:  # noqa: BLE001
                print(f"{key}: АЛДАА {e}")
                failed[key] = str(e)[:200]
        HIST_DIR.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(json.dumps({"cmd": cmd, "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                           "ok": ok, "failed": failed}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Дүн: {len(ok)} амжилттай, {len(failed)} алдаатай" + (": " + ", ".join(failed) if failed else ""))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
