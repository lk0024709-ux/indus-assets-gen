#!/usr/bin/env python3
"""Generate the custom 27-joint athletic female T-pose asset with heat weights.
Run: blender -b --python tools/generate_body_female_midpoly.py
or Python with bpy==4.5.3. Clears the scene; replaces only named outputs.
Names are the lead-developer custom schema, NOT native Mixamo bone names.
"""
from pathlib import Path
import json
import math
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
import bmesh
from mathutils import Vector
from generate_body_base_midpoly import activate, topology

OUT=Path(__file__).resolve().parents[1]/'docs/models/characters'
NAME='body_base_female_midpoly'
BONES=[]


def material(name, color, roughness):
    m=bpy.data.materials.new(name);m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=color
    bs.inputs['Roughness'].default_value=roughness
    bs.inputs['Metallic'].default_value=0
    m.diffuse_color=color
    return m


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
    torso_keys = [(.18, .115, .94), (.18, .12, 1.02), (.12, .085, 1.12),
                  (.145, .095, 1.26), (.165, .11, 1.33), (.18, .095, 1.45),
                  (.05, .05, 1.50), (.052, .052, 1.55), (.085, .082, 1.60),
                  (.108, .095, 1.695), (.080, .077, 1.775), (.026, .028, 1.805)]
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

    def limb(root, keys, samples, reference, thumb_side=None):
        data = sections(keys, samples)
        n = len(root)
        previous = root
        offset = None
        thumb_root = None
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
            if thumb_side and k == len(data)-4:
                candidates = list(range(len(faces)-n, len(faces)))
                fi = min(candidates, key=lambda i: sum(verts[v][1] for v in faces[i]))
                thumb_root = list(faces.pop(fi))
            previous = ring
        faces.append(tuple(reversed(previous)))
        if thumb_root:
            s = thumb_side
            limb(thumb_root, [(s*.795, -.041, 1.40, .017, .015),
                             (s*.80, -.063, 1.40, .015, .014),
                             (s*.825, -.085, 1.40, .011, .011)], 2, (0,0,1))

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
        limb(arm_loops[s], [(s * .215, 0, 1.40, .070, .070),
                    (s * .32, 0, 1.40, .063, .063),
                    (s * .445, 0, 1.40, .045, .045),
                    (s * .475, 0, 1.40, .045, .045),
                    (s * .57, 0, 1.40, .049, .049),
                    (s * .70, 0, 1.40, .029, .030),
                    (s * .74, 0, 1.40, .028, .028),
                    (s * .78, 0, 1.40, .041, .025),
                    (s * .85, 0, 1.40, .037, .022),
                    (s * .88, 0, 1.40, .028, .018)], 2, (0, 1, 0), thumb_side=s)
    mesh = bpy.data.meshes.new('FemaleContinuousQuadCage')
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new('Athletic_Female_Body', mesh)
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
    for vertex_data in obj.data.vertices:
        p = vertex_data.co
        if p.y < 0:
            # Paired pectoral volume under the sports bra, not separate shells.
            p.y -= .033*math.exp(-((abs(p.x)-.068)/.046)**2-((p.z-1.335)/.045)**2)
            # Nose bridge, cheek and chin shaping; a stylized face, no face rig.
            if 1.57 < p.z < 1.75:
                p.y -= .020*math.exp(-(p.x/.017)**2-((p.z-1.663)/.027)**2)
                p.y -= .007*math.exp(-((abs(p.x)-.044)/.025)**2-((p.z-1.648)/.026)**2)
        if .16 < p.z < .88:
            # Athletic legs: retain joint dimensions, slightly taper calves.
            p.x *= .98
    low = min(v.co.z for v in obj.data.vertices)
    high = max(v.co.z for v in obj.data.vertices)
    scale = 1.8 / (high - low)
    for v in obj.data.vertices:
        v.co = Vector((v.co.x * scale, v.co.y * scale, (v.co.z - low) * scale))
    for p in obj.data.polygons:
        p.use_smooth = True
    obj.data.materials.append(material('Neutral_Skin', (.50,.29,.19,1), .6))
    return obj, lambda p: (p[0] * scale, p[1] * scale, (p[2] - low) * scale)

