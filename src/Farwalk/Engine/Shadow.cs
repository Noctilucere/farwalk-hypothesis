// Shadow.cs — 平行光阴影贴图 (2048^2 深度 FBO + 3x3 PCF)
// 移植自遗留 Python 构建的 shadow.py
using System;
using OpenTK.Graphics.OpenGL4;

namespace Farwalk.Engine
{
    public class ShadowMap
    {
        public int Size { get; private set; } = 2048;
        public int Fbo, DepthTex;
        public bool Enabled = true;

        // 光源视图投影矩阵 (列主序)
        public float[] LightVP = Math3D.Mat4Identity();

        // 三种深度着色器: 静态 / 实例化 / 蒙皮
        public Shader DepthStatic = null!;
        public Shader DepthInstanced = null!;
        public Shader DepthSkinned = null!;

        int _prevViewportW = 1, _prevViewportH = 1;

        public void Init(int size = 2048)
        {
            Size = size;
            DepthTex = GL.GenTexture();
            GL.BindTexture(TextureTarget.Texture2D, DepthTex);
            GL.TexImage2D(TextureTarget.Texture2D, 0, PixelInternalFormat.DepthComponent24,
                Size, Size, 0, PixelFormat.DepthComponent, PixelType.Float, IntPtr.Zero);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureMinFilter, (int)TextureMinFilter.Linear);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureMagFilter, (int)TextureMagFilter.Linear);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureWrapS, (int)TextureWrapMode.ClampToBorder);
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureWrapT, (int)TextureWrapMode.ClampToBorder);
            float[] border = { 1f, 1f, 1f, 1f };
            GL.TexParameter(TextureTarget.Texture2D, TextureParameterName.TextureBorderColor, border);

            Fbo = GL.GenFramebuffer();
            GL.BindFramebuffer(FramebufferTarget.Framebuffer, Fbo);
            GL.FramebufferTexture2D(FramebufferTarget.Framebuffer, FramebufferAttachment.DepthAttachment,
                TextureTarget.Texture2D, DepthTex, 0);
            GL.DrawBuffer(DrawBufferMode.None);
            GL.ReadBuffer(ReadBufferMode.None);
            var st = GL.CheckFramebufferStatus(FramebufferTarget.Framebuffer);
            if (st != FramebufferErrorCode.FramebufferComplete)
                Console.WriteLine($"[ShadowMap] FBO 不完整: {st}");
            GL.BindFramebuffer(FramebufferTarget.Framebuffer, 0);

            DepthStatic = new Shader(VS_STATIC, FS_EMPTY);
            DepthInstanced = new Shader(VS_INSTANCED, FS_EMPTY);
            DepthSkinned = new Shader(VS_SKINNED, FS_EMPTY);
        }

        // 依据太阳方向 (指向太阳) 与聚焦点构造正交光源矩阵
        public void UpdateLightMatrix(Vec3 sunDir, Vec3 focus, float radius, float depthRange = 420f)
        {
            var d = sunDir.Normalized();
            if (MathF.Abs(d.Y) < 1e-4f) d = new Vec3(d.X, 0.35f, d.Z).Normalized();

            // 纹素对齐: 抑制相机移动时的阴影抖动
            float texelWorld = (radius * 2f) / Size;
            var snapped = new Vec3(
                MathF.Floor(focus.X / texelWorld) * texelWorld,
                MathF.Floor(focus.Y / texelWorld) * texelWorld,
                MathF.Floor(focus.Z / texelWorld) * texelWorld);

            var eye = snapped + d * (depthRange * 0.5f);
            var up = MathF.Abs(d.Y) > 0.98f ? new Vec3(0, 0, 1) : new Vec3(0, 1, 0);
            var view = Math3D.LookAt(eye, snapped, up);
            var proj = Math3D.Ortho(-radius, radius, -radius, radius, 1f, depthRange * 1.25f);
            LightVP = Math3D.Mul(proj, view);
        }

        public void Begin(int viewportW, int viewportH)
        {
            _prevViewportW = viewportW; _prevViewportH = viewportH;
            GL.BindFramebuffer(FramebufferTarget.Framebuffer, Fbo);
            GL.Viewport(0, 0, Size, Size);
            GL.Clear(ClearBufferMask.DepthBufferBit);
            GL.Enable(EnableCap.DepthTest);
            GL.DepthFunc(DepthFunction.Less);
            // 斜率缩放深度偏移, 缓解自遮蔽条纹
            GL.Enable(EnableCap.PolygonOffsetFill);
            GL.PolygonOffset(2.4f, 4.0f);
        }

        public void End()
        {
            GL.Disable(EnableCap.PolygonOffsetFill);
            GL.PolygonOffset(0f, 0f);
            GL.BindFramebuffer(FramebufferTarget.Framebuffer, 0);
            GL.Viewport(0, 0, _prevViewportW, _prevViewportH);
        }

        // 把阴影贴图与相关 uniform 绑定到目标着色器
        public void BindTo(Shader s, int unit = 4)
        {
            s.Use();
            GL.ActiveTexture(TextureUnit.Texture0 + unit);
            GL.BindTexture(TextureTarget.Texture2D, DepthTex);
            s.SetI("uShadowMap", unit);
            s.SetMat4("uLightVP", LightVP);
            s.SetF("uShadowTexel", 1f / Size);
            s.SetI("uShadowOn", Enabled ? 1 : 0);
        }

        public void Release()
        {
            GL.DeleteFramebuffer(Fbo);
            GL.DeleteTexture(DepthTex);
        }

        // ---- 深度着色器 ----
        const string FS_EMPTY = """
        #version 330 core
        void main(){ }
        """;

        const string VS_STATIC = """
        #version 330 core
        layout(location=0) in vec3 aPos;
        uniform mat4 uLightVP; uniform mat4 uModel;
        void main(){ gl_Position = uLightVP * uModel * vec4(aPos, 1.0); }
        """;

        const string VS_INSTANCED = """
        #version 330 core
        layout(location=0) in vec3 aPos;
        layout(location=1) in vec3 aNrm;
        layout(location=2) in vec4 iM0;
        layout(location=3) in vec4 iM1;
        layout(location=4) in vec4 iM2;
        layout(location=5) in vec4 iTint;
        uniform mat4 uLightVP;
        void main(){
            mat4 M = mat4(vec4(iM0.xyz,0.0), vec4(iM1.xyz,0.0), vec4(iM2.xyz,0.0), vec4(iM0.w, iM1.w, iM2.w, 1.0));
            gl_Position = uLightVP * M * vec4(aPos, 1.0);
        }
        """;

        const string VS_SKINNED = """
        #version 330 core
        layout(location=0) in vec3 aPos;
        layout(location=1) in vec3 aNrm;
        layout(location=2) in vec2 aBoneIdx;
        layout(location=3) in vec2 aBoneWt;
        uniform mat4 uLightVP; uniform mat4 uModel;
        uniform mat4 uBones[8];
        void main(){
            int i0 = int(aBoneIdx.x + 0.5);
            int i1 = int(aBoneIdx.y + 0.5);
            mat4 sk = uBones[i0] * aBoneWt.x + uBones[i1] * aBoneWt.y;
            gl_Position = uLightVP * uModel * (sk * vec4(aPos, 1.0));
        }
        """;
    }
}
