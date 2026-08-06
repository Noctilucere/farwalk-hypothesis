"""
skin.py -- 程序化骨架绑定 (LBS 蒙皮, GPU 姿势旋转)

为外部 AI 生成的静态 glb 角色模型生成简化人体骨架 (8 关节),
按顶点到关节的距离分配最近 2 个关节的权重, 输出扩展顶点格式:

    pos3 + nrm3 + j0,w0,j1,w1   (10 floats)

渲染时每个顶点受 <=2 个关节的"姿势旋转"影响:
    v' = w0 * R_{j0}(v) + w1 * R_{j1}(v)
其中 R_j(v) = T(origin_j) * Rot_j * T(-origin_j) * v  (绕关节位置的旋转)

骨架关节 (模型空间, 高度按模型归一化到 1.0 后缩放):
    root  骨盆      头/躯干/四肢共同根
    spine 躯干      呼吸/前倾
    neck  颈
    head  头        转头/点头
    l_arm 左上臂    摆臂
    r_arm 右上臂
    l_leg 左大腿    走路抬腿
    r_leg 右大腿
"""
from __future__ import annotations

import numpy as np

F32 = np.float32

JOINTS = ["root", "spine", "neck", "head",
          "l_arm", "r_arm", "l_leg", "r_leg"]


def joint_positions(h):
    """根据角色总高 h 返回每个关节的模型空间位置 (y 从脚底 0 起)。"""
    return {
        "root":  (0.0, h * 0.52, 0.0),
        "spine": (0.0, h * 0.62, 0.0),
        "neck":  (0.0, h * 0.83, 0.0),
        "head":  (0.0, h * 0.91, 0.0),
        "l_arm": (-h * 0.13, h * 0.78, 0.0),
        "r_arm": (h * 0.13, h * 0.78, 0.0),
        "l_leg": (-h * 0.055, h * 0.28, 0.0),
        "r_leg": (h * 0.055, h * 0.28, 0.0),
    }


def bind(verts6, h):
    """给 pos3+nrm3 顶点绑定骨架, 返回扩展顶点 (N, 10)。

    每顶点取最近 2 个关节; 若第二近的权重贡献 < 8% 则只用一个关节。
    """
    n = len(verts6)
    pos = verts6[:, 0:3]
    jp = joint_positions(h)
    names = JOINTS
    centers = np.array([jp[k] for k in names], F32)   # (J, 3)
    d2 = ((pos[:, None, :] - centers[None, :, :]) ** 2).sum(-1)  # (N, J)
    j0 = d2.argmin(1)
    d0 = d2[np.arange(n), j0]
    d2c = d2.copy()
    d2c[np.arange(n), j0] = 1e9
    j1 = d2c.argmin(1)
    d1 = d2c[np.arange(n), j1]

    w0 = np.ones(n, F32)
    w1 = np.zeros(n, F32)
    # 第二关节权重: 距离越接近占比越高 (取 exp(-Δd/阈值))
    delta = np.sqrt(d1) - np.sqrt(d0)
    blend = np.exp(-np.clip(delta - h * 0.12, 0.0, None) / (h * 0.30))
    use = blend > 0.08
    w1 = np.where(use, blend, 0.0).astype(F32)
    w0 = 1.0 - w1

    jd = np.stack([j0, w0, j1, w1], 1).astype(F32)
    return np.concatenate([verts6, jd], axis=1).astype(F32)


# --------------------------------------------------------------------------
# 动画: 每帧计算 8 个关节的姿势旋转矩阵 (模型空间)
# --------------------------------------------------------------------------
def _rot(axis, ang):
    """绕 axis (0/1/2 = x/y/z) 旋转 ang 弧度的 3x3 矩阵。"""
    c, s = np.cos(ang), np.sin(ang)
    if axis == 0:
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], F32)
    if axis == 1:
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], F32)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], F32)


def pose_matrices(anim, t, phase, h):
    """返回 (J,4,4) 模型空间骨骼矩阵 (仅姿势旋转, 含关节局部旋转)。

    anim: 动画名 (idle/walk/run/glide)
    """
    jp = joint_positions(h)
    R = {k: np.eye(3, dtype=F32) for k in JOINTS}

    if anim == "idle":
        R["root"] = _rot(0, 0.012 * np.sin(t * 1.4 + phase))
        R["spine"] = _rot(0, 0.030 * np.sin(t * 1.4 + phase))
        R["head"] = _rot(0, 0.045 * np.sin(t * 1.7 + phase + 0.5))
        R["head"] = R["head"] @ _rot(1, 0.03 * np.sin(t * 0.9 + phase))
        R["l_arm"] = _rot(2, 0.06 * np.sin(t * 1.4 + phase))
        R["r_arm"] = _rot(2, -0.06 * np.sin(t * 1.4 + phase))
        R["l_leg"] = _rot(2, 0.02 * np.sin(t * 1.4 + phase))
        R["r_leg"] = _rot(2, -0.02 * np.sin(t * 1.4 + phase))
    elif anim in ("walk", "run"):
        f = 1.6 if anim == "walk" else 2.4
        amp = 0.42 if anim == "walk" else 0.62
        s = np.sin(t * f * 2 * np.pi + phase)
        R["spine"] = _rot(2, 0.05 * s) @ _rot(0, 0.04 * abs(np.cos(t * f * 2 * np.pi + phase)))
        R["l_arm"] = _rot(2, -amp * s)
        R["r_arm"] = _rot(2, amp * s)
        R["l_leg"] = _rot(2, amp * s * 0.9)
        R["r_leg"] = _rot(2, -amp * s * 0.9)
        R["head"] = _rot(1, 0.06 * s)
    elif anim == "glide":
        R["l_arm"] = _rot(2, -1.15) @ _rot(0, -0.25)
        R["r_arm"] = _rot(2, 1.15) @ _rot(0, -0.25)
        R["spine"] = _rot(0, 0.10)
        R["l_leg"] = _rot(2, 0.18)
        R["r_leg"] = _rot(2, -0.18)
        R["head"] = _rot(0, -0.08)

    mats = np.zeros((len(JOINTS), 4, 4), F32)
    for i, k in enumerate(JOINTS):
        ox, oy, oz = jp[k]
        T = np.eye(4, dtype=F32)
        T[:3, 3] = (ox, oy, oz)
        Ti = np.eye(4, dtype=F32)
        Ti[:3, 3] = (-ox, -oy, -oz)
        Rm = np.eye(4, dtype=F32)
        Rm[:3, :3] = R[k]
        mats[i] = T @ Rm @ Ti
    return mats
