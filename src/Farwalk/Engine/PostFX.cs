// PostFX.cs — 后期处理链: HDR 场景 → 亮部提取 → 高斯泛光 → ACES 合成 → FXAA
// 移植自遗留 Python 构建的 postfx.py
using System;
using OpenTK.Graphics.OpenGL4;

namespace Farwalk.Engine
{
    public class PostFX
    {
        public bool Enabled = true;
        public float BloomThreshold = 1.02f;
        public float BloomStrength = 0.42f;
        public float Exposure = 1.06f;
        public float Vignette = 0.30f;
        public float Saturation = 1.06f;
        public int BlurIterations = 2;

        public int Width { get; private set; }
        public int Height { get; private set; }
        int _bw, _bh;   // 泛光半分辨率

        // 场景 (HDR)
        int _sceneFbo, _sceneTex, _sceneDepth;
        // 亮部 + 乒乓模糊
        int _brightFbo, _brightTex;
        int _blurFboA, _blurTexA, _blurFboB, _blurTexB;
        // LDR 中间结果 (给 FXAA)
        int _ldrFbo, _ldrTex;

        int _quadVao, _quadVbo;
        Shader _bright = null!, _blur = null!, _composite = null!, _fxaa = null!;
        bool _ready;

        public void Init(int w, int h)
        {
            _quadVao = GL.GenVertexArray();
            _quadVbo = GL.GenBuffer();
            float[] quad = {
                //  x,    y,   u,   v
                -1f, -1f, 0f, 0f,
                 1f, -1f, 1f, 0f,
                 1f,  1f, 1f, 1f,
                -1f, -1f, 0f, 0f,
                 1f,  1f, 1f, 1f,
                -1f,  1f, 0f, 1f,
            };
            GL.BindVertexArray(_quadVao);
            GL.BindBuffer(BufferTarget.ArrayBuffer, _quadVbo);
            GL.BufferData(BufferTarget.ArrayBuffer, quad.Length * 4, quad, BufferUsageHint.StaticDraw);
            GL.EnableVertexAttribArray(0);
            GL.VertexAttribPointer(0, 2, VertexAttribPointerType.Float, false, 4 * 4, 0);
            GL.EnableVertexAttribArray(1);
            GL.VertexAttribPointer(1, 2, VertexAttribPointerType.Float, false, 4 * 4, 2 * 4);
            GL.BindVertexArray(0);

            _bright = new Shader(QUAD_VS, BRIGHT_FS);
            _blur = new Shader(QUAD_VS, BLUR_FS);
            _composite = new Shader(QUAD_VS, COMPOSITE_FS);
            _fxaa = new Shader(QUAD_VS, FXAA_FS);

            Resize(w, h);
            _ready = true;
        }

        public void Resize(int w, int h)
        {
            Width = Math.Max(w, 8); Height = Math.Max(h, 8);
            _bw = Math.Max(Width / 2, 4); _bh = Math.Max(Height / 2, 4);
            DestroyTargets();

            (_sceneFbo, _sceneTex, _sceneDepth) = MakeColorDepth(Width, Height, PixelInternalFormat.Rgba16f);
            (_brightFbo, _brightTex) = MakeColor(_bw, _bh, PixelInternalFormat.Rgba16f);
            (_blurFboA, _blurTexA) = MakeColor(_bw, _bh, PixelInternalFormat.Rgba16f);
            (_blurFboB, _blurTexB) = MakeColor(_bw, _bh, PixelInternalFormat.Rgba16f);
            (_ldrFbo, _ldrTex) = MakeColor(Width, Height, PixelInternalFormat.Rgba8);
            GL.BindFramebuffer(FramebufferTarget.Framebuffer, 0);
        }

