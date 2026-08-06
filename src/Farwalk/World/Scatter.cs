// Scatter.cs — 场景散置生成 (草/树/岩石/建筑/NPC 位置)
using System;
using System.Collections.Generic;
using Farwalk.Engine;

namespace Farwalk.World
{
    public class ScatterGen
    {
        readonly WorldGen _gen;
        readonly Random _rng = new(777);

        public ScatterGen(WorldGen gen) { _gen = gen; }

        // 在区域随机采样 n 个地面点
        public (float[] xs, float[] ys, float[] zs) Sample(string region, int n, float minSlope = 0.5f)
        {
            var (cx, cz) = TerrainConfig.RegionPos[region];
            float rad = TerrainConfig.RegionRadius[region] * 0.85f;
            var xs = new List<float>(); var ys = new List<float>(); var zs = new List<float>();
            for (int i = 0; i < n * 4; i++)
            {
                if (xs.Count >= n) break;
                float x = cx + (float)(_rng.NextDouble() * 2 - 1) * rad;
                float z = cz + (float)(_rng.NextDouble() * 2 - 1) * rad;
                float h = _gen.HeightAt(x, z);
                if (h < TerrainConfig.WATER_LEVEL + 0.5f) continue;
                // 斜坡检查 (采样相邻点)
                float hx = _gen.HeightAt(x + 1.5f, z);
                float hz = _gen.HeightAt(x, z + 1.5f);
                if (MathF.Abs(hx - h) > 2.5f || MathF.Abs(hz - h) > 2.5f) continue;
                xs.Add(x); ys.Add(h); zs.Add(z);
            }
            return (xs.ToArray(), ys.ToArray(), zs.ToArray());
        }

        // 构建草 (两组草叶)
        public MeshData GrassMesh(int variant)
        {
            var parts = new List<MeshData>();
            for (int b = 0; b < 4; b++)
            {
                float h = (float)_rng.NextDouble() * 0.5f + 0.55f;
                float bend = (float)_rng.NextDouble() * 0.12f + 0.06f;
                parts.Add(MeshGen.GrassBlade(h, bend, variant));
            }
            return MeshData.Merge(parts);
        }

        // 树 (简化锥体)
        public MeshData TreeMesh()
        {
            var trunk = MeshGen.Capsule(0.18f, 1.8f, 6, 6);
            var cone = MeshGen.Capsule(1.3f, 1.2f, 8, 4); // 圆锥近似用胶囊
            return MeshData.Merge(new List<MeshData> { trunk, cone });
        }

        // 岩石
        public MeshData RockMesh()
        {
            var parts = new List<MeshData>();
            for (int i = 0; i < 3; i++)
            {
                float r = (float)_rng.NextDouble() * 0.3f + 0.25f;
                var m = MeshGen.Capsule(r, r * 0.7f, 6, 4);
                parts.Add(MeshGen.Transform(m,
                    (float)(_rng.NextDouble() * 0.8 - 0.4), r * 0.35f, (float)(_rng.NextDouble() * 0.8 - 0.4),
                    0, (float)(_rng.NextDouble() * 0.6), (float)(_rng.NextDouble() * 0.6)));
            }
            return MeshData.Merge(parts);
        }
    }
}
