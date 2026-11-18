#!/usr/bin/env python3
"""chart4report — зургийн суурь: Canvas, өнгө, фонт, карт, хөл.
Хэрэгтэй: Pillow ба Cyrillic фонт (fonts-liberation эсвэл fonts-dejavu-core).
    WEEKLY_FONT / WEEKLY_FONT_BOLD орчны хувьсагчаар өөр фонт зааж болно.
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont

S = 2            # нягтрал: логик 1 px = 2 бодит px (зураг 2800 px өргөнтэй)
W = 1400         # логик өргөн
M, G = 28, 18    # захын зай, картуудын завсар

BG = (232, 239, 248)
CARD = (255, 255, 255)
BORDER = (205, 217, 234)
NAVY1, NAVY2 = (8, 25, 60), (22, 62, 112)
BLUE = (30, 86, 160)
TXT = (18, 32, 62)
MUTED = (100, 116, 142)
GREEN = (22, 160, 74)
RED = (220, 38, 38)
GREEN_BG, RED_BG = (226, 246, 233), (253, 232, 232)
BLUE_BG, AMBER_BG, AMBER = (226, 238, 252), (255, 244, 214), (217, 119, 6)
CYAN = (86, 204, 255)
LOGO_GREEN, LOGO_RED = (61, 220, 132), (255, 64, 64)
STRIPE = (244, 248, 253)
HDR_SUB = (176, 200, 232)

_FONT_SETS = [
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def _find_fonts():
    reg, bold = os.environ.get("WEEKLY_FONT"), os.environ.get("WEEKLY_FONT_BOLD")
    if reg and bold and os.path.exists(reg) and os.path.exists(bold):
        return reg, bold
    for reg, bold in _FONT_SETS:
        if os.path.exists(reg) and os.path.exists(bold):
            return reg, bold
    raise RuntimeError("Cyrillic фонт олдсонгүй (fonts-liberation эсвэл fonts-dejavu-core суулгана уу)")



class Canvas:
    def __init__(self, h=None):
        self.dry = h is None
        self.fonts = {}
        self.reg, self.bold = _find_fonts()
        if not self.dry:
            self.img = Image.new("RGB", (W * S, int(h) * S), BG)
            self.d = ImageDraw.Draw(self.img)

    def font(self, size, bold=False):
        key = (round(size * 2) / 2, bold)
        if key not in self.fonts:
            self.fonts[key] = ImageFont.truetype(self.bold if bold else self.reg, int(round(key[0] * S)))
        return self.fonts[key]

    def tw(self, s, size, bold=False):
        return self.font(size, bold).getlength(s) / S

    def fit(self, s, size, bold, maxw, minsize=9):
        while maxw and size > minsize and self.tw(s, size, bold) > maxw:
            size -= 0.5
        return size

    def wrap(self, s, size, maxw, bold=False):
        words, lines, cur = s.split(" "), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if self.tw(t, size, bold) <= maxw or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def rect(self, x, y, w, h, fill=None, outline=None, r=0, bw=1):
        if self.dry:
            return
        box = [x * S, y * S, (x + w) * S - 1, (y + h) * S - 1]
        width = int(bw * S) if outline else 0
        if r:
            self.d.rounded_rectangle(box, radius=r * S, fill=fill, outline=outline, width=width)
        else:
            self.d.rectangle(box, fill=fill, outline=outline, width=width)

    def circle(self, cx, cy, r, fill):
        if not self.dry:
            self.d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], fill=fill)

    def line(self, x1, y1, x2, y2, fill, w=1):
        if not self.dry:
            self.d.line([x1 * S, y1 * S, x2 * S, y2 * S], fill=fill, width=max(1, int(w * S)))

    def text(self, x, y, s, size=18, bold=False, fill=TXT, anchor="lm", maxw=None):
        size = self.fit(s, size, bold, maxw)
        if not self.dry:
            self.d.text((x * S, y * S), s, font=self.font(size, bold), fill=fill, anchor=anchor)
        return self.tw(s, size, bold)

    def star(self, cx, cy, r, fill):
        if self.dry:
            return
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rad = r if i % 2 == 0 else r * 0.45
            pts.append(((cx + rad * math.cos(ang)) * S, (cy + rad * math.sin(ang)) * S))
        self.d.polygon(pts, fill=fill)

    def triangle_warn(self, x, y, size, fill):
        if self.dry:
            return
        self.d.polygon([((x + size / 2) * S, y * S), ((x + size) * S, (y + size * 0.88) * S), (x * S, (y + size * 0.88) * S)], fill=fill)
        self.text(x + size / 2, y + size * 0.62, "!", size * 0.62, True, (255, 255, 255), "mm")



def head_h(c, sub, w):
    if not sub:
        return 50
    return 46 + 17 * len(c.wrap(sub, 13, w - 36)) + 6


def card(c, x, y, w, h, title, sub=None, dot=BLUE):
    c.rect(x, y, w, h, fill=CARD, outline=BORDER, r=14)
    c.circle(x + 22, y + 26, 7, dot)
    c.text(x + 38, y + 26, title, 22, True, TXT, "lm", maxw=w - 56)
    if sub:
        for i, ln in enumerate(c.wrap(sub, 13, w - 36)):
            c.text(x + 18, y + 54 + i * 17, ln, 13, False, MUTED, "lm")


def draw_footer(c, y, fh):
    if c.dry:
        return
    c.rect(0, y, W, fh, fill=NAVY1)
    c.triangle_warn(M, y + fh / 2 - 13, 26, (245, 190, 40))
    c.text(M + 40, y + fh / 2, "Энэ нь хөрөнгө оруулалтын зөвлөгөө биш, зөвхөн хаалтын ханшийн статистик тойм юм.", 17, False, (255, 255, 255), "lm")
    c.text(W - M, y + fh / 2, "openmindMSE · powered by Big Short Ganbayar", 14, True, HDR_SUB, "rm")
