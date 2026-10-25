#!/usr/bin/env python3
"""Build a continuous quad humanoid, heat-bind, animate, and export for Godot 4.
Run with Blender 4.5: blender -b --python tools/generate_body_base_midpoly.py
or: python tools/generate_body_base_midpoly.py (requires bpy==4.5.3).
No downloaded assets, voxel remesh, separate shells, or fallback skin weights.
"""
from pathlib import Path
import json
import math
import struct

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

OUT = Path(__file__).resolve().parents[1] / 'docs/models/characters'
NAME = 'body_base_midpoly'


def activate(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def build_body():
    # Explicit surface construction: torso side openings are bridged to arms;
    # the pelvic rim splits across a shared crotch bridge into two leg loops.
    # There are no overlapping primitives, weld tolerances, or remesh steps.
    verts, faces = [], []

    def vertex(p):
        verts.append(tuple(p))
        return len(verts) - 1

    def bridge(a, b):
        assert len(a) == len(b)
        for i in range(len(a)):
            j = (i + 1) % len(a)
            faces.append((a[i], a[j], b[j], b[i]))

    def sections(keys, per_segment):
        result = []
        for a, b in zip(keys, keys[1:]):
            for j in range(per_segment):
                t = j / per_segment
                result.append(tuple(x * (1 - t) + y * t for x, y in zip(a, b)))
        result.append(keys[-1])
        return result

    # x radius, y radius, z; an octagonal cage becomes rounded after subdivision.
    torso_keys = [(.16, .11, .94), (.16, .115, 1.02), (.135, .095, 1.12),
                  (.18, .12, 1.26), (.195, .115, 1.33), (.20, .105, 1.45),
                  (.065, .065, 1.50), (.067, .07, 1.55), (.092, .09, 1.60),
                  (.108, .105, 1.70), (.095, .095, 1.78)]
    rings = []
    # Shoulder openings must span the full unsplit 1.33 -> 1.45 section.
    profile = []
    for a, b in zip(torso_keys, torso_keys[1:]):
        profile.extend(sections([a, b], 1 if a[2] == 1.33 else 2)[:-1])
    profile.append(torso_keys[-1])
    arm_loops = {}
    for rx, ry, z in profile:
        ring = [vertex((rx * math.sin((i + .5) * math.pi / 4),
                        -ry * math.cos((i + .5) * math.pi / 4), z)) for i in range(8)]
        if rings:
            previous = rings[-1]
            zprev = verts[previous[0]][2]
            for i in range(8):
                j = (i + 1) % 8
                loop = (previous[i], previous[j], ring[j], ring[i])
                if abs(zprev - 1.33) < 1e-6 and i in (1, 5):
                    arm_loops[1 if i == 1 else -1] = list(loop)
                else:
                    faces.append(loop)
        rings.append(ring)
    faces.append(tuple(reversed(rings[-1])))

    def limb(root, keys, samples, reference):
        data = sections(keys, samples)
        n = len(root)
        previous = root
        offset = None
        for k, d in enumerate(data):
            center = Vector(d[:3])
            before = Vector(data[max(0, k - 1)][:3])
            after = Vector(data[min(len(data) - 1, k + 1)][:3])
            tangent = (after - before).normalized()
            ref = Vector(reference)
            u = (ref - tangent * ref.dot(tangent)).normalized()
            v = tangent.cross(u).normalized()
            if offset is None:
                # Match the root perimeter to the new tube, including winding.
                angles = [math.atan2((Vector(verts[i]) - center).dot(v),
                                     (Vector(verts[i]) - center).dot(u)) for i in root]
                order = sorted(range(n), key=lambda i: angles[i])
                previous = [root[i] for i in order]
                offset = sum(angles[order[i]] - 2 * math.pi * i / n for i in range(n)) / n
            ring = [vertex(center + u * (d[3] * math.cos(offset + 2 * math.pi * i / n))
                           + v * (d[4] * math.sin(offset + 2 * math.pi * i / n))) for i in range(n)]
            bridge(previous, ring)
            previous = ring
        faces.append(tuple(reversed(previous)))

    bottom = rings[0]
    # Bottom has front-right and front-left vertices, rather than front centre.
    # Add shared front/back midpoints so each leg gets a six-sided perimeter.
    front = vertex((0, -.11 * math.cos(math.pi / 8), .94))
    back = vertex((0, .11 * math.cos(math.pi / 8), .94))
    # Insert midpoint into adjacent torso faces to retain a conforming surface.
    for edge, mid in (((7, 0), front), ((3, 4), back)):
        a, b = bottom[edge[0]], bottom[edge[1]]
        for fi, face in enumerate(faces):
            if a in face and b in face:
                # Insert into the adjacent face as well: subdivision turns
                # this conforming five-sided cage face into final quads.
                f = list(face)
                for j in range(len(f)):
                    if {f[j], f[(j + 1) % len(f)]} == {a, b}:
                        f.insert(j + 1, mid)
                        faces[fi] = tuple(f)
                        break
                break
    right = [front, bottom[0], bottom[1], bottom[2], bottom[3], back]
    left = [back, bottom[4], bottom[5], bottom[6], bottom[7], front]
    # Each leg loop closes directly from back to front: that single shared
    # crotch edge is incident on exactly two faces (one per leg).
    for s, root in ((1, right), (-1, left)):
        limb(root, [(s * .115, 0, .87, .105, .105),
                    (s * .12, 0, .73, .105, .105),
                    (s * .12, -.025, .55, .068, .070),
                    (s * .12, -.025, .50, .067, .068),
                    (s * .12, .005, .35, .078, .078),
                    (s * .12, 0, .14, .047, .05),
                    (s * .12, -.045, .07, .062, .055),
                    (s * .12, -.14, .065, .067, .05),
                    (s * .12, -.235, .065, .057, .038)], 2, (1, 0, 0))
        limb(arm_loops[s], [(s * .24, 0, 1.385, .083, .083),
                    (s * .32, 0, 1.30, .077, .077),
                    (s * .42, -.015, 1.215, .055, .055),
                    (s * .45, -.015, 1.185, .055, .055),
                    (s * .52, -.01, 1.12, .059, .059),
                    (s * .60, 0, 1.04, .035, .035),
                    (s * .65, -.005, .995, .034, .062),
                    (s * .71, -.005, .94, .031, .054)], 2, (0, 1, 0))
    mesh = bpy.data.meshes.new('ContinuousBodyCage')
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new('Body_Base_Midpoly', mesh)
    bpy.context.collection.objects.link(obj)
    activate(obj)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    sub = obj.modifiers.new('Quad joint loops', 'SUBSURF')
    sub.levels = 2
    bpy.ops.object.modifier_apply(modifier=sub.name)
    low = min(v.co.z for v in obj.data.vertices)
    high = max(v.co.z for v in obj.data.vertices)
    scale = 1.8 / (high - low)
    for v in obj.data.vertices:
        v.co = Vector((v.co.x * scale, v.co.y * scale, (v.co.z - low) * scale))
    for p in obj.data.polygons:
        p.use_smooth = True
    mat = bpy.data.materials.new('Neutral_Skin')
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (.53, .32, .22, 1)
    bsdf.inputs['Roughness'].default_value = .6
    bsdf.inputs['Metallic'].default_value = 0
    mat.diffuse_color = (.53, .32, .22, 1)
    obj.data.materials.append(mat)
    return obj, lambda p: (p[0] * scale, p[1] * scale, (p[2] - low) * scale)

def topology(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    unseen = set(bm.verts)
    components = 0
    while unseen:
        components += 1
        stack = [unseen.pop()]
        while stack:
            for e in stack.pop().link_edges:
                for v in e.verts:
                    if v in unseen:
                        unseen.remove(v)
                        stack.append(v)
    result = dict(vertices=len(bm.verts), quads=sum(len(f.verts) == 4 for f in bm.faces),
                  faces=len(bm.faces), triangles=sum(len(f.verts) - 2 for f in bm.faces),
                  connected_components=components,
                  non_manifold_edges=sum(not e.is_manifold for e in bm.edges),
                  signed_volume=bm.calc_volume(signed=True))
    bm.free()
    obj.data.calc_loop_triangles()
    triangles = [tuple(t.vertices) for t in obj.data.loop_triangles]
    tree = BVHTree.FromPolygons([v.co for v in obj.data.vertices], triangles,
                               all_triangles=True, epsilon=1e-8)
    intersections = {(min(a, b), max(a, b)) for a, b in tree.overlap(tree)
                     if a != b and not set(triangles[a]).intersection(triangles[b])}
    result['nonadjacent_triangle_intersections'] = len(intersections)
    assert not intersections, result
    assert components == 1, result
    assert result['non_manifold_edges'] == 0, result
    assert result['quads'] == result['faces'], result
    assert 15000 <= result['triangles'] <= 25000, result
    assert result['signed_volume'] > 0, result
    return result


def bind(obj, coord):
    arm = bpy.data.armatures.new('Humanoid')
    rig = bpy.data.objects.new('Body_Rig', arm)
    bpy.context.collection.objects.link(rig)
    activate(rig)
    bpy.ops.object.mode_set(mode='EDIT')

    def bone(name, head, tail, parent=None, deform=True):
        b = arm.edit_bones.new(name)
        b.head, b.tail = coord(head), coord(tail)
        if parent:
            b.parent = arm.edit_bones[parent]
        b.use_deform = deform

    bone('Root', (0, 0, .015), (0, 0, .16), deform=False)
    bone('Hips', (0, 0, .90), (0, 0, 1.04), 'Root')
    bone('Spine', (0, 0, 1.04), (0, 0, 1.23), 'Hips')
    bone('Chest', (0, 0, 1.23), (0, 0, 1.43), 'Spine')
    bone('Neck', (0, 0, 1.43), (0, 0, 1.56), 'Chest')
    bone('Head', (0, 0, 1.56), (0, 0, 1.78), 'Neck')
    for s, side in ((1, 'L'), (-1, 'R')):
        def p(x, y, z):
            return (s * x, y, z)
        bone('Shoulder.' + side, p(.05, 0, 1.40), p(.205, 0, 1.40), 'Chest')
        bone('UpperArm.' + side, p(.205, 0, 1.40), p(.435, -.015, 1.20), 'Shoulder.' + side)
        bone('LowerArm.' + side, p(.435, -.015, 1.20), p(.60, 0, 1.04), 'UpperArm.' + side)
        bone('Hand.' + side, p(.60, 0, 1.04), p(.70, -.005, .95), 'LowerArm.' + side)
        bone('UpperLeg.' + side, p(.115, 0, .88), p(.12, -.025, .52), 'Hips')
        bone('LowerLeg.' + side, p(.12, -.025, .52), p(.12, 0, .13), 'UpperLeg.' + side)
        bone('Foot.' + side, p(.12, 0, .13), p(.12, -.21, .06), 'LowerLeg.' + side)
    bpy.ops.object.mode_set(mode='OBJECT')
    activate(rig)
    obj.select_set(True)
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    deform = {g.index for g in obj.vertex_groups if g.name in arm.bones and arm.bones[g.name].use_deform}
    missing = [v.index for v in obj.data.vertices if sum(g.weight for g in v.groups if g.group in deform) < 1e-6]
    assert not missing, f'ARMATURE_AUTO failed: {len(missing)} unweighted vertices; no fallback allowed'
    # Standard glTF/Godot four-influence budget, preserving the heat solution.
    activate(obj)
    bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=4)
    bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    assert all(abs(sum(g.weight for g in v.groups) - 1) < 1e-5 for v in obj.data.vertices)
    rig.show_in_front = True
    return rig


def animate(rig):
    scene = bpy.context.scene
    scene.render.fps = 30
    rig.animation_data_create()
    for name, end in (('Idle', 61), ('Walk', 31)):
        action = bpy.data.actions.new(name)
        rig.animation_data.action = action
        for f in range(1, end + 1):
            t = 2 * math.pi * (f - 1) / (end - 1)
            for pb in rig.pose.bones:
                pb.rotation_mode = 'XYZ'
                pb.rotation_euler = (0, 0, 0)
                pb.location = (0, 0, 0)
            if name == 'Idle':
                rig.pose.bones['Chest'].rotation_euler.x = .015 * math.sin(t)
                rig.pose.bones['Head'].rotation_euler.z = .012 * math.sin(t)
                rig.pose.bones['Hips'].location.y = .002 * math.sin(t)
            else:
                rig.pose.bones['Hips'].location.y = .009 * (1 - math.cos(2 * t))
                for side, phase in (('L', t), ('R', t + math.pi)):
                    rig.pose.bones['UpperLeg.' + side].rotation_euler.x = .40 * math.sin(phase)
                    rig.pose.bones['LowerLeg.' + side].rotation_euler.x = -.60 * max(0, -math.sin(phase))
                    rig.pose.bones['Foot.' + side].rotation_euler.x = .12 * math.sin(phase)
                    rig.pose.bones['UpperArm.' + side].rotation_euler.x = -.26 * math.sin(phase)
                    rig.pose.bones['LowerArm.' + side].rotation_euler.x = -.10 - .08 * max(0, math.sin(phase))
            for pb in rig.pose.bones:
                pb.keyframe_insert('rotation_euler', frame=f, group=pb.name)
                pb.keyframe_insert('location', frame=f, group=pb.name)
        track = rig.animation_data.nla_tracks.new()
        track.name = name
        track.strips.new(name, 1, action)
        track.mute = True
    rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
    scene.frame_set(1)


def deformation_checks(obj, rig):
    """Sample every animation frame: finite positions and noncollapsed faces.
    This is a numerical smoke test, not a guarantee against all pose intersections.
    """
    minimum_area = float('inf')
    for name in ('Idle', 'Walk'):
        rig.animation_data.action = bpy.data.actions[name]
        for frame in range(1, 62 if name == 'Idle' else 32):
            bpy.context.scene.frame_set(frame)
            evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            assert all(math.isfinite(c) for v in mesh.vertices for c in v.co)
            minimum_area = min(minimum_area, min(p.area for p in mesh.polygons))
            evaluated.to_mesh_clear()
    assert minimum_area > 1e-10, minimum_area
    rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
    bpy.context.scene.frame_set(1)
    return minimum_area


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    body, coord = build_body()
    report = topology(body)
    print('TOPOLOGY', report, flush=True)
    rig = bind(body, coord)
    animate(rig)
    report['minimum_animated_face_area_m2'] = deformation_checks(body, rig)
    report.update(height_m=1.8, bones=len(rig.data.bones), binding='ARMATURE_AUTO',
                  unweighted_vertices=0, max_influences=4, animations={'Idle': 2.0, 'Walk': 1.0},
                  blender=bpy.app.version_string)
    activate(rig)
    body.select_set(True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / (NAME + '.blend')))
    # glTF skins use world-space joint matrices. Export the mesh at scene root
    # to avoid NODE_SKINNED_MESH_NON_ROOT and ambiguous inherited transforms.
    # The editable .blend retains the requested armature parenting.
    world = body.matrix_world.copy()
    body.parent = None
    body.matrix_world = world
    try:
        bpy.ops.export_scene.gltf(filepath=str(OUT / (NAME + '.glb')), export_format='GLB',
            use_selection=True, export_animations=True, export_animation_mode='ACTIONS',
            export_skins=True, export_yup=True, export_materials='EXPORT',
            export_def_bones=False, export_force_sampling=True)
    finally:
        body.parent = rig
        body.matrix_world = world
    raw = (OUT / (NAME + '.glb')).read_bytes()
    size, kind = struct.unpack_from('<I4s', raw, 12)
    assert kind == b'JSON'
    gltf = json.loads(raw[20:20 + size])
    assert {a['name'] for a in gltf['animations']} == {'Idle', 'Walk'}
    assert len(gltf['skins']) == 1 and len(gltf['meshes']) == 1
    assert len(gltf['materials']) == 1 and not gltf.get('textures')
    report['glb_bytes'] = len(raw)
    (OUT / (NAME + '.validation.json')).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
