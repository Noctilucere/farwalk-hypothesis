// Renderer.cs — OpenGL 渲染器 (SharpGLow)
// 着色器统一支持: 半球环境光 + 平行光 + 3x3 PCF 阴影 + 指数雾 + HDR 输出
using System;
using OpenTK.Graphics.OpenGL4;

namespace Farwalk.Engine
{
    public class Shader
    {
        public int Handle;

        // OpenTK 的 GL.ShaderSource(int, string) 便捷重载把「字符数」当作长度传给驱动,
        // 但字符串是按 UTF-8 字节编组的。着色器里只要出现一个非 ASCII 字符(例如中文注释),
        // 字节数就会大于字符数, 源码被从尾部截断 -> 驱动报 "pre-mature EOF : syntax error"。
        // GLSL 的非 ASCII 只可能出现在注释里, 因此逐字符替换成空格即可:
        // 既保持行列结构不变, 又让 字符数 == 字节数。
        static string AsciiSafe(string src)
        {
            var sb = new System.Text.StringBuilder(src.Length);
            foreach (char c in src) sb.Append(c < (char)128 ? c : ' ');
            return sb.ToString();
        }

        public Shader(string vs, string fs)
        {
            vs = AsciiSafe(vs); fs = AsciiSafe(fs);
            int vsId = GL.CreateShader(ShaderType.VertexShader);
            GL.ShaderSource(vsId, vs); GL.CompileShader(vsId);
            GL.GetShader(vsId, ShaderParameter.CompileStatus, out int okVs);
            if (okVs == 0) throw new Exception("VS: " + GL.GetShaderInfoLog(vsId));
            int fsId = GL.CreateShader(ShaderType.FragmentShader);
            GL.ShaderSource(fsId, fs); GL.CompileShader(fsId);
            GL.GetShader(fsId, ShaderParameter.CompileStatus, out int okFs);
            if (okFs == 0) throw new Exception("FS: " + GL.GetShaderInfoLog(fsId));
            Handle = GL.CreateProgram();
            GL.AttachShader(Handle, vsId); GL.AttachShader(Handle, fsId);
            GL.LinkProgram(Handle);
            GL.GetProgram(Handle, GetProgramParameterName.LinkStatus, out int okL);
            if (okL == 0) throw new Exception("LINK: " + GL.GetProgramInfoLog(Handle));
            GL.DeleteShader(vsId); GL.DeleteShader(fsId);
        }
        public void Use() => GL.UseProgram(Handle);
        public int U(string name) => GL.GetUniformLocation(Handle, name);
        public void SetI(string n, int v) => GL.Uniform1(U(n), v);
        public void SetF(string n, float v) => GL.Uniform1(U(n), v);
        public void SetV2(string n, float x, float y) => GL.Uniform2(U(n), x, y);
        public void SetV3(string n, float x, float y, float z) => GL.Uniform3(U(n), x, y, z);
        public void SetV4(string n, float x, float y, float z, float w) => GL.Uniform4(U(n), x, y, z, w);
        public void SetMat4(string n, float[] m) => GL.UniformMatrix4(U(n), 1, false, m);
        public void SetMat4Array(string n, float[] m, int count) => GL.UniformMatrix4(U(n), count, false, m);
    }

    // 场景光照参数集合
    public struct SceneLight
    {
        public Vec3 SunDir, SunColor, Sky, Ground, FogColor, CamPos;
        public float FogDensity;

        public static SceneLight Default(Vec3 camPos) => new SceneLight
        {
            SunDir = new Vec3(0.38f, 0.55f, 0.74f),
            SunColor = new Vec3(1.14f, 1.10f, 1.02f),
            Sky = new Vec3(0.34f, 0.40f, 0.50f),
            Ground = new Vec3(0.17f, 0.15f, 0.11f),
            FogColor = new Vec3(0.54f, 0.56f, 0.60f),
            CamPos = camPos,
            FogDensity = 0.0046f,
        };
    }

    public class Renderer
    {
        public Shader TerrainShader = null!;
        public Shader ObjectShader = null!;
        public Shader SkinnedShader = null!;
        public int Width, Height;

