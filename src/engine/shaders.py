"""
shaders.py -- 全部 GLSL 源码

以 Python 字符串常量内联, 这样 PyInstaller 打包时无需附带任何数据文件。
目标 GLSL 版本: 330 core (兼容绝大多数 2012 年后的独显/核显)。

渲染风格采用 PBR <-> NPR 双模混合:
    u_style = 0.0  -> 写实厚涂 (消音地带 / 镜之境 / 黑石)
    u_style = 1.0  -> 卡通渲染 (失落之地苔原 / 荒原白昼)
中间值做连续插值, 玩家跨区域时画风平滑过渡。
"""

# ==========================================================================
# 公共库: 噪声 / 光照 / 雾 / 阴影
# ==========================================================================
COMMON = """
#define PI 3.14159265359

// ---------- hash & noise ----------
float hash11(float p){ p = fract(p*0.1031); p *= p+33.33; p *= p+p; return fract(p); }
float hash12(vec2 p){ vec3 p3 = fract(vec3(p.xyx)*0.1031); p3 += dot(p3, p3.yzx+33.33); return fract((p3.x+p3.y)*p3.z); }
vec2  hash22(vec2 p){ vec3 p3 = fract(vec3(p.xyx)*vec3(.1031,.1030,.0973)); p3 += dot(p3, p3.yzx+33.33); return fract((p3.xx+p3.yz)*p3.zy); }
float hash13(vec3 p3){ p3 = fract(p3*0.1031); p3 += dot(p3, p3.zyx+31.32); return fract((p3.x+p3.y)*p3.z); }

float vnoise(vec2 p){
    vec2 i = floor(p); vec2 f = fract(p);
    vec2 u = f*f*(3.0-2.0*f);
    return mix(mix(hash12(i+vec2(0,0)), hash12(i+vec2(1,0)), u.x),
               mix(hash12(i+vec2(0,1)), hash12(i+vec2(1,1)), u.x), u.y);
}

float vnoise3(vec3 p){
    vec3 i = floor(p); vec3 f = fract(p);
    vec3 u = f*f*(3.0-2.0*f);
    float n000=hash13(i+vec3(0,0,0)), n100=hash13(i+vec3(1,0,0));
    float n010=hash13(i+vec3(0,1,0)), n110=hash13(i+vec3(1,1,0));
    float n001=hash13(i+vec3(0,0,1)), n101=hash13(i+vec3(1,0,1));
    float n011=hash13(i+vec3(0,1,1)), n111=hash13(i+vec3(1,1,1));
    return mix(mix(mix(n000,n100,u.x), mix(n010,n110,u.x), u.y),
               mix(mix(n001,n101,u.x), mix(n011,n111,u.x), u.y), u.z);
}

float fbm(vec2 p, int oct){
    float s = 0.0, a = 0.5;
    for(int i=0;i<6;i++){
        if(i>=oct) break;
        s += vnoise(p)*a; p *= 2.03; a *= 0.5;
    }
    return s;
}

// ---------- PBR ----------
float D_GGX(float NoH, float rough){
    float a = rough*rough;
    float a2 = a*a;
    float d = NoH*NoH*(a2-1.0)+1.0;
    return a2/max(PI*d*d, 1e-7);
}
float V_Smith(float NoV, float NoL, float rough){
    float a = rough*rough;
    float gv = NoL*(NoV*(1.0-a)+a);
    float gl = NoV*(NoL*(1.0-a)+a);
    return 0.5/max(gv+gl, 1e-6);
}
vec3 F_Schlick(float u, vec3 f0){
    float f = pow(1.0-u, 5.0);
    return f0 + (1.0-f0)*f;
}

// ---------- 阴影 ----------
uniform sampler2D u_shadowMap;
uniform mat4  u_lightVP;
uniform float u_shadowTexel;   // 1.0 / shadowMapSize
uniform float u_shadowStrength;

float sampleShadow(vec3 worldPos, float NoL){
    vec4 lp = u_lightVP * vec4(worldPos, 1.0);
    vec3 pc = lp.xyz / lp.w * 0.5 + 0.5;
    if(pc.z > 1.0 || pc.x < 0.001 || pc.x > 0.999 || pc.y < 0.001 || pc.y > 0.999)
        return 1.0;
    // 斜度自适应偏移, 抑制 shadow acne / peter-panning
    float bias = clamp(0.0016 * tan(acos(clamp(NoL,0.0,1.0))), 0.0004, 0.0055);
    float sum = 0.0;
    for(int y=-1;y<=1;y++){
        for(int x=-1;x<=1;x++){
            float d = texture(u_shadowMap, pc.xy + vec2(x,y)*u_shadowTexel).r;
            sum += (pc.z - bias > d) ? 0.0 : 1.0;
        }
    }
    float s = sum / 9.0;
    // 贴图边缘淡出, 避免硬切
    vec2 e = smoothstep(vec2(0.0), vec2(0.06), pc.xy) * (1.0-smoothstep(vec2(0.94), vec2(1.0), pc.xy));
    float edge = e.x*e.y;
    s = mix(1.0, s, edge);
    return mix(1.0, s, u_shadowStrength);
}

// ---------- 大气 / 雾 ----------
uniform vec3  u_fogColor;
uniform vec3  u_fogSunColor;
uniform float u_fogDensity;
uniform float u_fogHeightFalloff;
uniform vec3  u_sunDir;        // 指向太阳
uniform vec3  u_camPos;

vec3 applyFog(vec3 color, vec3 worldPos, vec3 viewDir){
    float dist = length(worldPos - u_camPos);
    // 高度雾: 相机与片元之间的雾积分
    float h0 = max(u_camPos.y, 0.0);
    float h1 = max(worldPos.y, 0.0);
    float dh = max(abs(h1-h0), 0.001);
    float t0 = exp(-h0*u_fogHeightFalloff);
    float t1 = exp(-h1*u_fogHeightFalloff);
    float integral = abs((t0-t1)/(dh*u_fogHeightFalloff));
    float amount = 1.0 - exp(-dist * u_fogDensity * integral);
    amount = clamp(amount, 0.0, 1.0);
    // 朝向太阳时雾偏暖 (前向散射)
    float sunAmount = max(dot(-viewDir, u_sunDir), 0.0);
    vec3 fogCol = mix(u_fogColor, u_fogSunColor, pow(sunAmount, 6.0));
    return mix(color, fogCol, amount);
}

// ---------- 主光照 (PBR/NPR 混合) ----------
uniform vec3  u_sunColor;
uniform vec3  u_ambientSky;
uniform vec3  u_ambientGround;
uniform float u_style;         // 0=写实 1=卡通
uniform float u_exposure;

vec3 shadeSurface(vec3 albedo, vec3 N, vec3 V, vec3 worldPos,
                  float rough, float metal, float ao, float shadow)
{
    vec3 L = normalize(u_sunDir);
    vec3 H = normalize(L+V);
    float NoL = dot(N, L);
    float NoV = max(dot(N, V), 1e-4);
    float NoH = max(dot(N, H), 0.0);
    float VoH = max(dot(V, H), 0.0);

    // --- 写实分支 ---
    float lambert = max(NoL, 0.0);
    vec3 f0 = mix(vec3(0.04), albedo, metal);
    float D = D_GGX(NoH, rough);
    float Vv = V_Smith(NoV, max(NoL,0.0), rough);
    vec3  F = F_Schlick(VoH, f0);
    vec3 spec = D*Vv*F;
    vec3 kd = (1.0-F)*(1.0-metal);
    vec3 pbrDirect = (kd*albedo/PI + spec) * u_sunColor * lambert * shadow;

    // --- 卡通分支: 色阶化 + 边缘光 ---
    float wrapped = NoL*0.5+0.5;                       // half-lambert, 暗部不死黑
    float band = smoothstep(0.48,0.52, wrapped)*0.55
               + smoothstep(0.62,0.66, wrapped)*0.28
               + smoothstep(0.80,0.84, wrapped)*0.17;
    band = mix(band, band*0.35+0.12, 1.0-shadow);
    float rim = pow(1.0-NoV, 3.5) * smoothstep(-0.3, 0.6, NoL);
    vec3 tonSpec = vec3(smoothstep(0.86, 0.90, NoH*(1.0-rough))) * u_sunColor * 0.6;
    vec3 npr = albedo * u_sunColor * band + tonSpec * shadow
             + rim * u_sunColor * 0.35 * albedo;

    vec3 direct = mix(pbrDirect, npr, u_style);

    // --- 环境光: 半球 IBL 近似 ---
    float hemi = N.y*0.5+0.5;
    vec3 ambient = mix(u_ambientGround, u_ambientSky, hemi) * albedo * ao;
    // 卡通模式下环境更平、更亮
    ambient = mix(ambient, mix(u_ambientGround,u_ambientSky,0.5)*albedo*mix(1.0,ao,0.5)*1.25, u_style);

    return direct + ambient;
}
"""

