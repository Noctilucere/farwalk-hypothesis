"""
player.py -- 第三人称角色控制器

玩法参考《原神》的移动手感:
    行走 / 冲刺(耗体) / 跳跃 / 攀爬(耗体) / 滑翔(耗体) / 涉水游泳(耗体)
    体力条在停止消耗 0.7 秒后回复
    额外能力: 回响 (Echo) —— 释放一圈共振波, 照亮附近的实体与刻痕

角色没有骨骼动画, 所有"动作"由程序化的挤压/倾斜/浮动叠加而成。
"""
from __future__ import annotations

import math

import numpy as np

from ..engine import math3d as m3
from ..world import terrain as T

F32 = np.float32

MAX_STAMINA = 100.0
WALK_SPEED = 4.6
SPRINT_SPEED = 8.4
CLIMB_SPEED = 2.7
SWIM_SPEED = 3.0
GLIDE_FALL = -1.55
GLIDE_SPEED = 7.6
JUMP_V = 7.4
GRAVITY = -21.0

COST_SPRINT = 12.0     # 每秒
COST_CLIMB = 9.0
COST_GLIDE = 6.0
COST_SWIM = 4.0
COST_JUMP = 4.0
COST_ECHO = 22.0
REGEN = 26.0
REGEN_DELAY = 0.7

# 生命值
MAX_HP = 100.0
REGEN_HP = 9.0         # 每秒回血
REGEN_HP_DELAY = 2.5   # 受击/出水后多久开始回血
DROWN_DPS = 5.0        # 溺水每秒伤害
FALL_SAFE = 16.0       # 落地速度低于此值无伤; 之上按超出比例扣血
VOID_Y = -25.0         # 掉出世界的高度阈值


