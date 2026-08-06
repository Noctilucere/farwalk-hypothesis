# The Farwalk Hypothesis (远行假设)

> A single-player 3D open-world narrative demo built on a **from-scratch OpenGL engine** (Python + ModernGL). Gameplay borrows *a little* from Genshin Impact. Some models and textures are placeholders / AI-generated because no artist was available. Bug reports welcome. Details below.

---

## 0. Overview

**The Farwalk Hypothesis** is a technical showcase of procedural world generation, GPU skinning, and real-time NPR/PBR rendering:

| Area | Description |
|---|---|
| **Engine** | Self-written Python + ModernGL engine: `math3d` (noise/vector/matrix), `mesh` (procedural geometry), `gltf` (binary glTF loader), `skin` (LBS binding), `renderer` (instancing/shadows/post), `shaders` (GLSL 330) |
| **World** | 960×960 m continuous terrain, 6 regions with **hard boundaries (no blending)** — each region owns distinct height fields, albedo, fog, sky and render style |
| **Characters** | 8-joint procedural skeleton, GPU **Linear Blend Skinning** (LBS) in a custom vertex shader (`u_bones[8]`), 4 runtime animations (idle / walk / run / glide) auto-switched by player/NPC state |
| **Story** | 8-chapter main quest (146 dialogue nodes), collectible heart-shard system, world map, achievements, in-game journal |
| **Portal system** | Each region has a portal that teleports to the next chapter's region and advances the main quest |
| **Distribution** | Standalone Windows exe (no Python needed); source runs cross-platform |

## 1. Rendering Pipeline

```
scene → [shadow pass 2048 depth] → [sky pass] → [terrain] → [instanced objects]
     → [skinned meshes] → [foliage] → [water] → scene FBO
     → post: bloom (separable gaussian) → composite (exposure/ACES/grading)
     → FXAA → default framebuffer
```

- **Terrain**: 384×384 heightfield sampled from multi-octave FBM; region weights are **one-hot (argmax)** so biomes meet at hard cliffs instead of smooth blends. Split into 12×12 chunks with frustum culling.
- **Shadows**: single 2048² directional shadow map, 3×3 PCF, slope-adaptive bias.
- **Instancing**: buildings/foliage/collectibles rendered via `glDrawElementsInstanced` with per-instance 3×4 affine matrix + tint + emissive.
- **Skinning**: per-vertex 2-joint weights (KNN from skeleton), CPU computes 8 pose matrices per frame → transposed to column-major → `uniform mat4 u_bones[8]` in the vertex shader.
- **Lighting**: stylized mix — PBR (GGX + Smith + Schlick) blended toward cel (wrapped half-Lambert banding + rim light) by a per-region `u_style` factor.

## 2. Procedural Content

| Asset | Method |
|---|---|
| Terrain mesh / albedo / normal | FBM + ridged noise, region-albedo lerp |
| Buildings (hut/tower/pillar/altar/ruin/portal/…) | Programmatic box/cylinder/ellipsoid assembly |
| Textures | **Real image textures** sampled from baked PNG tiles (brick / stone / plank / slab) via world-space projection; see `assets/textures/` |
| Foliage | Instanced grass blades with vertex wind sway + SSS backlight |
| Characters | 7 NPCs + player rigged with the built-in 8-joint skeleton; `assets/models/<eid>.glb` overrides the procedural mesh when present |
| Portrait art | 14 AI-generated character refs, rembg → transparent PNG in `assets/refs/` |

## 3. Building & Running

### 3.1 Dependencies

- Python 3.13+, ModernGL, glfw, numpy, Pillow
- OpenGL 3.3+ capable GPU

### 3.2 From source

```bash
git clone <repo> && cd <repo>
python -m venv .venv
.venv/Scripts/pip install moderngl glfw numpy Pillow
python run.py                    # default 1920x1080 high
python run.py --medium | --low | --fullscreen | --size=1280x720
```

### 3.3 Standalone exe (Windows)

Download `dist/远行假设.exe` (~100 MB). Double-click to play.

### 3.4 Controls

| Key | Action |
|---|---|
| WASD | Move |
| LShift | Sprint |
| Space | Jump / glide |
| E | Interact |
| Q | Echo scan |
| C / M / Tab / J | Character / Map / Journal |
| F5 / F11 | Save / fullscreen |
| = / - | Mouse sensitivity |
| Mouse | Direct camera mapping; wheel zooms |

## 4. Project Layout

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

## 5. Testing

```bash
python tools/story_walk.py                # logic-only full-play regression (no window)
python tools/smoke_test.py --seconds=80   # headless e2e, saves 9 screenshots to tools/shots/
```

## 6. Known Limitations

- Windows-tested only; other platforms untested
- Cloud AI 3D quota: 5 generations/day; remaining characters pending
- Texture tiles are baked once by `tools/gen_textures.py`; re-run to regenerate
- Skinning is a simplified 8-joint rig — swap in a Mixamo/Blender rig for production animation

## 7. Acknowledgements

- Tencent Hunyuan3D — free character 3D generation API
- ModernGL / GLFW — Python OpenGL bindings & windowing

---

## Author

**Noctilucere (芋泥P)**

Independent music producer, illustrator & programmer. This is the playable demo of *The Farwalk Hypothesis* (formerly 人外论 · 谁).

> *Behind every question stands another question.*
