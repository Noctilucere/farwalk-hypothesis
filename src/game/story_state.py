"""
story_state.py -- 主线状态机 (章节 / 任务 / 对话)

设计:
    每一章都是一条对话链 chN_01 -> chN_02 -> ... -> None。
    链上若干节点的 on_end 会完成一个任务步骤 (quest step), 这些节点即"闸门"。
    游戏流程 = 在闸门之间反复地: 暂停对话 -> 玩家去做那件事 -> 恢复对话。

    闸门顺序按对话链的实际顺序推导 (而非 QUESTS.steps 的书写顺序),
    因此叙事节奏与任务提示始终一致。

事件类型: reach(到达区域) / talk(交谈) / touch(检视) / echo(回响) / collect(拾取)
"""
from __future__ import annotations

from ..data import story as ST

TYPE_SPEED = 38.0          # 字/秒
TYPE_SPEED_FAST = 190.0


def _step_index():
    idx = {}
    for q in ST.QUESTS:
        for s in q["steps"]:
            idx[s["id"]] = (q, s)
    return idx


STEP_INDEX = _step_index()


def gate_order(chapter_id):
    """沿默认对话链推导闸门顺序 -> [(step_id, node_id), ...]"""
    order, seen = [], set()
    node = f"{chapter_id}_01"
    while node and node in ST.DIALOGUES and node not in seen:
        seen.add(node)
        d = ST.DIALOGUES[node]
        oe = d.get("on_end") or {}
        if "quest" in oe:
            order.append((oe["quest"], node))
        node = d.get("next")
    return order


class Dialogue:
    """单个对话节点的播放器 (逐字机 + 选项)。"""

    def __init__(self):
        self.active = False
        self.node_id = None
        self.node = None
        self.page = 0
        self.chars = 0.0
        self.speaker = ""
        self.portrait = None
        self.choice_i = 0
        self.choosing = False
        self.fast = False
        self.temp = False     # 临时闲聊/检视对话 (不走剧情链, 结束即关闭)

    def start(self, node_id):
        self.node_id = node_id
        self.node = ST.DIALOGUES[node_id]
        self.active = True
        self.page = 0
        self.chars = 0.0
        self.speaker = self.node.get("speaker") or ""
        self.portrait = self.node.get("portrait")
        self.choosing = False
        self.choice_i = 0

    def stop(self):
        self.active = False
        self.node = None
        self.node_id = None
        self.choosing = False

    @property
    def lines(self):
        return self.node["lines"] if self.node else []

    @property
    def current_line(self):
        if not self.node:
            return ""
        return self.lines[min(self.page, len(self.lines) - 1)]

    @property
    def visible_text(self):
        return self.current_line[:int(self.chars)]

    @property
    def typing(self):
        return self.chars < len(self.current_line)

    def update(self, dt):
        if not self.active or self.choosing:
            return
        sp = TYPE_SPEED_FAST if self.fast else TYPE_SPEED
        self.chars = min(len(self.current_line), self.chars + dt * sp)

    def advance(self):
        """返回 'typed' / 'page' / 'choices' / 'end'"""
        if not self.active:
            return "end"
        if self.typing:
            self.chars = len(self.current_line)
            return "typed"
        if self.page < len(self.lines) - 1:
            self.page += 1
            self.chars = 0.0
            return "page"
        if self.node.get("choices"):
            self.choosing = True
            return "choices"
        return "end"

    def start_temp(self, speaker, lines):
        """播放一段临时的闲聊/检视对话，结束即关闭，不进入剧情链。"""
        self.active = True
        self.temp = True
        self.node_id = None
        self.node = {"lines": list(lines), "speaker": speaker, "next": None}
        self.page = 0
        self.chars = 0.0
        self.speaker = speaker
        self.portrait = None
        self.choosing = False
        self.choice_i = 0


