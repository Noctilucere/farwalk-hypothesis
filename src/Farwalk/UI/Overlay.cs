// Overlay.cs — 2D 正交叠加层: 矩形 / 线 / 圆 / 图片 / 文本 (统一批次绘制)
using System;
using System.Collections.Generic;
using System.Runtime.Versioning;
using Farwalk.Engine;
using OpenTK.Graphics.OpenGL4;

namespace Farwalk.UI
{
    public struct Col
    {
        public float R, G, B, A;
        public Col(float r, float g, float b, float a = 1f) { R = r; G = g; B = b; A = a; }
        public static Col Rgb(int hex, float a = 1f) => new(
            ((hex >> 16) & 0xFF) / 255f, ((hex >> 8) & 0xFF) / 255f, (hex & 0xFF) / 255f, a);
        public Col WithA(float a) => new(R, G, B, a);
    }

    [SupportedOSPlatform("windows")]
    public class Overlay : IDisposable
    {
        // 顶点: x, y, u, v, r, g, b, a
        const int STRIDE = 8;
        readonly List<float> _verts = new(1 << 16);
        readonly List<(int mode, int start, int count, int tex)> _cmds = new();

        int _vao, _vbo, _capacity;
        Shader _shader = null!;
        public TextAtlas Font = null!;
        public TextAtlas FontSmall = null!;
        public TextAtlas FontBig = null!;

        int _w = 1, _h = 1;
        int _curMode = -1, _curTex = -1, _curStart;

        public void Init(int w, int h)
        {
            _w = w; _h = h;
            _shader = new Shader(VS, FS);
            _vao = GL.GenVertexArray();
            _vbo = GL.GenBuffer();
            GL.BindVertexArray(_vao);
            GL.BindBuffer(BufferTarget.ArrayBuffer, _vbo);
            _capacity = 1 << 16;
            GL.BufferData(BufferTarget.ArrayBuffer, _capacity * 4, IntPtr.Zero, BufferUsageHint.DynamicDraw);
            GL.EnableVertexAttribArray(0);
            GL.VertexAttribPointer(0, 2, VertexAttribPointerType.Float, false, STRIDE * 4, 0);
            GL.EnableVertexAttribArray(1);
            GL.VertexAttribPointer(1, 2, VertexAttribPointerType.Float, false, STRIDE * 4, 2 * 4);
            GL.EnableVertexAttribArray(2);
            GL.VertexAttribPointer(2, 4, VertexAttribPointerType.Float, false, STRIDE * 4, 4 * 4);
            GL.BindVertexArray(0);

            FontSmall = new TextAtlas(19f);
            Font = new TextAtlas(25f);
            FontBig = new TextAtlas(38f);
        }

        public void Resize(int w, int h) { _w = w; _h = h; }
        public int Width => _w;
        public int Height => _h;

        public void Begin()
        {
            _verts.Clear();
            _cmds.Clear();
            _curMode = -1; _curTex = -1; _curStart = 0;
        }

        void Mode(int mode, int tex)
        {
            if (_curMode == mode && _curTex == tex) return;
            FlushCmd();
            _curMode = mode; _curTex = tex; _curStart = _verts.Count / STRIDE;
        }

        void FlushCmd()
        {
            if (_curMode < 0) return;
            int count = _verts.Count / STRIDE - _curStart;
            if (count > 0) _cmds.Add((_curMode, _curStart, count, _curTex));
        }

        void V(float x, float y, float u, float v, in Col c)
        {
            _verts.Add(x); _verts.Add(y); _verts.Add(u); _verts.Add(v);
            _verts.Add(c.R); _verts.Add(c.G); _verts.Add(c.B); _verts.Add(c.A);
        }

        void Quad(float x, float y, float w, float h, float u0, float v0, float u1, float v1, in Col c)
        {
            V(x, y, u0, v0, c); V(x + w, y, u1, v0, c); V(x + w, y + h, u1, v1, c);
            V(x, y, u0, v0, c); V(x + w, y + h, u1, v1, c); V(x, y + h, u0, v1, c);
        }

        // ---------- 图形 ----------
        public void Rect(float x, float y, float w, float h, Col c)
        {
            Mode(0, 0);
            Quad(x, y, w, h, 0, 0, 0, 0, c);
        }

