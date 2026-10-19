# 🎨 Indus : Battle Royale — 3D Asset Generator

Welcome to the automated 3D asset generation pipeline for **Indus : Battle Royale**.

This repository uses **Blender Python (`bpy`)** to procedurally generate low-poly, game-ready 3D models. The generated models are automatically exported as `.glb` files and hosted on a web-based 3D viewer via **GitHub Pages**.

## 🚀 Live 3D Web Viewer
Click the link below to view, rotate, and zoom the generated 3D models directly in your mobile or PC browser:
👉 **[View 3D Models Live Here](https://lk0024709-ux.github.io/indus-assets-gen/)**
*(The site is published automatically by the GitHub Actions pipeline below — every push to `main` regenerates and redeploys the assets).*

## ⚙️ How the Pipeline Works
1. **Textures:** Four seamless, tileable texture images (`brick_wall`, `wood_plank`, `metal_corrugated`, `concrete_wall`) live in `docs/textures/` and drive the PBR materials.
2. **Code Generation:** `tools/generate_buildings.py` uses `bpy` (Blender as a Python module) to build the buildings at real-world metre scale — boolean door/window cutouts, `uv.smart_project()` unwrapping, and Principled BSDF materials with an Image Texture node feeding Base Color. Every building's origin sits exactly at its bottom-centre (0, 0, 0).
3. **Automated Export:** Models are exported as packed `.glb` files (`export_format='GLB'`, `export_image_format='JPEG'` so the textures pack inside the container) into `docs/models/buildings/`.
4. **CI/CD Deployment:** GitHub Actions (`.github/workflows/deploy.yml`) triggers on every push to `main`, installs `bpy`, runs the generator script, and deploys the `docs/` folder to GitHub Pages.
5. **Web Viewing:** `docs/index.html` uses Google's `<model-viewer>` (generated dynamically from a JS array) with `environment-image="neutral"` and `shadow-intensity="1"` so the textures read clearly on any device.

## 📂 Project Structure
*   `tools/generate_buildings.py` — `bpy` generator for all four buildings.
*   `tools/generate_test.py` — original pipeline smoke-test (brown test crate).
*   `docs/` — The root folder for GitHub Pages.
*   `docs/index.html` — The 3D web viewer (dark UI, mobile responsive, 4 building cards).
*   `docs/textures/` — Seamless AI-generated texture maps (PNG).
*   `docs/models/buildings/` — The generated building `.glb` files (textures packed inside).
*   `.github/workflows/deploy.yml` — CI/CD pipeline: generate assets and deploy to Pages.

## 🏗️ Building Assets
| File | Size (real-world) | Details | Texture |
|---|---|---|---|
| `garage.glb` | 10 m × 8 m × 4 m | Flat roof, 4 m × 3 m boolean door cutout | `concrete_wall.png` |
| `sniper_tower.glb` | 4 m × 4 m × 10 m | 4 pillars, wooden platform @ 8 m, railings, small roof | `wood_plank.png` |
| `house_small.glb` | 6 m × 6 m × 3.5 m walls | 1 door (1.2 m × 2.2 m), 2 window cutouts, wooden gable roof | `brick_wall.png` (walls) + `wood_plank.png` (roof) |
| `warehouse.glb` | 15 m × 10 m × 6 m | 5 m × 4.5 m sliding doors, flat roof | `metal_corrugated.png` |

## 🖥️ Running Locally
```bash
# 1. Install Blender as a Python module (Python 3.11 → bpy 5.0.x)
pip install bpy

# 2. Generate the buildings into docs/models/buildings/
python tools/generate_buildings.py

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
