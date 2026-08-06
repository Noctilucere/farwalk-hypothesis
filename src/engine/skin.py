"""
skin.py -- 第三方兼容 GPU LBS 蒙皮

骨架命名与 Mixamo 兼容 (19 关节), 4 关节混合权重 (glTF 2.0 标准),
动作横轴驱动 (idle / walk / run / glide / sprint / turn / jump / land /
greet / sit / sleep / dance / think).

顶点布局: pos3 + nrm3 + jw4 (4 关节 j0,w0,j1,w1,j2,w2,j3,w3)
shader: uniform mat4 u_bones[19]
"""
from __future__ import annotations

import math

import numpy as np

F32 = np.float32

# Mixamo 兼容关节 (19 关节, 标准人形骨架)
JOINTS = [
    "Hips", "Spine", "Spine1", "Spine2", "Neck", "Head",
    "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
    "RightShoulder", "RightArm", "RightForeArm", "RightHand",
    "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase",
    "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase",
]

# 默认骨架关节位置 (高度 h, 脚底 y=0)
# 按 Mixamo 标准的关节链结构 (父子关系)
JOINT_PARENT = {
    "Hips": None,
    "Spine": "Hips", "Spine1": "Spine", "Spine2": "Spine1",
    "Neck": "Spine2", "Head": "Neck",
    "LeftShoulder": "Spine2", "LeftArm": "LeftShoulder", "LeftForeArm": "LeftArm", "LeftHand": "LeftForeArm",
    "RightShoulder": "Spine2", "RightArm": "RightShoulder", "RightForeArm": "RightArm", "RightHand": "RightForeArm",
    "LeftUpLeg": "Hips", "LeftLeg": "LeftUpLeg", "LeftFoot": "LeftLeg", "LeftToeBase": "LeftFoot",
    "RightUpLeg": "Hips", "RightLeg": "RightUpLeg", "RightFoot": "RightLeg", "RightToeBase": "RightFoot",
}


def joint_positions(h):
    """返回 Mixamo 风格的默认关节位置 (脚底 y=0, 总高 h)."""
    return {
        # 骨盆到头
        "Hips":          (0.0, h * 0.55, 0.0),
        "Spine":         (0.0, h * 0.62, 0.0),
        "Spine1":        (0.0, h * 0.69, 0.0),
        "Spine2":        (0.0, h * 0.78, 0.0),
        "Neck":          (0.0, h * 0.84, 0.0),
        "Head":          (0.0, h * 0.92, 0.0),
        # 肩带
        "LeftShoulder":  (-h * 0.07, h * 0.82, 0.0),
        "LeftArm":       (-h * 0.13, h * 0.79, 0.0),
        "LeftForeArm":   (-h * 0.14, h * 0.63, 0.0),
        "LeftHand":      (-h * 0.14, h * 0.50, 0.0),
        "RightShoulder": ( h * 0.07, h * 0.82, 0.0),
        "RightArm":      ( h * 0.13, h * 0.79, 0.0),
        "RightForeArm":  ( h * 0.14, h * 0.63, 0.0),
        "RightHand":     ( h * 0.14, h * 0.50, 0.0),
        # 腿
        "LeftUpLeg":     (-h * 0.07, h * 0.50, 0.0),
        "LeftLeg":       (-h * 0.07, h * 0.27, 0.0),
        "LeftFoot":      (-h * 0.07, h * 0.05, h * 0.13),
        "LeftToeBase":   (-h * 0.07, h * 0.02, h * 0.22),
        "RightUpLeg":    ( h * 0.07, h * 0.50, 0.0),
        "RightLeg":      ( h * 0.07, h * 0.27, 0.0),
        "RightFoot":     ( h * 0.07, h * 0.05, h * 0.13),
        "RightToeBase":  ( h * 0.07, h * 0.02, h * 0.22),
    }


def bind(verts6, h):
    """绑定 4 关节权重 (glTF 2.0 标准), 取 top-2 输出到顶点 (vec4 jw: j0,w0,j1,w1)。

    其余 2 个关节的权重合并到 bone 0 的法线权重上 (避免硬度收缩)。
    顶点布局: pos3 + nrm3 + (j0,w0,j1,w1) = (N, 10)
    """
    n = len(verts6)
    pos = verts6[:, 0:3]
    jp = joint_positions(h)
    names = JOINTS
    centers = np.array([jp[k] for k in names], F32)
    d2 = ((pos[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
    # 权重: 1/(1+alpha*d^2) 归一化
    alpha = 1.0 / (h * h * 0.06)
    w_full = 1.0 / (1.0 + alpha * d2)
    w_full = w_full / w_full.sum(axis=1, keepdims=True)
    # 选 top-2 关节
    top2 = np.argsort(-w_full, axis=1)[:, :2]
    jw = np.empty((n, 4), F32)
    jw[:, 0] = top2[:, 0].astype(F32)
    jw[:, 1] = w_full[np.arange(n), top2[:, 0]]
    jw[:, 2] = top2[:, 1].astype(F32)
    jw[:, 3] = w_full[np.arange(n), top2[:, 1]]
    # 归一化 (top-2 之和可能 < 1)
    s = jw[:, 1] + jw[:, 3]
    jw[:, 1] = jw[:, 1] / np.maximum(s, 1e-5)
    jw[:, 3] = jw[:, 3] / np.maximum(s, 1e-5)
    return np.concatenate([verts6, jw], axis=1).astype(F32)


# --------------------------------------------------------------------------
# 动画: 每帧计算 22 个关节的姿势旋转矩阵 (模型空间)
# --------------------------------------------------------------------------
def _rot(axis, ang):
    c, s = math.cos(ang), math.sin(ang)
    if axis == 0:
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], F32)
    if axis == 1:
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], F32)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], F32)


