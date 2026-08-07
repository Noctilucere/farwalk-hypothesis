// TextAtlas.cs — 运行时中日韩字形图集 (GDI+ 栅格化 → OpenGL 纹理)
// 无需外置字体资源: 直接使用系统已安装的中文字体
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.Runtime.Versioning;
using OpenTK.Graphics.OpenGL4;

namespace Farwalk.UI
{
    public struct Glyph
    {
        public float U0, V0, U1, V1;   // 图集 UV
        public float W, H;             // 像素尺寸 (= 单元格)
        public float Advance;          // 步进宽度 (像素)
    }

    [SupportedOSPlatform("windows")]
    public class TextAtlas : IDisposable
    {
        public int Texture { get; private set; }
        public float PixelSize { get; private set; }
        public float LineHeight { get; private set; }
        public string FontName { get; private set; } = "";

        const int ATLAS = 2048;
        readonly int _cell;
        readonly int _cols;
        int _next;

        readonly Dictionary<char, Glyph> _map = new();
        readonly Font _font;
        readonly Bitmap _scratch;
        readonly Graphics _g;
        readonly StringFormat _fmt;

        static readonly string[] PREFERRED = {
            "Microsoft YaHei UI", "Microsoft YaHei", "Source Han Sans CN",
            "Noto Sans CJK SC", "SimHei", "DengXian", "SimSun", "Arial Unicode MS"
        };

        public TextAtlas(float pixelSize = 30f)
        {
            PixelSize = pixelSize;
            _cell = (int)MathF.Ceiling(pixelSize * 1.34f) + 2;
            _cols = ATLAS / _cell;

            _font = PickFont(pixelSize);
            FontName = _font.FontFamily.Name;
            LineHeight = _font.GetHeight() + 2f;

            _scratch = new Bitmap(_cell, _cell, System.Drawing.Imaging.PixelFormat.Format32bppArgb);
            _g = Graphics.FromImage(_scratch);
            _g.SmoothingMode = SmoothingMode.HighQuality;
            _g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            _g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
            _fmt = (StringFormat)StringFormat.GenericTypographic.Clone();
            _fmt.FormatFlags |= StringFormatFlags.MeasureTrailingSpaces;

            Texture = GL.GenTexture();
            GL.BindTexture(TextureTarget.Texture2D, Texture);
            GL.TexImage2D(TextureTarget.Texture2D, 0, PixelInternalFormat.Rgba8, ATLAS, ATLAS, 0,
                OpenTK.Graphics.OpenGL4.PixelFormat.Bgra, PixelType.UnsignedByte, IntPtr.Zero);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureMinFilter, (int)TextureMinFilter.Linear);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureMagFilter, (int)TextureMagFilter.Linear);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureWrapS, (int)TextureWrapMode.ClampToEdge);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureWrapT, (int)TextureWrapMode.ClampToEdge);
            GL.BindTexture(TextureTarget.Texture2D, 0);
        }

        static Font PickFont(float px)
        {
            foreach (var name in PREFERRED)
            {
                try
                {
                    var ff = new FontFamily(name);
                    if (ff.IsStyleAvailable(FontStyle.Regular))
                        return new Font(ff, px, FontStyle.Regular, GraphicsUnit.Pixel);
                }
                catch { /* 该字体不存在, 继续尝试 */ }
            }
            return new Font(FontFamily.GenericSansSerif, px, FontStyle.Regular, GraphicsUnit.Pixel);
        }

        public Glyph Ensure(char c)
        {
            if (_map.TryGetValue(c, out var g)) return g;
            if (_next >= _cols * (ATLAS / _cell))
            {
                // 图集用尽: 退化为空白字形
                g = new Glyph { Advance = PixelSize * 0.5f };
                _map[c] = g;
                return g;
            }

            int cx = (_next % _cols) * _cell;
            int cy = (_next / _cols) * _cell;
            _next++;

            _g.Clear(Color.Transparent);
            if (!char.IsWhiteSpace(c))
                _g.DrawString(c.ToString(), _font, Brushes.White, new PointF(1f, 1f), _fmt);

            float adv;
            if (c == ' ') adv = PixelSize * 0.32f;
            else
            {
                var sz = _g.MeasureString(c.ToString(), _font, PointF.Empty, _fmt);
                adv = sz.Width + 1.2f;
                if (adv < 1f) adv = PixelSize * 0.32f;
            }

            var data = _scratch.LockBits(new Rectangle(0, 0, _cell, _cell),
                ImageLockMode.ReadOnly, System.Drawing.Imaging.PixelFormat.Format32bppArgb);
            GL.BindTexture(TextureTarget.Texture2D, Texture);
            GL.PixelStore(PixelStoreParameter.UnpackAlignment, 4);
            GL.TexSubImage2D(TextureTarget.Texture2D, 0, cx, cy, _cell, _cell,
                OpenTK.Graphics.OpenGL4.PixelFormat.Bgra, PixelType.UnsignedByte, data.Scan0);
            _scratch.UnlockBits(data);
            GL.BindTexture(TextureTarget.Texture2D, 0);

            g = new Glyph
            {
                U0 = cx / (float)ATLAS,
                V0 = cy / (float)ATLAS,
                U1 = (cx + _cell) / (float)ATLAS,
                V1 = (cy + _cell) / (float)ATLAS,
                W = _cell,
                H = _cell,
                Advance = adv,
            };
            _map[c] = g;
            return g;
        }

        public float Measure(string s, float scale = 1f)
        {
            float w = 0;
            foreach (var c in s)
            {
                if (c == '\n') continue;
                w += Ensure(c).Advance * scale;
            }
            return w;
        }

        public void Dispose()
        {
            _g.Dispose();
            _scratch.Dispose();
            _font.Dispose();
            _fmt.Dispose();
            if (Texture != 0) GL.DeleteTexture(Texture);
        }
    }
}
