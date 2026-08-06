"""
hud.py -- 全部 2D 界面

包含: 主菜单 / 载入页 / 章节卡 / 区域横幅 / 对话框 / 任务追踪 / 罗盘 /
      体力环 / 交互提示 / 小地图 / 全图 / 残片手记 / 暂停菜单 / 结局演出
所有绘制都通过 UIBatch 汇入同一条顶点流。
"""
from __future__ import annotations

import math

import numpy as np

from ..data import story as ST
from ..world import terrain as T

F32 = np.float32

INK = (0.035, 0.040, 0.048, 0.86)
INK_SOFT = (0.05, 0.055, 0.065, 0.62)
GOLD = (0.855, 0.775, 0.585, 1.0)
GOLD_DIM = (0.68, 0.64, 0.57, 0.72)
PAPER = (0.90, 0.885, 0.855, 1.0)
DIMTXT = (0.74, 0.73, 0.70, 0.80)
TEAL = (0.40, 0.82, 0.76, 1.0)
RED = (0.86, 0.40, 0.36, 1.0)
SHADOW = (0.0, 0.0, 0.0, 0.70)

REGION_MARK = {
    "wilds": (0.86, 0.78, 0.52), "blackstone": (0.62, 0.52, 0.86),
    "lostland": (0.46, 0.86, 0.84), "silenthall": (0.88, 0.74, 0.48),
    "mutezone": (0.66, 0.66, 0.66), "mirror": (0.52, 0.62, 0.98),
}


def _sc(w, h):
    """按 1280x720 基准的 UI 缩放。"""
    return max(0.72, min(w / 1280.0, h / 720.0))


