"""
renderer.py -- HDR 前向渲染器

管线:
    1. 阴影 pass    -> 2048^2 正交深度图 (跟随玩家的级联近似)
    2. 主 pass      -> RGBA16F HDR 缓冲
         天空(全屏大气散射) -> 地形 -> 物件(实例化) -> 植被 -> 水面
    3. 后处理       -> 亮部提取 -> 高斯模糊(4 次) -> 合成(ACES+分级+描边+暗角+颗粒) -> FXAA -> 屏幕
"""
from __future__ import annotations

import numpy as np

from . import math3d as m3
from . import shaders as SH

F32 = np.float32


def setu(prog, name, value):
    """安全设置 uniform: 不存在或被优化掉时静默跳过。"""
    try:
        u = prog[name]
    except KeyError:
        return
    try:
        u.value = value
    except Exception:
        pass


def setm(prog, name, mat):
    try:
        u = prog[name]
    except KeyError:
        return
    u.write(m3.mat_bytes(mat))


class Renderer:
    SHADOW_SIZE = 2048

    def __init__(self, ctx, width, height, quality="high"):
        self.ctx = ctx
        self.width = max(int(width), 16)
        self.height = max(int(height), 16)
        self.quality = quality
        self.time = 0.0

        self._compile()
        self._make_quad()
        self._make_shadow()
        self._make_targets()

        # ---- 可调渲染参数 (由区域配置驱动) ----
        self.style = 0.0            # 0 写实 1 卡通
        self.exposure = 1.05
        self.bloom_strength = 0.55
        self.bloom_threshold = 1.02
        self.vignette = 0.55
        self.grain = 0.022
        self.saturation = 0.88
        self.lift = (0.0, 0.0, 0.0)
        self.gain = (1.0, 1.0, 1.0)
        self.outline = 0.0
        self.znear = 0.12
        self.zfar = 900.0

        self.sun_dir = m3.normalize(m3.vec3(0.42, 0.66, 0.62))
        self.sun_color = (1.28, 1.16, 0.98)
        self.ambient_sky = (0.30, 0.36, 0.46)
        self.ambient_ground = (0.15, 0.14, 0.13)
        self.fog_color = (0.55, 0.60, 0.68)
        self.fog_sun_color = (0.80, 0.76, 0.72)
        self.fog_density = 0.0075
        self.fog_height_falloff = 0.028
        self.sky_zenith = (0.19, 0.34, 0.62)
        self.sky_horizon = (0.72, 0.78, 0.86)
        self.ground_color = (0.16, 0.15, 0.14)
        self.star_amount = 0.0
        self.cloud_amount = 0.55
        self.shadow_strength = 0.86
        self.water_color = (0.16, 0.36, 0.42)
        self.water_deep = (0.03, 0.09, 0.14)
        self.wind = 0.055

        # 剧情用后处理
        self.fade_amount = 0.0
        self.fade_color = (0.0, 0.0, 0.0)
        self.pulse = 0.0
        self.desat_radial = 0.0

        # 回响波
        self.echo_origin = (0.0, 0.0, 0.0)
        self.echo_radius = -1.0
        self.echo_color = (0.22, 0.62, 0.60)

        self.frame_id = 0
        self._common_stamp = {}

    # ------------------------------------------------------------------
    def _compile(self):
        c = self.ctx
        self.p_sky = c.program(vertex_shader=SH.SKY_VS, fragment_shader=SH.SKY_FS)
        self.p_terrain = c.program(vertex_shader=SH.TERRAIN_VS, fragment_shader=SH.TERRAIN_FS)
        self.p_object = c.program(vertex_shader=SH.OBJECT_VS, fragment_shader=SH.OBJECT_FS)
        self.p_skin = c.program(vertex_shader=SH.OBJECT_SKIN_VS, fragment_shader=SH.OBJECT_FS)
        self.p_foliage = c.program(vertex_shader=SH.FOLIAGE_VS, fragment_shader=SH.FOLIAGE_FS)
        self.p_water = c.program(vertex_shader=SH.WATER_VS, fragment_shader=SH.WATER_FS)
        self.p_sh_obj = c.program(vertex_shader=SH.SHADOW_INST_VS, fragment_shader=SH.SHADOW_FS)
        self.p_sh_ter = c.program(vertex_shader=SH.SHADOW_TERRAIN_VS, fragment_shader=SH.SHADOW_FS)
        self.p_bright = c.program(vertex_shader=SH.FS_QUAD_VS, fragment_shader=SH.BRIGHT_FS)
        self.p_blur = c.program(vertex_shader=SH.FS_QUAD_VS, fragment_shader=SH.BLUR_FS)
        self.p_comp = c.program(vertex_shader=SH.FS_QUAD_VS, fragment_shader=SH.COMPOSITE_FS)
        self.p_fxaa = c.program(vertex_shader=SH.FS_QUAD_VS, fragment_shader=SH.FXAA_FS)
        self.p_ui = c.program(vertex_shader=SH.UI_VS, fragment_shader=SH.UI_FS)

    def _make_quad(self):
        data = np.array([-1, -1, 3, -1, -1, 3], F32)
        self.quad_vbo = self.ctx.buffer(data.tobytes())
        self.vao_sky = self.ctx.vertex_array(self.p_sky, [(self.quad_vbo, "2f", "in_pos")])
        self.vao_bright = self.ctx.vertex_array(self.p_bright, [(self.quad_vbo, "2f", "in_pos")])
        self.vao_blur = self.ctx.vertex_array(self.p_blur, [(self.quad_vbo, "2f", "in_pos")])
        self.vao_comp = self.ctx.vertex_array(self.p_comp, [(self.quad_vbo, "2f", "in_pos")])
        self.vao_fxaa = self.ctx.vertex_array(self.p_fxaa, [(self.quad_vbo, "2f", "in_pos")])

    def _make_shadow(self):
        s = self.SHADOW_SIZE if self.quality != "low" else 1024
        self.shadow_size = s
        self.shadow_tex = self.ctx.depth_texture((s, s))
        self.shadow_tex.compare_func = ""
        self.shadow_tex.repeat_x = False
        self.shadow_tex.repeat_y = False
        self.shadow_tex.filter = (self.ctx.LINEAR, self.ctx.LINEAR)
        self.shadow_fbo = self.ctx.framebuffer(depth_attachment=self.shadow_tex)
        self.light_vp = m3.identity()

    def _make_targets(self):
        c = self.ctx
        w, h = self.width, self.height
        self.scene_tex = c.texture((w, h), 4, dtype="f2")
        self.scene_tex.filter = (c.LINEAR, c.LINEAR)
        self.scene_tex.repeat_x = self.scene_tex.repeat_y = False
        self.depth_tex = c.depth_texture((w, h))
        self.depth_tex.compare_func = ""
        self.depth_tex.filter = (c.NEAREST, c.NEAREST)
        self.scene_fbo = c.framebuffer(color_attachments=[self.scene_tex],
                                       depth_attachment=self.depth_tex)
        bw, bh = max(w // 2, 8), max(h // 2, 8)
        self.bloom_tex = []
        self.bloom_fbo = []
        for _ in range(2):
            t = c.texture((bw, bh), 4, dtype="f2")
            t.filter = (c.LINEAR, c.LINEAR)
            t.repeat_x = t.repeat_y = False
            self.bloom_tex.append(t)
            self.bloom_fbo.append(c.framebuffer(color_attachments=[t]))
        self.bloom_size = (bw, bh)
        self.ldr_tex = c.texture((w, h), 4, dtype="f1")
        self.ldr_tex.filter = (c.LINEAR, c.LINEAR)
        self.ldr_tex.repeat_x = self.ldr_tex.repeat_y = False
        self.ldr_fbo = c.framebuffer(color_attachments=[self.ldr_tex])

    def resize(self, width, height):
        width, height = max(int(width), 16), max(int(height), 16)
        if width == self.width and height == self.height:
            return
        self.width, self.height = width, height
        for o in (self.scene_fbo, self.ldr_fbo, *self.bloom_fbo):
            o.release()
        for t in (self.scene_tex, self.depth_tex, self.ldr_tex, *self.bloom_tex):
            t.release()
        self._make_targets()

    # ------------------------------------------------------------------
    # 公共 uniform
    # ------------------------------------------------------------------
    def _apply_common(self, prog):
        # 一帧之内公共 uniform 不变, 同一程序只写一次
        stamp = self._common_stamp.get(id(prog))
        if stamp == self.frame_id:
            return
        self._common_stamp[id(prog)] = self.frame_id
        setu(prog, "u_time", self.time)
        setu(prog, "u_camPos", tuple(float(x) for x in self.cam_pos))
        setu(prog, "u_sunDir", tuple(float(x) for x in self.sun_dir))
        setu(prog, "u_sunColor", self.sun_color)
        setu(prog, "u_ambientSky", self.ambient_sky)
        setu(prog, "u_ambientGround", self.ambient_ground)
        setu(prog, "u_fogColor", self.fog_color)
        setu(prog, "u_fogSunColor", self.fog_sun_color)
        setu(prog, "u_fogDensity", self.fog_density)
        setu(prog, "u_fogHeightFalloff", self.fog_height_falloff)
        setu(prog, "u_style", self.style)
        setu(prog, "u_exposure", self.exposure)
        setu(prog, "u_shadowTexel", 1.0 / self.shadow_size)
        setu(prog, "u_shadowStrength", self.shadow_strength)
        setu(prog, "u_echoOrigin", tuple(float(x) for x in self.echo_origin))
        setu(prog, "u_echoRadius", self.echo_radius)
        setu(prog, "u_echoColor", self.echo_color)
        setm(prog, "u_viewProj", self.view_proj)
        setm(prog, "u_lightVP", self.light_vp)

    # ------------------------------------------------------------------
    # 阴影
    # ------------------------------------------------------------------
    def build_light_matrix(self, center, radius=95.0):
        eye = np.asarray(center, F32) + self.sun_dir * (radius * 1.9)
        view = m3.look_at(eye, center)
        proj = m3.ortho(-radius, radius, -radius, radius, 1.0, radius * 4.2)
        self.light_vp = proj @ view
        return self.light_vp

    def begin_shadow(self):
        self.shadow_fbo.use()
        self.ctx.viewport = (0, 0, self.shadow_size, self.shadow_size)
        self.shadow_fbo.clear(depth=1.0)
        self.ctx.enable(self.ctx.DEPTH_TEST)
        self.ctx.disable(self.ctx.CULL_FACE)

    # ------------------------------------------------------------------
    # 主 pass
    # ------------------------------------------------------------------
    def begin_scene(self, view, proj, cam_pos):
        self.frame_id += 1
        self.view = view
        self.proj = proj
        self.view_proj = proj @ view
        self.inv_view_proj = m3.inverse(self.view_proj)
        self.cam_pos = np.asarray(cam_pos, F32)
        self.scene_fbo.use()
        self.ctx.viewport = (0, 0, self.width, self.height)
        self.scene_fbo.clear(0.0, 0.0, 0.0, 1.0, depth=1.0)
        self.ctx.enable(self.ctx.DEPTH_TEST)
        self.shadow_tex.use(location=0)

    def draw_sky(self):
        c = self.ctx
        c.disable(c.DEPTH_TEST)
        p = self.p_sky
        setm(p, "u_invViewProj", self.inv_view_proj)
        setu(p, "u_camPos", tuple(float(x) for x in self.cam_pos))
        setu(p, "u_sunDir", tuple(float(x) for x in self.sun_dir))
        setu(p, "u_sunColor", self.sun_color)
        setu(p, "u_skyZenith", self.sky_zenith)
        setu(p, "u_skyHorizon", self.sky_horizon)
        setu(p, "u_groundColor", self.ground_color)
        setu(p, "u_starAmount", self.star_amount)
        setu(p, "u_cloudAmount", self.cloud_amount)
        setu(p, "u_time", self.time)
        setu(p, "u_style", self.style)
        self.vao_sky.render(mode=self.ctx.TRIANGLES, vertices=3)
        c.enable(c.DEPTH_TEST)

    def prepare_terrain(self):
        setu(self.p_terrain, "u_shadowMap", 0)
        self._apply_common(self.p_terrain)
        self.ctx.enable(self.ctx.CULL_FACE)
        self.ctx.cull_face = "back"

    def prepare_object(self, roughness=0.82, metallic=0.0, noise_scale=0.0):
        p = self.p_object
        setu(p, "u_shadowMap", 0)
        setu(p, "u_roughness", roughness)
        setu(p, "u_metallic", metallic)
        setu(p, "u_noiseScale", noise_scale)
        self._apply_common(p)

    def prepare_foliage(self):
        p = self.p_foliage
        setu(p, "u_shadowMap", 0)
        setu(p, "u_windStrength", self.wind)
        self._apply_common(p)

    def prepare_skin(self, roughness=0.78, metallic=0.0, noise_scale=0.0):
        p = self.p_skin
        setu(p, "u_shadowMap", 0)
        setu(p, "u_roughness", roughness)
        setu(p, "u_metallic", metallic)
        setu(p, "u_noiseScale", noise_scale)
        self._apply_common(p)
        self.ctx.enable(self.ctx.CULL_FACE)
        self.ctx.cull_face = "back"
        self.ctx.disable(self.ctx.CULL_FACE)

    def prepare_water(self):
        p = self.p_water
        setu(p, "u_shadowMap", 0)
        setu(p, "u_waterColor", self.water_color)
        setu(p, "u_waterDeep", self.water_deep)
        self._apply_common(p)
        self.ctx.enable(self.ctx.BLEND)
        self.ctx.blend_func = self.ctx.SRC_ALPHA, self.ctx.ONE_MINUS_SRC_ALPHA

    # ------------------------------------------------------------------
    # 后处理
    # ------------------------------------------------------------------
    def post_process(self):
        c = self.ctx
        c.disable(c.DEPTH_TEST)
        c.disable(c.BLEND)
        c.disable(c.CULL_FACE)
        bw, bh = self.bloom_size

        # 亮部
        self.bloom_fbo[0].use()
        c.viewport = (0, 0, bw, bh)
        self.scene_tex.use(0)
        setu(self.p_bright, "u_tex", 0)
        setu(self.p_bright, "u_threshold", self.bloom_threshold)
        setu(self.p_bright, "u_softKnee", 0.62)
        self.vao_bright.render(mode=c.TRIANGLES, vertices=3)

        # 分离高斯 x2
        src, dst = 0, 1
        iters = 2 if self.quality != "low" else 1
        for k in range(iters):
            for dx, dy in ((1.0 / bw, 0.0), (0.0, 1.0 / bh)):
                self.bloom_fbo[dst].use()
                self.bloom_tex[src].use(0)
                setu(self.p_blur, "u_tex", 0)
                setu(self.p_blur, "u_dir", (dx * (1.0 + k * 0.8), dy * (1.0 + k * 0.8)))
                self.vao_blur.render(mode=c.TRIANGLES, vertices=3)
                src, dst = dst, src

        # 合成
        self.ldr_fbo.use()
        c.viewport = (0, 0, self.width, self.height)
        self.scene_tex.use(0)
        self.bloom_tex[src].use(1)
        self.depth_tex.use(2)
        p = self.p_comp
        setu(p, "u_scene", 0)
        setu(p, "u_bloom", 1)
        setu(p, "u_depth", 2)
        setu(p, "u_bloomStrength", self.bloom_strength)
        setu(p, "u_exposure", self.exposure)
        setu(p, "u_vignette", self.vignette)
        setu(p, "u_grain", self.grain)
        setu(p, "u_time", self.time)
        setu(p, "u_saturation", self.saturation)
        setu(p, "u_lift", self.lift)
        setu(p, "u_gain", self.gain)
        setu(p, "u_style", self.style)
        setu(p, "u_texel", (1.0 / self.width, 1.0 / self.height))
        setu(p, "u_outline", self.outline)
        setu(p, "u_near", self.znear)
        setu(p, "u_far", self.zfar)
        setu(p, "u_fadeAmount", self.fade_amount)
        setu(p, "u_fadeColor", self.fade_color)
        setu(p, "u_pulse", self.pulse)
        setu(p, "u_desatRadial", self.desat_radial)
        self.vao_comp.render(mode=c.TRIANGLES, vertices=3)

        # FXAA -> 默认帧缓冲
        self.ctx.screen.use()
        c.viewport = (0, 0, self.width, self.height)
        self.ldr_tex.use(0)
        setu(self.p_fxaa, "u_tex", 0)
        setu(self.p_fxaa, "u_texel", (1.0 / self.width, 1.0 / self.height))
        self.vao_fxaa.render(mode=c.TRIANGLES, vertices=3)


# --------------------------------------------------------------------------
# 实例数据打包
# --------------------------------------------------------------------------
def pack_instances(positions, rot_y=None, scales=None, tints=None, glows=None):
    """
    生成着色器要求的 float32[N,16]:
        m0 = (R列0.x, R列0.y, R列0.z, tx)
        m1 = (R列1.x, R列1.y, R列1.z, ty)
        m2 = (R列2.x, R列2.y, R列2.z, tz)
        tint = (r, g, b, emissive)
    """
    p = np.asarray(positions, F32).reshape(-1, 3)
    n = len(p)
    if n == 0:
        return np.zeros((0, 16), F32)
    ry = np.zeros(n, F32) if rot_y is None else np.asarray(rot_y, F32).reshape(-1)
    if len(ry) == 1:
        ry = np.repeat(ry, n)
    if scales is None:
        s = np.ones((n, 3), F32)
    else:
        s = np.asarray(scales, F32)
        if s.ndim == 0:
            s = np.full((n, 3), float(s), F32)
        elif s.ndim == 1 and len(s) == n:
            s = np.repeat(s[:, None], 3, 1).astype(F32)
        elif s.ndim == 1 and len(s) == 3:
            s = np.tile(s[None, :], (n, 1)).astype(F32)
        else:
            s = s.reshape(n, 3).astype(F32)
    if tints is None:
        t = np.ones((n, 3), F32)
    else:
        t = np.asarray(tints, F32)
        if t.ndim == 1:
            t = np.tile(t[None, :3], (n, 1)).astype(F32)
        else:
            t = t.reshape(n, 3).astype(F32)
    if glows is None:
        g = np.zeros(n, F32)
    else:
        g = np.asarray(glows, F32).reshape(-1)
        if len(g) == 1:
            g = np.repeat(g, n)

    c, sn = np.cos(ry), np.sin(ry)
    out = np.empty((n, 16), F32)
    out[:, 0] = c * s[:, 0]
    out[:, 1] = 0.0
    out[:, 2] = -sn * s[:, 0]
    out[:, 3] = p[:, 0]
    out[:, 4] = 0.0
    out[:, 5] = s[:, 1]
    out[:, 6] = 0.0
    out[:, 7] = p[:, 1]
    out[:, 8] = sn * s[:, 2]
    out[:, 9] = 0.0
    out[:, 10] = c * s[:, 2]
    out[:, 11] = p[:, 2]
    out[:, 12:15] = t
    out[:, 15] = g
    return out


class InstancedMesh:
    """一份几何 + 一份实例缓冲, 同时持有主 pass 与阴影 pass 的 VAO。"""

    def __init__(self, ctx, renderer, verts, idx, max_instances=512, foliage=False):
        self.ctx = ctx
        self.foliage = foliage
        self.count = 0
        self.max_instances = max(int(max_instances), 1)
        self.vbo = ctx.buffer(np.ascontiguousarray(verts, F32).tobytes())
        self.ibo = ctx.buffer(np.ascontiguousarray(idx, np.uint32).tobytes())
        self.inst = ctx.buffer(reserve=self.max_instances * 16 * 4, dynamic=True)
        if foliage:
            content = [(self.vbo, "3f 3f 2f", "in_pos", "in_normal", "in_uv"),
                       (self.inst, "4f 4f 4f 4f /i", "in_m0", "in_m1", "in_m2", "in_tint")]
            self.vao = ctx.vertex_array(renderer.p_foliage, content, index_buffer=self.ibo)
            self.vao_shadow = None
        else:
            content = [(self.vbo, "3f 3f", "in_pos", "in_normal"),
                       (self.inst, "4f 4f 4f 4f /i", "in_m0", "in_m1", "in_m2", "in_tint")]
            self.vao = ctx.vertex_array(renderer.p_object, content, index_buffer=self.ibo)
            # 阴影 pass 不需要法线与色调
            content_s = [(self.vbo, "3f 3x4", "in_pos"),
                         (self.inst, "4f 4f 4f 4x4 /i", "in_m0", "in_m1", "in_m2")]
            self.vao_shadow = ctx.vertex_array(renderer.p_sh_obj, content_s,
                                               index_buffer=self.ibo)

    def upload(self, data):
        data = np.ascontiguousarray(data, F32)
        n = len(data)
        if n > self.max_instances:
            self.max_instances = int(n * 1.5) + 8
            self.inst.orphan(self.max_instances * 16 * 4)
        self.count = n
        if n:
            self.inst.write(data.tobytes())

    def render(self, shadow=False):
        if self.count <= 0:
            return
        vao = self.vao_shadow if shadow else self.vao
        if vao is None:
            return
        vao.render(instances=self.count)

    def release(self):
        for o in (self.vao, self.vao_shadow, self.vbo, self.ibo, self.inst):
            if o is not None:
                try:
                    o.release()
                except Exception:
                    pass


class SkinnedMesh:
    """蒙皮网格: 顶点含 (pos3, nrm3, j0,w0,j1,w1), 每帧上传骨骼矩阵 u_bones。

    每个实例独立渲染 (NPC/玩家各自 1 个实例), 支持程序化动画。
    """

    def __init__(self, ctx, renderer, verts, idx, max_instances=2):
        self.ctx = ctx
        self.count = 0
        self.max_instances = max(int(max_instances), 1)
        self.vbo = ctx.buffer(np.ascontiguousarray(verts, F32).tobytes())
        self.ibo = ctx.buffer(np.ascontiguousarray(idx, np.uint32).tobytes())
        self.inst = ctx.buffer(reserve=self.max_instances * 16 * 4, dynamic=True)
        content = [(self.vbo, "3f 3f 4f", "in_pos", "in_normal", "in_jw"),
                   (self.inst, "4f 4f 4f 4f /i", "in_m0", "in_m1", "in_m2", "in_tint")]
        self.vao = ctx.vertex_array(renderer.p_skin, content, index_buffer=self.ibo)
        content_s = [(self.vbo, "3f 3x4", "in_pos"),
                     (self.inst, "4f 4f 4f 4x4 /i", "in_m0", "in_m1", "in_m2")]
        self.vao_shadow = ctx.vertex_array(renderer.p_sh_obj, content_s,
                                           index_buffer=self.ibo)

    def upload(self, data):
        data = np.ascontiguousarray(data, F32)
        n = len(data)
        if n > self.max_instances:
            self.max_instances = int(n * 1.5) + 8
            self.inst.orphan(self.max_instances * 16 * 4)
        self.count = n
        if n:
            self.inst.write(data.tobytes())

    def set_bones(self, matrices):
        """matrices: (8,4,4) 骨骼矩阵 (numpy 行主序), 转置为 GLSL mat4 列主序写入。"""
        mats = np.asarray(matrices, F32).reshape(-1, 4, 4)
        # 列主序: 每 4x4 转置
        m = np.zeros((8, 4, 4), F32)
        m[:len(mats)] = mats.transpose(0, 2, 1)
        self.vao.program["u_bones"].write(np.ascontiguousarray(m, F32).tobytes())

    def render(self, shadow=False):
        if self.count <= 0:
            return
        vao = self.vao_shadow if shadow else self.vao
        if vao is None:
            return
        vao.render(instances=self.count)

    def release(self):
        for o in (self.vao, self.vao_shadow, self.vbo, self.ibo, self.inst):
            if o is not None:
                try:
                    o.release()
                except Exception:
                    pass
