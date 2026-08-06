"""
scatter.py -- 场景实例化填充

把程序化几何 (草丛 / 树 / 枯木 / 岩石 / 晶体 / 巨石碑 / 碎片) 按区域密度
散布到地形表面, 用实例化渲染一次性提交。

每类物件:
    * 生成阶段  -> 采样位置(区域权重+坡度过滤) -> 预打包成 float32[N,16]
    * 运行阶段  -> 按相机距离做向量化裁剪 -> 上传子集 -> 一次 draw call

所有随机都由固定种子驱动, 因此世界在每次启动时完全一致。
"""
from __future__ import annotations

import math

import numpy as np

from ..engine import mesh as MSH
from ..engine.renderer import InstancedMesh, pack_instances
from . import terrain as T

F32 = np.float32


# --------------------------------------------------------------------------
# 每个区域的植被 / 物件配色
# --------------------------------------------------------------------------
GRASS_TINT = {
    "wilds":      (0.270, 0.292, 0.236),
    "blackstone": (0.110, 0.108, 0.130),
    "lostland":   (0.300, 0.520, 0.545),
    "silenthall": (0.250, 0.238, 0.196),
    "mutezone":   (0.196, 0.196, 0.190),
    "mirror":     (0.070, 0.078, 0.110),
}
ROCK_TINT = {
    "wilds":      (0.272, 0.270, 0.252),
    "blackstone": (0.086, 0.084, 0.098),
    "lostland":   (0.330, 0.372, 0.392),
    "silenthall": (0.310, 0.296, 0.268),
    "mutezone":   (0.180, 0.178, 0.176),
    "mirror":     (0.052, 0.056, 0.076),
}
TREE_TINT = {
    "wilds":      (0.196, 0.236, 0.190),
    "lostland":   (0.260, 0.470, 0.470),
}
DEAD_TINT = {
    "wilds":      (0.166, 0.168, 0.158),
    "blackstone": (0.075, 0.072, 0.082),
    "silenthall": (0.190, 0.178, 0.158),
    "mutezone":   (0.150, 0.148, 0.144),
}
CRYSTAL_TINT = {
    "blackstone": ((0.34, 0.24, 0.52), 0.55),
    "lostland":   ((0.32, 0.72, 0.74), 0.42),
    "mirror":     ((0.26, 0.34, 0.72), 0.70),
    "silenthall": ((0.62, 0.54, 0.36), 0.30),
}


def _rng(seed):
    return np.random.default_rng(seed)


