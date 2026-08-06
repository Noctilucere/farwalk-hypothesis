"""
story_walk.py -- 纯逻辑剧情通关校验 (不开窗口 / 不建世界)

用最短路径驱动 StoryState 走完 8 章:
    对话中 -> advance / choose
    等待闸门 -> 直接 notify(kind, target) 满足条件
校验:
    1. 8 章全部走通, finished == True
    2. QUESTS 中所有 step 都被完成
    3. 所有 DIALOGUES 节点可达性统计 (孤儿节点告警)
    4. 目标 id 是否都存在于 NPCS / INTERACTABLES / COLLECTIBLES / REGIONS
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.data import story as ST            # noqa: E402
from src.game.story_state import StoryState  # noqa: E402


class FakePlayer:
    echo_unlocked = False


def valid_targets():
    ids = set(ST.NPCS) | set(ST.INTERACTABLES) | set(ST.COLLECTIBLES) | set(ST.REGIONS)
    return ids


def walk(verbose=True):
    events = []
    visited_nodes = set()

    def on_event(kind, val):
        events.append((kind, val))

    st = StoryState(player=FakePlayer(), world=None, on_event=on_event)
    st.set_fast(True)
    st.begin(0)
    st.resume_after_card()

    guard = 0
    chapters_seen = []
    while not st.finished and guard < 20000:
        guard += 1
        if st.dialogue.active:
            visited_nodes.add(st.dialogue.node_id)
            # 逐字机直接跳到底
            st.dialogue.chars = len(st.dialogue.current_line)
            if st.dialogue.choosing:
                st.choose(st.dialogue.choice_i)
            else:
                st.advance()
            continue
        # 处理章节卡: begin/_chapter_complete 之后需要 resume
        if st.waiting:
            kind, target = st.objective_target()
            if kind is None:
                st.resume_after_card()
                if not st.dialogue.active and not st.waiting:
                    break
                if st.dialogue.active:
                    continue
                # 仍然 waiting 且没有目标 -> 死锁
                print(f"[FAIL] 死锁: chapter={st.chapter_no()} cursor={st.cursor} "
                      f"gate_i={st.gate_i}/{len(st.gates)}")
                return False
            st.notify(kind, target)
            if not st.dialogue.active and st.waiting:
                # notify 没能打开闸门 -> 目标写错
                print(f"[FAIL] 闸门无法满足: chapter={st.chapter_no()} "
                      f"step={st.gates[st.gate_i] if st.gate_i < len(st.gates) else None} "
                      f"kind={kind} target={target}")
                return False
            continue
        st.resume_after_card()
        if not st.dialogue.active and not st.waiting:
            print(f"[FAIL] 空转: cursor={st.cursor}")
            return False

    total_steps = sum(len(q["steps"]) for q in ST.QUESTS)
    chapters_seen = [v for k, v in events if k == "chapter_card"]
    ends = [v for k, v in events if k == "chapter_end"]
    missing = []
    for q in ST.QUESTS:
        for s in q["steps"]:
            if s["id"] not in st.completed_steps:
                missing.append((q["chapter"], s["id"], s["kind"], s["target"]))

    orphans = sorted(set(ST.DIALOGUES) - visited_nodes)
    bad_targets = []
    ok_ids = valid_targets()
    for q in ST.QUESTS:
        for s in q["steps"]:
            if s["kind"] != "reach" and s["target"] not in ok_ids:
                bad_targets.append((s["id"], s["kind"], s["target"]))
            if s["kind"] == "reach" and s["target"] not in ST.REGIONS:
                bad_targets.append((s["id"], s["kind"], s["target"]))

    if verbose:
        print(f"[walk] iterations={guard}")
        print(f"[walk] chapters entered={chapters_seen}")
        print(f"[walk] chapters ended  ={ends}")
        print(f"[walk] steps {len(st.completed_steps)}/{total_steps}")
        print(f"[walk] fragments {len(st.inventory)}/{len(ST.COLLECTIBLES)} -> {st.inventory}")
        print(f"[walk] flags {sorted(st.flags)}")
        print(f"[walk] unlocked {sorted(st.unlocked)}")
        print(f"[walk] regions {sorted(st.visited_regions)}")
        print(f"[walk] dialogue nodes visited {len(visited_nodes)}/{len(ST.DIALOGUES)}")
        if orphans:
            print(f"[note] 未经过的对话节点 ({len(orphans)}): {orphans[:20]}"
                  f"{' ...' if len(orphans) > 20 else ''}")
        if missing:
            print(f"[warn] 未完成的 step ({len(missing)}):")
            for m in missing:
                print("        ", m)
        if bad_targets:
            print(f"[FAIL] step 目标 id 不存在 ({len(bad_targets)}):")
            for b in bad_targets:
                print("        ", b)

    ok = st.finished and not missing and not bad_targets
    print("[result]", "PASS 全线可通关" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if walk() else 1)
