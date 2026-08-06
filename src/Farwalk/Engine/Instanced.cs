// Instanced.cs — 实例化渲染 (草/树/建筑/NPC/收集品)
using System;
using System.Collections.Generic;
using OpenTK.Graphics.OpenGL4;
using Farwalk.World;

namespace Farwalk.Engine
{
    // 单组实例: 共享一个 MeshData, 每实例 16 floats (3x4 矩阵 + tint)
    public class InstancedGroup
    {
        public int Vao, Vbo, InstVbo, Ibo;
        public int IndexCount;
        public int MaxInstances = 512;
        public int Count;
        public float[] InstanceData = Array.Empty<float>();

        public void Setup(float[] verts, uint[] idx, int stride)
        {
            Vbo = GL.GenBuffer();
            GL.BindBuffer(BufferTarget.ArrayBuffer, Vbo);
            GL.BufferData(BufferTarget.ArrayBuffer, verts.Length * 4, verts, BufferUsageHint.StaticDraw);
            Ibo = GL.GenBuffer();
            GL.BindBuffer(BufferTarget.ElementArrayBuffer, Ibo);
            GL.BufferData(BufferTarget.ElementArrayBuffer, idx.Length * 4, idx, BufferUsageHint.StaticDraw);
            IndexCount = idx.Length;

            InstVbo = GL.GenBuffer();
            InstanceData = new float[MaxInstances * 16];
            GL.BindBuffer(BufferTarget.ArrayBuffer, InstVbo);
            GL.BufferData(BufferTarget.ArrayBuffer, InstanceData.Length * 4, InstanceData, BufferUsageHint.DynamicDraw);

            Vao = GL.GenVertexArray();
            GL.BindVertexArray(Vao);
            GL.BindBuffer(BufferTarget.ArrayBuffer, Vbo);
            GL.EnableVertexAttribArray(0);
            GL.VertexAttribPointer(0, 3, VertexAttribPointerType.Float, false, stride * 4, 0);
            GL.EnableVertexAttribArray(1);
            GL.VertexAttribPointer(1, 3, VertexAttribPointerType.Float, false, stride * 4, 3 * 4);
            GL.BindBuffer(BufferTarget.ArrayBuffer, InstVbo);
            for (int i = 0; i < 4; i++)
            {
                int loc = 2 + i;
                GL.EnableVertexAttribArray(loc);
                GL.VertexAttribPointer(loc, 4, VertexAttribPointerType.Float, false, 16 * 4, i * 16);
                GL.VertexAttribDivisor(loc, 1);
            }
            GL.BindVertexArray(0);
        }

        public void Upload(float[] data)
        {
            Count = data.Length / 16;
            if (Count == 0) return;
            if (Count > MaxInstances)
            {
                MaxInstances = Math.Max(Count * 2, MaxInstances);
                InstanceData = new float[MaxInstances * 16];
                GL.BindBuffer(BufferTarget.ArrayBuffer, InstVbo);
                GL.BufferData(BufferTarget.ArrayBuffer, InstanceData.Length * 4, InstanceData, BufferUsageHint.DynamicDraw);
            }
            Array.Copy(data, InstanceData, data.Length);
            GL.BindBuffer(BufferTarget.ArrayBuffer, InstVbo);
            GL.BufferSubData(BufferTarget.ArrayBuffer, 0, data.Length * 4, data);
        }

        public void Draw()
        {
            if (Count <= 0) return;
            GL.BindVertexArray(Vao);
            GL.BindBuffer(BufferTarget.ElementArrayBuffer, Ibo);
            GL.DrawElementsInstanced(PrimitiveType.Triangles, IndexCount, DrawElementsType.UnsignedInt, 0, Count);
        }

        public void Release()
        {
            GL.DeleteVertexArray(Vao);
            GL.DeleteBuffer(Vbo);
            GL.DeleteBuffer(InstVbo);
            GL.DeleteBuffer(Ibo);
        }
    }

    public class ScatterWorld
    {
        public List<(InstancedGroup group, string tag)> Groups = new();

        public InstancedGroup Add(MeshData mesh, float[] instanceData, string tag)
        {
            var g = new InstancedGroup();
            g.Setup(mesh.Verts, mesh.Index, mesh.Stride);
            g.Upload(instanceData);
            Groups.Add((g, tag));
            return g;
        }

        public void DrawAll(Shader s)
        {
            foreach (var (g, _) in Groups) g.Draw();
        }

        public void ReleaseAll()
        {
            foreach (var (g, _) in Groups) g.Release();
            Groups.Clear();
        }
    }

    // 实例数据打包工具
    public static class InstPack
    {
        // positions + rotY + scale + tint -> float[16*n]
        public static float[] Pack(float[] px, float[] py, float[] pz,
            float[] rotY, float[] sx, float[] sy, float[] sz,
            float[] tintR, float[] tintG, float[] tintB)
        {
            int n = px.Length;
            var o = new float[n * 16];
            for (int i = 0; i < n; i++)
            {
                float c = MathF.Cos(rotY[i]), s = MathF.Sin(rotY[i]);
                int b = i * 16;
                o[b + 0] = c * sx[i]; o[b + 1] = 0; o[b + 2] = -s * sz[i]; o[b + 3] = px[i];
                o[b + 4] = 0; o[b + 5] = sy[i]; o[b + 6] = 0; o[b + 7] = py[i];
                o[b + 8] = s * sx[i]; o[b + 9] = 0; o[b + 10] = c * sz[i]; o[b + 11] = pz[i];
                o[b + 12] = tintR[i]; o[b + 13] = tintG[i]; o[b + 14] = tintB[i]; o[b + 15] = 0;
            }
            return o;
        }
    }
}
