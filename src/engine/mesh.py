"""
mesh.py -- 程序化几何生成

本项目不使用任何外部模型文件, 所有网格在运行时由代码生成。
输出统一为 (vertices: float32[N, 6] (pos3+normal3), indices: uint32[M])。
植被另有 uv 通道 -> float32[N, 8]。

角色模型由基元拼装 (胶囊/球/锥/盒), 按 form 分为 7 种形态。
"""
from __future__ import annotations

import math

import numpy as np

F32 = np.float32
U32 = np.uint32


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def _pack(pos, nrm):
    return np.concatenate([np.asarray(pos, F32), np.asarray(nrm, F32)], axis=1).astype(F32)


def merge(parts):
    """把多个 (verts, idx) 合并成一个。"""
    vs, ids, off = [], [], 0
    for v, i in parts:
        if len(v) == 0:
            continue
        vs.append(v)
        ids.append(i + off)
        off += len(v)
    if not vs:
        return np.zeros((0, 6), F32), np.zeros((0,), U32)
    return np.concatenate(vs, 0).astype(F32), np.concatenate(ids, 0).astype(U32)


def transform(mesh, offset=(0, 0, 0), scl=(1, 1, 1), rot_y=0.0, rot_x=0.0, rot_z=0.0):
    """对网格做 缩放->旋转(ZXY)->平移。"""
    v, i = mesh
    v = v.copy()
    p = v[:, 0:3]
    n = v[:, 3:6]
    s = np.asarray(scl, F32)
    if s.ndim == 0:
        s = np.array([s, s, s], F32)
    p *= s
    # 法线用逆转置近似: 各向异性缩放时取倒数
    inv = 1.0 / np.maximum(s, 1e-6)
    n *= inv

    def rot(mat):
        nonlocal p, n
        p[:] = p @ mat.T
        n[:] = n @ mat.T

    if rot_z:
        c, sn = math.cos(rot_z), math.sin(rot_z)
        rot(np.array([[c, -sn, 0], [sn, c, 0], [0, 0, 1]], F32))
    if rot_x:
        c, sn = math.cos(rot_x), math.sin(rot_x)
        rot(np.array([[1, 0, 0], [0, c, -sn], [0, sn, c]], F32))
    if rot_y:
        c, sn = math.cos(rot_y), math.sin(rot_y)
        rot(np.array([[c, 0, sn], [0, 1, 0], [-sn, 0, c]], F32))

    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n /= np.maximum(ln, 1e-6)
    p += np.asarray(offset, F32)
    return v, i


# --------------------------------------------------------------------------
# 基元
# --------------------------------------------------------------------------
def sphere(rings=12, sectors=18, radius=1.0):
    r = np.linspace(0, math.pi, rings + 1)
    s = np.linspace(0, 2 * math.pi, sectors + 1)
    rr, ss = np.meshgrid(r, s, indexing="ij")
    x = np.sin(rr) * np.cos(ss)
    y = np.cos(rr)
    z = np.sin(rr) * np.sin(ss)
    nrm = np.stack([x, y, z], -1).reshape(-1, 3)
    pos = nrm * radius
    idx = []
    w = sectors + 1
    for a in range(rings):
        for b in range(sectors):
            i0 = a * w + b
            idx += [i0, i0 + w, i0 + 1, i0 + 1, i0 + w, i0 + w + 1]
    return _pack(pos, nrm), np.array(idx, U32)


def ellipsoid(rx, ry, rz, rings=12, sectors=18):
    v, i = sphere(rings, sectors, 1.0)
    return transform((v, i), scl=(rx, ry, rz))


def capsule(radius=0.3, height=1.0, rings=8, sectors=14):
    """沿 Y 轴的胶囊, 底部在 y=0。"""
    parts = []
    cyl_h = max(height - 2 * radius, 0.0)
    # 圆柱侧面
    s = np.linspace(0, 2 * math.pi, sectors + 1)
    cs, sn = np.cos(s), np.sin(s)
    ys = np.array([radius, radius + cyl_h], F32)
    pos, nrm = [], []
    for y in ys:
        pos.append(np.stack([cs * radius, np.full_like(cs, y), sn * radius], -1))
        nrm.append(np.stack([cs, np.zeros_like(cs), sn], -1))
    pos = np.concatenate(pos, 0)
    nrm = np.concatenate(nrm, 0)
    idx = []
    w = sectors + 1
    for b in range(sectors):
        idx += [b, b + w, b + 1, b + 1, b + w, b + w + 1]
    parts.append((_pack(pos, nrm), np.array(idx, U32)))
    # 上下半球
    top = hemisphere(radius, sectors, rings, up=True)
    parts.append(transform(top, offset=(0, radius + cyl_h, 0)))
    bot = hemisphere(radius, sectors, rings, up=False)
    parts.append(transform(bot, offset=(0, radius, 0)))
    return merge(parts)


def hemisphere(radius=1.0, sectors=14, rings=7, up=True):
    r = np.linspace(0, math.pi / 2, rings + 1)
    if not up:
        r = -r
    s = np.linspace(0, 2 * math.pi, sectors + 1)
    rr, ss = np.meshgrid(r, s, indexing="ij")
    x = np.sin(np.abs(rr)) * np.cos(ss)
    y = np.cos(rr) * (1 if up else -1)
    z = np.sin(np.abs(rr)) * np.sin(ss)
    y = np.where(np.abs(rr) < 1e-9, 1.0 if up else -1.0, y)
    nrm = np.stack([x, y, z], -1).reshape(-1, 3)
    ln = np.linalg.norm(nrm, axis=1, keepdims=True)
    nrm /= np.maximum(ln, 1e-6)
    pos = nrm * radius
    idx = []
    w = sectors + 1
    for a in range(rings):
        for b in range(sectors):
            i0 = a * w + b
            if up:
                idx += [i0, i0 + w, i0 + 1, i0 + 1, i0 + w, i0 + w + 1]
            else:
                idx += [i0, i0 + 1, i0 + w, i0 + 1, i0 + w + 1, i0 + w]
    return _pack(pos, nrm), np.array(idx, U32)


def box(sx=1.0, sy=1.0, sz=1.0):
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    faces = [
        ((0, 0, 1), [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]),
        ((0, 0, -1), [(hx, -hy, -hz), (-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz)]),
        ((1, 0, 0), [(hx, -hy, hz), (hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz)]),
        ((-1, 0, 0), [(-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz), (-hx, hy, -hz)]),
        ((0, 1, 0), [(-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz), (-hx, hy, -hz)]),
        ((0, -1, 0), [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)]),
    ]
    pos, nrm, idx = [], [], []
    for n, quad in faces:
        base = len(pos)
        for p in quad:
            pos.append(p)
            nrm.append(n)
        idx += [base, base + 1, base + 2, base, base + 2, base + 3]
    return _pack(np.array(pos, F32), np.array(nrm, F32)), np.array(idx, U32)


