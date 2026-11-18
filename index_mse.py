#!/usr/bin/env python3
"""chart4report — МХБ-ийн ТОП-20 индексийн түүх (зөвхөн mse.mn эх сурвалж).

    python index_mse.py history    # mse.mn/mse-index-ээс ТОП-20-ийн БҮХ түүхийг татна (top20ChartData / top20ChartList)
    python index_mse.py snapshot   # members.mse.mn-ийн ТОП-20 хуудаснаас өнөөдрийн индексийг авч хуримтлуулна (нөөц)
    python index_mse.py import     # data/index_top20.csv (date,value) — mse.mn-ээс гараар бэлтгэсэн түүхийг нэгтгэнэ
    python index_mse.py probe      # open.mse.mn дээр индексийн түүхийн хуудас хайна (HTML-ийг _probe/ дотор хадгална)

Хадгалах: data/history/TOP20.csv (date,close). Огноо = сүүлийн арилжааны өдөр (компаниудын түүхээс).
Орчны хувьсагч: INDEX_SNAPSHOT_URL (анхдагч https://members.mse.mn/en/mse_top_20/265)
"""
import csv
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

import history_mse as H

IMPORT_FILE = H.DATA_DIR / "index_top20.csv"
SNAPSHOT_URL = os.environ.get("INDEX_SNAPSHOT_URL", "https://members.mse.mn/en/mse_top_20/265")
LABELS = ("top 20", "top-20", "топ-20", "топ 20")


INDICES = {"TOP20": ("top20ChartData", "top20ChartList"), "MSEA": ("mseAChartData", "mseAChartList"),
           "MSEB": ("mseBChartData", "mseBChartList")}
STATUS = H.HIST_DIR / "index_status.json"


def index_file(code="TOP20"):
    return H.HIST_DIR / f"{code}.csv"


def read_index(code="TOP20"):
    f = index_file(code)
    if not f.exists():
        return {}
    with open(f, newline="", encoding="utf-8") as fh:
        return {r["date"]: float(r["close"]) for r in csv.DictReader(fh) if r.get("close")}


def write_index(series, code="TOP20"):
    f = index_file(code)
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "close"])
        for d in sorted(series):
            w.writerow([d, f"{series[d]:g}"])


def last_trading_day():
    """Компаниудын түүх дэх хамгийн сүүлийн арилжааны өдөр (индексийн хуудас огноо заадаггүй тул)."""
    best = None
    for k in H.KEYS:
        bars = H.read_csv(k)
        if bars:
            d = max(bars)
            best = d if best is None or d > best else best
    return best


def parse_top20(html):
    """Хуудасны хүснэгтээс "Top 20 Index" мөрийн утгыг олно."""
    for row in H.parse_rows(html):
        cells = row["cells"]
        if not cells:
            continue
        head = cells[0].strip().lower()
        if any(lb in head for lb in LABELS):
            for c in cells[1:]:
                v = H.num(c)
                if v and v > 100:
                    return v
    m = re.search(r"(?:Top\s*-?\s*20|ТОП\s*-?\s*20)[^0-9]{0,80}?([0-9][0-9,]*\.?[0-9]*)", html, re.I)
    if m:
        v = H.num(m.group(1))
        if v and v > 100:
            return v
    return None


