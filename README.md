# The Farwalk Hypothesis (远行假设) — powered by the SharpGLow engine

> A single-player 3D open-world narrative game built on a from-scratch OpenGL engine. The
> shipped build is powered by **SharpGLow**, a C# / OpenTK 4 rewrite of the original
> Python / ModernGL engine. Gameplay borrows *a little* from Genshin Impact. Some models
> and textures are placeholders / AI-generated. Bug reports welcome.

This repository contains **two things**:

1. **The Farwalk Hypothesis (远行假设)** — the game: a 960×960 m procedurally generated
   open world split into six themed regions with hard boundaries, a third-person player,
   instanced foliage, and a chapter-driven narrative state machine.
2. **SharpGLow** — the engine: a self-contained C# + OpenTK 4 renderer on an OpenGL 3.3
   core profile that the game runs on. It is published both *bundled with the game* and
   *on its own* as a reusable engine.

> **Legacy note.** The original Python + ModernGL engine is preserved in this repo under
> `src/` (Python) and `tools/` for reference. The actively developed, shipped engine is
> the C# SharpGLow rewrite under `src/Farwalk/`.

---

## 1. Game — The Farwalk Hypothesis

### Overview

*The Farwalk Hypothesis* is a technical showcase of procedural world generation and
real-time OpenGL rendering wrapped in a short narrative:

| Area | Description |
| --- | --- |
| **Engine** | Self-written renderer — originally Python + ModernGL, now the C# **SharpGLow** engine (see §2) |
| **World** | 960×960 m continuous terrain, 6 regions with **hard boundaries (no blending)** — each region owns distinct height fields, albedo, fog and sky |
| **Characters** | Procedural third-person player (capsule humanoid) with walk / run / jump / glide |
| **Story** | Chapter-driven quest (10 chapters, 30+ dialogue nodes), collectible system, gated progression |
| **Distribution** | Standalone Windows exe (no .NET / Python needed); source builds cross-platform |

### World & Regions

The terrain is a 960 m × 960 m heightfield (`CELL = 2.5`, `CELLS = 384`). Six regions are
placed around the map and selected by `argmax` of Perlin-driven region weights (hard
boundaries, no smooth blend):

| Region | Position (x, z) | Radius | Theme |
| --- | --- | --- | --- |
| `wilds` | (0, 60) | 300 | Open wilds (grass / trees / rocks) |
| `blackstone` | (-290, -230) | 190 | Black stone |
| `lostland` | (300, -215) | 200 | Lost land |
| `silenthall` | (320, 265) | 185 | Silent hall |
| `mutezone` | (-315, 275) | 195 | Mute zone |
| `mirror` | (-20, -400) | 165 | Mirror |

Water level is `WATER_LEVEL = 2.2`; scatter sampling skips points below water and steep
slopes.

### Controls

| Key | Action |
| --- | --- |
| WASD | Move |
| LShift | Sprint |
| Space | Jump / glide |
| E | Interact |
| Mouse | Look (orbit camera); wheel zooms |
| F1 | Toggle debug / help |
| F11 | Fullscreen |
| Esc | Quit |

> The legacy Python build additionally exposed Q (echo scan), C/M/Tab/J (character / map /
> journal), F5 (save) and `=`/`-` (mouse sensitivity). Those UI panels are not part of the
> current C# build.

---

## 2. Engine — SharpGLow (C# / OpenTK)

**SharpGLow** is the C# engine rewrite of *The Farwalk Hypothesis*. The original Python /
ModernGL engine has been fully ported to **C# + OpenTK 4** on an **OpenGL 3.3 Core
Profile**, with performance-oriented improvements (instanced rendering, procedural scatter,
region-based world generation).

### Tech Stack

| Concern | Choice |
| --- | --- |
| Language | C# 13 / .NET 9.0 |
| Window / GL | OpenTK 4.8.2 (OpenGL 3.3 core profile) |
| Shaders | GLSL `#version 330 core` |
| Noise | Perlin / FBM (Fbm2 / Fbm3) in `Math3D` |
| Packaging | Single-file self-contained `dotnet publish` |

