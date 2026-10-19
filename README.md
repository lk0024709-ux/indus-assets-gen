# 🎨 Indus : Battle Royale — 3D Asset Generator

Welcome to the automated 3D asset generation pipeline for **Indus : Battle Royale**.

This repository uses **Blender Python (`bpy`)** to procedurally generate low-poly, game-ready 3D models. The generated models are automatically exported as `.glb` files and hosted on a web-based 3D viewer via **GitHub Pages**.

## 🚀 Live 3D Web Viewer
Click the link below to view, rotate, and zoom the generated 3D models directly in your mobile or PC browser:
👉 **[View 3D Models Live Here](https://lk0024709-ux.github.io/indus-assets-gen/)**
*(The site is published automatically by the GitHub Actions pipeline below — every push to `main` regenerates and redeploys the assets).*

## ⚙️ How the Pipeline Works
1. **Textures:** Seamless tileable maps (`brick_wall`, `wood_plank`, `metal_corrugated`, `concrete_wall`) plus the procedurally generated Phase 1 maps (`grass`, `grass_hero` with baked building shadows, `metal_rusted`) live in `docs/textures/` and drive the PBR materials.
2. **Code Generation:** `tools/generate_phase1.py` uses `bpy` (Blender as a Python module) to build terrain and buildings at real-world metre scale — boolean door/window cutouts, `uv.smart_project()` unwrapping, Principled BSDF materials with Image Textures feeding Base Color, and point lights exported as `KHR_lights_punctual`. Every building's origin sits exactly at its bottom-centre (0, 0, 0).
3. **Automated Export:** Models are exported as packed `.glb` files (`export_format='GLB'`, `export_image_format='JPEG'` so the textures pack inside the container) into `docs/models/`.
4. **CI/CD Deployment:** GitHub Actions (`.github/workflows/deploy.yml`) triggers on every push to `main`, installs `bpy`, runs the Phase 1 generator, and deploys the `docs/` folder to GitHub Pages.
5. **Web Viewing:** `docs/index.html` uses Google's `<model-viewer>` (generated dynamically from a JS array) with `environment-image="neutral"` and `shadow-intensity="1"` so the PBR textures and shadows read clearly on any device — a hero card shows the combined `scene_phase1.glb` world preview.

## 📂 Project Structure
*   `tools/generate_phase1.py` — **Phase 1 `bpy` generator** (base ground + 4 buildings + hero scene).
*   `tools/generate_buildings.py` — original four-building generator (pre-Phase-1 assets).
*   `tools/generate_test.py` — pipeline smoke-test (brown test crate).
*   `tools/make_seamless.py` — makes the AI texture tiles perfectly seamless.
*   `docs/` — The root folder for GitHub Pages.
*   `docs/index.html` — The 3D web viewer (dark UI, mobile responsive, hero + 5 asset cards).
*   `docs/textures/` — Seamless texture maps (PNG), including procedural grass/rust.
*   `docs/models/terrain/` — `base_ground.glb`.
*   `docs/models/buildings/` — Building `.glb` files (textures packed inside).
*   `.github/workflows/deploy.yml` — CI/CD pipeline: generate assets and deploy to Pages.

## 🏗️ Phase 1 Assets
| File | Size (real-world) | Details | Texture |
|---|---|---|---|
| `base_ground.glb` | 100 m × 100 m flat plane | Ground for the preview; origin = surface centre | `grass.png` |
| `house_tactical.glb` | 10 m × 8 m · 2 floors | Brick walls, wooden porch, balcony, rusty metal gable roof, back fire escape, interior stairs + furniture + OmniLights | `brick_wall` + `wood_plank` + `metal_rusted` |
| `apartment_multifloor.glb` | 12 m × 10 m · 3 floors | Concrete; switchback stairs connect all 3 floors **and** the flat roof (exact 3 m × 1.5 m Boolean holes in every slab) | `concrete_wall` |
| `warehouse_metal.glb` | 20 m × 12 m · 1 floor | Corrugated metal, two open 6 m garage doors, side personnel door, concrete floor, crate cover | `metal_corrugated` + `concrete_wall` |
| `ruined_building.glb` | 10 m × 8 m · 2 floors | BMesh random face deletion, exposed rebar, rubble piles, no intact roof (stairs still passable) | `concrete_wall` + `metal_rusted` |
| `scene_phase1.glb` | 100 m × 100 m world | Hero scene: ground + all four buildings + baked soft shadows | packed PBR set |

### 🔺 Critical construction rules (enforced in code)
* **Stairs (trigonometry):** `step_depth = 0.2 / math.tan(math.radians(32))` → every flight climbs at exactly **32°**. Each floor slab above a flight gets an exact **3 m × 1.5 m Boolean Difference hole** (the head-room swept volume over the final 3 m of run), and the stairs are placed exactly there.
* **Passable openings:** doors 1.5 m W × 2.2 m H, windows 1.2 m × 1.2 m with sills at 1.0 m. Cutters are removed; **no glass, no blockers** — outside windows get open wooden shutters, doors get an open leaf.
* **Interiors:** internal floors/ceilings, bed · table · crates for cover, warm OmniLights inside every building.

## 🖥️ Running Locally
```bash
# 1. Install Blender as a Python module (Python 3.11 → bpy 5.0.x) + texture deps
pip install bpy pillow numpy

# 2. Generate Phase 1 assets (terrain + 4 buildings + hero scene)
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
