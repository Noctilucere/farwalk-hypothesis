# 技术架构

## 1. 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                       run.py 启动入口                         │
└─────────────────────────┬───────────────────────────────────┘
┌─────────────────────────┴───────────────────────────────────┐
│                     Game 主循环 (src/game/main.py)             │
│  状态机: MENU -> LOADING -> PLAY -> (JOURNAL/MAP/PAUSE) -> ENDING│
└──┬────────────┬────────────┬────────────┬─────────────────────┘
   │            │            │            │
   ▼            ▼            ▼            ▼
StoryState   Player    EntityWorld   Renderer + Terrain
(剧情闸门)  (控制器)    (NPC/刻痕)    (渲染管线)
```

## 2. 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| `src.data.story` | `story.py` | 区域、角色、任务、对话、收集品、结局数据 |
| `src.engine.renderer` | `renderer.py` | 渲染器封装：VAO/UBO/纹理/FBO/实例化/统一 uniform 缓存 |
| `src.engine.shaders` | `shaders.py` | GLSL 150：深度、地形、物体、水体、天空、后期 |
| `src.engine.camera` | `camera.py` | 第三人称轨道相机 + 演出机位 + 地形规避 |
| `src.engine.math3d` | `math3d.py` | vec3/vec4/矩阵/四元数/Frustum/阻尼/噪声 |
| `src.engine.text` | `text.py` | 动态中文字形图集 (2048² R8) |
| `src.engine.mesh` | `mesh.py` | 基础几何体：立方体、球、胶囊、锥、柱、地形 quad |
| `src.game.main` | `main.py` | 主循环、输入、状态机、HUD、存档、章节卡 |
| `src.game.player` | `player.py` | 第三人称移动、跳跃/攀爬/滑翔、体力、回响 |
| `src.game.entities` | `entities.py` | NPC/可互动物/收集品 的放置、实例化渲染、交互 |
| `src.game.story_state` | `story_state.py` | 章节/任务/对话/闸门的推进与事件通知 |
| `src.ui.hud` | `hud.py` | 罗盘、体力、对话、章节卡、地图、手记、暂停菜单 |
| `src.ui.draw` | `draw.py` | 2D 绘制：矩形、圆角、线、渐变 |
| `src.world.terrain` | `terrain.py` | 程序化地形生成、区域影响场、chunk 剔除 |
| `src.world.scatter` | `scatter.py` | 程序化植被/岩石散布、LOD/视距裁剪 |

## 3. 核心数据结构

### 3.1 世界坐标

- 地形尺寸：`SIZE = 960.0` 米
- Chunk 数量：`CHUNKS = 12`，单块边长 `SIZE / CHUNKS = 80.0` 米
- 单个 mesh 网格：`CELLS = 384`，`CELL = SIZE / CELLS = 2.5` 米
- 水体高度：`WATER_LEVEL = 2.2`

### 3.2 玩家

- 位置 `pos`、速度 `vel`
- 属性：`stamina`、`exhausted`、`echo_unlocked`、`echo_radius`
- 状态：地面/跳跃/滑翔/攀爬

### 3.3 剧情状态机

- `chapter`: 0-7 对应 8 章
- `gates`: 从对话链推导的 (step_id, node_id) 列表
- `gate_i`: 当前闸门索引
- `cursor`: 当前对话节点 id
- `waiting`: 是否暂停对话等待玩家完成世界事件
- `events`: 已发生事件集合 `(kind, target)`

## 4. 关键流程

### 4.1 章节推进

```
begin(chapter)
  -> 显示 chapter_card
  -> 从 chN_01 开始对话
  -> on_end 含 quest 的节点即"闸门"
  -> 闸门满足条件后继续对话
  -> 对话链结束 -> chapter_end -> 下一章
```

### 4.2 玩家与世界交互

```
玩家移动 -> _world_notify -> notify("reach", region)
按下 E -> entities.nearest -> story.interact(npc/inter/coll)
按下 Q -> trigger_echo -> 波掠过 inter -> notify("echo", id)
```

### 4.3 存档

```python
save_path = %APPDATA%/FarwalkHypothesis/save.json
```

存档包含：章节、闸门、光标、flag、收集品、事件、区域、玩家位置/体力/解锁能力。读档后自动恢复世界实体状态。

## 5. 性能设计

- **实例化渲染**：同一 mesh 的多实例合并为一次 draw call。
- **统一 uniform 去重**：`_apply_common` 通过 `frame_id + program id` 缓存，避免每 chunk/每组重复设置。
- **视锥剔除**：每帧用 `Frustum.sphere_visible` 剔除远处 chunk 与实体组。
- **距离裁剪**：地形渲染 620m，阴影 170m。
- **LOD**：散布系统按距离切换密度与实例数量。

## 6. 扩展点

- 新章节：在 `story.py` 添加 QUESTS + DIALOGUES，无需改代码。
- 新区域：修改 `REGIONS` 与 `REGION_POS`/`REGION_MOOD`。
- 新角色/收集品：在 `NPCS`/`COLLECTIBLES` 中定义，由 `EntityWorld` 自动布点。
- 新着色器：在 `shaders.py` 添加，通过 `Renderer` 的 `prepare_*` 方法绑定。