        static (int fbo, int tex) MakeColor(int w, int h, PixelInternalFormat fmt)
        {
            int tex = GL.GenTexture();
            GL.BindTexture(TextureTarget.Texture2D, tex);
            GL.TexImage2D(TextureTarget.Texture2D, 0, fmt, w, h, 0, PixelFormat.Rgba, PixelType.Float, IntPtr.Zero);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureMinFilter, (int)TextureMinFilter.Linear);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureMagFilter, (int)TextureMagFilter.Linear);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureWrapS, (int)TextureWrapMode.ClampToEdge);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureWrapT, (int)TextureWrapMode.ClampToEdge);
            int fbo = GL.GenFramebuffer();
            GL.BindFramebuffer(FramebufferTarget.Framebuffer, fbo);
            GL.FramebufferTexture2D(FramebufferTarget.Framebuffer, FramebufferAttachment.ColorAttachment0,
                TextureTarget.Texture2D, tex, 0);
            return (fbo, tex);
        }

        static (int fbo, int tex, int depth) MakeColorDepth(int w, int h, PixelInternalFormat fmt)
        {
            var (fbo, tex) = MakeColor(w, h, fmt);
            int rb = GL.GenRenderbuffer();
            GL.BindRenderbuffer(RenderbufferTarget.Renderbuffer, rb);
            GL.RenderbufferStorage(RenderbufferTarget.Renderbuffer, RenderbufferStorage.DepthComponent24, w, h);
            GL.FramebufferRenderbuffer(FramebufferTarget.Framebuffer, FramebufferAttachment.DepthAttachment,
                RenderbufferTarget.Renderbuffer, rb);
            var st = GL.CheckFramebufferStatus(FramebufferTarget.Framebuffer);
            if (st != FramebufferErrorCode.FramebufferComplete)
                Console.WriteLine($"[PostFX] 场景 FBO 不完整: {st}");
            return (fbo, tex, rb);
        }

        void DestroyTargets()
        {
            if (_sceneFbo != 0)
            {
                GL.DeleteFramebuffer(_sceneFbo); GL.DeleteTexture(_sceneTex); GL.DeleteRenderbuffer(_sceneDepth);
                GL.DeleteFramebuffer(_brightFbo); GL.DeleteTexture(_brightTex);
                GL.DeleteFramebuffer(_blurFboA); GL.DeleteTexture(_blurTexA);
                GL.DeleteFramebuffer(_blurFboB); GL.DeleteTexture(_blurTexB);
                GL.DeleteFramebuffer(_ldrFbo); GL.DeleteTexture(_ldrTex);
                _sceneFbo = 0;
            }
        }

        // 场景渲染开始: 绑定 HDR 目标
        public void BeginScene(float r, float g, float b)
        {
            if (!_ready || !Enabled)
            {
                GL.BindFramebuffer(FramebufferTarget.Framebuffer, 0);
                GL.Viewport(0, 0, Width, Height);
                GL.ClearColor(r, g, b, 1f);
                GL.Clear(ClearBufferMask.ColorBufferBit | ClearBufferMask.DepthBufferBit);
                return;
            }
            GL.BindFramebuffer(FramebufferTarget.Framebuffer, _sceneFbo);
            GL.Viewport(0, 0, Width, Height);
            GL.ClearColor(r, g, b, 1f);
            GL.Clear(ClearBufferMask.ColorBufferBit | ClearBufferMask.DepthBufferBit);
            GL.Enable(EnableCap.DepthTest);
        }

        // 场景渲染结束: 执行完整后处理链, 结果输出到默认帧缓冲
        public void Resolve()
        {
            if (!_ready || !Enabled) return;
            GL.Disable(EnableCap.DepthTest);
            GL.Disable(EnableCap.Blend);

            // 1) 亮部提取 (半分辨率)
            GL.BindFramebuffer(FramebufferTarget.Framebuffer, _brightFbo);
            GL.Viewport(0, 0, _bw, _bh);
            _bright.Use();
            BindTex(_bright, "uTex", _sceneTex, 0);
            _bright.SetF("uThreshold", BloomThreshold);
            DrawQuad();

            // 2) 分离高斯模糊 (水平/垂直交替)
            int src = _brightTex;
            for (int i = 0; i < BlurIterations; i++)
            {
                // 水平 → A
                GL.BindFramebuffer(FramebufferTarget.Framebuffer, _blurFboA);
                GL.Viewport(0, 0, _bw, _bh);
                _blur.Use();
                BindTex(_blur, "uTex", src, 0);
                _blur.SetV3("uDir", 1f / _bw, 0f, 0f);
                DrawQuad();
                // 垂直 → B
                GL.BindFramebuffer(FramebufferTarget.Framebuffer, _blurFboB);
                _blur.Use();
                BindTex(_blur, "uTex", _blurTexA, 0);
                _blur.SetV3("uDir", 0f, 1f / _bh, 0f);
                DrawQuad();
                src = _blurTexB;
            }

            // 3) 合成 (ACES 色调映射 + 泛光 + 暗角 + 饱和度) → LDR
            GL.BindFramebuffer(FramebufferTarget.Framebuffer, _ldrFbo);
            GL.Viewport(0, 0, Width, Height);
            _composite.Use();
            BindTex(_composite, "uScene", _sceneTex, 0);
            BindTex(_composite, "uBloom", src, 1);
            _composite.SetF("uExposure", Exposure);
            _composite.SetF("uBloomStrength", BloomStrength);
            _composite.SetF("uVignette", Vignette);
            _composite.SetF("uSaturation", Saturation);
            DrawQuad();

            // 4) FXAA → 默认帧缓冲
            GL.BindFramebuffer(FramebufferTarget.Framebuffer, 0);
            GL.Viewport(0, 0, Width, Height);
            _fxaa.Use();
            BindTex(_fxaa, "uTex", _ldrTex, 0);
            _fxaa.SetV3("uInvRes", 1f / Width, 1f / Height, 0f);
            DrawQuad();

            GL.BindTexture(TextureTarget.Texture2D, 0);
        }

        static void BindTex(Shader s, string name, int tex, int unit)
        {
            GL.ActiveTexture(TextureUnit.Texture0 + unit);
            GL.BindTexture(TextureTarget.Texture2D, tex);
            s.SetI(name, unit);
        }

        void DrawQuad()
        {
            GL.BindVertexArray(_quadVao);
            GL.DrawArrays(PrimitiveType.Triangles, 0, 6);
            GL.BindVertexArray(0);
        }

        public void Release()
        {
            DestroyTargets();
            GL.DeleteVertexArray(_quadVao);
            GL.DeleteBuffer(_quadVbo);
        }

        // ---------------- 着色器 ----------------
        const string QUAD_VS = """
        #version 330 core
        layout(location=0) in vec2 aPos;
        layout(location=1) in vec2 aUv;
        out vec2 vUv;
        void main(){ vUv = aUv; gl_Position = vec4(aPos, 0.0, 1.0); }
        """;

        const string BRIGHT_FS = """
        #version 330 core
        in vec2 vUv; out vec4 FragColor;
        uniform sampler2D uTex; uniform float uThreshold;
        void main(){
            vec3 c = texture(uTex, vUv).rgb;
            float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
            float k = max(l - uThreshold, 0.0) / max(l, 1e-4);
            FragColor = vec4(c * k, 1.0);
        }
        """;

        const string BLUR_FS = """
        #version 330 core
        in vec2 vUv; out vec4 FragColor;
        uniform sampler2D uTex; uniform vec3 uDir;
        // 9-tap 高斯
        const float W[5] = float[](0.227027, 0.194594, 0.121621, 0.054054, 0.016216);
        void main(){
            vec2 d = uDir.xy;
            vec3 c = texture(uTex, vUv).rgb * W[0];
            for (int i = 1; i < 5; i++){
                c += texture(uTex, vUv + d * float(i)).rgb * W[i];
                c += texture(uTex, vUv - d * float(i)).rgb * W[i];
            }
            FragColor = vec4(c, 1.0);
        }
        """;

        const string COMPOSITE_FS = """
        #version 330 core
        in vec2 vUv; out vec4 FragColor;
        uniform sampler2D uScene; uniform sampler2D uBloom;
        uniform float uExposure; uniform float uBloomStrength;
        uniform float uVignette; uniform float uSaturation;
        vec3 aces(vec3 x){
            const float a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14;
            return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
        }
        void main(){
            vec3 hdr = texture(uScene, vUv).rgb;
            vec3 bl  = texture(uBloom, vUv).rgb;
            hdr += bl * uBloomStrength;
            hdr *= uExposure;
            vec3 col = aces(hdr);
            // 饱和度
            float g = dot(col, vec3(0.2126, 0.7152, 0.0722));
            col = mix(vec3(g), col, uSaturation);
            // 暗角
            vec2 q = vUv - 0.5;
            float v = 1.0 - uVignette * dot(q, q) * 2.6;
            col *= clamp(v, 0.0, 1.0);
            // sRGB 近似
            col = pow(col, vec3(1.0 / 2.2));
            FragColor = vec4(col, 1.0);
        }
        """;

        const string FXAA_FS = """
        #version 330 core
        in vec2 vUv; out vec4 FragColor;
        uniform sampler2D uTex; uniform vec3 uInvRes;
        float lum(vec3 c){ return dot(c, vec3(0.299, 0.587, 0.114)); }
        void main(){
            vec2 inv = uInvRes.xy;
            vec3 rgbM  = texture(uTex, vUv).rgb;
            vec3 rgbNW = texture(uTex, vUv + vec2(-1.0, -1.0) * inv).rgb;
            vec3 rgbNE = texture(uTex, vUv + vec2( 1.0, -1.0) * inv).rgb;
            vec3 rgbSW = texture(uTex, vUv + vec2(-1.0,  1.0) * inv).rgb;
            vec3 rgbSE = texture(uTex, vUv + vec2( 1.0,  1.0) * inv).rgb;
            float lNW = lum(rgbNW), lNE = lum(rgbNE), lSW = lum(rgbSW), lSE = lum(rgbSE), lM = lum(rgbM);
            float lMin = min(lM, min(min(lNW, lNE), min(lSW, lSE)));
            float lMax = max(lM, max(max(lNW, lNE), max(lSW, lSE)));
            if (lMax - lMin < max(0.0312, lMax * 0.125)) { FragColor = vec4(rgbM, 1.0); return; }
            vec2 dir = vec2(-((lNW + lNE) - (lSW + lSE)), ((lNW + lSW) - (lNE + lSE)));
            float red = max((lNW + lNE + lSW + lSE) * 0.25 * 0.5, 1.0 / 128.0);
            float rcp = 1.0 / (min(abs(dir.x), abs(dir.y)) + red);
            dir = clamp(dir * rcp, vec2(-8.0), vec2(8.0)) * inv;
            vec3 a = 0.5 * (texture(uTex, vUv + dir * (1.0 / 3.0 - 0.5)).rgb
                          + texture(uTex, vUv + dir * (2.0 / 3.0 - 0.5)).rgb);
            vec3 b = a * 0.5 + 0.25 * (texture(uTex, vUv + dir * -0.5).rgb
                                     + texture(uTex, vUv + dir *  0.5).rgb);
            float lB = lum(b);
            FragColor = vec4((lB < lMin || lB > lMax) ? a : b, 1.0);
        }
        """;
    }
}