class Player:
    def __init__(self, terrain: T.Terrain, pos=None):
        self.terrain = terrain
        if pos is None:
            x, z = 6.0, 74.0
            pos = (x, terrain.height_at(x, z), z)
        self.pos = np.asarray(pos, F32).copy()
        self.vel = m3.vec3(0, 0, 0)
        self.yaw = 0.0
        self.grounded = True
        self.gliding = False
        self.climbing = False
        self.swimming = False
        self.sprinting = False
        self.stamina = MAX_STAMINA
        self._regen_t = 0.0
        self.speed01 = 0.0
        self.exhausted = False
        self._exh_t = 0.0

        # 生命值
        self.hp = MAX_HP
        self.hurt_t = 0.0
        self._hp_regen_t = 0.0
        self.dead = False
        self.step_phase = 0.0
        self.squash = 1.0
        self.lean = 0.0
        self.frozen = False          # 剧情演出时冻结

        # 回响能力
        self.echo_unlocked = False
        self.echo_radius = -1.0
        self.echo_origin = m3.vec3(0, 0, 0)
        self.echo_cd = 0.0

        self.distance_walked = 0.0

    # ------------------------------------------------------------------
    @property
    def eye(self):
        return self.pos + m3.vec3(0, 1.5, 0)

    def ground_h(self, x=None, z=None):
        return self.terrain.height_at(self.pos[0] if x is None else x,
                                      self.pos[2] if z is None else z)

    def _slope_ahead(self, dirv, dist=1.1):
        x = self.pos[0] + dirv[0] * dist
        z = self.pos[2] + dirv[2] * dist
        return self.terrain.height_at(x, z) - self.pos[1]

    def _drain(self, amount):
        if amount <= 0:
            return True
        if self.stamina <= 0.0:
            return False
        self.stamina = max(0.0, self.stamina - amount)
        self._regen_t = REGEN_DELAY
        if self.stamina <= 0.0:
            self.exhausted = True
            self._exh_t = 1.4
        return True

    # ------------------------------------------------------------------
    def trigger_echo(self):
        if not self.echo_unlocked or self.echo_cd > 0 or self.stamina < COST_ECHO:
            return False
        self._drain(COST_ECHO)
        self.echo_origin = self.pos.copy()
        self.echo_radius = 0.5
        self.echo_cd = 3.2
        return True

    # ------------------------------------------------------------------
    def damage(self, amount, cause=None):
        """扣血; hp<=0 时标记 dead, 由 Game 处理重生。"""
        if amount <= 0.0 or self.dead:
            return
        self.hp = max(0.0, self.hp - amount)
        self.hurt_t = max(self.hurt_t, 0.45)
        self._hp_regen_t = REGEN_HP_DELAY
        if self.hp <= 0.0:
            self.dead = True

    # ------------------------------------------------------------------
    def update(self, dt, inp, cam):
        """inp: dict(forward, back, left, right, sprint, jump_pressed, jump_held, echo)"""
        dt = min(dt, 0.05)

        # ---- 回响波推进 ----
        if self.echo_cd > 0:
            self.echo_cd -= dt
        if self.echo_radius > 0:
            self.echo_radius += dt * 46.0
            if self.echo_radius > 130.0:
                self.echo_radius = -1.0
        if inp.get("echo") and self.echo_radius < 0:
            self.trigger_echo()

        if self.frozen:
            self.speed01 = m3.damp(self.speed01, 0.0, 0.02, dt)
            self._settle(dt)
            return

        # ---- 输入方向 ----
        fwd = cam.forward_flat()
        rgt = cam.right_flat()
        wish = m3.vec3(0, 0, 0)
        if inp.get("forward"):
            wish = wish + fwd
        if inp.get("back"):
            wish = wish - fwd
        if inp.get("right"):
            wish = wish + rgt
        if inp.get("left"):
            wish = wish - rgt
        moving = m3.length2(wish) > 1e-4
        if moving:
            wish = m3.normalize(wish)

        gh = self.ground_h()
        water_depth = T.WATER_LEVEL - gh
        self.swimming = (self.pos[1] < T.WATER_LEVEL - 0.35) and water_depth > 1.0

        # ---- 攀爬判定 ----
        want_climb = False
        if moving and not self.swimming:
            rise = self._slope_ahead(wish, 1.15)
            if rise > 1.35 and self.stamina > 1.0:
                want_climb = True

        if self.climbing and (not moving or self.stamina <= 0.0):
            if self.stamina <= 0.0:
                self.climbing = False
        if want_climb:
            self.climbing = True
        elif self.climbing:
            rise = self._slope_ahead(wish, 1.15) if moving else -1.0
            if rise < 0.7:
                self.climbing = False

        # ---- 各状态运动 ----
        if self.climbing:
            self.gliding = False
            if not self._drain(COST_CLIMB * dt):
                self.climbing = False
            else:
                up = CLIMB_SPEED
                self.pos[0] += wish[0] * 1.5 * dt
                self.pos[2] += wish[2] * 1.5 * dt
                self.pos[1] += up * dt
                self.vel[:] = 0.0
                tgt_h = self.ground_h()
                if self.pos[1] > tgt_h + 0.15:
                    # 翻上边缘
                    self.pos[1] = min(self.pos[1], tgt_h + 1.6)
                if self.pos[1] >= tgt_h and self._slope_ahead(wish, 1.4) < 0.6:
                    self.climbing = False
                    self.pos[1] = max(self.pos[1], tgt_h)
                self.speed01 = 0.25
                self.yaw = math.atan2(wish[0], wish[2]) if moving else self.yaw
                self._settle(dt, climb=True)
                return

        if self.swimming:
            self.gliding = False
            self._drain(COST_SWIM * dt)
            # 修复: 正常游泳不掉血; 只有体力耗尽仍泡在水里才会溺水
            if self.stamina <= 0.0:
                self.damage(DROWN_DPS * dt, "drown")
            sp = SWIM_SPEED * (0.55 if self.stamina <= 0 else 1.0)
            self.pos[0] += wish[0] * sp * dt
            self.pos[2] += wish[2] * sp * dt
            target_y = T.WATER_LEVEL - 0.55
            self.pos[1] += (target_y - self.pos[1]) * min(1.0, dt * 6.0)
            self.vel[1] = 0.0
            if moving:
                self.yaw = m3.angle_lerp(self.yaw, math.atan2(wish[0], wish[2]), min(1.0, dt * 9))
            self.speed01 = m3.damp(self.speed01, 0.3 if moving else 0.0, 0.02, dt)
            self.grounded = False
            self._settle(dt, swim=True)
            return

        # 地面 / 空中
        gh = self.ground_h()
        self.grounded = self.pos[1] <= gh + 0.06 and self.vel[1] <= 0.01

        self.sprinting = bool(inp.get("sprint")) and moving and self.grounded and self.stamina > 0
        if self.sprinting and not self._drain(COST_SPRINT * dt):
            self.sprinting = False

        speed = SPRINT_SPEED if self.sprinting else WALK_SPEED
        if self.exhausted:
            speed *= 0.62

        if self.grounded:
            self.gliding = False
            self.pos[1] = gh
            self.vel[1] = 0.0
            if inp.get("jump_pressed") and self.stamina > COST_JUMP:
                self._drain(COST_JUMP)
                self.vel[1] = JUMP_V
                self.grounded = False
                self.squash = 1.22
            tv = wish * speed
            self.vel[0] = m3.damp(self.vel[0], tv[0], 0.0006, dt)
            self.vel[2] = m3.damp(self.vel[2], tv[2], 0.0006, dt)
        else:
            # 空中: 可开启滑翔
            if inp.get("jump_pressed") and not self.gliding and self.vel[1] < 1.5 \
                    and self.stamina > 2.0:
                self.gliding = True
                self.squash = 0.86
            if self.gliding:
                if not self._drain(COST_GLIDE * dt) or (self.pos[1] - gh) < 0.6:
                    self.gliding = False
                else:
                    self.vel[1] = m3.damp(self.vel[1], GLIDE_FALL, 0.05, dt)
                    tv = wish * GLIDE_SPEED
                    self.vel[0] = m3.damp(self.vel[0], tv[0], 0.02, dt)
                    self.vel[2] = m3.damp(self.vel[2], tv[2], 0.02, dt)
            if not self.gliding:
                self.vel[1] += GRAVITY * dt
                tv = wish * speed
                self.vel[0] = m3.damp(self.vel[0], tv[0], 0.35, dt)
                self.vel[2] = m3.damp(self.vel[2], tv[2], 0.35, dt)

        nx = self.pos[0] + self.vel[0] * dt
        nz = self.pos[2] + self.vel[2] * dt
        lim = T.HALF - 8.0
        nx = min(max(nx, -lim), lim)
        nz = min(max(nz, -lim), lim)
        # 陡坡阻挡 (非攀爬时)
        nh = self.terrain.height_at(nx, nz)
        if self.grounded and nh - self.pos[1] > 0.95:
            pass  # 由攀爬处理; 这里不推进
        else:
            self.distance_walked += math.hypot(nx - self.pos[0], nz - self.pos[2])
            self.pos[0], self.pos[2] = nx, nz

        self.pos[1] += self.vel[1] * dt
        gh = self.ground_h()
        if self.pos[1] < gh:
            fall = self.vel[1]
            was_air = not self.grounded
            if was_air and fall < -12.0:
                self.squash = 0.74
            self.pos[1] = gh
            self.vel[1] = 0.0
            self.grounded = True
            self.gliding = False
            if was_air and fall < -FALL_SAFE:
                self.damage((-fall - FALL_SAFE) * 1.1, "fall")

        hs = math.hypot(self.vel[0], self.vel[2])
        self.speed01 = m3.clamp(hs / SPRINT_SPEED, 0.0, 1.2)
        if moving:
            self.yaw = m3.angle_lerp(self.yaw, math.atan2(wish[0], wish[2]),
                                     min(1.0, dt * (14.0 if self.grounded else 6.0)))

        self._settle(dt)

    # ------------------------------------------------------------------
    def _settle(self, dt, climb=False, swim=False):
        # 掉出世界的致死检查 (覆盖所有分支)
        if self.pos[1] < VOID_Y:
            self.damage(999.0, "void")

        # 受击红屏计时
        if self.hurt_t > 0:
            self.hurt_t = max(0.0, self.hurt_t - dt)

        # 生命回复 (在地面且安全时)
        if self.hp < MAX_HP and not self.swimming and self.grounded and not self.dead:
            if self._hp_regen_t > 0:
                self._hp_regen_t -= dt
            else:
                self.hp = min(MAX_HP, self.hp + REGEN_HP * dt)

        # 体力回复
        if self._regen_t > 0:
            self._regen_t -= dt
        elif self.stamina < MAX_STAMINA:
            self.stamina = min(MAX_STAMINA, self.stamina + REGEN * dt)
        if self.exhausted:
            self._exh_t -= dt
            if self._exh_t <= 0 and self.stamina > MAX_STAMINA * 0.32:
                self.exhausted = False

        # 程序化动作
        hs = math.hypot(self.vel[0], self.vel[2])
        self.step_phase += dt * (hs * 1.35 + (2.0 if climb else 0.0))
        if self.grounded and hs > 0.4:
            bob = abs(math.sin(self.step_phase * 2.0)) * 0.055
            self.squash = m3.damp(self.squash, 1.0 - bob, 0.02, dt)
        elif self.gliding:
            self.squash = m3.damp(self.squash, 0.94, 0.05, dt)
        else:
            self.squash = m3.damp(self.squash, 1.0, 0.02, dt)
        target_lean = m3.clamp(hs / SPRINT_SPEED, 0, 1) * 0.16
        self.lean = m3.damp(self.lean, target_lean, 0.03, dt)

    # ------------------------------------------------------------------
    def state_name(self):
        if self.climbing:
            return "攀爬"
        if self.gliding:
            return "滑翔"
        if self.swimming:
            return "泅渡"
        if self.sprinting:
            return "疾行"
        if not self.grounded:
            return "腾空"
        return "行走"

    def save_dict(self):
        return dict(pos=[float(x) for x in self.pos], yaw=float(self.yaw),
                    stamina=float(self.stamina), hp=float(self.hp),
                    echo=bool(self.echo_unlocked),
                    walked=float(self.distance_walked))

    def load_dict(self, d):
        self.pos = np.asarray(d.get("pos", self.pos), F32)
        self.yaw = float(d.get("yaw", 0.0))
        self.stamina = float(d.get("stamina", MAX_STAMINA))
        self.hp = float(d.get("hp", MAX_HP))
        self.dead = self.hp <= 0.0
        self.echo_unlocked = bool(d.get("echo", False))
        self.distance_walked = float(d.get("walked", 0.0))
        self.vel[:] = 0.0