# ==========================================================================
# 天空 (大气散射)
# ==========================================================================
SKY_VS = """
#version 330 core
layout(location=0) in vec2 in_pos;
out vec2 v_uv;
void main(){
    v_uv = in_pos*0.5+0.5;
    gl_Position = vec4(in_pos, 1.0, 1.0);
}
"""

SKY_FS = """
#version 330 core
in vec2 v_uv;
out vec4 f_color;

uniform mat4  u_invViewProj;
uniform vec3  u_camPos;
uniform vec3  u_sunDir;
uniform vec3  u_sunColor;
uniform vec3  u_skyZenith;
uniform vec3  u_skyHorizon;
uniform vec3  u_groundColor;
uniform float u_starAmount;
uniform float u_cloudAmount;
uniform float u_time;
uniform float u_style;

float hash12(vec2 p){ vec3 p3 = fract(vec3(p.xyx)*0.1031); p3 += dot(p3, p3.yzx+33.33); return fract((p3.x+p3.y)*p3.z); }
float vnoise(vec2 p){
    vec2 i=floor(p), f=fract(p); vec2 u=f*f*(3.0-2.0*f);
    return mix(mix(hash12(i),hash12(i+vec2(1,0)),u.x), mix(hash12(i+vec2(0,1)),hash12(i+vec2(1,1)),u.x), u.y);
}
float fbm(vec2 p){
    float s=0.0,a=0.5;
    for(int i=0;i<5;i++){ s+=vnoise(p)*a; p*=2.07; a*=0.5; }
    return s;
}

void main(){
    // 重建世界空间视线方向
    vec4 ndc = vec4(v_uv*2.0-1.0, 1.0, 1.0);
    vec4 wp = u_invViewProj * ndc;
    vec3 dir = normalize(wp.xyz/wp.w - u_camPos);

    float h = dir.y;
    float sunDot = dot(dir, u_sunDir);

    // --- Rayleigh 近似: 天顶->地平线渐变 ---
    float t = pow(clamp(1.0 - max(h,0.0), 0.0, 1.0), 2.2);
    vec3 sky = mix(u_skyZenith, u_skyHorizon, t);

    // --- Mie 前向散射: 太阳周围辉光 ---
    float mie = pow(max(sunDot, 0.0), 8.0)*0.35 + pow(max(sunDot,0.0), 500.0)*3.0;
    sky += u_sunColor * mie * smoothstep(-0.12, 0.25, h+0.12);

    // --- 日轮 ---
    float disc = smoothstep(0.99965, 0.99992, sunDot);
    sky += u_sunColor * disc * 12.0;

    // --- 星空 (夜间/镜之境) ---
    if(u_starAmount > 0.001){
        vec2 sp = dir.xz/max(abs(dir.y)+0.18, 0.05);
        float stars = pow(hash12(floor(sp*180.0)), 62.0);
        float twinkle = 0.65+0.35*sin(u_time*2.3 + hash12(floor(sp*180.0))*44.0);
        sky += vec3(stars*twinkle) * u_starAmount * smoothstep(-0.02, 0.30, h);
    }

    // --- 云层 ---
    if(u_cloudAmount > 0.001 && h > 0.005){
        vec2 cp = dir.xz/(h+0.10) * 0.55 + vec2(u_time*0.006, u_time*0.0032);
        float c = fbm(cp*1.15);
        c = smoothstep(0.50, 0.86, c);
        // 卡通模式云边界更硬
        float cToon = smoothstep(0.58, 0.63, fbm(cp*1.15));
        c = mix(c, cToon, u_style);
        float shade = 0.55 + 0.45*smoothstep(-0.1, 0.5, sunDot);
        vec3 cloudCol = mix(vec3(0.62,0.66,0.74), u_sunColor*1.5, shade*0.55);
        sky = mix(sky, cloudCol, c*u_cloudAmount*smoothstep(0.005,0.22,h));
    }

    // --- 地平线以下 ---
    sky = mix(sky, u_groundColor, smoothstep(0.0, -0.10, h));

    f_color = vec4(sky, 1.0);
}
"""

