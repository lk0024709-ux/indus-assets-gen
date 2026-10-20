# Battle Royale Buildings — 11 blocks on a 15 m grid

Assembled by `tools/assemble_buildings.py` from the kit in `../modules/` (15 m grid, 3 m storeys).
Every file is **one joined mesh** (walls, slabs, stairs, roof *and interior furniture*), flat shaded,
origin at **bottom-centre `(0, 0, 0)`**, exported with materials only (no textures).

| Building | Footprint | Floors | Size (m) | Walls | Roof | Furniture | Tris | Mats |
|---|---|---|---|---|---|---|---|---|
| `house_blue.glb` | 2×2 | 2 | 30.3 × 30.3 × 9.0 | Bright Blue `#2F6FBF` | Dark Grey `#43454A` hip | 1 bed, 2 crates | 2,638 | 9 |
| `school_yellow.glb` | 3×2 | 2 | 45.3 × 30.3 × 6.7 | School Yellow `#E8C24A` | Flat Concrete `#A8A8A2` + 0.4 m parapet | 8 tables, 4 shelves | 4,494 | 8 |
| `apartment_green.glb` | 2×2 | 3 | 30.3 × 30.3 × 9.7 | Concrete Green `#5E9E5A` | Flat Concrete `#A8A8A2` | 4 beds, 6 crates | 4,964 | 9 |
| `warehouse_metal.glb` | 3×2 | 1 | 45.3 × 30.3 × 3.7 | Steel Blue `#4A7C99` | Rust Orange `#B4552E` | 14 crates | 3,104 | 6 |
| `cabin_wood.glb` | 1×1 | 1 | 15.3 × 15.2 × 6.0 | Wood Brown `#8B5A2B` | Slanted Red `#8E3B31` hip | 1 bed, 1 table | 684 | 9 |
| `ruined_building.glb` | 2×2 | 2 | 30.3 × 30.3 × 6.1 | Damaged Concrete `#8C8C84` | **none** (open sky) | 6 crates + 9 rubble | 3,129 | 5 |
| `shop_row.glb` | 2×1 | 1 | 30.3 × 17.4 × 6.0 | Off-White `#E8E4DA` | Slanted Red `#8E3B31` + 2 awnings | 4 counters, 6 shelves, 2 tables | 1,628 | 12 |
| `villa_white.glb` | L-shaped 2×2 | 2 | 30.3 × 30.3 × 9.0 | Off-White `#E8E4DA` | Flat Concrete + roof terrace/pergola | 4 sofas, 3 tables, 2 beds | 3,350 | 12 |
| `farmhouse_stone.glb` | 2×1 | 1 | 30.3 × 15.3 × 6.0 | Brick Red `#9E4B3C` | Tiled Terracotta `#A9573C` hip | 4 tables, 5 crates | 1,616 | 8 |
| `bunker_military.glb` | 1×1 | 1 | 15.3 × 15.2 × 3.7 | Dark Camo Green `#414B36` + Camo Brown bands, **no windows** | Flat Concrete `#A8A8A2` | 8 crates, 4 shelves | 1,504 | 9 |
| `tower_sniper.glb` | 1×1 | 4 | 15.3 × 15.3 × 13.0 | Concrete Grey `#B4B4AE` | **open top** + 0.95 m parapet | 1 crate | 2,422 | 5 |

## Recipe summary

* **1×1 = 15 × 15 m** (`cabin_wood`, `bunker_military`, `tower_sniper`), **2×1 = 30 × 15 m** (`shop_row`,
  `farmhouse_stone`), **2×2 = 30 × 30 m** (`house_blue`, `apartment_green`, `ruined_building`, `villa_white`,
  L-shaped for the villa) and **3×2 = 45 × 30 m** (`school_yellow`, `warehouse_metal`).
* Single-storey blocks get a protruding plinth band; multi-storey blocks also get one storey band per floor,
  so the storeys read as separate floors from outside.
* Doors are always on the south face so every building can be dropped on a street grid and entered from the road;
  `warehouse_metal` also has a 6.0 × 2.6 m garage door and `shop_row` has two shopfronts with awnings.
* Interior circulation: one 2.4 m wide staircase per storey in a reserved cell corner, with an exact Boolean
  hole in the slab above so the flight is walkable. `tower_sniper` therefore has 3 flights to its open top.
* Furniture sits on a 3 × 5 anchor lattice per cell (2.5 m pitch), never within 2.4 m of a doorway or 3.0 m of a
  staircase, so no piece blocks circulation. Beds/sofas are on upper floors, crates/tables/counters on the ground.
* `ruined_building` is the only file without a roof: three upper-floor bays are missing, 5 Boolean holes are punched
  through the remaining walls, 20 % of all faces are deleted (seed 11) and 9 rubble blocks are scattered inside.

## Engine notes

* One mesh per building → one `ConcavePolygonShape3D` (Godot) / one convex-per-face collider set (Unity) is enough.
  Windows, doorways and the 6 m garage opening are real holes, so interiors are enterable.
* Materials are plain Principled BSDF colours — no texture maps, no transparency, so these are safe on
  low-end / 4 GB RAM devices.
* Place at `(0, y, 0)` with the origin on the ground: the mesh never dips below `z = 0` (verified on re-import,
  `minZ = +0.000` for all 11 files).
