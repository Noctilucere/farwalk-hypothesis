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
- **Shadow mapping** — 2048² depth FBO, orthographic light VP with texel snapping, 3×3 PCF  
  + edge fade (`Engine/Shadow.cs`).
- **HDR post-processing** — scene FBO (`RGBA16f`) → bright-pass → separated Gaussian bloom →  
  ACES tone-map + vignette + saturation → FXAA (`Engine/PostFX.cs`).
- **GPU skinned character** — 8-bone linear-blend-skinning cat-beast biped with fully  
  procedural animation (idle / walk / run / glide / air), no external assets  
  (`Engine/Skinning.cs`, `World/SkinnedMeshGen.cs`).
- **Portals & fast travel** — six region gates with proximity discovery and a quick-travel  
  menu; sixteen world landmarks drive the story steps (`Game/Portals.cs`).
- **Map / Journal / Achievements UI** — runtime CJK glyph atlas, minimap, full world map,  
  journal and 15-achievement system with toasts (`UI/Hud.cs`, `UI/Overlay.cs`,  
  `UI/TextAtlas.cs`, `Game/Achievements.cs`).
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
      Renderer.cs             # Shader helper + terrain/object/skinned GLSL 330 shaders
      Shadow.cs               # 2048² shadow depth FBO + PCF (depth shaders)
      PostFX.cs               # HDR scene FBO → bloom → ACES → FXAA
      Skinning.cs             # 8-bone skeleton + procedural animation controller
      Instanced.cs            # InstancedMesh — per-instance matrix + tint VAO
    World/
      Terrain.cs              # TerrainConfig (6 regions), WorldGen, Terrain (960 m)
      MeshGen.cs              # procedural meshes: Capsule, GrassBlade, Character, Merge, Transform
      SkinnedMeshGen.cs       # GPU-skinned cat-beast biped (stride-10 mesh)
      Scatter.cs              # ScatterGen — samples ground, builds grass/tree/rock meshes
    Game/
      Camera.cs               # OrbitCamera (third-person, mouse + scroll)
      Player.cs               # movement / sprint / jump / glide
      Story.cs                # StoryData — dialogue nodes + chapter list
      StoryState.cs           # quest gates + chapter progression
      Portals.cs              # 6 region gates + 16 story landmarks
      Achievements.cs         # 15 achievements + unlock toasts
    UI/
      Hud.cs                  # HUD / dialogue / map / journal / achievements / portal menu
      Overlay.cs              # immediate-mode 2D overlay (rect/line/circle/text/image)
      TextAtlas.cs            # runtime CJK glyph atlas (GDI+ → texture)
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

### Controls

| Key | Action                                            |
| --- | ------------------------------------------------- |
| `W A S D` | Move (relative to camera)                         |
| `Shift` | Sprint                                            |
| `Space` | Jump; hold while falling to **glide**             |
| Mouse | Look around · scroll to zoom                      |
| `E` | Interact with the nearby landmark / advance dialogue |
| `F` | Open the fast-travel menu near a portal           |
| `M` | World map                                         |
| `J` | Journal                                           |
| `C` | Achievements                                      |
| `F2` / `F3` | Toggle shadows / post-processing (debug)      |
| `F11` | Fullscreen                                        |

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

Each frame runs three passes:

1. **Shadow pass** — the sun's orthographic view-projection (texel-snapped to reduce  
   shimmer) renders terrain, instanced scatter and the skinned player into a 2048² depth  
   FBO (`Engine/Shadow.cs`).
2. **Scene pass (HDR)** — everything is drawn into an `RGBA16f` scene FBO with the shadow  
   map sampled in the fragment shaders (3×3 PCF + edge fade):
   - **Terrain** — one large indexed mesh uploaded once (`Terrain.Upload()`), albedo from  
     region weights, hemisphere lighting, fog, water tint (`WATER_LEVEL`).
   - **Player** — a GPU-skinned cat-beast biped (`SkinnedMeshGen.Character`) whose 8 bones  
     are evaluated each frame by the procedural animation controller (`Engine/Skinning.cs`)  
     and uploaded as `uBones[8]`.
   - **Scatter** — grass (2 variants), trees and rocks packed into `InstancedMesh` objects  
     and drawn in a few instanced draw calls (`ScatterWorld.DrawAll`).
   - **Portals & landmarks** — each discovered region gate is a spinning vertical ring; each  
     story landmark is a glowing beacon, both drawn with the object shader.
3. **Post-processing** — the scene FBO is resolved through bright-pass → separated Gaussian  
   bloom → ACES tone-map + vignette + saturation → sRGB → FXAA into the default framebuffer  
   (`Engine/PostFX.cs`).
4. **UI** — the immediate-mode `Overlay` draws HUD, dialogue, minimap, world map, journal,  
   achievements and the portal menu on top (`UI/Hud.cs`).

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