### Features

- **Procedural world** — Perlin/FBM noise heightfield (960 m, 2.5 m cells) with six
  regions selected by `argmax` region weights (hard boundaries).
- **Instanced rendering** — grass blades, trees and rocks drawn in a few draw calls via a
  per-instance 4×4 model matrix + per-instance RGB tint (`Engine/Instanced.cs`).
- **Procedural meshes** — capsule body, tapered grass blade, terrain heightfield, and a
  humanoid character, all generated in code (`World/MeshGen.cs`).
- **Hemisphere lighting + exponential fog** — GLSL 330 shaders with sun direction, sky /
  ground ambient term, and distance fog (`Engine/Renderer.cs`).
- **Third-person orbit camera** — mouse-look, scroll zoom, smoothed follow.
- **Story state machine** — dialogue nodes, quest gates and chapter progression
  (`Game/Story.cs`, `Game/StoryState.cs`).

### Project Structure

```
src/Farwalk/
  Farwalk.csproj            # net9.0, OpenTK 4.8.2, Exe
  Program.cs                # GameApp : GameWindow — main loop, input, HUD
  Engine/
    Math3D.cs               # Vec2/3/4, Mat4, Perlin noise (Fbm2/Fbm3), look_at, perspective
    Renderer.cs             # Shader helper + terrain/object GLSL 330 shaders
    Instanced.cs            # InstancedMesh — per-instance matrix + tint VAO
  World/
    Terrain.cs              # TerrainConfig (6 regions), WorldGen, Terrain (960 m)
    MeshGen.cs              # procedural meshes: Capsule, GrassBlade, Character, Merge, Transform
    Scatter.cs              # ScatterGen — samples ground, builds grass/tree/rock meshes
  Game/
    Camera.cs               # OrbitCamera (third-person, mouse + scroll)
    Player.cs               # movement / sprint / jump
    Story.cs                # StoryData — dialogue nodes + chapter list
    StoryState.cs           # quest gates + chapter progression
  UI/  Data/                # auxiliary UI / data helpers
dist/                       # published build output (single-file exe)
```

### Build

Requirements: .NET 9 SDK (`dotnet --version` ≥ 9.0).

```bash
# Restore + build the Farwalk project
dotnet build src/Farwalk/Farwalk.csproj -c Release

# Publish a self-contained single-file executable for Windows x64
dotnet publish src/Farwalk/Farwalk.csproj -c Release -r win-x64 --self-contained \
  -p:PublishSingleFile=true \
  -p:IncludeNativeLibrariesForSelfExtract=true \
  -o dist
```

The published `dist/Farwalk.exe` is ~76 MB and needs **no installed .NET runtime** and
**no Python environment**.

> Cross-platform note: the engine targets `win-x64` for the single-file build. To run on
> Linux/macOS, drop `-r win-x64` and `--self-contained` and run on a machine with the
> .NET 9 runtime + an OpenGL 3.3 capable driver.

### Run

```bash
dist/Farwalk.exe
```

The window opens at **1920 × 1080** on an OpenGL 3.3 context. Press **Esc** to quit.

---

## 3. Downloads / Releases

This project is published as **two separate packages**:

| Package | Tag | Contents | Run |
| --- | --- | --- | --- |
| **The Farwalk Hypothesis — game + SharpGLow engine** | `v2.0.0` | Full game built on the new engine, plus `dist/Farwalk.exe` | Download `dist/Farwalk.exe`, double-click (no .NET / Python needed) |
| **SharpGLow engine (standalone)** | `sharpglow-v1.0.0` | Engine source under `src/Farwalk/` only — a reusable renderer / world / scatter / camera / story framework | `dotnet build src/Farwalk/Farwalk.csproj -c Release`, or embed the modules in your own project |

Both packages are **non-destructive** updates: the legacy Python engine (`src/` Python,
`tools/`, `assets/`, `docs/`) and all previously published releases remain in the
repository.

---

## 4. Legacy Python engine (reference)

