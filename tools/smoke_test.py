"""
smoke_test.py -- 无人值守自检 (渲染 + 剧情全流程)

流程:
    建世界 -> 开局 -> 机器人玩家自动推进全部 8 章 -> 抵达结局
机器人策略:
    1. 朝当前目标点直线奔跑 (自动冲刺 / 遇坎跳跃)
    2. 若 WARP_AFTER 秒内最近距离没有明显缩短, 判定被地形卡住 -> 传送到目标附近
    3. 到达后按目标类型触发 interact / echo / reach
每 shot_every 帧截屏一次到 tools/shots/, 用于人工肉眼复核画面。

用法:
    python tools/smoke_test.py [--seconds=600] [--quality=medium] [--no-warp]
"""
from __future__ import annotations

import math
import os
import sys
import time

os.environ.setdefault("RENWAI_HIDDEN", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
import glfw  # noqa: E402

from src.game import main as M  # noqa: E402
from src.data import story as ST  # noqa: E402

SHOTS = os.path.join(ROOT, "tools", "shots")
WARP_AFTER = 3.5        # 卡住多少秒后传送
ARRIVE = 3.2            # 判定到达的平面距离


def save_shot(game, name):
    os.makedirs(SHOTS, exist_ok=True)
    data = game.ctx.screen.read(components=3, alignment=1)
    img = np.frombuffer(data, np.uint8).reshape(game.fb_h, game.fb_w, 3)[::-1]
    try:
        from PIL import Image
        Image.fromarray(img).save(os.path.join(SHOTS, name))
    except ImportError:
        pass


def log(msg):
    print(msg, flush=True)


def steer(game, want, d):
    """把"朝目标走"翻译成移动输入。"""
    dx = float(want[0]) - float(game.player.pos[0])
    dz = float(want[2]) - float(game.player.pos[2])
    game.cam.yaw = math.atan2(-dx, -dz)
    return dict(forward=True, back=False, left=False, right=False,
                sprint=d > 18.0, jump_pressed=False, jump_held=False, echo=False)


def warp(game, want):
    """传送到目标旁边 (仅测试用, 正式游戏没有这个能力)。"""
    x = float(want[0]) + 2.0
    z = float(want[2]) + 2.0
    y = game.terrain.height_at(x, z) + 0.6
    game.player.pos[:] = (x, y, z)
    game.player.vel[:] = (0.0, 0.0, 0.0)
    game.player.stamina = 100.0
    game.cam.snap(game.player.pos)


def fire(game, kind, tid):
    """到达目标后按类型触发对应事件。"""
    ent = game.entities.get(tid) if tid else None
    if kind == "echo":
        game.player.echo_unlocked = True
        game.player.stamina = 100.0
        game.player.trigger_echo()
        game.story.notify("echo", tid)
        if ent is not None:
            game.story.interact(ent)
    elif kind == "reach":
        game.story.notify("reach", tid)
    elif ent is not None:
        game.story.interact(ent)
        game.talk_ent = ent
    else:
        game.story.notify(kind, tid)


def run(max_seconds=600.0, shot_every=900, quality="medium", allow_warp=True, verbose=False):
    game = M.Game(1280, 720, quality=quality)
    t0 = time.time()
    game.build_world()
    build_s = time.time() - t0
    log(f"[build] {build_s:.1f}s  chunks={len(game.terrain.chunks)} "
          f"scatter_groups={len(game.scatter.groups)} "
          f"npc={len(game.entities.npcs)} inter={len(game.entities.inters)} "
          f"coll={len(game.entities.colls)}")

    game.story.begin(0)
    game.state = M.PLAY
    dt = 1.0 / 60.0
    frame = 0
    stuck_t = 0.0
    best_d = 1e9
    last_target = None
    warps = 0
    t_start = time.time()
    warn = []
    chapters = []
    total_steps = sum(len(q["steps"]) for q in ST.QUESTS)

    while time.time() - t_start < max_seconds:
        frame += 1
        game.clock += dt
        game.r.time = game.clock
        game._frame_press = set()
        glfw.poll_events()

        # ---- 演出推进 (章节卡 / 区域横幅 / 淡入淡出) ----
        if game.card_active:
            game.card_t += dt
            if game.card_t > M.CARD_IN + M.CARD_HOLD + M.CARD_OUT:
                game.card_active = False
                game.story.resume_after_card()
        game.story.pending_fade = 0.0
        if game.banner_region and game.banner_t < M.BANNER_TOTAL:
            game.banner_t += dt

        busy = game.story.dialogue.active or game.card_active
        game.player.frozen = busy
        game.story.set_fast(True)
        game.story.update(dt)

        # ---- 目标跟踪 (每帧都更新, 卡片期间也算 stuck) ----
        kind, tid = game.story.objective_target()
        _k, tp = game._objective_pos()
        d = 1e9
        if tp is not None:
            d = math.hypot(float(tp[0]) - float(game.player.pos[0]),
                           float(tp[2]) - float(game.player.pos[2]))
            if (kind, tid) != last_target:
                last_target, best_d, stuck_t = (kind, tid), d, 0.0
            if d < best_d - 0.2:
                best_d, stuck_t = d, 0.0
            else:
                stuck_t += dt

        # ---- 机器人行为 ----
        if game.story.dialogue.active:
            if game.story.dialogue.choosing:
                game.story.choose(game.story.dialogue.choice_i)
            else:
                game.story.dialogue.chars = len(game.story.dialogue.current_line)
                game.story.advance()
        elif not game.card_active:
            if tp is None:
                game.player.update(dt, {}, game.cam)
                game._world_notify()
            else:
                # 剧情速通：目标较远时直接传送到附近（本测试只验证剧情闸与渲染）
                if allow_warp and d > 8.0:
                    warp(game, tp)
                    warps += 1
                    stuck_t = 0.0
                    best_d = 1e9
                else:
                    game.player.update(dt, steer(game, tp, d), game.cam)
                game._world_notify()
                if d < ARRIVE:
                    fire(game, kind, tid)
                    stuck_t = 0.0
                elif allow_warp and stuck_t > WARP_AFTER:
                    warp(game, tp)
                    warps += 1
                    stuck_t = 0.0
                    best_d = 1e9
        else:
            game.player.update(dt, {}, game.cam)

        game.cam.update(dt, game.player.pos, game.player.speed01, game.terrain.height_at)
        game.entities.update(dt, game.player.pos, game.player.echo_radius,
                             game.player.echo_origin)
        game.entities.upload_player(game.player.pos, game.player.yaw,
                                    game.player.squash, game.player.lean)
        game.scatter.update(game.cam.position)
        game._mood_update(dt)
        game._render_scene()
        game._render_hud(dt, False)
        glfw.swap_buffers(game.win)

        ch = game.story.chapter_no()
        if not chapters or chapters[-1] != ch:
            chapters.append(ch)
            save_shot(game, f"chapter_{ch:02d}.png")
        if frame % shot_every == 0:
            save_shot(game, f"scene_{frame:06d}.png")
            if verbose:
                kind, tid = game.story.objective_target()
                log(f"[progress] frame={frame:06d} chapter={ch} step={len(game.story.completed_steps)}/{total_steps} "
                      f"warp={warps} obj={kind}:{tid} pos=({game.player.pos[0]:.1f},{game.player.pos[2]:.1f})")

        if game.state == M.ENDING or game.story.finished:
            save_shot(game, "ending.png")
            break

    el = time.time() - t_start
    total = sum(len(q["steps"]) for q in ST.QUESTS)
    log(f"[run] frames={frame} {el:.1f}s  avg {frame / max(el, 1e-6):.1f} fps  warps={warps}")
    log(f"[story] chapter={game.story.chapter_no()} "
          f"steps={len(game.story.completed_steps)}/{total} "
          f"fragments={len(game.story.inventory)}/{len(ST.COLLECTIBLES)} "
          f"finished={game.story.finished}")
    log(f"[regions] {sorted(game.story.visited_regions)}")
    log(f"[chapters] {chapters}")
    ok = game.story.finished
    if not ok:
        warn.append("未走到结局")
    for w in warn:
        log(f"[warn] {w}")
    log(f"[result] {'PASS' if ok else 'FAIL'}")
    game.shutdown()
    return ok


def main(argv):
    kw = dict(max_seconds=600.0, quality="medium", allow_warp=True, verbose=False)
    for a in argv:
        if a.startswith("--seconds="):
            kw["max_seconds"] = float(a.split("=", 1)[1])
        elif a.startswith("--quality="):
            kw["quality"] = a.split("=", 1)[1]
        elif a == "--no-warp":
            kw["allow_warp"] = False
        elif a == "--verbose":
            kw["verbose"] = True
    return 0 if run(**kw) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
