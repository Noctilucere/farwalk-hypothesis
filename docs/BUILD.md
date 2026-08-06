# 构建与打包手册

## 1. 开发环境

### 1.1 推荐 Python

使用 WorkBuddy 隔离环境或任何 Python 3.10+。已通过 Python 3.13.12 验证。

### 1.2 安装依赖

```powershell
python -m venv C:\path\to\.venv
.venv\Scripts\activate
pip install -i https://mirrors.tencent.com/pypi/simple `
    moderngl glfw numpy pillow pyinstaller
```

本仓库未使用 `requirements.txt`，因为依赖数量少且固定。

## 2. 运行

```bash
python run.py [options]
```

| 选项 | 含义 |
|---|---|
| `--low` | 低画质：1024 阴影、稀疏植被、低后期 |
| `--medium` | 中画质：2048 阴影、中等植被 (默认) |
| `--high` | 高画质：2048 阴影、更密植被、完整后期 |
| `--fullscreen` | 无边框全屏 |
| `--size=1280x720` | 窗口分辨率 |

示例：

```bash
python run.py --size=1280x720 --medium
```

## 3. 测试

### 3.1 纯逻辑剧情测试

不开窗口、不建世界，直接驱动 `StoryState` 走完全部 8 章。

```bash
python tools/story_walk.py
```

成功输出：

```text
[walk] steps 39/39
[result] PASS 全线可通关
```

### 3.2 渲染+剧情烟雾测试

在隐藏窗口中跑完 8 章，验证渲染管线与事件触发。

```bash
python tools/smoke_test.py --seconds=420 --quality=medium
```

参数：

- `--seconds=N`：最大运行秒数
- `--quality=low|medium|high`
- `--no-warp`：关闭机器人传送兜底

输出示例：

```text
[build] 2.4s  chunks=144 scatter_groups=15 ...
[run] frames=... avg 75.2 fps  warps=23
[story] chapter=8 steps=39/39 fragments=7/12 finished=True
[result] PASS
```

截图保存到 `tools/shots/`。

## 4. 打包 exe

### 4.1 生成图标

```bash
python tools/make_icon.py
```

产物：`assets/icon.ico`、`assets/icon.png`。

### 4.2 PyInstaller

```bash
python -m PyInstaller build.spec --clean --noconfirm
```

配置要点：

- `run.py` 为入口；它通过 `sys._MEIPASS` 自动识别单文件模式。
- `src/` 源码树作为 data 目录打包到 `_MEIPASS/src`，运行时仍可 `import src.xxx`。
- `hiddenimports` 包含 `glfw`、`moderngl`、`numpy`、`PIL` 的关键子模块。
- 中文字体不打包，运行时从 `%WINDIR%/Fonts` 读取。
- 产物为 `dist/远行假设.exe` (单文件)。

### 4.3 验证 exe

```powershell
.\dist\远行假设.exe --medium --size=1280x720
```

若启动黑屏或闪退：

1. 检查显卡驱动是否支持 OpenGL 3.3 Core。
2. 检查系统是否安装中文字体。
3. 以 `--low` 重新启动。

## 5. 目录结构说明

```
renwai/
├── run.py          # 入口，自动处理 _MEIPASS
├── build.spec      # PyInstaller 配置
├── assets/
│   ├── icon.ico    # 程序图标
│   ├── icon.png    # 大图标
│   └── fonts/      # 空目录；运行时使用系统字体
├── src/            # 全部源码
└── tools/          # 测试与工具脚本
```

## 6. 常见问题

**Q: 打包后中文字体不显示？**
A: 本 Demo 默认从系统字体加载，请确保 Windows 已安装 `msyh.ttc` 或 `simhei.ttf`。也可在 `src/engine/text.py` 的 `FONT_CANDIDATES` 列表最前面加入自定义字体路径。

**Q: 运行提示 `glfw not found`？**
A: 安装依赖时 `pip install glfw`，或在打包环境中安装 PyInstaller 所需的 `hiddenimports`。

**Q: 如何调整画质预设？**
A: 在 `src/game/main.py` 的 `QUALITY` 字典中修改 `shadow_size`、`scatter_density`、`post` 等参数。

## 7. 发布 checklist

- [ ] 运行 `tools/story_walk.py` 通过
- [ ] 运行 `tools/smoke_test.py` 通过
- [ ] 执行 PyInstaller 成功
- [ ] 在干净 Windows 环境启动 exe 无报错
- [ ] 确认 `dist/远行假设/远行假设.exe` 图标正确