# ==========================================================================
# 地形
# ==========================================================================
TERRAIN_VS = """
#version 330 core
layout(location=0) in vec3 in_pos;
layout(location=1) in vec3 in_normal;
layout(location=2) in vec3 in_albedo;
layout(location=3) in vec2 in_params;   // x=style权重(未用,预留) y=湿润度

uniform mat4 u_viewProj;

out vec3 v_world;
out vec3 v_normal;
out vec3 v_albedo;
out vec2 v_params;

void main(){
    v_world  = in_pos;
    v_normal = in_normal;
    v_albedo = in_albedo;
    v_params = in_params;
    gl_Position = u_viewProj * vec4(in_pos, 1.0);
}
"""

TERRAIN_FS = """
#version 330 core
in vec3 v_world;
in vec3 v_normal;
in vec3 v_albedo;
in vec2 v_params;
out vec4 f_color;

__COMMON__

uniform float u_time;
uniform vec3  u_echoOrigin;      // 回响波中心
uniform float u_echoRadius;      // 当前半径, <0 表示未激活
uniform vec3  u_echoColor;

void main(){
    vec3 N = normalize(v_normal);
    vec3 V = normalize(u_camPos - v_world);
    float slope = 1.0 - clamp(N.y, 0.0, 1.0);

    // ---- 程序化细节: 三重尺度噪声打破平坦感 ----
    vec2 p = v_world.xz;
    float macro  = fbm(p*0.013, 4);
    float meso   = fbm(p*0.13, 3);
    float micro  = vnoise(p*1.7);

    vec3 albedo = v_albedo;
    // 宏观色相扰动
    albedo *= 0.80 + 0.40*macro;
    albedo *= 0.90 + 0.20*meso;
    albedo *= 0.94 + 0.12*micro;

    // ---- 陡坡露出岩层 (三平面近似) ----
    float rockMask = smoothstep(0.42, 0.72, slope);
    float strata = vnoise(vec2(v_world.y*2.6, (v_world.x+v_world.z)*0.12));
    vec3 rock = mix(vec3(0.196,0.196,0.216), vec3(0.322,0.310,0.318), strata);
    rock *= 0.85 + 0.30*fbm(p*0.6, 3);
    albedo = mix(albedo, rock, rockMask);

    // ---- 低洼处湿润变深 ----
    float wet = clamp(v_params.y, 0.0, 1.0);
    albedo = mix(albedo, albedo*0.55, wet*0.7);

    float rough = mix(0.94, 0.62, wet);
    rough = mix(rough, 0.80, rockMask);
    float ao = mix(1.0, 0.72, rockMask*0.5) * (0.86+0.14*meso);

    float NoL = dot(N, normalize(u_sunDir));
    float shadow = sampleShadow(v_world, NoL);

    vec3 col = shadeSurface(albedo, N, V, v_world, rough, 0.0, ao, shadow);

    // ---- 回响波: 沿地表扩散的环形辉光, 呼应"心跳/共振"主题 ----
    if(u_echoRadius > 0.0){
        float d = distance(v_world.xz, u_echoOrigin.xz);
        float ring = exp(-pow((d-u_echoRadius)*0.30, 2.0));
        float grid = 0.5+0.5*sin(d*1.4 - u_time*5.0);
        col += u_echoColor * ring * (0.35+0.65*grid) * 1.4;
    }

    col = applyFog(col, v_world, -V);
    f_color = vec4(col, 1.0);
}
""".replace("__COMMON__", COMMON)