def cone(radius=0.5, height=1.0, sectors=16):
    s = np.linspace(0, 2 * math.pi, sectors + 1)
    cs, sn = np.cos(s), np.sin(s)
    slope = radius / max(height, 1e-5)
    pos, nrm, idx = [], [], []
    for i in range(sectors):
        a0, a1 = i, i + 1
        base = len(pos)
        pos += [(cs[a0] * radius, 0, sn[a0] * radius),
                (cs[a1] * radius, 0, sn[a1] * radius),
                (0, height, 0)]
        for a in (a0, a1):
            n = np.array([cs[a], slope, sn[a]], F32)
            nrm.append(n / np.linalg.norm(n))
        mid = (a0 + a1) * 0.5
        n = np.array([math.cos(s[i] + (s[1] - s[0]) / 2), slope, math.sin(s[i] + (s[1] - s[0]) / 2)], F32)
        nrm.append(n / np.linalg.norm(n))
        idx += [base, base + 1, base + 2]
    # 底面
    base = len(pos)
    pos.append((0, 0, 0))
    nrm.append((0, -1, 0))
    for i in range(sectors + 1):
        pos.append((cs[i] * radius, 0, sn[i] * radius))
        nrm.append((0, -1, 0))
    for i in range(sectors):
        idx += [base, base + 1 + i + 1, base + 1 + i]
    return _pack(np.array(pos, F32), np.array(nrm, F32)), np.array(idx, U32)


def cylinder(r0=0.4, r1=0.4, height=1.0, sectors=14, caps=True):
    s = np.linspace(0, 2 * math.pi, sectors + 1)
    cs, sn = np.cos(s), np.sin(s)
    slope = (r0 - r1) / max(height, 1e-5)
    pos, nrm = [], []
    for y, r in ((0.0, r0), (height, r1)):
        pos.append(np.stack([cs * r, np.full_like(cs, y), sn * r], -1))
        n = np.stack([cs, np.full_like(cs, slope), sn], -1)
        n /= np.linalg.norm(n, axis=1, keepdims=True)
        nrm.append(n)
    pos = np.concatenate(pos, 0)
    nrm = np.concatenate(nrm, 0)
    idx = []
    w = sectors + 1
    for b in range(sectors):
        idx += [b, b + w, b + 1, b + 1, b + w, b + w + 1]
    parts = [(_pack(pos, nrm), np.array(idx, U32))]
    if caps:
        for y, r, ny in ((0.0, r0, -1.0), (height, r1, 1.0)):
            cp, cn, ci = [], [], []
            cp.append((0, y, 0))
            cn.append((0, ny, 0))
            for i in range(sectors + 1):
                cp.append((cs[i] * r, y, sn[i] * r))
                cn.append((0, ny, 0))
            for i in range(sectors):
                if ny > 0:
                    ci += [0, 1 + i, 1 + i + 1]
                else:
                    ci += [0, 1 + i + 1, 1 + i]
            parts.append((_pack(np.array(cp, F32), np.array(cn, F32)), np.array(ci, U32)))
    return merge(parts)


def torus(R=1.0, r=0.25, seg=24, side=12):
    u = np.linspace(0, 2 * math.pi, seg + 1)
    v = np.linspace(0, 2 * math.pi, side + 1)
    uu, vv = np.meshgrid(u, v, indexing="ij")
    cx, cz = np.cos(uu), np.sin(uu)
    x = (R + r * np.cos(vv)) * cx
    y = r * np.sin(vv)
    z = (R + r * np.cos(vv)) * cz
    nx = np.cos(vv) * cx
    ny = np.sin(vv)
    nz = np.cos(vv) * cz
    pos = np.stack([x, y, z], -1).reshape(-1, 3)
    nrm = np.stack([nx, ny, nz], -1).reshape(-1, 3)
    idx = []
    w = side + 1
    for a in range(seg):
        for b in range(side):
            i0 = a * w + b
            idx += [i0, i0 + w, i0 + 1, i0 + 1, i0 + w, i0 + w + 1]
    return _pack(pos, nrm), np.array(idx, U32)


def quad_xz(size=1.0):
    h = size / 2
    pos = np.array([(-h, 0, -h), (h, 0, -h), (h, 0, h), (-h, 0, h)], F32)
    nrm = np.tile(np.array([0, 1, 0], F32), (4, 1))
    idx = np.array([0, 2, 1, 0, 3, 2], U32)
    return _pack(pos, nrm), idx


# --------------------------------------------------------------------------
# 岩石 / 晶体 / 碎片
# --------------------------------------------------------------------------
def rock(seed=0, rings=9, sectors=14, rough=0.34):
    rng = np.random.default_rng(seed)
    v, i = sphere(rings, sectors, 1.0)
    p = v[:, 0:3]
    # 三层噪声形变
    f1 = rng.uniform(0.7, 1.5, 3)
    f2 = rng.uniform(2.0, 4.0, 3)
    ph = rng.uniform(0, 6.28, 6)
    d = (np.sin(p[:, 0] * f1[0] + ph[0]) * np.cos(p[:, 2] * f1[1] + ph[1]) * 0.5
         + np.sin(p[:, 1] * f1[2] + ph[2]) * 0.3
         + np.sin(p[:, 0] * f2[0] + ph[3]) * np.sin(p[:, 2] * f2[1] + ph[4]) * 0.18
         + np.cos(p[:, 1] * f2[2] + ph[5]) * 0.12)
    scl = 1.0 + d * rough
    p *= scl[:, None]
    p[:, 1] *= rng.uniform(0.55, 0.95)
    v[:, 0:3] = p
    return recompute_normals(v, i)


def crystal(seed=0, facets=6, height=2.0, radius=0.45):
    rng = np.random.default_rng(seed)
    parts = []
    s = np.linspace(0, 2 * math.pi, facets + 1)[:-1]
    ring = np.stack([np.cos(s) * radius, np.zeros_like(s), np.sin(s) * radius], -1)
    mid = ring * 1.0
    mid[:, 1] = height * 0.55
    pos, nrm, idx = [], [], []
    tip = np.array([0, height, 0], F32)
    bot = np.array([0, -height * 0.18, 0], F32)
    for k in range(facets):
        a, b = k, (k + 1) % facets
        for tri in ((ring[a], ring[b], mid[b]), (ring[a], mid[b], mid[a]),
                    (mid[a], mid[b], tip), (ring[b], ring[a], bot)):
            base = len(pos)
            n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
            ln = np.linalg.norm(n)
            n = n / ln if ln > 1e-6 else np.array([0, 1, 0], F32)
            for pt in tri:
                pos.append(pt)
                nrm.append(n)
            idx += [base, base + 1, base + 2]
    v = _pack(np.array(pos, F32), np.array(nrm, F32))
    parts.append((v, np.array(idx, U32)))
    # 侧生小晶簇
    for k in range(rng.integers(1, 4)):
        ang = rng.uniform(0, 6.28)
        sub = crystal_simple(rng.integers(0, 9999), facets=5,
                             height=height * rng.uniform(0.25, 0.5),
                             radius=radius * rng.uniform(0.3, 0.55))
        parts.append(transform(sub,
                               offset=(math.cos(ang) * radius * 0.8, height * rng.uniform(0.05, 0.3),
                                       math.sin(ang) * radius * 0.8),
                               rot_z=rng.uniform(-0.5, 0.5), rot_x=rng.uniform(-0.5, 0.5)))
    return merge(parts)


