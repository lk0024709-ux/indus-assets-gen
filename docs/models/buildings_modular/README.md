# Battle Royale Buildings — 11 blocks on a 15 m grid, with interior rooms

Assembled by `tools/assemble_buildings.py` from the kit in `../modules/` (15 m grid, 3 m storeys).
Every file is **one joined mesh** (walls, slabs, stairs, roof *and interior furniture*), flat shaded,
origin at **bottom-centre `(0, 0, 0)`**, exported with materials only (no textures).

| Building | Footprint | Floors | Size (m) | Walls | Roof | Rooms / floor | Furniture | Tris | Mats |
|---|---|---|---|---|---|---|---|---|---|
| `house_blue.glb` | 2×2 | 2 | 30.3 × 30.3 × 9.0 | Bright Blue `#2F6FBF` | Dark Grey `#43454A` hip | 3 (living + hallway + bedroom) | 2 beds, 2 tables, 2 counters, 2 shelves, 6 crates | 3,962 | 16 |
| `school_yellow.glb` | 3×2 | 2 | 45.3 × 30.3 × 6.7 | School Yellow `#E8C24A` | Flat Concrete + 0.4 m parapet | 7 (5 m central hallway + 6 classrooms) | 12 tables, 6 shelves, 3 counters, 6 crates | 6,894 | 13 |
| `apartment_green.glb` | 2×2 | 3 | 30.3 × 30.3 × 9.7 | Concrete Green `#5E9E5A` | Flat Concrete | 3 per floor (9 total) | 4 beds, 3 tables, 3 shelves, 2 counters, 9 crates | 6,416 | 16 |
| `warehouse_metal.glb` | 3×2 | 1 | 45.3 × 30.3 × 3.7 | Steel Blue `#4A7C99` | Rust Orange `#B4552E` | 7 (5 m aisle + 6 storage bays) | 18 crates, 4 shelves, 3 tables | 4,664 | 10 |
| `cabin_wood.glb` | 1×1 | 1 | 15.3 × 15.2 × 6.0 | Wood Brown `#8B5A2B` | Slanted Red `#8E3B31` hip | 2 (front room + bedroom) | 1 bed, 1 table, 1 counter, 1 shelf, 2 crates | 1,120 | 16 |
| `ruined_building.glb` | 2×2 | 2 | 30.3 × 30.3 × 6.1 | Damaged Concrete `#8C8C84` | **none** (open sky) | 3 per floor, shattered | 8 crates, 2 shelves + 9 rubble blocks | 3,736 | 7 |
| `shop_row.glb` | 2×1 | 1 | 30.3 × 17.4 × 6.0 | Off-White `#E8E4DA` | Slanted Red + 2 awnings | 2 shops with a connecting door | 4 counters, 3 shelves, 2 tables, 2 crates | 1,932 | 14 |
| `villa_white.glb` | L-shaped 2×2 | 2 | 30.3 × 30.3 × 9.0 | Off-White `#E8E4DA` | Flat Concrete + roof terrace | 3 per floor (6 total) | 4 sofas, 3 tables, 2 beds, 2 shelves, 2 counters, 4 crates | 4,398 | 18 |
| `farmhouse_stone.glb` | 2×1 | 1 | 30.3 × 15.3 × 6.0 | Brick Red `#9E4B3C` | Tiled Terracotta `#A9573C` hip | 2 (kitchen + bedroom) | 1 bed, 3 tables, 2 shelves, 5 crates | 1,980 | 13 |
| `bunker_military.glb` | 1×1 | 1 | 15.3 × 15.2 × 3.7 | Dark Camo Green + Camo Brown, **no windows** | Flat Concrete | 2 (bunk room + supply room) | 1 bed, 1 shelf, 6 crates | 1,700 | 12 |
| `tower_sniper.glb` | 1×1 | 4 | 15.3 × 15.3 × 13.0 | Concrete Grey `#B4B4AE` | **open top** + 0.95 m parapet | 2 per floor (8 total) | 2 crates, 1 shelf | 2,966 | 7 |

## Recipe summary

* **1×1 = 15 × 15 m** (`cabin_wood`, `bunker_military`, `tower_sniper`), **2×1 = 30 × 15 m** (`shop_row`,
  `farmhouse_stone`), **2×2 = 30 × 30 m** (`house_blue`, `apartment_green`, `ruined_building`, `villa_white`,
  L-shaped for the villa) and **3×2 = 45 × 30 m** (`school_yellow`, `warehouse_metal`).
* Single-storey blocks get a protruding plinth band; multi-storey blocks also get one storey band per floor,
  so the storeys read as separate floors from outside.
* Doors are always on the south face so every building can be dropped on a street grid and entered from the road;
  `warehouse_metal` also has a 6.0 × 2.6 m garage door and `shop_row` has two shopfronts with awnings.
* **Interior rooms.** Every floor is divided by 0.10 m partition walls (`mod_wall_partition` /
  `mod_wall_partition_door`), one material slot re-skinned in the building's own wall colour:
  * **2×2 blocks** — a 15 m wall down the middle (two 15 × 15 m halves) plus a 7.5 m jog wall, giving a
    living room, a 7.5 × 15 m hallway and a 7.5 × 7.5 m bedroom. The jog is mirrored automatically so the
    small room never lands on top of the staircase.
  * **3×2 blocks** — a **5 m central hallway** running the full 45 m length, with three rooms either side
    (12.5 × 15 m school classrooms, 10.5 m deep warehouse bays); every bay has its own doorway to the hall.
  * **1×1 huts** — one 15 m wall splitting the plan into a 15 × 7.5 m front room and a 15 × 7.5 m bedroom.
  * Each run gets exactly one 1.5 × 2.2 m doorway, and every doorway is checked to sit ≥ 1.1 m from any other
    wall and ≥ 2.4 m from the front door.
* **Build-time plan checks** (they abort the build): a partition may not cut the staircase, a doorway may not be
  buried in another wall or sit inside the stairwell, and every room must be graph-reachable from the entrance.
* **Build-time geometry checks**: ray casts at 2.65 m through each partition prove it is solid (bullets cannot pass),
  and ray casts through every doorway prove the openings are clear.
* Interior circulation: one 2.4 m wide staircase per storey in a reserved cell corner, with an exact Boolean
  hole in the slab above so the flight is walkable. `tower_sniper` therefore has 3 flights to its open top.
* Furniture is placed **per room** on a 2.6 m lattice 1.0 m off the walls, and every candidate is rejected if it
  overlaps a doorway (2.8 m), the staircase (1.2 m margin) or a partition (footprint maths, not just a centre
  point). Beds go in the bedroom, tables/shelves/counters in the living room & kitchen, and crates are dealt
  round-robin across all rooms so loot has to be searched for.
* `ruined_building` is the only file without a roof: three upper-floor bays are missing, 5 Boolean holes are punched
  through the remaining walls, 20 % of all faces are deleted (seed 11) and 9 rubble blocks are scattered inside.

## Engine notes

* One mesh per building → one `ConcavePolygonShape3D` (Godot) / one convex-per-face collider set (Unity) is enough.
  Windows, doorways and the 6 m garage opening are real holes, so interiors are enterable.
* Materials are plain Principled BSDF colours — no texture maps, no transparency, so these are safe on
  low-end / 4 GB RAM devices.
* Place at `(0, y, 0)` with the origin on the ground: the mesh never dips below `z = 0` (verified on re-import,
  `minZ = +0.000` for all 11 files).
