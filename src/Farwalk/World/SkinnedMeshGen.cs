// SkinnedMeshGen.cs — 带骨骼权重的角色网格 (GPU 蒙皮)
// 顶点格式: pos3 + nrm3 + boneIdx2 + boneWeight2 = stride 10
using System;
using System.Collections.Generic;
using Farwalk.Engine;

namespace Farwalk.World
{
    public class SkinnedMeshData
    {
        public float[] Verts = Array.Empty<float>();
        public uint[] Index = Array.Empty<uint>();
        public const int STRIDE = 10;
        public int VertexCount => Verts.Length / STRIDE;
    }

    public static class SkinnedMeshGen
    {
        // 把 stride6 网格转换为带权重的 stride10 网格
        static SkinnedMeshData Bind(MeshData m, Func<float, float, float, (int, int, float, float)> weightFn)
        {
            int n = m.Verts.Length / m.Stride;
            var v = new float[n * SkinnedMeshData.STRIDE];
            for (int i = 0; i < n; i++)
            {
                int s = i * m.Stride, d = i * SkinnedMeshData.STRIDE;
                float px = m.Verts[s], py = m.Verts[s + 1], pz = m.Verts[s + 2];
                v[d] = px; v[d + 1] = py; v[d + 2] = pz;
                v[d + 3] = m.Verts[s + 3]; v[d + 4] = m.Verts[s + 4]; v[d + 5] = m.Verts[s + 5];
                var (i0, i1, w0, w1) = weightFn(px, py, pz);
                float sum = w0 + w1;
                if (sum < 1e-5f) { w0 = 1f; w1 = 0f; }
                else { w0 /= sum; w1 /= sum; }
                v[d + 6] = i0; v[d + 7] = i1;
                v[d + 8] = w0; v[d + 9] = w1;
            }
            return new SkinnedMeshData { Verts = v, Index = m.Index };
        }

        static SkinnedMeshData MergeSkinned(List<SkinnedMeshData> parts)
        {
            long vn = 0, inx = 0;
            foreach (var p in parts) { vn += p.Verts.Length; inx += p.Index.Length; }
            var v = new float[vn];
            var ix = new uint[inx];
            long vo = 0, io = 0;
            foreach (var p in parts)
            {
                uint baseV = (uint)(vo / SkinnedMeshData.STRIDE);
                Array.Copy(p.Verts, 0, v, vo, p.Verts.Length);
                for (int i = 0; i < p.Index.Length; i++) ix[io + i] = p.Index[i] + baseV;
                vo += p.Verts.Length; io += p.Index.Length;
            }
            return new SkinnedMeshData { Verts = v, Index = ix };
        }

        /// <summary>
        /// 程序化人外角色 (猫兽人 biped), 与 Skeleton(height) 的绑定姿态严格对齐。
        /// </summary>
        public static SkinnedMeshData Character(float height = 1.74f)
        {
            float legH = height * 0.44f;
            float torsoH = height * 0.34f;
            float headR = height * 0.078f;
            float hipX = height * 0.065f;
            float shX = height * 0.135f;
            float shY = legH + torsoH * 0.88f;
            float armLen = height * 0.34f;
            float spineY = legH + torsoH * 0.55f;
            float headY = legH + torsoH;

            var parts = new List<SkinnedMeshData>();

            // ---- 腿 (LegL / LegR, 权重 1) ----
            for (int s = -1; s <= 1; s += 2)
            {
                int bone = s > 0 ? Bone.LegL : Bone.LegR;
                var leg = MeshGen.Transform(MeshGen.Capsule(height * 0.055f, legH, 7, 8),
                    hipX * s, 0, 0);
                parts.Add(Bind(leg, (x, y, z) =>
                {
                    // 顶端靠近髋部时与 hips 融合, 避免撕裂
                    float t = Math3D.Clamp((y - legH * 0.78f) / (legH * 0.28f), 0f, 1f);
                    return (bone, Bone.Hips, 1f - t * 0.45f, t * 0.45f);
                }));
            }

            // ---- 躯干 (Hips → Spine 渐变) ----
            {
                var torso = MeshGen.Transform(MeshGen.Capsule(height * 0.108f, torsoH, 9, 12),
                    0, legH, 0, 0, 0, 0, 1.16f, 1f, 0.82f);
                parts.Add(Bind(torso, (x, y, z) =>
                {
                    float t = Math3D.Smoothstep(0f, 1f, Math3D.Clamp((y - legH) / MathF.Max(torsoH, 1e-3f), 0f, 1f));
                    return (Bone.Spine, Bone.Hips, t, 1f - t);
                }));
            }

            // ---- 肩部 ----
            {
                var sh = MeshGen.Transform(MeshGen.Capsule(height * 0.132f, height * 0.05f, 8, 4),
                    0, shY - height * 0.03f, 0, 0, 0, 0, 1.3f, 1f, 0.9f);
                parts.Add(Bind(sh, (x, y, z) => (Bone.Spine, Bone.Spine, 1f, 0f)));
            }

            // ---- 手臂 (向下悬垂, rotX = PI 翻转胶囊朝向) ----
            for (int s = -1; s <= 1; s += 2)
            {
                int bone = s > 0 ? Bone.ArmL : Bone.ArmR;
                var arm = MeshGen.Transform(MeshGen.Capsule(height * 0.038f, armLen, 6, 7),
                    shX * s, shY, 0, MathF.PI, 0, 0);
                parts.Add(Bind(arm, (x, y, z) =>
                {
                    float t = Math3D.Clamp((y - (shY - height * 0.05f)) / (height * 0.06f), 0f, 1f);
                    return (bone, Bone.Spine, 1f - t * 0.4f, t * 0.4f);
                }));
            }

            // ---- 头 ----
            {
                var head = MeshGen.Transform(MeshGen.Capsule(headR, headR * 1.35f, 10, 8),
                    0, headY, 0, 0, 0, 0, 1.12f, 1.1f, 1.08f);
                parts.Add(Bind(head, (x, y, z) =>
                {
                    float t = Math3D.Clamp((y - headY) / (headR * 0.5f), 0f, 1f);
                    return (Bone.Head, Bone.Spine, 0.55f + t * 0.45f, 0.45f * (1f - t));
                }));
            }

            // ---- 耳 (人外特征) ----
            for (int s = -1; s <= 1; s += 2)
            {
                var ear = MeshGen.Transform(MeshGen.Capsule(headR * 0.30f, headR * 0.78f, 6, 4),
                    s * headR * 0.62f, headY + headR * 1.28f, 0, 0, 0, s * 0.26f);
                parts.Add(Bind(ear, (x, y, z) => (Bone.Head, Bone.Head, 1f, 0f)));
            }

            // ---- 尾 (三节, 全部绑到 Tail) ----
            {
                float ty = legH + height * 0.02f, tz = height * 0.075f;
                var segs = new List<MeshData>();
                float curY = ty, curZ = tz;
                for (int i = 0; i < 3; i++)
                {
                    float r = height * (0.026f - i * 0.006f);
                    float len = height * 0.13f;
                    // 逐节向后下方倾斜
                    float ang = 1.95f + i * 0.22f;
                    segs.Add(MeshGen.Transform(MeshGen.Capsule(r, len, 6, 4), 0, curY, curZ, ang, 0, 0));
                    curY += MathF.Cos(ang) * len;
                    curZ += MathF.Sin(ang) * len;
                }
                var tail = MeshData.Merge(segs);
                parts.Add(Bind(tail, (x, y, z) => (Bone.Tail, Bone.Hips, 0.85f, 0.15f)));
            }

            return MergeSkinned(parts);
        }
    }
}