def crystal_simple(seed=0, facets=5, height=1.0, radius=0.3):
    s = np.linspace(0, 2 * math.pi, facets + 1)[:-1]
    ring = np.stack([np.cos(s) * radius, np.zeros_like(s), np.sin(s) * radius], -1)
    tip = np.array([0, height, 0], F32)
    pos, nrm, idx = [], [], []
    for k in range(facets):
        a, b = k, (k + 1) % facets
        tri = (ring[a], ring[b], tip)
        base = len(pos)
        n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        ln = np.linalg.norm(n)
        n = n / ln if ln > 1e-6 else np.array([0, 1, 0], F32)
        for pt in tri:
            pos.append(pt)
            nrm.append(n)
        idx += [base, base + 1, base + 2]
    return _pack(np.array(pos, F32), np.array(nrm, F32)), np.array(idx, U32)


def shard(seed=0):
    """不规则薄片碎片。"""
    rng = np.random.default_rng(seed)
    n = rng.integers(4, 7)
    ang = np.sort(rng.uniform(0, 6.28, n))
    rad = rng.uniform(0.4, 1.0, n)
    pts = np.stack([np.cos(ang) * rad, np.zeros(n), np.sin(ang) * rad], -1).astype(F32)
    thick = rng.uniform(0.06, 0.16)
    pos, nrm, idx = [], [], []
    for sgn, ny in ((1, 1.0), (-1, -1.0)):
        base = len(pos)
        pos.append((0, thick * sgn * 0.5, 0))
        nrm.append((0, ny, 0))
        for p in pts:
            pos.append((p[0], thick * sgn * 0.5, p[2]))
            nrm.append((0, ny, 0))
        for i in range(n):
            j = (i + 1) % n
            if ny > 0:
                idx += [base, base + 1 + i, base + 1 + j]
            else:
                idx += [base, base + 1 + j, base + 1 + i]
    # 侧壁
    for i in range(n):
        j = (i + 1) % n
        a, b = pts[i], pts[j]
        base = len(pos)
        e = b - a
        nn = np.array([e[2], 0, -e[0]], F32)
        ln = np.linalg.norm(nn)
        nn = nn / ln if ln > 1e-6 else np.array([1, 0, 0], F32)
        for p, hy in ((a, thick * 0.5), (b, thick * 0.5), (b, -thick * 0.5), (a, -thick * 0.5)):
            pos.append((p[0], hy, p[2]))
            nrm.append(nn)
        idx += [base, base + 1, base + 2, base, base + 2, base + 3]
    return _pack(np.array(pos, F32), np.array(nrm, F32)), np.array(idx, U32)


def recompute_normals(v, i):
    p = v[:, 0:3]
    tri = i.reshape(-1, 3)
    e1 = p[tri[:, 1]] - p[tri[:, 0]]
    e2 = p[tri[:, 2]] - p[tri[:, 0]]
    fn = np.cross(e1, e2)
    n = np.zeros_like(p)
    for k in range(3):
        np.add.at(n, tri[:, k], fn)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n /= np.maximum(ln, 1e-6)
    v = v.copy()
    v[:, 3:6] = n
    return v, i


# --------------------------------------------------------------------------
# 植被 (带 uv)
# --------------------------------------------------------------------------
def grass_blade(segments=4, height=1.0, width=0.09, bend=0.35):
    """输出 float32[N,8]: pos3 + normal3 + uv2。"""
    pos, nrm, uv, idx = [], [], [], []
    for s in range(segments + 1):
        t = s / segments
        y = t * height
        x_off = bend * t * t
        w = width * (1.0 - t * 0.55)
        for side in (-1, 1):
            pos.append((side * w * 0.5 + x_off, y, 0.0))
            nrm.append((0.0, 0.25, 1.0))
            uv.append(((side + 1) * 0.5, t))
    for s in range(segments):
        i0 = s * 2
        idx += [i0, i0 + 1, i0 + 2, i0 + 1, i0 + 3, i0 + 2]
    n = np.array(nrm, F32)
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    v = np.concatenate([np.array(pos, F32), n, np.array(uv, F32)], 1).astype(F32)
    return v, np.array(idx, U32)


def grass_clump(blades=3, seed=0, height=1.0, width=0.09):
    rng = np.random.default_rng(seed)
    vs, ids, off = [], [], 0
    for b in range(blades):
        v, i = grass_blade(4, height * rng.uniform(0.7, 1.25), width, rng.uniform(0.15, 0.55))
        ang = rng.uniform(0, math.pi)
        c, s = math.cos(ang), math.sin(ang)
        R = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], F32)
        v = v.copy()
        v[:, 0:3] = v[:, 0:3] @ R.T
        v[:, 3:6] = v[:, 3:6] @ R.T
        v[:, 0] += rng.uniform(-0.10, 0.10)
        v[:, 2] += rng.uniform(-0.10, 0.10)
        vs.append(v)
        ids.append(i + off)
        off += len(v)
    return np.concatenate(vs, 0).astype(F32), np.concatenate(ids, 0).astype(U32)


# --------------------------------------------------------------------------
# 树 / 枯木
# --------------------------------------------------------------------------
def tree(seed=0, height=6.0, dead=False):
    rng = np.random.default_rng(seed)
    parts = []
    trunk_h = height * rng.uniform(0.55, 0.72)
    parts.append(cylinder(height * 0.055, height * 0.028, trunk_h, 8))
    # 主枝
    nb = int(rng.integers(3, 6))
    for k in range(nb):
        ang = k / nb * 6.28 + rng.uniform(-0.4, 0.4)
        t = rng.uniform(0.55, 0.95)
        bl = height * rng.uniform(0.18, 0.34)
        br = cylinder(height * 0.020, height * 0.008, bl, 6)
        br = transform(br, rot_z=rng.uniform(0.5, 1.05), rot_y=ang)
        parts.append(transform(br, offset=(0, trunk_h * t, 0)))
        if not dead:
            cx = math.cos(ang) * bl * 0.62
            cz = math.sin(ang) * bl * 0.62
            crown = ellipsoid(height * 0.16, height * 0.11, height * 0.16, 7, 10)
            parts.append(transform(crown, offset=(cx, trunk_h * t + bl * 0.68, cz)))
    if not dead:
        crown = ellipsoid(height * 0.24, height * 0.19, height * 0.24, 9, 13)
        parts.append(transform(crown, offset=(0, trunk_h + height * 0.10, 0)))
    return merge(parts)


