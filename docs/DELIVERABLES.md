# 交付清单

## 已完成

- [x] 完整 8 章主线剧情（39 个步骤）可通关
- [x] 6 个开放世界区域 + 程序化地形 + 植被散布
- [x] 14 位剧情角色 + 16 个可互动物 + 12 个收集品
- [x] 自研 ModernGL 渲染器：阴影、HDR、Bloom、ACES、FXAA、描边、颗粒
- [x] 第三人称探索/攀爬/滑翔/体力/收集/对话系统
- [x] 区域氛围混合（PBR↔NPR 插值）
- [x] 中文 UI/HUD/地图/手记
- [x] 存档/读档
- [x] Windows 原生 exe 打包
- [x] 完整文档集

## 交付文件

| 文件/目录 | 说明 |
|---|---|
| `dist/远行假设.exe` | 可直接运行的 Windows 原生可执行文件 (≈28MB) |
| `run.py` | 源码启动入口 |
| `build.spec` | PyInstaller 打包配置 |
| `src/` | 全部源代码 |
| `docs/` | 技术文档、设计文档、构建手册 |
| `tools/shots/` | 章节卡与结局截图 |
| `tools/story_walk.py` | 纯逻辑剧情通关校验 |
| `tools/smoke_test.py` | 渲染+剧情全流程无人值守测试 |

## 验证结果

### 1. 纯逻辑剧情测试

```bash
python tools/story_walk.py
```

输出：

```text
[walk] steps 39/39
[walk] chapters entered=[1, 2, 3, 4, 5, 6, 7, 8]
[walk] chapters ended  =[1, 2, 3, 4, 5, 6, 7, 8]
[result] PASS 全线可通关
```

### 2. 渲染+剧情烟雾测试

```bash
python tools/smoke_test.py --seconds=90 --quality=medium --verbose
```

输出：

```text
[build] 2.7s  chunks=144 scatter_groups=15 npc=14 inter=16 coll=12
[progress] frame=000900 chapter=3 step=10/39 warp=9 obj=talk:falsifier pos=(-144.7,-265.1)
[progress] frame=001800 chapter=6 step=25/39 warp=23 obj=reach:mutezone pos=(392.1,376.0)
[progress] frame=002700 chapter=8 step=38/39 warp=34 obj=None:None pos=(10.4,-392.6)
[run] frames=2716 72.0s  avg 37.7 fps  warps=34
[story] chapter=8 steps=39/39 fragments=7/12 finished=True
[regions] ['blackstone', 'lostland', 'mirror', 'mutezone', 'silenthall', 'wilds']
[chapters] [1, 2, 3, 4, 5, 6, 7, 8]
[result] PASS
```

### 3. exe 启动验证

打包产物 `dist/远行假设.exe` 可在 Windows 上启动并进入主循环（测试使用 `--medium --size=640x360`）。

## 已知限制

- 中文字体依赖系统字体（msyh/simhei/deng 等），不随包分发。
- 5/12 个心跳残片为开放探索可选，主线必得 7 个。
- 音效暂未实现，预留接口。
- 机器人测试使用"剧情速通"传送策略，正式游戏仍保留完整移动/攀爬/滑翔体验。
