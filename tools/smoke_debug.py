"""快速调试 smoke_test 卡住的原因, 只跑 5 秒, 大量输出。"""
import os
import sys
import math
import time

os.environ.setdefault("RENWAI_HIDDEN", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import glfw
from src.game import main as M

game = M.Game(1280, 720, quality="low")
game.build_world()
game.story.begin(0)
game.state = M.PLAY

dt = 1 / 60.0
for i in range(300):
    game._frame_press = set()
    glfw.poll_events()
    if game.card_active:
        game.card_t += dt
        if game.card_t > M.CARD_IN + M.CARD_HOLD + M.CARD_OUT:
            game.card_active = False
            game.story.resume_after_card()
    busy = game.story.dialogue.active or game.card_active
    game.player.frozen = busy
    game.story.set_fast(True)
    game.story.update(dt)

    kind, tid = game.story.objective_target()
    _k, tp = game._objective_pos()
    if tp is None:
        print(f"{i:03d} obj=None kind={kind} waiting={game.story.waiting} dlg={game.story.dialogue.active}")
        game.player.update(dt, {}, game.cam)
    else:
        d = math.hypot(tp[0] - game.player.pos[0], tp[2] - game.player.pos[2])
        dx = tp[0] - game.player.pos[0]
        dz = tp[2] - game.player.pos[2]
        game.cam.yaw = math.atan2(-dx, -dz)
        game.player.update(dt, dict(forward=True, sprint=False), game.cam)
        game._world_notify()
        if d < 3.2:
            print(f"{i:03d} ARRIVE kind={kind} tid={tid} pos={game.player.pos}")
            ent = game.entities.get(tid) if tid else None
            if kind == "echo":
                game.player.echo_unlocked = True
                game.player.trigger_echo()
                game.story.notify("echo", tid)
            elif ent is not None:
                game.story.interact(ent)
                game.talk_ent = ent
            elif kind == "reach":
                game.story.notify("reach", tid)
    if game.story.dialogue.active:
        game.story.dialogue.chars = len(game.story.dialogue.current_line)
        game.story.advance()
    game.cam.update(dt, game.player.pos, game.player.speed01, game.terrain.height_at)
    game.entities.update(dt, game.player.pos, game.player.echo_radius, game.player.echo_origin)
    game._mood_update(dt)
    game._render_scene()
    game._render_hud(dt, False)
    glfw.swap_buffers(game.win)
    if i % 60 == 0:
        print(f"{i:03d} ch={game.story.chapter_no()} steps={len(game.story.completed_steps)} "
              f"dlg={game.story.dialogue.active} waiting={game.story.waiting} "
              f"obj={kind}:{tid} d={d if tp is not None else -1:.1f} pos={game.player.pos}")
    if game.story.finished:
        print("FINISHED")
        break

game.shutdown()
