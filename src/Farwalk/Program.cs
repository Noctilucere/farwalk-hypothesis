// Program.cs — SharpGLow 入口: 《远行假设》v2.2.0
// 集成: 阴影贴图 / HDR 后期处理 / GPU 蒙皮角色 / 传送门 / 地图·日志·成就 UI / 成就系统
using System;
using System.Collections.Generic;
using Farwalk.Engine;
using Farwalk.Game;
using Farwalk.UI;
using Farwalk.World;
using OpenTK.Mathematics;
using OpenTK.Windowing.Common;
using OpenTK.Windowing.Desktop;
using OpenTK.Windowing.GraphicsLibraryFramework;
using OpenTK.Graphics.OpenGL4;

namespace Farwalk
{
    public class GameApp : GameWindow
    {
        const string TITLE = "远行假设 · SharpGLow v2.2.0";

        // 核心
        Renderer _renderer = null!;
        WorldGen _gen = null!;
        Terrain _terrain = null!;
        OrbitCamera _cam = null!;
        Player _player = null!;
        StoryState _story = null!;
        Vec3 _spawn;

        // 渲染特性
        ShadowMap _shadow = null!;
        PostFX _post = null!;
        Overlay _overlay = null!;
        GameUi _ui = null!;

        // 世界系统
        PortalSystem _portals = null!;
        LandmarkSystem _landmarks = null!;
        AchievementSystem _ach = null!;
        Skeleton _sk = null!;
        AnimController _anim = null!;

        // 资源
        int _terrainVao;
        int _skinVao, _skinVbo, _skinIbo, _skinIndexCount;
        int _portalVao, _portalVbo, _portalIbo, _portalIndexCount;
        int _beaconVao, _beaconVbo, _beaconIbo, _beaconIndexCount;
        int _mapTex;

        ScatterWorld _scatter = new();
        Shader _instShader = null!;

        bool _wireframe;
        float _time;
        UiPanel _panel = UiPanel.None;
        float _fps, _fpsAccum;
        int _fpsFrames;
        int _readPages;   // 已计数的对话行

        public GameApp() : base(
            GameWindowSettings.Default,
            new NativeWindowSettings
            {
                ClientSize = new Vector2i(1920, 1080),
                Title = TITLE,
                APIVersion = new Version(3, 3),
                Profile = ContextProfile.Core,
            })
        { }

        protected override void OnLoad()
        {
            base.OnLoad();
            GL.ClearColor(0.34f, 0.40f, 0.50f, 1f);

            _renderer = new Renderer();
            _renderer.Init(ClientSize.X, ClientSize.Y);
            _gen = new WorldGen();
            _terrain = new Terrain(_gen);
            _terrain.Upload();
            _terrainVao = SetupTerrainVao();

            _player = new Player(new Vec3(0, 30, 60));
            _spawn = new Vec3(0, 30, 60);
            _cam = new OrbitCamera();
            _cam.Snap(_player.Pos);
            _story = new StoryState();
            _story.Begin(0);

            // 渲染特性
            _shadow = new ShadowMap();
            _shadow.Init(2048);
            _post = new PostFX();
            _post.Init(ClientSize.X, ClientSize.Y);
            _overlay = new Overlay();
            _overlay.Init(ClientSize.X, ClientSize.Y);
            _ui = new GameUi();

            // 世界系统
            _portals = new PortalSystem();
            _portals.Build(_gen.HeightAt);
            _landmarks = new LandmarkSystem();
            _landmarks.Build(_gen.HeightAt);
            _ach = new AchievementSystem();

            // 蒙皮角色
            _sk = new Skeleton(1.74f);
            _anim = new AnimController();
            BuildSkinnedMesh();

            // 可视化网格 (传送门光环 / 地标信标)
            BuildPortalMesh();
            BuildBeaconMesh();

            // 世界缩略图
            _mapTex = Minimap.Build(_terrain);

            BuildScatter();
        }