class Minimap:
    """由地形反照率 + 山体阴影烘焙出的世界底图。"""

    def __init__(self, ctx, terrain: T.Terrain, size=384):
        A = terrain.A
        N = terrain.N
        H = terrain.H
        step = max(1, A.shape[0] // size)
        a = A[::step, ::step]
        n = N[::step, ::step]
        h = H[::step, ::step]
        light = np.clip(n[..., 0] * 0.42 + n[..., 1] * 0.72 + n[..., 2] * 0.30, 0.15, 1.4)
        col = np.clip(a * light[..., None] * 1.55, 0.0, 1.0) ** (1 / 2.2)
        water = h < T.WATER_LEVEL
        col[water] = np.array([0.10, 0.24, 0.32], F32)
        rgba = np.empty(col.shape[:2] + (4,), np.uint8)
        rgba[..., :3] = (col * 255).astype(np.uint8)
        rgba[..., 3] = 255
        # 数组是 [x, z]; 纹理行 = v = z, 故转置
        rgba = np.ascontiguousarray(rgba.transpose(1, 0, 2))
        self.res = rgba.shape[0]
        self.tex = ctx.texture((rgba.shape[1], rgba.shape[0]), 4, rgba.tobytes())
        self.tex.filter = (ctx.LINEAR, ctx.LINEAR)
        self.tex.repeat_x = self.tex.repeat_y = False

    @staticmethod
    def uv_of(x, z):
        return (x / T.SIZE + 0.5, z / T.SIZE + 0.5)


class HUD:
    def __init__(self, batch, atlas, minimap):
        self.ui = batch
        self.atlas = atlas
        self.minimap = minimap
        self.w = 1280
        self.h = 720
        self.s = 1.0
        self.time = 0.0

    def begin(self, w, h, dt):
        self.w, self.h = w, h
        self.s = _sc(w, h)
        self.time += dt
        self.ui.begin(w, h)

    # ==================================================================
    # 通用零件
    # ==================================================================
    def _title(self, x, y, s, size, color=GOLD, align="left"):
        self.ui.text(x, y, s, int(size), color, align=align, shadow=SHADOW)

    def vignette_overlay(self, a):
        if a <= 0.001:
            return
        self.ui.quad(0, 0, self.w, self.h, (0, 0, 0, min(1.0, a)))

    # ==================================================================
    # 主菜单
    # ==================================================================
    def main_menu(self, items, sel, has_save, sub="開 / 一个关于「问」的开放世界"):
        s, w, h = self.s, self.w, self.h
        # 左侧装饰背景: 柔和金色光晕 + 暗角
        self.ui.quad_grad_h(0, 0, w * 0.66, h, (0, 0, 0, 0.82), (0, 0, 0, 0.0))
        # 右侧小型传送门提示装饰 (金色光圈)
        cx, cy = w * 0.82, h * 0.34
        self.ui.ring(cx, cy, 78 * s, 84 * s, (0.78, 0.62, 0.32, 0.18), 36)
        self.ui.ring(cx, cy, 60 * s, 64 * s, (0.85, 0.72, 0.42, 0.30), 28)
        self.ui.ring(cx, cy, 30 * s, 36 * s, (0.92, 0.78, 0.50, 0.55), 18)
        self.ui.circle(cx, cy, 4 * s, GOLD, 8)

        # 主标题与副信息
        x = w * 0.11
        y = h * 0.26
        self._title(x, y, "远 行 假 设", 86 * s, GOLD)
        self.ui.line(x + 4, y + 114 * s, x + 360 * s, y + 114 * s, GOLD_DIM, 1.8)
        self.ui.text(x + 6, y + 128 * s, sub, int(17 * s), DIMTXT, shadow=SHADOW)
        self.ui.text(x + 6, y + 156 * s, "所谓的灵魂，其边界究竟在哪里？", int(15 * s),
                     (0.72, 0.70, 0.66, 0.78), shadow=SHADOW)

        # 更新公告面板
        self.ui.text(x + 4, y + 186 * s, f"v{ST.VERSION} · 更新公告", int(13 * s),
                     GOLD_DIM, shadow=SHADOW)
        for k, ln in enumerate(ST.CHANGELOG[1:6]):
            self.ui.text(x + 6, y + 212 * s + k * 21 * s, ln, int(13 * s),
                         (0.66, 0.65, 0.63, 0.78), shadow=SHADOW)

        # 菜单项 (面板化 + 当前项高亮)
        by = h * 0.54
        for i, it in enumerate(items):
            dis = (it == "继续旅程" and not has_save)
            cy = by + i * 52 * s
            if i == sel:
                self.ui.panel(x - 18 * s, cy - 8 * s, 280 * s, 42 * s,
                              (0.18, 0.13, 0.07, 0.62), GOLD, 2 * s)
            col = (0.42, 0.41, 0.39, 0.7) if dis else (GOLD if i == sel else PAPER)
            self.ui.text(x, cy + 4 * s, it, int(24 * s), col, shadow=SHADOW)
        self.ui.text(w - 24 * s, h - 56 * s,
                     "↑↓ 选择    Enter 确认", int(14 * s), DIMTXT, align="right")
        self.ui.text(w - 24 * s, h - 32 * s,
                     "Noctilucere (芋泥P) · v" + ST.VERSION, int(12 * s),
                     (0.55, 0.50, 0.45, 0.7), align="right")

    # ==================================================================
    # 载入
    # ==================================================================
    def loading(self, text, p):
        s, w, h = self.s, self.w, self.h
        self.ui.quad(0, 0, w, h, (0.02, 0.022, 0.028, 1.0))
        self._title(w * 0.5, h * 0.34, "远 行 假 设", 56 * s, GOLD, align="center")
        # 旋转的晶环加载动画
        cx, cy = w * 0.5, h * 0.42 + 26 * s
        t = self.time
        for k, (r_in, r_out, speed, col, alpha) in enumerate((
                (14 * s, 18 * s, 1.6, (0.30, 0.78, 0.86), 0.95),
                (22 * s, 25 * s, -1.1, (0.855, 0.775, 0.585), 0.85),
                (30 * s, 32 * s, 0.8, (0.72, 0.66, 0.58), 0.5))):
            self.ui.ring(cx, cy, r_in, r_out, col + (alpha,), 40,
                         t * speed, math.tau * 0.62)
        self.ui.circle(cx, cy, 5 * s, (0.85, 0.88, 0.92, 0.9), 14)
        self.ui.text(w * 0.5, h * 0.40 + 82 * s, text, int(16 * s), DIMTXT, align="center")
        bw = min(520 * s, w * 0.6)
        bx = (w - bw) * 0.5
        by = h * 0.62
        self.ui.quad(bx, by, bw, 3 * s, (1, 1, 1, 0.12))
        self.ui.quad(bx, by, bw * max(0.02, min(p, 1.0)), 3 * s, GOLD)
        self.ui.text(w * 0.5, h - 60 * s,
                     f"v{ST.VERSION} · 程序化生成中 · 无预制模型 · 无预制贴图", int(13 * s),
                     (0.55, 0.54, 0.52, 0.7), align="center")

    # ==================================================================
    # 章节卡
    # ==================================================================
    def chapter_card(self, no, alpha):
        s, w, h = self.s, self.w, self.h
        c = ST.CHAPTER_CARDS.get(no)
        if not c or alpha <= 0.002:
            return
        a = max(0.0, min(1.0, alpha))
        self.ui.quad(0, 0, w, h, (0.015, 0.017, 0.021, a))
        cy = h * 0.40
        self.ui.text(w * 0.5, cy, c["title"], int(20 * s), (GOLD[0], GOLD[1], GOLD[2], a),
                     align="center")
        self.ui.text(w * 0.5, cy + 40 * s, c["subtitle"], int(44 * s),
                     (PAPER[0], PAPER[1], PAPER[2], a), align="center")
        self.ui.line(w * 0.5 - 140 * s, cy + 108 * s, w * 0.5 + 140 * s, cy + 108 * s,
                     (GOLD[0], GOLD[1], GOLD[2], a * 0.55), 1.2)
        self.ui.text_block(w * 0.5 - 300 * s, cy + 128 * s, c["quote"], int(16 * s),
                           (0.78, 0.76, 0.72, a * 0.9), 600 * s, 1.6)

    # ==================================================================
    # 区域横幅
    # ==================================================================
    def region_banner(self, region, alpha):
        if alpha <= 0.002 or region not in ST.REGIONS:
            return
        s, w = self.s, self.w
        a = max(0.0, min(1.0, alpha))
        d = ST.REGIONS[region]
        y = self.h * 0.16
        self.ui.text(w * 0.5, y, d["name"], int(34 * s),
                     (PAPER[0], PAPER[1], PAPER[2], a), align="center", shadow=(0, 0, 0, a * 0.7))
        self.ui.line(w * 0.5 - 110 * s, y + 50 * s, w * 0.5 + 110 * s, y + 50 * s,
                     (GOLD[0], GOLD[1], GOLD[2], a * 0.6), 1.2)
        self.ui.text(w * 0.5, y + 58 * s, d["subtitle"], int(15 * s),
                     (GOLD[0], GOLD[1], GOLD[2], a * 0.85), align="center")

    # ==================================================================
    # 对话框
    # ==================================================================
    def dialogue(self, dlg, portrait_color=None):
        s, w, h = self.s, self.w, self.h
        bw = min(1060 * s, w - 120 * s)
        bh = 208 * s
        bx = (w - bw) * 0.5
        by = h - bh - 46 * s

        self.ui.quad_grad(0, h - bh - 150 * s, w, bh + 150 * s, (0, 0, 0, 0.0), (0, 0, 0, 0.62))
        self.ui.panel(bx, by, bw, bh, INK, (0.72, 0.68, 0.58, 0.34), 14 * s)

        tx = bx + 34 * s
        ty = by + 26 * s
        if dlg.speaker:
            cw = self.atlas.measure(dlg.speaker, int(19 * s)) + 34 * s
            self.ui.panel(bx + 22 * s, by - 19 * s, cw, 36 * s,
                          (0.10, 0.10, 0.11, 0.94), (0.72, 0.69, 0.60, 0.55), 8 * s)
            if portrait_color:
                self.ui.circle(bx + 22 * s + 15 * s, by - 1 * s, 5 * s,
                               (*portrait_color, 1.0), 14)
                self.ui.text(bx + 22 * s + 28 * s, by - 12 * s, dlg.speaker, int(19 * s), GOLD)
            else:
                self.ui.text(bx + 22 * s + 17 * s, by - 12 * s, dlg.speaker, int(19 * s), GOLD)
            ty = by + 34 * s

        col = PAPER if dlg.speaker else (0.80, 0.79, 0.77, 0.95)
        self.ui.text_block(tx, ty, dlg.visible_text, int(19 * s), col,
                           bw - 68 * s, 1.62, shadow=SHADOW)

        # 页码点
        n = len(dlg.lines)
        if n > 1:
            for i in range(n):
                c = GOLD if i <= dlg.page else (1, 1, 1, 0.18)
                self.ui.circle(bx + 34 * s + i * 11 * s, by + bh - 18 * s, 2.6 * s,
                               c if isinstance(c, tuple) and len(c) == 4 else (*c[:3], 1.0), 10)

        if dlg.choosing:
            self._choices(dlg, bx, by, bw)
        elif not dlg.typing:
            blink = 0.45 + 0.55 * abs(math.sin(self.time * 3.0))
            self.ui.text(bx + bw - 34 * s, by + bh - 30 * s, "▼  空格", int(14 * s),
                         (GOLD[0], GOLD[1], GOLD[2], blink), align="right")

    def _choices(self, dlg, bx, by, bw):
        s = self.s
        ch = dlg.node.get("choices") or []
        chh = 40 * s
        ph = len(ch) * chh + 22 * s
        px = bx + 30 * s
        py = by - ph - 16 * s
        pw = bw - 60 * s
        self.ui.panel(px, py, pw, ph, (0.06, 0.065, 0.075, 0.94),
                      (0.72, 0.69, 0.61, 0.42), 10 * s)
        for i, c in enumerate(ch):
            cy = py + 12 * s + i * chh
            if i == dlg.choice_i:
                self.ui.quad(px + 10 * s, cy, pw - 20 * s, chh - 6 * s, (0.78, 0.72, 0.60, 0.15))
                self.ui.quad(px + 10 * s, cy, 3 * s, chh - 6 * s, GOLD)
                self.ui.text(px + 26 * s, cy + 8 * s, "› " + c["text"], int(18 * s), GOLD)
            else:
                self.ui.text(px + 26 * s, cy + 8 * s, "  " + c["text"], int(18 * s), DIMTXT)

    # ==================================================================
    # 探索 HUD
    # ==================================================================
    def stamina(self, player):
        s, w, h = self.s, self.w, self.h
        if player.stamina >= 99.9 and not player.exhausted:
            return
        cx, cy = w * 0.5, h * 0.62
        r_in, r_out = 30 * s, 35 * s
        p = player.stamina / 100.0
        self.ui.ring(cx, cy, r_in, r_out, (0, 0, 0, 0.42), 48,
                     -math.pi * 0.5, math.tau)
        col = RED if player.exhausted else (0.92, 0.90, 0.84, 0.92)
        self.ui.ring(cx, cy, r_in, r_out, col, 48, -math.pi * 0.5, math.tau * p)

    def health(self, player):
        """左下角生命条 (红色)。"""
        s, w, h = self.s, self.w, self.h
        hp = max(0.0, min(1.0, player.hp / 100.0))
        bw, bh = 196 * s, 15 * s
        bx, by = 26 * s, h - 40 * s
        self.ui.text(bx + 2 * s, by - 22 * s, "生命", int(13 * s),
                     (0.92, 0.86, 0.82, 0.9), shadow=SHADOW)
        self.ui.panel(bx, by, bw, bh, (0.03, 0.035, 0.04, 0.70),
                      (0.62, 0.20, 0.18, 0.55), 6 * s)
        if hp > 0.004:
            col = (0.94, 0.34, 0.28, 0.96) if hp > 0.30 else (1.0, 0.14, 0.10, 0.98)
            self.ui.quad(bx + 3 * s, by + 3 * s, (bw - 6 * s) * hp, bh - 6 * s, col)
        self.ui.text(bx + bw - 6 * s, by + 1 * s, f"{player.hp:3.0f}",
                     int(12 * s), (0.95, 0.90, 0.86, 0.95), align="right")

    def hurt_overlay(self, hurt_t, hp01):
        """受伤红晕 + 低血持续红边。"""
        a = min(1.0, hurt_t / 0.45) * 0.30
        if hp01 < 0.30:
            a = max(a, (0.30 - hp01) * 0.42)
        if a <= 0.001:
            return
        self.ui.quad(0, 0, self.w, self.h, (0.62, 0.04, 0.03, min(0.42, a)))

    def prompt(self, ent, key="E"):
        if ent is None:
            return
        s, w, h = self.s, self.w, self.h
        label = {"npc": "交谈", "inter": "检视", "coll": "拾取"}.get(ent.kind, "交互")
        txt = f"{label}   {ent.name}"
        tw = self.atlas.measure(txt, int(17 * s))
        bwid = tw + 76 * s
        bx = (w - bwid) * 0.5
        by = h * 0.70
        self.ui.panel(bx, by, bwid, 40 * s, (0.05, 0.05, 0.06, 0.80),
                      (0.73, 0.70, 0.61, 0.40), 8 * s)
        self.ui.circle(bx + 24 * s, by + 20 * s, 12 * s, (0.85, 0.78, 0.58, 0.90), 20)
        self.ui.text(bx + 24 * s, by + 10 * s, key, int(15 * s), (0.06, 0.06, 0.07, 1.0),
                     align="center")
        self.ui.text(bx + 44 * s, by + 11 * s, txt, int(17 * s), PAPER, shadow=SHADOW)

    def guide(self, a=1.0):
        """新手引导面板 (首次进入游戏时显示)。"""
        s, w, h = self.s, self.w, self.h
        if a <= 0.002:
            return
        bw, bh = 470 * s, 268 * s
        bx, by = (w - bw) * 0.5, (h - bh) * 0.5
        self.ui.panel(bx, by, bw, bh, (0.03, 0.035, 0.045, 0.90 * a),
                      (0.72, 0.68, 0.58, 0.5 * a), 14 * s)
        self._title(w * 0.5, by + 18 * s, "旅程开始之前", 24 * s, GOLD, align="center")
        rows = [("WASD", "移动"), ("Shift", "冲刺"),
                ("Space", "跳跃 / 滑翔"), ("E", "交谈 / 检视 / 拾取"),
                ("Q", "回响 (解锁后)"), ("M", "世界地图"),
                ("Tab/J", "手记"), ("Esc", "暂停")]
        col_x = (bx + 40 * s, bx + 250 * s)
        for k, (key, desc) in enumerate(rows):
            cx = col_x[k // 4]
            cy = by + 62 * s + (k % 4) * 44 * s
            kw = max(62 * s, self.atlas.measure(key, int(14 * s)) + 18 * s)
            self.ui.quad(cx, cy, kw, 26 * s, (0.10, 0.11, 0.13, 0.9 * a), mode=0)
            self.ui.text(cx + 9 * s, cy + 6 * s, key, int(14 * s), (0.90, 0.90, 0.88, a))
            self.ui.text(cx + kw + 14 * s, cy + 6 * s, desc, int(14 * s),
                         (0.80, 0.79, 0.77, 0.85 * a))
        self.ui.text(w * 0.5, by + bh - 26 * s,
                     "按 H 关闭 · C 角色界面 · = / - 灵敏度", int(13 * s),
                     DIMTXT, align="center")

    def quest_tracker(self, story):
        s = self.s
        q = story.quest
        if q is None:
            return
        x, y = 26 * s, 26 * s
        wdt = 306 * s
        obj = story.objective_text()
        lines = self.atlas.wrap(obj, int(15 * s), wdt - 44 * s) if obj else []
        hgt = 62 * s + max(len(lines), 1) * 22 * s
        self.ui.panel(x, y, wdt, hgt, (0.03, 0.035, 0.042, 0.62),
                      (0.68, 0.64, 0.57, 0.26), 9 * s)
        self.ui.text(x + 18 * s, y + 12 * s, f"第 {q['chapter']} 章", int(12 * s), GOLD_DIM)
        self.ui.text(x + 18 * s, y + 28 * s, q["title"], int(18 * s), PAPER, shadow=SHADOW)
        yy = y + 56 * s
        if obj:
            self.ui.circle(x + 24 * s, yy + 8 * s, 3.2 * s, TEAL, 12)
            for i, ln in enumerate(lines):
                self.ui.text(x + 36 * s, yy + i * 22 * s, ln, int(15 * s), (0.86, 0.85, 0.82, 0.92))
        else:
            self.ui.text(x + 24 * s, yy, "……", int(15 * s), DIMTXT)
        # 完成度
        p = story.progress01()
        self.ui.quad(x + 18 * s, y + hgt - 10 * s, wdt - 36 * s, 2 * s, (1, 1, 1, 0.10))
        self.ui.quad(x + 18 * s, y + hgt - 10 * s, (wdt - 36 * s) * p, 2 * s, GOLD_DIM)

    def compass(self, cam_yaw, player_pos, target_pos, region_name=None):
        s, w = self.s, self.w
        cw = min(560 * s, w * 0.5)
        cx = w * 0.5
        y = 22 * s
        self.ui.quad_grad_h(cx - cw * 0.5, y, cw * 0.5, 26 * s, (0, 0, 0, 0.0), (0, 0, 0, 0.40))
        self.ui.quad_grad_h(cx, y, cw * 0.5, 26 * s, (0, 0, 0, 0.40), (0, 0, 0, 0.0))
        span = math.pi * 0.9

        def place(ang):
            d = (ang - cam_yaw + math.pi) % math.tau - math.pi
            if abs(d) > span * 0.5:
                return None
            return cx - d / span * cw

        for ang, lab in ((0.0, "南"), (math.pi * 0.5, "西"), (math.pi, "北"),
                         (-math.pi * 0.5, "东")):
            px = place(ang)
            if px is None:
                continue
            self.ui.text(px, y + 4 * s, lab, int(14 * s), (0.88, 0.86, 0.82, 0.75),
                         align="center", shadow=SHADOW)
        for k in range(24):
            ang = k / 24 * math.tau - math.pi
            px = place(ang)
            if px is None:
                continue
            self.ui.quad(px - 0.5 * s, y + 21 * s, 1 * s, 5 * s, (1, 1, 1, 0.28))

        if target_pos is not None:
            dx = float(target_pos[0]) - float(player_pos[0])
            dz = float(target_pos[2]) - float(player_pos[2])
            ang = math.atan2(dx, dz)
            px = place(ang)
            dist = math.hypot(dx, dz)
            if px is None:
                edge = cx + (cw * 0.5 - 8 * s) * (1 if ((ang - cam_yaw + math.pi) % math.tau - math.pi) < 0 else -1)
                self.ui.tri((edge, y + 6 * s), (edge + 7 * s, y + 14 * s),
                            (edge, y + 22 * s), (TEAL[0], TEAL[1], TEAL[2], 0.55))
            else:
                self.ui.tri((px, y + 2 * s), (px - 6 * s, y + 12 * s), (px + 6 * s, y + 12 * s), TEAL)
                self.ui.text(px, y + 26 * s, f"{dist:.0f}m", int(12 * s), TEAL, align="center",
                             shadow=SHADOW)
        if region_name:
            self.ui.text(cx, y + 40 * s, region_name, int(13 * s), (0.80, 0.78, 0.74, 0.6),
                         align="center", shadow=SHADOW)

    def map_widget(self, player, entities, story, cam_yaw):
        s, w = self.s, self.w
        size = 176 * s
        x = w - size - 26 * s
        y = 26 * s
        half = 118.0                     # 视野半径(米)
        u, v = Minimap.uv_of(player.pos[0], player.pos[2])
        du = half / T.SIZE
        self.ui.panel(x - 6 * s, y - 6 * s, size + 12 * s, size + 12 * s,
                      (0.03, 0.035, 0.042, 0.72), (0.68, 0.64, 0.57, 0.30), 10 * s)
        self.ui.image(x, y, size, size, self.minimap.tex,
                      (1, 1, 1, 0.94), (u - du, v - du, u + du, v + du))

        def to_px(wx, wz):
            return (x + size * 0.5 + (wx - player.pos[0]) / half * size * 0.5,
                    y + size * 0.5 + (wz - player.pos[2]) / half * size * 0.5)

        # 目标
        kind, target = story.objective_target()
        for e in entities.all_entities():
            if e.taken:
                continue
            px, py = to_px(e.pos[0], e.pos[2])
            if not (x < px < x + size and y < py < y + size):
                continue
            if e.kind == "coll":
                self.ui.circle(px, py, 2.6 * s, (0.55, 0.90, 0.95, 0.95), 10)
            elif e.kind == "npc":
                self.ui.circle(px, py, 2.4 * s, (0.95, 0.86, 0.55, 0.85), 10)
            else:
                self.ui.quad(px - 2 * s, py - 2 * s, 4 * s, 4 * s, (0.85, 0.72, 0.90, 0.80))
            if target == e.id:
                r = 6 * s + 2.4 * s * math.sin(self.time * 3.4)
                self.ui.ring(px, py, r, r + 1.4 * s, TEAL, 18)

        # 玩家箭头
        px, py = x + size * 0.5, y + size * 0.5
        a = player.yaw
        fx, fy = math.sin(a), math.cos(a)
        rx, ry = fy, -fx
        L, W = 8 * s, 5 * s
        self.ui.tri((px + fx * L, py + fy * L),
                    (px - fx * 4 * s + rx * W, py - fy * 4 * s + ry * W),
                    (px - fx * 4 * s - rx * W, py - fy * 4 * s - ry * W), PAPER)
        self.ui.text(x + size * 0.5, y + size + 8 * s,
                     f"X {player.pos[0]:.0f}  Z {player.pos[2]:.0f}", int(11 * s),
                     (0.72, 0.71, 0.68, 0.65), align="center")

    def toast(self, text, alpha):
        if not text or alpha <= 0.01:
            return
        s, w, h = self.s, self.w, self.h
        tw = self.atlas.measure(text, int(17 * s))
        x = (w - tw - 52 * s) * 0.5
        y = h * 0.78
        a = min(1.0, alpha)
        self.ui.panel(x, y, tw + 52 * s, 38 * s, (0.05, 0.05, 0.06, 0.72 * a),
                      (0.80, 0.74, 0.58, 0.34 * a), 8 * s)
        self.ui.circle(x + 24 * s, y + 19 * s, 4 * s, (TEAL[0], TEAL[1], TEAL[2], a), 12)
        self.ui.text(x + 38 * s, y + 10 * s, text, int(17 * s), (PAPER[0], PAPER[1], PAPER[2], a))

    def echo_hint(self, player):
        if not player.echo_unlocked:
            return
        s, w, h = self.s, self.w, self.h
        x, y = 26 * s, self.h - 66 * s
        ready = player.echo_cd <= 0 and player.stamina >= 22
        col = TEAL if ready else (0.45, 0.48, 0.50, 0.6)
        self.ui.circle(x + 18 * s, y + 18 * s, 17 * s, (0.05, 0.06, 0.07, 0.70), 24)
        self.ui.ring(x + 18 * s, y + 18 * s, 15 * s, 17 * s, col, 28)
        self.ui.text(x + 18 * s, y + 9 * s, "Q", int(16 * s), col, align="center")
        self.ui.text(x + 44 * s, y + 11 * s, "回响", int(15 * s),
                     (0.86, 0.85, 0.82, 0.85 if ready else 0.45))

    # ==================================================================
    # 全屏页面
    # ==================================================================
    def journal(self, story, sel, tab, achievements=None):
        s, w, h = self.s, self.w, self.h
        self.ui.quad(0, 0, w, h, (0.02, 0.022, 0.028, 0.92))
        m = 60 * s
        self.ui.panel(m, m, w - m * 2, h - m * 2, (0.045, 0.048, 0.056, 0.92),
                      (0.72, 0.66, 0.52, 0.32), 16 * s)
        self._title(m + 34 * s, m + 24 * s, "手 记", 30 * s)
        tabs = ["心跳残片", "所遇之人", "此地之名", "旅途成就"]
        for i, tname in enumerate(tabs):
            tx = m + 220 * s + i * 122 * s
            col = GOLD if i == tab else DIMTXT
            self.ui.text(tx, m + 34 * s, tname, int(17 * s), col)
            if i == tab:
                self.ui.quad(tx, m + 56 * s, self.atlas.measure(tname, int(17 * s)), 2 * s, GOLD)
        self.ui.text(w - m - 30 * s, m + 34 * s, "Tab 切换页    Esc 关闭", int(13 * s),
                     DIMTXT, align="right")

        lx = m + 34 * s
        ly = m + 86 * s
        lw = 300 * s
        rx = lx + lw + 28 * s
        rw = w - m * 2 - lw - 96 * s

        if tab == 0:
            ids = list(ST.COLLECTIBLES.keys())
            got = set(story.inventory)
            self.ui.text(lx, ly - 24 * s, f"已收集 {len(got)} / {len(ids)}", int(13 * s), GOLD_DIM)
            for i, cid in enumerate(ids):
                cy = ly + i * 30 * s
                d = ST.COLLECTIBLES[cid]
                has = cid in got
                if i == sel:
                    self.ui.quad(lx - 10 * s, cy - 4 * s, lw, 28 * s, (0.85, 0.76, 0.56, 0.12))
                    self.ui.quad(lx - 10 * s, cy - 4 * s, 2.5 * s, 28 * s, GOLD)
                self.ui.text(lx, cy, d["name"] if has else "？？？", int(16 * s),
                             (GOLD if i == sel else PAPER) if has else (0.42, 0.42, 0.42, 0.8))
            cid = ids[max(0, min(sel, len(ids) - 1))]
            d = ST.COLLECTIBLES[cid]
            if cid in got:
                self._title(rx, ly, d["name"], 24 * s, PAPER)
                self.ui.text(rx, ly + 34 * s, ST.REGIONS[d["region"]]["name"], int(13 * s), GOLD_DIM)
                self.ui.text_block(rx, ly + 62 * s, d["text"], int(16 * s),
                                   (0.84, 0.83, 0.80, 0.95), rw, 1.75)
            else:
                self.ui.text(rx, ly, "尚未拾得。", int(17 * s), DIMTXT)
                self.ui.text_block(rx, ly + 34 * s,
                                   "「他们从不记录，也从不证明。但每一次心跳都留下了形状。」",
                                   int(15 * s), (0.55, 0.54, 0.52, 0.8), rw, 1.7)
        elif tab == 1:
            ids = [k for k in ST.NPCS if f"met_{k}" in story.flags or k in story.flags]
            if not ids:
                ids = []
            allids = list(ST.NPCS.keys())
            for i, nid in enumerate(allids):
                cy = ly + i * 26 * s
                d = ST.NPCS[nid]
                met = f"met_{nid}" in story.flags
                if i == sel:
                    self.ui.quad(lx - 10 * s, cy - 4 * s, lw, 24 * s, (0.85, 0.76, 0.56, 0.12))
                    self.ui.quad(lx - 10 * s, cy - 4 * s, 2.5 * s, 24 * s, GOLD)
                self.ui.text(lx, cy, d["name"] if met else "？？？", int(15 * s),
                             (GOLD if i == sel else PAPER) if met else (0.42, 0.42, 0.42, 0.8))
            nid = allids[max(0, min(sel, len(allids) - 1))]
            d = ST.NPCS[nid]
            if f"met_{nid}" in story.flags:
                self.ui.circle(rx + 12 * s, ly + 12 * s, 11 * s, (*d["color"], 1.0), 20)
                self._title(rx + 34 * s, ly, d["name"], 24 * s, PAPER)
                self.ui.text(rx + 34 * s, ly + 34 * s,
                             f"{d['race']} · {ST.REGIONS[d['region']]['name']}",
                             int(13 * s), GOLD_DIM)
                self.ui.text_block(rx, ly + 66 * s, d["desc"], int(16 * s),
                                   (0.84, 0.83, 0.80, 0.95), rw, 1.75)
            else:
                self.ui.text(rx, ly, "还没有遇见。", int(17 * s), DIMTXT)
        elif tab == 2:
            allids = list(ST.REGIONS.keys())
            for i, rid in enumerate(allids):
                cy = ly + i * 30 * s
                d = ST.REGIONS[rid]
                seen = rid in story.visited_regions
                if i == sel:
                    self.ui.quad(lx - 10 * s, cy - 4 * s, lw, 28 * s, (0.85, 0.76, 0.56, 0.12))
                    self.ui.quad(lx - 10 * s, cy - 4 * s, 2.5 * s, 28 * s, GOLD)
                self.ui.text(lx, cy, d["name"] if seen else "未至之地", int(16 * s),
                             (GOLD if i == sel else PAPER) if seen else (0.42, 0.42, 0.42, 0.8))
            rid = allids[max(0, min(sel, len(allids) - 1))]
            d = ST.REGIONS[rid]
            if rid in story.visited_regions:
                self._title(rx, ly, d["name"], 24 * s, PAPER)
                self.ui.text(rx, ly + 34 * s, d["subtitle"], int(14 * s), GOLD_DIM)
                self.ui.text_block(rx, ly + 62 * s, d["desc"], int(16 * s),
                                   (0.84, 0.83, 0.80, 0.95), rw, 1.75)
            else:
                self.ui.text(rx, ly, "尚未抵达。", int(17 * s), DIMTXT)
        else:  # tab == 3: 旅途成就
            aids = [a for a, _n, _d in ST.ACHIEVEMENTS]
            got = achievements or set()
            self.ui.text(lx, ly - 24 * s,
                         f"已达成 {len([a for a in aids if a in got])} / {len(aids)}",
                         int(13 * s), GOLD_DIM)
            for i, aid in enumerate(aids):
                cy = ly + i * 28 * s
                _a, name, _d = ST.ACHIEVEMENTS[i]
                unlocked = aid in got
                if i == sel:
                    self.ui.quad(lx - 10 * s, cy - 4 * s, lw, 26 * s, (0.85, 0.76, 0.56, 0.12))
                    self.ui.quad(lx - 10 * s, cy - 4 * s, 2.5 * s, 26 * s, GOLD)
                self.ui.text(lx, cy, name if unlocked else "？？？", int(16 * s),
                             (GOLD if i == sel else PAPER) if unlocked
                             else (0.42, 0.42, 0.42, 0.8))
            aid = aids[max(0, min(sel, len(aids) - 1))]
            _a, name, desc = ST.ACHIEVEMENTS[aids.index(aid)]
            if aid in got:
                self._title(rx, ly, name, 24 * s, PAPER)
                self.ui.circle(rx + lw - 22 * s, ly + 12 * s, 9 * s, GOLD, 16)
                self.ui.text(rx + lw - 26 * s, ly + 6 * s, "✓", int(14 * s),
                             (0.05, 0.05, 0.06, 1.0), align="center")
                self.ui.text_block(rx, ly + 40 * s, desc, int(16 * s),
                                   (0.84, 0.83, 0.80, 0.95), rw, 1.75)
            else:
                self.ui.text(rx, ly, "尚未达成。", int(17 * s), DIMTXT)
                self.ui.text_block(rx, ly + 34 * s, desc, int(15 * s),
                                   (0.55, 0.54, 0.52, 0.8), rw, 1.7)

    def character(self, player, story, region=""):
        """角色界面 (C 键): 玩家角色卡 + 属性。"""
        s, w, h = self.s, self.w, self.h
        self.ui.quad(0, 0, w, h, (0.02, 0.022, 0.028, 0.94))
        bw, bh = 560 * s, 430 * s
        bx, by = (w - bw) * 0.5, (h - bh) * 0.5
        self.ui.panel(bx, by, bw, bh, (0.04, 0.045, 0.055, 0.92),
                      (0.72, 0.68, 0.58, 0.5), 16 * s)
        self._title(w * 0.5, by + 20 * s, "角 色", 26 * s, GOLD, align="center")

        # 左侧: 头像框 (程序化玩家模型符号)
        ax, ay, ar = bx + 96 * s, by + 96 * s, 54 * s
        self.ui.circle(ax, ay, ar + 6 * s, (0.10, 0.11, 0.13, 0.9), 36)
        self.ui.ring(ax, ay, ar + 4 * s, ar + 8 * s,
                     (0.855, 0.775, 0.585, 0.85), 40, -math.pi * 0.5, math.tau * 0.62)
        # 猫耳剪影 (两只小三角)
        for sx in (-1, 1):
            self.ui.tri((ax + sx * 16 * s, ay - ar * 0.55),
                        (ax + sx * 30 * s, ay - ar * 1.05),
                        (ax + sx * 38 * s, ay - ar * 0.35),
                        (0.60, 0.55, 0.48, 0.95))
        self.ui.text(ax, ay - 12 * s, "灰", int(34 * s), (0.90, 0.885, 0.855, 1.0),
                     align="center")
        self.ui.text(ax, ay + 22 * s, "猫兽人 · 拓荒者", int(13 * s),
                     (0.74, 0.73, 0.70, 0.85), align="center")
        self.ui.text(ax, ay + 44 * s, "Lv.1 记录者", int(13 * s),
                     (0.855, 0.775, 0.585, 0.9), align="center")

        # 右侧: 属性
        rx = bx + 220 * s
        ry = by + 70 * s
        rows = [
            ("生命", player.hp, 100.0, (0.94, 0.34, 0.28)),
            ("体力", player.stamina, 100.0, (0.92, 0.90, 0.84)),
        ]
        for k, (lab, cur, mx, col) in enumerate(rows):
            y0 = ry + k * 58 * s
            self.ui.text(rx, y0, lab, int(15 * s), PAPER, shadow=SHADOW)
            self.ui.quad(rx + 64 * s, y0 + 4 * s, 200 * s, 10 * s, (1, 1, 1, 0.12))
            self.ui.quad(rx + 64 * s, y0 + 4 * s, 200 * s * (cur / mx), 10 * s, col)
            self.ui.text(rx + 272 * s, y0, f"{cur:.0f} / {mx:.0f}", int(13 * s),
                         DIMTXT, align="right")

        # 能力
        yy = ry + 130 * s
        echo = "已解锁 · 按 Q 释放回响" if player.echo_unlocked else "未解锁 · 第二章后获得"
        self.ui.text(rx, yy, f"回响能力：{echo}", int(14 * s),
                     (0.40, 0.82, 0.76, 0.95) if player.echo_unlocked else DIMTXT,
                     shadow=SHADOW)
        self.ui.text(rx, yy + 30 * s, f"行走距离：{player.distance_walked / 1000.0:.2f} km",
                     int(14 * s), DIMTXT, shadow=SHADOW)
        self.ui.text(rx, yy + 60 * s,
                     f"章节进度：第 {story.chapter_no()} 章  ({story.progress01() * 100:.0f}%)",
                     int(14 * s), DIMTXT, shadow=SHADOW)
        self.ui.text(rx, yy + 90 * s, f"当前区域：{region or '无名荒原'}", int(14 * s),
                     DIMTXT, shadow=SHADOW)

        # 描述
        dd = ST.NPCS["hui"]["desc"]
        lines = self.atlas.wrap(dd, int(14 * s), bw - 70 * s)
        for k, ln in enumerate(lines[:5]):
            self.ui.text(bx + 35 * s, by + bh - 110 * s + k * 20 * s, ln, int(14 * s),
                         (0.72, 0.71, 0.69, 0.8), shadow=SHADOW)
        self.ui.text(w * 0.5, h - 40 * s, "C / Esc 关闭", int(13 * s), DIMTXT,
                     align="center")

    def world_map(self, player, entities, story):
        s, w, h = self.s, self.w, self.h
        self.ui.quad(0, 0, w, h, (0.02, 0.022, 0.028, 0.94))
        size = min(w - 180 * s, h - 150 * s)
        x = (w - size) * 0.5
        y = (h - size) * 0.5 + 12 * s
        self.ui.panel(x - 8 * s, y - 8 * s, size + 16 * s, size + 16 * s,
                      (0.04, 0.045, 0.05, 0.9), (0.72, 0.66, 0.52, 0.32), 12 * s)
        self.ui.image(x, y, size, size, self.minimap.tex, (0.95, 0.95, 0.95, 1.0))
        self._title(w * 0.5, y - 52 * s, "世 界", 26 * s, GOLD, align="center")
        self.ui.text(w * 0.5, h - 44 * s, "M 关闭", int(13 * s), DIMTXT, align="center")

        def to_px(wx, wz):
            u, v = Minimap.uv_of(wx, wz)
            return x + u * size, y + v * size

        for rid, (cx, cz) in T.REGION_POS.items():
            px, py = to_px(cx, cz)
            seen = rid in story.visited_regions
            col = (*REGION_MARK[rid], 0.95 if seen else 0.30)
            self.ui.ring(px, py, 8 * s, 9.6 * s, col, 26)
            self.ui.text(px, py + 14 * s,
                         ST.REGIONS[rid]["name"] if seen else "？？？",
                         int(13 * s), (0.92, 0.90, 0.86, 0.9 if seen else 0.35),
                         align="center", shadow=SHADOW)
        kind, target = story.objective_target()
        if target and target in T.REGION_POS:
            px, py = to_px(*T.REGION_POS[target])
            r = 14 * s + 3 * s * math.sin(self.time * 3.0)
            self.ui.ring(px, py, r, r + 1.6 * s, TEAL, 28)
        ent = entities.get(target) if target else None
        if ent is not None:
            px, py = to_px(ent.pos[0], ent.pos[2])
            r = 9 * s + 2.5 * s * math.sin(self.time * 3.4)
            self.ui.ring(px, py, r, r + 1.5 * s, TEAL, 22)

        # 未收集的心跳残片标记 (金黄色小点, 已拾取的不显示)
        for cid, e in entities.colls.items():
            if e.taken:
                continue
            if cid in story.inventory:
                continue
            px, py = to_px(e.pos[0], e.pos[2])
            self.ui.circle(px, py, 2.4 * s, (0.95, 0.80, 0.40, 0.9), 10)

        px, py = to_px(player.pos[0], player.pos[2])
        a = player.yaw
        fx, fy = math.sin(a), math.cos(a)
        rx, ry = fy, -fx
        L, W = 11 * s, 6.5 * s
        self.ui.tri((px + fx * L, py + fy * L),
                    (px - fx * 5 * s + rx * W, py - fy * 5 * s + ry * W),
                    (px - fx * 5 * s - rx * W, py - fy * 5 * s - ry * W), PAPER)

    def pause(self, items, sel, region_name, play_time, progress):
        s, w, h = self.s, self.w, self.h
        self.ui.quad(0, 0, w, h, (0.015, 0.017, 0.022, 0.80))
        pw, ph = 340 * s, 420 * s
        x = (w - pw) * 0.5
        y = (h - ph) * 0.5
        self.ui.panel(x, y, pw, ph, (0.045, 0.05, 0.058, 0.94),
                      (0.75, 0.68, 0.54, 0.35), 14 * s)
        self._title(x + pw * 0.5, y + 30 * s, "暂 停", 26 * s, GOLD, align="center")
        self.ui.line(x + 40 * s, y + 76 * s, x + pw - 40 * s, y + 76 * s, GOLD_DIM, 1.0)
        for i, it in enumerate(items):
            cy = y + 104 * s + i * 44 * s
            if i == sel:
                self.ui.quad(x + 30 * s, cy - 6 * s, pw - 60 * s, 34 * s, (0.85, 0.76, 0.56, 0.13))
                self.ui.quad(x + 30 * s, cy - 6 * s, 3 * s, 34 * s, GOLD)
            self.ui.text(x + pw * 0.5, cy, it, int(19 * s), GOLD if i == sel else PAPER,
                         align="center")
        info = f"{region_name}   ·   {int(play_time // 60)} 分   ·   {progress * 100:.0f}%"
        self.ui.text(x + pw * 0.5, y + ph - 44 * s, info, int(13 * s), DIMTXT, align="center")

    def ending(self, t, lines, final, alpha=1.0):
        s, w, h = self.s, self.w, self.h
        self.ui.quad(0, 0, w, h, (0.01, 0.011, 0.014, 1.0))
        top = h * 0.92 - t * 34.0 * s
        size = int(19 * s)
        lh = self.atlas.line_height(size) * 1.9
        y = top
        for ln in lines:
            if -60 < y < h + 40 and ln:
                a = 1.0
                if y < h * 0.16:
                    a = max(0.0, (y - h * 0.04) / (h * 0.12))
                self.ui.text(w * 0.5, y, ln, size, (0.88, 0.87, 0.84, a * alpha),
                             align="center")
            y += lh
        if y < h * 0.55:
            fa = min(1.0, (h * 0.55 - y) / (h * 0.2)) * alpha
            self.ui.text(w * 0.5, h * 0.44, final, int(64 * s),
                         (GOLD[0], GOLD[1], GOLD[2], fa), align="center")
            self.ui.text(w * 0.5, h * 0.60, "—— 远 行 假 设 ——", int(16 * s),
                         (0.70, 0.68, 0.64, fa * 0.8), align="center")
            self.ui.text(w * 0.5, h - 60 * s, "Esc 返回主菜单", int(13 * s),
                         (0.6, 0.6, 0.6, fa * 0.7), align="center")

    def debug(self, lines):
        s = self.s
        for i, ln in enumerate(lines):
            self.ui.text(12 * s, self.h - 18 * s - (len(lines) - i) * 15 * s, ln,
                         int(12 * s), (0.6, 0.9, 0.7, 0.75))

    def flush(self):
        self.ui.flush()
