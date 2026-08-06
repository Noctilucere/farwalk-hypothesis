// Mesh.cs — 程序化网格生成 (C# 移植自 Python 版 mesh.py / terrain.py)
using System;
using System.Collections.Generic;
using Farwalk.Engine;

namespace Farwalk.World
{
    // 网格: 顶点 float[] (pos3+nrm3+uv2 或 pos3+nrm3) + 索引 uint[]
    public class MeshData
    {
        public float[] Verts;   // stride = Stride
        public uint[] Index;
        public int Stride = 6;  // pos3+nrm3 默认; 8 = +uv2
        public int VertexCount => Verts.Length / Stride;

        public static MeshData Merge(List<MeshData> parts)
        {
            if (parts.Count == 0) return new MeshData();
            int stride = parts[0].Stride;
            long vn = 0, inx = 0;
            foreach (var p in parts) { vn += p.Verts.Length / stride; inx += p.Index.Length; }
            var v = new float[vn * stride];
            var ix = new uint[inx];
            long vo = 0, io = 0;
            foreach (var p in parts)
            {
                uint baseV = (uint)(vo / stride);
                Array.Copy(p.Verts, 0, v, vo, p.Verts.Length);
                for (int i = 0; i < p.Index.Length; i++) ix[io + i] = p.Index[i] + baseV;
                vo += p.Verts.Length; io += p.Index.Length;
            }
            return new MeshData { Verts = v, Index = ix, Stride = stride };
        }
    }

    public static class MeshGen
    {
        static Random _rng = new(42);

        // 草叶: 单片带弯曲的 blade (pos3+nrm3)
        public static MeshData GrassBlade(float height, float bend, int variant)
        {
            var v = new List<float>(); var ix = new List<uint>();
            int segs = 4;
            for (int s = 0; s <= segs; s++)
            {
                float t = s / (float)segs;
                float y = t * height;
                float xo = bend * t * t;
                float w = 0.045f * (1f - t * 0.55f);
                for (int side = -1; side <= 1; side += 2)
                {
                    v.Add(side * w + xo); v.Add(y); v.Add(0);
                    v.Add(side * 0.15f); v.Add(0.25f); v.Add(1f);
                }
            }
            for (int s = 0; s < segs; s++)
            {
                uint a = (uint)(s * 2), b = a + 1, c = a + 2, d = a + 3;
                ix.Add(a); ix.Add(c); ix.Add(b); ix.Add(b); ix.Add(c); ix.Add(d);
            }
            return new MeshData { Verts = v.ToArray(), Index = ix.ToArray(), Stride = 6 };
        }

        public static MeshData Capsule(float radius, float height, int segR, int segH, bool withUV = false)
        {
            var v = new List<float>(); var ix = new List<uint>();
            int stride = withUV ? 8 : 6;
            void AddV(float x, float y, float z, float nx, float ny, float nz, float u = 0, float w = 0)
            {
                v.Add(x); v.Add(y); v.Add(z); v.Add(nx); v.Add(ny); v.Add(nz);
                if (withUV) { v.Add(u); v.Add(w); }
            }
            // 圆柱体 (简化胶囊: 圆柱 + 两端半球用圆锥近似)
            for (int i = 0; i <= segH; i++)
            {
                float t = i / (float)segH;
                float y = t * height;
                for (int j = 0; j <= segR; j++)
                {
                    float a = j / (float)segR * Math3D.TAU;
                    float c = MathF.Cos(a), s = MathF.Sin(a);
                    AddV(c * radius, y, s * radius, c, 0, s, j / (float)segR, t);
                }
            }
            for (int i = 0; i < segH; i++)
                for (int j = 0; j < segR; j++)
                {
                    uint a = (uint)(i * (segR + 1) + j), b = a + 1u, c = a + (uint)(segR + 1), d = c + 1u;
                    ix.Add(a); ix.Add(c); ix.Add(b); ix.Add(b); ix.Add(c); ix.Add(d);
                }
            // 顶帽 (圆锥)
            uint baseV = (uint)(v.Count / stride);
            AddV(0, height + radius * 0.7f, 0, 0, 1, 0);
            uint top = (uint)(v.Count / stride) - 1;
            for (int j = 0; j <= segR; j++)
            {
                float a = j / (float)segR * Math3D.TAU;
                AddV(MathF.Cos(a) * radius * 0.6f, height, MathF.Sin(a) * radius * 0.6f, MathF.Cos(a) * 0.3f, 0.9f, MathF.Sin(a) * 0.3f);
                uint b = (uint)(v.Count / stride) - 1;
                if (j > 0) { ix.Add(top); ix.Add(b); ix.Add(b - 1); }
            }
            var d1 = new MeshData { Verts = v.ToArray(), Index = ix.ToArray(), Stride = stride };
            return d1;
        }

