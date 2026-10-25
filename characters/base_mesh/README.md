# Base mesh drop-point

Put the AI-generated player body here and `tools/retarget_animations.py` will
use it instead of the committed fallback rig. The first matching file wins,
preferred in this order:

    .glb  .gltf  .fbx  .blend  .obj

**The mesh must already be skinned to the 27-bone rig** whose exact bone names
and parentage are listed in
`docs/models/characters/body_base_female_midpoly.hierarchy.json`. The pipeline
reuses a supplied 27-bone armature verbatim; if the import has no armature, or
one that does not match, the build fails loudly rather than guessing.

If this directory holds no model, the pipeline falls back to
`docs/models/characters/body_base_female_midpoly.glb`, which already carries
that exact rig. **That fallback is deliberate: CI must never break just because
nobody has uploaded a mesh yet.**

Models dropped here are the one thing under `characters/` that *is* committed —
everything else in this directory is a build product and is gitignored.
