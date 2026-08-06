// Renderer.cs — OpenGL 渲染器 (SharpGLow)
using System;
using OpenTK.Graphics.OpenGL4;

namespace Farwalk.Engine
{
    public class Shader
    {
        public int Handle;
        public Shader(string vs, string fs)
        {
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
        public void SetV3(string n, float x, float y, float z) => GL.Uniform3(U(n), x, y, z);
        public void SetMat4(string n, float[] m) => GL.UniformMatrix4(U(n), 1, false, m);
    }

    public class Renderer
    {
        public Shader TerrainShader;
        public Shader ObjectShader;
        public int Width, Height;

        public void Init(int w, int h)
        {
            Width = w; Height = h;
            TerrainShader = new Shader(TerrainVS, TerrainFS);
            ObjectShader = new Shader(ObjectVS, ObjectFS);
        }

        public void Resize(int w, int h) { Width = w; Height = h; GL.Viewport(0, 0, w, h); }

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

        const string TerrainFS = """
        #version 330 core
        in vec3 vNrm; in vec3 vAlb; in vec3 vWorld;
        out vec4 FragColor;
        uniform vec3 uSunDir; uniform vec3 uSunColor;
        uniform vec3 uSky; uniform vec3 uGround;
        uniform vec3 uCamPos; uniform vec3 uFogColor; uniform float uFogDensity;
        void main(){
            vec3 N = normalize(vNrm);
            vec3 V = normalize(uCamPos - vWorld);
            float NoL = max(dot(N, normalize(uSunDir)), 0.0);
            float hemi = N.y * 0.5 + 0.5;
            vec3 amb = mix(uGround, uSky, hemi);
            vec3 col = vAlb * (amb * 0.55 + uSunColor * NoL * 0.75);
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
        out vec3 vNrm; out vec3 vWorld; out vec3 vTint;
        uniform mat4 uVP; uniform mat4 uModel; uniform vec3 uTint;
        void main(){
            vec4 wp = uModel * vec4(aPos, 1.0);
            vWorld = wp.xyz;
            vNrm = mat3(uModel) * aNrm;
            vTint = uTint;
            gl_Position = uVP * wp;
        }
        """;

        const string ObjectFS = """
        #version 330 core
        in vec3 vNrm; in vec3 vWorld; in vec3 vTint;
        out vec4 FragColor;
        uniform vec3 uSunDir; uniform vec3 uSunColor;
        uniform vec3 uSky; uniform vec3 uGround;
        uniform vec3 uCamPos; uniform vec3 uFogColor; uniform float uFogDensity;
        void main(){
            vec3 N = normalize(vNrm);
            vec3 V = normalize(uCamPos - vWorld);
            float NoL = max(dot(N, normalize(uSunDir)), 0.0);
            float hemi = N.y * 0.5 + 0.5;
            vec3 amb = mix(uGround, uSky, hemi);
            vec3 col = vTint * (amb * 0.6 + uSunColor * NoL * 0.9);
            float dist = length(vWorld - uCamPos);
            float fog = 1.0 - exp(-dist * uFogDensity * 2.0);
            col = mix(col, uFogColor, clamp(fog, 0.0, 0.92));
            FragColor = vec4(col, 1.0);
        }
        """;

        public void SetTerrainUniforms(Shader s, float[] vp, float[] model, Vec3 sunDir,
            Vec3 sunColor, Vec3 sky, Vec3 ground, Vec3 camPos, Vec3 fogColor, float fogDens)
        {
            s.Use();
            s.SetMat4("uVP", vp); s.SetMat4("uModel", model);
            s.SetV3("uSunDir", sunDir.X, sunDir.Y, sunDir.Z);
            s.SetV3("uSunColor", sunColor.X, sunColor.Y, sunColor.Z);
            s.SetV3("uSky", sky.X, sky.Y, sky.Z);
            s.SetV3("uGround", ground.X, ground.Y, ground.Z);
            s.SetV3("uCamPos", camPos.X, camPos.Y, camPos.Z);
            s.SetV3("uFogColor", fogColor.X, fogColor.Y, fogColor.Z);
            s.SetF("uFogDensity", fogDens);
        }
    }
}