class Scatter:
    """全部静态场景物件的容器。"""

    def __init__(self, ctx, renderer, terrain: T.Terrain, progress=None, quality="high"):
        self.ctx = ctx
        self.r = renderer
        self.terrain = terrain
        self.gen = terrain.gen
        self.quality = quality
        self.groups = []       # [dict(mesh, data, pos, cull)]
        self.drawn = 0

        dens = 1.0 if quality == "high" else (0.62 if quality == "medium" else 0.34)

        if progress:
            progress("正在播种植被", 0.42)
        self._build_grass(dens)
        if progress:
            progress("正在生长林木", 0.52)
        self._build_trees(dens)
        if progress:
            progress("正在堆叠岩层", 0.60)
        self._build_rocks(dens)
        if progress:
            progress("正在结晶", 0.68)
        self._build_crystals(dens)
        if progress:
            progress("正在竖立石碑", 0.74)
        self._build_monoliths()
        if progress:
            progress("正在搭建建筑", 0.80)
        self._build_structures(dens)

    # ------------------------------------------------------------------
    # 采样工具
    # ------------------------------------------------------------------
    def _sample(self, region, count, rng, max_slope=0.42, radius_mul=1.0,
                min_h=None, max_h=None, ring=None):
        """在区域影响圈内采样合法落点, 返回 (xs, zs, ys, weights)。"""
        if count <= 0:
            return (np.zeros(0, F32),) * 4
        cx, cz = T.REGION_POS[region]
        rad = T.REGION_RADIUS[region] * radius_mul
        n = int(count * 2.2) + 16
        if ring is None:
            rr = np.sqrt(rng.random(n)) * rad
        else:
            lo, hi = ring
            rr = np.sqrt(rng.uniform(lo ** 2, hi ** 2, n)) * rad
        aa = rng.random(n) * math.tau
        xs = (cx + np.cos(aa) * rr).astype(F32)
        zs = (cz + np.sin(aa) * rr).astype(F32)

        lim = T.HALF - 40.0
        keep = (np.abs(xs) < lim) & (np.abs(zs) < lim)
        xs, zs = xs[keep], zs[keep]
        if len(xs) == 0:
            return (np.zeros(0, F32),) * 4

        ws = self.gen.region_weights(xs, zs)
        w = ws[region]
        keep = w > 0.30
        xs, zs, w = xs[keep], zs[keep], w[keep]
        if len(xs) == 0:
            return (np.zeros(0, F32),) * 4

        ys = self.terrain.heights_at(xs, zs).astype(F32)
        # 坡度过滤 (用高度差近似)
        d = 1.6
        hx = self.terrain.heights_at(xs + d, zs) - self.terrain.heights_at(xs - d, zs)
        hz = self.terrain.heights_at(xs, zs + d) - self.terrain.heights_at(xs, zs - d)
        slope = np.sqrt(hx ** 2 + hz ** 2) / (2 * d)
        keep = slope < max_slope
        if min_h is not None:
            keep &= ys > min_h
        if max_h is not None:
            keep &= ys < max_h
        xs, zs, ys, w = xs[keep], zs[keep], ys[keep], w[keep]

        if len(xs) > count:
            idx = rng.choice(len(xs), count, replace=False)
            xs, zs, ys, w = xs[idx], zs[idx], ys[idx], w[idx]
        return xs, zs, ys, w

    def _add_group(self, verts, idx, data, cull, foliage=False, roughness=0.85,
                   metallic=0.0, noise=0.0, tag=None):
        if len(data) == 0:
            return
        im = InstancedMesh(self.ctx, self.r, verts, idx,
                           max_instances=max(len(data) // 3, 64), foliage=foliage)
        self.groups.append(dict(mesh=im, data=np.ascontiguousarray(data, F32),
                                pos=np.ascontiguousarray(data[:, [3, 7, 11]], F32),
                                cull=float(cull), foliage=foliage,
                                roughness=roughness, metallic=metallic, noise=noise,
                                tag=tag))

    # ------------------------------------------------------------------
    # 植被
    # ------------------------------------------------------------------
    def _build_grass(self, dens):
        plan = [("wilds", 30000, 0.85), ("lostland", 17000, 0.72),
                ("silenthall", 4200, 0.55), ("mutezone", 6000, 0.50),
                ("blackstone", 1800, 0.40)]
        for vi in range(2):
            v, i = MSH.grass_clump(3 + vi, seed=71 + vi * 13, height=1.0, width=0.085)
            chunks = []
            for region, cnt, hs in plan:
                rng = _rng(hash((region, "grass", vi)) & 0xFFFF)
                xs, zs, ys, w = self._sample(region, int(cnt * dens * 0.5), rng, 0.52,
                                             min_h=T.WATER_LEVEL + 0.3)
                if len(xs) == 0:
                    continue
                n = len(xs)
                base = np.asarray(GRASS_TINT[region], F32)
                tint = base[None, :] * rng.uniform(0.72, 1.28, (n, 1)).astype(F32)
                sc = rng.uniform(0.62, 1.45, n).astype(F32) * hs
                scl = np.stack([sc * rng.uniform(0.8, 1.2, n), sc, sc], 1).astype(F32)
                chunks.append(pack_instances(np.stack([xs, ys - 0.05, zs], 1),
                                             rng.random(n).astype(F32) * math.tau,
                                             scl, tint, None))
            if chunks:
                self._add_group(v, i, np.concatenate(chunks, 0), 74.0, foliage=True)

    # ------------------------------------------------------------------
    def _build_trees(self, dens):
        # 活树 (荒原 / 苔原)
        for vi in range(2):
            v, i = MSH.tree(seed=200 + vi * 7, height=6.4 + vi * 1.6, dead=False)
            chunks = []
            for region, cnt in (("wilds", 340), ("lostland", 240)):
                rng = _rng(hash((region, "tree", vi)) & 0xFFFF)
                xs, zs, ys, w = self._sample(region, int(cnt * dens * 0.5), rng, 0.34,
                                             min_h=T.WATER_LEVEL + 0.35)
                if len(xs) == 0:
                    continue
                n = len(xs)
                base = np.asarray(TREE_TINT[region], F32)
                tint = base[None, :] * rng.uniform(0.78, 1.22, (n, 1)).astype(F32)
                sc = rng.uniform(0.72, 1.5, n).astype(F32)
                glow = np.full(n, 0.10 if region == "lostland" else 0.0, F32)
                chunks.append(pack_instances(np.stack([xs, ys - 0.2, zs], 1),
                                             rng.random(n).astype(F32) * math.tau,
                                             sc, tint, glow))
            if chunks:
                self._add_group(v, i, np.concatenate(chunks, 0), 250.0, noise=0.55)

        # 枯木
        for vi in range(2):
            v, i = MSH.tree(seed=310 + vi * 11, height=5.2 + vi * 2.0, dead=True)
            chunks = []
            for region, cnt in (("mutezone", 520), ("blackstone", 210),
                                ("silenthall", 140), ("wilds", 170)):
                rng = _rng(hash((region, "dead", vi)) & 0xFFFF)
                xs, zs, ys, w = self._sample(region, int(cnt * dens * 0.5), rng, 0.46,
                                             min_h=T.WATER_LEVEL + 0.35)
                if len(xs) == 0:
                    continue
                n = len(xs)
                base = np.asarray(DEAD_TINT[region], F32)
                tint = base[None, :] * rng.uniform(0.80, 1.20, (n, 1)).astype(F32)
                sc = rng.uniform(0.65, 1.35, n).astype(F32)
                chunks.append(pack_instances(np.stack([xs, ys - 0.2, zs], 1),
                                             rng.random(n).astype(F32) * math.tau,
                                             sc, tint, None))
            if chunks:
                self._add_group(v, i, np.concatenate(chunks, 0), 230.0, noise=0.75)

    # ------------------------------------------------------------------
    def _build_rocks(self, dens):
        # 小石 (贴地)
        for vi in range(3):
            v, i = MSH.rock(seed=400 + vi * 5, rings=8, sectors=12, rough=0.36)
            chunks = []
            for region in T.REGION_ORDER:
                cnt = {"wilds": 900, "blackstone": 1300, "lostland": 620,
                       "silenthall": 700, "mutezone": 520, "mirror": 380}[region]
                rng = _rng(hash((region, "rock", vi)) & 0xFFFF)
                xs, zs, ys, w = self._sample(region, int(cnt * dens / 3), rng, 0.85,
                                             min_h=T.WATER_LEVEL + 0.4)
                if len(xs) == 0:
                    continue
                n = len(xs)
                base = np.asarray(ROCK_TINT[region], F32)
                tint = base[None, :] * rng.uniform(0.74, 1.26, (n, 1)).astype(F32)
                sc = rng.uniform(0.30, 1.05, n).astype(F32)
                scl = np.stack([sc, sc * rng.uniform(0.5, 1.0, n), sc], 1).astype(F32)
                chunks.append(pack_instances(np.stack([xs, ys - 0.16, zs], 1),
                                             rng.random(n).astype(F32) * math.tau,
                                             scl, tint, None))
            if chunks:
                self._add_group(v, i, np.concatenate(chunks, 0), 165.0, noise=1.4)

        # 巨岩
        for vi in range(2):
            v, i = MSH.rock(seed=520 + vi * 9, rings=10, sectors=16, rough=0.30)
            chunks = []
            for region in T.REGION_ORDER:
                cnt = {"wilds": 130, "blackstone": 260, "lostland": 90,
                       "silenthall": 150, "mutezone": 70, "mirror": 46}[region]
                rng = _rng(hash((region, "boulder", vi)) & 0xFFFF)
                xs, zs, ys, w = self._sample(region, int(cnt * dens / 2), rng, 0.95,
                                             min_h=T.WATER_LEVEL + 0.5)
                if len(xs) == 0:
                    continue
                n = len(xs)
                base = np.asarray(ROCK_TINT[region], F32)
                tint = base[None, :] * rng.uniform(0.70, 1.20, (n, 1)).astype(F32)
                sc = rng.uniform(1.8, 5.4, n).astype(F32)
                scl = np.stack([sc, sc * rng.uniform(0.55, 1.15, n), sc], 1).astype(F32)
                chunks.append(pack_instances(np.stack([xs, ys - sc * 0.30, zs], 1),
                                             rng.random(n).astype(F32) * math.tau,
                                             scl, tint, None))
            if chunks:
                self._add_group(v, i, np.concatenate(chunks, 0), 340.0, noise=0.55)

    # ------------------------------------------------------------------
    def _build_crystals(self, dens):
        for vi in range(2):
            v, i = MSH.crystal(seed=600 + vi * 3, facets=6, height=2.2, radius=0.40)
            chunks = []
            for region, cnt in (("blackstone", 300), ("lostland", 180),
                                ("mirror", 150), ("silenthall", 90)):
                rng = _rng(hash((region, "crystal", vi)) & 0xFFFF)
                xs, zs, ys, w = self._sample(region, int(cnt * dens * 0.5), rng, 0.75,
                                             min_h=T.WATER_LEVEL + 0.4)
                if len(xs) == 0:
                    continue
                n = len(xs)
                base, g = CRYSTAL_TINT[region]
                tint = np.asarray(base, F32)[None, :] * rng.uniform(0.80, 1.25, (n, 1)).astype(F32)
                glow = (rng.uniform(0.55, 1.35, n) * g).astype(F32)
                sc = rng.uniform(0.42, 1.9, n).astype(F32)
                chunks.append(pack_instances(np.stack([xs, ys - 0.3, zs], 1),
                                             rng.random(n).astype(F32) * math.tau,
                                             sc, tint, glow))
            if chunks:
                self._add_group(v, i, np.concatenate(chunks, 0), 260.0,
                                roughness=0.22, metallic=0.15)

        # 镜之境的悬浮碎玻璃
        v, i = MSH.shard(seed=777)
        rng = _rng(9911)
        xs, zs, ys, w = self._sample("mirror", int(420 * dens), rng, 1.4,
                                     radius_mul=1.15, min_h=T.WATER_LEVEL + 0.6)
        if len(xs):
            n = len(xs)
            tint = np.tile(np.asarray((0.30, 0.36, 0.62), F32)[None, :], (n, 1))
            glow = rng.uniform(0.30, 0.95, n).astype(F32)
            sc = rng.uniform(0.30, 1.1, n).astype(F32)
            ys2 = ys + rng.uniform(0.4, 9.0, n).astype(F32)
            self._add_group(v, i, pack_instances(np.stack([xs, ys2, zs], 1),
                                                 rng.random(n).astype(F32) * math.tau,
                                                 sc, tint, glow),
                            230.0, roughness=0.14, metallic=0.35)

    # ------------------------------------------------------------------
    def _build_monoliths(self):
        v, i = MSH.monolith(seed=888, height=5.6, width=1.15)
        chunks = []
        for region, cnt in (("blackstone", 46), ("silenthall", 30),
                            ("mirror", 18), ("mutezone", 22)):
            rng = _rng(hash((region, "mono")) & 0xFFFF)
            xs, zs, ys, w = self._sample(region, cnt, rng, 0.40,
                                         min_h=T.WATER_LEVEL + 0.5)
            if len(xs) == 0:
                continue
            n = len(xs)
            base = np.asarray(ROCK_TINT[region], F32) * 0.85
            tint = np.tile(base[None, :], (n, 1)) * rng.uniform(0.85, 1.15, (n, 1)).astype(F32)
            sc = rng.uniform(0.6, 1.6, n).astype(F32)
            chunks.append(pack_instances(np.stack([xs, ys - 0.35, zs], 1),
                                         rng.random(n).astype(F32) * math.tau,
                                         sc, tint, None))
        if chunks:
            self._add_group(v, i, np.concatenate(chunks, 0), 330.0, noise=0.9)

    def _build_structures(self, dens):
        """场景建筑与地貌地标: 遗迹/拱门/高柱/小屋/篝火/祭坛/路标/瞭望塔/石圈。"""
        plan = [
            (MSH.ruin, "ruin", ("wilds", 30), ("lostland", 18), ("blackstone", 34),
             ("silenthall", 14), ("mutezone", 12)),
            (MSH.arch, "arch", ("blackstone", 16), ("silenthall", 24), ("mutezone", 10),
             ("mirror", 8), ("wilds", 8)),
            (MSH.pillar, "pillar", ("wilds", 18), ("blackstone", 26), ("silenthall", 40),
             ("mutezone", 14), ("lostland", 12)),
            (MSH.hut, "hut", ("wilds", 16), ("lostland", 20), ("mutezone", 10),
             ("blackstone", 8)),
            (MSH.campfire, "campfire", ("wilds", 22), ("lostland", 14), ("blackstone", 12),
             ("silenthall", 10), ("mutezone", 8), ("mirror", 4)),
            (MSH.altar, "altar", ("wilds", 8), ("blackstone", 10), ("silenthall", 8),
             ("lostland", 6), ("mutezone", 5)),
            (MSH.signpost, "signpost", ("wilds", 14), ("lostland", 10), ("blackstone", 8),
             ("silenthall", 8), ("mutezone", 6)),
            (MSH.tower, "tower", ("wilds", 8), ("blackstone", 7), ("silenthall", 6),
             ("lostland", 6), ("mutezone", 4)),
            (MSH.stonecircle, "stonecircle", ("blackstone", 6), ("wilds", 6),
             ("lostland", 5), ("silenthall", 5), ("mirror", 3)),
            # 传送门: 每区域 1 个, 通向下一章节
            (MSH.portal, "portal", ("wilds", 1), ("blackstone", 1), ("lostland", 1),
             ("silenthall", 1), ("mutezone", 1), ("mirror", 1)),
        ]
        for fn, name, *regions in plan:
            v, i = fn(seed=abs(hash(name)) % 99991)
            chunks = []
            for region, cnt in regions:
                rng = _rng(hash((region, name)) & 0xFFFF)
                xs, zs, ys, w = self._sample(region, int(cnt * dens), rng, 0.32,
                                             min_h=T.WATER_LEVEL + 0.6)
                if len(xs) == 0:
                    continue
                n = len(xs)
                base = np.asarray(ROCK_TINT[region], F32)
                tint = np.tile(base[None, :], (n, 1)) * rng.uniform(0.85, 1.15, (n, 1)).astype(F32)
                sc = rng.uniform(0.85, 1.35, n).astype(F32)
                glow = np.zeros(n, F32)
                # 建筑类: tint.r = 1.05 标记 shader 启用程序化贴图
                if name in ("ruin", "arch", "pillar", "hut", "altar",
                            "signpost", "tower", "stonecircle", "portal"):
                    tint[:, 0] = 1.05
                if name == "hut":
                    glow = np.full(n, 0.55, F32)     # 顶光石
                elif name == "pillar":
                    glow = np.full(n, 0.12, F32)
                elif name == "campfire":
                    glow = np.full(n, 1.0, F32)      # 火焰
                    tint = tint * 0.9
                    tint[:, 0] = 0.0               # 篝火不用建筑贴图
                elif name == "altar":
                    glow = np.full(n, 0.65, F32)     # 祭坛光石
                elif name == "tower":
                    glow = np.full(n, 0.5, F32)      # 塔窗
                elif name == "portal":
                    glow = np.full(n, 1.2, F32)      # 传送门光柱
                    tint = tint * 1.1
                chunks.append(pack_instances(np.stack([xs, ys - 0.4, zs], 1),
                                             rng.random(n).astype(F32) * math.tau,
                                             sc, tint, glow))
            if chunks:
                self._add_group(v, i, np.concatenate(chunks, 0), 420.0, noise=0.7,
                                roughness=0.9, tag=name)

    # ------------------------------------------------------------------
    # 每帧裁剪 + 上传
    # ------------------------------------------------------------------
    def update(self, cam_pos):
        cx, cz = float(cam_pos[0]), float(cam_pos[2])
        total = 0
        for g in self.groups:
            p = g["pos"]
            dx = p[:, 0] - cx
            dz = p[:, 2] - cz
            m = (dx * dx + dz * dz) < (g["cull"] * g["cull"])
            sub = g["data"][m]
            g["mesh"].upload(sub)
            total += len(sub)
        self.drawn = total
        return total

    def render(self, shadow=False):
        # 不透明物件
        first = True
        for g in self.groups:
            if g["foliage"]:
                continue
            if not shadow:
                self.r.prepare_object(roughness=g["roughness"], metallic=g["metallic"],
                                      noise_scale=g["noise"])
            g["mesh"].render(shadow=shadow)
            first = False
        if shadow:
            return
        # 植被 (无阴影投射, 双面)
        prepared = False
        for g in self.groups:
            if not g["foliage"]:
                continue
            if not prepared:
                self.r.prepare_foliage()
                prepared = True
            g["mesh"].render(shadow=False)
        if prepared:
            self.ctx.enable(self.ctx.CULL_FACE)

    def release(self):
        for g in self.groups:
            g["mesh"].release()
        self.groups.clear()
