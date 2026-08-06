// Program.cs — SharpGLow 入口: 《远行假设》v2.0.0
using System;
using System.Collections.Generic;
using System.Numerics;
using Farwalk.Engine;
using Farwalk.Game;
using Farwalk.World;
using OpenTK.Mathematics;
using OpenTK.Windowing.Common;
using OpenTK.Windowing.Desktop;
using OpenTK.Windowing.GraphicsLibraryFramework;
using OpenTK.Graphics.OpenGL4;
using OpenTK.Windowing.Common;

namespace Farwalk
{
    public class GameApp : GameWindow
    {
        const string TITLE = "远行假设 · SharpGLow v2.0.0";

        Renderer _renderer = null!;
        WorldGen _gen = null!;
        Terrain _terrain = null!;
        OrbitCamera _cam = null!;
        Player _player = null!;
        StoryState _story = null!;

        int _terrainVao;
        int _playerVao, _playerVbo, _playerIbo, _playerIndexCount;
        bool _wireframe;
        float _time;
        float[] _model = Math3D.Mat4Identity();

        public GameApp() : base(
            GameWindowSettings.Default,
            new NativeWindowSettings
            {
                Size = new Vector2i(1920, 1080),
                Title = TITLE,
                APIVersion = new Version(3, 3),
                Profile = ContextProfile.Core,
            })
        { }

        protected override void OnLoad()
        {
            base.OnLoad();
            GL.ClearColor(0.3f, 0.4f, 0.55f, 1f);
            _renderer = new Renderer();
            _renderer.Init(ClientSize.X, ClientSize.Y);
            _gen = new WorldGen();
            _terrain = new Terrain(_gen);
            _terrain.Upload();
            _terrainVao = SetupTerrainVao();
            _player = new Player(new Vec3(0, 30, 60));
            _cam = new OrbitCamera();
            _cam.Snap(_player.Pos);
            _story = new StoryState();
            _story.Begin(0);
            BuildPlayerMesh();
            BuildScatter();
        }

        ScatterWorld _scatter = new();
        Shader _instShader = null!;

        void BuildScatter()
        {
            _instShader = new Shader(InstVS, InstFS);
            var sc = new ScatterGen(_gen);
            // 草 (两组)
            for (int v = 0; v < 2; v++)
            {
                var mesh = sc.GrassMesh(v);
                var (xs, ys, zs) = sc.Sample("wilds", 600);
                var rot = RandArr(xs.Length, 0f, Math3D.TAU);
                var scl = RandArr(xs.Length, 0.7f, 1.3f);
                var tint = RandArr(xs.Length, 0.5f, 0.9f);
                var data = InstPack.Pack(xs, ys, zs, rot, scl, scl, scl,
                    tint, Mult(tint, 0.85f), Mult(tint, 0.45f));
                _scatter.Add(mesh, data, "grass");
            }
            // 树
            {
                var mesh = sc.TreeMesh();
                var (xs, ys, zs) = sc.Sample("wilds", 40);
                var rot = RandArr(xs.Length, 0f, Math3D.TAU);
                var scl = RandArr(xs.Length, 0.8f, 1.6f);
                var data = InstPack.Pack(xs, ys, zs, rot, scl, scl, scl,
                    RandArr(xs.Length, 0.3f, 0.45f), RandArr(xs.Length, 0.38f, 0.5f), RandArr(xs.Length, 0.2f, 0.3f));
                _scatter.Add(mesh, data, "tree");
            }
            // 岩石
            {
                var mesh = sc.RockMesh();
                var (xs, ys, zs) = sc.Sample("wilds", 30);
                var rot = RandArr(xs.Length, 0f, Math3D.TAU);
                var scl = RandArr(xs.Length, 0.6f, 1.8f);
                var data = InstPack.Pack(xs, ys, zs, rot, scl, scl, scl,
                    RandArr(xs.Length, 0.45f, 0.5f), RandArr(xs.Length, 0.44f, 0.49f), RandArr(xs.Length, 0.42f, 0.47f));
                _scatter.Add(mesh, data, "rock");
            }
        }

        static float[] RandArr(int n, float lo, float hi)
        {
            var rnd = new Random(1);
            var o = new float[n];
            for (int i = 0; i < n; i++) o[i] = lo + (float)rnd.NextDouble() * (hi - lo);
            return o;
        }
        static float[] Mult(float[] a, float k)
        {
            var o = new float[a.Length];
            for (int i = 0; i < a.Length; i++) o[i] = a[i] * k;
            return o;
        }

        const string InstVS = """
        #version 330 core
        layout(location=0) in vec3 aPos;
        layout(location=1) in vec3 aNrm;
        layout(location=2) in vec4 iM0;
        layout(location=3) in vec4 iM1;
        layout(location=4) in vec4 iM2;
        layout(location=5) in vec4 iTint;
        out vec3 vNrm; out vec3 vWorld; out vec3 vTint;
        uniform mat4 uVP;
        void main(){
            mat4 M = mat4(vec4(iM0.xyz,0.0), vec4(iM1.xyz,0.0), vec4(iM2.xyz,0.0), vec4(iM0.w, iM1.w, iM2.w, 1.0));
            vec4 wp = M * vec4(aPos, 1.0);
            vWorld = wp.xyz;
            vNrm = mat3(M) * aNrm;
            vTint = iTint.rgb;
            gl_Position = uVP * wp;
        }
        """;