        public void RectOutline(float x, float y, float w, float h, float t, Col c)
        {
            Rect(x, y, w, t, c);
            Rect(x, y + h - t, w, t, c);
            Rect(x, y + t, t, h - t * 2, c);
            Rect(x + w - t, y + t, t, h - t * 2, c);
        }

        // 竖直渐变矩形
        public void RectV(float x, float y, float w, float h, Col top, Col bottom)
        {
            Mode(0, 0);
            V(x, y, 0, 0, top); V(x + w, y, 0, 0, top); V(x + w, y + h, 0, 0, bottom);
            V(x, y, 0, 0, top); V(x + w, y + h, 0, 0, bottom); V(x, y + h, 0, 0, bottom);
        }

        public void Line(float x0, float y0, float x1, float y1, float t, Col c)
        {
            float dx = x1 - x0, dy = y1 - y0;
            float len = MathF.Sqrt(dx * dx + dy * dy);
            if (len < 1e-4f) return;
            float nx = -dy / len * t * 0.5f, ny = dx / len * t * 0.5f;
            Mode(0, 0);
            V(x0 + nx, y0 + ny, 0, 0, c); V(x1 + nx, y1 + ny, 0, 0, c); V(x1 - nx, y1 - ny, 0, 0, c);
            V(x0 + nx, y0 + ny, 0, 0, c); V(x1 - nx, y1 - ny, 0, 0, c); V(x0 - nx, y0 - ny, 0, 0, c);
        }

        public void Circle(float cx, float cy, float r, Col c, int segs = 20)
        {
            Mode(0, 0);
            for (int i = 0; i < segs; i++)
            {
                float a0 = i / (float)segs * Math3D.TAU, a1 = (i + 1) / (float)segs * Math3D.TAU;
                V(cx, cy, 0, 0, c);
                V(cx + MathF.Cos(a0) * r, cy + MathF.Sin(a0) * r, 0, 0, c);
                V(cx + MathF.Cos(a1) * r, cy + MathF.Sin(a1) * r, 0, 0, c);
            }
        }

        public void CircleOutline(float cx, float cy, float r, float t, Col c, int segs = 36)
        {
            for (int i = 0; i < segs; i++)
            {
                float a0 = i / (float)segs * Math3D.TAU, a1 = (i + 1) / (float)segs * Math3D.TAU;
                Line(cx + MathF.Cos(a0) * r, cy + MathF.Sin(a0) * r,
                     cx + MathF.Cos(a1) * r, cy + MathF.Sin(a1) * r, t, c);
            }
        }

        // 等边三角形标记 (朝上)
        public void Marker(float cx, float cy, float r, Col c)
        {
            Mode(0, 0);
            V(cx, cy - r, 0, 0, c);
            V(cx + r * 0.86f, cy + r * 0.6f, 0, 0, c);
            V(cx - r * 0.86f, cy + r * 0.6f, 0, 0, c);
        }

        public void Image(int tex, float x, float y, float w, float h, Col tint,
            float u0 = 0, float v0 = 0, float u1 = 1, float v1 = 1)
        {
            Mode(2, tex);
            Quad(x, y, w, h, u0, v0, u1, v1, tint);
        }

        // ---------- 文本 ----------
        public float Text(string s, float x, float y, Col c, TextAtlas? atlas = null, float scale = 1f)
        {
            var f = atlas ?? Font;
            Mode(1, f.Texture);
            float cx = x;
            foreach (var ch in s)
            {
                if (ch == '\n') continue;
                var g = f.Ensure(ch);
                if (!char.IsWhiteSpace(ch))
                    Quad(cx, y, g.W * scale, g.H * scale, g.U0, g.V0, g.U1, g.V1, c);
                cx += g.Advance * scale;
            }
            return cx - x;
        }

        public float TextShadow(string s, float x, float y, Col c, TextAtlas? atlas = null, float scale = 1f)
        {
            Text(s, x + 1.6f, y + 1.6f, new Col(0, 0, 0, c.A * 0.72f), atlas, scale);
            return Text(s, x, y, c, atlas, scale);
        }

        public float TextCentered(string s, float cx, float y, Col c, TextAtlas? atlas = null, float scale = 1f)
        {
            var f = atlas ?? Font;
            float w = f.Measure(s, scale);
            return TextShadow(s, cx - w * 0.5f, y, c, f, scale);
        }