The original engine (`Python + ModernGL`) is preserved for reference. It is more
feature-complete than the current C# build and includes GPU Linear Blend Skinning (LBS), a
2048² shadow map, post-processing (bloom / ACES / FXAA), 8 chapters with 146 dialogue
nodes, a portal system, world map, achievements and an in-game journal.

### Rendering pipeline (legacy)

```
scene → [shadow pass 2048 depth] → [sky pass] → [terrain] → [instanced objects]
     → [skinned meshes] → [foliage] → [water] → scene FBO
     → post: bloom (separable gaussian) → composite (exposure/ACES/grading)
     → FXAA → default framebuffer
```

### Build & run (legacy)

Requirements: Python 3.13+, ModernGL, glfw, numpy, Pillow; an OpenGL 3.3+ GPU.

```bash
git clone <repo> && cd <repo>
python -m venv .venv
.venv/Scripts/pip install moderngl glfw numpy Pillow
python run.py                    # default 1920x1080 high
python run.py --medium | --low | --fullscreen | --size=1280x720
```

The legacy standalone Windows build was `dist/远行假设.exe` (~100 MB).

### Project layout (legacy)

```
src/
  data/     story data, NPCs, landmarks, achievements, version
  engine/   math3d, mesh, gltf, skin, renderer, shaders, camera
  game/     main loop, player, entities, story_state
  ui/       HUD, text, panels, loading, menus, map
  world/    terrain, scatter (24 object types)
tools/      story_walk, smoke_test, packaging, push scripts
assets/
  models/   AI glb character models
  textures/ baked tile textures (brick/stone/plank/slab)
  refs/     AI portrait art + model previews
docs/       architecture, build, rendering, GDD, story docs
```

### Testing (legacy)

```bash
python tools/story_walk.py                # logic-only full-play regression (no window)
python tools/smoke_test.py --seconds=80   # headless e2e, saves 9 screenshots to tools/shots/
```

---

## 5. Porting notes (Python ModernGL → C# OpenTK)

The original engine was fully re-implemented in C#:

| Module | Python | SharpGLow (C#) |
| --- | --- | --- |
| Math | `math3d.py` | `Engine/Math3D.cs` |
| Mesh | `mesh.py` | `World/MeshGen.cs` |
| Terrain | `terrain.py` | `World/Terrain.cs` |
| Renderer | `renderer.py` + `shaders.py` | `Engine/Renderer.cs` (GLSL inlined) |
| Camera | `camera.py` | `Game/Camera.cs` |
| Player | `player.py` | `Game/Player.cs` |
| Story | `data/story.py` + `story_state.py` | `Game/Story.cs` + `StoryState.cs` |
| Main loop | `game/main.py` | `Program.cs` |

Optimizations added during the port: instanced scatter rendering, region-based world
generation, and a single-file self-contained publish.

---

## 6. Known limitations

- Windows-tested only for the single-file build; other platforms untested.
- The C# engine is a streamlined port: it ships terrain, instanced scatter, a procedural
  character, hemisphere lighting + fog, and the story state machine, but does **not** yet
  include the legacy Python build's shadows, post-processing, GPU skinning, portals, map /
  journal UI, or achievements.
- Legacy Python build: cloud AI 3D quota is limited (≈5 generations/day); texture tiles are
  baked once by `tools/gen_textures.py` (re-run to regenerate).
- The 76 MB `dist/Farwalk.exe` exceeds GitHub's 50 MB *recommended* file size but is below
  the 100 MB hard limit.

---

## 7. Acknowledgements

- Tencent Hunyuan3D — free character 3D generation API
- ModernGL / GLFW — Python OpenGL bindings & windowing
- OpenTK — .NET OpenGL / windowing bindings

---

## 8. License & Author

Game & engine by **Noctilucere (芋泥P)** — independent music producer, illustrator &
programmer. This is the playable demo of *The Farwalk Hypothesis* (formerly 人外论 · 谁).

Open-sourced at
[Noctilucere/farwalk-hypothesis](https://github.com/Noctilucere/farwalk-hypothesis).

> *Behind every question stands another question.*
