#!/usr/bin/env python3
"""Inspect a downloaded Blender skeleton, decimate only if >30k, export its rig.
Run with bpy 4.5.3 or blender -b --python tools/process_downloaded_skeleton.py.
Never overwrites the source .blend, creates bones, or fabricates animation clips.
Embedded scripts in the downloaded file are intentionally disabled.
"""
from pathlib import Path
import hashlib
import json
import struct
import bpy

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/models/characters/skeleton/skeleton_A_pose.blend'
OUTPUT = ROOT / 'docs/models/characters/skeleton_base_midpoly.glb'
REPORT = OUTPUT.with_suffix('.inspection.json')


def triangles(obj, evaluated=False):
    if evaluated:
        ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = ev.to_mesh()
        mesh.calc_loop_triangles()
        count = len(mesh.loop_triangles)
        ev.to_mesh_clear()
        return count
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def main():
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE), load_ui=False, use_scripts=False)
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    scene_meshes = sorted((o for o in bpy.context.scene.objects if o.type == 'MESH'), key=lambda o: o.name)
    armatures = sorted((o for o in bpy.data.objects if o.type == 'ARMATURE'), key=lambda o: o.name)
    action_info = []
    for action in bpy.data.actions:
        # This source is a legacy Action; use its actual F-curves, not its name,
        # to distinguish a rig animation from a curve-evaluation placeholder.
        curves = list(action.fcurves)
        action_info.append(dict(name=action.name, id_root=action.id_root,
            frame_range=list(action.frame_range), fcurves=len(curves),
            keyframes=sum(len(f.keyframe_points) for f in curves),
            paths=sorted({f.data_path for f in curves}),
            object_users=[o.name for o in bpy.data.objects if o.animation_data and o.animation_data.action == action],
            data_users=[d.name for d in bpy.data.curves if d.animation_data and d.animation_data.action == action]))
    counts = {o.name: triangles(o) for o in scene_meshes}
    evaluated_before = sum(triangles(o, True) for o in scene_meshes)
    geometry = [o for o in scene_meshes if counts[o.name] > 0]
    used_rigs = {m.object for o in geometry for m in o.modifiers if m.type == 'ARMATURE' and m.object}
    rig_actions = {a.name for r in used_rigs if r.animation_data for a in
        ([r.animation_data.action] if r.animation_data.action else []) +
        [strip.action for track in r.animation_data.nla_tracks for strip in track.strips if strip.action]}
    report = dict(source=str(SOURCE.relative_to(ROOT)), source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        blender=bpy.app.version_string,
        armatures=[dict(name=o.name, bones=len(o.data.bones), deform_bones=sum(b.use_deform for b in o.data.bones)) for o in armatures],
        actions=action_info, armature_actions=sorted(rig_actions),
        source_mesh_objects=len(scene_meshes), source_surface_mesh_objects=len(geometry),
        source_zero_triangle_mesh_objects=len(scene_meshes)-len(geometry),
        source_triangles=sum(counts.values()), source_evaluated_triangles=evaluated_before,
        mesh_triangles_before=counts,
        classification='rigged, no character animation clips' if used_rigs and not rig_actions else 'rigged' if used_rigs else 'static mesh',
        exported_armatures=sorted(r.name for r in used_rigs),
        excluded_armatures=sorted(r.name for r in armatures if r not in used_rigs))
    coords = []
    for obj in geometry:
        ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = ev.to_mesh()
        coords.extend(tuple(ev.matrix_world @ v.co) for v in mesh.vertices)
        ev.to_mesh_clear()
    report['source_world_bounds'] = {
        'min': [min(p[i] for p in coords) for i in range(3)],
        'max': [max(p[i] for p in coords) for i in range(3)],
    }
    report['source_height_m'] = report['source_world_bounds']['max'][2] - report['source_world_bounds']['min'][2]
    report['export_max_vertex_influences'] = 4
    report['decimation_applied'] = evaluated_before > 30000
    report['decimate_ratio'] = 25000 / evaluated_before if report['decimation_applied'] else 1.0
    if report['decimation_applied']:
        for obj in geometry:
            bpy.ops.object.select_all(action='DESELECT')
            obj.hide_set(False)
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            decimate = obj.modifiers.new('Midpoly_25k', 'DECIMATE')
            decimate.decimate_type = 'COLLAPSE'
            decimate.ratio = report['decimate_ratio']
            decimate.use_collapse_triangulate = True
            # Reduce undeformed coordinates; preserve the existing Armature
            # modifier and vertex groups rather than freezing the posed mesh.
            while obj.modifiers.find(decimate.name) > 0:
                bpy.ops.object.modifier_move_up(modifier=decimate.name)
            bpy.ops.object.modifier_apply(modifier=decimate.name)
    report['mesh_validation_repairs'] = {o.name: o.data.validate(clean_customdata=True) for o in geometry}
    report['mesh_triangles_after'] = {o.name: triangles(o) for o in geometry}
    report['optimized_triangles'] = sum(report['mesh_triangles_after'].values())
    assert not report['decimation_applied'] or 24000 <= report['optimized_triangles'] <= 26000, report['optimized_triangles']
    bpy.ops.object.select_all(action='DESELECT')
    for obj in geometry + list(used_rigs):
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(used_rigs), geometry[0])
    # glTF skins use world-space joints; mesh nodes should be scene roots.
    # Preserve the world transform while dropping only object parenting in
    # this transient export scene. Existing Armature modifiers stay intact.
    for obj in geometry:
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = world
    bpy.context.view_layer.update()
    # Do not export the Rigify template metarig, wire custom-shape widgets,
    # cameras, or unrelated curve action. Constraints/drivers remain in the
    # source; glTF gets skin joints and the evaluated current A-pose.
    bpy.ops.export_scene.gltf(filepath=str(OUTPUT), export_format='GLB', use_selection=True,
        export_skins=True, export_def_bones=True, export_animations=bool(rig_actions),
        export_current_frame=True, export_rest_position_armature=False,
        export_cameras=False, export_lights=False, export_materials='EXPORT',
        export_yup=True)
    raw = OUTPUT.read_bytes()
    size = struct.unpack_from('<I', raw, 12)[0]
    doc = json.loads(raw[20:20+size])
    report['export_triangles'] = sum(doc['accessors'][p['indices']]['count']//3 for m in doc['meshes'] for p in m['primitives'])
    report['export_meshes'] = len(doc.get('meshes', []))
    report['export_skins'] = len(doc.get('skins', []))
    report['export_joint_counts'] = [len(s['joints']) for s in doc.get('skins', [])]
    report['export_animations'] = [a.get('name') for a in doc.get('animations', [])]
    report['export_bytes'] = len(raw)
    assert report['export_triangles'] == report['optimized_triangles']
    assert not used_rigs or report['export_skins'], 'Existing source rig was lost'
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    lines = [
        '=== SKELETON SOURCE INSPECTION ===',
        'File: skeleton_A_pose.blend',
        f'Armature objects: {len(armatures)}',
        *[f'  {a.name}: {len(a.data.bones)} bones ({sum(b.use_deform for b in a.data.bones)} deform)' for a in armatures],
        f'Actions: {len(action_info)}',
        *[f"  {a['name']}: type={a['id_root']}, frames={a['frame_range'][0]:g}..{a['frame_range'][1]:g}, F-curves={a['fcurves']}, keyframes={a['keyframes']}, paths={','.join(a['paths'])}" for a in action_info],
        f'Character/armature Actions: {len(rig_actions)}',
        f'Scene mesh objects: {len(scene_meshes)} ({len(geometry)} surface meshes, {len(scene_meshes)-len(geometry)} zero-triangle widgets)',
        f'Total source triangles: {sum(counts.values()):,}',
        f'Total evaluated source triangles: {evaluated_before:,}',
        f"Classification: {report['classification']}",
        '=== OPTIMIZATION / EXPORT ===',
        f"Decimation applied: {report['decimation_applied']}",
        f"Decimate ratio: {report['decimate_ratio']:.9f}",
        f"Final triangles: {report['export_triangles']:,}",
        f"Exported armatures: {', '.join(report['exported_armatures']) or 'none'}",
        f"Excluded template armatures: {', '.join(report['excluded_armatures']) or 'none'}",
        f"Exported meshes: {report['export_meshes']}",
        f"Exported skins: {report['export_skins']}",
        f"Exported animation clips: {', '.join(report['export_animations']) or 'none'}",
        'Output: docs/models/characters/skeleton_base_midpoly.glb',
    ]
    text='\n'.join(lines)+'\n'
    REPORT.with_suffix('.txt').write_text(text)
    print(text, flush=True)


if __name__ == '__main__':
    main()