def monolith(seed=0, height=5.0, width=1.1):
    """黑石 / 石碑: 微微倾斜的不规则柱体。"""
    rng = np.random.default_rng(seed)
    sides = 6
    s = np.linspace(0, 2 * math.pi, sides + 1)[:-1]
    lv = 5
    pos, nrm, idx = [], [], []
    rings = []
    for l in range(lv + 1):
        t = l / lv
        r = width * (1.0 - t * 0.22) * rng.uniform(0.9, 1.1)
        jitter = rng.uniform(0.86, 1.14, sides)
        pts = np.stack([np.cos(s) * r * jitter,
                        np.full(sides, t * height),
                        np.sin(s) * r * jitter], -1).astype(F32)
        pts[:, 0] += t * t * rng.uniform(-0.22, 0.22) * width
        pts[:, 2] += t * t * rng.uniform(-0.22, 0.22) * width
        rings.append(pts)
    for l in range(lv):
        for k in range(sides):
            a, b = k, (k + 1) % sides
            quad = (rings[l][a], rings[l][b], rings[l + 1][b], rings[l + 1][a])
            base = len(pos)
            n = np.cross(quad[1] - quad[0], quad[3] - quad[0])
            ln = np.linalg.norm(n)
            n = n / ln if ln > 1e-6 else np.array([0, 1, 0], F32)
            for pt in quad:
                pos.append(pt)
                nrm.append(n)
            idx += [base, base + 1, base + 2, base, base + 2, base + 3]
    # 顶盖
    base = len(pos)
    top = rings[-1]
    ctr = top.mean(0)
    pos.append(ctr)
    nrm.append((0, 1, 0))
    for p in top:
        pos.append(p)
        nrm.append((0, 1, 0))
    for k in range(sides):
        idx += [base, base + 1 + k, base + 1 + (k + 1) % sides]
    return _pack(np.array(pos, F32), np.array(nrm, F32)), np.array(idx, U32)


# --------------------------------------------------------------------------
# 角色: 7 种形态
# --------------------------------------------------------------------------
def _biped_base(H, rng):
    """人形基础骨架: 腿/躯干/肩/臂/颈/头/口鼻/耳/尾。返回 (parts, head_r, leg_h, torso_h, neck_y)。"""
    parts = []
    leg_h = H * 0.44
    torso_h = H * 0.34
    head_r = H * 0.078
    for sx in (-1, 1):
        parts.append(transform(capsule(H * 0.052, leg_h, 5, 9),
                               offset=(sx * H * 0.065, 0, 0)))
    torso = capsule(H * 0.108, torso_h, 7, 12)
    parts.append(transform(torso, offset=(0, leg_h, 0), scl=(1.15, 1.0, 0.78)))
    # 肩
    parts.append(transform(ellipsoid(H * 0.135, H * 0.055, H * 0.085, 6, 10),
                           offset=(0, leg_h + torso_h * 0.92, 0)))
    for sx in (-1, 1):
        arm = capsule(H * 0.038, H * 0.36, 5, 8)
        arm = transform(arm, rot_z=sx * 0.14, rot_x=0.10)
        parts.append(transform(arm, offset=(sx * H * 0.135, leg_h + torso_h * 0.86 - H * 0.36, 0)))
    neck_y = leg_h + torso_h + H * 0.02
    parts.append(transform(cylinder(H * 0.035, H * 0.032, H * 0.045, 7),
                           offset=(0, neck_y - H * 0.03, 0)))
    head = ellipsoid(head_r, head_r * 1.16, head_r * 1.05, 9, 13)
    parts.append(transform(head, offset=(0, neck_y + head_r * 1.05, 0)))
    # 口鼻 (兽人特征)
    parts.append(transform(ellipsoid(head_r * 0.42, head_r * 0.36, head_r * 0.55, 6, 9),
                           offset=(0, neck_y + head_r * 0.92, -head_r * 0.90)))
    # 耳
    for sx in (-1, 1):
        ear = cone(head_r * 0.34, head_r * 0.80, 7)
        parts.append(transform(ear, offset=(sx * head_r * 0.62, neck_y + head_r * 1.72, 0),
                               rot_z=-sx * 0.28))
    # 尾
    tail = capsule(H * 0.022, H * 0.30, 4, 7)
    parts.append(transform(tail, offset=(0, leg_h + H * 0.06, H * 0.10), rot_x=-1.15))
    return parts, head_r, leg_h, torso_h, neck_y


