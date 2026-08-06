# 渲染管线说明

## 1. 管线概览

```
阴影 Pass  (2048² 深度图)
    │
    ▼
HDR 主 Pass  (RGBA16F, 1280×720/1600×900)
    │
    ▼
后处理链
    ├── Bloom (阈值提取 → 高斯模糊)
    ├── ACES 色调映射
    ├── FXAA
    ├── 暗角 (vignette)
    ├── 描边 (sobel 深度/法线边缘)
    └── 颗粒 (film grain)
    │
    ▼
屏幕输出
```

## 2. 阴影 Pass

- 光源：单一方向光 (阳光)，正交投影。
- 阴影图分辨率：`2048×2048` (高/中) / `1024×1024` (低)。
- 深度绘制：地形 + 实体 (实例化)。
- 主着色器采样 `u_shadowMap` 做 PCF3×3 软阴影。

阴影 pass 对 VAO 做了精简：只绑定 `in_pos`，跳过法线/颜色/参数，避免 ModernGL 属性映射冲突。

## 3. HDR 主 Pass

### 3.1 地形 (Terrain)

输入：高度图由 CPU 程序化生成，顶点包含位置、法线、反照色、参数 (粗糙度/金属度/风格权重)。

顶点着色器根据区域权重 blend 六种氛围：

- `wilds` 无名荒原
- `blackstone` 黑石祭址
- `lostland` 银蓝苔原
- `silenthall` 无声殿
- `mutezone` 消音地带
- `mirror` 镜之境

片段着色器：

- 基础漫反射
- 法线扰动
- 粗糙度/金属度 PBR 近似
- `u_style` 插值 PBR ↔ NPR
- 阴影采样
- 雾效 (指数高度雾 + 距离雾)

### 3.2 实体 (InstancedMesh)

同一几何体使用实例化矩阵批量渲染：

```
in_pos     vec3
in_normal  vec3
in_tint    vec4
in_m0/m1/m2 vec4  (实例化矩阵的前三行)
```

实例化数据 `float32[N, 16]` 按 `(m0, m1, m2, tint)` 布局上传。

实体类型：

- NPC：直立/爬行/鸟类/水晶/软体/暗影
- 可互动物：石碑、遗迹、刻痕
- 收集品：心跳残片

### 3.3 水体 (Water)

- 透明平面，高度 `WATER_LEVEL = 2.2`
- 片段着色器：反射近似、焦散、菲涅尔
- 与地形相接处做深度混合

### 3.4 天空 (Sky)

- 方向光 + 散射渐变
- 太阳盘
- 简单云层

## 4. 后处理

### 4.1 Bloom

1. 阈值提取：亮度 > `u_bloom_threshold` 的像素。
2. 下采样 3-4 级。
3. 高斯模糊 (水平和垂直分离)。
4. 上采样叠加回原图。

### 4.2 ACES 色调映射

```glsl
vec3 aces(vec3 x) { ... }
```

将 HDR 线性色彩压缩到 sRGB。

### 4.3 FXAA

基于亮度差检测边缘，做子像素混合抗锯齿。

### 4.4 风格化效果

- **暗角**：屏幕四角降低亮度。
- **描边**：对深度/法线 buffer 做 Sobel，边缘叠加黑色。
- **颗粒**：时间噪声叠加，增强胶片感。

## 5. PBR ↔ NPR 混合

每个片段根据 `u_style` 在写实与卡通之间插值：

| 分量 | PBR (style=0) | NPR (style=1) |
|---|---|---|
| 漫反射 | 能量守恒 Lambert | 硬切 banded diffuse |
| 高光 | GGX-ish | 锐化边缘光 |
| 阴影 | PCF 软阴影 | 二值硬阴影 |
| 描边 | 无 | 屏幕空间边缘 |
| 雾 | 物理指数 | 大气色块 |

区域氛围 (`REGION_MOOD`) 驱动 `u_style`：

- `wilds` / `lostland`：偏写实
- `silenthall` / `mirror`：偏 NPR
- 边界处做指数阻尼插值

## 6. UI 渲染

- 所有 UI 在 HDR pass 之后用屏幕空间三角形绘制。
- 中文字体使用动态图集：`2048×2048 R8`，货架式装箱。
- HUD：罗盘、体力条、对话窗口、章节卡、地图、手记。

## 7. 调试与性能

- F1 显示 FPS、draw calls、instance groups、chunk 数。
- `tools/smoke_test.py` 可无人值守跑完并截图。
- 主要性能热点：uniform 去重、视锥剔除、实例化合批。
