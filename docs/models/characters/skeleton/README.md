> **Historical procedural source only.** The procedural GLB described below is no longer hosted. The active viewer now uses the supplied CGTrader A-pose file, processed to `../skeleton_base_midpoly.glb`. See [the current inspection and export report](../skeleton_base_midpoly.README.md). Do not apply the historical 151-bone/375-piece statistics below to the downloaded model.

# Anatomical skeleton — stylized mid-poly

## Files

- `skeleton_base_midpoly.glb`: runtime skeleton and articulated armature.
- `skeleton_base_midpoly.blend`: editable faceted source surfaces and armature.
- `skeleton_base_midpoly.validation.json`: face counts and per-piece anatomical inventory, including vertex ranges and corresponding rig bones.
- Generator: `tools/generate_skeleton_midpoly.py` (Blender/bpy 4.5.3).

## Geometry

24,816 triangles; 13,158 source vertices; 12,675 source faces, of which 10,272 (81%) are quads. UV-surface poles use triangles and sweep caps use polygons. No decimation, downloaded model, generated image-to-mesh, mitten hands, fused spine substitute, or solid ribcage substitute is used.

375 explicitly generated anatomical pieces share a single export mesh container. Pieces remain disconnected surfaces, not welded into a solid body. The source inventory retains all piece names, vertex ranges, and rig assignments; Blender's Separate by Loose Parts can extract the shells if needed. Anatomical articulations intentionally meet/intersect, rather than requiring a globally watertight union.

Included anatomy:

- Cranium with actual recessed orbital wells and nasal cavity; maxilla, zygomatic arches, mandible, and 28 individually modelled teeth. Teeth are stylized, not a complete 32-tooth adult dentition.
- 7 cervical, 12 thoracic, and 5 lumbar vertebrae, each with a body, neural arch, spinous process, and paired transverse processes. Five sacral segment forms and a coccyx complete the spine.
- 12 individually curved rib pairs, including short floating ribs 11/12; manubrium, sternal body, xiphoid.
- Separate iliac wings, pubic/ischial rami with open obturator regions, sacrum, acetabular forms.
- Clavicles, scapular blades/spines, humeri with condylar forms, radii, ulnae and olecranons.
- 8 carpals per hand; 5 metacarpals and 14 individual phalanges per hand (2 thumb, 3 each other finger).
- Femora with heads/condyles, patellae, tibiae, fibulae.
- 7 tarsals per foot; 5 metatarsals and 14 individual toe phalanges per foot.

This is a procedural **stylized approximation** guided by the supplied front reference, not an exact scan or a medically validated reconstruction. It has a simplified skull, teeth, and pelvis; the front reference cannot specify hidden anatomy. Bone heights reach approximately 1.80 m, with a small floor clearance.

## Rig and material

151 named hierarchical bones. Every mesh vertex has exactly one influence at weight **1.0**. No auto weighting, smoothing, or blended skin weights are used. Phalanges have their own hierarchical rig bones. Ribs follow corresponding thoracic bones, each vertebral component follows its named vertebra, and fused sacral/pelvic components follow their corresponding pelvic hierarchy. A posed finger smoke test verifies that rigid segment distances remain unchanged.

One off-white `Ivory_Bone` Principled PBR material, metallic 0, roughness 0.4, Blender subsurface weight 0.035. Subsurface appearance is renderer-dependent and not guaranteed to transfer identically through glTF/Godot. No textures.

No animation clips are included for this skeleton; it is an articulated rest-pose asset. Existing Base Body animations belong to a different rig and are not silently applied to the anatomical rig.

## Regeneration and QA

```sh
blender --background --python tools/generate_skeleton_midpoly.py
# or, in an environment with bpy==4.5.3:
python tools/generate_skeleton_midpoly.py
python -m unittest discover -s tools -p 'test_*midpoly.py' -v
python tools/validate_character_site.py
```

The generator clears the current scene; run in a fresh/background Blender process. It checks the triangle budget, finite vertices and exact rigid weighting, and tests a finger pose. Dependency-free GLB tests verify anatomical counts, rig joint names, every exported rigid weight, material, and exported triangle count. Khronos glTF Validator passed with **zero errors and zero warnings**. The front render was visually inspected; this does not certify medical accuracy or all possible joint poses.

The Pages viewer adds **Skeleton** beside **Base Body** and selects Skeleton by default for QA. Its animation controls are intentionally disabled in skeleton mode. The browser integration test loads both files, checks asset switching/download targets, verifies static skeleton mode, and preserves body Idle/Walk playback tests. Pages stages only the runtime GLB, not source `.blend` files or metadata. Feature-branch preview is immediately available in Arena; GitHub Pages updates after merge to `main` and successful deployment.