# ==========================================================================
# 通用物件 (实例化): 岩石 / 道具 / NPC / 玩家
# ==========================================================================
OBJECT_VS = """
#version 330 core
layout(location=0) in vec3 in_pos;
layout(location=1) in vec3 in_normal;
// 实例属性
layout(location=2) in vec4 in_m0;
layout(location=3) in vec4 in_m1;
layout(location=4) in vec4 in_m2;
layout(location=5) in vec4 in_tint;   // rgb=色调 a=自发光强度

uniform mat4 u_viewProj;

out vec3 v_world;
out vec3 v_normal;
out vec4 v_tint;

void main(){
    mat4 M = mat4(vec4(in_m0.xyz,0.0), vec4(in_m1.xyz,0.0), vec4(in_m2.xyz,0.0),
                  vec4(in_m0.w, in_m1.w, in_m2.w, 1.0));
    vec4 wp = M * vec4(in_pos, 1.0);
    v_world = wp.xyz;
    // 均匀缩放假设下用左上 3x3 直接变换法线
    mat3 nm = mat3(in_m0.xyz, in_m1.xyz, in_m2.xyz);
    v_normal = normalize(nm * in_normal);
    v_tint = in_tint;
    gl_Position = u_viewProj * wp;
}
"""

# 蒙皮版对象 VS: 顶点附带最多 2 个关节 (j0,w0,j1,w1), 由 u_bones 做姿势旋转
OBJECT_SKIN_VS = """
#version 330 core
layout(location=0) in vec3 in_pos;
layout(location=1) in vec3 in_normal;
layout(location=2) in vec4 in_jw;      // x=j0, y=w0, z=j1, w=w1
// 实例属性
layout(location=3) in vec4 in_m0;
layout(location=4) in vec4 in_m1;
layout(location=5) in vec4 in_m2;
layout(location=6) in vec4 in_tint;

uniform mat4 u_viewProj;
uniform mat4 u_bones[8];

out vec3 v_world;
out vec3 v_normal;
out vec4 v_tint;

void main(){
    vec3 sp = in_pos;
    vec3 sn = in_normal;
    // 两关节权重混合 (姿势旋转矩阵由 CPU 每帧计算)
    vec4 p0 = u_bones[int(in_jw.x)] * vec4(sp, 1.0);
    vec4 p1 = u_bones[int(in_jw.z)] * vec4(sp, 1.0);
    vec3 bp = in_jw.y * p0.xyz + in_jw.w * p1.xyz;
    mat3 n0 = mat3(u_bones[int(in_jw.x)]);
    mat3 n1 = mat3(u_bones[int(in_jw.z)]);
    vec3 bn = normalize(in_jw.y * (n0 * sn) + in_jw.w * (n1 * sn));
    if (length(bn) < 0.5) bn = sn;

    mat4 M = mat4(vec4(in_m0.xyz,0.0), vec4(in_m1.xyz,0.0), vec4(in_m2.xyz,0.0),
                  vec4(in_m0.w, in_m1.w, in_m2.w, 1.0));
    vec4 wp = M * vec4(bp, 1.0);
    v_world = wp.xyz;
    mat3 nm = mat3(in_m0.xyz, in_m1.xyz, in_m2.xyz);
    v_normal = normalize(nm * bn);
    v_tint = in_tint;
    gl_Position = u_viewProj * wp;
}
"""

