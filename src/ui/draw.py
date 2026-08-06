"""
draw.py -- 2D 批处理绘制层

所有 UI 元素写入同一条顶点流 (pos2 + uv2 + rgba), 按 mode 分段提交:
    mode 0 = 纯色   1 = 字形(r通道当alpha)   2 = 普通纹理
连续同 mode 的元素自动合并为一次 draw call。
"""
from __future__ import annotations

import math

import numpy as np

from ..engine import math3d as m3
from ..engine.renderer import setu, setm

F32 = np.float32
STRIDE = 8  # x y u v r g b a


class UIBatch:
    def __init__(self, ctx, renderer, atlas):
        self.ctx = ctx
        self.r = renderer
        self.atlas = atlas
        self.prog = renderer.p_ui
        self._cap = 65536
        self.vbo = ctx.buffer(reserve=self._cap * STRIDE * 4, dynamic=True)
        self.vao = ctx.vertex_array(
            self.prog,
            [(self.vbo, "2f 2f 4f", "in_pos", "in_uv", "in_color")],
        )
        self.verts = []
        self.runs = []
        self.width = 1280
        self.height = 720

    # ------------------------------------------------------------------
    def begin(self, width, height):
        self.width, self.height = width, height
        self.verts.clear()
        self.runs.clear()

    def _push(self, mode, data, tex=None):
        n = len(data) // STRIDE
        if self.runs and self.runs[-1][0] == mode and self.runs[-1][3] is tex:
            self.runs[-1][2] += n
        else:
            self.runs.append([mode, len(self.verts) // STRIDE, n, tex])
        self.verts.extend(data)

    # ------------------------------------------------------------------
    # 基本图元
    # ------------------------------------------------------------------
    def quad(self, x, y, w, h, color, uv=(0, 0, 1, 1), mode=0, tex=None):
        r, g, b, a = color
        u0, v0, u1, v1 = uv
        x1, y1 = x + w, y + h
        d = [x, y, u0, v0, r, g, b, a,
             x1, y, u1, v0, r, g, b, a,
             x1, y1, u1, v1, r, g, b, a,
             x, y, u0, v0, r, g, b, a,
             x1, y1, u1, v1, r, g, b, a,
             x, y1, u0, v1, r, g, b, a]
        self._push(mode, d, tex)

    def image(self, x, y, w, h, tex, color=(1, 1, 1, 1), uv=(0, 0, 1, 1)):
        """绘制任意纹理 (小地图 / 立绘)。"""
        self.quad(x, y, w, h, color, uv, mode=2, tex=tex)

    def quad_grad(self, x, y, w, h, c_top, c_bot):
        r0, g0, b0, a0 = c_top
        r1, g1, b1, a1 = c_bot
        x1, y1 = x + w, y + h
        d = [x, y, 0, 0, r0, g0, b0, a0,
             x1, y, 0, 0, r0, g0, b0, a0,
             x1, y1, 0, 0, r1, g1, b1, a1,
             x, y, 0, 0, r0, g0, b0, a0,
             x1, y1, 0, 0, r1, g1, b1, a1,
             x, y1, 0, 0, r1, g1, b1, a1]
        self._push(0, d)

    def quad_grad_h(self, x, y, w, h, c_left, c_right):
        r0, g0, b0, a0 = c_left
        r1, g1, b1, a1 = c_right
        x1, y1 = x + w, y + h
        d = [x, y, 0, 0, r0, g0, b0, a0,
             x1, y, 0, 0, r1, g1, b1, a1,
             x1, y1, 0, 0, r1, g1, b1, a1,
             x, y, 0, 0, r0, g0, b0, a0,
             x1, y1, 0, 0, r1, g1, b1, a1,
             x, y1, 0, 0, r0, g0, b0, a0]
        self._push(0, d)

    def outline(self, x, y, w, h, color, t=1.0):
        self.quad(x, y, w, t, color)
        self.quad(x, y + h - t, w, t, color)
        self.quad(x, y, t, h, color)
        self.quad(x + w - t, y, t, h, color)

    def tri(self, p0, p1, p2, color):
        r, g, b, a = color
        d = []
        for p in (p0, p1, p2):
            d += [p[0], p[1], 0, 0, r, g, b, a]
        self._push(0, d)

    def circle(self, cx, cy, radius, color, seg=32):
        r, g, b, a = color
        d = []
        for i in range(seg):
            a0 = i / seg * math.tau
            a1 = (i + 1) / seg * math.tau
            d += [cx, cy, 0, 0, r, g, b, a,
                  cx + math.cos(a0) * radius, cy + math.sin(a0) * radius, 0, 0, r, g, b, a,
                  cx + math.cos(a1) * radius, cy + math.sin(a1) * radius, 0, 0, r, g, b, a]
        self._push(0, d)

    def ring(self, cx, cy, r_in, r_out, color, seg=48, start=0.0, sweep=math.tau):
        r, g, b, a = color
        d = []
        n = max(int(seg * (abs(sweep) / math.tau)), 1)
        for i in range(n):
            a0 = start + sweep * (i / n)
            a1 = start + sweep * ((i + 1) / n)
            c0, s0 = math.cos(a0), math.sin(a0)
            c1, s1 = math.cos(a1), math.sin(a1)
            p0 = (cx + c0 * r_in, cy + s0 * r_in)
            p1 = (cx + c0 * r_out, cy + s0 * r_out)
            p2 = (cx + c1 * r_out, cy + s1 * r_out)
            p3 = (cx + c1 * r_in, cy + s1 * r_in)
            for p in (p0, p1, p2, p0, p2, p3):
                d += [p[0], p[1], 0, 0, r, g, b, a]
        self._push(0, d)

    def line(self, x0, y0, x1, y1, color, t=1.0):
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy)
        if ln < 1e-5:
            return
        nx, ny = -dy / ln * t * 0.5, dx / ln * t * 0.5
        r, g, b, a = color
        d = []
        for p in ((x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny),
                  (x0 + nx, y0 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)):
            d += [p[0], p[1], 0, 0, r, g, b, a]
        self._push(0, d)

    def panel(self, x, y, w, h, fill=(0, 0, 0, 0.62), border=(0.72, 0.70, 0.66, 0.30),
              corner=10.0, accent=None):
        """带斜切角的面板 —— 全局 UI 的统一底板样式。"""
        self.quad(x + corner, y, w - corner * 2, h, fill)
        self.quad(x, y + corner, corner, h - corner * 2, fill)
        self.quad(x + w - corner, y + corner, corner, h - corner * 2, fill)
        self.tri((x + corner, y), (x, y + corner), (x + corner, y + corner), fill)
        self.tri((x + w - corner, y), (x + w, y + corner), (x + w - corner, y + corner), fill)
        self.tri((x + corner, y + h), (x, y + h - corner), (x + corner, y + h - corner), fill)
        self.tri((x + w - corner, y + h), (x + w, y + h - corner), (x + w - corner, y + h - corner), fill)
        if border:
            self.line(x + corner, y, x + w - corner, y, border, 1.2)
            self.line(x + corner, y + h, x + w - corner, y + h, border, 1.2)
            self.line(x, y + corner, x, y + h - corner, border, 1.2)
            self.line(x + w, y + corner, x + w, y + h - corner, border, 1.2)
            self.line(x + corner, y, x, y + corner, border, 1.2)
            self.line(x + w - corner, y, x + w, y + corner, border, 1.2)
            self.line(x + corner, y + h, x, y + h - corner, border, 1.2)
            self.line(x + w - corner, y + h, x + w, y + h - corner, border, 1.2)
        if accent:
            self.quad(x + corner, y + h - 2.0, (w - corner * 2) * accent[0], 2.0, accent[1])

    # ------------------------------------------------------------------
    # 文本
    # ------------------------------------------------------------------
    def text(self, x, y, s, size=20, color=(1, 1, 1, 1), align="left", shadow=None):
        """y 为基线上方的行顶。返回绘制宽度。"""
        if not s:
            return 0.0
        w = self.atlas.measure(s, size)
        if align == "center":
            x -= w * 0.5
        elif align == "right":
            x -= w
        if shadow:
            self._text_run(x + 1.4, y + 1.6, s, size, shadow)
        self._text_run(x, y, s, size, color)
        return w

    def _text_run(self, x, y, s, size, color):
        asc = self.atlas.ascent(size)
        r, g, b, a = color
        pen = x
        d = []
        for ch in s:
            gl = self.atlas.glyph(ch, size)
            if gl.w > 0 and gl.h > 0:
                gx = pen + gl.bx
                gy = y + asc + gl.by - asc
                gy = y + gl.by
                x1, y1 = gx + gl.w, gy + gl.h
                d += [gx, gy, gl.u0, gl.v0, r, g, b, a,
                      x1, gy, gl.u1, gl.v0, r, g, b, a,
                      x1, y1, gl.u1, gl.v1, r, g, b, a,
                      gx, gy, gl.u0, gl.v0, r, g, b, a,
                      x1, y1, gl.u1, gl.v1, r, g, b, a,
                      gx, y1, gl.u0, gl.v1, r, g, b, a]
            pen += gl.adv
        if d:
            self._push(1, d)

    def text_block(self, x, y, s, size, color, max_width, line_gap=1.5, shadow=None,
                   max_lines=None):
        lines = self.atlas.wrap(s, size, max_width)
        if max_lines:
            lines = lines[:max_lines]
        lh = self.atlas.line_height(size) * line_gap
        for i, ln in enumerate(lines):
            self.text(x, y + i * lh, ln, size, color, shadow=shadow)
        return len(lines) * lh

    # ------------------------------------------------------------------
    def flush(self):
        if not self.verts:
            return
        arr = np.asarray(self.verts, F32)
        need = len(arr) // STRIDE
        if need > self._cap:
            self._cap = int(need * 1.6) + 1024
            self.vbo.orphan(self._cap * STRIDE * 4)
        self.vbo.write(arr.tobytes())

        c = self.ctx
        c.disable(c.DEPTH_TEST)
        c.enable(c.BLEND)
        c.blend_func = c.SRC_ALPHA, c.ONE_MINUS_SRC_ALPHA
        proj = m3.ortho(0, self.width, self.height, 0, -1, 1)
        setm(self.prog, "u_proj", proj)
        setu(self.prog, "u_tex", 0)
        for mode, start, count, tex in self.runs:
            (tex if tex is not None else self.atlas.tex).use(0)
            setu(self.prog, "u_mode", mode)
            self.vao.render(mode=c.TRIANGLES, vertices=count, first=start)
        c.disable(c.BLEND)
        self.verts.clear()
        self.runs.clear()
