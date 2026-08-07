// Portals.cs — 区域传送门 (发现 → 解锁 → 快速旅行) + 剧情推进钩子
using System;
using System.Collections.Generic;
using System.Linq;
using Farwalk.Engine;
using Farwalk.World;

namespace Farwalk.Game
{
    public class Portal
    {
        public string Region = "";
        public string Title = "";
        public Vec3 Pos;
        public bool Discovered;
        public float Pulse;     // 动画相位
    }

    public class PortalSystem
    {
        public List<Portal> Portals = new();
        public HashSet<string> Visited = new();

        public bool MenuOpen;
        public int MenuIndex;
        public int UseCount;

        public const float InteractRange = 7.5f;
        public const float VisitRange = 0.86f;   // 相对区域半径

        // 生成 6 个传送门 (位于各区域中心, 贴合地形高度)
        public void Build(Func<float, float, float> heightAt)
        {
            Portals.Clear();
            foreach (var region in TerrainConfig.RegionOrder)
            {
                var (cx, cz) = TerrainConfig.RegionPos[region];
                // 稍微偏离正中心, 避开静默厅堂 / 镜之境的中央凹陷
                float ox = 0f, oz = 0f;
                if (region == "silenthall") { ox = 34f; oz = 22f; }
                if (region == "mirror") { oz = 40f; }
                float px = cx + ox, pz = cz + oz;
                Portals.Add(new Portal
                {
                    Region = region,
                    Title = TerrainConfig.RegionTitle[region],
                    Pos = new Vec3(px, heightAt(px, pz), pz),
                    Discovered = region == "wilds",   // 起始区域默认解锁
                });
            }
            Visited.Add("wilds");
        }

        public void Update(float dt)
        {
            foreach (var p in Portals)
            {
                p.Pulse += dt * (p.Discovered ? 1.35f : 0.35f);
                if (p.Pulse > Math3D.TAU) p.Pulse -= Math3D.TAU;
            }
        }

        /// <summary>玩家进入某区域范围时返回新发现的区域名, 否则返回 null。</summary>
        public string? UpdateVisit(Vec3 playerPos)
        {
            string? found = null;
            foreach (var p in Portals)
            {
                var (cx, cz) = TerrainConfig.RegionPos[p.Region];
                float rad = TerrainConfig.RegionRadius[p.Region] * VisitRange;
                float dx = playerPos.X - cx, dz = playerPos.Z - cz;
                if (dx * dx + dz * dz > rad * rad) continue;
                if (!p.Discovered)
                {
                    p.Discovered = true;
                    Visited.Add(p.Region);
                    found = p.Region;
                }
                else Visited.Add(p.Region);
            }
            return found;
        }

        public Portal? Nearest(Vec3 pos, out float dist)
        {
            Portal? best = null; dist = float.MaxValue;
            foreach (var p in Portals)
            {
                float dx = pos.X - p.Pos.X, dy = pos.Y - p.Pos.Y, dz = pos.Z - p.Pos.Z;
                float d = MathF.Sqrt(dx * dx + dy * dy + dz * dz);
                if (d < dist) { dist = d; best = p; }
            }
            return best;
        }

        public List<Portal> Unlocked() => Portals.Where(p => p.Discovered).ToList();

        public void OpenMenu()
        {
            MenuOpen = true;
            MenuIndex = 0;
        }

        public void CloseMenu() => MenuOpen = false;

        public void MoveMenu(int delta)
        {
            var list = Unlocked();
            if (list.Count == 0) return;
            MenuIndex = (MenuIndex + delta % list.Count + list.Count) % list.Count;
        }

        public Portal? Selected()
        {
            var list = Unlocked();
            if (list.Count == 0) return null;
            return list[Math3D.ClampI(MenuIndex, 0, list.Count - 1)];
        }
    }

    // ---------------------------------------------------------------
    // 地标 / 可交互物: 让剧情 step 在世界里真正可达
    // ---------------------------------------------------------------
    public enum MarkKind { Touch, Talk, Collect }

    public class Landmark
    {
        public string Id = "";
        public string Label = "";
        public MarkKind Kind;
        public string Region = "";
        public Vec3 Pos;
        public bool Used;
        public float Bob;
    }

    public class LandmarkSystem
    {
        public List<Landmark> Marks = new();
        public const float Range = 6.0f;

        // (id, 显示名, 类型, 所属区域, 相对区域中心的偏移)
        static readonly (string id, string label, MarkKind kind, string region, float ox, float oz)[] DEF =
        {
            ("manuscript", "灰的手稿",      MarkKind.Touch,   "wilds",      -44f,  62f),
            ("echo",       "回音",          MarkKind.Talk,    "wilds",       58f, -36f),
            ("fragment_01","手稿的最后一页", MarkKind.Collect, "wilds",       12f, 118f),
            ("anchor",     "锚",            MarkKind.Talk,    "blackstone",  46f,  28f),
            ("blackstone", "黑石铭文",      MarkKind.Touch,   "blackstone", -38f, -44f),
            ("axolotl",    "美西螈",        MarkKind.Talk,    "lostland",   -52f,  36f),
            ("reptile",    "爬虫族女性",    MarkKind.Talk,    "lostland",    64f, -28f),
            ("ear",        "倾听者·耳",     MarkKind.Talk,    "silenthall", -58f,  18f),
            ("beast_a",    "狼鹿兽人·渐",   MarkKind.Talk,    "silenthall",  40f, -62f),
            ("fragment_08","渐留下的琥珀",  MarkKind.Collect, "mutezone",    22f,  52f),
            ("pen",        "笔",            MarkKind.Talk,    "mutezone",   -60f, -30f),
            ("circle",     "无名者的纪念碑",MarkKind.Touch,   "mutezone",    70f, -48f),
            ("glass",      "绝对寂静的琉璃",MarkKind.Touch,   "mirror",     -34f,  26f),
            ("converger",  "收束者",        MarkKind.Talk,    "mirror",       0f, -18f),
            ("mirror",     "终焉之镜",      MarkKind.Touch,   "mirror",      38f,  10f),
            ("chronicler", "编年者",        MarkKind.Talk,    "mirror",     -56f, -52f),
        };

        public void Build(Func<float, float, float> heightAt)
        {
            Marks.Clear();
            foreach (var d in DEF)
            {
                var (cx, cz) = TerrainConfig.RegionPos[d.region];
                float px = cx + d.ox, pz = cz + d.oz;
                Marks.Add(new Landmark
                {
                    Id = d.id, Label = d.label, Kind = d.kind, Region = d.region,
                    Pos = new Vec3(px, heightAt(px, pz), pz),
                });
            }
        }

        public void Update(float dt)
        {
            foreach (var m in Marks)
            {
                m.Bob += dt * 1.6f;
                if (m.Bob > Math3D.TAU) m.Bob -= Math3D.TAU;
            }
        }

        public Landmark? Nearest(Vec3 pos, out float dist)
        {
            Landmark? best = null; dist = float.MaxValue;
            foreach (var m in Marks)
            {
                float dx = pos.X - m.Pos.X, dz = pos.Z - m.Pos.Z, dy = pos.Y - m.Pos.Y;
                float d = MathF.Sqrt(dx * dx + dy * dy * 0.35f + dz * dz);
                if (d < dist) { dist = d; best = m; }
            }
            return best;
        }

        public Landmark? Find(string id) => Marks.FirstOrDefault(m => m.Id == id);
    }
}