OBJECT_FS = """
#version 330 core
in vec3 v_world;
in vec3 v_normal;
in vec4 v_tint;
out vec4 f_color;

__COMMON__

uniform float u_time;
uniform float u_roughness;
uniform float u_metallic;
uniform float u_noiseScale;
uniform vec3  u_echoOrigin;
uniform float u_echoRadius;
uniform vec3  u_echoColor;

void main(){
    vec3 N = normalize(v_normal);
    vec3 V = normalize(u_camPos - v_world);

    vec3 albedo = v_tint.rgb;
    if(u_noiseScale > 0.0){
        float n = vnoise3(v_world*u_noiseScale);
        float n2 = vnoise3(v_world*u_noiseScale*4.1);
        albedo *= 0.80 + 0.28*n + 0.12*n2;
    }

    float NoL = dot(N, normalize(u_sunDir));
    float shadow = sampleShadow(v_world, NoL);
    vec3 col = shadeSurface(albedo, N, V, v_world, u_roughness, u_metallic, 1.0, shadow);

    // 自发光 (晶石 / 刻痕 / 冷光 / 收集物)
    float pulse = 0.72 + 0.28*sin(u_time*2.1 + v_world.x*0.35 + v_world.z*0.27);
    col += v_tint.rgb * v_tint.a * pulse * 2.6;
    // 自发光物体的菲涅尔外扩, 增强"发光体"观感
    float fres = pow(1.0-max(dot(N,V),0.0), 2.5);
    col += v_tint.rgb * v_tint.a * fres * 1.8;

    if(u_echoRadius > 0.0){
        float d = distance(v_world.xz, u_echoOrigin.xz);
        float ring = exp(-pow((d-u_echoRadius)*0.30, 2.0));
        col += u_echoColor * ring * 1.1;
    }

    col = applyFog(col, v_world, -V);
    f_color = vec4(col, 1.0);
}
""".replace("__COMMON__", COMMON)

# ==========================================================================
# 植被 (实例化 + 风场 + alpha 裁剪)
# ==========================================================================
FOLIAGE_VS = """
#version 330 core
layout(location=0) in vec3 in_pos;
layout(location=1) in vec3 in_normal;
layout(location=2) in vec2 in_uv;
layout(location=3) in vec4 in_m0;
layout(location=4) in vec4 in_m1;
layout(location=5) in vec4 in_m2;
layout(location=6) in vec4 in_tint;

uniform mat4  u_viewProj;
uniform float u_time;
uniform float u_windStrength;

out vec3 v_world;
out vec3 v_normal;
out vec2 v_uv;
out vec4 v_tint;
out float v_height;

void main(){
    mat4 M = mat4(vec4(in_m0.xyz,0.0), vec4(in_m1.xyz,0.0), vec4(in_m2.xyz,0.0),
                  vec4(in_m0.w, in_m1.w, in_m2.w, 1.0));
    vec4 wp = M * vec4(in_pos, 1.0);

    // 顶部摆动幅度大, 根部固定
    float h = clamp(in_uv.y, 0.0, 1.0);
    float sway = h*h * u_windStrength;
    float ph = wp.x*0.16 + wp.z*0.21;
    wp.x += sin(u_time*1.35 + ph)*sway
          + sin(u_time*3.10 + ph*2.3)*sway*0.30;
    wp.z += cos(u_time*1.12 + ph*0.83)*sway*0.75;

    v_world  = wp.xyz;
    v_normal = normalize(mat3(in_m0.xyz, in_m1.xyz, in_m2.xyz) * in_normal);
    v_uv     = in_uv;
    v_tint   = in_tint;
    v_height = h;
    gl_Position = u_viewProj * wp;
}
"""