        public float TextRight(string s, float rx, float y, Col c, TextAtlas? atlas = null, float scale = 1f)
        {
            var f = atlas ?? Font;
            float w = f.Measure(s, scale);
            return TextShadow(s, rx - w, y, c, f, scale);
        }

        /// <summary>自动换行绘制, 返回消耗的行数。</summary>
        public int TextWrapped(string s, float x, float y, float maxW, float lineH, Col c,
            TextAtlas? atlas = null, float scale = 1f)
        {
            var f = atlas ?? Font;
            float cx = x, cy = y;
            int lines = 1;
            foreach (var ch in s)
            {
                if (ch == '\n')
                {
                    cx = x; cy += lineH; lines++;
                    continue;
                }
                var g = f.Ensure(ch);
                if (cx - x + g.Advance * scale > maxW)
                {
                    cx = x; cy += lineH; lines++;
                }
                Mode(1, f.Texture);
                if (!char.IsWhiteSpace(ch))
                {
                    Quad(cx + 1.4f, cy + 1.4f, g.W * scale, g.H * scale, g.U0, g.V0, g.U1, g.V1,
                        new Col(0, 0, 0, c.A * 0.7f));
                    Quad(cx, cy, g.W * scale, g.H * scale, g.U0, g.V0, g.U1, g.V1, c);
                }
                cx += g.Advance * scale;
            }
            return lines;
        }

        // ---------- 提交 ----------
        public void End()
        {
            FlushCmd();
            if (_verts.Count == 0) return;

            var arr = _verts.ToArray();
            GL.BindVertexArray(_vao);
            GL.BindBuffer(BufferTarget.ArrayBuffer, _vbo);
            if (arr.Length > _capacity)
            {
                _capacity = arr.Length * 2;
                GL.BufferData(BufferTarget.ArrayBuffer, _capacity * 4, IntPtr.Zero, BufferUsageHint.DynamicDraw);
            }
            GL.BufferSubData(BufferTarget.ArrayBuffer, 0, arr.Length * 4, arr);

            GL.Disable(EnableCap.DepthTest);
            GL.Enable(EnableCap.Blend);
            GL.BlendFunc(BlendingFactor.SrcAlpha, BlendingFactor.OneMinusSrcAlpha);

            _shader.Use();
            _shader.SetMat4("uProj", Math3D.Ortho(0, _w, _h, 0, -1, 1));
            foreach (var (mode, start, count, tex) in _cmds)
            {
                _shader.SetI("uMode", mode);
                if (mode != 0)
                {
                    GL.ActiveTexture(TextureUnit.Texture0);
                    GL.BindTexture(TextureTarget.Texture2D, tex);
                    _shader.SetI("uTex", 0);
                }
                GL.DrawArrays(PrimitiveType.Triangles, start, count);
            }
            GL.BindVertexArray(0);
            GL.Disable(EnableCap.Blend);
        }

        public void Dispose()
        {
            Font?.Dispose(); FontSmall?.Dispose(); FontBig?.Dispose();
            GL.DeleteVertexArray(_vao);
            GL.DeleteBuffer(_vbo);
        }

        const string VS = """
        #version 330 core
        layout(location=0) in vec2 aPos;
        layout(location=1) in vec2 aUv;
        layout(location=2) in vec4 aCol;
        out vec2 vUv; out vec4 vCol;
        uniform mat4 uProj;
        void main(){ vUv = aUv; vCol = aCol; gl_Position = uProj * vec4(aPos, 0.0, 1.0); }
        """;

        const string FS = """
        #version 330 core
        in vec2 vUv; in vec4 vCol;
        out vec4 FragColor;
        uniform sampler2D uTex;
        uniform int uMode;   // 0=纯色 1=文本(alpha) 2=图片
        void main(){
            if (uMode == 0) { FragColor = vCol; }
            else if (uMode == 1) {
                float a = texture(uTex, vUv).a;
                if (a < 0.004) discard;
                FragColor = vec4(vCol.rgb, vCol.a * a);
            } else {
                vec4 t = texture(uTex, vUv);
                FragColor = t * vCol;
            }
        }
        """;
    }
}
