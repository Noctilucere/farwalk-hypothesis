// StoryState.cs — 剧情推进状态机
using System;
using System.Collections.Generic;

namespace Farwalk.Game
{
    public class Dialogue
    {
        public DialogueNode? Node;
        public bool Active;
        public bool Temp;
        public int Page;
        public float Chars;
        public string Speaker = "";
        public bool Typing => Chars < CurrentLine.Length;

        public string[] Lines => Node?.Lines ?? Array.Empty<string>();
        public string CurrentLine => Lines.Length == 0 ? "" : Lines[Math.Min(Page, Lines.Length - 1)];
        public string VisibleText => CurrentLine.Substring(0, Math.Min((int)Chars, CurrentLine.Length));

        public void Start(string nodeId)
        {
            Node = StoryData.Nodes[nodeId];
            Active = true; Temp = false; Page = 0; Chars = 0;
            Speaker = Node.Speaker;
        }

        public void StartTemp(string speaker, string line)
        {
            Node = new DialogueNode { Speaker = speaker, Lines = new[] { line } };
            Active = true; Temp = true; Page = 0; Chars = 0; Speaker = speaker;
        }

        public void Stop() { Active = false; Node = null; Temp = false; }

        public void Update(float dt, bool fast)
        {
            if (!Active) return;
            float sp = fast ? 90f : 30f;
            Chars = Math.Min(Chars + dt * sp, CurrentLine.Length);
        }

        public string Advance()
        {
            if (!Active) return "end";
            if (Typing) { Chars = CurrentLine.Length; return "typed"; }
            if (Page < Lines.Length - 1) { Page++; Chars = 0; return "page"; }
            return "end";
        }
    }

    public class StoryState
    {
        public Dialogue Dlg = new();
        public int Chapter;
        public string? Cursor;
        public bool Waiting = true;
        public bool Finished;
        public HashSet<string> Flags = new();
        public HashSet<string> CompletedSteps = new();
        public HashSet<string> Inventory = new();
        public List<string> Gates = new();
        public int GateI;
        public Dictionary<string, bool> StepDone = new();

        public void Begin(int chapter = 0)
        {
            Chapter = chapter;
            GateI = 0;
            Gates = BuildGates(chapter);
            Cursor = $"ch{chapter + 1}_01";
            Waiting = true;
            CheckGate();
        }

        static List<string> BuildGates(int chapter)
        {
            var list = new List<string>();
            // 章节的 step 顺序由数据表定义
            foreach (var (k, _) in StoryData.Steps)
                if (k.StartsWith($"ch{chapter + 1}_")) list.Add(k);
            return list;
        }

        public string? CurrentObjective()
        {
            if (Finished) return "旅程已经走到镜子前面。";
            if (Dlg.Active) return null;
            if (GateI >= Gates.Count) return null;
            var sid = Gates[GateI];
            return StoryData.Steps.TryGetValue(sid, out var s) ? s.text : null;
        }

        public (string? kind, string? target) ObjectiveTarget()
        {
            if (Dlg.Active || GateI >= Gates.Count) return (null, null);
            var sid = Gates[GateI];
            if (!StoryData.Steps.TryGetValue(sid, out var s)) return (null, null);
            return (s.kind, s.target);
        }

        public void CheckGate()
        {
            if (Finished || Cursor == null) return;
            if (GateI >= Gates.Count)
            {
                // 章节完成
                FinishChapter();
                return;
            }
            if (StepDone.TryGetValue(Gates[GateI], out bool done) && done)
            {
                GateI++;
                CheckGate();
                return;
            }
            // 有未完成 step, 等待玩家行动
            Waiting = true;
        }

        void FinishChapter()
        {
            int nxt = Chapter + 1;
            if (nxt >= StoryData.Chapters.Length)
            {
                Finished = true;
                Flags.Add("ending_reached");
                return;
            }
            Chapter = nxt;
            GateI = 0;
            Gates = BuildGates(nxt);
            Cursor = $"ch{nxt + 1}_01";
            Waiting = true;
            // 自动触发第一段对话 (若当前 step 已满足)
            CheckGate();
        }

        public void Notify(string kind, string target)
        {
            if (Finished) return;
            if (GateI >= Gates.Count) { CheckGate(); return; }
            var sid = Gates[GateI];
            if (!StoryData.Steps.TryGetValue(sid, out var s)) return;
            if (s.kind == kind && s.target == target)
            {
                StepDone[sid] = true;
                CompletedSteps.Add(sid);
                AdvanceToDialogue();
            }
        }

        void AdvanceToDialogue()
        {
            GateI++;
            if (GateI >= Gates.Count) { FinishChapter(); return; }
            // 找到下一个未完成 step, 若无则章节完成
            while (GateI < Gates.Count && StepDone.TryGetValue(Gates[GateI], out bool d) && d) GateI++;
            if (GateI >= Gates.Count) { FinishChapter(); return; }
            // 检查该 step 对应的对话节点并播放
            var sid = Gates[GateI];
            var nodeId = FindNodeForStep(sid);
            if (nodeId != null && Cursor != null)
            {
                Cursor = nodeId;
                Waiting = false;
                Dlg.Start(nodeId);
            }
            else Waiting = true;
        }

        string? FindNodeForStep(string sid)
        {
            // 每个 step 由它的编号对应节点: chX_sY -> chX_YY
            // 简化: 顺序对应 01..NN
            var parts = sid.Split('_'); // chN_sM
            if (parts.Length != 2) return null;
            int n = int.Parse(parts[0].Substring(2));
            int m = int.Parse(parts[1].Substring(1));
            string cand = $"ch{n}_{m:D2}";
            return StoryData.Nodes.ContainsKey(cand) ? cand : null;
        }

        public void Advance()
        {
            if (!Dlg.Active) return;
            var r = Dlg.Advance();
            if (r != "end") return;
            var node = Dlg.Node;
            Dlg.Stop();
            if (node == null) return;
            // 处理 on_end
            if (node.QuestStep != null)
            {
                CompletedSteps.Add(node.QuestStep);
                StepDone[node.QuestStep] = true;
            }
            if (node.Flag != null) Flags.Add(node.Flag);
            if (node.Give != null) Inventory.Add(node.Give);
            var next = node.Next;
            if (next == null)
            {
                // 推进到下一 gate
                GateI++;
                CheckGate();
                return;
            }
            Cursor = next;
            Dlg.Start(next);
        }

        public void Interact(string kind, string id)
        {
            if (Dlg.Active) return;
            if (kind == "inter")
            {
                Notify("touch", id);
                Notify("echo", id);
                Dlg.StartTemp("此处", "这是一处刻痕。你辨认出，它记录着某个被遗忘的生命存在过的证据。");
            }
            else if (kind == "npc")
            {
                Notify("talk", id);
                if (!Dlg.Active)
                    Dlg.StartTemp(id, "他/她沉默地看了你一会儿，然后移开了目光。");
            }
            else if (kind == "coll")
            {
                Inventory.Add(id);
                Notify("collect", id);
            }
        }
    }
}
