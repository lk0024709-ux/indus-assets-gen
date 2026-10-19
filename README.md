# 🎨 Indus : Battle Royale — 3D Asset Generator

Welcome to the automated 3D asset generation pipeline for **Indus : Battle Royale**.

This repository uses **Blender Python (`bpy`)** to procedurally generate low-poly, game-ready 3D models. The generated models are automatically exported as `.glb` files and hosted on a web-based 3D viewer via **GitHub Pages**.

## 🚀 Live 3D Web Viewer
Click the link below to view, rotate, and zoom the generated 3D models directly in your mobile or PC browser:
👉 **[View 3D Models Live Here](https://lk0024709-ux.github.io/indus-assets-gen/)**
*(The site is published automatically by the GitHub Actions pipeline below — every push to `main` regenerates and redeploys the assets).*

## ⚙️ How the Pipeline Works
1. **Textures:** Seamless tileable maps (`brick_wall`, `wood_plank`, `metal_corrugated`, `concrete_wall`) plus procedurally generated maps (`grass`, `grass_hero` with baked building shadows, `metal_rusted`) live in `docs/textures/`. The generator also bakes **vibrant tinted variants** (`brick_red`, `concrete_yellow`, `concrete_green`, `wood_warm`, `metal_steelblue`, `rust_orange`, `concrete_greydark`, `concrete_dark`, `wood_dark`) so the colour multiplies are stored in the texture pixels themselves — Blender's glTF exporter drops intermediate MixRGB tint nodes, but honours baked images.
2. **Code Generation:** `tools/generate_phase1.py` uses `bpy` (Blender as a Python module) to build terrain and buildings at real-world metre scale — boolean stair-hole cutouts (**solid shells: no door or window openings**), density-normalised `uv.smart_project()` unwrapping, and for every wall/floor material the chain **`Texture Coordinate (UV) → Mapping (Scale 0.3, 0.3, 0.3) → Image Texture (Extension REPEAT) → Base Color`** so bricks/wood/concrete tile at human scale with no stretching (exported to glTF as `KHR_texture_transform`). Point lights are exported as `KHR_lights_punctual`. Every building's origin sits exactly at its bottom-centre (0, 0, 0).
3. **Automated Export:** Models are exported as packed `.glb` files (`export_format='GLB'`, `export_image_format='JPEG'` so the textures pack inside the container) into `docs/models/`.
4. **CI/CD Deployment:** GitHub Actions (`.github/workflows/deploy.yml`) triggers on every push to `main`, installs `bpy`, runs the Phase 1 generator, and deploys the `docs/` folder to GitHub Pages.
5. **Web Viewing:** `docs/index.html` uses Google's `<model-viewer>` (generated dynamically from a JS array) with `environment-image="neutral"` and `shadow-intensity="1"` so the PBR textures and shadows read clearly on any device — a hero card shows the combined `scene_phase1.glb` world preview.

## 📂 Project Structure
*   `tools/generate_phase1.py` — **Phase 1 `bpy` generator** (base ground + 6 buildings + hero scene).
*   `tools/generate_buildings.py` — original four-building generator (pre-Phase-1 assets).
*   `tools/generate_test.py` — pipeline smoke-test (brown test crate).
*   `tools/make_seamless.py` — makes the AI texture tiles perfectly seamless.
*   `docs/` — The root folder for GitHub Pages.
*   `docs/index.html` — The 3D web viewer (dark UI, mobile responsive, hero + 7 asset cards).
*   `docs/textures/` — Seamless texture maps (PNG), including procedural grass/rust.
*   `docs/models/terrain/` — `base_ground.glb`.
*   `docs/models/buildings/` — Building `.glb` files (textures packed inside).
*   `.github/workflows/deploy.yml` — CI/CD pipeline: generate assets and deploy to Pages.

## 🏗️ Phase 1 Assets
| File | Size (real-world) | Details | Texture |
|---|---|---|---|
| `base_ground.glb` | 100 m × 100 m flat plane | Ground for the preview; origin = surface centre | `grass.png` |
| `house_tactical.glb` | 10 m × 8 m · 2 floors | **Red-brown brick**, wooden porch, balcony, rusty metal gable roof, back fire escape, interior stairs + furniture + OmniLights | `brick_red` + `wood_dark` + `rust_orange` |
| `school_yellow.glb` | 14 m × 10 m · 2 floors | **Bright yellow concrete** school: corridor partition, classrooms with desks on both floors, one 32° stair through an exact 3 m × 1.5 m slab hole, flat roof + parapet | `concrete_yellow` + `wood` |
| `apartment_green.glb` | 12 m × 10 m · 3 floors | **Vibrant green concrete**; switchback stairs connect all 3 floors **and** the flat roof (exact 3 m × 1.5 m Boolean holes in every slab) | `concrete_green` |
| `cabin_wood.glb` | 8 m × 6 m · 1 floor | **Warm brown wood** cabin: pitched rust roof, brick chimney, porch, solid walls (no openings), one OmniLight | `wood_warm` + `rust_orange` + `brick_red` |
| `warehouse_metal.glb` | 20 m × 12 m · 1 floor | **Split colourway: steel-blue walls + rusty orange roof**; solid shell with no doors or windows, dark concrete floor, crate cover | `metal_steelblue` + `rust_orange` |
| `ruined_building.glb` | 10 m × 8 m · 2 floors | **Darkened grey concrete**; BMesh random face deletion, exposed rebar, rubble piles, no intact roof (stairs still passable) | `concrete_greydark` + `metal_rusted` |
| `scene_phase1.glb` | 100 m × 100 m world | Hero scene: ground + all six buildings + baked soft shadows | packed tinted PBR set |

### 🔺 Critical construction rules (enforced in code)
* **Stairs (trigonometry):** `step_depth = 0.2 / math.tan(math.radians(32))` → every flight climbs at exactly **32°**. Each floor slab above a flight gets an exact **3 m × 1.5 m Boolean Difference hole** (the head-room swept volume over the final 3 m of run), and the stairs are placed exactly there.
* **Texture scale (UV):** every wall/floor material is `TexCoord (UV) → Mapping (Scale 0.3) → Image Texture (REPEAT) → Base Color`, with per-object UV density normalised to `1 / (0.3 × tile_size)` world UV/m — bricks, planks and panels stay human-sized and tile without stretching.
* **Colour:** vibrant tinted textures per building (red brick house, yellow school, green apartment, warm-brown cabin, steel-blue + rust warehouse, dark-grey ruin); tint is baked into the PNG pixels because the glTF exporter drops MixRGB tint nodes.
* **Solid shells — no doors, no windows:** all six buildings are closed boxes: no door cutouts, no window cutouts, no door leaves, no shutters, no garage-door rolls. The only openings are the stair slab holes (and the apartment roof hatch); cutters are removed, no glass, no blockers.
* **Interiors:** internal floors/ceilings use dark tinted concrete/wood (never plain white), roof material covers the roof underside, bed · table · crates for cover, warm OmniLights inside every building.

## 🖥️ Running Locally
```bash
# 1. Install Blender as a Python module (Python 3.11 → bpy 5.0.x) + texture deps
pip install bpy pillow numpy

# 2. Generate Phase 1 assets (terrain + 6 buildings + hero scene)
python tools/generate_phase1.py

# 3. Serve the viewer locally
python -m http.server 8000 --directory docs
# → open http://localhost:8000 in a browser
```

## 🛠️ Tech Stack
*   **3D Engine:** Blender (via `bpy` Python API — `pip install bpy`)
*   **Textures:** Seamless AI-generated texture maps, packed into the GLB as JPEG
*   **Frontend Viewer:** HTML / JS / Google `<model-viewer>`
*   **CI/CD:** GitHub Actions (`actions/configure-pages@v5`, `actions/upload-pages-artifact@v3`, `actions/deploy-pages@v4`)
*   **Hosting:** GitHub Pages

## 📜 License
All procedurally generated assets in this repository are created in-house and are free to use for the "Indus : Battle Royale" project.
