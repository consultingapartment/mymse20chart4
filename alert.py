#!/usr/bin/env python3
"""chart4report — алдааны мэдэгдлийг ХУВИЙН Telegram чат руу илгээнэ (суваг руу биш).

    python alert.py --check-status      # татах алдаа, сайтын бүтцийн өөрчлөлт, хуучирсан ханш, шинэ ±15% үсрэлт, индекс
    python alert.py --send-file ФАЙЛ "тайлбар"   # файлыг (жишээ нь Excel) хувийн чат руу илгээнэ
    python alert.py "мессеж"            # шууд мэдэгдэл (workflow унасан үед)

Орчны хувьсагч:
    TELEGRAM_BOT_TOKEN       суваг руу илгээдэг ботын токен (адилхан)
    TELEGRAM_ADMIN_CHAT_ID   таны хувийн чатын ID (ботод нэг удаа /start бичсэн байх ёстой)
    ALERT_MAX_FAILED         анхдагч 3 — үүнээс ОЛОН компани алдаатай бол мэдэгдэнэ
    ALERT_STALE_DAYS         анхдагч 30 — сүүлийн ханш бусдаас үүнээс олон хоногоор хоцорвол мэдэгдэнэ
Нэг асуудлыг өдөр бүр давтахгүйн тулд мэдэгдсэнээ data/history/alerted.json-д тэмдэглэнэ.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

import history_mse as H


def run_url():
    srv, repo, rid = (os.environ.get(k, "") for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{srv}/{repo}/actions/runs/{rid}" if srv and repo and rid else ""


def send(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "").strip()
    url = run_url()
    if url:
        text += f"\n{url}"
    if not token or not chat:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_ADMIN_CHAT_ID тохируулаагүй тул мэдэгдэл илгээхгүй:\n" + text)
        return 0
    api = os.environ.get("TELEGRAM_API_URL", "https://api.telegram.org").rstrip("/") + f"/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(api, data=data), timeout=60) as r:
            r.read()
        print("Алдааны мэдэгдэл хувийн чат руу илгээгдлээ.")
    except (urllib.error.URLError, OSError) as e:
        print(f"Мэдэгдэл илгээж чадсангүй: {e}")
    return 0


ALERTED = H.HIST_DIR / "alerted.json"
NO_ROWS = "хуудаснаас ханшийн мөр олдсонгүй"


def send_file(path, caption=""):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "").strip()
    if not token or not chat:
        print(f"TELEGRAM_BOT_TOKEN / TELEGRAM_ADMIN_CHAT_ID тохируулаагүй — {path} илгээхгүй")
        return 0
    import mimetypes
    import uuid
    from pathlib import Path
    f = Path(path)
    if not f.exists():
        print(f"{path} байхгүй")
        return 0
    import hashlib
    reg = Path(os.environ.get("REPORT_DIR", "reports")) / "admin_sent.json"
    sent = _load(reg, [])
    h = hashlib.sha256(f.read_bytes()).hexdigest()
    if h in sent and os.environ.get("FORCE_SEND", "").lower() != "true":
        print(f"{f.name} өмнө илгээгдсэн — давтахгүй")
        return 0
    bnd = uuid.uuid4().hex
    parts = []
    for k, v in (("chat_id", chat), ("caption", caption[:1000])):
        parts.append(f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    ct = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    parts.append(f'--{bnd}\r\nContent-Disposition: form-data; name="document"; filename="{f.name}"\r\n'
                 f"Content-Type: {ct}\r\n\r\n".encode() + f.read_bytes() + b"\r\n")
    parts.append(f"--{bnd}--\r\n".encode())
    api = os.environ.get("TELEGRAM_API_URL", "https://api.telegram.org").rstrip("/") + f"/bot{token}/sendDocument"
    req = urllib.request.Request(api, data=b"".join(parts), headers={"Content-Type": f"multipart/form-data; boundary={bnd}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            r.read()
        print(f"{f.name} хувийн чат руу илгээгдлээ.")
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text(json.dumps((sent + [h])[-200:]), encoding="utf-8")
    except (urllib.error.URLError, OSError) as e:
        print(f"Файл илгээж чадсангүй: {e}")
    return 0


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except ValueError:
        return default


def check_status():
    msgs = []
    seen = _load(ALERTED, {"stale": [], "breaks": []})
    # 1) татах алдаа ба сайтын бүтцийн өөрчлөлт
    st = _load(H.STATUS_FILE, None)
    if st is None:
        msgs.append("⚠ Ханшийн түүх татах алхам дүнгээ бичээгүй (status.json алга) — workflow-ийн логийг шалгана уу.")
    else:
        failed, ok = st.get("failed", {}), st.get("ok", [])
        limit = int(os.environ.get("ALERT_MAX_FAILED", "3"))
        print(f"Татах дүн: {len(ok)} амжилттай, {len(failed)} алдаатай (босго: {limit}-аас олон)")
        norows = [k for k, v in failed.items() if NO_ROWS in v]
        if norows and len(norows) * 2 >= len(ok) + len(failed):
            msgs.append(f"🛠 open.mse.mn-ийн хуудасны бүтэц өөрчлөгдсөн байж болзошгүй: {len(norows)} компанийн хуудаснаас "
                        "ханшийн хүснэгт уншигдсангүй (сайт ажиллаж байгаа ч хүснэгт танигдахгүй байна). "
                        "Run workflow → history_probe ажиллуулж data/history/_probe/-ийг шалгана уу.")
        elif len(failed) > limit:
            lines = "\n".join(f"• {k}: {v}" for k, v in sorted(failed.items()))
            msgs.append(f"⚠ {len(failed)} компанийн ханшийн түүх open.mse.mn-ээс татагдсангүй ({st.get('cmd')}).\n{lines}")
    # 2) индекс
    ist = _load(H.HIST_DIR / "index_status.json", None)
    if ist and ist.get("result", {}).get("TOP20") == "failed":
        msgs.append("🛠 ТОП-20 индекс mse.mn/mse-index-ээс татагдсангүй (нөөц members.mse.mn ч бүтэлгүйтэв). "
                    "Сайтын next-action ID солигдсон байж болзошгүй — data/history/_probe/index_*.txt-ийг шалгана уу.")
    elif ist and ist.get("result", {}).get("TOP20") == "snapshot":
        msgs.append("ℹ ТОП-20-ийн түүх mse.mn/mse-index-ээс татагдсангүй, зөвхөн өнөөдрийн утгыг members.mse.mn-ээс авлаа.")
    # 3) хуучирсан ханш ба шинэ ±15% үсрэлт
    data = {k: H.read_csv(k) for k in H.KEYS}
    latest = max((max(b) for b in data.values() if b), default=None)
    stale_days = int(os.environ.get("ALERT_STALE_DAYS", "30"))
    manual = H.load_adjustments()
    stale_now, new_stale, new_breaks, all_breaks, new_splits = [], [], [], [], []
    for k, bars in data.items():
        if not bars or not latest:
            continue
        lag = (H.date.fromisoformat(latest) - H.date.fromisoformat(max(bars))).days
        if lag > stale_days:
            stale_now.append(k)
            if k not in seen["stale"]:
                new_stale.append(f"{k} (сүүлийн ханш {max(bars)}, {lag} хоног)")
        closes = {d: x["close"] for d, x in bars.items()}
        eff = H.effective_adjustments(k, closes, manual.get(k, []))
        for d, f, note in eff:
            key = f"{k}:{d}"
            if note.startswith("автомат"):
                all_breaks.append(key)
                if key not in seen["breaks"]:
                    new_splits.append(f"{k} {d}: {note.replace('автомат: ', '')} (өмнөх ханш ×{f:g})")
        for b in H.limit_breaks(closes):
            if any(b["date"] == d for d, _, _ in eff):
                continue
            key = f"{k}:{b['date']}"
            all_breaks.append(key)
            if key not in seen["breaks"]:
                new_breaks.append(f"{k} {b['prev_date']} → {b['date']}: {b['prev_close']:,.2f} → {b['close']:,.2f} ({b['change'] * 100:+.1f}%)")
    if new_stale:
        msgs.append(f"⏳ {stale_days}+ хоног шинэчлэгдээгүй ханш:\n" + "\n".join("• " + x for x in new_stale))
    # ҮЦТХТ-ийн тайлангаар хуваалт (гараар ба автомат) баталгаажсан эсэх
    reg_msgs, reg_keys = [], []
    try:
        import shares as S
        shs = S.load()
    except Exception:  # noqa: BLE001
        S, shs = None, {}
    if shs:
        for k, bars in data.items():
            closes = {d: x["close"] for d, x in bars.items()}
            for d, f, note in H.effective_adjustments(k, closes, manual.get(k, [])):
                if f == 1:
                    continue
                st, ratio = S.confirm_split(shs.get(k), d, f)
                key = f"reg:{k}:{d}:{st}"
                reg_keys.append(key)
                if st in ("pending", "nodata") or key in seen.get("registry", []):
                    continue
                txt = {"confirmed": f"✅ {k} {d}: ×{f:g} хуваалтыг ҮЦТХТ-ийн хувьцааны тоо баталлаа",
                       "corrected": f"🔁 {k} {d}: ҮЦТХТ-ийн харьцаа ×{ratio:.4g} (бүртгэсэн ×{f:g}) — шалгана уу",
                       "contradicted": f"❓ {k} {d}: ×{f:g} засвар байгаа ч ҮЦТХТ-д хувьцааны тоо өөрчлөгдөөгүй — шалгана уу"}[st]
                reg_msgs.append(txt)
    if reg_msgs:
        msgs.append("ҮЦТХТ-ийн тайлангаар хуваалтын шалгалт:\n" + "\n".join("• " + x for x in reg_msgs))
    if new_splits:
        msgs.append("✂ Хуваалт автоматаар танигдаж, чартад засагдлаа (буруу бол data/adjustments.csv-д тэр өдрийг factor=1 гэж бичнэ):\n"
                    + "\n".join("• " + x for x in new_splits))
    if new_breaks:
        shown = new_breaks[:15]
        msgs.append(f"⚡ Өдрийн хязгаар (±{H.DAILY_LIMIT * 100:g}%)-аас их, тайлбаргүй шинэ өөрчлөлт — хуваалт бол "
                    "data/adjustments.csv-д нэмнэ үү:\n" + "\n".join("• " + x for x in shown)
                    + (f"\n… бас {len(new_breaks) - len(shown)}" if len(new_breaks) > len(shown) else ""))
    ALERTED.parent.mkdir(parents=True, exist_ok=True)
    ALERTED.write_text(json.dumps({"stale": stale_now, "breaks": sorted(set(all_breaks)),
                                   "registry": sorted(set(reg_keys) | set(seen.get("registry", [])))}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    if not msgs:
        print("Мэдэгдэх асуудал алга.")
        return 0
    return send("chart4report:\n\n" + "\n\n".join(msgs))


def main(argv):
    if len(argv) > 1 and argv[1] == "--check-status":
        return check_status()
    if len(argv) > 2 and argv[1] == "--send-file":
        return send_file(argv[2], " ".join(argv[3:]))
    if len(argv) > 1:
        return send(" ".join(argv[1:]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
