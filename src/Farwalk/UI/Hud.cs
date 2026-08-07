// Hud.cs — 游戏界面: HUD / 对话框 / 地图 / 日志 / 成就 / 传送菜单
using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.Versioning;
using Farwalk.Engine;
using Farwalk.Game;
using Farwalk.World;
using OpenTK.Graphics.OpenGL4;

namespace Farwalk.UI
{
    public enum UiPanel { None, Map, Journal, Achievements, Portal }

    // ---------------------------------------------------------------
    // 世界缩略图: 由地形高度场 + 反照率烘焙成一张纹理
    // ---------------------------------------------------------------
    public static class Minimap
    {
        public static int Size { get; private set; }

        public static int Build(Terrain t)
        {
            int n = TerrainConfig.CELLS + 1;
            Size = n;
            var px = new byte[n * n * 4];
            for (int k = 0; k < n * n; k++)
            {
                float h = t.Heights[k];
                float nx = t.Normals[k * 3], ny = t.Normals[k * 3 + 1], nz = t.Normals[k * 3 + 2];
                // 西北向斜光, 强化地貌起伏
                float shade = 0.62f + 0.38f * Math3D.Clamp(ny, 0f, 1f) + (-nx * 0.42f - nz * 0.42f);
                shade = Math3D.Clamp(shade, 0.22f, 1.45f);
                float r = t.Albedo[k * 3] * shade * 2.15f;
                float g = t.Albedo[k * 3 + 1] * shade * 2.15f;
                float b = t.Albedo[k * 3 + 2] * shade * 2.15f;
                if (h < TerrainConfig.WATER_LEVEL)
                {
                    float d = Math3D.Clamp((TerrainConfig.WATER_LEVEL - h) / 12f, 0f, 1f);
                    r = Math3D.Lerp(r, 0.10f, 0.55f + d * 0.35f);
                    g = Math3D.Lerp(g, 0.26f, 0.55f + d * 0.35f);
                    b = Math3D.Lerp(b, 0.38f, 0.55f + d * 0.35f);
                }
                px[k * 4 + 0] = (byte)(Math3D.Clamp(r, 0f, 1f) * 255f);
                px[k * 4 + 1] = (byte)(Math3D.Clamp(g, 0f, 1f) * 255f);
                px[k * 4 + 2] = (byte)(Math3D.Clamp(b, 0f, 1f) * 255f);
                px[k * 4 + 3] = 255;
            }
            int tex = GL.GenTexture();
            GL.BindTexture(TextureTarget.Texture2D, tex);
            GL.PixelStore(PixelStoreParameter.UnpackAlignment, 4);
            GL.TexImage2D(TextureTarget.Texture2D, 0, PixelInternalFormat.Rgba8, n, n, 0,
                OpenTK.Graphics.OpenGL4.PixelFormat.Rgba, PixelType.UnsignedByte, px);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureMinFilter, (int)TextureMinFilter.Linear);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureMagFilter, (int)TextureMagFilter.Linear);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureWrapS, (int)TextureWrapMode.ClampToEdge);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureWrapT, (int)TextureWrapMode.ClampToEdge);
            GL.BindTexture(TextureTarget.Texture2D, 0);
            return tex;
        }
    }

    public class HudContext
    {
        public StoryState Story = null!;
        public Player Player = null!;
        public PortalSystem Portals = null!;
        public LandmarkSystem Landmarks = null!;
        public AchievementSystem Ach = null!;
        public UiPanel Panel = UiPanel.None;
        public string RegionName = "";
        public string? Prompt;
        public int MapTex;
        public float Time;
        public float Fps;
        public float PlayerYaw;
        public bool ShadowOn = true;
        public bool PostOn = true;
    }

    [SupportedOSPlatform("windows")]
    public class GameUi
    {
        // 配色
        static readonly Col Ink = Col.Rgb(0xF2EDE4);
        static readonly Col Dim = Col.Rgb(0x9FA6AE);
        static readonly Col Gold = Col.Rgb(0xD9B86A);
        static readonly Col Teal = Col.Rgb(0x74C4C0);
        static readonly Col Rose = Col.Rgb(0xD2716B);
        static readonly Col Panel = new(0.055f, 0.062f, 0.078f, 0.90f);
        static readonly Col PanelSoft = new(0.09f, 0.10f, 0.12f, 0.72f);
        static readonly Col Edge = new(0.55f, 0.50f, 0.38f, 0.55f);

        public void Draw(Overlay o, HudContext c)
        {
            o.Begin();
            switch (c.Panel)
            {
                case UiPanel.Map: DrawMapPanel(o, c); break;
                case UiPanel.Journal: DrawJournal(o, c); break;
                case UiPanel.Achievements: DrawAchievements(o, c); break;
                default:
                    DrawHud(o, c);
                    if (c.Portals.MenuOpen) DrawPortalMenu(o, c);
                    break;
            }
            DrawToasts(o, c);
            o.End();
        }

        // ---------------- 常规 HUD ----------------
        void DrawHud(Overlay o, HudContext c)
        {
            float W = o.Width, H = o.Height;

            // 左上: 章节 + 目标
            string chapter = c.Story.Finished
                ? "尾声 · 旅程完成"
                : $"第 {c.Story.Chapter + 1} 章 · {StoryData.Chapters[Math.Min(c.Story.Chapter, StoryData.Chapters.Length - 1)]}";
            o.Rect(0, 0, 470, 118, new Col(0, 0, 0, 0.26f));
            o.TextShadow(chapter, 26, 22, Gold, o.Font);
            o.TextShadow(c.RegionName, 26, 60, Teal, o.FontSmall);
            var obj = c.Story.CurrentObjective();
            if (!string.IsNullOrEmpty(obj))
                o.TextShadow("◈ " + obj, 26, 86, Ink, o.FontSmall);

            // 左下: 生命 / 体力
            float bx = 26, by = H - 74, bw = 300, bh = 12;
            o.Rect(bx - 3, by - 3, bw + 6, bh + 6, new Col(0, 0, 0, 0.45f));
            o.Rect(bx, by, bw * Math3D.Clamp(c.Player.Hp / 100f, 0, 1), bh, Rose);
            o.Rect(bx - 3, by + 23, bw + 6, bh + 6, new Col(0, 0, 0, 0.45f));
            o.Rect(bx, by + 26, bw * Math3D.Clamp(c.Player.Stamina / 100f, 0, 1), bh, Teal);
            o.TextShadow($"HP {c.Player.Hp:F0}", bx + bw + 14, by - 8, Dim, o.FontSmall);
            o.TextShadow($"STA {c.Player.Stamina:F0}", bx + bw + 14, by + 18, Dim, o.FontSmall);

            // 右上: 小地图
            DrawMiniMap(o, c, W - 236, 22, 214);

            // 底部中央: 交互提示
            if (!string.IsNullOrEmpty(c.Prompt) && !c.Story.Dlg.Active)
            {
                float tw = o.Font.Measure(c.Prompt!) + 40;
                o.Rect(W * 0.5f - tw * 0.5f, H - 168, tw, 46, PanelSoft);
                o.RectOutline(W * 0.5f - tw * 0.5f, H - 168, tw, 46, 1.5f, Edge);
                o.TextCentered(c.Prompt!, W * 0.5f, H - 160, Ink, o.Font);
            }

            // 右下: 按键提示
            string keys = "WASD 移动 · Shift 疾跑 · Space 跳跃/滑翔 · E 交互 · F 传送 · M 地图 · J 日志 · C 成就";
            o.TextRight(keys, W - 24, H - 32, new Col(0.62f, 0.64f, 0.68f, 0.75f), o.FontSmall);
            o.TextRight($"{c.Fps:F0} FPS · 阴影 {(c.ShadowOn ? "开" : "关")} · 后期 {(c.PostOn ? "开" : "关")}",
                W - 24, 244, new Col(0.55f, 0.58f, 0.62f, 0.7f), o.FontSmall);

            // 对话框
            if (c.Story.Dlg.Active) DrawDialogue(o, c);
        }

        void DrawDialogue(Overlay o, HudContext c)
        {
            float W = o.Width, H = o.Height;
            float bw = MathF.Min(W * 0.78f, 1280), bh = 208;
            float x = (W - bw) * 0.5f, y = H - bh - 46;
            o.RectV(x, y, bw, bh, new Col(0.05f, 0.055f, 0.07f, 0.93f), new Col(0.03f, 0.035f, 0.05f, 0.96f));
            o.RectOutline(x, y, bw, bh, 2f, Edge);
            // 顶部金线
            o.Rect(x + 18, y + 2, bw - 36, 2f, Gold.WithA(0.55f));

            var dlg = c.Story.Dlg;
            if (!string.IsNullOrEmpty(dlg.Speaker))
            {
                float nw = o.Font.Measure(dlg.Speaker) + 34;
                o.Rect(x + 26, y - 21, nw, 42, new Col(0.10f, 0.11f, 0.13f, 0.96f));
                o.RectOutline(x + 26, y - 21, nw, 42, 1.5f, Gold.WithA(0.6f));
                o.TextShadow(dlg.Speaker, x + 43, y - 14, Gold, o.Font);
            }
            o.TextWrapped(dlg.VisibleText, x + 40, y + 48, bw - 80, 42, Ink, o.Font);

            if (!dlg.Typing)
            {
                float blink = 0.45f + 0.55f * MathF.Abs(MathF.Sin(c.Time * 3.2f));
                o.TextRight("▼ 空格 / E 继续", x + bw - 30, y + bh - 40, Ink.WithA(blink), o.FontSmall);
            }
            if (dlg.Lines.Length > 1)
                o.TextShadow($"{dlg.Page + 1} / {dlg.Lines.Length}", x + 40, y + bh - 40, Dim, o.FontSmall);
        }

        // ---------------- 小地图 ----------------
        void DrawMiniMap(Overlay o, HudContext c, float x, float y, float size)
        {
            const float WINDOW = 320f;   // 视野半径 (米)
            float half = TerrainConfig.HALF, full = TerrainConfig.SIZE;
            float px = c.Player.Pos.X, pz = c.Player.Pos.Z;
            float u0 = (px - WINDOW + half) / full, u1 = (px + WINDOW + half) / full;
            float v0 = (pz - WINDOW + half) / full, v1 = (pz + WINDOW + half) / full;

            o.Rect(x - 3, y - 3, size + 6, size + 6, new Col(0, 0, 0, 0.55f));
            if (c.MapTex != 0) o.Image(c.MapTex, x, y, size, size, new Col(1, 1, 1, 0.95f), u0, v0, u1, v1);
            o.RectOutline(x - 3, y - 3, size + 6, size + 6, 2f, Edge);

            // 视窗内的地标 / 传送门
            float Sx(float wx) => x + (wx - (px - WINDOW)) / (WINDOW * 2f) * size;
            float Sy(float wz) => y + (wz - (pz - WINDOW)) / (WINDOW * 2f) * size;
            bool Inside(float sx, float sy) => sx > x && sx < x + size && sy > y && sy < y + size;

            foreach (var p in c.Portals.Portals)
            {
                if (!p.Discovered) continue;
                float sx = Sx(p.Pos.X), sy = Sy(p.Pos.Z);
                if (!Inside(sx, sy)) continue;
                o.CircleOutline(sx, sy, 6.5f, 2f, Teal, 14);
                o.Circle(sx, sy, 2.4f, Teal);
            }
            var (kind, target) = c.Story.ObjectiveTarget();
            if (target != null)
            {
                var lm = c.Landmarks.Find(target);
                if (lm != null)
                {
                    float sx = Sx(lm.Pos.X), sy = Sy(lm.Pos.Z);
                    if (Inside(sx, sy))
                    {
                        float pulse = 4f + MathF.Sin(c.Time * 4f) * 1.6f;
                        o.CircleOutline(sx, sy, pulse + 3f, 1.6f, Gold.WithA(0.75f), 16);
                        o.Circle(sx, sy, 3.2f, Gold);
                    }
                }
            }
            // 玩家 (朝向三角)
            float cxp = x + size * 0.5f, cyp = y + size * 0.5f;
            DrawFacingMarker(o, cxp, cyp, 8f, c.PlayerYaw, Col.Rgb(0xFFF3D6));
            o.TextShadow("N", cxp - 6, y + 4, new Col(1, 1, 1, 0.55f), o.FontSmall);
        }

        void DrawFacingMarker(Overlay o, float cx, float cy, float r, float yaw, Col col)
        {
            // 世界 forward = (-sin yaw, -cos yaw); 屏幕 y 轴与世界 z 同向
            float fx = -MathF.Sin(yaw), fz = -MathF.Cos(yaw);
            float rx = -fz, rz = fx;
            o.Circle(cx, cy, r * 0.42f, col.WithA(0.9f));
            o.Line(cx, cy, cx + fx * r * 1.5f, cy + fz * r * 1.5f, 2.6f, col);
            o.Line(cx + fx * r * 1.5f, cy + fz * r * 1.5f, cx + rx * r * 0.55f - fx * r * 0.15f,
                cy + rz * r * 0.55f - fz * r * 0.15f, 2.2f, col.WithA(0.8f));
            o.Line(cx + fx * r * 1.5f, cy + fz * r * 1.5f, cx - rx * r * 0.55f - fx * r * 0.15f,
                cy - rz * r * 0.55f - fz * r * 0.15f, 2.2f, col.WithA(0.8f));
        }

        // ---------------- 大地图 ----------------
        void DrawMapPanel(Overlay o, HudContext c)
        {
            float W = o.Width, H = o.Height;
            o.Rect(0, 0, W, H, new Col(0.02f, 0.024f, 0.03f, 0.88f));

            float m = MathF.Min(W * 0.62f, H * 0.80f);
            float x = (W - m) * 0.5f - 130, y = (H - m) * 0.5f + 18;

            o.TextCentered("世 界 地 图", W * 0.5f, 36, Gold, o.FontBig);
            o.Rect(x - 5, y - 5, m + 10, m + 10, new Col(0, 0, 0, 0.7f));
            if (c.MapTex != 0) o.Image(c.MapTex, x, y, m, m, new Col(1, 1, 1, 1));
            o.RectOutline(x - 5, y - 5, m + 10, m + 10, 2.5f, Edge);

            float half = TerrainConfig.HALF, full = TerrainConfig.SIZE;
            float Sx(float wx) => x + (wx + half) / full * m;
            float Sy(float wz) => y + (wz + half) / full * m;

            // 区域范围 + 名称
            foreach (var region in TerrainConfig.RegionOrder)
            {
                var (rx, rz) = TerrainConfig.RegionPos[region];
                float rad = TerrainConfig.RegionRadius[region] / full * m;
                bool known = c.Portals.Visited.Contains(region);
                var col = known ? Teal.WithA(0.40f) : new Col(0.45f, 0.45f, 0.48f, 0.20f);
                o.CircleOutline(Sx(rx), Sy(rz), rad, 1.6f, col, 44);
                string label = known ? TerrainConfig.RegionTitle[region] : "未知区域";
                o.TextCentered(label, Sx(rx), Sy(rz) - rad - 30,
                    known ? Teal : new Col(0.5f, 0.5f, 0.55f, 0.65f), o.FontSmall);
            }

            // 传送门
            foreach (var p in c.Portals.Portals)
            {
                if (!p.Discovered) continue;
                float sx = Sx(p.Pos.X), sy = Sy(p.Pos.Z);
                float pulse = 8f + MathF.Sin(c.Time * 2.4f + p.Pulse) * 2f;
                o.CircleOutline(sx, sy, pulse, 2f, Teal, 18);
                o.Circle(sx, sy, 3.4f, Teal);
            }

            // 已知区域内的地标
            foreach (var lm in c.Landmarks.Marks)
            {
                if (!c.Portals.Visited.Contains(lm.Region)) continue;
                float sx = Sx(lm.Pos.X), sy = Sy(lm.Pos.Z);
                var col = lm.Kind switch
                {
                    MarkKind.Talk => Col.Rgb(0xE0C070),
                    MarkKind.Collect => Col.Rgb(0x8FD08A),
                    _ => Col.Rgb(0xB0B8C4),
                };
                if (c.Story.CompletedSteps.Count > 0 && lm.Used) col = col.WithA(0.35f);
                o.Marker(sx, sy, 5f, col);
            }

            // 当前目标高亮
            var (_, target) = c.Story.ObjectiveTarget();
            if (target != null)
            {
                var lm = c.Landmarks.Find(target);
                if (lm != null)
                {
                    float sx = Sx(lm.Pos.X), sy = Sy(lm.Pos.Z);
                    float pulse = 11f + MathF.Sin(c.Time * 4.2f) * 3.4f;
                    o.CircleOutline(sx, sy, pulse, 2.2f, Gold, 22);
                    o.TextCentered(lm.Label, sx, sy + 16, Gold, o.FontSmall);
                }
            }

            // 玩家
            DrawFacingMarker(o, Sx(c.Player.Pos.X), Sy(c.Player.Pos.Z), 11f, c.PlayerYaw, Col.Rgb(0xFFF3D6));

            // 右侧信息栏
            float ix = x + m + 40, iy = y + 4, iw = W - ix - 40;
            o.Rect(ix, iy, iw, m, PanelSoft);
            o.RectOutline(ix, iy, iw, m, 1.5f, Edge);
            float ty = iy + 22;
            o.TextShadow("坐 标", ix + 20, ty, Gold, o.Font); ty += 40;
            o.TextShadow($"X {c.Player.Pos.X:F1}   Z {c.Player.Pos.Z:F1}", ix + 20, ty, Ink, o.FontSmall); ty += 28;
            o.TextShadow($"海拔 {c.Player.Pos.Y:F1} m", ix + 20, ty, Ink, o.FontSmall); ty += 28;
            o.TextShadow($"所在 {c.RegionName}", ix + 20, ty, Teal, o.FontSmall); ty += 46;

            o.TextShadow("已 发 现 区 域", ix + 20, ty, Gold, o.Font); ty += 40;
            foreach (var region in TerrainConfig.RegionOrder)
            {
                bool known = c.Portals.Visited.Contains(region);
                o.TextShadow((known ? "◆ " : "◇ ") + (known ? TerrainConfig.RegionTitle[region] : "？？？"),
                    ix + 20, ty, known ? Ink : Dim.WithA(0.55f), o.FontSmall);
                ty += 28;
            }
            ty += 18;
            o.TextShadow($"进度  {c.Portals.Visited.Count} / 6", ix + 20, ty, Teal, o.FontSmall);

            o.TextCentered("M / Esc 关闭   ·   传送需在传送门旁按 F", W * 0.5f, H - 44, Dim, o.FontSmall);
        }

        // ---------------- 日志 ----------------
        void DrawJournal(Overlay o, HudContext c)
        {
            float W = o.Width, H = o.Height;
            o.Rect(0, 0, W, H, new Col(0.02f, 0.024f, 0.03f, 0.90f));
            float pw = MathF.Min(W * 0.82f, 1400), ph = H - 130;
            float x = (W - pw) * 0.5f, y = 80;
            o.Rect(x, y, pw, ph, Panel);
            o.RectOutline(x, y, pw, ph, 2f, Edge);
            o.TextCentered("远 行 日 志", W * 0.5f, 26, Gold, o.FontBig);

            float colW = pw * 0.52f;
            float lx = x + 34, ly = y + 26;

            // 左栏: 章节进度
            o.TextShadow("章 节", lx, ly, Gold, o.Font); ly += 44;
            for (int i = 0; i < StoryData.Chapters.Length; i++)
            {
                bool done = i < c.Story.Chapter || c.Story.Finished;
                bool cur = i == c.Story.Chapter && !c.Story.Finished;
                var col = done ? Teal : (cur ? Ink : Dim.WithA(0.45f));
                string mark = done ? "✓" : (cur ? "▶" : "·");
                string title = (done || cur) ? StoryData.Chapters[i] : "？？？";
                o.TextShadow($"{mark}  第 {i + 1} 章   {title}", lx, ly, col, o.FontSmall);
                ly += 30;
            }

            // 左栏下方: 当前目标
            ly += 22;
            o.TextShadow("当 前 目 标", lx, ly, Gold, o.Font); ly += 44;
            var obj = c.Story.CurrentObjective();
            if (string.IsNullOrEmpty(obj))
                o.TextShadow(c.Story.Finished ? "旅程已经走到镜子前面。" : "（对话进行中）", lx, ly, Dim, o.FontSmall);
            else
            {
                o.TextWrapped("◈ " + obj, lx, ly, colW - 40, 30, Ink, o.FontSmall);
                var (_, target) = c.Story.ObjectiveTarget();
                if (target != null)
                {
                    var lm = c.Landmarks.Find(target);
                    if (lm != null)
                    {
                        float dx = c.Player.Pos.X - lm.Pos.X, dz = c.Player.Pos.Z - lm.Pos.Z;
                        float dist = MathF.Sqrt(dx * dx + dz * dz);
                        o.TextShadow($"位置：{TerrainConfig.RegionTitle[lm.Region]} · 距离 {dist:F0} m",
                            lx, ly + 36, Teal, o.FontSmall);
                    }
                    else if (TerrainConfig.RegionTitle.TryGetValue(target, out var rt))
                        o.TextShadow($"前往：{rt}", lx, ly + 36, Teal, o.FontSmall);
                }
            }

            // 右栏: 已完成记录 / 收藏品
            float rx = x + colW + 40, ry = y + 26;
            o.Line(x + colW + 12, y + 20, x + colW + 12, y + ph - 20, 1.4f, Edge);
            o.TextShadow("已 完 成", Gold.R > 0 ? rx : rx, ry, Gold, o.Font); ry += 44;
            var doneSteps = StoryData.Steps.Where(s => c.Story.CompletedSteps.Contains(s.Key)).ToList();
            if (doneSteps.Count == 0)
                o.TextShadow("（尚无记录）", rx, ry, Dim, o.FontSmall);
            int shown = 0;
            foreach (var s in doneSteps)
            {
                if (shown++ >= 12) break;
                o.TextShadow("✓ " + s.Value.text, rx, ry, Dim, o.FontSmall);
                ry += 28;
            }
            if (doneSteps.Count > 12)
                o.TextShadow($"… 另有 {doneSteps.Count - 12} 条", rx, ry, Dim.WithA(0.6f), o.FontSmall);

            ry += 40;
            o.TextShadow("行 囊", rx, ry, Gold, o.Font); ry += 44;
            if (c.Story.Inventory.Count == 0)
                o.TextShadow("（空）", rx, ry, Dim, o.FontSmall);
            foreach (var it in c.Story.Inventory)
            {
                var lm = c.Landmarks.Find(it);
                o.TextShadow("◆ " + (lm?.Label ?? it), rx, ry, Ink, o.FontSmall);
                ry += 28;
            }

            o.TextCentered("J / Esc 关闭", W * 0.5f, H - 42, Dim, o.FontSmall);
        }

        // ---------------- 成就 ----------------
        void DrawAchievements(Overlay o, HudContext c)
        {
            float W = o.Width, H = o.Height;
            o.Rect(0, 0, W, H, new Col(0.02f, 0.024f, 0.03f, 0.90f));
            float pw = MathF.Min(W * 0.80f, 1320), ph = H - 140;
            float x = (W - pw) * 0.5f, y = 88;
            o.Rect(x, y, pw, ph, Panel);
            o.RectOutline(x, y, pw, ph, 2f, Edge);

            var ach = c.Ach;
            o.TextCentered("成 就", W * 0.5f, 26, Gold, o.FontBig);
            o.TextCentered($"{ach.UnlockedCount} / {ach.All.Count}", W * 0.5f, 66, Teal, o.FontSmall);

            int cols = 2;
            float cw = (pw - 68) / cols, chh = 76;
            for (int i = 0; i < ach.All.Count; i++)
            {
                var a = ach.All[i];
                int cx = i % cols, cy = i / cols;
                float ax = x + 34 + cx * cw, ay = y + 34 + cy * chh;
                if (ay + chh > y + ph) break;

                o.Rect(ax, ay, cw - 20, chh - 12, a.Unlocked
                    ? new Col(0.10f, 0.13f, 0.13f, 0.85f)
                    : new Col(0.07f, 0.075f, 0.088f, 0.7f));
                o.Rect(ax, ay, 4f, chh - 12, a.Unlocked ? Gold : new Col(0.3f, 0.3f, 0.33f, 0.6f));

                string title = (a.Hidden && !a.Unlocked) ? "？？？" : a.Title;
                string desc = (a.Hidden && !a.Unlocked) ? "隐藏成就" : a.Desc;
                o.TextShadow(title, ax + 20, ay + 10, a.Unlocked ? Gold : Dim.WithA(0.7f), o.Font);
                o.TextShadow(desc, ax + 20, ay + 42, a.Unlocked ? Ink.WithA(0.8f) : Dim.WithA(0.5f), o.FontSmall);

                if (!a.Unlocked && a.Progress > 0.001f)
                {
                    float pbw = cw - 60;
                    o.Rect(ax + 20, ay + chh - 22, pbw, 4f, new Col(0, 0, 0, 0.5f));
                    o.Rect(ax + 20, ay + chh - 22, pbw * a.Progress, 4f, Teal.WithA(0.8f));
                    o.TextRight($"{a.Progress * 100f:F0}%", ax + cw - 30, ay + 12, Teal.WithA(0.7f), o.FontSmall);
                }
                else if (a.Unlocked)
                    o.TextRight("已解锁", ax + cw - 30, ay + 12, Teal, o.FontSmall);
            }

            o.TextCentered("C / Esc 关闭", W * 0.5f, H - 42, Dim, o.FontSmall);
        }

        // ---------------- 传送菜单 ----------------
        void DrawPortalMenu(Overlay o, HudContext c)
        {
            float W = o.Width, H = o.Height;
            o.Rect(0, 0, W, H, new Col(0.02f, 0.03f, 0.04f, 0.62f));
            var list = c.Portals.Unlocked();
            float pw = 560, ph = 120 + list.Count * 62;
            float x = (W - pw) * 0.5f, y = (H - ph) * 0.5f;
            o.Rect(x, y, pw, ph, Panel);
            o.RectOutline(x, y, pw, ph, 2f, Gold.WithA(0.6f));
            o.TextCentered("传 送 门", W * 0.5f, y + 22, Gold, o.Font);
            o.Line(x + 30, y + 66, x + pw - 30, y + 66, 1.4f, Edge);

            for (int i = 0; i < list.Count; i++)
            {
                var p = list[i];
                float iy = y + 82 + i * 62;
                bool sel = i == c.Portals.MenuIndex;
                if (sel)
                {
                    o.Rect(x + 22, iy - 6, pw - 44, 52, new Col(0.16f, 0.19f, 0.19f, 0.9f));
                    o.Rect(x + 22, iy - 6, 4f, 52, Gold);
                }
                float dx = c.Player.Pos.X - p.Pos.X, dz = c.Player.Pos.Z - p.Pos.Z;
                float dist = MathF.Sqrt(dx * dx + dz * dz);
                o.TextShadow(p.Title, x + 44, iy, sel ? Gold : Ink, o.Font);
                o.TextRight($"{dist:F0} m", x + pw - 44, iy + 6, sel ? Teal : Dim, o.FontSmall);
            }
            o.TextCentered("↑ ↓ 选择 · Enter 传送 · Esc / F 取消", W * 0.5f, y + ph - 36, Dim, o.FontSmall);
        }

        // ---------------- 成就弹窗 ----------------
        void DrawToasts(Overlay o, HudContext c)
        {
            float W = o.Width;
            float y = 262;
            foreach (var t in c.Ach.Toasts)
            {
                float k = t.Life / t.MaxLife;
                float slide = k < 0.12f ? (1f - k / 0.12f) : 0f;
                float alpha = k > 0.86f ? (1f - k) / 0.14f : 1f;
                float tw = 400, th = 84;
                float x = W - tw - 26 + slide * (tw + 40);
                o.Rect(x, y, tw, th, new Col(0.07f, 0.08f, 0.09f, 0.94f * alpha));
                o.Rect(x, y, 5f, th, Gold.WithA(alpha));
                o.RectOutline(x, y, tw, th, 1.5f, Edge.WithA(alpha * 0.8f));
                o.TextShadow("成就解锁", x + 24, y + 12, Teal.WithA(alpha), o.FontSmall);
                o.TextShadow(t.Title, x + 24, y + 38, Gold.WithA(alpha), o.Font);
                o.TextRight(t.Desc, x + tw - 20, y + 14, new Col(0.7f, 0.72f, 0.75f, alpha * 0.85f), o.FontSmall);
                y += th + 12;
            }
        }
    }
}
