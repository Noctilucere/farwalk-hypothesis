"""
main.py -- 游戏主循环 (窗口 / 输入 / 状态机 / 渲染调度)

状态: MENU -> LOADING -> PLAY <-> (JOURNAL / MAP / PAUSE) -> ENDING -> MENU

渲染每帧:
    阴影 pass -> 主 pass(天空/地形/散布/实体/水面) -> 后处理 -> UI
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import glfw
import moderngl
import numpy as np

from ..data import story as ST
from ..engine import math3d as m3
from ..engine.camera import OrbitCamera
from ..engine.renderer import Renderer, setm
from ..engine.text import FontAtlas
from ..ui.draw import UIBatch
from ..ui.hud import HUD, Minimap
from ..world import terrain as T
from ..world.scatter import Scatter
from .entities import EntityWorld
from .player import MAX_HP, Player
from .story_state import StoryState

F32 = np.float32

MENU, LOADING, PLAY, JOURNAL, MAP, PAUSE, ENDING, CHAR = range(8)

MENU_ITEMS = ["开始旅程", "继续旅程", "退出"]
PAUSE_ITEMS = ["继续", "手记", "世界地图", "保存进度", "返回主菜单"]

CARD_IN, CARD_HOLD, CARD_OUT = 0.9, 2.8, 0.9
BANNER_TOTAL = 3.6


# --------------------------------------------------------------------------
# 存档
# --------------------------------------------------------------------------
def save_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "FarwalkHypothesis")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = os.path.expanduser("~")
    return os.path.join(d, "save.json")


# --------------------------------------------------------------------------
# 氛围插值
# --------------------------------------------------------------------------
MOOD_KEYS = list(T.REGION_MOOD["wilds"].keys())


def blend_mood(weights):
    tot = sum(max(0.0, v) for v in weights.values()) or 1.0
    ref = T.REGION_MOOD["wilds"]
    out = {}
    for k in MOOD_KEYS:
        v0 = ref[k]
        if isinstance(v0, tuple):
            acc = [0.0] * len(v0)
            for rid, w in weights.items():
                if w <= 0.0:
                    continue
                vv = T.REGION_MOOD[rid][k]
                for i in range(len(v0)):
                    acc[i] += vv[i] * w
            out[k] = tuple(a / tot for a in acc)
        else:
            acc = 0.0
            for rid, w in weights.items():
                if w <= 0.0:
                    continue
                acc += T.REGION_MOOD[rid][k] * w
            out[k] = acc / tot
    return out


def approach_mood(cur, tgt, k):
    for key, tv in tgt.items():
        cv = cur[key]
        if isinstance(tv, tuple):
            cur[key] = tuple(c + (t - c) * k for c, t in zip(cv, tv))
        else:
            cur[key] = cv + (tv - cv) * k


def apply_mood(r: Renderer, mood):
    r.style = mood["style"]
    r.exposure = mood["exposure"]
    r.sun_dir = m3.normalize(m3.vec3(*mood["sun_dir"]))
    r.sun_color = mood["sun_color"]
    r.ambient_sky = mood["ambient_sky"]
    r.ambient_ground = mood["ambient_ground"]
    r.fog_color = mood["fog_color"]
    r.fog_sun_color = mood["fog_sun_color"]
    r.fog_density = mood["fog_density"]
    r.fog_height_falloff = mood["fog_height"]
    r.sky_zenith = mood["sky_zenith"]
    r.sky_horizon = mood["sky_horizon"]
    r.ground_color = mood["ground"]
    r.star_amount = mood["stars"]
    r.cloud_amount = mood["clouds"]
    r.saturation = mood["saturation"]
    r.lift = mood["lift"]
    r.gain = mood["gain"]
    r.outline = mood["outline"]
    r.bloom_strength = mood["bloom"]
    r.vignette = mood["vignette"]
    r.grain = mood["grain"]
    r.wind = mood["wind"]
    r.water_color = mood["water"]
    r.water_deep = mood["water_deep"]


# --------------------------------------------------------------------------
class Game:
    def __init__(self, width=1920, height=1080, quality="high", fullscreen=False):
        self.req_w, self.req_h = width, height
        self.quality = quality
        self.fullscreen = fullscreen

        self.state = MENU
        self.running = True
        self.clock = 0.0
        self.play_time = 0.0
        self.fps = 0.0
        self._fps_acc = 0.0
        self._fps_n = 0
        self.show_guide = False
        self.guide_t = 0.0
        self.guide_line = False
        self.achievements = set()
        self._campfire_t = 0.0
        self._portal_cd = 0.0
        self._ach_km = 0.0

        # 输入
        self.mouse_dx = 0.0
        self.mouse_dy = 0.0
        self.scroll = 0.0
        self.keys_pressed = set()      # 本帧的按下事件
        self.cursor_locked = False

        # 菜单
        self.menu_sel = 0
        self.pause_sel = 0
        self.journal_sel = 0
        self.journal_tab = 0
        self.has_save = os.path.exists(save_path())

        # 演出
        self.card_no = 0
        self.card_t = 0.0
        self.card_active = False
        self.banner_region = None
        self.banner_t = 0.0
        self.fade_total = 0.0
        self.fade_t = 0.0
        self.fade_active = False
        self.talk_ent = None
        self.show_debug = False

        self.world_ready = False
        self._init_window()
        self._init_gl()

    # ==================================================================
    # 初始化
    # ==================================================================
    def _init_window(self):
        if not glfw.init():
            raise RuntimeError("GLFW 初始化失败")
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)
        glfw.window_hint(glfw.SAMPLES, 0)
        glfw.window_hint(glfw.DEPTH_BITS, 24)
        if os.environ.get("RENWAI_HIDDEN"):
            glfw.window_hint(glfw.VISIBLE, False)

        monitor = glfw.get_primary_monitor() if self.fullscreen else None
        if monitor:
            mode = glfw.get_video_mode(monitor)
            self.req_w, self.req_h = mode.size.width, mode.size.height
        self.win = glfw.create_window(self.req_w, self.req_h, "远行假设 · Farwalk",
                                      monitor, None)
        if not self.win:
            glfw.terminate()
            raise RuntimeError("窗口创建失败 (需要 OpenGL 3.3)")
        glfw.make_context_current(self.win)
        glfw.swap_interval(1)

        glfw.set_key_callback(self.win, self._cb_key)
        glfw.set_cursor_pos_callback(self.win, self._cb_cursor)
        glfw.set_scroll_callback(self.win, self._cb_scroll)
        glfw.set_framebuffer_size_callback(self.win, self._cb_resize)
        self._last_cursor = None

    def _init_gl(self):
        self.ctx = moderngl.create_context()
        w, h = glfw.get_framebuffer_size(self.win)
        self.fb_w, self.fb_h = max(w, 16), max(h, 16)
        self.r = Renderer(self.ctx, self.fb_w, self.fb_h, self.quality)
        self.atlas = FontAtlas(self.ctx)
        self.ui = UIBatch(self.ctx, self.r, self.atlas)
        self.hud = HUD(self.ui, self.atlas, None)
        self.mood = dict(T.REGION_MOOD["wilds"])
        apply_mood(self.r, self.mood)
        self.cam = OrbitCamera()

    # ==================================================================
    # 世界构建
    # ==================================================================
    def _progress(self, text, p):
        self.ctx.screen.use()
        self.ctx.viewport = (0, 0, self.fb_w, self.fb_h)
        self.ctx.clear(0.02, 0.022, 0.028, 1.0)
        self.hud.begin(self.fb_w, self.fb_h, 0.016)
        self.hud.loading(text, p)
        self.hud.flush()
        glfw.swap_buffers(self.win)
        glfw.poll_events()

    def build_world(self):
        t0 = time.time()
        self._progress("正在描摹世界的轮廓", 0.03)
        self.gen = T.WorldGen()
        self.terrain = T.Terrain(self.ctx, self.r, self.gen, self._progress)
        self.water = T.Water(self.ctx, self.r)
        self.scatter = Scatter(self.ctx, self.r, self.terrain, self._progress, self.quality)
        self.entities = EntityWorld(self.ctx, self.r, self.terrain, self._progress)
        self._progress("正在绘制地图", 0.92)
        self.minimap = Minimap(self.ctx, self.terrain)
        self.hud.minimap = self.minimap

        self.player = Player(self.terrain)
        self.story = StoryState(self.player, self.entities, self._on_story_event)
        self._progress("准备好了", 1.0)
        self.world_ready = True
        self.build_seconds = time.time() - t0

    # ==================================================================
    # 回调
    # ==================================================================
    def _cb_key(self, win, key, scancode, action, mods):
        if action == glfw.PRESS:
            self.keys_pressed.add(key)
        elif action == glfw.RELEASE:
            self.keys_pressed.discard(key)

    def _cb_cursor(self, win, x, y):
        if self._last_cursor is None:
            self._last_cursor = (x, y)
            return
        dx = x - self._last_cursor[0]
        dy = y - self._last_cursor[1]
        self._last_cursor = (x, y)
        if self.cursor_locked:
            self.mouse_dx += dx
            self.mouse_dy += dy

    def _cb_scroll(self, win, dx, dy):
        self.scroll += dy

    def _cb_resize(self, win, w, h):
        if w <= 0 or h <= 0:
            return
        self.fb_w, self.fb_h = w, h
        self.r.resize(w, h)

    def _lock_cursor(self, on):
        if on == self.cursor_locked:
            return
        self.cursor_locked = on
        glfw.set_input_mode(self.win, glfw.CURSOR,
                            glfw.CURSOR_DISABLED if on else glfw.CURSOR_NORMAL)
        self._last_cursor = None

    def down(self, key):
        return glfw.get_key(self.win, key) == glfw.PRESS

    def pressed(self, *keys):
        for k in keys:
            if k in self._frame_press:
                return True
        return False

    # ==================================================================
    # 剧情事件
    # ==================================================================
    def _unlock_achieve(self, aid):
        if aid in self.achievements:
            return
        self.achievements.add(aid)
        for a, name, _d in ST.ACHIEVEMENTS:
            if a == aid:
                self.story.show_toast(f"成就 · {name}", 3.2)
                return

    def _on_story_event(self, kind, value):
        if kind == "chapter_card":
            self.card_no = int(value)
            self.card_t = 0.0
            self.card_active = True
        elif kind == "region":
            self.banner_region = value
            self.banner_t = 0.0
            if len(self.story.visited_regions) >= 6:
                self._unlock_achieve("region_all")
        elif kind == "unlock" and value == "echo_ability":
            self.story.show_toast("习得 · 回响   （Q 释放）", 3.4)
        elif kind == "collect":
            d = ST.COLLECTIBLES.get(value)
            if d:
                self.story.show_toast(f"拾得心跳残片 · {d['name']}", 3.0)
            n = len(self.story.inventory)
            for aid, cnt in (("frag_3", 3), ("frag_6", 6), ("frag_9", 9), ("frag_12", 12)):
                if n >= cnt:
                    self._unlock_achieve(aid)
        elif kind == "step":
            self.story.show_toast("目标完成", 2.0)
        elif kind == "chapter_end":
            self.save_game()
            if self.story.finished:
                self._unlock_achieve("ch_end")
        elif kind == "ending":
            self.state = ENDING
            self.end_t = 0.0
            self._lock_cursor(False)

    # ==================================================================
    # 主循环
    # ==================================================================
    def run(self):
        last = time.perf_counter()
        while not glfw.window_should_close(self.win) and self.running:
            now = time.perf_counter()
            dt = min(now - last, 0.1)
            last = now
            self.clock += dt
            self.r.time = self.clock

            self._frame_press = set(self.keys_pressed)
            self.keys_pressed.clear()
            glfw.poll_events()
            self._frame_press |= self.keys_pressed
            self.keys_pressed.clear()

            self._fps_acc += dt
            self._fps_n += 1
            if self._fps_acc > 0.4:
                self.fps = self._fps_n / self._fps_acc
                self._fps_acc = 0.0
                self._fps_n = 0

            if self.state == MENU:
                self._tick_menu(dt)
            elif self.state == ENDING:
                self._tick_ending(dt)
            else:
                self._tick_game(dt)

            self.mouse_dx = self.mouse_dy = 0.0
            self.scroll = 0.0
            glfw.swap_buffers(self.win)
        self.shutdown()

    # ==================================================================
    # 主菜单
    # ==================================================================
    def _tick_menu(self, dt):
        self._lock_cursor(False)
        if self.pressed(glfw.KEY_UP, glfw.KEY_W):
            self.menu_sel = (self.menu_sel - 1) % len(MENU_ITEMS)
        if self.pressed(glfw.KEY_DOWN, glfw.KEY_S):
            self.menu_sel = (self.menu_sel + 1) % len(MENU_ITEMS)
        if self.pressed(glfw.KEY_ENTER, glfw.KEY_KP_ENTER, glfw.KEY_SPACE):
            it = MENU_ITEMS[self.menu_sel]
            if it == "开始旅程":
                self._start(new_game=True)
                return
            if it == "继续旅程" and self.has_save:
                self._start(new_game=False)
                return
            if it == "退出":
                self.running = False
                return
        if self.pressed(glfw.KEY_ESCAPE):
            self.running = False
            return

        # 背景: 缓慢旋转的天空
        m = dict(T.REGION_MOOD["wilds"])
        m["exposure"] = 0.86
        m["vignette"] = 1.05
        apply_mood(self.r, m)
        yaw = self.clock * 0.035
        eye = m3.vec3(0.0, 6.0, 0.0)
        look = eye + m3.vec3(math.sin(yaw), 0.06, math.cos(yaw))
        view = m3.look_at(eye, look)
        proj = m3.perspective(58.0, self.fb_w / max(self.fb_h, 1), 0.1, 900.0)
        self.r.begin_scene(view, proj, eye)
        self.r.draw_sky()
        self.r.post_process()

        self.hud.begin(self.fb_w, self.fb_h, dt)
        self.hud.main_menu(MENU_ITEMS, self.menu_sel, self.has_save)
        self.hud.flush()

    def _start(self, new_game):
        self.state = LOADING
        if not self.world_ready:
            self.build_world()
        else:
            self._reset_world()
        if new_game:
            self.story.begin(0)
            self.play_time = 0.0
            self._unlock_achieve("start")
        else:
            self.load_game()
        self.cam.yaw = self.player.yaw + math.pi
        self.cam.update(0.016, self.player.pos, 0.0, self.terrain.height_at)
        self.state = PLAY
        self._lock_cursor(True)

    def _reset_world(self):
        """从菜单再次开始: 重置玩家与剧情, 世界几何复用。"""
        self.player = Player(self.terrain)
        sx, sz = 6.0, 74.0
        self.respawn_point = np.array([sx, self.terrain.height_at(sx, sz), sz], F32)
        self.story = StoryState(self.player, self.entities, self._on_story_event)
        self.show_guide = True
        self.guide_t = 0.0
        for e in self.entities.all_entities():
            e.taken = False
            e.highlight = 0.0
        self.card_active = False
        self.fade_active = False
        self.banner_region = None
        self.talk_ent = None

    # ==================================================================
    # 游戏
    # ==================================================================
    def _tick_game(self, dt):
        self._handle_game_input(dt)

        blocking = self.state in (PAUSE, JOURNAL, MAP, CHAR)
        sdt = 0.0 if blocking else dt
        if not blocking:
            self.play_time += dt

        # --- 演出计时 ---
        if self.card_active:
            self.card_t += sdt
            if self.card_t > CARD_IN + CARD_HOLD + CARD_OUT:
                self.card_active = False
                self.story.resume_after_card()
        if self.banner_region and self.banner_t < BANNER_TOTAL:
            self.banner_t += sdt
        if self.story.pending_fade > 0.0 and not self.fade_active:
            self.fade_total = float(self.story.pending_fade)
            self.fade_t = 0.0
            self.fade_active = True
            self.story.pending_fade = 0.0
        if self.fade_active:
            self.fade_t += sdt
            half = self.fade_total * 0.5
            self.r.fade_amount = (self.fade_t / half) if self.fade_t < half else \
                max(0.0, 1.0 - (self.fade_t - half) / half)
            if self.fade_t >= self.fade_total:
                self.fade_active = False
                self.r.fade_amount = 0.0

        story_busy = self.story.dialogue.active or self.card_active
        self.player.frozen = story_busy or blocking

        # 新手引导计时
        if self.show_guide and not blocking:
            self.guide_t += sdt
            if self.guide_t > 20.0:
                self.show_guide = False

        # --- 更新 ---
        self.story.update(sdt)
        if not blocking:
            inp = self._movement_input(story_busy)
            self.player.update(sdt, inp, self.cam)
            self._camera_update(sdt, story_busy)
            self._world_notify()
            if self.player.dead:
                self._respawn()

            # 行走距离成就
            km = self.player.distance_walked / 1000.0
            if km >= 10.0 and self._ach_km < 10:
                self._unlock_achieve("walk_10k")
            elif km >= 1.0 and self._ach_km < 1:
                self._unlock_achieve("walk_1k")
            self._ach_km = km

            # 篝火回血: 靠近任意篝火时快速恢复生命
            if self.player.hp < 100.0:
                self._campfire_t -= sdt
                best = 1e9
                for g in self.scatter.groups:
                    if g.get("tag") != "campfire":
                        continue
                    dx = g["pos"][:, 0] - self.player.pos[0]
                    dz = g["pos"][:, 2] - self.player.pos[2]
                    d = np.min(dx * dx + dz * dz)
                    if d < best:
                        best = d
                if best < 2.8 * 2.8:
                    self.player.hp = min(100.0, self.player.hp + 34.0 * sdt)
                    if self._campfire_t <= 0:
                        self._campfire_t = 3.5
                        self.story.show_toast("篝火温暖了你……", 1.6)

            # 传送门: 靠近传送门即传送至下一章节区域
            if self._portal_cd <= 0:
                for g in self.scatter.groups:
                    if g.get("tag") != "portal":
                        continue
                    dx = g["pos"][:, 0] - self.player.pos[0]
                    dz = g["pos"][:, 2] - self.player.pos[2]
                    d = np.min(dx * dx + dz * dz)
                    if d < 3.0 * 3.0:
                        # 找到最近 portal 所属 region
                        idx = int(np.argmin(dx * dx + dz * dz))
                        regs = list(T.REGION_POS.keys())
                        # 用 portal 实例坐标反查最近 region (粗略)
                        ppos = g["pos"][idx]
                        cur_reg = regs[min(range(len(regs)),
                                            key=lambda i: (T.REGION_POS[regs[i]][0] - ppos[0]) ** 2 +
                                            (T.REGION_POS[regs[i]][1] - ppos[2]) ** 2)]
                        self._warp_to_next_chapter(cur_reg)
                        self._portal_cd = 1.5
                        break
            else:
                self._portal_cd -= sdt

        self.entities.update(sdt, self.player.pos,
                             self.player.echo_radius, self.player.echo_origin)
        panim = "idle"
        if not blocking:
            _mv = inp.get("fwd") or inp.get("strafe")
            panim = "glide" if self.player.gliding else \
                    ("run" if self.player.sprinting else
                     ("walk" if _mv else "idle"))
        self.entities.upload_player(self.player.pos, self.player.yaw,
                                    self.player.squash, self.player.lean,
                                    anim=panim)
        self.scatter.update(self.cam.position)
        self._mood_update(sdt)

        self._render_scene()
        self._render_hud(dt, blocking)

    # ------------------------------------------------------------------
    def _movement_input(self, story_busy):
        if story_busy:
            return {}
        return dict(
            forward=self.down(glfw.KEY_W),
            back=self.down(glfw.KEY_S),
            left=self.down(glfw.KEY_A),
            right=self.down(glfw.KEY_D),
            sprint=self.down(glfw.KEY_LEFT_SHIFT) or self.down(glfw.KEY_RIGHT_SHIFT),
            jump_pressed=self.pressed(glfw.KEY_SPACE),
            jump_held=self.down(glfw.KEY_SPACE),
            echo=False,
        )

    def _handle_game_input(self, dt):
        dlg = self.story.dialogue

        # ---- 暂停 / 面板 ----
        if self.pressed(glfw.KEY_ESCAPE):
            if self.state in (JOURNAL, MAP):
                self.state = PLAY
                self._lock_cursor(True)
            elif self.state == PAUSE:
                self.state = PLAY
                self._lock_cursor(True)
            else:
                self.state = PAUSE
                self.pause_sel = 0
                self._lock_cursor(False)
            return

        if self.state == PAUSE:
            self._input_pause()
            return
        if self.state == JOURNAL:
            self._input_journal()
            return
        if self.state == MAP:
            if self.pressed(glfw.KEY_M, glfw.KEY_TAB):
                self.state = PLAY
                self._lock_cursor(True)
            return
        if self.state == CHAR:
            if self.pressed(glfw.KEY_C, glfw.KEY_ESCAPE, glfw.KEY_TAB, glfw.KEY_J):
                self.state = PLAY
                self._lock_cursor(True)
            return

        # ---- PLAY ----
        if self.pressed(glfw.KEY_C):
            self.state = CHAR
            self._lock_cursor(False)
            return
        if self.card_active:
            if self.pressed(glfw.KEY_SPACE, glfw.KEY_ENTER) and self.card_t > CARD_IN * 0.6:
                self.card_t = CARD_IN + CARD_HOLD
            return

        self.story.set_fast(self.down(glfw.KEY_LEFT_CONTROL) or self.down(glfw.KEY_RIGHT_CONTROL))

        if dlg.active:
            if dlg.choosing:
                if self.pressed(glfw.KEY_W, glfw.KEY_UP):
                    self.story.move_choice(-1)
                if self.pressed(glfw.KEY_S, glfw.KEY_DOWN):
                    self.story.move_choice(1)
                if self.pressed(glfw.KEY_SPACE, glfw.KEY_ENTER, glfw.KEY_E,
                                glfw.KEY_KP_ENTER):
                    self.story.choose(dlg.choice_i)
            elif self.pressed(glfw.KEY_SPACE, glfw.KEY_ENTER, glfw.KEY_E,
                              glfw.KEY_KP_ENTER):
                self.story.advance()
                if not self.story.dialogue.active:
                    self.talk_ent = None
            return

        if self.pressed(glfw.KEY_TAB, glfw.KEY_J):
            self.state = JOURNAL
            self.journal_sel = 0
            self._lock_cursor(False)
            return
        if self.pressed(glfw.KEY_M):
            self.state = MAP
            self._lock_cursor(False)
            return
        if self.pressed(glfw.KEY_F1):
            self.show_debug = not self.show_debug
        if self.pressed(glfw.KEY_F5):
            self.save_game()
            self.story.show_toast("已保存")
        if self.pressed(glfw.KEY_F11):
            self._toggle_fullscreen()
        if self.pressed(glfw.KEY_H) and self.show_guide:
            self.show_guide = False
        if self.pressed(glfw.KEY_Y):
            self.guide_line = not self.guide_line
        if self.pressed(glfw.KEY_EQUAL):  # = 调高鼠标灵敏度
            self.cam.sensitivity = min(0.010, self.cam.sensitivity + 0.0004)
            self.story.show_toast(f"鼠标灵敏度 {self.cam.sensitivity:.4f}（= / - 调节）", 1.6)
        if self.pressed(glfw.KEY_MINUS):  # - 调低鼠标灵敏度
            self.cam.sensitivity = max(0.001, self.cam.sensitivity - 0.0004)
            self.story.show_toast(f"鼠标灵敏度 {self.cam.sensitivity:.4f}（= / - 调节）", 1.6)

        if self.pressed(glfw.KEY_Q):
            if self.player.trigger_echo():
                self.story.show_toast("回响扩散开来……", 1.8)
                self._unlock_achieve("echo_first")
        if self.pressed(glfw.KEY_E):
            ent, _d = self.entities.nearest(self.player.pos, 4.4)
            if ent is not None:
                self.talk_ent = ent
                self.story.interact(ent)

    def _toggle_fullscreen(self):
        """F11: 窗口 <-> 全屏切换。"""
        self.fullscreen = not self.fullscreen
        mon = glfw.get_primary_monitor()
        if self.fullscreen:
            mode = glfw.get_video_mode(mon)
            glfw.set_window_monitor(self.win, mon, 0, 0,
                                    mode.width, mode.height, mode.refresh_rate)
        else:
            glfw.set_window_monitor(self.win, None, 60, 60,
                                    self.req_w, self.req_h, 0)
        self.story.show_toast("全屏模式" if self.fullscreen else "窗口模式", 1.5)

    def _warp_to_region(self, region):
        x, z = T.REGION_POS.get(region, (0.0, 0.0))
        y = self.terrain.height_at(x, z) + 1.2
        self.player.pos[:] = (x, y, z)
        self.player.vel[:] = 0
        self.cam.snap(self.player.pos)
        self.banner_region = region
        self.banner_t = 0.0
        # 地图分开: 重新加载该区域的实体 (远 region 清空)
        self.entities.reload_region(region)
        self.story.show_toast(f"已传送至 {ST.REGIONS[region]['name']}", 2.4)

    def _warp_to_next_chapter(self, current_region):
        order = ("wilds", "blackstone", "lostland",
                 "silenthall", "mutezone", "mirror")
        try:
            idx = order.index(current_region)
        except ValueError:
            return
        nxt = order[min(idx + 1, len(order) - 1)]
        self._warp_to_region(nxt)
        # 推进章节 (若非最后一章)
        cur = self.story.chapter_no()
        if cur < len(ST.QUESTS) - 1:
            self.story.begin(cur + 1)

    def _input_pause(self):
        if self.pressed(glfw.KEY_UP, glfw.KEY_W):
            self.pause_sel = (self.pause_sel - 1) % len(PAUSE_ITEMS)
        if self.pressed(glfw.KEY_DOWN, glfw.KEY_S):
            self.pause_sel = (self.pause_sel + 1) % len(PAUSE_ITEMS)
        if self.pressed(glfw.KEY_ENTER, glfw.KEY_SPACE, glfw.KEY_KP_ENTER):
            it = PAUSE_ITEMS[self.pause_sel]
            if it == "继续":
                self.state = PLAY
                self._lock_cursor(True)
            elif it == "手记":
                self.state = JOURNAL
                self.journal_sel = 0
            elif it == "世界地图":
                self.state = MAP
            elif it == "保存进度":
                self.save_game()
                self.story.show_toast("已保存")
            elif it == "返回主菜单":
                self.save_game()
                self.state = MENU
                self.menu_sel = 0
                self._lock_cursor(False)

    def _input_journal(self):
        if self.pressed(glfw.KEY_TAB):
            self.journal_tab = (self.journal_tab + 1) % 4
            self.journal_sel = 0
        if self.journal_tab == 3:
            n = len(ST.ACHIEVEMENTS)
        else:
            n = (len(ST.COLLECTIBLES), len(ST.NPCS), len(ST.REGIONS))[self.journal_tab]
        if self.pressed(glfw.KEY_UP, glfw.KEY_W):
            self.journal_sel = (self.journal_sel - 1) % n
        if self.pressed(glfw.KEY_DOWN, glfw.KEY_S):
            self.journal_sel = (self.journal_sel + 1) % n
        if self.pressed(glfw.KEY_J):
            self.state = PLAY
            self._lock_cursor(True)

    # ------------------------------------------------------------------
    def _camera_update(self, dt, story_busy):
        if self.cursor_locked and not story_busy:
            self.cam.handle_mouse(self.mouse_dx, self.mouse_dy)
        zoom = -self.scroll * 0.7

        # 对话演出机位
        tw = 0.0
        if story_busy and self.talk_ent is not None:
            a = self.player.pos
            b = self.talk_ent.pos
            mid = (a + b) * 0.5
            dx, dz = float(b[0] - a[0]), float(b[2] - a[2])
            L = math.hypot(dx, dz) or 1.0
            sx, sz = -dz / L, dx / L
            self.cam.cine_pos = m3.vec3(mid[0] + sx * 3.6, mid[1] + 2.15, mid[2] + sz * 3.6)
            self.cam.cine_look = m3.vec3(mid[0], mid[1] + 1.15, mid[2])
            tw = 0.78
        self.cam.cine_weight = m3.damp(self.cam.cine_weight, tw, 0.05, dt)
        self.cam.update(dt, self.player.pos, self.player.speed01,
                        self.terrain.height_at, zoom)

    def _world_notify(self):
        # 记录安全重生点 (站在地面上且不在水中时)
        p = self.player
        if p.grounded and not p.swimming and not p.dead:
            self.respawn_point = np.array(
                [float(p.pos[0]), float(p.pos[1]) + 0.5, float(p.pos[2])], F32)
        # 区域到达
        px, pz = float(self.player.pos[0]), float(self.player.pos[2])
        best, w = self.terrain.region_at(px, pz)
        self._region_w = w
        self._region = best
        if w[best] > 0.34:
            self.story.notify("reach", best)
        # 回响波掠过刻痕
        er = self.player.echo_radius
        if er > 0:
            ox, oz = float(self.player.echo_origin[0]), float(self.player.echo_origin[2])
            for e in self.entities.inters.values():
                d = math.hypot(e.pos[0] - ox, e.pos[2] - oz)
                if abs(d - er) < 7.0:
                    self.story.notify("echo", e.id)

    def _respawn(self):
        """死亡后回到最近安全点, 恢复部分生命。"""
        sp = self.respawn_point
        self.player.pos[:] = (float(sp[0]), float(sp[1]), float(sp[2]))
        self.player.vel[:] = (0.0, 0.0, 0.0)
        self.player.hp = MAX_HP * 0.6
        self.player.dead = False
        self.player.gliding = False
        self.player.climbing = False
        self.player.swimming = False
        self.player.stamina = min(self.player.stamina, 60.0)
        self.cam.snap(self.player.pos)
        self.r.desat_radial = 0.0
        self._unlock_achieve("revive")
        self.story.show_toast("你被风带回了安全之地……", 3.2)

    def _mood_update(self, dt):
        w = getattr(self, "_region_w", None)
        if w is None:
            best, w = self.terrain.region_at(float(self.player.pos[0]),
                                             float(self.player.pos[2]))
        tgt = blend_mood(w)
        approach_mood(self.mood, tgt, 1.0 - math.exp(-dt * 1.6))
        apply_mood(self.r, self.mood)
        # 剧情脉动
        self.r.pulse = 0.0
        self.r.desat_radial = 0.0
        if self.player.exhausted:
            self.r.desat_radial = 0.55
            self.r.pulse = 0.25
        if self.player.echo_radius > 0:
            self.r.echo_origin = tuple(float(x) for x in self.player.echo_origin)
            self.r.echo_radius = float(self.player.echo_radius)
        else:
            self.r.echo_radius = -1.0

    # ==================================================================
    # 渲染
    # ==================================================================
    def _render_scene(self):
        r, c = self.r, self.ctx
        # ---- 阴影 ----
        fwd = self.cam.forward_flat()
        center = self.player.pos + fwd * 22.0
        r.build_light_matrix(center, 100.0)
        r.begin_shadow()
        setm(r.p_sh_ter, "u_lightVP", r.light_vp)
        setm(r.p_sh_obj, "u_lightVP", r.light_vp)
        self.terrain.render(None, True, center, 170.0)
        self.scatter.render(shadow=True)
        self.entities.render(shadow=True)

        # ---- 主 pass ----
        aspect = self.fb_w / max(self.fb_h, 1)
        view = self.cam.view_matrix()
        proj = self.cam.proj_matrix(aspect, r.znear, r.zfar)
        r.begin_scene(view, proj, self.cam.position)
        frustum = m3.Frustum(r.view_proj)
        r.draw_sky()
        r.prepare_terrain()
        self.terrain.render(frustum, False, self.cam.position, 620.0)
        self.scatter.render(shadow=False)
        self.entities.render(shadow=False)
        r.prepare_water()
        self.water.render()
        c.disable(c.BLEND)
        r.post_process()

    def _render_hud(self, dt, blocking):
        hud = self.hud
        hud.begin(self.fb_w, self.fb_h, dt)

        if self.state == PLAY:
            dlg = self.story.dialogue
            if not self.card_active:
                hud.quest_tracker(self.story)
                hud.map_widget(self.player, self.entities, self.story, self.cam.yaw)
                kind, tpos = self._objective_pos()
                reg = ST.REGIONS.get(getattr(self, "_region", "wilds"), {}).get("name")
                hud.compass(self.cam.yaw, self.player.pos, tpos, reg)
                if self.guide_line:
                    hud.guide_arrow(self.cam.yaw, self.cam.pitch,
                                    self.player.pos, tpos)
                hud.health(self.player)
                hud.stamina(self.player)
                hud.echo_hint(self.player)
                if dlg.active:
                    pc = None
                    if self.talk_ent is not None and self.talk_ent.kind == "npc":
                        pc = self.talk_ent.data.get("color")
                    hud.dialogue(dlg, pc)
                else:
                    ent, _d = self.entities.nearest(self.player.pos, 4.4)
                    hud.prompt(ent)
                hud.region_banner(self.banner_region, self._banner_alpha())
                if self.story.toast:
                    hud.toast(self.story.toast, min(1.0, self.story.toast_t / 0.6))
            if self.show_guide:
                ga = min(1.0, max(0.0, (20.0 - self.guide_t) / 2.0))
                hud.guide(ga)
            hud.chapter_card(self.card_no, self._card_alpha())
        elif self.state == PAUSE:
            reg = ST.REGIONS.get(getattr(self, "_region", "wilds"), {}).get("name", "")
            hud.pause(PAUSE_ITEMS, self.pause_sel, reg, self.play_time,
                      self.story.progress01())
        elif self.state == JOURNAL:
            hud.journal(self.story, self.journal_sel, self.journal_tab,
                        self.achievements)
        elif self.state == MAP:
            hud.world_map(self.player, self.entities, self.story)
        elif self.state == CHAR:
            reg = ST.REGIONS.get(getattr(self, "_region", "wilds"), {}).get("name", "")
            hud.character(self.player, self.story, reg)

        # 受伤红屏 (所有状态之上)
        hud.hurt_overlay(self.player.hurt_t, self.player.hp / MAX_HP)

        if self.show_debug:
            hud.debug([
                f"FPS {self.fps:5.1f}   chunks {self.terrain.visible}   "
                f"scatter {self.scatter.drawn}",
                f"pos {self.player.pos[0]:7.1f} {self.player.pos[1]:6.1f} "
                f"{self.player.pos[2]:7.1f}   {self.player.state_name()}",
                f"region {getattr(self, '_region', '-')}   style {self.r.style:.2f}   "
                f"ch{self.story.chapter_no()} gate {self.story.gate_i}/"
                f"{len(self.story.gates)}   cursor {self.story.cursor}",
            ])
        hud.flush()

    def _card_alpha(self):
        if not self.card_active:
            return 0.0
        t = self.card_t
        if t < CARD_IN:
            return t / CARD_IN
        if t < CARD_IN + CARD_HOLD:
            return 1.0
        return max(0.0, 1.0 - (t - CARD_IN - CARD_HOLD) / CARD_OUT)

    def _banner_alpha(self):
        if not self.banner_region:
            return 0.0
        t = self.banner_t
        if t < 0.6:
            return t / 0.6
        if t < BANNER_TOTAL - 0.9:
            return 1.0
        return max(0.0, (BANNER_TOTAL - t) / 0.9)

    def _objective_pos(self):
        kind, target = self.story.objective_target()
        if target is None:
            return kind, None
        if kind == "reach" and target in T.REGION_POS:
            x, z = T.REGION_POS[target]
            return kind, m3.vec3(x, self.terrain.height_at(x, z), z)
        e = self.entities.get(target)
        if e is not None and not e.taken:
            return kind, e.pos
        return kind, None

    # ==================================================================
    # 结局
    # ==================================================================
    def _tick_ending(self, dt):
        self.end_t = getattr(self, "end_t", 0.0) + dt
        if self.pressed(glfw.KEY_ESCAPE, glfw.KEY_ENTER):
            self.state = MENU
            self.menu_sel = 0
            self.has_save = os.path.exists(save_path())
            return
        self.ctx.screen.use()
        self.ctx.viewport = (0, 0, self.fb_w, self.fb_h)
        self.ctx.clear(0.01, 0.011, 0.014, 1.0)
        self.hud.begin(self.fb_w, self.fb_h, dt)
        self.hud.ending(self.end_t, ST.ENDING["lines"], ST.ENDING["final"])
        self.hud.flush()

    # ==================================================================
    # 存档
    # ==================================================================
    def save_game(self):
        if not self.world_ready:
            return
        data = dict(version=1, play_time=self.play_time,
                    player=self.player.save_dict(), story=self.story.save_dict(),
                    achievements=sorted(self.achievements))
        try:
            with open(save_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            self.has_save = True
        except OSError as ex:
            print("保存失败:", ex)

    def load_game(self):
        try:
            with open(save_path(), "r", encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            self.story.begin(0)
            return
        self.play_time = float(d.get("play_time", 0.0))
        self.achievements = set(d.get("achievements", []))
        self.player.load_dict(d.get("player", {}))
        self.story.load_dict(d.get("story", {}))
        self.show_guide = False  # 读档玩家不需要新手引导
        if self.story.finished:
            self.story.begin(len(ST.QUESTS) - 1)
            return
        self.card_active = False
        self.story.resume_after_card()

    def shutdown(self):
        try:
            glfw.terminate()
        except Exception:
            pass


# --------------------------------------------------------------------------
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    quality = "high"
    fullscreen = False
    w, h = 1920, 1080
    for a in argv:
        if a in ("--low", "--medium", "--high"):
            quality = a[2:]
        elif a == "--fullscreen":
            fullscreen = True
        elif a.startswith("--size="):
            try:
                w, h = (int(x) for x in a.split("=", 1)[1].split("x"))
            except ValueError:
                pass
    g = Game(w, h, quality, fullscreen)
    try:
        g.run()
    finally:
        g.shutdown()


if __name__ == "__main__":
    main()