def create_rig(body, coord):
    arm=bpy.data.armatures.new('Female_Custom_Humanoid')
    rig=bpy.data.objects.new('Female_Rig',arm)
    bpy.context.collection.objects.link(rig)
    activate(rig);bpy.ops.object.mode_set(mode='EDIT')
    def add(name,a,b,parent=None):
        eb=arm.edit_bones.new(name);eb.head=coord(a);eb.tail=coord(b)
        if parent:eb.parent=arm.edit_bones[parent]
        # Z-up roll convention: align local Z towards forward -Y for horizontal
        # arm segments; Blender retains a consistent right-handed basis.
        eb.align_roll(Vector((0,-1,0)))
        BONES.append(dict(name=name,parent=parent,head=list(eb.head),tail=list(eb.tail)))
    add('HIPS',(0,0,.91),(0,0,1.04))
    add('SPINE_NAVAL',(0,0,1.04),(0,0,1.23),'HIPS')
    add('SPINE_CHEST',(0,0,1.23),(0,0,1.45),'SPINE_NAVAL')
    add('NECK',(0,0,1.45),(0,0,1.56),'SPINE_CHEST')
    add('HEAD',(0,0,1.56),(0,0,1.79),'NECK')
    for s,side in ((1,'L'),(-1,'R')):
        def p(x,y,z):return (s*x,y,z)
        add('CLAVICLE_'+side,p(.04,0,1.40),p(.205,0,1.40),'SPINE_CHEST')
        add('SHOULDER_'+side,p(.205,0,1.40),p(.46,0,1.40),'CLAVICLE_'+side)
        add('ELBOW_'+side,p(.46,0,1.40),p(.70,0,1.40),'SHOULDER_'+side)
        add('WRIST_'+side,p(.70,0,1.40),p(.77,0,1.40),'ELBOW_'+side)
        add('HAND_'+side,p(.77,0,1.40),p(.84,0,1.40),'WRIST_'+side)
        add('HANDTIP_'+side,p(.84,0,1.40),p(.875,0,1.40),'HAND_'+side)
        add('THUMB_'+side,p(.785,-.025,1.40),p(.825,-.085,1.40),'HAND_'+side)
        add('HIP_'+side,p(.115,0,.90),p(.12,-.025,.525),'HIPS')
        add('KNEE_'+side,p(.12,-.025,.525),p(.12,0,.14),'HIP_'+side)
        add('ANKLE_'+side,p(.12,0,.14),p(.12,-.045,.07),'KNEE_'+side)
        add('FOOT_'+side,p(.12,-.045,.07),p(.12,-.235,.065),'ANKLE_'+side)
    bpy.ops.object.mode_set(mode='OBJECT')
    activate(rig);body.select_set(True)
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    assert all(sum(g.weight for g in v.groups)>1e-6 for v in body.data.vertices), 'ARMATURE_AUTO failed; no fallback permitted'
    # Local smoothing only at shoulders, elbows and hips. Preserve the heat
    # solver's groups rather than replacing them with distance-based weights.
    activate(body)
    bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='DESELECT');bpy.ops.object.mode_set(mode='OBJECT')
    centers=[Vector(coord((s*x,y,z))) for s in (-1,1) for x,y,z in [(.205,0,1.40),(.46,0,1.40),(.115,0,.90)]]
    count=0
    for v in body.data.vertices:
        v.select=any((v.co-c).length<.13 for c in centers)
        count+=v.select
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.object.vertex_group_smooth(group_select_mode='ALL',factor=.5,repeat=4,expand=0)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL',limit=4)
    bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    assert all(len(v.groups)<=4 and abs(sum(g.weight for g in v.groups)-1)<1e-5 for v in body.data.vertices)
    rig.show_in_front=True
    return rig,count