        public void Init(int w, int h)
        {
            Width = w; Height = h;
            TerrainShader = new Shader(TerrainVS, SHADOW_FN + TerrainFS);
            ObjectShader = new Shader(ObjectVS, SHADOW_FN + ObjectFS);
            SkinnedShader = new Shader(SkinnedVS, SHADOW_FN + ObjectFS);
        }

        public void Resize(int w, int h) { Width = w; Height = h; GL.Viewport(0, 0, w, h); }

        // ---------- 共享的阴影采样函数 (拼接到各 FS 头部) ----------
        public const string SHADOW_FN = """
        #version 330 core
        uniform sampler2D uShadowMap;
        uniform mat4 uLightVP;
        uniform float uShadowTexel;
        uniform int uShadowOn;
        float shadowFactor(vec3 world, float NoL){
            if (uShadowOn == 0) return 1.0;
            vec4 lp = uLightVP * vec4(world, 1.0);
            vec3 pc = lp.xyz / lp.w;
            pc = pc * 0.5 + 0.5;
            if (pc.z > 1.0 || pc.x < 0.002 || pc.x > 0.998 || pc.y < 0.002 || pc.y > 0.998)
                return 1.0;
            float bias = max(0.0026 * (1.0 - NoL), 0.00055);
            float sum = 0.0;
            for (int y = -1; y <= 1; y++){
                for (int x = -1; x <= 1; x++){
                    float d = texture(uShadowMap, pc.xy + vec2(float(x), float(y)) * uShadowTexel).r;
                    sum += (pc.z - bias > d) ? 0.0 : 1.0;
                }
            }
            // 贴图边缘平滑过渡回全亮
            float edge = min(min(pc.x, 1.0 - pc.x), min(pc.y, 1.0 - pc.y));
            float fade = smoothstep(0.0, 0.06, edge);
            return mix(1.0, sum / 9.0, fade);
        }
        """;

        const string TerrainVS = """
        #version 330 core
        layout(location=0) in vec3 aPos;
        layout(location=1) in vec3 aNrm;
        layout(location=2) in vec3 aAlb;
        out vec3 vNrm; out vec3 vAlb; out vec3 vWorld;
        uniform mat4 uVP; uniform mat4 uModel;
        void main(){
            vec4 wp = uModel * vec4(aPos, 1.0);
            vWorld = wp.xyz;
            vNrm = mat3(uModel) * aNrm;
            vAlb = aAlb;
            gl_Position = uVP * wp;
        }
        """;

        // 注意: 版本声明由 SHADOW_FN 提供
        const string TerrainFS = """

        in vec3 vNrm; in vec3 vAlb; in vec3 vWorld;
        out vec4 FragColor;
        uniform vec3 uSunDir; uniform vec3 uSunColor;
        uniform vec3 uSky; uniform vec3 uGround;
        uniform vec3 uCamPos; uniform vec3 uFogColor; uniform float uFogDensity;
        uniform float uWaterLevel;
        void main(){
            vec3 N = normalize(vNrm);
            vec3 L = normalize(uSunDir);
            float NoL = max(dot(N, L), 0.0);
            float hemi = N.y * 0.5 + 0.5;
            vec3 amb = mix(uGround, uSky, hemi);
            float sh = shadowFactor(vWorld, NoL);
            vec3 col = vAlb * (amb * 0.55 + uSunColor * NoL * 0.78 * sh);
            // 水面以下的冷色浸染
            float sub = clamp((uWaterLevel - vWorld.y) * 0.22, 0.0, 0.72);
            col = mix(col, vec3(0.10, 0.20, 0.27), sub);
            float dist = length(vWorld - uCamPos);
            float fog = 1.0 - exp(-dist * uFogDensity * 2.0);
            col = mix(col, uFogColor, clamp(fog, 0.0, 0.92));
            FragColor = vec4(col, 1.0);
        }
        """;

        const string ObjectVS = """
        #version 330 core
        layout(location=0) in vec3 aPos;
        layout(location=1) in vec3 aNrm;
        out vec3 vNrm; out vec3 vWorld;
        uniform mat4 uVP; uniform mat4 uModel;
        void main(){
            vec4 wp = uModel * vec4(aPos, 1.0);
            vWorld = wp.xyz;
            vNrm = mat3(uModel) * aNrm;
            gl_Position = uVP * wp;
        }
        """;

