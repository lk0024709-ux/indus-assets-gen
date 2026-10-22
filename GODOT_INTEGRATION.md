# Godot Integration — Grand Mahal, Modular Buildings, Terrain

This repo (`lk0024709-ux/indus-assets-gen`) is the **3D asset pipeline**. Its GitHub Action generates the GLBs and
deploys the web viewer to GitHub Pages; it does **not** build a Godot APK. Your game repo consumes the published `.glb`
URLs below.

**Live viewer:** https://lk0024709-ux.github.io/indus-assets-gen/

---

## 1 — What is published

| Asset | File on Pages | Size |
|---|---|---|
| Grand Mahal (assembled palace) | `models/mahal/rajasthani_mahal_mega.glb` | ~4.0 MB |
| Mahal rooms (4 walk-in blocks) | `models/mahal/rooms/room_*.glb` | 0.2–0.7 MB each |
| 11 Modular Buildings | `models/buildings_modular/<name>.glb` | 0.08–0.45 MB each |
| 4 Terrain tiles | `models/terrain/terrain_*.glb` | 0.45–2.1 MB each |
| Mount Abu hill station | `models/terrain/terrain_mount_abu.glb` | 2.1 MB (visual) |
| Mount Abu collider | `models/terrain/terrain_mount_abu_collision.glb` | 0.53 MB (concave, no vegetation) |
| Elite Cargo Dropship (drop sequence) | `models/vehicles/plane_cargo_elite.glb` | 1.2 MB |

Base URL: `https://lk0024709-ux.github.io/indus-assets-gen/models/`

> The retired building/nature/water/bridge sets and the old modular palace blocks are **no longer published**.
> Use the four assets above.

---

## 2 — Download the assets

Copy `examples/godot/download_assets.sh` (Linux/macOS) or `download_assets.ps1` (Windows) into your Godot project root
and run it. Files land in `res://assets/downloaded_models/`:

```
assets/downloaded_models/
  rajasthani_mahal_mega.glb
  house_blue.glb … tower_sniper.glb      (11 buildings)
  terrain/terrain_ground.glb, terrain_hill_large.glb, terrain_plateau.glb, terrain_valley.glb
```

Or fetch them by hand:

```bash
curl -L -o assets/downloaded_models/rajasthani_mahal_mega.glb \
  https://lk0024709-ux.github.io/indus-assets-gen/models/mahal/rajasthani_mahal_mega.glb
```

**Auto-sync:** copy `.github/workflows/sync-mahal-assets.yml.example` into your game repo as
`.github/workflows/sync-mahal-assets.yml` — it refreshes the assets daily and on demand, and commits them.

---

## 3 — Import settings in Godot 4.x

Select each `.glb` → **Import** tab:

| Setting | Value | Why |
|---|---|---|
| Root Type | `Node3D` | keeps the scene hierarchy intact |
| Generate Collisions | **Off** | we build accurate trimesh at runtime (convex hulls seal doorways and arches) |
| Meshes → Ensure Tangents | Off | materials are solid colours, no normal maps |
| Scale | 1.0 | the GLBs are authored in metres |

Every asset has its **origin at bottom-centre `(0, 0, 0)`**, so dropping it at `Vector3.ZERO` puts its floor exactly on
your ground plane — no offset needed.

---

## 4 — Load the Mahal

`examples/godot/main_mahal_godot.gd` is a drop-in `Node3D` script (`class_name MainMahalLoader`):

* resolves `res://assets/downloaded_models/rajasthani_mahal_mega.glb`,
* instances it at `Vector3.ZERO`,
* walks every `MeshInstance3D` and creates a `StaticBody3D` + `ConcavePolygonShape3D` (trimesh) so the darbar, courtyard
  arches, stairs and roof are all walkable,
* optionally re-bakes a `NavigationRegion3D`.

Attach it to your map root (or call `MainMahalLoader.load_full_mahal_at(Vector3.ZERO)` from `main.gd`) and remove the old
procedural Mahal call.

Key point: use **trimesh** (`mesh.create_trimesh_shape()`), never `ConvexPolygonShape3D` — convex shapes seal the
archways and doorways.

---

## 5 — Place the modular buildings

The 11 buildings are single joined meshes on a 15 m grid, each with real interior rooms, doorways and furniture:

| File | Footprint × height | Floors |
|---|---|---|
| `house_blue.glb` | 30.3 × 30.3 × 9.0 m | 2 |
| `school_yellow.glb` | 45.3 × 30.3 × 6.7 m | 2 |
| `apartment_green.glb` | 30.3 × 30.3 × 9.7 m | 3 |
| `warehouse_metal.glb` | 45.3 × 30.3 × 3.7 m | 1 |
| `cabin_wood.glb` | 15.3 × 15.2 × 6.0 m | 1 |
| `ruined_building.glb` | 30.3 × 30.3 × 6.1 m | 2 (no roof) |
| `shop_row.glb` | 30.3 × 17.4 × 6.0 m | 1 |
| `villa_white.glb` | 30.3 × 30.3 × 9.0 m | 2 |
| `farmhouse_stone.glb` | 30.3 × 15.3 × 6.0 m | 1 |
| `bunker_military.glb` | 15.3 × 15.2 × 3.7 m | 1 |
| `tower_sniper.glb` | 15.3 × 15.3 × 13.0 m | 4 |

Place them on a 15 m grid; the same trimesh-collision helper works for each one (interiors matter — players must be able
to walk in, up the stairs and out the back).

---

## 6 — Terrain

| File | Size | Notes |
|---|---|---|
| `terrain_ground.glb` | 1000 × 1000 m | flat base island |
| `terrain_hill_large.glb` | 80 × 80 × 40 m | jagged mountain, rock + grass |
| `terrain_plateau.glb` | 200 × 200 × 15 m | ramps on all four sides |
| `terrain_valley.glb` | 200 × 200 × 15 m | 15 m V-shaped cut |

All four are origin bottom-centre and tile edge-to-edge, so you can compose a map from a handful of copies. Generate
trimesh collision once per tile at load time (or bake a NavigationMesh from them).

---

## 7 — Checklist

- [ ] `res://assets/downloaded_models/rajasthani_mahal_mega.glb` loads without `ERR_FILE_NOT_FOUND`
- [ ] Mahal sits at `(0,0,0)` with its floor flush on the terrain
- [ ] Player can walk through the gateway arch, into the darbar and around the courtyard
- [ ] Player can enter each modular building through a doorway and climb its stairs
- [ ] Old procedural Mahal / building calls removed from `main.gd`
