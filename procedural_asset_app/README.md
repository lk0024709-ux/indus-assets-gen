# Procedural 3D Asset Generator

A browser-based procedural modeling workspace. FastAPI validates recipe parameters, launches Blender in background mode, exports GLB, and caches the exact result by a deterministic SHA-256 parameter key. The frontend uses Three.js to preview the GLB with orbit controls and an environment-lit viewport.

## Included recipes

- **Chair:** seat width/depth/height, backrest height, 3/4 leg layout, material color.
- **Table:** dimensions, rectangular/round top, straight/tapered legs, color.
- **Lamp:** base radius, stem height, shade size/type, radial detail, color.
- **Rock:** deterministic seed, size, irregularity, subdivision and smoothing.
- **Barrel:** radius, height, bulge, stave count and metal hoops.

All recipe inputs have server-side type and range validation. A repeated recipe + parameter set returns the cached GLB. Blender subprocesses have a 60-second timeout and errors include the diagnostic tail.

## Requirements

- Python 3.11 recommended
- Blender 4.x installed and available as `blender`, or set `BLENDER_BIN`
- Internet access in the browser for Three.js modules loaded from jsDelivr

## Run locally

From this folder:

```bash
chmod +x run.sh
./run.sh
```

Then open http://localhost:8000. API health is at `/api/health`, recipe schemas at `/api/recipes`, and generation at `POST /api/generate`.

Example request:

```json
{
  "recipe": "chair",
  "params": {
    "seat_width": 1.2,
    "seat_depth": 0.9,
    "seat_height": 0.55,
    "back_height": 1.1,
    "leg_count": "4",
    "color": "#B87843"
  }
}
```

Outputs are saved under `outputs/`. They are served at `/outputs/<filename>.glb`. Cache keys are based on the normalized recipe ID and validated parameters. Set `BLENDER_BIN=/path/to/blender` if Blender is not on PATH.

## GitHub Actions and hosting

GitHub Actions can run syntax checks and build/test automation, but it does not keep a persistent FastAPI + Blender server running after a workflow ends. GitHub Pages can host static files only; it cannot execute Blender or the FastAPI generation endpoint. For live procedural generation, deploy this folder to a persistent Python host/container that has Blender installed. If only the static frontend is published, generation requires a separately hosted backend and its API URL must be configured.

## Godot 4

Import downloaded GLB files into your Godot 4 project. Keep model scale consistent, add collision shapes and gameplay-specific materials in Godot, and inspect triangle count before shipping to mobile. Generated geometry is deliberately low-poly; it is not a replacement for final art review.