class StoryState:
    def __init__(self, player=None, world=None, on_event=None):
        self.player = player
        self.world = world
        self.on_event = on_event or (lambda *a, **k: None)

        self.flags = set()
        self.inventory = []          # 收集到的残片 id (有序)
        self.unlocked = set()
        self.events = set()          # (kind, target)
        self.completed_steps = set()

        self.chapter = 0             # QUESTS 下标
        self.gates = []
        self.gate_i = 0
        self.cursor = None
        self.waiting = True
        self.finished = False

        self.dialogue = Dialogue()
        self.pending_fade = 0.0
        self.objective = None        # (step_dict, quest_dict)
        self.visited_regions = set()
        self.toast = None
        self.toast_t = 0.0

    # ------------------------------------------------------------------
    @property
    def quest(self):
        return ST.QUESTS[self.chapter] if self.chapter < len(ST.QUESTS) else None

    def chapter_no(self):
        q = self.quest
        return q["chapter"] if q else len(ST.QUESTS)

    def begin(self, chapter=0):
        self.chapter = chapter
        q = self.quest
        self.gates = gate_order(q["id"])
        self.gate_i = 0
        self.cursor = f"{q['id']}_01"
        self.waiting = True
        self.on_event("chapter_card", q["chapter"])
        self._check_gate()

    # ------------------------------------------------------------------
    def notify(self, kind, target):
        key = (kind, target)
        if key in self.events:
            already = True
        else:
            already = False
            self.events.add(key)
        if kind == "reach" and target not in self.visited_regions:
            self.visited_regions.add(target)
            self.on_event("region", target)
        if self.waiting and not self.dialogue.active:
            self._check_gate()
        return not already

    def _gate_step(self):
        if self.gate_i >= len(self.gates):
            return None
        sid = self.gates[self.gate_i][0]
        q, s = STEP_INDEX.get(sid, (None, None))
        return s

    def _gate_satisfied(self):
        s = self._gate_step()
        if s is None:
            return True
        return (s["kind"], s["target"]) in self.events

    def _check_gate(self):
        """若当前闸门条件已满足则继续播放对话, 否则挂起等待。"""
        if self.finished or self.cursor is None:
            return
        s = self._gate_step()
        self.objective = s
        if self._gate_satisfied():
            self.waiting = False
            self.dialogue.start(self.cursor)
            self.on_event("dialogue_start", self.cursor)
        else:
            self.waiting = True

    # ------------------------------------------------------------------
    def update(self, dt):
        self.dialogue.update(dt)
        if self.toast_t > 0:
            self.toast_t -= dt
            if self.toast_t <= 0:
                self.toast = None

    def set_fast(self, v):
        self.dialogue.fast = bool(v)

    # ------------------------------------------------------------------
    def advance(self):
        """玩家按下确认键。"""
        if not self.dialogue.active:
            return
        r = self.dialogue.advance()
        if r == "end":
            if self.dialogue.temp:
                # 临时闲聊/检视对话: 结束即关闭, 不推进剧情
                self.dialogue.stop()
                self.dialogue.temp = False
            else:
                self._finish_node(self.dialogue.node.get("next"))

    def choose(self, i):
        node = self.dialogue.node
        if not node:
            return
        ch = node.get("choices") or []
        if not ch:
            return
        i = max(0, min(i, len(ch) - 1))
        c = ch[i]
        if c.get("flag"):
            self.flags.add(c["flag"])
        self._finish_node(c.get("goto") or node.get("next"))

    def move_choice(self, d):
        node = self.dialogue.node
        if node and self.dialogue.choosing:
            n = len(node.get("choices") or [])
            if n:
                self.dialogue.choice_i = (self.dialogue.choice_i + d) % n

    # ------------------------------------------------------------------
    def _finish_node(self, next_id):
        node = self.dialogue.node
        oe = (node.get("on_end") or {}) if node else {}
        gate_done = False

        if "flag" in oe:
            self.flags.add(oe["flag"])
        if "unlock" in oe:
            self.unlocked.add(oe["unlock"])
            if oe["unlock"] == "echo_ability" and self.player is not None:
                self.player.echo_unlocked = True
                self.on_event("unlock", "echo_ability")
        if "give" in oe:
            self._give(oe["give"])
        if "fade" in oe:
            self.pending_fade = float(oe["fade"])
        if "quest" in oe:
            sid = oe["quest"]
            self.completed_steps.add(sid)
            self.events.add(tuple(self._step_event(sid)))
            if self.gate_i < len(self.gates) and self.gates[self.gate_i][0] == sid:
                self.gate_i += 1
                gate_done = True
            self.on_event("step", sid)

        self.cursor = next_id
        if next_id is None:
            self.dialogue.stop()
            self._chapter_complete()
            return

        if gate_done:
            self.dialogue.stop()
            self._check_gate()
            if not self.dialogue.active:
                self.on_event("dialogue_end", None)
        else:
            self.dialogue.start(next_id)

    def _step_event(self, sid):
        q, s = STEP_INDEX.get(sid, (None, None))
        if s is None:
            return ("step", sid)
        return (s["kind"], s["target"])

    def _give(self, cid):
        if cid not in self.inventory:
            self.inventory.append(cid)
        if self.world is not None:
            e = self.world.colls.get(cid)
            if e:
                e.taken = True

    # ------------------------------------------------------------------
    def _chapter_complete(self):
        self.on_event("chapter_end", self.chapter_no())
        nxt = self.chapter + 1
        if nxt >= len(ST.QUESTS):
            self.finished = True
            self.flags.add("ending_reached")
            self.on_event("ending", None)
            return
        self.chapter = nxt
        q = self.quest
        self.gates = gate_order(q["id"])
        self.gate_i = 0
        self.cursor = f"{q['id']}_01"
        self.waiting = True
        self.objective = self._gate_step()
        self.on_event("chapter_card", q["chapter"])

    def resume_after_card(self):
        self._check_gate()

    # ------------------------------------------------------------------
    # 与世界的交互入口
    # ------------------------------------------------------------------
    def interact(self, ent):
        if ent is None or self.dialogue.active:
            return None
        if ent.kind == "npc":
            self.notify("talk", ent.id)
            if not self.dialogue.active:
                # 闸门未满足: 播放该角色的闲聊台词, 交互永远有内容
                idle = ent.data.get("idle") or ["（他沉默地看了你一会儿。）"]
                import random as _r
                self.dialogue.start_temp(ent.name, [_r.choice(idle)])
            return "talk"
        if ent.kind == "inter":
            self.notify("touch", ent.id)
            self.notify("echo", ent.id)
            if not self.dialogue.active:
                # 检视反馈: 展示该处的 lore 文本
                d = ent.data
                lines = [d.get("desc") or d.get("name", "此处")]
                self.dialogue.start_temp(d.get("name", "此处"), lines)
            return "touch"
        if ent.kind == "coll":
            ent.taken = True
            if ent.id not in self.inventory:
                self.inventory.append(ent.id)
            self.notify("collect", ent.id)
            self.on_event("collect", ent.id)
            return "collect"
        return None

    def echo_ping(self, entities):
        for e in entities:
            if e.kind == "inter":
                self.notify("echo", e.id)

    def show_toast(self, text, t=2.6):
        self.toast = text
        self.toast_t = t

    # ------------------------------------------------------------------
    def objective_text(self):
        if self.finished:
            return "旅程已经走到镜子前面。"
        if self.dialogue.active:
            return None
        s = self.objective
        if s is None:
            return None
        return s["text"]

    def objective_target(self):
        """返回需要指引的世界目标 id 或区域名。"""
        s = self.objective
        if s is None or self.dialogue.active:
            return None, None
        return s["kind"], s["target"]

    def progress01(self):
        total = sum(len(q["steps"]) for q in ST.QUESTS)
        return len(self.completed_steps) / max(total, 1)

    # ------------------------------------------------------------------
    def save_dict(self):
        return dict(chapter=self.chapter, gate_i=self.gate_i, cursor=self.cursor,
                    waiting=self.waiting, finished=self.finished,
                    flags=sorted(self.flags), inventory=list(self.inventory),
                    unlocked=sorted(self.unlocked),
                    events=[list(e) for e in self.events],
                    steps=sorted(self.completed_steps),
                    regions=sorted(self.visited_regions))

    def load_dict(self, d):
        self.chapter = int(d.get("chapter", 0))
        self.gates = gate_order(ST.QUESTS[min(self.chapter, len(ST.QUESTS) - 1)]["id"])
        self.gate_i = int(d.get("gate_i", 0))
        self.cursor = d.get("cursor")
        self.waiting = True
        self.finished = bool(d.get("finished", False))
        self.flags = set(d.get("flags", []))
        self.inventory = list(d.get("inventory", []))
        self.unlocked = set(d.get("unlocked", []))
        self.events = set(tuple(e) for e in d.get("events", []))
        self.completed_steps = set(d.get("steps", []))
        self.visited_regions = set(d.get("regions", []))
        if self.player is not None and "echo_ability" in self.unlocked:
            self.player.echo_unlocked = True
        if self.world is not None:
            for cid in self.inventory:
                e = self.world.colls.get(cid)
                if e:
                    e.taken = True
        self.dialogue.stop()
        self.objective = self._gate_step()
