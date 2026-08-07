// Terrain.cs — 程序化地形 (960m x 960m, 6 区域硬边界)
using System;
using System.Collections.Generic;
using Farwalk.Engine;
using OpenTK.Graphics.OpenGL4;

namespace Farwalk.World
{
    public static class TerrainConfig
    {
        public const float CELL = 2.5f;
        public const int CELLS = 384;
        public const float SIZE = CELL * CELLS;
        public const float HALF = SIZE * 0.5f;
        public const float WATER_LEVEL = 2.2f;

        public static readonly string[] RegionOrder = { "wilds", "blackstone", "lostland", "silenthall", "mutezone", "mirror" };

        public static readonly Dictionary<string, (float x, float z)> RegionPos = new()
        {
            ["wilds"] = (0, 60), ["blackstone"] = (-290, -230), ["lostland"] = (300, -215),
            ["silenthall"] = (320, 265), ["mutezone"] = (-315, 275), ["mirror"] = (-20, -400),
        };

        public static readonly Dictionary<string, float> RegionRadius = new()
        {
            ["wilds"] = 300, ["blackstone"] = 190, ["lostland"] = 200,
            ["silenthall"] = 185, ["mutezone"] = 195, ["mirror"] = 165,
        };

        public static readonly Dictionary<string, string> RegionTitle = new()
        {
            ["wilds"] = "无名荒原", ["blackstone"] = "黑石祭址", ["lostland"] = "失落的世界",
            ["silenthall"] = "无声钟塔", ["mutezone"] = "消音地带", ["mirror"] = "镜之境",
        };

        // 与 WorldGen.RegionWeights 完全一致的 argmax 判定 (硬边界, 不缝合)
        public static string RegionAt(float x, float z)
        {
            string best = RegionOrder[0];
            float bv = -1f;
            foreach (var name in RegionOrder)
            {
                var (cx, cz) = RegionPos[name];
                float rad = RegionRadius[name];
                float d = MathF.Sqrt((x - cx) * (x - cx) + (z - cz) * (z - cz));
                float v = 1f - Math3D.Clamp(d / (rad * 1.55f), 0f, 1f);
                float s = v * v * (3f - 2f * v);
                if (s > bv) { bv = s; best = name; }
            }
            return best;
        }
    }

    public class WorldGen
    {
        readonly int[] _permA, _permB, _permC;
        public int[] PermC => _permC;

        public WorldGen(int seed = 20260805)
        {
            _permA = Math3D.BuildPerm(seed);
            _permB = Math3D.BuildPerm(seed + 977);
            _permC = Math3D.BuildPerm(seed + 3313);
        }

        // 区域权重: argmax 硬切 (不缝合)
        public Dictionary<string, float[]> RegionWeights(float[] xs, float[] zs)
        {
            int n = xs.Length;
            var raw = new Dictionary<string, float[]>();
            foreach (var name in TerrainConfig.RegionOrder)
            {
                var (cx, cz) = TerrainConfig.RegionPos[name];
                float rad = TerrainConfig.RegionRadius[name];
                var w = new float[n];
                for (int i = 0; i < n; i++)
                {
                    float d = MathF.Sqrt((xs[i] - cx) * (xs[i] - cx) + (zs[i] - cz) * (zs[i] - cz));
                    float v = 1f - Math3D.Clamp(d / (rad * 1.55f), 0, 1);
                    float s = v * v * (3 - 2 * v);
                    w[i] = s;
                }
                raw[name] = w;
            }
            // argmax one-hot
            var ws = new Dictionary<string, float[]>();
            foreach (var name in TerrainConfig.RegionOrder) ws[name] = new float[n];
            for (int i = 0; i < n; i++)
            {
                string best = TerrainConfig.RegionOrder[0];
                float bv = -1;
                foreach (var name in TerrainConfig.RegionOrder)
                    if (raw[name][i] > bv) { bv = raw[name][i]; best = name; }
                ws[best][i] = 1f;
            }
            return ws;
        }

        public float HeightAt(float x, float z)
        {
            // 区域高度算子
            var ws = RegionWeights(new[] { x }, new[] { z });
            float h = 0;
            foreach (var name in TerrainConfig.RegionOrder)
            {
                if (ws[name][0] <= 0) continue;
                h += ws[name][0] * RegionHeight(name, x, z);
            }
            // 世界边界环山
            float edge = MathF.Max(MathF.Abs(x), MathF.Abs(z)) / TerrainConfig.HALF;
            float wall = Math3D.Clamp((edge - 0.80f) / 0.20f, 0, 1);
            h += wall * wall * 130f;
            return h;
        }

