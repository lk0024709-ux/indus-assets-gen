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
| **Animated player — 27 bones, 35 clips** | `models/characters/player_animated.glb` | 2.87 MB |
| ↳ build report (measured validation numbers) | `models/characters/player_animated.report.json` | 40 KB |
| **Clothing shirt** (same 27-bone rig) | `models/characters/clothing/clothing_shirt.glb` | 1.25 MB |
| **Clothing trousers** (same 27-bone rig) | `models/characters/clothing/clothing_pants.glb` | 1.14 MB |
| Base body (T-pose, unanimated) | `models/characters/body_base_female_midpoly.glb` | 2.0 MB |
| **Character pool (15)** | `models/characters/<name>.glb` — `female_casual`, `male_shirt`, `smooth_female_dress`, … | 51–183 KB each |
| Player Tactical character | `models/characters/player_tactical.glb` | 65 KB |
| **Trees (3)** | `models/nature/tree_pine.glb`, `tree_oak.glb`, `tree_palm.glb` | 7–38 KB |
| Elite Cargo Dropship (drop sequence) | `models/vehicles/plane_cargo_elite.glb` | 1.2 MB |

**Modular outfits.** `player_animated.glb`, `clothing/clothing_shirt.glb` and `clothing/clothing_pants.glb` each
contain the *same* 27-bone armature and all 35 clips, exported at the same origin. Drop them in as three imported scenes and, in the inspector, set
each garment's `Skeleton3D` to reuse the body's (`Skeleton3D > skeleton = NodePath("../BodyBase/Skeleton3D")`), or
simply instance the shirt and trousers as children of the body's `Skeleton3D` — every garment vertex carries the same
weights as the body vertices it was cut from, so they follow every clip with no retargeting. Swap outfits by
changing which garment scenes are children; the body never changes. All three files use a single solid material and
zero textures, so they cannot fall back to untextured grey in Godot.

Base URL: `https://lk0024709-ux.github.io/indus-assets-gen/models/`

> The retired building/nature/water/bridge sets and the old modular palace blocks are **no longer published**.
> Use the four assets above.

---

## 2 — The animated player (27 bones, 35 clips)

`player_animated.glb` is rebuilt on every push by
[`tools/retarget_animations.py`](tools/retarget_animations.py), which imports the Mixamo FBX motion set in
`docs/Motions/` and retargets it onto the repo's own 27-bone rig. The GLB carries the skinned body **and every clip
embedded as a named glTF animation** — there are no side-car animation files to wire up.

### Clips

| Group | Animation names |
|---|---|
| Idles | `Idle`, `IdleAiming`, `IdleCrouch`, `ProneIdle` |
| Walk (8-way) | `Walk_F`, `Walk_FL`, `Walk_FR`, `Walk_L`, `Walk_R`, `Walk_B`, `Walk_BL`, `Walk_BR` |
| Run (8-way) | `Run_F`, `Run_FL`, `Run_FR`, `Run_L`, `Run_R`, `Run_B`, `Run_BL`, `Run_BR` |
| Movement | `Sprint`, `CrouchWalk`, `DiveRoll`, `JumpUp`, `JumpLoop`, `JumpDown`, `TurnLeft90`, `TurnRight90` |
| Combat | `FireRifle`, `Reload`, `TossGrenade`, `HitReaction` |
| Deaths | `Dying`, `DeathFront`, `DeathBack` |

Looping clips (idles, walks, runs, sprint, crouch walk, jump loop) are keyed so the last frame joins the first
cleanly; the one-shot clips (dive roll, grenade, deaths, turns, jump up/down) are not meant to loop.

### What is guaranteed, and how it is measured

Every number below is re-measured on each build and written to `player_animated.report.json`; the build **fails**
rather than publishing if any of them regresses.

