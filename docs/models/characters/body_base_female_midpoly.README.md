# Athletic female — custom uppercase humanoid rig

## Deliverables

- `body_base_female_midpoly.glb`: skinned T-pose runtime asset, **24,238 triangles** total.
- `body_base_female_midpoly.blend`: editable quad body, fitted sportswear, accessories and armature.
- `body_base_female_midpoly.validation.json`: topology, binding, smoothing and pose-check results.
- `body_base_female_midpoly.hierarchy.json`: exported schema companion; regression-tested against the GLB.
- `tools/generate_body_female_midpoly.py`: reproducible Blender 4.5.3 generator.
- `tools/test_body_female_midpoly.py`: dependency-free GLB regression tests.

This is a **stylized procedural base** guided by the supplied athletic female reference (black sports bra and shorts), not an exact face/body likeness, photo-real production sculpt, or reconstruction from the image. The explicit written request for a horizontal T-pose takes precedence over the A-pose in the sportswear image. Each hand now has a connected thumb and four individually separated fingers; each foot has five connected toes. The strict 27-bone schema is unchanged: fingers still share HAND/HANDTIP control rather than receiving individual phalange bones, so independent trigger-finger articulation is not provided. Eyes have inset geometry and upper/lower eyelid strips; the face has a geometric nose bridge, chin and lip shaping. Swept hair locks follow a scalp-fitted cap into a multi-lock ponytail. These are stylized geometry, not a facial animation system or an exact reference likeness.

## Exact bone schema

There are **27 joints**, with no additional root, twist or facial bones. `HIPS` is the root. The armature object itself is `Female_Rig`, not an extra bone.

```text
HIPS
├── SPINE_NAVAL
│   └── SPINE_CHEST
│       ├── NECK
│       │   └── HEAD
│       ├── CLAVICLE_L
│       │   └── SHOULDER_L
│       │       └── ELBOW_L
│       │           └── WRIST_L
│       │               └── HAND_L
│       │                   ├── HANDTIP_L
│       │                   └── THUMB_L
│       └── CLAVICLE_R
│           └── SHOULDER_R
│               └── ELBOW_R
│                   └── WRIST_R
│                       └── HAND_R
│                           ├── HANDTIP_R
│                           └── THUMB_R
├── HIP_L
│   └── KNEE_L
│       └── ANKLE_L
│           └── FOOT_L
└── HIP_R
    └── KNEE_R
        └── ANKLE_R
            └── FOOT_R
```

Spelling is deliberately **SPINE_NAVAL**, not NAVEL; **HIP**, not THIGH; `_L/_R`, not `_LEFT/_RIGHT`; **HIPS**, not PELVIS. These are the written lead-developer schema, even where the screenshot uses different labels.

**Compatibility caveat:** this is not native Adobe/Mixamo naming (e.g. `mixamorig:Hips`, `Spine`, `LeftArm`). The exact requested custom names and hierarchy are preserved; one-click Mixamo retargeting has **not** been demonstrated. Bone names alone do not guarantee retargeting, which also depends on joint axes, proportions, bind matrices, rest pose and importer mappings. The strict schema omits dedicated twist bones; no blanket promise of artifact-free extreme forearm twisting is made.

## Mesh and weighting

The underlying body is a single connected, closed surface: **9,640 quads / 19,280 triangles**, zero non-manifold edges and no detected nonadjacent rest-pose triangle intersections. Shoulder/limb/crotch/thumb branches share vertices; the body is not assembled from overlapping disconnected cylinders. Joint-following cross sections and Catmull–Clark subdivision produce the final body topology. Face poles are permitted; this is not a claim of animation-studio hand-retopology.

Sports bra and shorts use fitted outer quad surfaces with real 1.5 mm opening rims, rather than duplicating hidden inner faces. Their boundaries are relaxed along the body, then reprojected at a nominal 7 mm outer offset. Dense triangle samples check rest-pose skin clearance; this is not an all-pose cloth collision guarantee. Their skin weights are copied from the corresponding heat-bound body vertices, not independently heat-bound against disconnected garment shells. Head accessories use a rigid HEAD attachment, as expected for these simple non-expressive features. Surface-based garments and head pieces account for the remainder of the total triangle budget; the quoted closed-manifold/body-only checks do not describe every accessory as one continuous body.

The continuous body is bound using `bpy.ops.object.parent_set(type='ARMATURE_AUTO')`. Generation fails if any body vertex is unweighted; there is no distance-solver fallback. Shoulder, elbow and hip vertex selections receive four smoothing passes at factor 0.5, followed by four-influence limiting and normalization. **1,199** joint-area vertices are selected for smoothing. All exported mesh vertices have one to four normalized influences.