        float RegionHeight(string name, float x, float z)
        {
            float base_ = Math3D.Fbm2(x * 0.0021f, z * 0.0021f, 5, 2.05f, 0.52f, _permA) * 34f;
            switch (name)
            {
                case "wilds":
                    {
                        float h = base_ * 1.05f + Math3D.Fbm2(x * 0.0082f, z * 0.0082f, 4, 2.1f, 0.5f, _permB) * 11f;
                        float riv = MathF.Abs(Math3D.Fbm2(x * 0.0032f + 4, z * 0.0032f - 2, 3, 2f, 0.5f, _permC));
                        h -= MathF.Exp(-((riv - 0.06f) * 26f) * ((riv - 0.06f) * 26f)) * 7.5f;
                        return h + 8f;
                    }
                case "blackstone":
                    {
                        float ridge = Math3D.Ridged2(x * 0.0046f, z * 0.0046f, 5, 2.15f, 0.52f, _permB);
                        float h = 6f + ridge * 62f + base_ * 0.3f;
                        float crack = MathF.Abs(Math3D.Fbm2(x * 0.0125f - 8, z * 0.0125f + 5, 3, 2f, 0.5f, _permA));
                        h -= MathF.Exp(-((crack - 0.05f) * 34f) * ((crack - 0.05f) * 34f)) * 16f;
                        return h;
                    }
                case "lostland":
                    return 26f + Math3D.Fbm2(x * 0.0038f, z * 0.0038f, 4, 2f, 0.42f, _permC) * 13f
                        + MathF.Sin(x * 0.0125f) * MathF.Cos(z * 0.0112f) * 3.4f;
                case "silenthall":
                    {
                        var (cx, cz) = TerrainConfig.RegionPos["silenthall"];
                        float dr = MathF.Sqrt((x - cx) * (x - cx) + (z - cz) * (z - cz));
                        float bowl = Math3D.Clamp(dr / 150f, 0, 1.4f);
                        return 10f + bowl * bowl * 46f - 20f * MathF.Exp(-(dr / 46f) * (dr / 46f))
                            + Math3D.Fbm2(x * 0.0068f, z * 0.0068f, 4, 2f, 0.5f, _permA) * 6.5f;
                    }
                case "mutezone":
                    {
                        float h = 12f + Math3D.Fbm2(x * 0.003f, z * 0.003f, 3, 2f, 0.45f, _permB) * 5f;
                        float sink = Math3D.Fbm2(x * 0.0092f + 21, z * 0.0092f - 13, 3, 2f, 0.5f, _permC);
                        h -= Math3D.Clamp(sink - 0.18f, 0, 1) * 14f;
                        return h;
                    }
                case "mirror":
                    {
                        var (cx, cz) = TerrainConfig.RegionPos["mirror"];
                        float dr = MathF.Sqrt((x - cx) * (x - cx) + (z - cz) * (z - cz));
                        float rim = Math3D.Clamp((dr - 120f) / 90f, 0, 1);
                        return 18f + rim * rim * 40f + Math3D.Fbm2(x * 0.0052f, z * 0.0052f, 3, 2f, 0.5f, _permA) * 1.1f;
                    }
                default: return 10f;
            }
        }
    }

    public class Terrain
    {
        public int Vao, VaoShadow, Vbo, Ibo, IndexCount;
        public float[] Heights;      // (CELLS+1)^2
        public float[] Normals;
        public float[] Albedo;

        readonly WorldGen _gen;

        public Terrain(WorldGen gen)
        {
            _gen = gen;
            BuildHeightfield();
        }