FOLIAGE_FS = """
#version 330 core
in vec3 v_world;
in vec3 v_normal;
in vec2 v_uv;
in vec4 v_tint;
in float v_height;
out vec4 f_color;

__COMMON__

uniform float u_time;
uniform vec3  u_echoOrigin;
uniform float u_echoRadius;
uniform vec3  u_echoColor;

void main(){
    // 草叶剪影: 越靠顶端越窄
    float halfW = 0.5*(1.0 - v_height*0.82);
    if(abs(v_uv.x-0.5) > halfW) discard;

    vec3 N = normalize(v_normal);
    // 双面光照
    if(dot(N, u_camPos-v_world) < 0.0) N = -N;
    // 法线上扬, 让草地整体接近地表受光, 避免一片死黑
    N = normalize(mix(N, vec3(0.0,1.0,0.0), 0.55));

    vec3 V = normalize(u_camPos - v_world);

    // 根部暗、尖端亮的渐变
    vec3 albedo = v_tint.rgb * (0.45 + 0.75*v_height);
    albedo *= 0.85 + 0.30*vnoise(v_world.xz*3.3);

    float NoL = dot(N, normalize(u_sunDir));
    float shadow = mix(1.0, sampleShadow(v_world, NoL), 0.65);

    vec3 col = shadeSurface(albedo, N, V, v_world, 0.85, 0.0, 0.55+0.45*v_height, shadow);

    // 次表面透光: 逆光时草叶透亮, 是植被出彩的关键
    float back = pow(max(dot(-V, normalize(u_sunDir)), 0.0), 3.0);
    col += albedo * u_sunColor * back * 0.85 * v_height;

    col += v_tint.rgb * v_tint.a * 2.2;

    if(u_echoRadius > 0.0){
        float d = distance(v_world.xz, u_echoOrigin.xz);
        float ring = exp(-pow((d-u_echoRadius)*0.30, 2.0));
        col += u_echoColor * ring * 1.5;
    }

    col = applyFog(col, v_world, -V);
    f_color = vec4(col, 1.0);
}
""".replace("__COMMON__", COMMON)

# ==========================================================================
# 水面
# ==========================================================================
WATER_VS = """
#version 330 core
layout(location=0) in vec3 in_pos;
uniform mat4 u_viewProj;
uniform float u_time;
out vec3 v_world;
void main(){
    vec3 p = in_pos;
    p.y += sin(p.x*0.09 + u_time*0.8)*0.10 + cos(p.z*0.11 - u_time*0.62)*0.09;
    v_world = p;
    gl_Position = u_viewProj * vec4(p, 1.0);
}
"""

WATER_FS = """
#version 330 core
in vec3 v_world;
out vec4 f_color;

__COMMON__

uniform float u_time;
uniform vec3  u_waterColor;
uniform vec3  u_waterDeep;

void main(){
    vec3 V = normalize(u_camPos - v_world);

    // 多层法线扰动模拟波纹
    vec2 p = v_world.xz;
    float n1 = fbm(p*0.16 + vec2(u_time*0.055, u_time*0.032), 3);
    float n2 = fbm(p*0.44 - vec2(u_time*0.085, u_time*0.061), 3);
    float e = 0.55;
    float hx = fbm((p+vec2(e,0))*0.16 + vec2(u_time*0.055,u_time*0.032), 3) - n1;
    float hz = fbm((p+vec2(0,e))*0.16 + vec2(u_time*0.055,u_time*0.032), 3) - n1;
    vec3 N = normalize(vec3(-hx*7.0, 1.0, -hz*7.0));
    N = normalize(N + vec3((n2-0.5)*0.28, 0.0, (n2-0.5)*0.28));

    float fres = pow(1.0 - max(dot(N,V),0.0), 4.0);
    fres = clamp(fres*0.92 + 0.045, 0.0, 1.0);

    vec3 deep = u_waterDeep;
    vec3 shallow = u_waterColor;
    vec3 body = mix(deep, shallow, clamp(n1*1.25, 0.0, 1.0));

    // 天空反射近似
    vec3 R = reflect(-V, N);
    vec3 skyRefl = mix(u_fogColor, u_ambientSky*1.35, clamp(R.y*0.5+0.5, 0.0, 1.0));

    vec3 col = mix(body, skyRefl, fres);

    // 高光
    vec3 L = normalize(u_sunDir);
    vec3 H = normalize(L+V);
    float spec = pow(max(dot(N,H),0.0), 380.0);
    col += u_sunColor * spec * 2.4;
    // 细碎闪光
    float sparkle = pow(max(dot(N,H),0.0), 60.0) * step(0.72, n2);
    col += u_sunColor * sparkle * 0.35;

    col = applyFog(col, v_world, -V);
    f_color = vec4(col, mix(0.78, 0.97, fres));
}
""".replace("__COMMON__", COMMON)

# ==========================================================================
# 阴影深度 pass
# ==========================================================================
SHADOW_VS = """
#version 330 core
layout(location=0) in vec3 in_pos;
uniform mat4 u_lightVP;
uniform mat4 u_model;
void main(){ gl_Position = u_lightVP * u_model * vec4(in_pos, 1.0); }
"""

SHADOW_INST_VS = """
#version 330 core
layout(location=0) in vec3 in_pos;
layout(location=1) in vec3 in_normal;
layout(location=2) in vec4 in_m0;
layout(location=3) in vec4 in_m1;
layout(location=4) in vec4 in_m2;
layout(location=5) in vec4 in_tint;
uniform mat4 u_lightVP;
void main(){
    mat4 M = mat4(vec4(in_m0.xyz,0.0), vec4(in_m1.xyz,0.0), vec4(in_m2.xyz,0.0),
                  vec4(in_m0.w, in_m1.w, in_m2.w, 1.0));
    gl_Position = u_lightVP * M * vec4(in_pos, 1.0);
}
"""

