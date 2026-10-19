# 🎨 Indus : Battle Royale — 3D Asset Generator

Welcome to the automated 3D asset generation pipeline for **Indus : Battle Royale**. 

This repository uses **Blender Python (`bpy`)** to procedurally generate low-poly, game-ready 3D models (weapons, vehicles, buildings, and props). The generated models are automatically exported as `.glb` files and hosted on a web-based 3D viewer via **GitHub Pages**.

## 🚀 Live 3D Web Viewer
Click the link below to view, rotate, and zoom the generated 3D models directly in your mobile or PC browser:
👉 **[View 3D Models Live Here](https://lk0024709-ux.github.io/indus-assets-gen/)** 
*(Note: This link will be active once the GitHub Actions deployment is complete).*

## ⚙️ How the Pipeline Works
1. **Code Generation:** Python scripts using `bpy` (Blender as a Python module) create models and apply PBR (Physically Based Rendering) materials.
2. **Automated Export:** Models are exported as `.glb` files into the `docs/models/` folder.
3. **CI/CD Deployment:** GitHub Actions automatically triggers on push, runs the Python script, and deploys the `docs/` folder to GitHub Pages.
4. **Web Viewing:** The `docs/index.html` file uses Google's `<model-viewer>` to render the 3D models with HDRI lighting, allowing anyone to view them without downloading heavy software.

## 📂 Project Structure
*   `tools/` — Contains the Python (`bpy`) scripts used to generate the 3D assets.
*   `docs/` — The root folder for GitHub Pages.
*   `docs/index.html` — The 3D web viewer interface.
*   `docs/models/` — The generated `.glb` files live here.

## 🛠️ Tech Stack
*   **3D Engine:** Blender (via `bpy` Python API)
*   **Frontend Viewer:** HTML / JS / Google `<model-viewer>`
*   **CI/CD:** GitHub Actions
*   **Hosting:** GitHub Pages

## 📜 License
All procedurally generated assets in this repository are created in-house and are free to use for the "Indus : Battle Royale" project.