def character(form="biped", height=1.7, seed=0):
    """生成朝向 -Z 的角色网格, 脚底在 y=0, 总高约 height。

    形态 (人外种族):
        biped     猫兽人 (灰 / 玩家)
        ear       蝠翼族 (耳)      —— 巨型膜耳 + 翼膜披肩
        pen       四臂虫族 (笔)    —— 甲壳背 + 四臂 + 触角
        falsifier 证伪者          —— 面具 + 提灯 + 兜帽
        reptile   爬虫族 (女性)    —— 粗尾 + 头冠鳞
        beast     狼鹿兽人 (渐)    —— 分叉鹿角 + 毛领
        quadruped 狼鹿 (兽人同伴)  —— 四足
        puzzler   拼图者          —— 苍白身形 + 悬浮碎片环
        crystal   晶石族 (回音)
        serpent   龙裔 (锚)
        blob      美西螈
        avian     羽族 (鸟族少年)
        shadow    收束者 / 编年者
    """
    rng = np.random.default_rng(seed)
    H = height
    parts = []

    if form == "biped":
        parts, *_ = _biped_base(H, rng)

    elif form == "ear":
        parts, head_r, leg_h, torso_h, neck_y = _biped_base(H, rng)
        # 巨型膜状耳 (听力): 两片大膜向两侧展开
        for sx in (-1, 1):
            wing = ellipsoid(H * 0.27, H * 0.075, H * 0.15, 7, 9)
            parts.append(transform(wing, offset=(sx * H * 0.26, neck_y + head_r * 1.35, 0),
                                   rot_z=-sx * 0.75, rot_x=sx * 0.35))
            inner = ellipsoid(H * 0.21, H * 0.045, H * 0.10, 6, 8)
            parts.append(transform(inner, offset=(sx * H * 0.30, neck_y + head_r * 1.30, 0),
                                   rot_z=-sx * 0.75, rot_x=sx * 0.35))
        # 翼膜披肩
        for sx in (-1, 1):
            cape = ellipsoid(H * 0.16, H * 0.05, H * 0.11, 6, 8)
            parts.append(transform(cape, offset=(sx * H * 0.22, leg_h + torso_h * 0.85, H * 0.02),
                                   rot_z=-sx * 0.55, rot_x=0.35))

    elif form == "pen":
        parts, head_r, leg_h, torso_h, neck_y = _biped_base(H, rng)
        # 背部甲壳 + 刻痕
        shell = ellipsoid(H * 0.15, H * 0.19, H * 0.085, 8, 10)
        parts.append(transform(shell, offset=(0, leg_h + torso_h * 0.52, -H * 0.045), rot_x=0.35))
        for k in range(3):
            mark = shard(seed * 7 + k)
            parts.append(transform(mark, scl=(H * 0.016, H * 0.016, H * 0.016),
                                   offset=((k - 1) * H * 0.05, leg_h + torso_h * (0.40 + k * 0.12),
                                           -H * 0.11), rot_y=k))
        # 第二对下臂 (四臂)
        for sx in (-1, 1):
            arm2 = capsule(H * 0.030, H * 0.30, 5, 8)
            arm2 = transform(arm2, rot_z=sx * 0.30, rot_x=0.30)
            parts.append(transform(arm2, offset=(sx * H * 0.17, leg_h + torso_h * 0.25, H * 0.02)))
        # 触角
        for sx in (-1, 1):
            ant = cone(H * 0.011, H * 0.10, 5)
            parts.append(transform(ant, offset=(sx * head_r * 0.45, neck_y + head_r * 1.95, 0),
                                   rot_z=-sx * 0.35))

    elif form == "falsifier":
        parts, head_r, leg_h, torso_h, neck_y = _biped_base(H, rng)
        # 兜帽
        hood = cone(H * 0.115, H * 0.17, 8)
        parts.append(transform(hood, offset=(0, neck_y + head_r * 1.15, -H * 0.005),
                               rot_x=0.55))
        # 面具
        mask = ellipsoid(H * 0.055, H * 0.062, H * 0.015, 7, 9)
        parts.append(transform(mask, offset=(0, neck_y + head_r * 1.02, -head_r * 0.95)))
        # 提灯 (右手)
        lamp_handle = capsule(H * 0.009, H * 0.06, 4, 6)
        parts.append(transform(lamp_handle, offset=(H * 0.115, leg_h + torso_h * 0.62, H * 0.02),
                               rot_x=0.6))
        lamp = ellipsoid(H * 0.038, H * 0.05, H * 0.038, 7, 9)
        parts.append(transform(lamp, offset=(H * 0.115, leg_h + torso_h * 0.50, H * 0.05)))

    elif form == "reptile":
        parts, head_r, leg_h, torso_h, neck_y = _biped_base(H, rng)
        # 粗尾
        tail = capsule(H * 0.045, H * 0.34, 5, 9)
        parts.append(transform(tail, offset=(0, H * 0.12, H * 0.12), rot_x=-1.35))
        # 头冠鳞
        for k in range(3):
            crest = cone(head_r * 0.16, H * 0.06, 5)
            parts.append(transform(crest, offset=(0, neck_y + head_r * (1.35 + k * 0.10),
                                                  -head_r * (0.35 - k * 0.28)), rot_x=-0.9))
        # 颈部鳞环
        for k in range(3):
            r0 = H * (0.028 - k * 0.003)
            ring = ellipsoid(r0, r0, H * 0.012, 6, 8)
            parts.append(transform(ring, offset=(0, neck_y - H * (0.01 + k * 0.022), 0)))

    elif form == "beast":
        parts, head_r, leg_h, torso_h, neck_y = _biped_base(H, rng)
        # 分叉鹿角
        for sx in (-1, 1):
            main = cone(H * 0.020, H * 0.22, 6)
            parts.append(transform(main, offset=(sx * head_r * 0.55, neck_y + head_r * 1.90, 0),
                                   rot_z=-sx * 0.40, rot_x=-0.15))
            br1 = cone(H * 0.014, H * 0.13, 6)
            parts.append(transform(br1, offset=(sx * head_r * 0.62, neck_y + head_r * 1.95, 0),
                                   rot_z=-sx * 0.85, rot_x=0.35))
            br2 = cone(H * 0.012, H * 0.10, 6)
            parts.append(transform(br2, offset=(sx * head_r * 0.50, neck_y + head_r * 2.05, 0),
                                   rot_z=-sx * 0.15, rot_x=0.5))
        # 毛领
        for sx in (-1, 1):
            fur = ellipsoid(H * 0.11, H * 0.07, H * 0.06, 6, 8)
            parts.append(transform(fur, offset=(sx * H * 0.12, leg_h + torso_h * 0.90, 0),
                                   rot_z=-sx * 0.5))
        # 粗尾
        tail = capsule(H * 0.036, H * 0.34, 5, 8)
        parts.append(transform(tail, offset=(0, leg_h + H * 0.08, H * 0.11), rot_x=-1.2))

    elif form == "puzzler":
        parts, head_r, leg_h, torso_h, neck_y = _biped_base(H, rng)
        # 环绕躯干的悬浮拼图碎片
        for k in range(5):
            a = k / 5.0 * 6.283 + 0.7
            frag = shard(seed * 17 + k)
            parts.append(transform(frag, scl=(H * 0.030, H * 0.030, H * 0.030),
                                   offset=(math.cos(a) * H * 0.19,
                                           leg_h + torso_h * (0.30 + 0.40 * math.sin(a * 1.7)),
                                           math.sin(a) * H * 0.19),
                                   rot_y=a, rot_x=k * 0.5))
        # 头顶碎块环
        for k in range(6):
            a = k / 6.0 * 6.283
            frag = shard(seed * 31 + k)
            parts.append(transform(frag, scl=(H * 0.016, H * 0.016, H * 0.016),
                                   offset=(math.cos(a) * head_r * 0.9,
                                           neck_y + head_r * 2.35,
                                           math.sin(a) * head_r * 0.9),
                                   rot_y=a, rot_x=1.2))

    elif form == "quadruped":
        body_h = H * 0.58
        for sx in (-1, 1):
            for sz in (-1, 1):
                parts.append(transform(capsule(H * 0.048, body_h, 5, 8),
                                       offset=(sx * H * 0.16, 0, sz * H * 0.30)))
        body = ellipsoid(H * 0.20, H * 0.19, H * 0.44, 9, 13)
        parts.append(transform(body, offset=(0, body_h + H * 0.16, 0)))
        neck = capsule(H * 0.07, H * 0.30, 5, 9)
        parts.append(transform(neck, offset=(0, body_h + H * 0.18, -H * 0.34), rot_x=-0.55))
        head = ellipsoid(H * 0.085, H * 0.082, H * 0.14, 8, 11)
        parts.append(transform(head, offset=(0, body_h + H * 0.42, -H * 0.50)))
        for sx in (-1, 1):
            antler = cone(H * 0.022, H * 0.22, 6)
            parts.append(transform(antler, offset=(sx * H * 0.05, body_h + H * 0.49, -H * 0.46),
                                   rot_z=-sx * 0.42, rot_x=-0.22))
        tail = capsule(H * 0.020, H * 0.24, 4, 7)
        parts.append(transform(tail, offset=(0, body_h + H * 0.24, H * 0.42), rot_x=-2.1))

    elif form == "crystal":
        parts.append(transform(crystal(seed, 6, H * 0.92, H * 0.17), offset=(0, H * 0.04, 0)))
        base = rock(seed + 7, 7, 11, 0.28)
        parts.append(transform(base, scl=(H * 0.22, H * 0.09, H * 0.22), offset=(0, H * 0.05, 0)))
        for k in range(4):
            ang = rng.uniform(0, 6.28)
            r = H * rng.uniform(0.12, 0.22)
            sh = crystal_simple(seed * 13 + k, 5, H * rng.uniform(0.14, 0.30), H * 0.045)
            parts.append(transform(sh, offset=(math.cos(ang) * r, H * rng.uniform(0.30, 0.62),
                                               math.sin(ang) * r),
                                   rot_z=rng.uniform(-0.7, 0.7), rot_x=rng.uniform(-0.7, 0.7)))

    elif form == "blob":
        body = ellipsoid(H * 0.30, H * 0.24, H * 0.42, 11, 15)
        parts.append(transform(body, offset=(0, H * 0.26, 0)))
        head = ellipsoid(H * 0.24, H * 0.21, H * 0.24, 10, 13)
        parts.append(transform(head, offset=(0, H * 0.32, -H * 0.34)))
        # 六鳃
        for sx in (-1, 1):
            for k in range(3):
                g = capsule(H * 0.026, H * 0.20, 4, 7)
                parts.append(transform(g, offset=(sx * H * 0.20, H * 0.36, -H * 0.24 + k * H * 0.055),
                                       rot_z=-sx * 1.15, rot_x=-0.28 + k * 0.28))
        tail = ellipsoid(H * 0.055, H * 0.19, H * 0.30, 7, 9)
        parts.append(transform(tail, offset=(0, H * 0.26, H * 0.44)))
        for sx in (-1, 1):
            for sz in (-1, 1):
                parts.append(transform(capsule(H * 0.032, H * 0.14, 4, 7),
                                       offset=(sx * H * 0.22, 0, sz * H * 0.22),
                                       rot_z=-sx * 0.9))

    elif form == "avian":
        leg_h = H * 0.34
        for sx in (-1, 1):
            parts.append(transform(cylinder(H * 0.020, H * 0.016, leg_h, 6),
                                   offset=(sx * H * 0.055, 0, 0)))
        body = ellipsoid(H * 0.13, H * 0.17, H * 0.15, 9, 13)
        parts.append(transform(body, offset=(0, leg_h + H * 0.16, 0)))
        neck = capsule(H * 0.045, H * 0.16, 4, 8)
        parts.append(transform(neck, offset=(0, leg_h + H * 0.26, -H * 0.03), rot_x=-0.18))
        head = ellipsoid(H * 0.072, H * 0.075, H * 0.082, 8, 11)
        parts.append(transform(head, offset=(0, leg_h + H * 0.46, -H * 0.04)))
        beak = cone(H * 0.030, H * 0.11, 6)
        parts.append(transform(beak, offset=(0, leg_h + H * 0.45, -H * 0.10), rot_x=-1.57))
        # 翼: 三层羽片
        for sx in (-1, 1):
            for k in range(3):
                w = ellipsoid(H * 0.020, H * 0.035, H * 0.19, 5, 8)
                parts.append(transform(w, offset=(sx * (H * 0.13 + k * H * 0.045),
                                                  leg_h + H * 0.22 - k * H * 0.02,
                                                  k * H * 0.02),
                                       rot_z=-sx * (0.30 + k * 0.16)))
        for k in range(3):
            t = ellipsoid(H * 0.030, H * 0.014, H * 0.16, 5, 8)
            parts.append(transform(t, offset=((k - 1) * H * 0.035, leg_h + H * 0.12, H * 0.20),
                                   rot_z=(k - 1) * 0.20))

    elif form == "serpent":
        # 龙裔: 长躯干盘绕, 头部低垂 (背对观者的姿态)
        segs = 12
        for k in range(segs):
            t = k / (segs - 1)
            ang = t * 3.6
            r = H * (0.34 - t * 0.16)
            y = H * (0.16 + t * 0.52)
            rad = H * (0.115 - t * 0.058)
            seg = ellipsoid(rad, rad * 0.86, rad * 1.35, 6, 9)
            parts.append(transform(seg, offset=(math.cos(ang) * r, y, math.sin(ang) * r),
                                   rot_y=-ang))
        head = ellipsoid(H * 0.072, H * 0.062, H * 0.12, 8, 11)
        hy = H * 0.70
        parts.append(transform(head, offset=(0, hy, H * 0.16), rot_x=0.30))
        for sx in (-1, 1):
            horn = cone(H * 0.018, H * 0.15, 6)
            parts.append(transform(horn, offset=(sx * H * 0.035, hy + H * 0.04, H * 0.19),
                                   rot_x=1.05, rot_z=-sx * 0.25))
        # 残翼
        for sx in (-1, 1):
            w = ellipsoid(H * 0.016, H * 0.13, H * 0.10, 5, 8)
            parts.append(transform(w, offset=(sx * H * 0.14, H * 0.50, H * 0.02), rot_z=-sx * 0.55))

    elif form == "shadow":
        # 收束者 / 编年者: 无实体的高耸剪影
        segs = 7
        for k in range(segs):
            t = k / (segs - 1)
            r = H * (0.20 - t * 0.13) * (1.0 + 0.18 * math.sin(t * 9.0 + seed))
            seg = ellipsoid(r, H * 0.11, r * 0.82, 7, 11)
            parts.append(transform(seg, offset=(math.sin(t * 4.2 + seed) * H * 0.035,
                                                H * (0.06 + t * 0.80), 0)))
        hood = ellipsoid(H * 0.085, H * 0.11, H * 0.085, 9, 12)
        parts.append(transform(hood, offset=(0, H * 0.90, 0)))
        # 悬浮碎屑环
        for k in range(9):
            a = k / 9 * 6.28
            r = H * 0.26
            parts.append(transform(shard(seed * 31 + k),
                                   scl=(H * 0.045, H * 0.045, H * 0.045),
                                   offset=(math.cos(a) * r, H * (0.40 + 0.30 * math.sin(a * 2.3)),
                                           math.sin(a) * r),
                                   rot_y=a, rot_x=k * 0.4))
    else:
        parts.append(capsule(H * 0.18, H, 8, 12))

    return merge(parts)