def garments(body,rig,coord):
    black=material('Black_Sportswear',(.008,.010,.014,1),.68)
    scale=coord((1,0,0))[0];origin=Vector(coord((0,0,0)))
    body.data.update()
    result=[]
    for name in ('Sports_Bra','Athletic_Shorts'):
        chosen=[]
        for face in body.data.polygons:
            c=(face.center-origin)/scale
            x,y,z=c
            if name=='Athletic_Shorts':
                take=.785<z<1.06 and abs(x)<.215
            else:
                band=1.255<z<1.365 and abs(x)<.183
                straps=1.365<=z<1.487 and .09<abs(x)<.135
                take=band or straps
            if take:chosen.append(face)
        indices=sorted({i for face in chosen for i in face.vertices})
        remap={v:i for i,v in enumerate(indices)}
        mesh=bpy.data.meshes.new(name+'_Quads')
        mesh.from_pydata([body.data.vertices[i].co+body.data.vertices[i].normal*.005 for i in indices],[],[tuple(remap[i] for i in f.vertices) for f in chosen]);mesh.update()
        obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj);mesh.materials.append(black)
        for g in body.vertex_groups:obj.vertex_groups.new(name=g.name)
        for i in indices:
            for group in body.data.vertices[i].groups:obj.vertex_groups[group.group].add([remap[i]],group.weight,'REPLACE')
        activate(obj)
        relax=obj.modifiers.new('Smooth garment boundaries','SMOOTH');relax.factor=.3;relax.iterations=2
        bpy.ops.object.modifier_apply(modifier=relax.name)
        shell=obj.modifiers.new('Fabric thickness','SOLIDIFY');shell.thickness=.0015;shell.offset=0
        bpy.ops.object.modifier_apply(modifier=shell.name)
        for f in mesh.polygons:f.use_smooth=True
        mod=obj.modifiers.new('Female armature','ARMATURE');mod.object=rig;obj.parent=rig
        result.append(obj)
    return result


def head_details(rig,coord,skin):
    """Stylized eyes, ears, lips and tied-back hair; rigid HEAD accessories.
    These are intentionally added after heat binding the continuous body.
    """
    objects=[]
    hair=material('Dark_Brown_Hair',(.025,.014,.010,1),.65)
    white=material('Eye_White',(.80,.77,.70,1),.35)
    iris=material('Dark_Iris',(.018,.012,.008,1),.3)
    lips=material('Natural_Lips',(.30,.105,.075,1),.6)
    scale=coord((1,0,0))[0]
    def sphere(name,center,radius,mat,segments=10,rings=6):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=segments,ring_count=rings,location=coord(center))
        obj=bpy.context.object;obj.name=name;obj.scale=Vector(radius)*scale
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        obj.data.materials.append(mat)
        for f in obj.data.polygons:f.use_smooth=True
        objects.append(obj)
        return obj
    for s in (-1,1):
        sphere('Ear', (s*.087,-.002,1.665),(.012,.015,.023),skin)
        sphere('Eye',(s*.035,-.079,1.681),(.013,.005,.006),white)
        sphere('Iris',(s*.035,-.084,1.681),(.0045,.002,.0045),iris,10,6)
        brow=sphere('Brow',(s*.035,-.08,1.701),(.022,.004,.0035),hair,10,6)
        brow.rotation_euler.y=s*.10
    sphere('Upper_Lip',(0,-.084,1.623),(.023,.004,.003),lips,12,6)
    sphere('Lower_Lip',(0,-.084,1.616),(.021,.004,.0035),lips,12,6)
    # Quad hair cap: the front hairline is high, back extends below ears.
    verts=[];faces=[];n=20;rows=7
    for j in range(rows):
        t=j/(rows-1)
        for i in range(n):
            phi=i*math.tau/n
            front=(1+math.cos(phi))/2
            end=1.9-.72*front
            theta=.04+t*end
            verts.append(coord((.117*math.sin(theta)*math.sin(phi),-.108*math.sin(theta)*math.cos(phi)+.006,1.698+.128*math.cos(theta))))
    for j in range(rows-1):
        for i in range(n):
            k=(i+1)%n;a=j*n;b=(j+1)*n;faces.append((a+i,a+k,b+k,b+i))
    faces.append(tuple(reversed(range(n))))
    mesh=bpy.data.meshes.new('HairCapQuads');mesh.from_pydata(verts,[],faces);mesh.update()
    cap=bpy.data.objects.new('Tied_Back_Hair',mesh);bpy.context.collection.objects.link(cap);mesh.materials.append(hair);objects.append(cap)
    for f in mesh.polygons:f.use_smooth=True
    sphere('Hair_Tie',(0,.095,1.77),(.037,.029,.035),hair)
    tail=sphere('Ponytail',(0,.125,1.675),(.035,.033,.10),hair,10,8)
    tail.rotation_euler.x=-.16
    for obj in objects:
        group=obj.vertex_groups.new(name='HEAD');group.add(list(range(len(obj.data.vertices))),1,'REPLACE')
        mod=obj.modifiers.new('HEAD attachment','ARMATURE');mod.object=rig;obj.parent=rig
    return objects


