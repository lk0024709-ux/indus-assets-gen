# Mid-poly humanoid body base

## Deliverables

- `body_base_midpoly.glb` — Godot-ready mesh, skin, skeleton, Idle and Walk clips.
- `body_base_midpoly.blend` — editable **quad** mesh, armature parenting, heat weights, and actions.
- `body_base_midpoly.validation.json` — generated source-mesh validation results.
- Generator: `tools/generate_body_base_midpoly.py`.
- Export regression tests: `tools/test_body_base_midpoly.py`.

## Asset specification

| Property | Value |
| --- | --- |
| Height | 1.80 m, feet at ground, metre units |
| Rest pose | Symmetrical relaxed A-pose |
| Source mesh | 7,706 vertices, 7,704 quads |
| Export mesh | 15,408 triangles, one mesh/primitive |
| Connectivity | One connected component; zero boundary/non-manifold edges |
| Rest-pose intersections | Zero intersections between nonadjacent triangles |
| Skeleton | 20 bones, including a nondeforming Root |
| Binding | Blender `ARMATURE_AUTO`; no fallback solver |
| Weights | All vertices weighted and normalized; maximum four influences |
| Material | One solid neutral skin Principled PBR material, roughness 0.6, metallic 0 |
| Textures | None |
| Animation | Idle: 2 seconds; Walk: 1 second; sampled at 30 fps |

This is an unclothed, neutral stylized **blockout/base**, not a finished anatomical sculpt. It has a featureless head, simple mitten hands, and blockout feet; no individual fingers, toes, facial rig, clothes, hair, or genital detail. Walk is an in-place procedural starter animation, not mocap or an IK/foot-lock gait. Arms remain in a relaxed A-pose with a basic opposing swing.

### Construction and validation

The generator creates an explicit continuous surface, not joined overlapping primitives. Openings in the torso's side faces connect directly to arm rings. The pelvic rim splits into two leg rings sharing a crotch edge. Cross sections follow shoulders, elbows, hips, and knees; Catmull–Clark subdivision produces the final all-quad surface, including caps and junctions. Normals are recalculated before subdivision.

Before rigging, the script asserts the triangle budget, all-quad faces, one component, closed manifold edges, positive volume, and no nonadjacent triangle intersections. It calls `bpy.ops.object.parent_set(type='ARMATURE_AUTO')` and **fails** if any vertex is unweighted. Only influence limiting and normalization are applied afterward; no replacement/distance-based weighting is used.

Every Idle and Walk frame is evaluated for finite coordinates and noncollapsed face areas. This numerical smoke test is not a guarantee against intersections in arbitrary extreme poses. The rest pose was also visually inspected. Export regression tests check geometry, height, skin weights, material, skeleton size, animation movement, duration, and matching loop endpoints. The exported GLB passed Khronos glTF Validator with **zero errors and zero warnings**. Runtime Godot import/retargeting has not been tested in this environment.

GLB necessarily triangulates the mesh; use the `.blend` for editing quad loops. The GLB mesh is exported at scene root, linked to its skeleton by a skin, avoiding inherited skinned-mesh transform warnings. The `.blend` retains the requested mesh-to-armature parenting and Armature modifier.

## Regenerate

With Blender 4.5 LTS installed:

```sh
blender --background --python tools/generate_body_base_midpoly.py
```

Or in a Python 3.11 environment with Blender's wheel:

```sh
python -m venv .venv
.venv/bin/pip install bpy==4.5.3
.venv/bin/python tools/generate_body_base_midpoly.py
```

Linux wheel installations also require Blender's normal X11/OpenGL runtime libraries, even for headless use. Run from the repository; no asset downloads or third-party Blender add-ons are required. The generator replaces its named outputs and clears the current Blender scene, so run it in a fresh/background process rather than an unsaved working scene.

```sh
python -m unittest discover -s tools -p test_body_base_midpoly.py -v
```

## Godot 4

1. Copy `body_base_midpoly.glb` into your Godot project's assets directory.
2. Open the advanced import settings and enable looping for both `Idle` and `Walk`. glTF clips have matching endpoints but do not encode Godot's loop flag.
3. Instantiate the imported scene under your `CharacterBody3D`. Use the imported `AnimationPlayer`/`AnimationTree` for the two clips.
4. Mesh and skeleton are already bound; do not reparent the mesh to an individual bone. GLB is Y-up; Blender source is Z-up and faces -Y (exported forward is +Z). Rotate the character container if your controller uses Godot's conventional -Z forward.
5. For animation retargeting, configure a `SkeletonProfileHumanoid` BoneMap: Hips, Spine, Chest, Neck, Head; Shoulder.L/R, UpperArm.L/R, LowerArm.L/R, Hand.L/R; UpperLeg.L/R, LowerLeg.L/R, Foot.L/R. Names are intentionally readable, not a claim of automatic Godot profile mapping.
6. In Blender, choose `Idle` or `Walk` in the Action Editor to preview. Both actions are also retained as muted NLA tracks, preventing accidental mixed playback.
