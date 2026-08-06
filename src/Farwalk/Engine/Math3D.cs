// Math3D.cs — 向量/矩阵/噪声工具 (C# 移植自 Python 版 math3d)
using System;

namespace Farwalk.Engine
{
    public struct Vec3
    {
        public float X, Y, Z;
        public Vec3(float x, float y, float z) { X = x; Y = y; Z = z; }
        public static Vec3 operator +(Vec3 a, Vec3 b) => new(a.X + b.X, a.Y + b.Y, a.Z + b.Z);
        public static Vec3 operator -(Vec3 a, Vec3 b) => new(a.X - b.X, a.Y - b.Y, a.Z - b.Z);
        public static Vec3 operator *(Vec3 a, float s) => new(a.X * s, a.Y * s, a.Z * s);
        public static Vec3 operator *(float s, Vec3 a) => a * s;
        public static Vec3 operator /(Vec3 a, float s) => new(a.X / s, a.Y / s, a.Z / s);
        public float Length() => MathF.Sqrt(X * X + Y * Y + Z * Z);
        public Vec3 Normalized()
        {
            float l = Length();
            return l < 1e-6f ? this : this / l;
        }
        public static float Dot(Vec3 a, Vec3 b) => a.X * b.X + a.Y * b.Y + a.Z * b.Z;
        public static Vec3 Cross(Vec3 a, Vec3 b) => new(
            a.Y * b.Z - a.Z * b.Y,
            a.Z * b.X - a.X * b.Z,
            a.X * b.Y - a.Y * b.X);
        public static Vec3 Lerp(Vec3 a, Vec3 b, float t) => a + (b - a) * t;
        public override string ToString() => $"({X:F2},{Y:F2},{Z:F2})";
    }

    public static class Math3D
    {
        public const float PI = 3.14159265f;
        public const float TAU = 6.2831853f;

        public static float Clamp(float v, float lo, float hi) => v < lo ? lo : (v > hi ? hi : v);
        public static int ClampI(int v, int lo, int hi) => v < lo ? lo : (v > hi ? hi : v);
        public static float Damp(float cur, float tgt, float k, float dt) =>
            cur + (tgt - cur) * (1f - MathF.Exp(-k * 120f * dt));
        public static float Lerp(float a, float b, float t) => a + (b - a) * t;
        public static float Smoothstep(float e0, float e1, float x)
        {
            float t = Clamp((x - e0) / (e1 - e0), 0f, 1f);
            return t * t * (3f - 2f * t);
        }

        public static float[] Mat4Identity()
        {
            var m = new float[16];
            m[0] = m[5] = m[10] = m[15] = 1f;
            return m;
        }

        // 列主序 mat4 (OpenGL 风格)
        public static float[] Perspective(float fovyDeg, float aspect, float zn, float zf)
        {
            float f = 1f / MathF.Tan(fovyDeg * PI / 360f);
            var m = new float[16];
            m[0] = f / aspect; m[5] = f; m[10] = (zf + zn) / (zn - zf); m[11] = -1f;
            m[14] = (2f * zf * zn) / (zn - zf);
            return m;
        }

        public static float[] Ortho(float l, float r, float b, float t, float zn, float zf)
        {
            var m = new float[16];
            m[0] = 2f / (r - l); m[5] = 2f / (t - b); m[10] = -2f / (zf - zn);
            m[12] = -(r + l) / (r - l); m[13] = -(t + b) / (t - b); m[14] = -(zf + zn) / (zf - zn);
            m[15] = 1f;
            return m;
        }

        public static float[] LookAt(Vec3 eye, Vec3 center, Vec3? upHint = null)
        {
            Vec3 up = upHint ?? new Vec3(0, 1, 0);
            Vec3 f = (center - eye).Normalized();
            Vec3 s = Vec3.Cross(f, up).Normalized();
            Vec3 u = Vec3.Cross(s, f);
            var m = new float[16];
            m[0] = s.X; m[1] = u.X; m[2] = -f.X; m[3] = 0;
            m[4] = s.Y; m[5] = u.Y; m[6] = -f.Y; m[7] = 0;
            m[8] = s.Z; m[9] = u.Z; m[10] = -f.Z; m[11] = 0;
            m[12] = -Vec3.Dot(s, eye); m[13] = -Vec3.Dot(u, eye); m[14] = Vec3.Dot(f, eye); m[15] = 1;
            return m;
        }

        // 矩阵乘法 (列主序)
        public static float[] Mul(float[] a, float[] b)
        {
            var o = new float[16];
            for (int c = 0; c < 4; c++)
                for (int r = 0; r < 4; r++)
                {
                    float s = 0;
                    for (int k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k];
                    o[c * 4 + r] = s;
                }
            return o;
        }

        // ---- 值噪声 ----
        public static int[] BuildPerm(int seed)
        {
            var p = new int[512];
            var rnd = new Random(seed);
            var base_ = new int[256];
            for (int i = 0; i < 256; i++) base_[i] = i;
            for (int i = 255; i > 0; i--)
            {
                int j = rnd.Next(i + 1);
                (base_[i], base_[j]) = (base_[j], base_[i]);
            }
            for (int i = 0; i < 512; i++) p[i] = base_[i & 255];
            return p;
        }

        static float Grad(int h, float x, float y, float z)
        {
            h &= 15;
            float u = h < 8 ? x : y;
            float v = h < 4 ? y : (h == 12 || h == 14 ? x : z);
            return ((h & 1) == 0 ? u : -u) + ((h & 2) == 0 ? v : -v);
        }

        public static float Noise3(float x, float y, float z, int[] perm)
        {
            int X = (int)MathF.Floor(x) & 255, Y = (int)MathF.Floor(y) & 255, Z = (int)MathF.Floor(z) & 255;
            x -= MathF.Floor(x); y -= MathF.Floor(y); z -= MathF.Floor(z);
            float u = x * x * (3 - 2 * x), v = y * y * (3 - 2 * y), w = z * z * (3 - 2 * z);
            int A = perm[X] + Y, AA = perm[A] + Z, AB = perm[A + 1] + Z;
            int B = perm[X + 1] + Y, BA = perm[B] + Z, BB = perm[B + 1] + Z;
            return Lerp(
                Lerp(Lerp(Grad(perm[AA], x, y, z), Grad(perm[BA], x - 1, y, z), u),
                     Lerp(Grad(perm[AB], x, y - 1, z), Grad(perm[BB], x - 1, y - 1, z), u), v),
                Lerp(Lerp(Grad(perm[AA + 1], x, y, z - 1), Grad(perm[BA + 1], x - 1, y, z - 1), u),
                     Lerp(Grad(perm[AB + 1], x, y - 1, z - 1), Grad(perm[BB + 1], x - 1, y - 1, z - 1), u), v),
                w);
        }

        public static float Fbm2(float x, float y, int oct, float lac, float gain, int[] perm)
        {
            float total = 0, amp = 1, freq = 1, norm = 0;
            for (int i = 0; i < oct; i++)
            {
                total += Noise3(x * freq, y * freq, 0.5f, perm) * amp;
                norm += amp;
                amp *= gain; freq *= lac;
            }
            return total / norm;
        }

        public static float Ridged2(float x, float y, int oct, float lac, float gain, int[] perm)
        {
            float total = 0, amp = 1, freq = 1, norm = 0;
            for (int i = 0; i < oct; i++)
            {
                float n = 1f - MathF.Abs(Noise3(x * freq, y * freq, 0.3f, perm));
                total += n * n * amp;
                norm += amp; amp *= gain; freq *= lac;
            }
            return total / norm;
        }
    }
}