        void BuildHeightfield()
        {
            int n = TerrainConfig.CELLS + 1;
            int count = n * n;
            var xs = new float[count]; var zs = new float[count];
            Heights = new float[count];
            for (int i = 0; i < n; i++)
                for (int j = 0; j < n; j++)
                {
                    int k = i * n + j;
                    xs[k] = -TerrainConfig.HALF + j * TerrainConfig.CELL;
                    zs[k] = -TerrainConfig.HALF + i * TerrainConfig.CELL;
                }
            for (int k = 0; k < count; k++) Heights[k] = _gen.HeightAt(xs[k], zs[k]);
            // 法线 (中心差分)
            Normals = new float[count * 3];
            for (int i = 1; i < n - 1; i++)
                for (int j = 1; j < n - 1; j++)
                {
                    int k = i * n + j;
                    float hR = Heights[k + 1], hL = Heights[k - 1];
                    float hU = Heights[k + n], hD = Heights[k - n];
                    float dx = (hR - hL) / (2 * TerrainConfig.CELL);
                    float dz = (hU - hD) / (2 * TerrainConfig.CELL);
                    var nrm = new Vec3(-dx, 1, -dz).Normalized();
                    Normals[k * 3] = nrm.X; Normals[k * 3 + 1] = nrm.Y; Normals[k * 3 + 2] = nrm.Z;
                }
            for (int k = 0; k < count; k++)
                if (Normals[k * 3 + 1] == 0) Normals[k * 3 + 1] = 1;
            // albedo: 区域基色
            var ws = _gen.RegionWeights(xs, zs);
            var permC = _gen.PermC;
            Albedo = new float[count * 3];
            for (int k = 0; k < count; k++)
            {
                float n1 = Math3D.Clamp(Math3D.Fbm2(xs[k] * 0.0068f, zs[k] * 0.0068f, 3, 2f, 0.5f, permC) * 1.4f + 0.5f, 0, 1);
                float r = 0, g = 0, b = 0;
                foreach (var name in TerrainConfig.RegionOrder)
                {
                    if (ws[name][k] <= 0) continue;
                    var pal = RegionAlbedo(name);
                    var c0 = pal[0]; var c1 = pal[1];
                    float wgt = ws[name][k];
                    r += wgt * (c0.Item1 * (1 - n1) + c1.Item1 * n1);
                    g += wgt * (c0.Item2 * (1 - n1) + c1.Item2 * n1);
                    b += wgt * (c0.Item3 * (1 - n1) + c1.Item3 * n1);
                }
                Albedo[k * 3] = r; Albedo[k * 3 + 1] = g; Albedo[k * 3 + 2] = b;
            }
        }

        static (float, float, float)[] RegionAlbedo(string name) => name switch
        {
            "wilds" => new[] { (0.222f, 0.220f, 0.206f), (0.190f, 0.190f, 0.182f) },
            "blackstone" => new[] { (0.062f, 0.060f, 0.070f), (0.104f, 0.098f, 0.108f) },
            "lostland" => new[] { (0.212f, 0.318f, 0.352f), (0.336f, 0.422f, 0.436f) },
            "silenthall" => new[] { (0.268f, 0.252f, 0.226f), (0.352f, 0.338f, 0.310f) },
            "mutezone" => new[] { (0.128f, 0.126f, 0.124f), (0.186f, 0.182f, 0.176f) },
            "mirror" => new[] { (0.028f, 0.030f, 0.042f), (0.062f, 0.066f, 0.086f) },
            _ => new[] { (0.2f, 0.2f, 0.2f), (0.2f, 0.2f, 0.2f) },
        };

        public void Upload()
        {
            int n = TerrainConfig.CELLS + 1;
            int count = n * n;
            // 顶点: pos3 + nrm3 + albedo3 = 9 floats
            var verts = new float[count * 9];
            for (int k = 0; k < count; k++)
            {
                int i = k / n, j = k % n;
                verts[k * 9] = -TerrainConfig.HALF + j * TerrainConfig.CELL;
                verts[k * 9 + 1] = Heights[k];
                verts[k * 9 + 2] = -TerrainConfig.HALF + i * TerrainConfig.CELL;
                verts[k * 9 + 3] = Normals[k * 3]; verts[k * 9 + 4] = Normals[k * 3 + 1]; verts[k * 9 + 5] = Normals[k * 3 + 2];
                verts[k * 9 + 6] = Albedo[k * 3]; verts[k * 9 + 7] = Albedo[k * 3 + 1]; verts[k * 9 + 8] = Albedo[k * 3 + 2];
            }
            // 索引
            var idx = new List<uint>();
            for (int i = 0; i < n - 1; i++)
                for (int j = 0; j < n - 1; j++)
                {
                    uint a = (uint)(i * n + j), b = a + 1, c = a + (uint)n, d = c + 1;
                    idx.Add(a); idx.Add(c); idx.Add(b); idx.Add(b); idx.Add(c); idx.Add(d);
                }
            IndexCount = idx.Count;
            Vbo = GL.GenBuffer();
            GL.BindBuffer(BufferTarget.ArrayBuffer, Vbo);
            GL.BufferData(BufferTarget.ArrayBuffer, verts.Length * 4, verts, BufferUsageHint.StaticDraw);
            Ibo = GL.GenBuffer();
            GL.BindBuffer(BufferTarget.ElementArrayBuffer, Ibo);
            GL.BufferData(BufferTarget.ElementArrayBuffer, idx.Count * 4, idx.ToArray(), BufferUsageHint.StaticDraw);
        }

        public void Release()
        {
            GL.DeleteBuffer(Vbo); GL.DeleteBuffer(Ibo);
            if (Vao > 0) GL.DeleteVertexArray(Vao);
            if (VaoShadow > 0) GL.DeleteVertexArray(VaoShadow);
        }
    }
}
