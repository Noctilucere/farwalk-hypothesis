// Achievements.cs — 成就系统 (解锁判定 + 弹窗队列)
using System;
using System.Collections.Generic;
using System.Linq;
using Farwalk.Engine;
using Farwalk.World;

namespace Farwalk.Game
{
    public class Achievement
    {
        public string Id = "";
        public string Title = "";
        public string Desc = "";
        public bool Unlocked;
        public float Progress;      // 0..1, 仅用于展示
        public bool Hidden;         // 隐藏成就: 未解锁时不显示描述
    }

    public class Toast
    {
        public string Title = "";
        public string Desc = "";
        public float Life;
        public float MaxLife = 4.6f;
    }

    public class AchievementSystem
    {
        public List<Achievement> All = new();
        public List<Toast> Toasts = new();
        public int UnlockedCount => All.Count(a => a.Unlocked);

        // 累计统计量
        public float DistanceWalked;
        public float GlideSeconds;
        public int DialogueLines;
        public int PortalUses;
        public float MaxAltitude;

        public AchievementSystem()
        {
            void A(string id, string t, string d, bool hidden = false) =>
                All.Add(new Achievement { Id = id, Title = t, Desc = d, Hidden = hidden });

            A("first_walk", "第一步", "离开出生点 100 米");
            A("wanderer", "漫游者", "累计行走 3000 米");
            A("climber", "攀高者", "抵达海拔 100 米以上");
            A("skyform", "风的形状", "累计滑翔 20 秒");
            A("deepwater", "涉水者", "沉入水线以下");
            A("see_blackstone", "黑石之下", "抵达黑石祭址");
            A("see_lostland", "失落之处", "抵达失落的世界");
            A("see_silenthall", "钟不再响", "抵达无声钟塔");
            A("see_mutezone", "被消掉的音", "抵达消音地带");
            A("see_mirror", "镜的边缘", "抵达镜之境");
            A("cartographer", "制图者", "发现全部 6 个区域");
            A("gatekeeper", "门的用途", "使用传送门 5 次");
            A("listener", "倾听者", "读完 100 行对话");
            A("midway", "行至中途", "完成第 5 章");
            A("farwalk", "远行假设", "抵达旅程的终点", hidden: true);
        }

        public Achievement? Get(string id) => All.FirstOrDefault(a => a.Id == id);

        public bool Unlock(string id)
        {
            var a = Get(id);
            if (a == null || a.Unlocked) return false;
            a.Unlocked = true;
            a.Progress = 1f;
            Toasts.Add(new Toast { Title = a.Title, Desc = a.Desc, Life = 0f });
            return true;
        }

        void SetProgress(string id, float p)
        {
            var a = Get(id);
            if (a != null && !a.Unlocked) a.Progress = Math3D.Clamp(p, 0f, 1f);
        }

        public void UpdateToasts(float dt)
        {
            for (int i = Toasts.Count - 1; i >= 0; i--)
            {
                Toasts[i].Life += dt;
                if (Toasts[i].Life > Toasts[i].MaxLife) Toasts.RemoveAt(i);
            }
        }

        /// <summary>每帧驱动: 汇总玩家 / 剧情 / 传送门状态并判定解锁。</summary>
        public void Evaluate(float dt, Player player, Vec3 spawn, StoryState story,
            PortalSystem portals, bool gliding, bool underwater)
        {
            // --- 统计 ---
            if (gliding) GlideSeconds += dt;
            MaxAltitude = MathF.Max(MaxAltitude, player.Pos.Y);
            PortalUses = portals.UseCount;

            float dx = player.Pos.X - spawn.X, dz = player.Pos.Z - spawn.Z;
            float fromSpawn = MathF.Sqrt(dx * dx + dz * dz);

            // --- 判定 ---
            SetProgress("first_walk", fromSpawn / 100f);
            if (fromSpawn >= 100f) Unlock("first_walk");

            SetProgress("wanderer", DistanceWalked / 3000f);
            if (DistanceWalked >= 3000f) Unlock("wanderer");

            SetProgress("climber", MaxAltitude / 100f);
            if (MaxAltitude >= 100f) Unlock("climber");

            SetProgress("skyform", GlideSeconds / 20f);
            if (GlideSeconds >= 20f) Unlock("skyform");

            if (underwater) Unlock("deepwater");

            foreach (var (region, id) in RegionAchievement)
                if (portals.Visited.Contains(region)) Unlock(id);

            SetProgress("cartographer", portals.Visited.Count / 6f);
            if (portals.Visited.Count >= 6) Unlock("cartographer");

            SetProgress("gatekeeper", PortalUses / 5f);
            if (PortalUses >= 5) Unlock("gatekeeper");

            SetProgress("listener", DialogueLines / 100f);
            if (DialogueLines >= 100) Unlock("listener");

            SetProgress("midway", story.Chapter / 5f);
            if (story.Chapter >= 5) Unlock("midway");

            if (story.Finished) Unlock("farwalk");
        }

        static readonly (string region, string id)[] RegionAchievement =
        {
            ("blackstone", "see_blackstone"),
            ("lostland", "see_lostland"),
            ("silenthall", "see_silenthall"),
            ("mutezone", "see_mutezone"),
            ("mirror", "see_mirror"),
        };
    }
}