| Property | Limit | Measured |
|---|---|---|
| Planted foot floats above the floor | ≤ 20 mm | **7.0 mm** worst case (`DeathFront`); 33 of 35 clips ≤ 0.3 mm |
| Mesh sinks through the floor | ≤ 10 mm | **0.08 mm** worst case |
| Quaternion sign flips between keys | none (dot ≥ 0) | **+0.487** worst inter-key dot, verified *in the exported GLB* |
| Body-shell edge stretch in extreme poses | ≤ 1.75× | **1.285×** / 5.4 mm, over 46,980 edges × 70 poses |
| Influences per vertex | ≤ 4 | 4 |
| Unweighted vertices | 0 | 0 |

Feet are grounded against **the source clip's own foot clearance**, not against `z = 0` — so a genuine airborne
recoil frame stays airborne instead of being slammed onto the floor.

### Using it in Godot 4.x

The GLB imports as a `Node3D` → `Skeleton3D` → `MeshInstance3D`, with one `AnimationPlayer` holding all 35 clips.

```gdscript
@onready var anim: AnimationPlayer = $player_animated/AnimationPlayer
@onready var skel: Skeleton3D = $player_animated/Skeleton3D

func _ready() -> void:
    # Loop the locomotion clips; the one-shots are left as-is.
    for name in ["Idle", "IdleAiming", "IdleCrouch", "ProneIdle", "Sprint", "CrouchWalk", "JumpLoop"]:
        anim.get_animation(name).loop_mode = Animation.LOOP_LINEAR
    for dir in ["F", "FL", "FR", "L", "R", "B", "BL", "BR"]:
        anim.get_animation("Walk_%s" % dir).loop_mode = Animation.LOOP_LINEAR
        anim.get_animation("Run_%s" % dir).loop_mode = Animation.LOOP_LINEAR
    anim.play("Idle")

func equip(garment_scene: PackedScene) -> void:
    # The garment carries the identical 27-bone rig, so it just re-uses the
    # body's skeleton -- no retargeting, no per-clip fixups.
    var g := garment_scene.instantiate()
    skel.add_child(g)
    for mi in g.find_children("*", "MeshInstance3D"):
        mi.skeleton = mi.get_path_to(skel)
```

Because the garments were cut from the body and inherit its weights vertex-for-vertex, they deform identically in
all 35 clips. Swap outfits by adding/removing garment children; the body never changes.

Root motion: `DiveRoll`, the three jumps and the three deaths translate the hips in world space; every other clip is
authored **in place**, so drive those from your own `CharacterBody3D` velocity.

---

## 3 — Download the assets

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

## 4 — Import settings in Godot 4.x

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

## 5 — Load the Mahal

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

## 6 — Place the modular buildings

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

## 7 — Terrain

| File | Size | Notes |
|---|---|---|
| `terrain_ground.glb` | 1000 × 1000 m | flat base island |
| `terrain_hill_large.glb` | 80 × 80 × 40 m | jagged mountain, rock + grass |
| `terrain_plateau.glb` | 200 × 200 × 15 m | ramps on all four sides |
| `terrain_valley.glb` | 200 × 200 × 15 m | 15 m V-shaped cut |

All four are origin bottom-centre and tile edge-to-edge, so you can compose a map from a handful of copies. Generate
trimesh collision once per tile at load time (or bake a NavigationMesh from them).

---

## 8 — Checklist

- [ ] `res://assets/downloaded_models/rajasthani_mahal_mega.glb` loads without `ERR_FILE_NOT_FOUND`
- [ ] Mahal sits at `(0,0,0)` with its floor flush on the terrain
- [ ] Player can walk through the gateway arch, into the darbar and around the courtyard
- [ ] Player can enter each modular building through a doorway and climb its stairs
- [ ] Old procedural Mahal / building calls removed from `main.gd`
- [ ] `player_animated.glb` imports with **27 bones** and **35 animations** in the `AnimationPlayer`
- [ ] Locomotion clips set to `LOOP_LINEAR`; feet stay planted (no sliding or floating) on `Walk_F` and `Run_F`
- [ ] Shirt and trousers re-parented to the body's `Skeleton3D` deform identically through `DiveRoll` and `ProneIdle`