# --------------------------------------------------------------------------
# 交互物
# --------------------------------------------------------------------------
def interactable_mesh(kind, seed=0):
    if kind == "scroll":
        parts = [transform(cylinder(0.055, 0.055, 0.86, 10), rot_z=1.5708, offset=(0, 0.06, 0))]
        sheet = box(0.62, 0.012, 0.46)
        parts.append(transform(sheet, offset=(0.30, 0.10, 0), rot_z=-0.12))
        parts.append(transform(box(0.50, 0.010, 0.40), offset=(0.66, 0.16, 0.06), rot_z=-0.22, rot_y=0.3))
        return merge(parts)
    if kind == "monolith":
        return monolith(seed, 4.6, 0.95)
    if kind == "pillar":
        parts = [cylinder(0.42, 0.34, 3.4, 14)]
        parts.append(transform(torus(0.44, 0.05, 20, 8), offset=(0, 0.55, 0)))
        parts.append(transform(torus(0.40, 0.05, 20, 8), offset=(0, 2.30, 0)))
        parts.append(transform(cylinder(0.50, 0.44, 0.16, 14), offset=(0, 0, 0)))
        parts.append(transform(ellipsoid(0.30, 0.24, 0.30, 8, 12), offset=(0, 3.45, 0)))
        return merge(parts)
    if kind == "crystal":
        return crystal(seed, 6, 2.1, 0.42)
    if kind == "mirror":
        parts = [transform(box(2.0, 3.1, 0.10), offset=(0, 1.75, 0))]
        parts.append(transform(torus(1.12, 0.07, 26, 9), offset=(0, 1.75, -0.06), rot_x=1.5708))
        parts.append(transform(box(2.3, 0.18, 0.5), offset=(0, 0.09, 0)))
        return merge(parts)
    if kind == "trace":
        # 地面上的一道纹路: 若干扁平弧段
        parts = []
        rng = np.random.default_rng(seed)
        for k in range(9):
            t = k / 8
            parts.append(transform(box(0.9, 0.035, 0.16),
                                   offset=(math.sin(t * 4.2) * 1.5, 0.02, t * 5.0 - 2.5),
                                   rot_y=math.cos(t * 4.2) * 0.7))
        return merge(parts)
    if kind == "shard":
        parts = []
        rng = np.random.default_rng(seed)
        for k in range(14):
            a = rng.uniform(0, 6.28)
            r = rng.uniform(0.0, 0.85)
            parts.append(transform(shard(seed * 17 + k),
                                   scl=rng.uniform(0.22, 0.46),
                                   offset=(math.cos(a) * r, rng.uniform(0.02, 0.42), math.sin(a) * r),
                                   rot_y=rng.uniform(0, 6.28), rot_x=rng.uniform(-1.1, 1.1),
                                   rot_z=rng.uniform(-1.1, 1.1)))
        return merge(parts)
    return rock(seed)


