#!/usr/bin/env python3
"""chart4report — сар, улирал, хагас жил, жилийн ханшийн хөдөлгөөний өнгөт хүснэгт (PNG).
Тоо бүр өгөгдлөөс шууд зурагдана (AI зураг биш)."""
from PIL import Image, ImageDraw

from render_base import (AMBER, AMBER_BG, BLUE, CYAN, G, HDR_SUB, LOGO_GREEN, LOGO_RED, M, MUTED, NAVY1, NAVY2, S, STRIPE,
                         TXT, W, Canvas, card, draw_footer, head_h)


def brand_header(c, title, label, sub, kpis, hdr_h=232):
    """kpis: [(утга, тайлбар, өнгө|None)] — тэнцүү өргөнтэй."""
    if c.dry:
        return
    for yy in range(hdr_h * S):
        t = yy / (hdr_h * S)
        col = tuple(int(NAVY1[i] + (NAVY2[i] - NAVY1[i]) * t) for i in range(3))
        c.d.line([0, yy, W * S, yy], fill=col)
    bx, by = M + 6, 78
    for i, hh in enumerate([22, 36, 52]):
        c.rect(bx + i * 20, by - hh, 14, hh, fill=CYAN, r=2)
    c.line(bx - 4, by - 30, bx + 28, by - 54, (255, 255, 255), 3)
    c.line(bx + 28, by - 54, bx + 18, by - 54, (255, 255, 255), 3)
    c.line(bx + 28, by - 54, bx + 28, by - 44, (255, 255, 255), 3)
    x0 = M + 92
    logo_left = W - M - c.tw("openmind", 52, True) - c.tw("MSE", 52, True)
    base = [(title, 50, True), (label, 38, True), (sub, 28, False)]
    total_w = sum(c.tw(t, s_, b_) for t, s_, b_ in base if t) + 34 + 16
    f = min(1.0, (logo_left - 24 - x0) / total_w)
    xx = x0
    for (t, s_, b_), col_, y_ in zip(base, [(255, 255, 255), CYAN, HDR_SUB], [54, 56, 58]):
        if t:
            xx += c.text(xx, y_, t, s_ * f, b_, col_, "lm") + 16 * f
    c.text(W - M, 50, "MSE", 52, True, LOGO_GREEN, "rm")
    c.text(W - M - c.tw("MSE", 52, True), 50, "openmind", 52, True, (255, 255, 255), "rm")
    c.text(W - M, 92, "powered by Big Short Ganbayar", 20, True, LOGO_RED, "rm")
    ky, kh = 118, 96
    n = len(kpis)
    cw = (W - 2 * M) / n
    for i, (val, cap, col) in enumerate(kpis):
        x = M + i * cw
        if i:
            c.line(x, ky + 6, x, ky + kh - 6, (70, 104, 160), 1)
        c.text(x + 18, ky + 36, val, 38, True, col or (255, 255, 255), "lm", maxw=cw - 30)
        c.text(x + 18, ky + 76, cap, 16, False, HDR_SUB, "lm", maxw=cw - 30)


def render(ctx, rows, header_fn, path, hdr_h=232, foot_h=58):
    def run(c, plan=None):
        header_fn(c, ctx, hdr_h)
        y, heights = hdr_h + G, []
        for ri, row in enumerate(rows):
            rh = max(fn(c, 0, 0, w, 0, ctx) for fn, w in row) if plan is None else plan[ri]
            heights.append(rh)
            if rh and plan is not None:
                x = M
                for fn, w in row:
                    fn(c, x, y, w, rh, ctx)
                    x += w + G
            if rh:
                y += rh + G
        if plan is not None:
            draw_footer(c, y, foot_h)
        return heights, y + foot_h

    heights, total = run(Canvas(None))
    c = Canvas(total)
    run(c, heights)
    c.img.save(path, "PNG", optimize=True)
    return path


# ------------------------------------------------------------------ график хэрэгслүүд


