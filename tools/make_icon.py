"""
make_icon.py -- 程序化生成《远行假设》图标 assets/icon.ico

图形语义: 深色底 + 一枚"被看见的眼" —— 竖瞳(人外) 落在 一圈回响涟漪 中。
不依赖任何外部素材, 纯 PIL 绘制, 输出多尺寸 ico。
"""
from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "icon.ico")
SIZES = [16, 24, 32, 48, 64, 128, 256]
S = 512


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def build():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 圆角底: 由深墨蓝到微紫的对角渐变
    bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg)
    c0, c1 = (12, 16, 26), (38, 30, 58)
    for y in range(S):
        for_t = y / (S - 1)
        bd.line([(0, y), (S, y)], fill=lerp(c0, c1, for_t) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255)
    img.paste(bg, (0, 0), mask)

    # 回响涟漪
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx = cy = S / 2
    for i, r in enumerate((S * 0.42, S * 0.34, S * 0.26)):
        a = 42 + i * 26
        gd.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(120, 200, 235, a),
                   width=max(2, int(S * 0.010)))
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.012))
    img.alpha_composite(glow)

    # 眼形: 两段圆弧夹成的杏仁
    w, h = S * 0.40, S * 0.20
    pts_top, pts_bot = [], []
    for i in range(81):
        t = i / 80.0
        x = cx - w + 2 * w * t
        k = math.sin(math.pi * t)
        pts_top.append((x, cy - h * k))
        pts_bot.append((x, cy + h * k))
    eye = pts_top + pts_bot[::-1]

    eyelayer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ed = ImageDraw.Draw(eyelayer)
    ed.polygon(eye, fill=(228, 236, 244, 250))
    # 虹膜
    ir = S * 0.115
    ed.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=(96, 176, 208, 255))
    ed.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], outline=(38, 82, 104, 255),
               width=max(2, int(S * 0.008)))
    # 竖瞳 —— 人外的记号
    pw, ph = S * 0.030, S * 0.108
    ed.ellipse([cx - pw, cy - ph, cx + pw, cy + ph], fill=(14, 16, 22, 255))
    # 高光
    ed.ellipse([cx + ir * 0.18, cy - ir * 0.62, cx + ir * 0.58, cy - ir * 0.22],
               fill=(255, 255, 255, 215))
    # 眼廓
    ed.line(eye + [eye[0]], fill=(216, 228, 240, 255), width=max(2, int(S * 0.012)),
            joint="curve")
    img.alpha_composite(eyelayer)

    # 上方一道裂痕: 镜子
    cd = ImageDraw.Draw(img)
    cd.line([(cx - S * 0.16, cy - S * 0.30), (cx + S * 0.02, cy - S * 0.20),
             (cx - S * 0.06, cy - S * 0.12)],
            fill=(198, 214, 236, 120), width=max(2, int(S * 0.010)), joint="curve")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT, sizes=[(s, s) for s in SIZES])
    img.resize((256, 256), Image.LANCZOS).save(
        os.path.join(ROOT, "assets", "icon.png"))
    print("[icon]", OUT)


if __name__ == "__main__":
    build()