        // 程序化 biped 猫兽人 (玩家/NPC 基础): 简化胶囊人形
        public static MeshData Character(float height, int seed)
        {
            _rng = new Random(seed);
            var parts = new List<MeshData>();
            float legH = height * 0.44f, torsoH = height * 0.34f, headR = height * 0.078f;
            // 腿
            for (int sx = -1; sx <= 1; sx += 2)
                parts.Add(Transform(Capsule(height * 0.052f, legH, 6, 8),
                    height * 0.065f * sx, 0, 0, 0, 0, 0, 1, 1, 1));
            // 躯干
            var torso = Transform(Capsule(height * 0.11f, torsoH, 7, 10),
                0, legH, 0, 0, 0, 0, 1.15f, 1f, 0.8f);
            parts.Add(torso);
            // 肩
            parts.Add(Transform(Capsule(height * 0.135f, height * 0.05f, 6, 4),
                0, legH + torsoH * 0.92f, 0, 0, 0, 0, 1.3f, 1f, 0.9f));
            // 臂
            for (int sx = -1; sx <= 1; sx += 2)
                parts.Add(Transform(Capsule(height * 0.038f, height * 0.34f, 5, 6),
                    sx * height * 0.135f, legH + torsoH * 0.6f, 0, sx * 0.12f, 0, 0, 1, 1, 1));
            // 头
            parts.Add(Transform(Capsule(headR, headR * 1.4f, 8, 8),
                0, legH + torsoH + headR, 0, 0, 0, 0, 1.1f, 1.1f, 1.1f));
            // 耳
            for (int sx = -1; sx <= 1; sx += 2)
                parts.Add(Transform(Capsule(headR * 0.3f, headR * 0.7f, 5, 4),
                    sx * headR * 0.6f, legH + torsoH + headR * 1.6f, 0, 0, 0, sx * 0.2f, 1, 1, 1));
            return MeshData.Merge(parts);
        }

        // 变换: 平移 + 旋转 (绕Y) + 缩放
        public static MeshData Transform(MeshData m, float tx, float ty, float tz,
            float rotX = 0, float rotY = 0, float rotZ = 0, float sx = 1, float sy = 1, float sz = 1)
        {
            int stride = m.Stride;
            var v = new float[m.Verts.Length];
            float cy = MathF.Cos(rotY), sy_ = MathF.Sin(rotY);
            float cx = MathF.Cos(rotX), sx_ = MathF.Sin(rotX);
            float cz = MathF.Cos(rotZ), sz_ = MathF.Sin(rotZ);
            for (int i = 0; i < m.Verts.Length; i += stride)
            {
                float px = m.Verts[i] * sx, py = m.Verts[i + 1] * sy, pz = m.Verts[i + 2] * sz;
                // rotZ
                float x1 = cz * px - sz_ * py, y1 = sz_ * px + cz * py, z1 = pz;
                // rotX
                float y2 = cx * y1 - sx_ * z1, z2 = sx_ * y1 + cx * z1;
                // rotY
                float x3 = cy * x1 + sy_ * z2, z3 = -sy_ * x1 + cy * z2;
                v[i] = x3 + tx; v[i + 1] = y2 + ty; v[i + 2] = z3 + tz;
                // 法线 (只旋转)
                float nx = m.Verts[i + 3], ny = m.Verts[i + 4], nz = m.Verts[i + 5];
                float nx1 = cz * nx - sz_ * ny, ny1 = sz_ * nx + cz * ny, nz1 = nz;
                float ny2 = cx * ny1 - sx_ * nz1, nz2 = sx_ * ny1 + cx * nz1;
                float nx3 = cy * nx1 + sy_ * nz2, nz3 = -sy_ * nx1 + cy * nz2;
                float l = MathF.Sqrt(nx3 * nx3 + ny2 * ny2 + nz3 * nz3);
                if (l < 1e-6f) l = 1;
                v[i + 3] = nx3 / l; v[i + 4] = ny2 / l; v[i + 5] = nz3 / l;
                if (stride == 8) { v[i + 6] = m.Verts[i + 6]; v[i + 7] = m.Verts[i + 7]; }
            }
            return new MeshData { Verts = v, Index = m.Index, Stride = stride };
        }
    }
}
