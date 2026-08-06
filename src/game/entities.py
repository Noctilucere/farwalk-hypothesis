"""
entities.py -- 世界中的可交互实体

三类:
    NPC          -- 剧情角色, 7 种程序化形态, 会呼吸/浮动/转向玩家
    Interactable -- 手稿 / 黑石 / 石柱 / 镜子 / 纹路 ...
    Collectible  -- 12 枚"心跳残片"

布点规则: 每个实体按其所属区域, 用确定性哈希在区域影响圈内取角度与半径,
再做坡度重试, 保证站得住、走得到。因此每次启动世界完全一致。
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

from ..data import story as ST
from ..engine import gltf
from ..engine import mesh as MSH
from ..engine import skin as SKIN
from ..engine.renderer import InstancedMesh, SkinnedMesh, pack_instances
from ..world import terrain as T

F32 = np.float32


def _model_dir():
    """外部 AI 生成的模型目录 (源码 / PyInstaller _MEIPASS 均可)。"""
    base = getattr(sys, "_MEIPASS",
                   os.path.dirname(os.path.dirname(os.path.dirname(
                       os.path.abspath(__file__)))))
    return os.path.join(base, "assets", "models")


def _glb_or_none(eid, height):
    p = os.path.join(_model_dir(), f"{eid}.glb")
    if not os.path.isfile(p):
        return None
    res = gltf.load_or_none(p, target_height=height)
    if res is None:
        return None
    verts, idx = res
    return SKIN.bind(verts, height), idx

# 关键实体的手工布点 (区域中心的相对偏移), 保证开局动线合理
FIXED = {
    "manuscript":   ("wilds", 26.0, 0.9),
    "harmonic_stone": ("wilds", 58.0, 2.4),
    "hui":          ("wilds", 96.0, 4.1),
    "chronicler":   ("wilds", 18.0, 5.4),
    "blackstone":   ("blackstone", 0.0, 0.0),
    "mirror":       ("mirror", 0.0, 0.0),
    "converger":    ("mirror", 26.0, 3.6),
    "glass":        ("mirror", 52.0, 1.2),
}


def _hash01(s, salt=0):
    h = 2166136261
    for ch in f"{s}#{salt}":
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h / 0xFFFFFFFF


class Entity:
    __slots__ = ("id", "kind", "data", "pos", "yaw", "radius", "form", "taken",
                 "phase", "highlight", "name", "region")

    def __init__(self, eid, kind, data, pos, yaw, radius, form=None):
        self.id = eid
        self.kind = kind
        self.data = data
        self.pos = np.asarray(pos, F32)
        self.yaw = float(yaw)
        self.radius = float(radius)
        self.form = form
        self.taken = False
        self.phase = _hash01(eid, 7) * math.tau
        self.highlight = 0.0
        self.name = data.get("name", eid)
        self.region = data.get("region", "wilds")


class EntityWorld:
    def __init__(self, ctx, renderer, terrain: T.Terrain, progress=None):
        self.ctx = ctx
        self.r = renderer
        self.terrain = terrain
        self.time = 0.0

        if progress:
            progress("正在唤醒此地的居民", 0.80)

        self.npcs: dict[str, Entity] = {}
        self.inters: dict[str, Entity] = {}
        self.colls: dict[str, Entity] = {}
        self._place()

        if progress:
            progress("正在铸造形体", 0.86)
        self._build_meshes()

    # ------------------------------------------------------------------
    # 布点
    # ------------------------------------------------------------------
    def _spot(self, eid, region, want_r=None, want_a=None, max_slope=0.40):
        cx, cz = T.REGION_POS[region]
        rad = T.REGION_RADIUS[region]
        base_a = _hash01(eid, 1) * math.tau if want_a is None else want_a
        base_r = (0.22 + _hash01(eid, 2) * 0.58) * rad if want_r is None else want_r
        best = None
        for k in range(24):
            a = base_a + k * 0.41
            rr = base_r * (1.0 + (k % 5) * 0.055)
            rr = min(rr, rad * 0.94)
            x = cx + math.cos(a) * rr
            z = cz + math.sin(a) * rr
            if abs(x) > T.HALF - 40 or abs(z) > T.HALF - 40:
                continue
            y = self.terrain.height_at(x, z)
            if y < T.WATER_LEVEL + 1.2:
                continue
            d = 1.8
            hx = self.terrain.height_at(x + d, z) - self.terrain.height_at(x - d, z)
            hz = self.terrain.height_at(x, z + d) - self.terrain.height_at(x, z - d)
            slope = math.hypot(hx, hz) / (2 * d)
            if best is None or slope < best[3]:
                best = (x, y, z, slope)
            if slope < max_slope:
                return np.array([x, y, z], F32)
        if best is None:
            y = self.terrain.height_at(cx, cz)
            return np.array([cx, y, cz], F32)
        return np.array([best[0], best[1], best[2]], F32)

    def _place(self):
        for eid, d in ST.NPCS.items():
            reg = d["region"]
            if eid in FIXED:
                _, rr, aa = FIXED[eid]
                p = self._spot(eid, reg, rr, aa)
            else:
                p = self._spot(eid, reg)
            cx, cz = T.REGION_POS[reg]
            yaw = math.atan2(cx - p[0], cz - p[2])
            self.npcs[eid] = Entity(eid, "npc", d, p, yaw, 3.4, d.get("form", "biped"))

        for eid, d in ST.INTERACTABLES.items():
            reg = d["region"]
            if eid in FIXED:
                _, rr, aa = FIXED[eid]
                p = self._spot(eid, reg, rr, aa)
            else:
                p = self._spot(eid, reg)
            self.inters[eid] = Entity(eid, "inter", d, p,
                                      _hash01(eid, 3) * math.tau, 3.2, d.get("kind"))

        for eid, d in ST.COLLECTIBLES.items():
            reg = d["region"]
            p = self._spot(eid, reg, max_slope=0.55)
            p = p.copy()
            p[1] += 1.25
            self.colls[eid] = Entity(eid, "coll", d, p, 0.0, 2.6)

    # ------------------------------------------------------------------
    # 网格
    # ------------------------------------------------------------------
    def _build_meshes(self):
        self.npc_groups = {}
        forms = sorted({e.form for e in self.npcs.values()})
        for f in forms:
            members = [e for e in self.npcs.values() if e.form == f]
            h = members[0].data.get("height", 1.7)
            v, i = MSH.character(f, h, seed=abs(hash(f)) % 9999)
            im = InstancedMesh(self.ctx, self.r, v, i, max_instances=8)
            self.npc_groups[f] = (im, members, h)

        # 外部 AI 生成模型覆盖: assets/models/<eid>.glb, 加载成功则该角色
        # 从程序化分组中独立出来, 使用完整建模 + 骨骼蒙皮动画
        self.glb_npcs = []
        for eid, e in self.npcs.items():
            res = _glb_or_none(eid, e.data.get("height", 1.7))
            if res is None:
                continue  # 加载失败 → 保留在程序化组作为兜底
            v, i = res
            im = SkinnedMesh(self.ctx, self.r, v, i, max_instances=2)
            self.glb_npcs.append((im, e))
            for (_im, members, _h) in self.npc_groups.values():
                if e in members:
                    members.remove(e)

        self.inter_groups = {}
        kinds = sorted({e.form for e in self.inters.values()})
        for k in kinds:
            members = [e for e in self.inters.values() if e.form == k]
            v, i = MSH.interactable_mesh(k, seed=abs(hash(k)) % 999)
            im = InstancedMesh(self.ctx, self.r, v, i, max_instances=8)
            self.inter_groups[k] = (im, members)

        v, i = MSH.collectible_mesh()
        self.coll_mesh = InstancedMesh(self.ctx, self.r, v, i, max_instances=16)

        # 玩家 (猫兽人拓荒者): 外部 player.glb 优先, 否则程序化 biped
        pv, pi = MSH.character("biped", 1.74, seed=4242)
        pres = _glb_or_none("player", 1.74)
        self.player_skinned = False
        if pres is not None:
            pv, pi = pres
            self.player_skinned = True
        if self.player_skinned:
            self.player_mesh = SkinnedMesh(self.ctx, self.r, pv, pi, max_instances=2)
        else:
            self.player_mesh = InstancedMesh(self.ctx, self.r, pv, pi, max_instances=2)

    # ------------------------------------------------------------------
    def all_entities(self):
        for d in (self.npcs, self.inters, self.colls):
            for e in d.values():
                yield e

    def get(self, eid):
        return self.npcs.get(eid) or self.inters.get(eid) or self.colls.get(eid)

    def nearest(self, pos, max_dist=4.2, skip_taken=True):
        """返回最近的可交互实体 (Entity, 距离)。"""
        best, bd = None, max_dist
        px, py, pz = float(pos[0]), float(pos[1]), float(pos[2])
        for e in self.all_entities():
            if skip_taken and e.taken:
                continue
            dx = e.pos[0] - px
            dz = e.pos[2] - pz
            dy = e.pos[1] - py
            d = math.sqrt(dx * dx + dz * dz + (dy * 0.5) ** 2)
            if d < min(bd, e.radius):
                best, bd = e, d
        return best, bd

    # ------------------------------------------------------------------
    def update(self, dt, player_pos, echo_radius=-1.0, echo_origin=None):
        self.time += dt
        t = self.time
        px, pz = float(player_pos[0]), float(player_pos[2])

        # 回响照亮
        if echo_radius > 0 and echo_origin is not None:
            ex, ez = float(echo_origin[0]), float(echo_origin[2])
            for e in self.all_entities():
                d = math.hypot(e.pos[0] - ex, e.pos[2] - ez)
                if abs(d - echo_radius) < 14.0:
                    e.highlight = 1.0
        for e in self.all_entities():
            if e.highlight > 0:
                e.highlight = max(0.0, e.highlight - dt * 0.42)

        # NPC
        for f, (im, members, base_h) in self.npc_groups.items():
            pos, rot, scl, tint, glow = [], [], [], [], []
            for e in members:
                d = math.hypot(e.pos[0] - px, e.pos[2] - pz)
                if d > 190.0:
                    continue
                breathe = math.sin(t * 1.35 + e.phase) * 0.018
                hover = 0.0
                if f in ("blob", "shadow", "crystal", "puzzler"):
                    hover = math.sin(t * 0.85 + e.phase) * 0.16 + 0.12
                yaw = e.yaw
                if d < 16.0:
                    yaw = math.atan2(px - e.pos[0], pz - e.pos[2])
                hs = e.data.get("height", 1.7) / base_h
                pos.append((e.pos[0], e.pos[1] + hover, e.pos[2]))
                rot.append(yaw)
                scl.append((hs * (1.0 - breathe * 0.5), hs * (1.0 + breathe), hs * (1.0 - breathe * 0.5)))
                c = e.data.get("color", (0.6, 0.6, 0.6))
                tint.append(c)
                glow.append(e.data.get("glow", 0.0) * (0.85 + 0.35 * math.sin(t * 1.9 + e.phase))
                            + e.highlight * 0.5)
            im.upload(pack_instances(pos, rot, scl, tint, glow) if pos else np.zeros((0, 16), F32))

        # 外部建模 NPC (glb): 完整模型 + 骨骼蒙皮动画
        for im, e in self.glb_npcs:
            d = math.hypot(e.pos[0] - px, e.pos[2] - pz)
            if d > 190.0:
                im.upload(np.zeros((0, 16), F32))
                continue
            breathe = math.sin(t * 1.35 + e.phase) * 0.02
            hover = 0.0
            if e.form in ("blob", "shadow", "crystal", "puzzler"):
                hover = math.sin(t * 0.85 + e.phase) * 0.18 + 0.14
            yaw = e.yaw
            if d < 16.0:
                yaw = math.atan2(px - e.pos[0], pz - e.pos[2])
            hgt = e.data.get("height", 1.7)
            im.set_bones(SKIN.pose_matrices("idle", t, e.phase, hgt))
            im.upload(pack_instances(
                [(e.pos[0], e.pos[1] + hover, e.pos[2])], [yaw],
                [(1.0 - breathe * 0.4, 1.0 + breathe, 1.0 - breathe * 0.4)],
                [e.data.get("color", (0.6, 0.6, 0.6))],
                [e.data.get("glow", 0.0) * (0.8 + 0.4 * math.sin(t * 1.9 + e.phase))
                 + e.highlight * 0.6]))

        # 交互物
        for k, (im, members) in self.inter_groups.items():
            pos, rot, scl, tint, glow = [], [], [], [], []
            for e in members:
                d = math.hypot(e.pos[0] - px, e.pos[2] - pz)
                if d > 240.0:
                    continue
                pos.append(tuple(e.pos))
                rot.append(e.yaw)
                scl.append(1.0)
                tint.append(e.data.get("color", (0.5, 0.5, 0.5)))
                g = e.data.get("glow", 0.0)
                glow.append(g * (0.72 + 0.30 * math.sin(t * 1.5 + e.phase)) + e.highlight * 0.7)
            im.upload(pack_instances(pos, rot, scl, tint, glow) if pos else np.zeros((0, 16), F32))

        # 收集品
        pos, rot, scl, tint, glow = [], [], [], [], []
        for e in self.colls.values():
            if e.taken:
                continue
            d = math.hypot(e.pos[0] - px, e.pos[2] - pz)
            if d > 200.0:
                continue
            bob = math.sin(t * 1.15 + e.phase) * 0.28
            pos.append((e.pos[0], e.pos[1] + bob, e.pos[2]))
            rot.append(t * 0.75 + e.phase)
            scl.append(0.95 + 0.06 * math.sin(t * 2.4 + e.phase))
            tint.append((0.62, 0.86, 0.92))
            glow.append(0.95 + 0.30 * math.sin(t * 2.0 + e.phase) + e.highlight)
        self.coll_mesh.upload(pack_instances(pos, rot, scl, tint, glow) if pos
                              else np.zeros((0, 16), F32))

    def upload_player(self, pos, yaw, squash=1.0, lean=0.0, tint=(0.60, 0.55, 0.48),
                      anim="idle"):
        # 呼吸律动: 胸口微胀, 肩背微收 (与 NPC 一致的"活物"感)
        br = math.sin(self.time * 1.35) * 0.012
        sy = squash * (1.0 + br)
        sxz = 1.0 + (1.0 - squash) * 0.35 - br * 0.55
        data = pack_instances([tuple(pos)], [yaw],
                              [(sxz, sy, sxz)],
                              [tint], [0.02])
        self.player_mesh.upload(data)
        if self.player_skinned:
            self.player_mesh.set_bones(
                SKIN.pose_matrices(anim, self.time, 0.0, 1.74))

    # ------------------------------------------------------------------
    def render(self, shadow=False):
        if not shadow:
            self.r.prepare_object(roughness=0.68, metallic=0.02, noise_scale=0.0)
        for im, members, _h in self.npc_groups.values():
            im.render(shadow=shadow)
        for im, _e in self.glb_npcs:
            im.render(shadow=shadow)
        self.player_mesh.render(shadow=shadow)

        if not shadow:
            self.r.prepare_object(roughness=0.55, metallic=0.05, noise_scale=0.7)
        for im, members in self.inter_groups.values():
            im.render(shadow=shadow)

        if not shadow:
            self.r.prepare_object(roughness=0.18, metallic=0.25, noise_scale=0.0)
        self.coll_mesh.render(shadow=shadow)

    def release(self):
        for im, _m, _h in self.npc_groups.values():
            im.release()
        for im, _e in self.glb_npcs:
            im.release()
        for im, _m in self.inter_groups.values():
            im.release()
        self.coll_mesh.release()
        self.player_mesh.release()
