# Superhero Character Studio

The repository's models in `Base model /Character/` are packed into portable, textured GLBs with the source maps from `Base model /Texture/`, and paired with fitted **Battle Royale tactical outfits** built directly onto their **65-joint skeletons**.

## Character variants

| Preview name | GLB | Base-color map | Vertices | Rig |
|---|---|---|---:|---:|
| Female · Dark | `superhero_female_dark.glb` | Original female dark map | 8,844 | 65 joints |
| Female · Light | `superhero_female_light.glb` | Alternate female light map | 8,844 | 65 joints |
| Male · Dark | `superhero_male_dark.glb` | Original male dark map | 8,483 | 65 joints |
| Male · Light | `superhero_male_light.glb` | Supplied alternate map (`T_Superhero_Male_Ligh.png`) | 8,483 | 65 joints |

The character GLBs are under `procedural_asset_app/frontend/assets/characters/`. Each is self-contained: geometry, skeleton, materials, and seven embedded PNG maps.

## Battle Royale tactical outfits

| Outfit asset | GLB | Pieces | Rig | Source logic |
|---|---|---:|---|---|
| Female · Battle Royale Fit | `outfit_br_female.glb` | 20 | 65 joints | `tools/outfit_fit_character.py` |
| Male · Battle Royale Fit | `outfit_br_male.glb` | 20 | 65 joints | `tools/outfit_fit_character.py` |
| Standalone `Outfit_BR` Kit | `outfit_battle_royale.glb` | 30 | Static modular kit | `tools/outfit_battle_royale.py` |

* **Fitted rigged garments (`outfit_br_female.glb`, `outfit_br_male.glb`):** `Tee`, `Cargo_Pants`, and `Boots` are cut out of each hero's body mesh by bone region and normalized height, offset outward from the skin, and solidified into closed 2-manifold shells while retaining exact 4-bone skin weights. `Belt`, `Belt_Buckle`, `Pouch_R`, `Pouch_L`, `Bullet_0..2`, `Carabiner`, `KneePad_R/L`, `Holster`, `Holster_Strap_0..1`, `Cargo_Pocket`, `Cargo_Flap`, `Tee_ChestPatch`, and `Tee_ChestStar` are measured from the body cross-sections and skinned to `pelvis`, `spine_03`, `thigh_r/l`, and `calf_r/l`.
* **Wardrobe modes & layer toggles:** Character Studio supports **Equipped**, **Suit Only**, **Outfit Rig** (65-joint outfit without body), and **Kit (Static)** (`Outfit_BR`), plus live modular toggles for **Tee + Star**, **Cargo Pants**, **Belt + Holster**, and **Combat Boots**.
* **Single-file GLB combiner (`glb-combine.js` & `pack_character_with_outfit`):** Downloading an equipped hero packs the character's untouched PBR textures, 65-joint skin, and active skinned outfit pieces into one portable `.glb` (`superhero_female_dark_battle_royale.glb`, etc.).

## Motion library and web playback

`Base model /Motion/` contains **74 FBX motion clips** on a Mixamo 65-bone rig. The Character Studio loads each FBX on demand, maps Mixamo joints to the superhero skeleton, converts bone-space and centimeter units, and plays it on both the character body and the fitted Battle Royale outfit simultaneously. The first idle motion starts automatically; every clip has its own clickable button, arranged in scrollable Movement, Stance, Combat, and Special groups.

## Preview locally

Use the repository preview server, which serves the frontend and maps the motion URL back to the original `Base model /Motion/` folder:

```bash
python tools/serve_character_preview.py --host 0.0.0.0 --port 8000
```

Open `/characters.html` (or `/asset-viewer.html`).

## Rebuild and validate

From the repository root:

```bash
python tools/build_superhero_characters.py
python tools/build_battle_royale_outfits.py
python tools/build_motion_manifest.py
python -m unittest discover -s tools -p 'test_*.py' -v
npm install --prefix /tmp/three-validation --no-save --no-package-lock three@0.166.1
THREE_PACKAGE=/tmp/three-validation/node_modules/three node tools/validate_motion_retarget.mjs
```

If Blender 3.2+ / 4.x is installed locally, you can also run the standalone Blender scripts directly:

```bash
blender -b -P tools/outfit_battle_royale.py -- --export outfit_br.glb
blender -b -P tools/outfit_fit_character.py -- --char "Base model /Character/Superhero_Female_FullBody.gltf" --export outfit_br_female_blender.glb
```
