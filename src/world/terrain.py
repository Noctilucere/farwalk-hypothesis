"""
terrain.py -- 程序化开放世界地形

世界为 960m x 960m 的连续地表, 由 6 个区域的影响场混合而成:
    wilds(荒原) blackstone(黑石祭址) lostland(银蓝苔原)
    silenthall(无声殿) mutezone(消音地带) mirror(镜之境)

每个区域各有独立的高度算子与配色, 靠 smoothstep 影响权重做无缝过渡,
玩家跨区域时地貌、色调、雾、天空、渲染风格 (写实<->卡通) 同步插值。

地形被切成 12x12 个 chunk 分别提交, 配合视锥剔除。
"""
from __future__ import annotations

import math

import numpy as np

from ..engine import math3d as m3

F32 = np.float32

CELL = 2.5
CELLS = 384
SIZE = CELL * CELLS            # 960 m
HALF = SIZE * 0.5
CHUNK_CELLS = 32
CHUNKS = CELLS // CHUNK_CELLS  # 12
WATER_LEVEL = 2.2

# --------------------------------------------------------------------------
# 区域定义
# --------------------------------------------------------------------------
REGION_ORDER = ["wilds", "blackstone", "lostland", "silenthall", "mutezone", "mirror"]

REGION_POS = {
    "wilds":      (0.0, 60.0),
    "blackstone": (-290.0, -230.0),
    "lostland":   (300.0, -215.0),
    "silenthall": (320.0, 265.0),
    "mutezone":   (-315.0, 275.0),
    "mirror":     (-20.0, -400.0),
}
REGION_RADIUS = {
    "wilds": 300.0, "blackstone": 190.0, "lostland": 200.0,
    "silenthall": 185.0, "mutezone": 195.0, "mirror": 165.0,
}

# 地表基色 (线性空间)
REGION_ALBEDO = {
    "wilds":      ((0.222, 0.220, 0.206), (0.190, 0.190, 0.182)),
    "blackstone": ((0.062, 0.060, 0.070), (0.104, 0.098, 0.108)),
    "lostland":   ((0.212, 0.318, 0.352), (0.336, 0.422, 0.436)),
    "silenthall": ((0.268, 0.252, 0.226), (0.352, 0.338, 0.310)),
    "mutezone":   ((0.128, 0.126, 0.124), (0.186, 0.182, 0.176)),
    "mirror":     ((0.028, 0.030, 0.042), (0.062, 0.066, 0.086)),
}

