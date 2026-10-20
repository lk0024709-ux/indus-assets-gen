# Godot Integration — Rajasthani Mahal (Tasks 1-4)

This file implements your exact requested workflow for the **Godot game project** (separate from this asset repo `indus-assets-gen`).  
**This repo is the asset pipeline** — it generates and hosts the GLBs. Your Godot project consumes them.

---

## Repo layout (this asset repo)

```
docs/models/buildings/rajasthani_mahal.glb  ← alias of mahal_palace_master.glb (4.2 MB, 40×34×26.6 m, bottom-center (0,0,0))
docs/models/buildings/mahal_palace_master.glb  (canonical master)
docs/models/modular/wall_block.glb | wall_module.glb   (3.4 KB)
docs/models/modular/arch_block.glb | arch_module.glb   (38 KB)
docs/models/modular/dome.glb | dome_module.glb         (17 KB)  r=5 + spire
docs/models/modular/pillar.glb | pillar_module.glb     (86 KB)  r0.5 h6 + 3 bands
```

> All modular blocks use `create_solid_material` Principled BSDF `Roughness 0.6`, `EXACT` Booleans, origin set via 3D cursor bottom-center `(0,0,0)` — so dropping them at `(0,0,0)` in Godot puts the floor at `y=0`.

Live viewer + direct downloads (after `main` deploy succeeds):
* Viewer: https://lk0024709-ux.github.io/indus-assets-gen/
* Mahal full: https://lk0024709-ux.github.io/indus-assets-gen/models/buildings/rajasthani_mahal.glb
* Alternate (same file): https://lk0024709-ux.github.io/indus-assets-gen/models/buildings/mahal_palace_master.glb
* Modular folder: https://lk0024709-ux.github.io/indus-assets-gen/models/modular/ → `wall_block.glb`, `arch_block.glb`, `dome.glb`, `pillar.glb` (and `*_module.glb` aliases)

---

## TASK 1 — Download new assets (do this in your GODOT repo)

### Option A: Manual (one-time)

1. Go to the latest successful Action run → artifact `github-pages` is not a zip of `docs/` you want — easiest is direct download:

```bash
# in your Godot project root
mkdir -p assets/downloaded_models/modular

# Mahal — full assembled (use either name):
curl -L -o assets/downloaded_models/rajasthani_mahal.glb \
  https://lk0024709-ux.github.io/indus-assets-gen/models/buildings/rajasthani_mahal.glb

# Modular blocks (4 files, 2 naming schemes kept in sync):
for f in wall_block arch_block dome pillar; do
  curl -L -o assets/downloaded_models/modular/${f}.glb \
    https://lk0024709-ux.github.io/indus-assets-gen/models/modular/${f}.glb
done
# aliases if your GDScript expects *_module.glb:
for f in wall_module arch_module dome_module pillar_module; do
  cp assets/downloaded_models/modular/${f%_module*}.glb assets/downloaded_models/modular/${f}.glb 2>/dev/null || true
done
```

PowerShell (Windows):

```powershell
New-Item -ItemType Directory -Force -Path assets/downloaded_models/modular | Out-Null
Invoke-WebRequest -Uri https://lk0024709-ux.github.io/indus-assets-gen/models/buildings/rajasthani_mahal.glb -OutFile assets/downloaded_models/rajasthani_mahal.glb
@("wall_block","arch_block","dome","pillar") | ForEach-Object {
  Invoke-WebRequest -Uri "https://lk0024709-ux.github.io/indus-assets-gen/models/modular/$_.glb" -OutFile "assets/downloaded_models/modular/$_.glb"
}
```

### Option B: Auto-sync via GitHub Action (recommended — add to your GODOT repo)

Copy `.github/workflows/sync-mahal-assets.yml.example` from this repo into your Godot repo as `.github/workflows/sync-mahal-assets.yml`.  
It runs on `workflow_dispatch` and on a daily cron, fetches the 5 GLBs above, commits if changed, and can trigger your Godot export.