        const string InstFS = """
        #version 330 core
        in vec3 vNrm; in vec3 vWorld; in vec3 vTint;
        out vec4 FragColor;
        uniform vec3 uSunDir; uniform vec3 uSunColor;
        uniform vec3 uSky; uniform vec3 uGround;
        uniform vec3 uCamPos; uniform vec3 uFogColor; uniform float uFogDensity;
        void main(){
            vec3 N = normalize(vNrm);
            if (dot(N, normalize(uCamPos - vWorld)) < 0.0) N = -N;
            vec3 V = normalize(uCamPos - vWorld);
            float NoL = max(dot(N, normalize(uSunDir)), 0.0);
            float hemi = N.y * 0.5 + 0.5;
            vec3 col = vTint * (mix(uGround, uSky, hemi) * 0.6 + uSunColor * NoL * 0.9);
            float dist = length(vWorld - uCamPos);
            float fog = 1.0 - exp(-dist * uFogDensity * 2.0);
            col = mix(col, uFogColor, clamp(fog, 0.0, 0.92));
            FragColor = vec4(col, 1.0);
        }
        """;

        int SetupTerrainVao()
        {
            // terrain 顶点已在 Terrain.UploadGL 上传, 这里只需 VAO 配置
            int vao = GL.GenVertexArray();
            GL.BindVertexArray(vao);
            GL.BindBuffer(BufferTarget.ArrayBuffer, _terrain.Vbo);
            GL.EnableVertexAttribArray(0);
            GL.VertexAttribPointer(0, 3, VertexAttribPointerType.Float, false, 9 * 4, 0);
            GL.EnableVertexAttribArray(1);
            GL.VertexAttribPointer(1, 3, VertexAttribPointerType.Float, false, 9 * 4, 3 * 4);
            GL.EnableVertexAttribArray(2);
            GL.VertexAttribPointer(2, 3, VertexAttribPointerType.Float, false, 9 * 4, 6 * 4);
            GL.BindVertexArray(0);
            return vao;
        }

        void BuildPlayerMesh()
        {
            var m = MeshGen.Character(1.74f, 4242);
            _playerVbo = GL.GenBuffer();
            GL.BindBuffer(BufferTarget.ArrayBuffer, _playerVbo);
            GL.BufferData(BufferTarget.ArrayBuffer, m.Verts.Length * 4, m.Verts, BufferUsageHint.StaticDraw);
            _playerIbo = GL.GenBuffer();
            GL.BindBuffer(BufferTarget.ElementArrayBuffer, _playerIbo);
            GL.BufferData(BufferTarget.ElementArrayBuffer, m.Index.Length * 4, m.Index, BufferUsageHint.StaticDraw);
            _playerIndexCount = m.Index.Length;
            _playerVao = GL.GenVertexArray();
            GL.BindVertexArray(_playerVao);
            GL.BindBuffer(BufferTarget.ArrayBuffer, _playerVbo);
            GL.EnableVertexAttribArray(0);
            GL.VertexAttribPointer(0, 3, VertexAttribPointerType.Float, false, 6 * 4, 0);
            GL.EnableVertexAttribArray(1);
            GL.VertexAttribPointer(1, 3, VertexAttribPointerType.Float, false, 6 * 4, 3 * 4);
            GL.BindVertexArray(0);
        }

        protected override void OnUpdateFrame(FrameEventArgs e)
        {
            base.OnUpdateFrame(e);
            float dt = (float)e.Time;
            _time += dt;
            HandleInput(dt);
            float h = _gen.HeightAt(_player.Pos.X, _player.Pos.Z);
            _player.Update(dt, h);
            _cam.Update(dt, _player.Pos, 0, _gen.HeightAt);
            _story.Dlg.Update(dt, KeyboardState.IsKeyDown(Keys.LeftControl));
        }

        void HandleInput(float dt)
        {
            var k = KeyboardState;
            if (k.IsKeyDown(Keys.Escape)) Close();
            if (k.IsKeyPressed(Keys.F11)) WindowState = WindowState == WindowState.Fullscreen ? WindowState.Normal : WindowState.Fullscreen;
            if (k.IsKeyPressed(Keys.F1)) _wireframe = !_wireframe;
            if (k.IsKeyPressed(Keys.Enter) || k.IsKeyPressed(Keys.E))
            {
                if (_story.Dlg.Active) _story.Advance();
                else _story.Interact("inter", "manuscript"); // 简化: 按下交互
            }
            // 移动 (相对相机)
            var fwd = _cam.ForwardFlat();
            var right = new Vec3(-fwd.Z, 0, fwd.X);
            var wish = new Vec3(0, 0, 0);
            if (k.IsKeyDown(Keys.W)) wish += fwd;
            if (k.IsKeyDown(Keys.S)) wish -= fwd;
            if (k.IsKeyDown(Keys.D)) wish += right;
            if (k.IsKeyDown(Keys.A)) wish -= right;
            if (wish.Length() > 0) wish = wish.Normalized();
            bool sprint = k.IsKeyDown(Keys.LeftShift);
            bool jump = k.IsKeyPressed(Keys.Space);
            bool jumpHeld = k.IsKeyDown(Keys.Space);
            _player.ApplyMove(dt, wish, sprint, jump, jumpHeld);
            // 鼠标
            var m = MouseState;
            _cam.HandleMouse(m.Delta.X, m.Delta.Y);
            float scroll = m.ScrollDelta.Y;
            if (Math.Abs(scroll) > 0.01f) _cam.Update(dt, _player.Pos, 0, _gen.HeightAt, scroll * 0.3f);
        }

