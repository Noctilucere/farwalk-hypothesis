"""
camera.py -- 第三人称轨道相机 (原神式)

特性:
    * 鼠标控制的偏航/俯仰, 带角度阻尼
    * 弹簧臂: 目标点后方固定距离, 随速度轻微拉远 (速度感)
    * 地形穿插规避: 相机低于地表时抬升
    * 剧情演出用的相机接管 (cinematic lerp)
"""
from __future__ import annotations

import math

import numpy as np

from . import math3d as m3

F32 = np.float32


class OrbitCamera:
    def __init__(self, fov=52.0):
        self.target = m3.vec3(0, 2, 0)
        self.yaw = 0.0
        self.pitch = 0.18
        self.distance = 5.2
        self.base_distance = 5.2
        self.fov = fov
        self.base_fov = fov
        self.height_offset = 1.55
        self.min_pitch = -0.52
        self.max_pitch = 1.16
        self.sensitivity = 0.0034
        self.position = m3.vec3(0, 5, 10)
        self.smooth_target = m3.vec3(0, 2, 0)
        self._lift = 0.0
        self._shake = 0.0
        self._shake_t = 0.0
        # 演出接管
        self.cine_weight = 0.0
        self.cine_pos = m3.vec3(0, 0, 0)
        self.cine_look = m3.vec3(0, 0, 0)

    def handle_mouse(self, dx, dy, invert_y=False):
        # 鼠标上移 → 相机上移 (pitch+); 鼠标右移 → 相机右移
        # 经玩家反馈校正后: 横向输入取反 (yaw -= dx) 实现直观方向感
        self.yaw -= dx * self.sensitivity
        self.pitch += (dy if invert_y else -dy) * self.sensitivity
        self.pitch = m3.clamp(self.pitch, self.min_pitch, self.max_pitch)
        if self.yaw > math.pi:
            self.yaw -= 2 * math.pi
        elif self.yaw < -math.pi:
            self.yaw += 2 * math.pi

    def add_shake(self, amount):
        self._shake = max(self._shake, amount)

    def snap(self, focus):
        """瞬间把相机贴到目标上 (传送 / 过场切镜 / 读档后使用, 避免拉丝)。"""
        focus = np.asarray(focus, F32)
        self.smooth_target = focus + m3.vec3(0, self.height_offset, 0)
        cp = math.cos(self.pitch)
        offset = m3.vec3(math.sin(self.yaw) * cp, math.sin(self.pitch),
                         math.cos(self.yaw) * cp)
        self.position = self.smooth_target + offset * self.distance

    def update(self, dt, focus, speed01=0.0, height_fn=None, zoom=0.0):
        focus = np.asarray(focus, F32)
        aim = focus + m3.vec3(0, self.height_offset, 0)
        # 更跟手的目标跟随 (降低 smoothing 值 -> 收敛更快)
        self.smooth_target = m3.damp(self.smooth_target, aim, 0.0009, dt)

        self.base_distance = m3.clamp(self.base_distance + zoom, 2.6, 13.5)
        want = self.base_distance + speed01 * 1.15
        self.distance = m3.damp(self.distance, want, 0.02, dt)
        self.fov = m3.damp(self.fov, self.base_fov + speed01 * 7.5, 0.02, dt)

        cp = math.cos(self.pitch)
        offset = m3.vec3(math.sin(self.yaw) * cp, math.sin(self.pitch), math.cos(self.yaw) * cp)
        pos = self.smooth_target + offset * self.distance

        # 地形穿插规避: 平滑抬升, 避免丘陵转视角时的硬跳
        if height_fn is not None:
            gh = height_fn(pos[0], pos[2]) + 0.85
            if pos[1] < gh:
                self._lift = m3.damp(self._lift, gh - pos[1], 0.10, dt)
            else:
                self._lift = m3.damp(self._lift, 0.0, 0.10, dt)
            pos = pos + m3.vec3(0, self._lift, 0)

        # 抖动
        if self._shake > 0.001:
            self._shake_t += dt * 34.0
            amp = self._shake * 0.16
            pos = pos + m3.vec3(math.sin(self._shake_t * 1.7) * amp,
                                math.cos(self._shake_t * 2.3) * amp,
                                math.sin(self._shake_t * 3.1) * amp * 0.6)
            self._shake = max(0.0, self._shake - dt * 1.9)

        if self.cine_weight > 0.001:
            w = m3.clamp(self.cine_weight, 0.0, 1.0)
            pos = m3.lerp(pos, self.cine_pos, w)
            self.smooth_target = m3.lerp(self.smooth_target, self.cine_look, w)

        self.position = pos
        return pos

    def view_matrix(self):
        return m3.look_at(self.position, self.smooth_target)

    def proj_matrix(self, aspect, znear=0.12, zfar=900.0):
        return m3.perspective(self.fov, aspect, znear, zfar)

    def forward_flat(self):
        return m3.normalize(m3.vec3(-math.sin(self.yaw), 0.0, -math.cos(self.yaw)))

    def right_flat(self):
        f = self.forward_flat()
        return m3.normalize(m3.vec3(-f[2], 0.0, f[0]))
