"""
math3d.py -- 轻量 3D 数学库

《远行假设 · 谁》自研引擎的数学基础层。
全部基于 numpy float32，矩阵采用列主序（OpenGL 约定），
即 M @ v 形式做变换，上传 GL 时使用 .T.tobytes() 或 bytes(M.T)。

约定:
  - 右手坐标系, +Y 向上, -Z 为相机前方
  - 角度单位统一为弧度, 对外接口若用角度会显式标注 _deg
"""
from __future__ import annotations

import math

import numpy as np

F32 = np.float32


# --------------------------------------------------------------------------
# 向量
# --------------------------------------------------------------------------
def vec3(x=0.0, y=0.0, z=0.0) -> np.ndarray:
    return np.array([x, y, z], dtype=F32)


def vec4(x=0.0, y=0.0, z=0.0, w=1.0) -> np.ndarray:
    return np.array([x, y, z, w], dtype=F32)


def normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n < 1e-9:
        return np.zeros_like(v, dtype=F32)
    return (v / n).astype(F32)


def length(v: np.ndarray) -> float:
    return float(np.linalg.norm(v))


def length2(v: np.ndarray) -> float:
    return float(np.dot(v, v))


def cross(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.cross(a, b).astype(F32)


def dot(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def lerp(a, b, t):
    return a + (b - a) * t


def clamp(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


def smoothstep(e0, e1, x):
    t = clamp((x - e0) / (e1 - e0 + 1e-9), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def damp(current, target, smoothing, dt):
    """帧率无关的指数插值。smoothing 越小收敛越快。"""
    return lerp(current, target, 1.0 - math.pow(smoothing, dt))


def move_towards(current, target, max_delta):
    d = target - current
    if abs(d) <= max_delta:
        return target
    return current + math.copysign(max_delta, d)


def angle_lerp(a, b, t):
    """角度插值, 处理 -pi..pi 环绕。"""
    d = (b - a + math.pi) % (2 * math.pi) - math.pi
    return a + d * t


# --------------------------------------------------------------------------
# 矩阵
# --------------------------------------------------------------------------
def identity() -> np.ndarray:
    return np.identity(4, dtype=F32)


def translate(x, y, z) -> np.ndarray:
    m = identity()
    m[0, 3] = x
    m[1, 3] = y
    m[2, 3] = z
    return m


def scale(x, y=None, z=None) -> np.ndarray:
    if y is None:
        y = z = x
    m = identity()
    m[0, 0] = x
    m[1, 1] = y
    m[2, 2] = z
    return m


def rotate_x(a) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    m = identity()
    m[1, 1], m[1, 2] = c, -s
    m[2, 1], m[2, 2] = s, c
    return m


def rotate_y(a) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    m = identity()
    m[0, 0], m[0, 2] = c, s
    m[2, 0], m[2, 2] = -s, c
    return m


def rotate_z(a) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    m = identity()
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    return m


def compose_trs(pos, rot_y=0.0, scl=1.0) -> np.ndarray:
    """最常用的 平移*绕Y旋转*缩放 组合, 避免通用矩阵乘的开销。"""
    c, s = math.cos(rot_y), math.sin(rot_y)
    if np.isscalar(scl):
        sx = sy = sz = float(scl)
    else:
        sx, sy, sz = float(scl[0]), float(scl[1]), float(scl[2])
    m = np.zeros((4, 4), dtype=F32)
    m[0, 0] = c * sx
    m[0, 2] = s * sz
    m[1, 1] = sy
    m[2, 0] = -s * sx
    m[2, 2] = c * sz
    m[0, 3] = pos[0]
    m[1, 3] = pos[1]
    m[2, 3] = pos[2]
    m[3, 3] = 1.0
    return m


def perspective(fovy_deg, aspect, znear, zfar) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fovy_deg) * 0.5)
    m = np.zeros((4, 4), dtype=F32)
    m[0, 0] = f / max(aspect, 1e-6)
    m[1, 1] = f
    m[2, 2] = (zfar + znear) / (znear - zfar)
    m[2, 3] = (2.0 * zfar * znear) / (znear - zfar)
    m[3, 2] = -1.0
    return m


def ortho(left, right, bottom, top, znear, zfar) -> np.ndarray:
    m = identity()
    m[0, 0] = 2.0 / (right - left)
    m[1, 1] = 2.0 / (top - bottom)
    m[2, 2] = -2.0 / (zfar - znear)
    m[0, 3] = -(right + left) / (right - left)
    m[1, 3] = -(top + bottom) / (top - bottom)
    m[2, 3] = -(zfar + znear) / (zfar - znear)
    return m


def look_at(eye, target, up=None) -> np.ndarray:
    if up is None:
        up = vec3(0, 1, 0)
    eye = np.asarray(eye, dtype=F32)
    target = np.asarray(target, dtype=F32)
    f = normalize(target - eye)
    # 前向与 up 平行时换一个 up, 防止叉乘退化
    if abs(dot(f, normalize(up))) > 0.9995:
        up = vec3(0, 0, 1) if abs(f[1]) > 0.9 else vec3(0, 1, 0)
    s = normalize(cross(f, up))
    u = cross(s, f)
    m = identity()
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -dot(s, eye)
    m[1, 3] = -dot(u, eye)
    m[2, 3] = dot(f, eye)
    return m


def mat_bytes(m: np.ndarray) -> bytes:
    """转成 GL 需要的列主序字节流。"""
    return np.ascontiguousarray(m.T, dtype=F32).tobytes()


def inverse(m: np.ndarray) -> np.ndarray:
    return np.linalg.inv(m).astype(F32)


def transform_point(m: np.ndarray, p) -> np.ndarray:
    v = np.array([p[0], p[1], p[2], 1.0], dtype=F32)
    r = m @ v
    if abs(r[3]) > 1e-9:
        r = r / r[3]
    return r[:3].astype(F32)


def transform_dir(m: np.ndarray, d) -> np.ndarray:
    v = np.array([d[0], d[1], d[2], 0.0], dtype=F32)
    return (m @ v)[:3].astype(F32)


# --------------------------------------------------------------------------
# 视锥剔除
# --------------------------------------------------------------------------
class Frustum:
    """从 view-projection 矩阵提取 6 个裁剪平面, 做包围球剔除。"""

    __slots__ = ("planes",)

    def __init__(self, viewproj: np.ndarray):
        m = viewproj
        rows = []
        # left, right, bottom, top, near, far
        rows.append(m[3] + m[0])
        rows.append(m[3] - m[0])
        rows.append(m[3] + m[1])
        rows.append(m[3] - m[1])
        rows.append(m[3] + m[2])
        rows.append(m[3] - m[2])
        planes = np.array(rows, dtype=F32)
        norms = np.linalg.norm(planes[:, :3], axis=1, keepdims=True)
        norms[norms < 1e-9] = 1.0
        self.planes = (planes / norms).astype(F32)

    def sphere_visible(self, center, radius: float) -> bool:
        p = self.planes
        d = p[:, 0] * center[0] + p[:, 1] * center[1] + p[:, 2] * center[2] + p[:, 3]
        return bool(np.all(d >= -radius))

    def spheres_visible(self, centers: np.ndarray, radius: float) -> np.ndarray:
        """批量剔除, centers 形状 (N,3), 返回 bool 掩码。"""
        p = self.planes
        d = centers @ p[:, :3].T + p[:, 3]
        return np.all(d >= -radius, axis=1)


# --------------------------------------------------------------------------
# 噪声 (地形/植被分布共用)
# --------------------------------------------------------------------------
_PERM_SEED = 1337


def _build_perm(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    p = np.arange(256, dtype=np.int32)
    rng.shuffle(p)
    return np.concatenate([p, p]).astype(np.int32)


_PERM = _build_perm(_PERM_SEED)


def _fade(t):
    return t * t * t * (t * (t * 6 - 15) + 10)


def perlin2(x: np.ndarray, y: np.ndarray, perm: np.ndarray | None = None) -> np.ndarray:
    """向量化 2D Perlin 噪声, 返回大致 [-1,1]。"""
    if perm is None:
        perm = _PERM
    xi = np.floor(x).astype(np.int32) & 255
    yi = np.floor(y).astype(np.int32) & 255
    xf = x - np.floor(x)
    yf = y - np.floor(y)
    u = _fade(xf)
    v = _fade(yf)

    aa = perm[perm[xi] + yi]
    ab = perm[perm[xi] + yi + 1]
    ba = perm[perm[xi + 1] + yi]
    bb = perm[perm[xi + 1] + yi + 1]

    def grad(h, dx, dy):
        h = h & 7
        gx = np.where(h < 4, dx, dy)
        gy = np.where(h < 4, dy, dx)
        sx = np.where((h & 1) == 0, 1.0, -1.0)
        sy = np.where((h & 2) == 0, 1.0, -1.0)
        return gx * sx + gy * sy

    x1 = lerp(grad(aa, xf, yf), grad(ba, xf - 1, yf), u)
    x2 = lerp(grad(ab, xf, yf - 1), grad(bb, xf - 1, yf - 1), u)
    return lerp(x1, x2, v).astype(F32)


def fbm2(x, y, octaves=5, lacunarity=2.0, gain=0.5, perm=None) -> np.ndarray:
    """分形布朗运动, 地形主体。"""
    total = np.zeros_like(np.asarray(x, dtype=F32))
    amp = 1.0
    freq = 1.0
    norm = 0.0
    for _ in range(octaves):
        total = total + perlin2(x * freq, y * freq, perm) * amp
        norm += amp
        amp *= gain
        freq *= lacunarity
    return (total / max(norm, 1e-6)).astype(F32)


def ridged2(x, y, octaves=5, lacunarity=2.0, gain=0.5, perm=None) -> np.ndarray:
    """脊状噪声, 用于山脊线。"""
    total = np.zeros_like(np.asarray(x, dtype=F32))
    amp = 1.0
    freq = 1.0
    norm = 0.0
    for _ in range(octaves):
        n = 1.0 - np.abs(perlin2(x * freq, y * freq, perm))
        total = total + (n * n) * amp
        norm += amp
        amp *= gain
        freq *= lacunarity
    return (total / max(norm, 1e-6)).astype(F32)
