"""
text.py -- 动态中文字形图集

CJK 字符集过大, 不能预烘焙整张字体贴图。这里用「按需光栅化 + 货架式装箱」:
首次遇到某个 (字符, 字号) 时用 PIL 渲染成灰度位图, 写入一张 2048^2 的 R8 纹理,
之后直接查缓存。UI 着色器以 r 通道作为 alpha。
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ATLAS = 2048

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhl.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/deng.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def find_font():
    env = os.environ.get("RENWAI_FONT")
    if env and os.path.exists(env):
        return env
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = os.path.join(base, "assets", "fonts", "ui.ttf")
        if os.path.exists(p):
            return p
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    p = os.path.join(here, "assets", "fonts", "ui.ttf")
    if os.path.exists(p):
        return p
    for c in _FONT_CANDIDATES:
        if os.path.exists(c):
            return c
    return None


class Glyph:
    __slots__ = ("u0", "v0", "u1", "v1", "w", "h", "bx", "by", "adv")

    def __init__(self, u0, v0, u1, v1, w, h, bx, by, adv):
        self.u0, self.v0, self.u1, self.v1 = u0, v0, u1, v1
        self.w, self.h, self.bx, self.by, self.adv = w, h, bx, by, adv


class FontAtlas:
    def __init__(self, ctx, path=None):
        self.ctx = ctx
        self.path = path or find_font()
        self._fonts = {}
        self._glyphs = {}
        self._metrics = {}
        self.tex = ctx.texture((ATLAS, ATLAS), 1, dtype="f1")
        self.tex.filter = (ctx.LINEAR, ctx.LINEAR)
        self.tex.repeat_x = self.tex.repeat_y = False
        self.tex.swizzle = "RRRR"
        self._clear_atlas()
        # 货架装箱游标
        self._cx = 1
        self._cy = 1
        self._row_h = 0

    def _clear_atlas(self):
        self.tex.write(np.zeros((ATLAS, ATLAS), np.uint8).tobytes())

    def font(self, size):
        size = int(size)
        f = self._fonts.get(size)
        if f is None:
            try:
                if self.path and self.path.lower().endswith(".ttc"):
                    f = ImageFont.truetype(self.path, size, index=0)
                elif self.path:
                    f = ImageFont.truetype(self.path, size)
                else:
                    f = ImageFont.load_default()
            except Exception:
                f = ImageFont.load_default()
            self._fonts[size] = f
        return f

    def line_height(self, size):
        m = self._metrics.get(size)
        if m is None:
            f = self.font(size)
            try:
                asc, desc = f.getmetrics()
            except Exception:
                asc, desc = int(size * 0.8), int(size * 0.2)
            m = (asc, desc, asc + desc)
            self._metrics[size] = m
        return m[2]

    def ascent(self, size):
        self.line_height(size)
        return self._metrics[int(size)][0]

    # ------------------------------------------------------------------
    def glyph(self, ch, size):
        size = int(size)
        key = (ch, size)
        g = self._glyphs.get(key)
        if g is not None:
            return g
        f = self.font(size)
        try:
            bbox = f.getbbox(ch)
        except Exception:
            bbox = (0, 0, size, size)
        if bbox is None:
            bbox = (0, 0, 0, 0)
        x0, y0, x1, y1 = bbox
        w = max(int(x1 - x0), 0)
        h = max(int(y1 - y0), 0)
        try:
            adv = f.getlength(ch)
        except Exception:
            adv = w
        if w == 0 or h == 0:
            g = Glyph(0, 0, 0, 0, 0, 0, 0, 0, float(adv))
            self._glyphs[key] = g
            return g

        pad = 1
        img = Image.new("L", (w + pad * 2, h + pad * 2), 0)
        d = ImageDraw.Draw(img)
        d.text((pad - x0, pad - y0), ch, font=f, fill=255)
        aw, ah = img.size

        if self._cx + aw >= ATLAS:
            self._cx = 1
            self._cy += self._row_h + 1
            self._row_h = 0
        if self._cy + ah >= ATLAS:
            # 图集满: 重置 (极端长会话下的兜底, 实际几乎不会触发)
            self._clear_atlas()
            self._glyphs.clear()
            self._cx = self._cy = 1
            self._row_h = 0

        px, py = self._cx, self._cy
        self.tex.write(np.asarray(img, np.uint8).tobytes(), viewport=(px, py, aw, ah))
        self._cx += aw + 1
        self._row_h = max(self._row_h, ah)

        g = Glyph((px + pad) / ATLAS, (py + pad) / ATLAS,
                  (px + pad + w) / ATLAS, (py + pad + h) / ATLAS,
                  w, h, int(x0), int(y0), float(adv))
        self._glyphs[key] = g
        return g

    # ------------------------------------------------------------------
    def measure(self, text, size):
        w = 0.0
        for ch in text:
            if ch == "\n":
                continue
            w += self.glyph(ch, size).adv
        return w

    def wrap(self, text, size, max_width):
        """按像素宽度折行, 返回行列表。中文逐字断行, 英文按空格。"""
        lines = []
        for para in text.split("\n"):
            if not para:
                lines.append("")
                continue
            cur, curw = "", 0.0
            i = 0
            while i < len(para):
                ch = para[i]
                gw = self.glyph(ch, size).adv
                if curw + gw > max_width and cur:
                    # 尝试在最近的空格处断开 (拉丁文本)
                    if ch.isascii() and ch not in " ,.;:!?)]}":
                        sp = cur.rfind(" ")
                        if sp > 0 and len(cur) - sp < 18:
                            lines.append(cur[:sp])
                            cur = cur[sp + 1:]
                            curw = self.measure(cur, size)
                            continue
                    lines.append(cur)
                    cur, curw = "", 0.0
                cur += ch
                curw += gw
                i += 1
            if cur:
                lines.append(cur)
        return lines
