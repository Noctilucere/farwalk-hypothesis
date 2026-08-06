"""生成真实感平铺贴图 (砖/石/木/石板) 到 assets/textures/。

算法: 每类贴图用程序化图案 + 多频噪声 + 光照凹凸, 生成 512x512 可平铺纹理。
运行: python tools/gen_textures.py
"""
import os
import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "textures")
SIZE = 512


def _fbm(x, y, octaves=5):
    """简易可平铺值噪声 (hash 采样 + 双线性)。"""
    total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
    for _ in range(octaves):
        total += _smooth_noise(x * freq, y * freq) * amp
        norm += amp
        amp *= 0.5
        freq *= 2.0
    return total / norm


def _hash(ix, iy):
    n = ix * 374761393 + iy * 668265263
    n = (n ^ (n >> 13)) * 1274126177
    return ((n ^ (n >> 16)) & 0xFFFFFFFF) / 0xFFFFFFFF


def _smooth_noise(x, y):
    ix, iy = int(np.floor(x)), int(np.floor(y))
    fx, fy = x - ix, y - iy
    ux = fx * fx * (3 - 2 * fx)
    uy = fy * fy * (3 - 2 * fy)
    v00 = _hash(ix, iy)
    v10 = _hash(ix + 1, iy)
    v01 = _hash(ix, iy + 1)
    v11 = _hash(ix + 1, iy + 1)
    a = v00 + (v10 - v00) * ux
    b = v01 + (v11 - v01) * ux
    return a + (b - a) * uy


def _tile_xy(i, j):
    """将 (i,j) 映射为可平铺输入坐标: 用 sin/cos 包装。"""
    return (np.sin(i * 0.628) * 1.6, np.sin(j * 0.628) * 1.6)


def brick_tile():
    a = np.zeros((SIZE, SIZE, 3), np.float32)
    for y in range(SIZE):
        for x in range(SIZE):
            # 砖格: 行高 64px, 每行错位半砖
            row = y // 64
            yy = y % 64
            xx = (x + (32 if row % 2 else 0)) % SIZE
            col = xx // 96
            xxc = xx % 96
            # 缝
            mortar = (yy < 6) or (xxc < 5)
            base = np.array([0.55, 0.26, 0.16]) if not mortar else np.array([0.28, 0.24, 0.20])
            n = _smooth_noise(x * 0.06, y * 0.06)
            n2 = _smooth_noise(x * 0.9, y * 0.9)
            base *= 0.82 + 0.30 * n + 0.10 * n2
            if not mortar:
                # 砖面斜光
                base *= 0.92 + (yy / 64) * 0.16
            a[y, x] = base
    return a


def stone_tile():
    a = np.zeros((SIZE, SIZE, 3), np.float32)
    # 随机石块: 直径 ~80px 的六边形排列
    rng = np.random.default_rng(7)
    for y in range(SIZE):
        for x in range(SIZE):
            n = _smooth_noise(x * 0.05, y * 0.05)
            n2 = _smooth_noise(x * 0.45, y * 0.45)
            base = np.array([0.45, 0.44, 0.42]) * (0.80 + 0.32 * n + 0.08 * n2)
            # 石缝: 距离网格点近的变暗
            gx, gy = x % 96, y % 96
            d = min(gx, 96 - gx, gy, 96 - gy)
            if d < 7:
                base *= 0.45
            a[y, x] = base
    return a


def plank_tile():
    a = np.zeros((SIZE, SIZE, 3), np.float32)
    for y in range(SIZE):
        board = y // 64
        by = y % 64
        for x in range(SIZE):
            # 板缝 + 木纹
            groove = (by < 5)
            grain = _smooth_noise(x * 0.35, y * 0.10)
            base = np.array([0.52, 0.36, 0.20]) * (0.78 + 0.30 * grain)
            if groove:
                base *= 0.4
            a[y, x] = base
    return a


def slab_tile():
    a = np.zeros((SIZE, SIZE, 3), np.float32)
    for y in range(SIZE):
        for x in range(SIZE):
            n = _smooth_noise(x * 0.08, y * 0.08)
            n2 = _smooth_noise(x * 0.5, y * 0.5)
            base = np.array([0.52, 0.50, 0.47]) * (0.82 + 0.28 * n + 0.06 * n2)
            # 大石板缝
            gx, gy = x % 160, y % 160
            d = min(gx, 160 - gx, gy, 160 - gy)
            if d < 6:
                base *= 0.5
            a[y, x] = base
    return a


def main():
    os.makedirs(OUT, exist_ok=True)
    gens = {
        "brick": brick_tile,
        "stone": stone_tile,
        "plank": plank_tile,
        "slab": slab_tile,
    }
    for name, fn in gens.items():
        a = fn()
        a = np.clip(a * 255.0, 0, 255).astype(np.uint8)
        im = Image.fromarray(a, "RGB")
        # 轻微模糊降噪, 更接近照片
        im = im.filter(ImageFilter.GaussianBlur(0.6))
        p = os.path.join(OUT, f"{name}.png")
        im.save(p)
        print(f"[ok] {name} -> {p} ({os.path.getsize(p)//1024} KB)")


if __name__ == "__main__":
    main()