def _local_anim(anim, t, phase, h):
    """返回每个关节的局部 3x3 旋转矩阵 (相对父关节)。

    完整姿态由父关节复合得到 (relative -> global)。
    """
    s = math.sin
    c = math.cos
    R = {k: np.eye(3, dtype=F32) for k in JOINTS}

    # 全身姿态 (Hips 决定位置/方向)
    if anim in ("walk", "run", "sprint"):
        f = {"walk": 1.6, "run": 2.4, "sprint": 3.2}[anim]
        amp = {"walk": 0.42, "run": 0.62, "sprint": 0.78}[anim]
        bc = (anim != "walk")  # 身体前倾
        ph = 2 * math.pi * f * t + phase
        # 骨盆: 轻微上下颠簸 + 转向
        R["Hips"] = _rot(0, 0.05 * s(ph)) @ _rot(1, 0.04 * s(ph * 0.5))
        # 脊柱: 扭转 + 前倾
        R["Spine"] = _rot(2, 0.05 * s(ph)) @ _rot(0, 0.04 * abs(c(ph)) + 0.04 * bc)
        R["Spine1"] = _rot(2, 0.06 * s(ph + 0.3))
        # 头
        R["Head"] = _rot(1, 0.06 * s(ph))
        # 肩 (与腿异相)
        R["LeftShoulder"] = _rot(2, -0.05 * s(ph))
        R["LeftArm"] = _rot(2, -amp * s(ph)) @ _rot(0, 0.10)
        R["LeftForeArm"] = _rot(0, -0.3 - 0.2 * abs(s(ph)))
        R["RightShoulder"] = _rot(2, 0.05 * s(ph))
        R["RightArm"] = _rot(2, amp * s(ph)) @ _rot(0, 0.10)
        R["RightForeArm"] = _rot(0, -0.3 - 0.2 * abs(s(ph + math.pi)))
        # 腿
        R["LeftUpLeg"] = _rot(0, -amp * 0.4 * s(ph))
        R["LeftLeg"] = _rot(0, 0.5 * (1 - c(ph)))
        R["LeftFoot"] = _rot(0, -0.3 * s(ph - 0.5))
        R["LeftToeBase"] = _rot(0, 0.25 * s(ph - 0.5))
        R["RightUpLeg"] = _rot(0, amp * 0.4 * s(ph))
        R["RightLeg"] = _rot(0, 0.5 * (1 - c(ph + math.pi)))
        R["RightFoot"] = _rot(0, -0.3 * s(ph + math.pi - 0.5))
        R["RightToeBase"] = _rot(0, 0.25 * s(ph + math.pi - 0.5))
    elif anim == "idle":
        # 站立呼吸 + 微摆
        R["Hips"] = _rot(0, 0.012 * s(t * 1.4 + phase))
        R["Spine"] = _rot(0, 0.025 * s(t * 1.4 + phase))
        R["Spine1"] = _rot(0, 0.020 * s(t * 1.4 + phase + 0.3))
        R["Spine2"] = _rot(0, 0.018 * s(t * 1.4 + phase + 0.5))
        R["Head"] = _rot(0, 0.045 * s(t * 1.7 + phase + 0.5)) @ _rot(1, 0.03 * s(t * 0.9 + phase))
        # 臂下垂 + 微摆
        R["LeftArm"] = _rot(2, 0.06 * s(t * 1.4 + phase))
        R["LeftForeArm"] = _rot(0, -0.15)
        R["RightArm"] = _rot(2, -0.06 * s(t * 1.4 + phase))
        R["RightForeArm"] = _rot(0, -0.15)
    elif anim == "glide":
        # 滑翔: 双臂张开
        R["Hips"] = _rot(1, 0.05)
        R["Spine"] = _rot(0, 0.10)
        R["Spine1"] = _rot(0, 0.04)
        R["Head"] = _rot(0, -0.08)
        R["LeftShoulder"] = _rot(2, -1.2)
        R["LeftArm"] = _rot(2, -0.2)
        R["LeftForeArm"] = _rot(0, -0.3)
        R["RightShoulder"] = _rot(2, 1.2)
        R["RightArm"] = _rot(2, 0.2)
        R["RightForeArm"] = _rot(0, -0.3)
        R["LeftUpLeg"] = _rot(2, 0.18)
        R["RightUpLeg"] = _rot(2, -0.18)
    elif anim == "jump":
        R["Hips"] = _rot(0, 0.15)
        R["Spine"] = _rot(0, 0.10)
        R["LeftUpLeg"] = _rot(0, -0.40)
        R["RightUpLeg"] = _rot(0, -0.40)
        R["LeftLeg"] = _rot(0, 0.80)
        R["RightLeg"] = _rot(0, 0.80)
        R["LeftArm"] = _rot(2, -0.5) @ _rot(0, -0.30)
        R["RightArm"] = _rot(2, 0.5) @ _rot(0, -0.30)
    elif anim == "land":
        R["Hips"] = _rot(0, -0.10)
        R["Spine"] = _rot(0, -0.05)
        R["LeftUpLeg"] = _rot(0, 0.50)
        R["RightUpLeg"] = _rot(0, 0.50)
        R["LeftLeg"] = _rot(0, -0.80)
        R["RightLeg"] = _rot(0, -0.80)
        R["LeftForeArm"] = _rot(0, -0.3)
        R["RightForeArm"] = _rot(0, -0.3)
    elif anim == "greet":
        # 举手挥动
        R["RightArm"] = _rot(2, -2.6) @ _rot(0, -0.15)
        R["RightForeArm"] = _rot(2, -0.4 * s(t * 4.0 + phase))
        f = 4.0
        R["Head"] = _rot(1, 0.12 * s(t * f + phase))
    elif anim == "sit":
        R["Hips"] = _rot(0, -0.85)
        R["Spine"] = _rot(0, 0.20)
        R["LeftUpLeg"] = _rot(0, 0.85)
        R["RightUpLeg"] = _rot(0, 0.85)
        R["LeftLeg"] = _rot(0, -1.55)
        R["RightLeg"] = _rot(0, -1.55)
        R["LeftArm"] = _rot(2, 0.15)
        R["RightArm"] = _rot(2, -0.15)
    elif anim == "sleep":
        R["Hips"] = _rot(0, -0.30)
        R["LeftUpLeg"] = _rot(0, 0.40)
        R["RightUpLeg"] = _rot(0, 0.40)
        R["LeftLeg"] = _rot(0, -0.20)
        R["RightLeg"] = _rot(0, -0.20)
        R["LeftArm"] = _rot(2, 0.20)
        R["RightArm"] = _rot(2, -0.20)
    elif anim == "dance":
        # 摆臀
        R["Hips"] = _rot(2, 0.3 * s(t * 3.5 + phase))
        R["Spine"] = _rot(0, 0.08 * s(t * 3.5 + phase))
        R["LeftArm"] = _rot(2,  0.9 * s(t * 3.5 + phase))
        R["RightArm"] = _rot(2, -0.9 * s(t * 3.5 + phase))
        R["LeftUpLeg"] = _rot(2, 0.15 * s(t * 3.5 + phase))
        R["RightUpLeg"] = _rot(2, -0.15 * s(t * 3.5 + phase))
    elif anim == "think":
        # 思考: 单手扶下巴
        R["RightArm"] = _rot(2, -1.2) @ _rot(0, -1.0)
        R["RightForeArm"] = _rot(2, 0.3)
        R["Head"] = _rot(1, -0.15)
    elif anim == "turn":
        # 急转: 身体大幅转向
        R["Hips"] = _rot(1, 0.4)
        R["Spine"] = _rot(1, -0.4)
        R["LeftUpLeg"] = _rot(0, -0.30)
        R["RightUpLeg"] = _rot(0, 0.40)
    return R


def pose_matrices(anim, t, phase, h):
    """返回 (J, 4, 4) 全局骨骼矩阵 (每个关节从 model 空间到 bind 局部, 包含父关节复合)。

    关节的最终矩阵 = T(joint_pos) @ R(local_global) @ T(-joint_pos)
    其中 local_global = 父关节 global_x_R @ 本关节 local_R
    """
    jp = joint_positions(h)
    local = _local_anim(anim, t, phase, h)
    # 复合父关节
    global_R = {}
    for k in JOINTS:
        p = JOINT_PARENT[k]
        if p is None:
            global_R[k] = local[k]
        else:
            global_R[k] = global_R[p] @ local[k]
    # 构造 mat4: T @ R @ T^-1
    mats = np.zeros((len(JOINTS), 4, 4), dtype=F32)
    for i, k in enumerate(JOINTS):
        ox, oy, oz = jp[k]
        T = np.eye(4, dtype=F32); T[:3, 3] = (ox, oy, oz)
        Ti = np.eye(4, dtype=F32); Ti[:3, 3] = (-ox, -oy, -oz)
        Rm = np.eye(4, dtype=F32); Rm[:3, :3] = global_R[k]
        mats[i] = T @ Rm @ Ti
    return mats