# 每个区域的渲染氛围 (供 Renderer 插值)
REGION_MOOD = {
    "wilds": dict(
        style=0.62, exposure=1.06, sun_dir=(0.38, 0.55, 0.74),
        sun_color=(1.10, 1.08, 1.04), ambient_sky=(0.34, 0.40, 0.50),
        ambient_ground=(0.17, 0.15, 0.11), fog_color=(0.54, 0.56, 0.60),
        fog_sun_color=(0.78, 0.75, 0.70), fog_density=0.0046, fog_height=0.020,
        sky_zenith=(0.20, 0.36, 0.64), sky_horizon=(0.78, 0.80, 0.80),
        ground=(0.20, 0.18, 0.14), stars=0.0, clouds=0.62,
        saturation=0.90, lift=(0.006, 0.005, 0.002), gain=(1.02, 1.00, 0.96),
        outline=0.55, bloom=0.48, vignette=0.48, grain=0.020, wind=0.062,
        water=(0.22, 0.40, 0.44), water_deep=(0.03, 0.08, 0.11),
    ),
    "blackstone": dict(
        style=0.05, exposure=1.02, sun_dir=(-0.42, 0.30, 0.36),
        sun_color=(0.82, 0.80, 0.92), ambient_sky=(0.14, 0.16, 0.24),
        ambient_ground=(0.05, 0.05, 0.07), fog_color=(0.20, 0.21, 0.27),
        fog_sun_color=(0.42, 0.38, 0.46), fog_density=0.0128, fog_height=0.032,
        sky_zenith=(0.030, 0.038, 0.070), sky_horizon=(0.15, 0.15, 0.21),
        ground=(0.04, 0.04, 0.05), stars=0.55, clouds=0.34,
        saturation=0.78, lift=(0.004, 0.004, 0.010), gain=(0.94, 0.96, 1.06),
        outline=0.0, bloom=0.76, vignette=0.86, grain=0.030, wind=0.030,
        water=(0.08, 0.12, 0.18), water_deep=(0.01, 0.02, 0.04),
    ),
    "lostland": dict(
        style=1.0, exposure=1.12, sun_dir=(0.24, 0.72, -0.62),
        sun_color=(1.24, 1.26, 1.30), ambient_sky=(0.44, 0.54, 0.62),
        ambient_ground=(0.20, 0.24, 0.26), fog_color=(0.72, 0.80, 0.84),
        fog_sun_color=(0.92, 0.95, 0.98), fog_density=0.0058, fog_height=0.016,
        sky_zenith=(0.30, 0.50, 0.72), sky_horizon=(0.84, 0.90, 0.92),
        ground=(0.26, 0.32, 0.34), stars=0.0, clouds=0.44,
        saturation=1.10, lift=(0.010, 0.014, 0.016), gain=(0.99, 1.02, 1.04),
        outline=0.92, bloom=0.52, vignette=0.36, grain=0.010, wind=0.048,
        water=(0.26, 0.54, 0.58), water_deep=(0.05, 0.16, 0.22),
    ),
    "silenthall": dict(
        style=0.22, exposure=0.98, sun_dir=(0.62, 0.44, -0.20),
        sun_color=(1.10, 1.02, 0.88), ambient_sky=(0.22, 0.24, 0.28),
        ambient_ground=(0.09, 0.08, 0.08), fog_color=(0.36, 0.35, 0.34),
        fog_sun_color=(0.60, 0.56, 0.50), fog_density=0.0108, fog_height=0.026,
        sky_zenith=(0.10, 0.13, 0.20), sky_horizon=(0.40, 0.38, 0.36),
        ground=(0.10, 0.09, 0.08), stars=0.22, clouds=0.30,
        saturation=0.88, lift=(0.008, 0.006, 0.004), gain=(1.02, 1.00, 0.96),
        outline=0.0, bloom=0.68, vignette=0.78, grain=0.026, wind=0.018,
        water=(0.12, 0.20, 0.24), water_deep=(0.02, 0.04, 0.07),
    ),
    "mutezone": dict(
        style=0.0, exposure=0.92, sun_dir=(-0.20, 0.36, -0.70),
        sun_color=(0.72, 0.72, 0.74), ambient_sky=(0.16, 0.16, 0.17),
        ambient_ground=(0.06, 0.06, 0.06), fog_color=(0.30, 0.30, 0.31),
        fog_sun_color=(0.40, 0.40, 0.41), fog_density=0.0190, fog_height=0.040,
        sky_zenith=(0.09, 0.09, 0.10), sky_horizon=(0.28, 0.28, 0.29),
        ground=(0.08, 0.08, 0.08), stars=0.0, clouds=0.86,
        saturation=0.34, lift=(0.010, 0.010, 0.010), gain=(0.96, 0.96, 0.96),
        outline=0.0, bloom=0.58, vignette=0.96, grain=0.042, wind=0.006,
        water=(0.10, 0.11, 0.12), water_deep=(0.02, 0.02, 0.03),
    ),
    "mirror": dict(
        style=0.0, exposure=1.00, sun_dir=(0.10, 0.24, 0.96),
        sun_color=(0.70, 0.74, 0.96), ambient_sky=(0.10, 0.12, 0.20),
        ambient_ground=(0.03, 0.03, 0.05), fog_color=(0.10, 0.11, 0.16),
        fog_sun_color=(0.24, 0.26, 0.40), fog_density=0.0128, fog_height=0.022,
        sky_zenith=(0.010, 0.012, 0.024), sky_horizon=(0.05, 0.06, 0.10),
        ground=(0.02, 0.02, 0.03), stars=1.25, clouds=0.06,
        saturation=0.62, lift=(0.002, 0.003, 0.008), gain=(0.92, 0.95, 1.10),
        outline=0.0, bloom=0.98, vignette=1.02, grain=0.020, wind=0.004,
        water=(0.06, 0.09, 0.16), water_deep=(0.01, 0.01, 0.03),
    ),
}


def lerp_mood(a, b, t):
    out = {}
    for k, va in a.items():
        vb = b[k]
        if isinstance(va, tuple):
            out[k] = tuple(va[i] + (vb[i] - va[i]) * t for i in range(len(va)))
        else:
            out[k] = va + (vb - va) * t
    return out