def collectible_mesh():
    """心跳残片: 悬浮的双层多面体。"""
    parts = [transform(crystal_simple(3, 6, 0.34, 0.16), offset=(0, 0.0, 0))]
    parts.append(transform(crystal_simple(5, 6, 0.34, 0.16), offset=(0, 0.0, 0), rot_x=math.pi))
    parts.append(transform(torus(0.30, 0.022, 20, 7), offset=(0, 0, 0), rot_x=0.5))
    return merge(parts)


# --------------------------------------------------------------------------
# 场景建筑 (程序化, 供 Scatter 散布)
# --------------------------------------------------------------------------
def ruin(seed=0, scale=1.0):
    """残破石墙: 断柱 + 斜横梁 + 碎石堆。"""
    rng = np.random.default_rng(seed)
    parts = []
    for k in range(3):
        h = scale * rng.uniform(1.2, 2.6)
        c = cylinder(scale * rng.uniform(0.16, 0.22), scale * rng.uniform(0.10, 0.18), h, 8)
        parts.append(transform(c, offset=(scale * (k - 1) * 0.55, h * 0.5, 0),
                               rot_z=rng.uniform(-0.16, 0.16), rot_x=rng.uniform(-0.12, 0.12)))
    beam = box(scale * 1.6, scale * 0.16, scale * 0.16)
    parts.append(transform(beam, offset=(0, scale * rng.uniform(1.6, 2.3), 0),
                           rot_z=rng.uniform(-0.06, 0.06), rot_y=rng.uniform(-0.1, 0.1)))
    for k in range(4):
        b = box(scale * rng.uniform(0.20, 0.50), scale * rng.uniform(0.15, 0.30),
                scale * rng.uniform(0.20, 0.50))
        parts.append(transform(b, offset=(rng.uniform(-0.6, 0.6) * scale,
                                          scale * rng.uniform(0.12, 0.28),
                                          rng.uniform(-0.4, 0.4) * scale),
                               rot_y=rng.random() * 6.28))
    return merge(parts)


def arch(seed=0, scale=1.0):
    """拱门: 双柱 + 弧形顶。"""
    rng = np.random.default_rng(seed)
    parts = []
    h = scale * 2.5
    for sx in (-1, 1):
        c = cylinder(scale * 0.16, scale * 0.13, h, 10)
        parts.append(transform(c, offset=(sx * scale * 0.80, h * 0.5, 0),
                               rot_z=sx * rng.uniform(-0.05, 0.05)))
    # 弧形顶: 一排拱石
    for k in range(9):
        a = math.pi * k / 8.0
        x = math.cos(a) * scale * 0.80
        y = h + math.sin(a) * scale * 0.30
        stone = ellipsoid(scale * 0.16, scale * 0.13, scale * 0.16, 6, 8)
        parts.append(transform(stone, offset=(x, y, 0)))
    return merge(parts)


def pillar(seed=0, scale=1.0):
    """高柱: 底座 + 柱身 + 顶冠。"""
    rng = np.random.default_rng(seed)
    parts = []
    h = scale * 3.4
    parts.append(transform(box(scale * 0.9, scale * 0.28, scale * 0.9), offset=(0, scale * 0.14, 0)))
    c = cylinder(scale * 0.20, scale * 0.17, h, 10)
    parts.append(transform(c, offset=(0, scale * 0.28 + h * 0.5, 0),
                           rot_z=rng.uniform(-0.05, 0.05)))
    parts.append(transform(ellipsoid(scale * 0.30, scale * 0.22, scale * 0.30, 7, 9),
                           offset=(0, scale * 0.28 + h + scale * 0.22, 0)))
    return merge(parts)


