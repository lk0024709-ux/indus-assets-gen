# Source Superhero Character Studio

The repository's supplied models under `Base model /Character/` are now packed as portable, textured GLB files using the maps in `Base model /Texture/`.

## Character outputs

| Preview name | GLB | Base-color variant | Vertices | Rig |
|---|---|---|---:|---:|
| Female · Dark | `superhero_female_dark.glb` | Original female dark map | 8,844 | 65 joints |
| Female · Light | `superhero_female_light.glb` | Supplied alternate female light map | 8,844 | 65 joints |
| Male · Dark | `superhero_male_dark.glb` | Original male dark map | 8,483 | 65 joints |
| Male · Light | `superhero_male_light.glb` | Supplied alternate male light map (`T_Superhero_Male_Ligh.png`) | 8,483 | 65 joints |

The GLBs are at `procedural_asset_app/frontend/assets/characters/`. Each is self-contained: geometry, the source skeleton, materials, and seven embedded PNG maps (hair, eyes, body color, normal, and roughness maps). The original mesh and bind pose are preserved. The source GLTFs do not contain animation clips, so these exports are rigged but static until animations are authored separately.

## Preview

Open `procedural_asset_app/frontend/characters.html` through any static file server. For example:

```bash
python -m http.server 8000 --bind 0.0.0.0 --directory procedural_asset_app/frontend
```

Then visit `http://localhost:8000/characters.html`. The Three.js modules are loaded from jsDelivr, so the browser needs internet access. The viewer includes a four-model selector, orbit/zoom controls, a turntable toggle, fullscreen mode, and direct GLB downloads. A link to the studio is also in the procedural generator header.

## Rebuild and validate

From the repository root:

```bash
python tools/build_superhero_characters.py
python -m unittest discover -s tools -p 'test_*.py' -v
```

The packer uses only the Python standard library. It resolves the source export's texture filename quirks, embeds the PNG data into each GLB, and verifies its own GLB chunk/image/rig structure. The unit tests verify all four outputs and ensure each BaseColor variant points at the intended source map.