        protected override void OnResize(ResizeEventArgs e)
        {
            base.OnResize(e);
            _renderer?.Resize(e.Width, e.Height);
            _post?.Resize(e.Width, e.Height);
            _overlay?.Resize(e.Width, e.Height);
            GL.Viewport(0, 0, e.Width, e.Height);
        }

        // ---------------- 资源构建 ----------------

        int SetupTerrainVao()
        {
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

        void BuildSkinnedMesh()
        {
            var m = SkinnedMeshGen.Character(1.74f);
            _skinVbo = GL.GenBuffer();
            GL.BindBuffer(BufferTarget.ArrayBuffer, _skinVbo);
            GL.BufferData(BufferTarget.ArrayBuffer, m.Verts.Length * 4, m.Verts, BufferUsageHint.StaticDraw);
            _skinIbo = GL.GenBuffer();
            GL.BindBuffer(BufferTarget.ElementArrayBuffer, _skinIbo);
            GL.BufferData(BufferTarget.ElementArrayBuffer, m.Index.Length * 4, m.Index, BufferUsageHint.StaticDraw);
            _skinIndexCount = m.Index.Length;
            _skinVao = GL.GenVertexArray();
            GL.BindVertexArray(_skinVao);
            GL.BindBuffer(BufferTarget.ArrayBuffer, _skinVbo);
            int stride = SkinnedMeshData.STRIDE * 4;
            GL.EnableVertexAttribArray(0);
            GL.VertexAttribPointer(0, 3, VertexAttribPointerType.Float, false, stride, 0);
            GL.EnableVertexAttribArray(1);
            GL.VertexAttribPointer(1, 3, VertexAttribPointerType.Float, false, stride, 3 * 4);
            GL.EnableVertexAttribArray(2);
            GL.VertexAttribPointer(2, 2, VertexAttribPointerType.Float, false, stride, 6 * 4);
            GL.EnableVertexAttribArray(3);
            GL.VertexAttribPointer(3, 2, VertexAttribPointerType.Float, false, stride, 8 * 4);
            GL.BindVertexArray(0);
        }

        void BuildPortalMesh()
        {
            // 平躺圆环绕 X 轴立起 -> 竖直传送光环
            var torus = MeshGen.Transform(MeshGen.Torus(2.2f, 0.26f, 36, 12), 0, 0, 0, MathF.PI / 2, 0, 0);
            UploadMesh(torus.Verts, torus.Index, out _portalVao, out _portalVbo, out _portalIbo, out _portalIndexCount);
        }

        void BuildBeaconMesh()
        {
            var beacon = MeshGen.Capsule(0.22f, 1.4f, 8, 8);
            UploadMesh(beacon.Verts, beacon.Index, out _beaconVao, out _beaconVbo, out _beaconIbo, out _beaconIndexCount);
        }

        static void UploadMesh(float[] verts, uint[] idx, out int vao, out int vbo, out int ibo, out int count)
        {
            vbo = GL.GenBuffer();
            GL.BindBuffer(BufferTarget.ArrayBuffer, vbo);
            GL.BufferData(BufferTarget.ArrayBuffer, verts.Length * 4, verts, BufferUsageHint.StaticDraw);
            ibo = GL.GenBuffer();
            GL.BindBuffer(BufferTarget.ElementArrayBuffer, ibo);
            GL.BufferData(BufferTarget.ElementArrayBuffer, idx.Length * 4, idx, BufferUsageHint.StaticDraw);
            count = idx.Length;
            vao = GL.GenVertexArray();
            GL.BindVertexArray(vao);
            GL.BindBuffer(BufferTarget.ArrayBuffer, vbo);
            GL.EnableVertexAttribArray(0);
            GL.VertexAttribPointer(0, 3, VertexAttribPointerType.Float, false, 6 * 4, 0);
            GL.EnableVertexAttribArray(1);
            GL.VertexAttribPointer(1, 3, VertexAttribPointerType.Float, false, 6 * 4, 3 * 4);
            GL.BindVertexArray(0);
        }

        // ---------------- 散置场景 ----------------

        void BuildScatter()
        {
            _instShader = new Shader(InstVS, InstFS);
            var sc = new ScatterGen(_gen);
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
            {
                var mesh = sc.TreeMesh();
                var (xs, ys, zs) = sc.Sample("wilds", 40);
                var rot = RandArr(xs.Length, 0f, Math3D.TAU);
                var scl = RandArr(xs.Length, 0.8f, 1.6f);
                var data = InstPack.Pack(xs, ys, zs, rot, scl, scl, scl,
                    RandArr(xs.Length, 0.3f, 0.45f), RandArr(xs.Length, 0.38f, 0.5f), RandArr(xs.Length, 0.2f, 0.3f));
                _scatter.Add(mesh, data, "tree");
            }
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

        // ---------------- 更新 ----------------

        protected override void OnUpdateFrame(FrameEventArgs e)
        {
            base.OnUpdateFrame(e);
            float dt = (float)e.Time;
            if (dt > 0.1f) dt = 0.1f;   // 防止卡顿后大跳变
            _time += dt;

            HandleInput(dt);

            float h = _gen.HeightAt(_player.Pos.X, _player.Pos.Z);
            _player.Update(dt, h);

            _cam.HandleMouse(MouseState.Delta.X, MouseState.Delta.Y);
            _cam.Update(dt, _player.Pos, 0, _gen.HeightAt, MouseState.ScrollDelta.Y * 0.3f);

            _story.Dlg.Update(dt, KeyboardState.IsKeyDown(Keys.LeftControl));

            _portals.Update(dt);
            _landmarks.Update(dt);

            // 区域发现 -> 推进章节
            var found = _portals.UpdateVisit(_player.Pos);
            if (found != null) _story.Notify("reach", found);

            // 过程式动画
            bool grounded = _player.Pos.Y <= h + 0.05f;
            float speed01 = _player.Sprinting ? 1f : (_player.Moving ? 0.5f : 0f);
            _anim.Update(dt, _player.Moving, _player.Sprinting, grounded, _player.Gliding, speed01);
            _anim.Apply(_sk, _time);

            // 成就统计
            if (_player.Moving) _ach.DistanceWalked += (_player.Sprinting ? _player.RunSpeed : _player.Speed) * dt;
            if (_story.Dlg.Active && !_story.Dlg.Typing)
            {
                int shown = _story.Dlg.Page + 1;
                if (shown > _readPages) { _ach.DialogueLines += (shown - _readPages); _readPages = shown; }
            }
            else if (!_story.Dlg.Active) _readPages = 0;

            bool underwater = _player.Pos.Y < TerrainConfig.WATER_LEVEL;
            _ach.Evaluate(dt, _player, _spawn, _story, _portals, _player.Gliding, underwater);
            _ach.UpdateToasts(dt);

            // FPS
            _fpsAccum += dt; _fpsFrames++;
            if (_fpsAccum >= 0.5f) { _fps = _fpsFrames / _fpsAccum; _fpsAccum = 0; _fpsFrames = 0; }
        }

        void HandleInput(float dt)
        {
            var k = KeyboardState;

            // Esc: 关闭面板/菜单 或 退出
            if (k.IsKeyPressed(Keys.Escape))
            {
                if (_panel != UiPanel.None) { _panel = UiPanel.None; return; }
                if (_portals.MenuOpen) { _portals.CloseMenu(); return; }
                Close(); return;
            }
            // 面板快捷键
            if (k.IsKeyPressed(Keys.M)) { _panel = (_panel == UiPanel.Map) ? UiPanel.None : UiPanel.Map; _portals.CloseMenu(); return; }
            if (k.IsKeyPressed(Keys.J)) { _panel = (_panel == UiPanel.Journal) ? UiPanel.None : UiPanel.Journal; _portals.CloseMenu(); return; }
            if (k.IsKeyPressed(Keys.C)) { _panel = (_panel == UiPanel.Achievements) ? UiPanel.None : UiPanel.Achievements; _portals.CloseMenu(); return; }
            // 调试开关
            if (k.IsKeyPressed(Keys.F2)) { _shadow.Enabled = !_shadow.Enabled; return; }
            if (k.IsKeyPressed(Keys.F3)) { _post.Enabled = !_post.Enabled; return; }
            if (k.IsKeyPressed(Keys.F11)) { WindowState = WindowState == WindowState.Fullscreen ? WindowState.Normal : WindowState.Fullscreen; return; }
            if (k.IsKeyPressed(Keys.F1)) { _wireframe = !_wireframe; return; }

            // 传送门菜单导航
            if (_portals.MenuOpen)
            {
                if (k.IsKeyPressed(Keys.Up)) _portals.MoveMenu(-1);
                if (k.IsKeyPressed(Keys.Down)) _portals.MoveMenu(1);
                if (k.IsKeyPressed(Keys.Enter)) TeleportSelected();
                if (k.IsKeyPressed(Keys.F)) _portals.CloseMenu();
                return;
            }

            // 对话推进
            if (_story.Dlg.Active)
            {
                if (k.IsKeyPressed(Keys.Enter) || k.IsKeyPressed(Keys.E)) _story.Advance();
                return;
            }

            // F: 邻近传送门 -> 打开菜单
            if (k.IsKeyPressed(Keys.F))
            {
                var np = _portals.Nearest(_player.Pos, out float pdist);
                if (np != null && pdist <= PortalSystem.InteractRange) _portals.OpenMenu();
                return;
            }
            // E: 邻近地标交互
            if (k.IsKeyPressed(Keys.E))
            {
                var lm = _landmarks.Nearest(_player.Pos, out float ldist);
                if (lm != null && ldist <= LandmarkSystem.Range)
                {
                    string kind = lm.Kind switch { MarkKind.Touch => "inter", MarkKind.Talk => "npc", _ => "coll" };
                    _story.Interact(kind, lm.Id);
                    lm.Used = true;
                }
                return;
            }

            // 面板打开时锁住移动
            if (_panel != UiPanel.None) return;

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
            if (_player.Moving) _player.Yaw = MathF.Atan2(wish.X, -wish.Z);
        }

        void TeleportSelected()
        {
            var p = _portals.Selected();
            if (p == null) { _portals.CloseMenu(); return; }
            _player.Pos = new Vec3(p.Pos.X, p.Pos.Y + 0.1f, p.Pos.Z);
            _player.Vel = new Vec3(0, 0, 0);
            _portals.UseCount++;
            _portals.CloseMenu();
            _story.Notify("reach", p.Region);
        }

        // ---------------- 渲染 ----------------

        protected override void OnRenderFrame(FrameEventArgs e)
        {
            base.OnRenderFrame(e);
            float aspect = ClientSize.X / (float)Math.Max(ClientSize.Y, 1);
            var vp = Math3D.Mul(_cam.ProjMatrix(aspect), _cam.ViewMatrix());
            var light = SceneLight.Default(_cam.Position);
            var pmodel = PlayerModel();

            if (_wireframe) GL.PolygonMode(MaterialFace.FrontAndBack, PolygonMode.Line);
            else GL.PolygonMode(MaterialFace.FrontAndBack, PolygonMode.Fill);

            // ---- 阴影 pass (深度) ----
            _shadow.UpdateLightMatrix(light.SunDir, _player.Pos, 140f);
            _shadow.Begin(ClientSize.X, ClientSize.Y);

            _shadow.DepthStatic.Use();
            _shadow.DepthStatic.SetMat4("uLightVP", _shadow.LightVP);
            _shadow.DepthStatic.SetMat4("uModel", Math3D.Mat4Identity());
            GL.BindVertexArray(_terrainVao);
            GL.BindBuffer(BufferTarget.ElementArrayBuffer, _terrain.Ibo);
            GL.DrawElements(PrimitiveType.Triangles, _terrain.IndexCount, DrawElementsType.UnsignedInt, 0);

            _shadow.DepthInstanced.Use();
            _shadow.DepthInstanced.SetMat4("uLightVP", _shadow.LightVP);
            _scatter.DrawAll(_shadow.DepthInstanced);

            _shadow.DepthSkinned.Use();
            _shadow.DepthSkinned.SetMat4("uLightVP", _shadow.LightVP);
            _shadow.DepthSkinned.SetMat4("uModel", pmodel);
            _shadow.DepthSkinned.SetMat4Array("uBones", _sk.SkinMatrices, Bone.Count);
            GL.BindVertexArray(_skinVao);
            GL.BindBuffer(BufferTarget.ElementArrayBuffer, _skinIbo);
            GL.DrawElements(PrimitiveType.Triangles, _skinIndexCount, DrawElementsType.UnsignedInt, 0);

            _shadow.End();

            // ---- 场景 pass (HDR) ----
            _post.BeginScene(0.34f, 0.40f, 0.50f);
            GL.Enable(EnableCap.DepthTest);

            // 地形
            _renderer.SetSceneUniforms(_renderer.TerrainShader, vp, Math3D.Mat4Identity(), light);
            _shadow.BindTo(_renderer.TerrainShader);
            _renderer.TerrainShader.SetF("uWaterLevel", TerrainConfig.WATER_LEVEL);
            GL.BindVertexArray(_terrainVao);
            GL.BindBuffer(BufferTarget.ElementArrayBuffer, _terrain.Ibo);
            GL.DrawElements(PrimitiveType.Triangles, _terrain.IndexCount, DrawElementsType.UnsignedInt, 0);

            // 散置 / 传送门 / 地标 / 玩家
            RenderScatter(vp, light);
            RenderPortals(vp, light);
            RenderLandmarks(vp, light);
            RenderPlayer(vp, light, pmodel);

            _post.Resolve();

            // ---- UI ----
            DrawGameUi();

            SwapBuffers();
        }

        void RenderScatter(float[] vp, SceneLight light)
        {
            _instShader.Use();
            _instShader.SetMat4("uVP", vp);
            _instShader.SetV3("uSunDir", light.SunDir.X, light.SunDir.Y, light.SunDir.Z);
            _instShader.SetV3("uSunColor", light.SunColor.X, light.SunColor.Y, light.SunColor.Z);
            _instShader.SetV3("uSky", light.Sky.X, light.Sky.Y, light.Sky.Z);
            _instShader.SetV3("uGround", light.Ground.X, light.Ground.Y, light.Ground.Z);
            _instShader.SetV3("uCamPos", light.CamPos.X, light.CamPos.Y, light.CamPos.Z);
            _instShader.SetV3("uFogColor", light.FogColor.X, light.FogColor.Y, light.FogColor.Z);
            _instShader.SetF("uFogDensity", light.FogDensity);
            _scatter.DrawAll(_instShader);
        }

        void RenderPortals(float[] vp, SceneLight light)
        {
            var s = _renderer.ObjectShader;
            foreach (var p in _portals.Portals)
            {
                if (!p.Discovered) continue;
                float pulse = 1f + MathF.Sin(p.Pulse * 1.2f) * 0.06f;
                var m = Math3D.Compose(p.Pos.X, p.Pos.Y + 1.4f, p.Pos.Z, 0, _time * 0.6f, 0, pulse, pulse, pulse);
                _renderer.SetSceneUniforms(s, vp, m, light);
                _shadow.BindTo(s);
                s.SetV3("uTint", 0.42f, 0.74f, 0.72f);
                s.SetF("uRim", 1.0f);
                s.SetV3("uEmissive", 0.05f, 0.18f, 0.18f);
                GL.BindVertexArray(_portalVao);
                GL.BindBuffer(BufferTarget.ElementArrayBuffer, _portalIbo);
                GL.DrawElements(PrimitiveType.Triangles, _portalIndexCount, DrawElementsType.UnsignedInt, 0);
            }
        }

        void RenderLandmarks(float[] vp, SceneLight light)
        {
            var s = _renderer.ObjectShader;
            foreach (var lm in _landmarks.Marks)
            {
                float bob = MathF.Sin(lm.Bob) * 0.18f;
                float y = lm.Pos.Y + 0.9f + bob;
                var m = Math3D.Compose(lm.Pos.X, y, lm.Pos.Z, 0, _time * 1.2f, 0, 0.5f, 1.4f, 0.5f);
                (float r, float g, float b) = lm.Kind switch
                {
                    MarkKind.Talk => (0.86f, 0.72f, 0.40f),
                    MarkKind.Collect => (0.52f, 0.80f, 0.50f),
                    _ => (0.66f, 0.70f, 0.78f),
                };
                _renderer.SetSceneUniforms(s, vp, m, light);
                _shadow.BindTo(s);
                s.SetV3("uTint", r, g, b);
                s.SetF("uRim", 0.8f);
                s.SetV3("uEmissive", r * 0.18f, g * 0.18f, b * 0.18f);
                GL.BindVertexArray(_beaconVao);
                GL.BindBuffer(BufferTarget.ElementArrayBuffer, _beaconIbo);
                GL.DrawElements(PrimitiveType.Triangles, _beaconIndexCount, DrawElementsType.UnsignedInt, 0);
            }
        }

        void RenderPlayer(float[] vp, SceneLight light, float[] model)
        {
            var s = _renderer.SkinnedShader;
            _renderer.SetSceneUniforms(s, vp, model, light);
            _shadow.BindTo(s);
            s.SetMat4Array("uBones", _sk.SkinMatrices, Bone.Count);
            s.SetV3("uTint", 0.66f, 0.52f, 0.40f);
            s.SetF("uRim", 0.55f);
            s.SetV3("uEmissive", 0, 0, 0);
            GL.BindVertexArray(_skinVao);
            GL.BindBuffer(BufferTarget.ElementArrayBuffer, _skinIbo);
            GL.DrawElements(PrimitiveType.Triangles, _skinIndexCount, DrawElementsType.UnsignedInt, 0);
        }

        float[] PlayerModel()
        {
            var m = Math3D.Mat4Identity();
            float cy = MathF.Cos(_player.Yaw), sy = MathF.Sin(_player.Yaw);
            m[0] = cy; m[2] = -sy; m[8] = sy; m[10] = cy;
            m[12] = _player.Pos.X; m[13] = _player.Pos.Y; m[14] = _player.Pos.Z;
            return m;
        }

        // ---------------- UI ----------------

        void DrawGameUi()
        {
            var ctx = new HudContext
            {
                Story = _story, Player = _player, Portals = _portals, Landmarks = _landmarks,
                Ach = _ach, Panel = _panel, RegionName = RegionTitleNow(), Prompt = PromptNow(),
                MapTex = _mapTex, Time = _time, Fps = _fps, PlayerYaw = _player.Yaw,
                ShadowOn = _shadow.Enabled, PostOn = _post.Enabled,
            };
            _ui.Draw(_overlay, ctx);
            Title = $"{TITLE} | {(_story.Finished ? "旅程完成" : $"{_story.Chapter + 1}. {StoryData.Chapters[Math.Min(_story.Chapter, StoryData.Chapters.Length - 1)]}")}";
        }

        string RegionTitleNow()
        {
            var r = TerrainConfig.RegionAt(_player.Pos.X, _player.Pos.Z);
            return TerrainConfig.RegionTitle.TryGetValue(r, out var t) ? t : r;
        }

        string? PromptNow()
        {
            if (_story.Dlg.Active || _panel != UiPanel.None || _portals.MenuOpen) return null;
            var lm = _landmarks.Nearest(_player.Pos, out float ld);
            if (lm != null && ld <= LandmarkSystem.Range) return $"E · {lm.Label}";
            var p = _portals.Nearest(_player.Pos, out float pd);
            if (p != null && pd <= PortalSystem.InteractRange) return $"F · 传送门 {p.Title}";
            return null;
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