def demo_mark(path):
    """DEMO_DATA=1 үед (зохиомол өгөгдлөөр туршихад) зургийг "ЗОХИОМОЛ ӨГӨГДӨЛ" гэж тод тэмдэглэнэ."""
    import os
    if os.environ.get("DEMO_DATA") != "1":
        return
    im = Image.open(path).convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    f = Canvas(None).font(120, True)
    txt = "ЗОХИОМОЛ ӨГӨГДӨЛ"
    tmp = Image.new("RGBA", (int(f.getlength(txt)) + 40, 200), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((20, 20), txt, font=f, fill=(220, 38, 38, 70))
    tmp = tmp.rotate(24, expand=True, resample=Image.BICUBIC)
    for oy in range(200, im.height, 900):
        ov.paste(tmp, ((im.width - tmp.width) // 2, oy - tmp.height // 2), tmp)
    Image.alpha_composite(im, ov).convert("RGB").save(path, "PNG", optimize=True)


def heat_color(v, cap):
    """Өсөлт ногоон, уналт улаан; хэмжээгээр нь өнгө бүдэг/тод болно. Буцаах: (дэвсгэр, үсгийн өнгө)."""
    if v is None:
        return STRIPE, MUTED
    a = min(1.0, abs(v) / cap)
    al = 0.30 + 0.70 * a
    base = (34, 170, 90) if v >= 0 else (222, 54, 48)
    col = tuple(int(255 - (255 - b) * al) for b in base)
    return col, ((255, 255, 255) if al > 0.58 else TXT)


def pt_header(c, ctx, hdr_h):
    brand_header(c, ctx["title"], "", f"({ctx['range']})", ctx["kpis"], hdr_h)


def pt_table(c, x, y, w, h, ctx):
    cols, rows = ctx["cols"], ctx["rows"]
    sub = ctx["subtitle"]
    hh = head_h(c, sub, w)
    rh, hd = 36, 40
    n_sum = 3 + len(ctx.get("indices") or []) + (1 if ctx.get("wavg") else 0)      # дундаж, [индексүүд], өссөн/унасан, хамрагдсан компани
    need = hh + hd + rh * (len(rows) + n_sum) + 24
    if c.dry:
        return need
    card(c, x, y, w, h, ctx["card_title"], sub, dot=(22, 163, 74))
    has_total = bool(ctx["total_label"])
    ncols = len(cols) + (1 if has_total else 0)
    tx, ty = x + 18, y + hh
    tw_ = w - 36
    first = 262
    cw = min((tw_ - first) / ncols, 170)
    tw_ = first + cw * ncols
    c.rect(tx, ty, tw_, hd, fill=BLUE, r=6)
    c.text(tx + 12, ty + hd / 2, "Компани", 13.5, True, (255, 255, 255), "lm")
    c.text(tx + first - 10, ty + hd / 2, "түүх", 11, False, HDR_SUB, "rm")
    labels = [lab + ("*" if i == len(cols) - 1 and ctx["partial_last"] else "") for i, lab in enumerate(cols)] + ([ctx["total_label"]] if has_total else [])
    for i, lab in enumerate(labels):
        parts = lab.split("\n")
        for k, ln in enumerate(parts):
            c.text(tx + first + cw * i + cw / 2, ty + hd / 2 + (k - (len(parts) - 1) / 2) * 15, ln, 13, True, (255, 255, 255), "mm", maxw=cw - 6)
    yy = ty + hd
    gap = 2.5
    GREY_BG, GREY_FG = (226, 230, 236), (120, 132, 150)

    def cell(i, v, mark, cap, dim=False):
        cx = tx + first + cw * i
        if mark == "nt":
            bg, fg, txt = GREY_BG, GREY_FG, "арилжаагүй"
        else:
            bg, fg = heat_color(v, cap)
            txt = "—" if v is None else f"{v:+.2f}%" + ("†" if mark == "†" else "")
            if dim and v is not None:
                bg, fg = GREY_BG, TXT
        c.rect(cx + gap, yy + gap, cw - 2 * gap, rh - 2 * gap, fill=bg, r=5)
        c.text(cx + cw / 2, yy + rh / 2, txt, 13.5 if mark != "nt" else 11.5, mark != "nt", fg, "mm", maxw=cw - 8)

    for k, row in enumerate(rows):
        if k % 2:
            c.rect(tx, yy, first, rh, fill=STRIPE)
        c.text(tx + 12, yy + rh / 2 - 6, row["key"], 15, True, TXT, "lm")
        if row["flag"]:
            c.triangle_warn(tx + 12 + c.tw(row["key"], 15, True) + 6, yy + rh / 2 - 15, 14, AMBER)
        c.text(tx + first - 10, yy + rh / 2 - 6, row["start"] + "-", 11, False, MUTED, "rm")
        c.text(tx + 12, yy + rh / 2 + 10, row["name"], 11, False, MUTED, "lm", maxw=first - 20)
        for i, (v, m) in enumerate(zip(row["vals"], row["marks"])):
            cell(i, v, m, ctx["cap"])
        if has_total:
            cell(len(cols), row["total"], row["total_mark"], ctx["cap"] * 2.2)
        yy += rh
    # нэгтгэл мөрүүд
    c.line(tx, yy + 1, tx + tw_, yy + 1, (170, 186, 210), 1.2)
    c.text(tx + 12, yy + rh / 2, "МХБ-н 20 (тэнцүү жин)", 13.5, True, TXT, "lm", maxw=first - 16)
    full_n = ctx["n_rows"]
    for i, v in enumerate(ctx["avg"] + ([ctx["avg_total"]] if has_total else [])):
        cell(i, v, "", ctx["cap"] if i < len(cols) else ctx["cap"] * 2.2, dim=ctx["ns"][i] < full_n)
    yy += rh
    if ctx.get("wavg"):
        c.text(tx + 12, yy + rh / 2, "МХБ-н 20 (үнэлгээгээр)", 13.5, True, TXT, "lm", maxw=first - 16)
        for i, v in enumerate(ctx["wavg"][:ncols]):
            cell(i, v, "", ctx["cap"] if i < len(cols) else ctx["cap"] * 2.2)
        yy += rh
    for ix in ctx.get("indices") or []:
        c.text(tx + 12, yy + rh / 2, ix["name"], 13.5, True, TXT, "lm", maxw=first - 16)
        for i, v in enumerate(ix["vals"] + ([ix["total"]] if has_total else [])):
            cell(i, v, "", ctx["cap"] if i < len(cols) else ctx["cap"] * 2.2)
        yy += rh
    c.text(tx + 12, yy + rh / 2, "Өссөн ↑ / Унасан ↓", 13.5, True, TXT, "lm", maxw=first - 16)
    for i, (u, d) in enumerate(ctx["counts"][:ncols]):
        c.text(tx + first + cw * i + cw / 2, yy + rh / 2, f"{u} / {d}", 13.5, True, TXT, "mm", maxw=cw - 6)
    yy += rh
    c.text(tx + 12, yy + rh / 2, "Хамрагдсан компани", 13.5, True, TXT, "lm", maxw=first - 16)
    for i, nn in enumerate(ctx["ns"][:ncols]):
        c.text(tx + first + cw * i + cw / 2, yy + rh / 2, f"{nn}/{full_n}", 13.5, nn == full_n, TXT if nn == full_n else GREY_FG, "mm", maxw=cw - 6)
    return need


def pt_note(c, x, y, w, h, ctx):
    wrapped = [c.wrap(t, 14, w - 36) for t in ctx["notes"]]
    need = 22 + sum(len(wl) * 20 + 6 for wl in wrapped) + 12
    if c.dry:
        return need
    c.rect(x, y, w, h, fill=AMBER_BG, outline=(240, 200, 120), r=14)
    yy = y + 20
    for wl in wrapped:
        for ln in wl:
            c.text(x + 18, yy, ln, 14, False, TXT, "lm")
            yy += 20
        yy += 6
    return need


def render_periods(ctx, path):
    render(ctx, [[(pt_table, 1344)], [(pt_note, 1344)]], pt_header, path)
    demo_mark(path)
    return path