# --------------------------------------------------------------------------
# 世界生成
# --------------------------------------------------------------------------
class WorldGen:
    def __init__(self, seed=20260805):
        self.seed = seed
        self.perm_a = m3._build_perm(seed)
        self.perm_b = m3._build_perm(seed + 977)
        self.perm_c = m3._build_perm(seed + 3313)

    # ---- 区域权重场 ----
    def region_weights(self, X, Z):
        ws = {}
        total = np.zeros_like(X)
        for name in REGION_ORDER:
            cx, cz = REGION_POS[name]
            rad = REGION_RADIUS[name]
            d = np.sqrt((X - cx) ** 2 + (Z - cz) ** 2)
            w = 1.0 - np.clip(d / (rad * 1.55), 0.0, 1.0)
            w = w * w * (3.0 - 2.0 * w)
            w = w ** 1.7 + 1e-4
            ws[name] = w
            total = total + w
        for name in REGION_ORDER:
            ws[name] = ws[name] / total
        return ws

    # ---- 高度场 ----
    def height(self, X, Z, ws=None):
        if ws is None:
            ws = self.region_weights(X, Z)
        base = m3.fbm2(X * 0.0021, Z * 0.0021, 5, 2.05, 0.52, self.perm_a) * 34.0

        # 荒原: 起伏丘陵 + 干河床
        h_w = base * 1.05
        h_w += m3.fbm2(X * 0.0082, Z * 0.0082, 4, 2.1, 0.5, self.perm_b) * 11.0
        riv = np.abs(m3.fbm2(X * 0.0032 + 4.0, Z * 0.0032 - 2.0, 3, 2.0, 0.5, self.perm_c))
        h_w -= np.exp(-((riv - 0.06) * 26.0) ** 2) * 7.5
        h_w += 8.0

        # 黑石: 锐利脊线 + 深裂隙
        ridge = m3.ridged2(X * 0.0046, Z * 0.0046, 5, 2.15, 0.52, self.perm_b)
        h_b = 6.0 + ridge * 62.0 + base * 0.30
        crack = np.abs(m3.fbm2(X * 0.0125 - 8.0, Z * 0.0125 + 5.0, 3, 2.0, 0.5, self.perm_a))
        h_b -= np.exp(-((crack - 0.05) * 34.0) ** 2) * 16.0

        # 失落之地: 高台苔原, 平缓丘包
        h_l = 26.0 + m3.fbm2(X * 0.0038, Z * 0.0038, 4, 2.0, 0.42, self.perm_c) * 13.0
        h_l += np.sin(X * 0.0125) * np.cos(Z * 0.0112) * 3.4

        # 无声殿: 环形碗地 + 中央洞窟口
        cx, cz = REGION_POS["silenthall"]
        dr = np.sqrt((X - cx) ** 2 + (Z - cz) ** 2)
        bowl = np.clip(dr / 150.0, 0.0, 1.4)
        h_s = 10.0 + (bowl ** 2) * 46.0 - 20.0 * np.exp(-((dr / 46.0) ** 2))
        h_s += m3.fbm2(X * 0.0068, Z * 0.0068, 4, 2.0, 0.5, self.perm_a) * 6.5

        # 消音地带: 近乎水平的死寂平原, 偶有塌陷
        h_m = 12.0 + m3.fbm2(X * 0.0030, Z * 0.0030, 3, 2.0, 0.45, self.perm_b) * 5.0
        sink = m3.fbm2(X * 0.0092 + 21.0, Z * 0.0092 - 13.0, 3, 2.0, 0.5, self.perm_c)
        h_m -= np.clip(sink - 0.18, 0.0, 1.0) * 14.0

        # 镜之境: 绝对水平的黑色镜面台地
        cx2, cz2 = REGION_POS["mirror"]
        dr2 = np.sqrt((X - cx2) ** 2 + (Z - cz2) ** 2)
        h_r = 18.0 + np.clip((dr2 - 120.0) / 90.0, 0.0, 1.0) ** 2 * 40.0
        h_r += m3.fbm2(X * 0.0052, Z * 0.0052, 3, 2.0, 0.5, self.perm_a) * 1.1

        h = (ws["wilds"] * h_w + ws["blackstone"] * h_b + ws["lostland"] * h_l
             + ws["silenthall"] * h_s + ws["mutezone"] * h_m + ws["mirror"] * h_r)

        # 世界边界抬高成环山, 形成天然屏障
        edge = np.maximum(np.abs(X), np.abs(Z)) / HALF
        wall = np.clip((edge - 0.80) / 0.20, 0.0, 1.0)
        h = h + wall ** 2 * 130.0
        return h.astype(F32)

    def albedo(self, X, Z, ws):
        n = m3.fbm2(X * 0.0068, Z * 0.0068, 3, 2.0, 0.5, self.perm_c)
        n = np.clip(n * 1.4 + 0.5, 0.0, 1.0)[..., None]
        out = np.zeros(X.shape + (3,), F32)
        for name in REGION_ORDER:
            c0, c1 = REGION_ALBEDO[name]
            col = np.asarray(c0, F32) * (1.0 - n) + np.asarray(c1, F32) * n
            out += ws[name][..., None] * col
        return out


