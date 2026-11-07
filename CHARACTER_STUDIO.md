# Superhero Character Studio

The repository's models in `Base model /Character/` are packed into portable, textured GLBs with the source maps from `Base model /Texture/`. Both source characters already have a **65-joint skin and skeleton**, so no replacement skeleton was needed.

## Character variants

| Preview name | GLB | Base-color map | Vertices | Rig |
|---|---|---|---:|---:|
| Female · Dark | `superhero_female_dark.glb` | Original female dark map | 8,844 | 65 joints |
| Female · Light | `superhero_female_light.glb` | Alternate female light map | 8,844 | 65 joints |
| Male · Dark | `superhero_male_dark.glb` | Original male dark map | 8,483 | 65 joints |
| Male · Light | `superhero_male_light.glb` | Supplied alternate map (`T_Superhero_Male_Ligh.png`) | 8,483 | 65 joints |

The GLBs are under `procedural_asset_app/frontend/assets/characters/`. Each is self-contained: geometry, skeleton, materials, and seven embedded PNG maps. The GLBs preserve the original mesh and bind pose and do not contain animation clips.

## Motion library and web playback

`Base model /Motion/` contains **74 FBX motion clips** on a Mixamo 65-bone rig. The Character Studio loads each FBX on demand, maps Mixamo joints to the superhero skeleton, converts bone-space and centimeter units, and plays it on the selected male or female model. The first idle motion starts automatically; every clip has its own clickable button, arranged in scrollable Movement, Stance, Combat, and Special groups. Play/pause, stop, speed, and timeline controls remain available.

The motion button library and retargeter are in `procedural_asset_app/frontend/characters.html` and `character-viewer.js`; `motion-retarget.js` contains the skeleton mapping. Rotation deltas are converted between each source/target bone's rest-local frame, while translation deltas use the parent-frame basis and preserve the FBX root trajectory at centimeter-to-meter scale. The compact motion list is generated as `assets/motion-manifest.json`. GitHub Pages staging copies the FBXs into `assets/motions/` without duplicating those source files in the repository.

## Preview locally

Use the repository preview server, which serves the frontend and maps the motion URL back to the original `Base model /Motion/` folder:

```bash
python tools/serve_character_preview.py --host 0.0.0.0 --port 8000
```

Open `/characters.html`. Three.js is loaded from jsDelivr, so the browser needs internet access. The viewer also supports model orbit/zoom, turntable, fullscreen, and GLB download.

## Rebuild and validate

From the repository root:

```bash
python tools/build_superhero_characters.py
python tools/build_motion_manifest.py
python -m unittest discover -s tools -p 'test_*.py' -v
npm install --prefix /tmp/three-validation --no-save --no-package-lock three@0.166.1
THREE_PACKAGE=/tmp/three-validation/node_modules/three node tools/validate_motion_retarget.mjs
```

The test suite checks the embedded GLBs, verifies the motion button UI, and confirms that the manifest covers every source FBX. The Node validation parses and retargets all 74 clips, checks finite animated keys, samples AnimationMixer playback across the four motion categories, and compares Run Right root travel and pelvis-relative foot positions against the unmodified source FBX.
