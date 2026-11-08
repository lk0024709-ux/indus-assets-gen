# Indus Character & Outfit Web Studio

The **Indus Web Suite** ships three integrated, static-host-ready 3D web tools deployed to GitHub Pages (`https://lk0024709-ux.github.io/indus-assets-gen/`):

1. **Character & Battle Royale Outfit Studio** (`/` and `/characters.html`)
2. **Browser Procedural 3D Asset & Outfit Generator** (`/generator.html`)
3. **3D File & Motion Inspector** (`/asset-viewer.html`)

---

## Recent Capabilities Live on Web

### 1. Fitted 65-Joint Battle Royale Tactical Wardrobe (`Outfit_BR_Fit`)
- **20 watertight `SkinnedMesh` pieces** per gender (`outfit_br_female.glb` and `outfit_br_male.glb`), generated directly from `Base model /Character/Superhero_Female_FullBody.gltf` and `Superhero_Male_FullBody.gltf` (`tools/build_battle_royale_outfits.py`, mirroring the Blender script `tools/outfit_fit_character.py`):
  - **Body-cut garments** (`Tee`, `Cargo_Pants`, `Boots`): cut from the hero body mesh, extruded outward along smoothed vertex normals into closed 2-manifold shells (`boundary_edges == 0`), inheriting exact 4-bone `JOINTS_0` / `WEIGHTS_0` skinning.
  - **Rigid-skinned tactical gear**: `Belt`, `Belt_Buckle`, `Pouch_R`, `Pouch_L`, `Bullet_0..2`, `Carabiner`, `KneePad_R/L`, `Holster`, `Holster_Strap_0..1`, `Cargo_Pocket`, `Cargo_Flap`, `Tee_ChestPatch`, and `Tee_ChestStar`.
- **4 Wardrobe Modes**:
  - `Equipped` — Hero + fitted 20-piece Battle Royale outfit animating together on the shared 65-bone skeleton.
  - `Suit Only` — Base superhero suit with 7 embedded PBR maps.
  - `Outfit Rig` — Rigged 20-piece outfit animating on the 65-bone skeleton without the body mesh.
  - `Kit (Static)` — Standalone 30-piece modular `Outfit_BR` kit (`outfit_battle_royale.glb`).
- **4 Modular Layer Toggles**: `Tee + Star`, `Cargo Pants`, `Belt + Holster`, and `Combat Boots`.

### 2. Live Squad Loadout Color Customizer
- **5 Tactical Presets**: `Olive` (Default), `Desert`, `Night`, `Arctic`, and `Crimson`.
- **3 Live Color Swatches**: Custom `Tee`, `Pants`, and `Gear` pickers that recolor PBR materials in real time in the 3D viewport **and** write linear-RGB `baseColorFactor` overrides into exported `.glb` files (`glb-combine.js`).

### 3. 74 Retargeted Mixamo Motions + Instant Search
- All 74 FBX clips in `Base model /Motion/` are grouped into `Movement`, `Stance`, `Combat`, and `Special`, with instant search filtering (`#motionSearch`), playback speed (`0.5×`–`2×`), timeline scrubbing, and world-delta retargeting onto the 65-joint rig (`motion-retarget.js`).

### 4. Browser-Native GLB Combiner & Procedural Asset Generator
- **Single-file Outfitted Character GLB Export** (`glb-combine.js`): Merges any hero GLB + active outfit layers + custom tactical colors into one self-contained `.glb` without re-encoding the 7 embedded PBR PNG textures.
- **Zero-Server Procedural GLB Builder** (`web-recipes.js` + `/generator.html`): Generates downloadable binary glTF 2.0 `.glb` files directly in the browser for all 6 recipes (`Battle Royale Outfit`, `Chair`, `Table`, `Lamp`, `Rock`, `Barrel`) on static GitHub Pages, while automatically using FastAPI + Blender when run locally with a backend.

---

## Rebuilding Assets & Running Locally

```bash
# Rebuild character GLBs, fitted/standalone Battle Royale outfit GLBs, and motion manifest
python3 tools/build_superhero_characters.py
python3 tools/build_battle_royale_outfits.py
python3 tools/build_motion_manifest.py

# Serve the complete Web Suite locally on http://localhost:8000
python3 tools/serve_character_preview.py --port 8000
```
