# Source character assets

`Male_Suit.obj` / `Male_Suit.mtl` — the raw OBJ this repo converts into the
game-ready player character. **Do not load these in Godot:** the `.mtl`
references an external tie texture and the OBJ is Y-up with an arbitrary unit
scale, which is what caused the broken/magenta character in-engine.

Convert them instead:

```bash
pip install bpy
python tools/convert_character_obj.py --shading smooth
# -> docs/models/characters/player_tactical.glb
```

| Field | Value |
|---|---|
| Source | [Quaternius — Animated Men Characters](https://quaternius.com/) (`Male_Suit`) |
| License | **CC0 1.0 Universal** (public domain dedication) |
| Geometry | 1,044 verts · 1,165 faces · 7 material groups (`Skin`, `Shirt`, `Pants`, `Hair`, `Eyes`, `Details`, `TieTexture`) |
| Textures | none — the MTL only references `TieTexture` with a flat grey `Kd` |

The converter keys the new solid colours off those seven OBJ groups, so no
texture ever has to resolve at runtime.