Shoulder, elbow, wrist, hip, knee, ankle and foot locations are generated from the same coordinates as the mesh profiles. The arms' rest axes are horizontal. The numerical pose smoke test bends both elbows and samples knee, shoulder and hip motion, checking finite coordinates and noncollapsed face areas. It does not certify every pose against intersections, clothing penetration, volume loss or candy-wrapper artifacts. No animation clips or weapon assets are included.

## Materials and dimensions

- Neutral skin: solid Principled PBR, metallic 0, roughness **0.6**. The body is deliberately flat/faceted shaded to reflect the latest low-poly reference; clothing and hair are smooth shaded.
- Black sportswear: solid PBR, roughness 0.68; no textures.
- Simple eyes, lips and dark brown hair use additional solid PBR materials.
- Body height: 1.80 m with soles at zero. Hair adds a small amount of overall height.
- Blender is Z-up, forward -Y; GLB is Y-up, forward +Z. Review the game controller's forward convention before integration.

## Rebuild and verify

```sh
blender --background --python tools/generate_body_female_midpoly.py
# or, with bpy==4.5.3 and Blender's Linux runtime libraries installed:
python tools/generate_body_female_midpoly.py
python -m unittest discover -s tools -p 'test_*midpoly.py' -v
python tools/validate_character_site.py
```

The generator clears the current scene, so use a fresh/background Blender process. The `.blend` preserves object parenting and Armature modifiers; the GLB places mesh nodes at scene root while retaining skins, avoiding inherited-transform ambiguity.

Khronos glTF Validator: **zero errors, zero warnings, zero informational issues**. All eleven Python export tests pass. The new female tests verify the full exact name/parent map, rest alignment, total triangle count, quad body, material settings and normalized four-influence skins.

## Web QA

The Pages viewer adds **Athletic Female** beside Base Body and Skeleton and selects the T-pose by default. Its hierarchy panel parses joint names/parentage from the **actual GLB**, not a hardcoded name list. The optional round markers show the female asset's rest-pose joint positions computed from GLB joint transforms; hover/focus for joint names. They are viewer overlays, not metal rings baked into the character mesh.

The browser integration test checks all 27 hierarchy entries, pivot visibility toggle, female loading, all three asset selections, static female controls, body Idle/Walk playback, mobile layout and request/page errors. Runtime Godot import/retargeting and weapon-grip integration have not been tested here.

GitHub Pages updates only after merge to `main` and a successful deployment. The Arena live preview is available before that. Blender source and metadata stay in Git; only the runtime GLBs and viewer files are staged for Pages.

## Athletic sculpt revision v2

This revision reshapes the **existing connected body surface** with smooth spatial muscle fields. It does not attach muscle spheres/cylinders or rely on painted normal maps. The fields add deltoid roundness, front biceps/back triceps volume, forearm fullness, quadriceps taper, posterior calf heads, a subtle patella/tibial ridge, paired abdominal relief/linea alba, obliques, gluteal projection and back/lat contours. Effects taper towards wrist/ankle joint regions.

Palms and forefeet now branch into real individual digit surfaces sharing webbing vertices. Cross-sectional tests on the **actual exported triangles** resolve four separated fingers (beyond the thumb) and five separated toes. The body remains one closed connected all-quad surface after subdivision, with zero detected nonadjacent rest-pose triangle intersections. Sampling of long straight segments was reduced while explicit elbow/knee support sections were retained to fund this detail within the 25k budget; no decimation is used.

All 12 principal shoulder/elbow/wrist/hip/knee/ankle pivots are numerically verified **inside** the body, with more than 5 mm surface clearance. The GLB's full exact 27-name/parent map remains regression-tested. Eleven Python tests also cover measured upper-arm-versus-elbow and calf-versus-distal-shin contours, normalized weights, cloth rest clearance and digit separation. Cloth sampling covers 30,688 bra and 40,768 shorts positions; recorded minimum signed clearance is approximately 0.64 mm / 2.58 mm respectively. This is a sampled rest-pose test, not a mathematically exhaustive collision proof.

Front, three-quarter and combined elbow/hip/knee bend renders were visually inspected. Neither these renders nor numerical tests prove "perfect" deformation in every extreme pose; arbitrary axial twists and Godot retargeting still need game-side QA. No new animations or expanded finger bones were added.

Viewer module and female GLB URLs carry `v=athletic-sculpt-v2` to avoid reusing the prior asset from browser caches. The download retains the same file name. The new version becomes public only after merge and successful Pages deployment.