def pose_checks(body,rig):
    # Bend in-plane elbows/knees, elevate shoulders, and flex hips. These
    # numerical tests detect invalid/degenerate faces, not all visual artifacts.
    report=[]
    for name,axis,angle in [('ELBOW_L',2,1.2),('ELBOW_R',2,-1.2),('KNEE_L',0,-1.0),('SHOULDER_L',2,.6),('HIP_L',0,.7)]:
        pb=rig.pose.bones[name];pb.rotation_mode='XYZ';pb.rotation_euler[axis]=angle
        bpy.context.view_layer.update()
        ev=body.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
        minimum=min(f.area for f in mesh.polygons)
        assert minimum>1e-10,(name,minimum)
        assert all(math.isfinite(c) for v in mesh.vertices for c in v.co)
        report.append(dict(bone=name,angle_rad=angle,minimum_face_area_m2=minimum))
        ev.to_mesh_clear();pb.rotation_euler[axis]=0
    bpy.context.view_layer.update()
    return report


def main():
    BONES.clear()
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    body,coord=build_body()
    report=topology(body)
    rig,smoothed=create_rig(body,coord)
    clothing=garments(body,rig,coord)
    accessories=head_details(rig,coord,body.data.materials[0])
    report['pose_checks']=pose_checks(body,rig)
    meshes=[body]+clothing+accessories
    for obj in meshes:obj.data.calc_loop_triangles()
    report.update(total_triangles=sum(len(o.data.loop_triangles) for o in meshes),
                  binding='ARMATURE_AUTO',max_influences=4,unweighted_vertices=0,
                  smoothed_joint_vertices=smoothed,bones=BONES,bone_count=len(BONES),
                  pose='T-pose',height_m=1.8,blender=bpy.app.version_string,
                  rig_convention='Lead developer custom uppercase schema; not native Mixamo names',
                  reference='Athletic female sportswear reference; stylized procedural approximation')
    assert 15000<=report['total_triangles']<=25000,report['total_triangles']
    assert len(BONES)==27
    # All exposed meshes must have a valid normalized four-influence skin.
    assert all(0<len(v.groups)<=4 and abs(sum(g.weight for g in v.groups)-1)<1e-5 for o in meshes for v in o.data.vertices)
    bpy.context.scene.unit_settings.system='METRIC'
    bpy.context.scene.render.fps=30
    activate(rig)
    for obj in meshes:obj.select_set(True)
    OUT.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(NAME+'.blend')))
    # glTF skin mesh nodes at scene root avoid transform inheritance warnings.
    for obj in meshes:
        world=obj.matrix_world.copy();obj.parent=None;obj.matrix_world=world
    bpy.ops.export_scene.gltf(filepath=str(OUT/(NAME+'.glb')),export_format='GLB',use_selection=True,
        export_skins=True,export_animations=False,export_def_bones=False,export_materials='EXPORT',export_yup=True,export_texcoords=False)
    raw=(OUT/(NAME+'.glb')).read_bytes();size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+size])
    joints={doc['nodes'][i]['name'] for s in doc['skins'] for i in s['joints']}
    assert joints=={b['name'] for b in BONES},joints
    report['export_bytes']=len(raw)
    (OUT/(NAME+'.validation.json')).write_text(json.dumps(report,indent=2)+'\n')
    # The web hierarchy panel uses the same names/parentage validated in GLB.
    (OUT/(NAME+'.hierarchy.json')).write_text(json.dumps(dict(name='Athletic Female — custom rig',bones=BONES),indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='bones'},indent=2),flush=True)


if __name__=='__main__':main()
