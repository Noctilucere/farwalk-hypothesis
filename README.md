# SharpGLow

**SharpGLow** is the C# engine rewrite of *《远行假设》 (The Farwalk Hypothesis)* — an  
open-world narrative game. The original Python / ModernGL engine has been fully ported  
to **C# + OpenTK 4** on an **OpenGL 3.3 Core Profile**, with performance-oriented  
improvements (instanced rendering, procedural scatter, region-based world generation).

---

## Overview

SharpGLow renders a 960 m × 960 m procedurally generated world split into six themed  
regions with hard boundaries, a third-person player character, instanced grass / trees /  
rocks, and a chapter-driven narrative state machine. The whole engine is a single  
self-contained executable with no external asset files — all meshes and shaders are  
generated at runtime.

### Features

- **Procedural world** — Perlin/FBM noise heightfield (960 m, 2.5 m cells) with six  
  regions selected by `argmax` region weights (no seamless blending, hard boundaries).
- **Instanced rendering** — grass blades, trees and rocks are drawn in a few draw calls  
  via a per-instance 4×4 model matrix + per-instance RGB tint (`Engine/Instanced.cs`).
- **Procedural meshes** — capsule body, tapered grass blade, terrain heightfield, and a  
  humanoid character, all generated in code (`World/MeshGen.cs`).
- **Hemisphere lighting + exponential fog** — GLSL 330 shaders with sun direction, sky /  
  ground ambient term, and distance fog (`Engine/Renderer.cs`).
- **Third-person orbit camera** — mouse-look, scroll zoom, smoothed follow.
- **Story state machine** — dialogue nodes, quest gates and chapter progression  
  (`Game/Story.cs`, `Game/StoryState.cs`).

---

## Tech Stack

| Concern     | Choice                                      |
| ----------- | ------------------------------------------- |
| Language    | C# 13 / .NET 9.0                            |
| Window / GL | OpenTK 4.8.2 (OpenGL 3.3 core profile)      |
| Shaders     | GLSL `#version 330 core`                    |
| Noise       | Perlin / FBM (Fbm2 / Fbm3) in `Math3D`      |
| Packaging   | Single-file self-contained `dotnet publish` |

---

## Project Structure

```
SharpGLow/
  SharpGlow.sln
  README.md
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
  build_output/               # verified latest build (see note below)
```

---

## Build

Requirements: .NET 9 SDK (`dotnet --version` ≥ 9.0).

From the repository root:

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

---

## Run

```bash
# From the published output directory
dist/Farwalk.exe
```

The window opens at **1920 × 1080** on an OpenGL 3.3 context. Press **Esc** to quit.

---

## World & Regions

The terrain is a 960 m × 960 m heightfield (`TerrainConfig.SIZE = CELL * CELLS`,  
`CELL = 2.5`, `CELLS = 384`). Six regions are placed around the map and selected by  
`argmax` of Perlin-driven region weights:

| Region       | Position (x, z) | Radius | Theme                              |
| ------------ | --------------- | ------ | ---------------------------------- |
| `wilds`      | (0, 60)         | 300    | Open wilds (grass / trees / rocks) |
| `blackstone` | (-290, -230)    | 190    | Black stone                        |
| `lostland`   | (300, -215)     | 200    | Lost land                          |
| `silenthall` | (320, 265)      | 185    | Silent hall                        |
| `mutezone`   | (-315, 275)     | 195    | Mute zone                          |
| `mirror`     | (-20, -400)     | 165    | Mirror                             |

Water level is `WATER_LEVEL = 2.2`; scatter sampling skips points below water and  
steep slopes.

---

## Rendering Pipeline

1. **Terrain** — one large indexed mesh uploaded once (`Terrain.Upload()`); drawn with the  
   terrain shader (albedo from region weights, hemisphere lighting, fog).
2. **Player** — a procedural humanoid capsule character mesh (`MeshGen.Character`),  
   drawn with the object shader.
3. **Scatter** — grass (2 variants × 4 blades), trees (trunk + cone) and rocks are packed  
   into `InstancedMesh` objects and rendered in a handful of instanced draw calls  
   (`ScatterWorld.DrawAll`). Each instance carries its own model matrix and tint, so a few  
   thousand props cost only a few draw calls.
4. **Camera / HUD** — `OrbitCamera` produces the view/projection matrices; the window title  
   shows the current chapter and objective.

All shaders are embedded as C# raw strings (`const string ... """`), so there are no  
external `.glsl` files to ship.

---

## Porting Notes (Python ModernGL → C# OpenTK)

The original engine (`renwai/`, Python + ModernGL) was fully re-implemented:

| Module    | Python                             | SharpGLow (C#)                      |
| --------- | ---------------------------------- | ----------------------------------- |
| Math      | `math3d.py`                        | `Engine/Math3D.cs`                  |
| Mesh      | `mesh.py`                          | `World/MeshGen.cs`                  |
| Terrain   | `terrain.py`                       | `World/Terrain.cs`                  |
| Renderer  | `renderer.py` + `shaders.py`       | `Engine/Renderer.cs` (GLSL inlined) |
| Camera    | `camera.py`                        | `Game/Camera.cs`                    |
| Player    | `player.py`                        | `Game/Player.cs`                    |
| Story     | `data/story.py` + `story_state.py` | `Game/Story.cs` + `StoryState.cs`   |
| Main loop | `game/main.py`                     | `Program.cs`                        |

Optimizations added during the port: instanced scatter rendering, region-based world  
generation, and a single-file self-contained publish.

---

## License & Author

Game & engine by **Noctilucere (芋泥P)**. Open-sourced at  
[Noctilucere/farwalk-hypothesis](https://github.com/Noctilucere/farwalk-hypothesis).