        protected override void OnRenderFrame(FrameEventArgs e)
        {
            base.OnRenderFrame(e);
            GL.Clear(ClearBufferMask.ColorBufferBit | ClearBufferMask.DepthBufferBit);
            GL.Enable(EnableCap.DepthTest);
            if (_wireframe) GL.PolygonMode(MaterialFace.FrontAndBack, PolygonMode.Line);
            else GL.PolygonMode(MaterialFace.FrontAndBack, PolygonMode.Fill);

            float aspect = ClientSize.X / (float)Math.Max(ClientSize.Y, 1);
            var vp = Math3D.Mul(_cam.ProjMatrix(aspect), _cam.ViewMatrix());

            // 地形
            _renderer.SetTerrainUniforms(_renderer.TerrainShader, vp, _model,
                new Vec3(0.38f, 0.55f, 0.74f), new Vec3(1.1f, 1.08f, 1.04f),
                new Vec3(0.34f, 0.4f, 0.5f), new Vec3(0.17f, 0.15f, 0.11f),
                _cam.Position, new Vec3(0.54f, 0.56f, 0.6f), 0.0046f);
            GL.BindVertexArray(_terrainVao);
            GL.BindBuffer(BufferTarget.ElementArrayBuffer, _terrain.Ibo);
            GL.DrawElements(PrimitiveType.Triangles, _terrain.IndexCount, DrawElementsType.UnsignedInt, 0);

            // 玩家
            RenderPlayer(vp);

            // 散置场景 (草/树/岩石)
            RenderScatter(vp);

            // HUD 文本 (简化: 控制台标题 + 章节提示)
            DrawHud();

            SwapBuffers();
        }

        void RenderScatter(float[] vp)
        {
            _instShader.Use();
            _instShader.SetMat4("uVP", vp);
            _instShader.SetV3("uSunDir", 0.38f, 0.55f, 0.74f);
            _instShader.SetV3("uSunColor", 1.1f, 1.08f, 1.04f);
            _instShader.SetV3("uSky", 0.34f, 0.4f, 0.5f);
            _instShader.SetV3("uGround", 0.17f, 0.15f, 0.11f);
            _instShader.SetV3("uCamPos", _cam.Position.X, _cam.Position.Y, _cam.Position.Z);
            _instShader.SetV3("uFogColor", 0.54f, 0.56f, 0.6f);
            _instShader.SetF("uFogDensity", 0.0046f);
            _scatter.DrawAll(_instShader);
        }

        void RenderPlayer(float[] vp)
        {
            var s = _renderer.ObjectShader;
            s.Use();
            s.SetMat4("uVP", vp);
            var m = Math3D.Mat4Identity();
            float cy = MathF.Cos(_player.Yaw), sy = MathF.Sin(_player.Yaw);
            m[0] = cy; m[2] = -sy; m[8] = sy; m[10] = cy;
            m[12] = _player.Pos.X; m[13] = _player.Pos.Y; m[14] = _player.Pos.Z;
            s.SetMat4("uModel", m);
            s.SetV3("uTint", 0.62f, 0.5f, 0.38f);
            _renderer.SetTerrainUniforms(_renderer.ObjectShader, vp, m,
                new Vec3(0.38f, 0.55f, 0.74f), new Vec3(1.1f, 1.08f, 1.04f),
                new Vec3(0.34f, 0.4f, 0.5f), new Vec3(0.17f, 0.15f, 0.11f),
                _cam.Position, new Vec3(0.54f, 0.56f, 0.6f), 0.0046f);
            GL.BindVertexArray(_playerVao);
            GL.BindBuffer(BufferTarget.ElementArrayBuffer, _playerIbo);
            GL.DrawElements(PrimitiveType.Triangles, _playerIndexCount, DrawElementsType.UnsignedInt, 0);
        }

        void DrawHud()
        {
            var obj = _story.CurrentObjective();
            string ch = _story.Finished ? "旅程完成" : $"{_story.Chapter + 1}. {StoryData.Chapters[Math.Min(_story.Chapter, StoryData.Chapters.Length - 1)]}";
            Title = $"{TITLE} | {ch}";
            Console.Title = $"{TITLE} | {ch} | 目标: {obj ?? "(对话中)"}";
        }
    }

    public static class Program
    {
        [STAThread]
        public static void Main()
        {
            using var g = new GameApp();
            g.Run();
        }
    }
}