SHADOW_TERRAIN_VS = """
#version 330 core
layout(location=0) in vec3 in_pos;
layout(location=1) in vec3 in_normal;
layout(location=2) in vec3 in_albedo;
layout(location=3) in vec2 in_params;
uniform mat4 u_lightVP;
void main(){ gl_Position = u_lightVP * vec4(in_pos, 1.0); }
"""

SHADOW_FS = """
#version 330 core
void main(){ }
"""

# ==========================================================================
# 后处理
# ==========================================================================
FS_QUAD_VS = """
#version 330 core
layout(location=0) in vec2 in_pos;
out vec2 v_uv;
void main(){
    v_uv = in_pos*0.5+0.5;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

BRIGHT_FS = """
#version 330 core
in vec2 v_uv;
out vec4 f_color;
uniform sampler2D u_tex;
uniform float u_threshold;
uniform float u_softKnee;
void main(){
    vec3 c = texture(u_tex, v_uv).rgb;
    float br = max(c.r, max(c.g, c.b));
    float knee = u_threshold*u_softKnee + 1e-5;
    float soft = clamp(br - u_threshold + knee, 0.0, 2.0*knee);
    soft = soft*soft/(4.0*knee);
    float contrib = max(soft, br - u_threshold)/max(br, 1e-5);
    f_color = vec4(c*contrib, 1.0);
}
"""

BLUR_FS = """
#version 330 core
in vec2 v_uv;
out vec4 f_color;
uniform sampler2D u_tex;
uniform vec2 u_dir;        // (1/w,0) 或 (0,1/h)
void main(){
    // 9-tap 高斯, 利用线性采样折半
    float w0=0.227027, w1=0.316216, w2=0.070270, w3=0.008081;
    vec3 c = texture(u_tex, v_uv).rgb * w0;
    c += texture(u_tex, v_uv + u_dir*1.3846).rgb * w1;
    c += texture(u_tex, v_uv - u_dir*1.3846).rgb * w1;
    c += texture(u_tex, v_uv + u_dir*3.2308).rgb * w2;
    c += texture(u_tex, v_uv - u_dir*3.2308).rgb * w2;
    c += texture(u_tex, v_uv + u_dir*5.1765).rgb * w3;
    c += texture(u_tex, v_uv - u_dir*5.1765).rgb * w3;
    f_color = vec4(c, 1.0);
}
"""

COMPOSITE_FS = """
#version 330 core
in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_scene;
uniform sampler2D u_bloom;
uniform sampler2D u_depth;

uniform float u_bloomStrength;
uniform float u_exposure;
uniform float u_vignette;
uniform float u_grain;
uniform float u_time;
uniform float u_saturation;
uniform vec3  u_lift;
uniform vec3  u_gain;
uniform float u_style;

// 屏幕空间描边 (卡通模式)
uniform vec2  u_texel;
uniform float u_outline;
uniform float u_near;
uniform float u_far;

// 剧情用全屏效果
uniform float u_fadeAmount;   // 黑场
uniform vec3  u_fadeColor;
uniform float u_pulse;        // 心跳脉动 (回响能力)
uniform float u_desatRadial;  // 边缘去色 (收束逼近)

float linearizeDepth(float d){
    float z = d*2.0-1.0;
    return (2.0*u_near*u_far)/(u_far+u_near - z*(u_far-u_near));
}

// ACES filmic (Narkowicz 近似)
vec3 ACES(vec3 x){
    const float a=2.51, b=0.03, c=2.43, d=0.59, e=0.14;
    return clamp((x*(a*x+b))/(x*(c*x+d)+e), 0.0, 1.0);
}