We also provide `examples/godot/download_assets.sh` / `.ps1` helper scripts — copy them into your Godot project.

> **Where to place files:** Exactly `res://assets/downloaded_models/rajasthani_mahal.glb` and `res://assets/downloaded_models/modular/*.glb` as you specified. Do **not** put them under `res://addons/` or `res://imports/`.

---

## TASK 2 — Replace the old procedural Mahal (`main.gd`)

In your Godot project's map builder (typically `main.gd`, `world.gd`, or `mahal_manager.gd`):

1. **Remove/disable** the old procedural calls (`generate_mahal()`, `build_mahal_walls()`, etc.).
2. **Instance the new GLB** at map center `(0,0,0)` and generate trimesh collision so stairs, archways, interior Darbar, jali, and chhatris are walkable.

Paste one of these ready-made scripts:

* **Minimal** — `examples/godot/main_mahal_godot.gd` (drop-in `Node3D` script, auto-creates `StaticBody3D` with `ConcavePolygonShape3D` per mesh, handles bottom-center origin correctly).
* **Advanced** — includes navmesh rebake hook and LOD placeholder.

Key points already handled in the script:
* `GLTFDocument` load at runtime OR pre-import via Godot's `Import` tab (recommended: set `Root Type: Node3D`, ensure `Generate Collisions: Off` — we generate our own trimesh so you get perfect stair collisions instead of convex hull approximations).
* `StaticBody3D` + `CollisionShape3D` with `ConcavePolygonShape3D` (trimesh) — required for interior + stairs + arched openings. Do **not** use `ConvexPolygonShape3D` (it will seal doorways).
* Recursively walks `MeshInstance3D` children (the master has 23 mats, ~9816 tris, 40×34×26.6 bbox) and calls `mesh.create_trimesh_shape()`.
* Map center: `mahal.global_position = Vector3.ZERO` — the GLB's origin is already bottom-center `(0,0,0)`, so its floor sits flush on your `terrain_ground`/`base_ground` at `y=0`. No offset needed.
* Optional: enable `physics/physics_ticks_per_second = 60`, `collision_layer = 1`.

> See file header comments for tuning (e.g., `collision_mask`, `navmesh`).

### Verify

Run scene → player should:
* Spawn outside, walk through 3 front + side multi-layer arches (5 m outer gold trim, 4 m inner deep-blue)
* Climb 60-step 30° stair loop to roof hole, walk on dome base
* Enter interior Darbar (checkered floor, 8 pillars with red/blue/yellow bands, throne, jali lattice), pass sawtooth parapet and jharokhas with teal half-domes

If collisions feel “floaty”, ensure `create_trimesh_collision()` ran (check Remote Inspector for `StaticBody3D` children).

---

## TASK 3 — Optional: Modular assembly (when full GLB is too heavy)

Use when `rajasthani_mahal.glb` (4.2 MB) exceeds your mobile budget or you want procedural variation.

Script: `examples/godot/modular_mahal_builder.gd`

It demonstrates:
* Instantiating `dome_module.glb` at center `(0, 12, 0)` r=6 logic → places `dome.glb` (r=5) scaled 1.2× to approximate r=6 central dome + 4 corners at `(±10, 0, ±7)` scaled 0.6× for corner r=3 domes (positions match Master spec: BUILD_W 30×BUILD_D 20, BUILD_H 12)
* `pillar_module.glb` grid: 8 interior pillars + jharokha pillars + chhatri supports
* `wall_module.glb` / `arch_module.glb` rows to rebuild 30×20×12 walls with 5 front / 3 side arch cutters (replicating the `math.sin/cos` arch logic in GDScript for placement, not geometry)
* Jharokha composition: `wall_module` stub + 2× `pillar_module` (scaled 0.25×) + `dome_module` half-sphere (scaled 0.3×) at `y=7`

Switch with a feature flag:

```gdscript
const USE_MODULAR_FALLBACK = false # set from ProjectSettings or memory check
if USE_MODULAR_FALLBACK:
    ModularMahalBuilder.assemble_at(Vector3.ZERO, get_tree().current_scene)
else:
    MainMahalLoader.load_full_mahal_at(Vector3.ZERO)
```

Collision: each module also gets `ConcavePolygonShape3D` trimesh via same helper.

---

## TASK 4 — Build & Deploy → Live APK link

**Important scope clarification:**

* This repository (`lk0024709-ux/indus-assets-gen`) is the **3D asset pipeline** — its GitHub Action **generates GLBs and deploys the web viewer** to GitHub Pages. It does **not** build a Godot APK. Pushing to `main` here correctly triggers `Generate & Deploy 3D Assets` → https://lk0024709-ux.github.io/indus-assets-gen/ (verified in last run #39403901369 `success`).
* Your Godot game (where `main.gd` lives) is a **separate repository** (e.g., `lk0024709-ux/indus` or `indus-game`). The live APK is built by **that repo's** Godot export Action (e.g., `godot-export.yml` using `barichello/godot-ci:4.x` + `actions/upload-artifact` → Release).

What to do:

1. **In this asset repo:** Push is already done on branch `arena/6eae1dec-indus-assets-gen` → open PR → merge to `main` → Action deploys viewer + `rajasthani_mahal.glb` URL above becomes live. (We have prepared alias copies so your download script works immediately after merge.)

2. **In your Godot repo:** Copy the `download_assets` step (Option B) or run the manual `curl` (Option A), commit `assets/downloaded_models/`, replace `main.gd` with the provided loader script, then:

```bash
git add assets/downloaded_models/ main.gd
git commit -m "feat: replace procedural mahal with rajasthani_mahal.glb + trimesh collisions"
git push origin main
```

Your Godot repo's export workflow (example supplied in `examples/godot/godot-export.yml.example`) will build:

* `export_presets.cfg` preset `Android` → `builds/indus.apk`
* On success, the Action uploads artifact and creates a Release; the live link looks like:

```
https://github.com/<YOUR_GODOT_ORG>/<YOUR_GODOT_REPO>/releases/download/latest/indus.apk
or
https://github.com/<YOUR_GODOT_ORG>/<YOUR_GODOT_REPO>/actions/runs/<RUN_ID>  → Artifacts → indus-apk
```

**We cannot provide a real APK link from this asset repo** — if you share your Godot repo URL, we can create the export workflow there and trigger it. Until then, test locally:

* Godot Editor → Play → walk inside Mahal (WASD + mouse, jump to test stairs).
* Android → `Project → Export → Android → Export With Debug` → install on device / `adb install builds/indus.apk`.

### Checklist before you report “done”

- [ ] `res://assets/downloaded_models/rajasthani_mahal.glb` loads without `ERR_FILE_NOT_FOUND`
- [ ] `StaticBody3D` children visible in Remote, `ConcavePolygonShape3D` data non-empty
- [ ] Player can pass all archways (no invisible wall) and climb stairs to roof
- [ ] Modular fallback tested on low-end device (if applicable)
- [ ] `main` pushed → Godot Action green → APK artifact downloadable → link pasted in PR description

---

## Files delivered in this branch

* `docs/models/buildings/rajasthani_mahal.glb` (alias, 4.2 MB)
* `docs/models/modular/{dome,pillar,wall,arch}_module.glb` aliases + `README.md`
* `examples/godot/main_mahal_godot.gd` — Task 2 loader with trimesh collisions
* `examples/godot/modular_mahal_builder.gd` — Task 3 runtime assembler
* `examples/godot/download_assets.{sh,ps1}` — Task 1 helpers
* `.github/workflows/sync-mahal-assets.yml.example` + `godot-export.yml.example` — Task 4 templates

Questions? Open an Issue with your Godot repo link and target Godot version (3.x / 4.x) — loader script currently targets **Godot 4.2+** (`GLTFDocument`, `create_trimesh_collision()`).