def hut(seed=0, scale=1.0):
    """低矮圆顶小屋: 石壁 + 草顶 + 门口光石。"""
    rng = np.random.default_rng(seed)
    parts = []
    h = scale * 1.15
    wall = cylinder(scale * 0.55, scale * 0.62, h, 10)
    parts.append(transform(wall, offset=(0, h * 0.5, 0)))
    roof = cone(scale * 0.78, scale * 0.72, 10)
    parts.append(transform(roof, offset=(0, h + scale * 0.36, 0)))
    # 门口 (两根矮柱示意)
    for sx in (-1, 1):
        parts.append(transform(cylinder(scale * 0.05, scale * 0.05, scale * 0.7, 6),
                               offset=(sx * scale * 0.20, scale * 0.35, scale * 0.62)))
    # 顶部光石 (由实例 glow 染色)
    parts.append(transform(crystal_simple(seed % 97, 5, scale * 0.16, scale * 0.06),
                           offset=(0, h + scale * 0.74, 0)))
    return merge(parts)


def campfire(seed=0, scale=1.0):
    """篝火: 石圈 + 柴薪 + 火焰。"""
    rng = np.random.default_rng(seed)
    parts = []
    for k in range(6):
        a = k / 6 * math.tau + 0.3
        st = rock(seed * 3 + k, 6, 9, 0.4)
        parts.append(transform(st, scl=(scale * 0.16, scale * 0.11, scale * 0.16),
                               offset=(math.cos(a) * scale * 0.30, 0,
                                       math.sin(a) * scale * 0.30)))
    for k in range(3):
        log = cylinder(scale * 0.045, scale * 0.045, scale * 0.5, 6)
        parts.append(transform(log, offset=(0, scale * 0.12, 0), rot_y=k * 0.9,
                               rot_x=1.35))
    for k in range(3):
        fl = cone(scale * (0.16 - k * 0.04), scale * (0.34 + k * 0.16), 7)
        parts.append(transform(fl, offset=(0, scale * (0.16 + k * 0.14), 0),
                               rot_y=k * 2.1))
    return merge(parts)


def altar(seed=0, scale=1.0):
    """祭坛: 三层方台 + 顶部光石。"""
    rng = np.random.default_rng(seed)
    parts = []
    for k, (w, h) in enumerate(((1.0, 0.22), (0.72, 0.20), (0.46, 0.20))):
        parts.append(transform(box(scale * w, scale * h, scale * w),
                               offset=(0, scale * (0.11 + k * 0.20), 0)))
    parts.append(transform(crystal_simple(seed % 97, 6, scale * 0.22, scale * 0.09),
                           offset=(0, scale * 0.86, 0)))
    return merge(parts)


def signpost(seed=0, scale=1.0):
    """路标: 木杆 + 指向木板。"""
    rng = np.random.default_rng(seed)
    parts = []
    pole = cylinder(scale * 0.05, scale * 0.05, scale * 1.5, 7)
    parts.append(transform(pole, offset=(0, scale * 0.75, 0)))
    for k, rot in ((0, 0.35), (1, -0.5)):
        b = box(scale * 0.62, scale * 0.10, scale * 0.03)
        parts.append(transform(b, offset=(math.cos(rot) * scale * 0.28,
                                          scale * (1.02 + k * 0.20),
                                          math.sin(rot) * scale * 0.28),
                               rot_y=rot))
    return merge(parts)


def tower(seed=0, scale=1.0):
    """瞭望塔: 高柱 + 平台 + 锥顶。"""
    rng = np.random.default_rng(seed)
    parts = []
    h = scale * 3.6
    body = cylinder(scale * 0.30, scale * 0.22, h, 10)
    parts.append(transform(body, offset=(0, scale * 0.2 + h * 0.5, 0)))
    plat = cylinder(scale * 0.42, scale * 0.42, scale * 0.14, 10)
    parts.append(transform(plat, offset=(0, scale * 0.2 + h, 0)))
    roof = cone(scale * 0.40, scale * 0.62, 10)
    parts.append(transform(roof, offset=(0, scale * 0.2 + h + scale * 0.31, 0)))
    for k in range(3):
        parts.append(transform(crystal_simple(seed + k, 5, scale * 0.08, scale * 0.03),
                               offset=(math.cos(k * 2.1) * scale * 0.25,
                                       scale * (0.8 + k * 0.9), math.sin(k * 2.1) * scale * 0.25)))
    return merge(parts)


def stonecircle(seed=0, scale=1.0):
    """石圈: 一圈竖立的巨石 + 中央祭石。"""
    rng = np.random.default_rng(seed)
    parts = []
    n = 9
    for k in range(n):
        a = k / n * math.tau + 0.4
        h = scale * rng.uniform(1.0, 1.7)
        w = scale * rng.uniform(0.22, 0.32)
        st = rock(seed * 5 + k, 7, 9, 0.3)
        parts.append(transform(st, scl=(w, h * 0.7, w),
                               offset=(math.cos(a) * scale * 1.35, h * 0.35,
                                       math.sin(a) * scale * 1.35),
                               rot_y=a))
    parts.append(transform(box(scale * 0.5, scale * 0.24, scale * 0.5),
                           offset=(0, scale * 0.12, 0)))
    return merge(parts)


def portal(seed=0, scale=1.0):
    """传送门: 双柱拱门 + 中心发光柱 + 旋转光圈。"""
    rng = np.random.default_rng(seed)
    parts = []
    h = scale * 2.6
    w = scale * 1.4
    for sx in (-1, 1):
        parts.append(transform(cylinder(scale * 0.12, scale * 0.10, h, 10),
                               offset=(sx * w * 0.55, h * 0.5, 0)))
    for k in range(7):
        a = math.pi * k / 6
        stone = ellipsoid(scale * 0.15, scale * 0.12, scale * 0.15, 6, 8)
        parts.append(transform(stone,
                               offset=(math.cos(a) * w * 0.55, h + math.sin(a) * scale * 0.4, 0)))
    for k in range(3):
        ring = torus(scale * (0.45 - k * 0.12), scale * 0.04, 18, 6)
        parts.append(transform(ring, offset=(0, h * 0.55 + k * scale * 0.18, 0),
                               rot_z=rng.uniform(0, math.tau)))
    parts.append(transform(box(scale * 1.6, scale * 0.16, scale * 1.0),
                           offset=(0, scale * 0.08, 0)))
    parts.append(transform(crystal_simple(seed % 97, 5, scale * 0.22, scale * 0.08),
                           offset=(0, h * 0.55, 0)))
    return merge(parts)

