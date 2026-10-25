# Downloaded A-pose skeleton — inspected and optimized

The active viewer asset is `skeleton_base_midpoly.glb` in this directory, processed from the user-supplied `skeleton/skeleton_A_pose.blend`. This is **not** the earlier procedural skeleton.

## Exact findings

See `skeleton_base_midpoly.inspection.txt` for the exact printed report and `.inspection.json` for full per-object counts, source SHA-256, action channels/users, and export statistics.

- Source armatures: `metarig` (63 bones, 63 deform) and `rig` (388 bones, 65 deform).
- Source Actions: only `BézierCircleAction`, a curve `eval_time` F-curve with **zero keyframes**, frame range 0..0, not a character motion clip. No armature Actions, Idle, or Walk.
- Source scene: 158 mesh objects, including 28 surface meshes and 130 zero-triangle wire rig widgets. Total base and evaluated triangle counts both **112,361**.
- **Rigged, but no character animation clips.** It is not an unrigged/static source. The website displays its A-pose and disables motion controls rather than inventing animations from MP4s.
- Decimate COLLAPSE ratio 0.222497130 is applied to the undeformed geometry before each existing Armature modifier. Mesh validation cleans invalid mesh data in the transient processing scene.
- Final output: **24,970 triangles**, 28 meshes, 1 skin, **65 original deform joints**, no animations. The unbound Rigify template metarig, controller widgets, cameras and unrelated curve action are excluded from runtime export.

## Preservation and export

The source `.blend` is never saved or overwritten. No new armature, bones, weights, or animation are generated. Source embedded `rig_ui.py` is not executed. Rigify controls, constraints, and drivers remain available in the original `.blend`; glTF exports the skin deform hierarchy and evaluated current pose, not the full Blender control UI.

The glTF exporter keeps and normalizes the strongest four vertex influences for game compatibility; this is not a claim of rigid weight=1 skinning for this downloaded model. Mesh world transforms are preserved while exporting skinned mesh nodes at scene root, avoiding parent-transform ambiguity. The source material and scale are retained; source evaluated height is approximately 1.838 m.

The old nested procedural GLB has been removed from the hosted catalog. Its procedural `.blend`, generator and inventory are historical source references only and are not this asset's anatomy/rig report. Pages publishes only Base Body and the new root-level skeleton GLB. Source .blend files and inspection metadata are not included in the Pages runtime artifact.

## Reproduction

With Blender 4.5.3 / `bpy==4.5.3` installed:

```sh
blender --background --python tools/process_downloaded_skeleton.py
# or
python tools/process_downloaded_skeleton.py
python tools/validate_character_site.py
python -m unittest discover -s tools -p 'test_*midpoly.py' -v
```

Run in a fresh process: the script opens the supplied source file. Linux wheel installations require Blender's usual X11/OpenGL runtime libraries even when headless.

## QA

Khronos glTF Validator: **0 errors, 0 warnings**. Six Python regression tests cover both models, including source checksum, exact inspection findings, final triangle budget, original deform-joint names and normalized exported skin weights. Chromium integration verifies both asset loads, correct skeleton download URL, disabled skeleton animation controls, switching, body Idle/Walk playback, pause/resume, and mobile layout. The skeleton was visually inspected in the browser.

The CGTrader file was supplied by the user. No independent licensing/redistribution clearance is asserted; the asset owner's license governs public hosting and reuse. No MP4 video has been treated as skeletal animation data.