        const string SkinnedVS = """
        #version 330 core
        layout(location=0) in vec3 aPos;
        layout(location=1) in vec3 aNrm;
        layout(location=2) in vec2 aBoneIdx;
        layout(location=3) in vec2 aBoneWt;
        out vec3 vNrm; out vec3 vWorld;
        uniform mat4 uVP; uniform mat4 uModel;
        uniform mat4 uBones[8];
        void main(){
            int i0 = int(aBoneIdx.x + 0.5);
            int i1 = int(aBoneIdx.y + 0.5);
            mat4 sk = uBones[i0] * aBoneWt.x + uBones[i1] * aBoneWt.y;
            vec4 lp = sk * vec4(aPos, 1.0);
            vec4 wp = uModel * lp;
            vWorld = wp.xyz;
            vNrm = mat3(uModel) * (mat3(sk) * aNrm);
            gl_Position = uVP * wp;
        }
        """;

        // 物体 / 蒙皮共用片元着色器 (uTint 统一着色 + 边缘光)
        const string ObjectFS = """

        in vec3 vNrm; in vec3 vWorld;
        out vec4 FragColor;
        uniform vec3 uTint;
        uniform vec3 uSunDir; uniform vec3 uSunColor;
        uniform vec3 uSky; uniform vec3 uGround;
        uniform vec3 uCamPos; uniform vec3 uFogColor; uniform float uFogDensity;
        uniform vec3 uEmissive;
        uniform float uRim;
        void main(){
            vec3 N = normalize(vNrm);
            vec3 V = normalize(uCamPos - vWorld);
            if (dot(N, V) < 0.0) N = -N;
            vec3 L = normalize(uSunDir);
            float NoL = max(dot(N, L), 0.0);
            float hemi = N.y * 0.5 + 0.5;
            vec3 amb = mix(uGround, uSky, hemi);
            float sh = shadowFactor(vWorld, NoL);
            vec3 col = uTint * (amb * 0.62 + uSunColor * NoL * 0.92 * sh);
            // 高光
            vec3 H = normalize(L + V);
            col += uSunColor * pow(max(dot(N, H), 0.0), 34.0) * 0.16 * sh;
            // 边缘光
            float rim = pow(1.0 - max(dot(N, V), 0.0), 2.6);
            col += uSky * rim * uRim;
            col += uEmissive;
            float dist = length(vWorld - uCamPos);
            float fog = 1.0 - exp(-dist * uFogDensity * 2.0);
            col = mix(col, uFogColor, clamp(fog, 0.0, 0.92));
            FragColor = vec4(col, 1.0);
        }
        """;

        // 统一设置光照 / 雾 / 相机 uniform
        public void SetSceneUniforms(Shader s, float[] vp, float[] model, in SceneLight lt)
        {
            s.Use();
            s.SetMat4("uVP", vp);
            s.SetMat4("uModel", model);
            s.SetV3("uSunDir", lt.SunDir.X, lt.SunDir.Y, lt.SunDir.Z);
            s.SetV3("uSunColor", lt.SunColor.X, lt.SunColor.Y, lt.SunColor.Z);
            s.SetV3("uSky", lt.Sky.X, lt.Sky.Y, lt.Sky.Z);
            s.SetV3("uGround", lt.Ground.X, lt.Ground.Y, lt.Ground.Z);
            s.SetV3("uCamPos", lt.CamPos.X, lt.CamPos.Y, lt.CamPos.Z);
            s.SetV3("uFogColor", lt.FogColor.X, lt.FogColor.Y, lt.FogColor.Z);
            s.SetF("uFogDensity", lt.FogDensity);
        }

        // 兼容旧调用签名
        public void SetTerrainUniforms(Shader s, float[] vp, float[] model, Vec3 sunDir,
            Vec3 sunColor, Vec3 sky, Vec3 ground, Vec3 camPos, Vec3 fogColor, float fogDens)
        {
            var lt = new SceneLight
            {
                SunDir = sunDir, SunColor = sunColor, Sky = sky, Ground = ground,
                CamPos = camPos, FogColor = fogColor, FogDensity = fogDens
            };
            SetSceneUniforms(s, vp, model, lt);
        }
    }
}