# ------------------------------------------------------------------ mse.mn/mse-index (Next.js server action)
INDEX_PAGE = os.environ.get("MSE_INDEX_PAGE", "https://mse.mn/mse-index")
# Хуудас дахин build хийгдэхэд энэ ID солигдож болно — тэгвэл хуудасны JS-ээс автоматаар хайна (find_action_ids)
ACTION_ID = os.environ.get("MSE_NEXT_ACTION", "7f15ecc768683d85b3e8f80304cb1bba603ff76b3e")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def post_action(action_id, name, timeout=60):
    body = json.dumps([{"url": name, "parameter": "?lang=mn", "config": {"hasToken": False}}]).encode()
    req = urllib.request.Request(INDEX_PAGE, data=body, method="POST", headers={
        "Accept": "text/x-component", "Content-Type": "text/plain;charset=UTF-8", "next-action": action_id,
        "Origin": "https://mse.mn", "Referer": INDEX_PAGE, "User-Agent": UA, "Accept-Language": "mn,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def find_action_ids():
    """Хуудасны HTML ба JS chunk-уудаас 40-42 тэмдэгттэй hex server-action ID-уудыг хайна."""
    ids, html = [], H.fetch(INDEX_PAGE, retries=2)
    chunks = sorted(set(re.findall(r'src="(/_next/static/[^"]+\.js)"', html)))
    texts = [html]
    for c in chunks[:60]:
        try:
            texts.append(H.fetch("https://mse.mn" + c, retries=1))
        except Exception:  # noqa: BLE001
            pass
    for t in texts:
        for m in re.finditer(r'["\']([0-9a-f]{40,42})["\']', t):
            if m.group(1) not in ids:
                ids.append(m.group(1))
    return ids


def _rsc_values(text):
    """RSC хариу (мөр бүр "N:<json>") эсвэл энгийн JSON-оос бүх JSON утгыг гаргана."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^[0-9a-zA-Z]+:(.*)$", line)
        for cand in ((m.group(1),) if m else ()) + (line,):
            try:
                out.append(json.loads(cand))
                break
            except ValueError:
                continue
    return out


def _as_date(v):
    if isinstance(v, (int, float)) and 9.0e11 < v < 4.0e12:             # мс timestamp
        return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=v) + timedelta(hours=8)).date()
    if isinstance(v, (int, float)) and 9.0e8 < v < 4.0e9:               # сек timestamp
        return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=v) + timedelta(hours=8)).date()
    if isinstance(v, str):
        return H.parse_date(v)
    return None


VALUE_KEYS = ("close", "closeprice", "closingprice", "indexvalue", "index", "value", "price", "y", "last", "amount", "unit")
DATE_KEYS = ("date", "tradedate", "tradingdate", "createdat", "x", "time", "day", "dt", "datetime")


def _point(item):
    """{date, value} эсвэл [date, value] → (date, value)."""
    if isinstance(item, dict):
        low = {str(k).lower().replace("_", ""): v for k, v in item.items()}
        d = next((_as_date(low[k]) for k in DATE_KEYS if k in low and _as_date(low[k])), None)
        if not d:
            d = next((_as_date(v) for v in low.values() if _as_date(v)), None)
        val = None
        for k in VALUE_KEYS:
            if k in low:
                val = H.num(low[k]) if not isinstance(low[k], (int, float)) else float(low[k])
                if val:
                    break
        return (d, val) if d and val and val > 100 else None
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        d = _as_date(item[0])
        v = item[1] if isinstance(item[1], (int, float)) else H.num(item[1])
        return (d, float(v)) if d and v and v > 100 else None
    return None


def extract_series(obj):
    """Хамгийн олон (огноо, утга) цэгтэй жагсаалтыг рекурсив хайна."""
    best = []

    def walk(o):
        nonlocal best
        if isinstance(o, list):
            pts = [p for p in (_point(x) for x in o) if p]
            if len(pts) > len(best) and len(pts) >= max(3, len(o) // 2):
                best = pts
            for x in o:
                walk(x)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, str) and len(o) > 20 and o[:1] in "[{":
            try:
                walk(json.loads(o))
            except ValueError:
                pass
    walk(obj)
    return best


def history(code="TOP20"):
    """mse.mn/mse-index-ийн индексийн түүхийг татаж <code>.csv-д нэгтгэнэ. Хариуг _probe/-д хадгална."""
    global ACTION_ID
    H.PROBE_DIR.mkdir(parents=True, exist_ok=True)
    tried, ids = [], [ACTION_ID]
    got = {}
    for attempt in range(2):
        for aid in ids:
            if aid in tried:
                continue
            tried.append(aid)
            for name in INDICES[code]:
                try:
                    txt = post_action(aid, name)
                except Exception as e:  # noqa: BLE001
                    print(f"Индекс: {name} (action {aid[:10]}…) — {e}")
                    continue
                (H.PROBE_DIR / f"index_{name}.txt").write_text(txt, encoding="utf-8")
                pts = []
                for v in _rsc_values(txt):
                    s_ = extract_series(v)
                    if len(s_) > len(pts):
                        pts = s_
                print(f"Индекс: {name} — {len(txt):,} тэмдэгт, {len(pts)} цэг"
                      + (f" ({min(pts)[0]} → {max(pts)[0]})" if pts else ""))
                for d, v in pts:
                    got[d.isoformat()] = v
            if got:
                ACTION_ID = aid          # ажилласан ID-г бусад индекст дахин ашиглана
                break
        if got or attempt:
            break
        try:
            ids = find_action_ids()
            print(f"Индекс: action ID ажилласангүй — хуудаснаас {len(ids)} нэр дэвшигч олдлоо")
        except Exception as e:  # noqa: BLE001
            print(f"Индекс: хуудас татаж чадсангүй ({e})")
            break
    if not got:
        print(f"Индекс: {code} түүх олдсонгүй. data/history/_probe/index_*.txt файлыг шалгана уу "
              "(эсвэл MSE_NEXT_ACTION орчны хувьсагчаар шинэ ID өгнө).")
        return 1
    s_ = read_index(code)
    before = len(s_)
    s_.update(got)                     # mse.mn-ийн түүх давамгайлна
    write_index(s_, code)
    print(f"Индекс: {code} түүх {len(got)} өдөр ({min(got)} → {max(got)}), файлд нийт {len(s_)} (+{len(s_) - before})")
    return 0


def snapshot():
    d = last_trading_day()
    if not d:
        print("Индекс: компаниудын түүх алга — огноо тогтоох боломжгүй, алгасав")
        return 1
    html = H.fetch(SNAPSHOT_URL)
    v = parse_top20(html)
    if not v:
        H.PROBE_DIR.mkdir(parents=True, exist_ok=True)
        (H.PROBE_DIR / "index_snapshot.html").write_text(html, encoding="utf-8")
        print(f"Индекс: {SNAPSHOT_URL} хуудаснаас ТОП-20 утга олдсонгүй (HTML-ийг _probe/index_snapshot.html-д хадгалав)")
        return 1
    s = read_index()
    s[d] = v
    write_index(s)
    print(f"Индекс: ТОП-20 {d} = {v:,.2f} (нийт {len(s)} өдөр)")
    return 0


def import_csv():
    if not IMPORT_FILE.exists():
        print(f"Индекс: {IMPORT_FILE} байхгүй — алгасав")
        return 0
    s, n = read_index(), 0
    with open(IMPORT_FILE, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            d = H.parse_date(r.get("date", ""))
            v = H.num(r.get("value") or r.get("close") or "")
            if d and v:
                s[d.isoformat()] = v
                n += 1
    write_index(s)
    print(f"Индекс: {IMPORT_FILE.name}-ээс {n} мөр нэгтгэв (нийт {len(s)})")
    return 0


def probe():
    """open.mse.mn-ийн нүүр, /securities болон таамагласан хаягуудаас индекстэй холбоотой линк, хүснэгт хайна."""
    H.PROBE_DIR.mkdir(parents=True, exist_ok=True)
    pages = ["/", "/securities", "/indices", "/index", "/indexes", "/market", "/statistics"]
    pat = re.compile(r'href="([^"]*(?:index|indice|top.?20|индекс)[^"]*)"', re.I)
    for path in pages:
        url = H.BASE + path
        try:
            html = H.fetch(url, retries=1)
        except Exception as e:  # noqa: BLE001
            print(f"{url}: татаж чадсангүй ({e})")
            continue
        name = "index_probe_" + (path.strip("/").replace("/", "_") or "home") + ".html"
        (H.PROBE_DIR / name).write_text(html, encoding="utf-8")
        links = sorted(set(pat.findall(html)))
        tables = sum(1 for row in H.parse_rows(html) if any(any(lb in c.lower() for lb in LABELS + ("индекс",)) for c in row["cells"]))
        print(f"{url}: {len(html):,} тэмдэгт · индекстэй мөр {tables} · линк: {', '.join(links[:15]) or '—'}")
    try:
        html = H.fetch(SNAPSHOT_URL, retries=1)
        (H.PROBE_DIR / "index_snapshot.html").write_text(html, encoding="utf-8")
        print(f"{SNAPSHOT_URL}: ТОП-20 = {parse_top20(html)}")
    except Exception as e:  # noqa: BLE001
        print(f"{SNAPSHOT_URL}: татаж чадсангүй ({e})")
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "history":
        import_csv()
        return history()
    if cmd == "snapshot":
        import_csv()
        return snapshot()
    if cmd == "update":                # өдөр бүр: ТОП-20, MSE A, MSE B-ийн бүх түүх; ТОП-20 бүтэлгүйтвэл нөөц snapshot
        import_csv()
        res = {}
        rc = history("TOP20")
        res["TOP20"] = "ok" if rc == 0 else ("snapshot" if snapshot() == 0 else "failed")
        for code in ("MSEA", "MSEB"):
            res[code] = "ok" if history(code) == 0 else "failed"
        STATUS.write_text(json.dumps({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "result": res,
                                      "action_id": ACTION_ID}, ensure_ascii=False), encoding="utf-8")
        return 0 if res["TOP20"] != "failed" else 1
    if cmd == "import":
        return import_csv()
    if cmd == "probe":
        return probe()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
