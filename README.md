# 🎨 Indus : Battle Royale — 3D Asset Generator

Welcome to the automated 3D asset generation pipeline for **Indus : Battle Royale**.

This repository uses **Blender Python (`bpy`)** to procedurally generate low-poly, game-ready 3D models (weapons, vehicles, buildings, and props). The generated models are automatically exported as `.glb` files and hosted on a web-based 3D viewer via **GitHub Pages**.

## 🚀 Live 3D Web Viewer
Click the link below to view, rotate, and zoom the generated 3D models directly in your mobile or PC browser:
👉 **[View 3D Models Live Here](https://lk0024709-ux.github.io/indus-assets-gen/)**
*(The site is published automatically by the GitHub Actions pipeline below — every push to `main` regenerates and redeploys the assets).*

## ⚙️ How the Pipeline Works
1. **Code Generation:** Python scripts using `bpy` (Blender as a Python module) create models and apply PBR (Physically Based Rendering) materials — starting with the test asset in `tools/generate_test.py`.
2. **Automated Export:** Models are exported as `.glb` files (`export_format='GLB'`) into the `docs/models/` folder.
3. **CI/CD Deployment:** GitHub Actions (`.github/workflows/deploy.yml`) triggers on every push to `main`, installs `bpy`, runs the generator script, and deploys the `docs/` folder to GitHub Pages.
4. **Web Viewing:** The `docs/index.html` file uses Google's `<model-viewer>` to render the 3D models with neutral HDRI lighting, allowing anyone to view them without downloading heavy software.

## 📂 Project Structure
*   `tools/` — Contains the Python (`bpy`) scripts used to generate the 3D assets.
*   `tools/generate_test.py` — Test-asset generator (brown 1×1×1 crate cube).
*   `docs/` — The root folder for GitHub Pages.
*   `docs/index.html` — The 3D web viewer interface (dark UI, mobile responsive).
*   `docs/models/` — The generated `.glb` files live here.
*   `docs/models/test_crate.glb` — The current test asset, loaded by the viewer.
*   `.github/workflows/deploy.yml` — CI/CD pipeline: generate assets and deploy to Pages.

## 🧪 Test Asset
The pipeline is currently exercised with a dummy asset: a **1×1×1 cube** named `TestCrate` with a **brown Principled BSDF material** (Roughness `0.8`), exported as `docs/models/test_crate.glb`. Once the pipeline is proven green, real game assets (weapons, vehicles, buildings, props) will follow the exact same generate → export → deploy loop.

## 🖥️ Running Locally
```bash
# 1. Install Blender as a Python module (Python 3.11 → bpy 5.0.x)
pip install bpy

# 2. Generate the test asset into docs/models/test_crate.glb
python tools/generate_test.py

# 3. Serve the viewer locally
python -m http.server 8000 --directory docs
# → open http://localhost:8000 in a browser
```

## 🛠️ Tech Stack
*   **3D Engine:** Blender (via `bpy` Python API — `pip install bpy`)
*   **Frontend Viewer:** HTML / JS / Google `<model-viewer>`
*   **CI/CD:** GitHub Actions (`actions/configure-pages@v5`, `actions/upload-pages-artifact@v3`, `actions/deploy-pages@v4`)
*   **Hosting:** GitHub Pages

## 📜 License
All procedurally generated assets in this repository are created in-house and are free to use for the "Indus : Battle Royale" project.