void main(){
    vec3 col = texture(u_scene, v_uv).rgb;
    vec3 bloom = texture(u_bloom, v_uv).rgb;
    col += bloom * u_bloomStrength;

    // ---- 卡通描边: 深度不连续检测 ----
    if(u_outline > 0.001){
        float dc = linearizeDepth(texture(u_depth, v_uv).r);
        float d1 = linearizeDepth(texture(u_depth, v_uv+vec2( u_texel.x,0)).r);
        float d2 = linearizeDepth(texture(u_depth, v_uv+vec2(-u_texel.x,0)).r);
        float d3 = linearizeDepth(texture(u_depth, v_uv+vec2(0, u_texel.y)).r);
        float d4 = linearizeDepth(texture(u_depth, v_uv+vec2(0,-u_texel.y)).r);
        float edge = abs(d1-dc)+abs(d2-dc)+abs(d3-dc)+abs(d4-dc);
        edge = smoothstep(0.035*dc, 0.16*dc, edge);
        col = mix(col, col*0.14, edge*u_outline);
    }

    // ---- 曝光 + 色调映射 ----
    col *= u_exposure;
    col = ACES(col);

    // ---- 分级: lift/gain + 饱和度 ----
    col = col*u_gain + u_lift;
    float lum = dot(col, vec3(0.2126,0.7152,0.0722));
    col = mix(vec3(lum), col, u_saturation);

    // ---- 径向去色: 收束的视觉隐喻 ----
    if(u_desatRadial > 0.001){
        float r = length(v_uv-0.5)*1.4142;
        float m = smoothstep(0.25, 1.0, r)*u_desatRadial;
        col = mix(col, vec3(dot(col, vec3(0.299,0.587,0.114)))*0.82, m);
    }

    // ---- 回响脉冲: 屏幕轻微呼吸 ----
    if(u_pulse > 0.001){
        float r = length(v_uv-0.5);
        col += vec3(0.16,0.42,0.40) * u_pulse * exp(-pow((r-0.34)*4.2,2.0));
    }

    // ---- 暗角 ----
    vec2 q = v_uv - 0.5;
    float vig = 1.0 - dot(q,q)*u_vignette;
    col *= clamp(vig, 0.0, 1.0);

    // ---- 胶片颗粒 ----
    if(u_grain > 0.0001){
        float n = fract(sin(dot(v_uv*vec2(1.0,1.3) + u_time*0.37, vec2(12.9898,78.233)))*43758.5453);
        col += (n-0.5)*u_grain;
    }

    // ---- 剧情黑场 ----
    col = mix(col, u_fadeColor, clamp(u_fadeAmount,0.0,1.0));

    f_color = vec4(col, 1.0);
}
"""

FXAA_FS = """
#version 330 core
in vec2 v_uv;
out vec4 f_color;
uniform sampler2D u_tex;
uniform vec2 u_texel;

float luma(vec3 c){ return dot(c, vec3(0.299,0.587,0.114)); }

void main(){
    vec3 rgbM = texture(u_tex, v_uv).rgb;
    vec3 rgbNW = texture(u_tex, v_uv+vec2(-1,-1)*u_texel).rgb;
    vec3 rgbNE = texture(u_tex, v_uv+vec2( 1,-1)*u_texel).rgb;
    vec3 rgbSW = texture(u_tex, v_uv+vec2(-1, 1)*u_texel).rgb;
    vec3 rgbSE = texture(u_tex, v_uv+vec2( 1, 1)*u_texel).rgb;

    float lM=luma(rgbM), lNW=luma(rgbNW), lNE=luma(rgbNE), lSW=luma(rgbSW), lSE=luma(rgbSE);
    float lMin = min(lM, min(min(lNW,lNE), min(lSW,lSE)));
    float lMax = max(lM, max(max(lNW,lNE), max(lSW,lSE)));

    if(lMax - lMin < max(0.0312, lMax*0.125)){ f_color = vec4(rgbM,1.0); return; }

    vec2 dir = vec2(-((lNW+lNE)-(lSW+lSE)), ((lNW+lSW)-(lNE+lSE)));
    float reduce = max((lNW+lNE+lSW+lSE)*0.25*0.125, 1.0/128.0);
    float rcpMin = 1.0/(min(abs(dir.x),abs(dir.y))+reduce);
    dir = clamp(dir*rcpMin, vec2(-8.0), vec2(8.0))*u_texel;

    vec3 rgbA = 0.5*(texture(u_tex, v_uv+dir*(1.0/3.0-0.5)).rgb
                   + texture(u_tex, v_uv+dir*(2.0/3.0-0.5)).rgb);
    vec3 rgbB = rgbA*0.5 + 0.25*(texture(u_tex, v_uv-dir*0.5).rgb
                               + texture(u_tex, v_uv+dir*0.5).rgb);
    float lB = luma(rgbB);
    f_color = vec4((lB < lMin || lB > lMax) ? rgbA : rgbB, 1.0);
}
"""

# ==========================================================================
# UI (正交, 纹理四边形 / 纯色)
# ==========================================================================
UI_VS = """
#version 330 core
layout(location=0) in vec2 in_pos;
layout(location=1) in vec2 in_uv;
layout(location=2) in vec4 in_color;
uniform mat4 u_proj;
out vec2 v_uv;
out vec4 v_color;
void main(){
    v_uv = in_uv;
    v_color = in_color;
    gl_Position = u_proj * vec4(in_pos, 0.0, 1.0);
}
"""

UI_FS = """
#version 330 core
in vec2 v_uv;
in vec4 v_color;
out vec4 f_color;
uniform sampler2D u_tex;
uniform int u_mode;      // 0=纯色 1=字形(r通道当alpha) 2=普通纹理
void main(){
    if(u_mode == 0){
        f_color = v_color;
    } else if(u_mode == 1){
        float a = texture(u_tex, v_uv).r;
        f_color = vec4(v_color.rgb, v_color.a*a);
    } else {
        vec4 t = texture(u_tex, v_uv);
        f_color = t*v_color;
    }
}
"""