# --------------------------------------------------------------------------
# 地形网格
# --------------------------------------------------------------------------
class Terrain:
    def __init__(self, ctx, renderer, gen: WorldGen, progress=None):
        self.ctx = ctx
        self.r = renderer
        self.gen = gen
        n = CELLS + 1
        xs = (np.arange(n, dtype=F32) - CELLS * 0.5) * CELL
        self.X, self.Z = np.meshgrid(xs, xs, indexing="ij")
        if progress:
            progress("正在演算地表高度场", 0.10)
        self.ws = gen.region_weights(self.X, self.Z)
        self.H = gen.height(self.X, self.Z, self.ws)
        if progress:
            progress("正在计算法线与湿润度", 0.24)
        self.N = self._normals(self.H)
        self.A = gen.albedo(self.X, self.Z, self.ws)
        # 湿润度: 低洼 + 平缓处
        flat = np.clip(self.N[..., 1], 0.0, 1.0) ** 3
        low = np.clip((WATER_LEVEL + 7.0 - self.H) / 9.0, 0.0, 1.0)
        self.W = (flat * low).astype(F32)

        if progress:
            progress("正在切分地形区块", 0.34)
        self.chunks = []
        self._build_chunks()
        self.visible = 0

    def _normals(self, H):
        gz, gx = np.gradient(H.astype(np.float64), CELL)
        n = np.stack([-gz, np.ones_like(H, np.float64), -gx], -1)
        n /= np.linalg.norm(n, axis=-1, keepdims=True)
        return n.astype(F32)

    def _build_chunks(self):
        prog = self.r.p_terrain
        prog_s = self.r.p_sh_ter
        cc = CHUNK_CELLS
        # 单个 chunk 的索引模板
        idx = []
        w = cc + 1
        for a in range(cc):
            for b in range(cc):
                i0 = a * w + b
                idx += [i0, i0 + 1, i0 + w, i0 + 1, i0 + w + 1, i0 + w]
        idx = np.array(idx, np.uint32)
        ibo = self.ctx.buffer(idx.tobytes())
        self.shared_ibo = ibo
        self.index_count = len(idx)

        for ci in range(CHUNKS):
            for cj in range(CHUNKS):
                i0, j0 = ci * cc, cj * cc
                sl = (slice(i0, i0 + cc + 1), slice(j0, j0 + cc + 1))
                px = self.X[sl]
                pz = self.Z[sl]
                py = self.H[sl]
                nn = self.N[sl]
                aa = self.A[sl]
                wwet = self.W[sl]
                v = np.empty((cc + 1, cc + 1, 11), F32)
                v[..., 0] = px
                v[..., 1] = py
                v[..., 2] = pz
                v[..., 3:6] = nn
                v[..., 6:9] = aa
                v[..., 9] = 0.0
                v[..., 10] = wwet
                vbo = self.ctx.buffer(np.ascontiguousarray(v.reshape(-1, 11)).tobytes())
                content = [(vbo, "3f 3f 3f 2f", "in_pos", "in_normal", "in_albedo", "in_params")]
                # 阴影 pass 只需要位置, 其余属性以填充跳过 (否则驱动会剔除未用属性)
                content_s = [(vbo, "3f 8x4", "in_pos")]
                vao = self.ctx.vertex_array(prog, content, index_buffer=ibo)
                vao_s = self.ctx.vertex_array(prog_s, content_s, index_buffer=ibo)
                cx = float(px.mean())
                cz = float(pz.mean())
                ymin, ymax = float(py.min()), float(py.max())
                radius = math.sqrt((cc * CELL * 0.5) ** 2 * 2 + ((ymax - ymin) * 0.5) ** 2) + 2.0
                self.chunks.append(dict(vbo=vbo, vao=vao, vao_s=vao_s,
                                        center=(cx, (ymin + ymax) * 0.5, cz),
                                        radius=radius, ij=(ci, cj)))

    # ------------------------------------------------------------------
    def height_at(self, x, z):
        """双线性采样, 与网格完全一致。"""
        fx = (x / CELL) + CELLS * 0.5
        fz = (z / CELL) + CELLS * 0.5
        i = int(math.floor(fx))
        j = int(math.floor(fz))
        if i < 0 or j < 0 or i >= CELLS or j >= CELLS:
            i = min(max(i, 0), CELLS - 1)
            j = min(max(j, 0), CELLS - 1)
        tx = fx - i
        tz = fz - j
        tx = min(max(tx, 0.0), 1.0)
        tz = min(max(tz, 0.0), 1.0)
        H = self.H
        h00 = H[i, j]
        h10 = H[i + 1, j]
        h01 = H[i, j + 1]
        h11 = H[i + 1, j + 1]
        return float((h00 * (1 - tx) + h10 * tx) * (1 - tz) + (h01 * (1 - tx) + h11 * tx) * tz)

    def heights_at(self, xs, zs):
        fx = np.clip(np.asarray(xs, F32) / CELL + CELLS * 0.5, 0, CELLS - 1e-3)
        fz = np.clip(np.asarray(zs, F32) / CELL + CELLS * 0.5, 0, CELLS - 1e-3)
        i = fx.astype(np.int32)
        j = fz.astype(np.int32)
        tx = fx - i
        tz = fz - j
        H = self.H
        h00 = H[i, j]
        h10 = H[i + 1, j]
        h01 = H[i, j + 1]
        h11 = H[i + 1, j + 1]
        return (h00 * (1 - tx) + h10 * tx) * (1 - tz) + (h01 * (1 - tx) + h11 * tx) * tz

    def normal_at(self, x, z):
        fx = min(max(x / CELL + CELLS * 0.5, 0), CELLS - 1e-3)
        fz = min(max(z / CELL + CELLS * 0.5, 0), CELLS - 1e-3)
        return self.N[int(fx), int(fz)]

    def slope_at(self, x, z):
        return 1.0 - float(self.normal_at(x, z)[1])

    def region_at(self, x, z):
        """返回 (主区域名, 权重字典)。"""
        X = np.array([[x]], F32)
        Z = np.array([[z]], F32)
        ws = self.gen.region_weights(X, Z)
        best, bw = "wilds", -1.0
        d = {}
        for k in REGION_ORDER:
            v = float(ws[k][0, 0])
            d[k] = v
            if v > bw:
                best, bw = k, v
        return best, d

    # ------------------------------------------------------------------
    def render(self, frustum=None, shadow=False, center=None, max_dist=None):
        n = 0
        for c in self.chunks:
            if frustum is not None and not frustum.sphere_visible(c["center"], c["radius"]):
                continue
            if max_dist is not None and center is not None:
                dx = c["center"][0] - center[0]
                dz = c["center"][2] - center[2]
                if dx * dx + dz * dz > max_dist * max_dist:
                    continue
            (c["vao_s"] if shadow else c["vao"]).render()
            n += 1
        if not shadow:
            self.visible = n
        return n


# --------------------------------------------------------------------------
# 水面
# --------------------------------------------------------------------------
class Water:
    def __init__(self, ctx, renderer, level=WATER_LEVEL, extent=HALF, step=12.0):
        self.level = level
        n = int(extent * 2 / step) + 1
        xs = np.linspace(-extent, extent, n).astype(F32)
        X, Z = np.meshgrid(xs, xs, indexing="ij")
        v = np.stack([X, np.full_like(X, level), Z], -1).reshape(-1, 3).astype(F32)
        idx = []
        for a in range(n - 1):
            for b in range(n - 1):
                i0 = a * n + b
                idx += [i0, i0 + 1, i0 + n, i0 + 1, i0 + n + 1, i0 + n]
        idx = np.array(idx, np.uint32)
        self.vbo = ctx.buffer(v.tobytes())
        self.ibo = ctx.buffer(idx.tobytes())
        self.vao = ctx.vertex_array(renderer.p_water,
                                    [(self.vbo, "3f", "in_pos")], index_buffer=self.ibo)

    def render(self):
        self.vao.render()
