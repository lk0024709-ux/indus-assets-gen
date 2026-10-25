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
from mathutils.bvhtree import BVHTree
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

    def split_edge(a, b, segments):
        chain=[a]+[vertex(Vector(verts[a]).lerp(Vector(verts[b]), i/segments)) for i in range(1,segments)]+[b]
        for fi,face in enumerate(faces):
            f=list(face)
            for k in range(len(f)):
                if f[k]==a and f[(k+1)%len(f)]==b:
                    faces[fi]=tuple(f[:k+1]+chain[1:-1]+f[k+1:]);break
                if f[k]==b and f[(k+1)%len(f)]==a:
                    faces[fi]=tuple(f[:k+1]+list(reversed(chain[1:-1]))+f[k+1:]);break
        return chain

    def terminal_digits(root, kind, side):
        # Branch digits from a shared palm/forefoot perimeter. Adjacent roots
        # share their webbing edge: there are no floating finger/toe cylinders.
        lateral=1 if kind=='hand' else 0
        center=sum((Vector(verts[i]) for i in root),Vector())/len(root)
        if len(root)!=4:
            # Transition six-sided ankle/foot tubing to a rectangular forefoot.
            lo=min(verts[i][lateral] for i in root);hi=max(verts[i][lateral] for i in root)
            zlo=center.z-.020;zhi=center.z+.020
            rect=[vertex((x,center.y-.012,z)) for x,z in [(lo,zhi),(hi,zhi),(hi,zlo),(lo,zlo)]]
            def angle(i):return math.atan2(verts[i][2]-center.z,verts[i][lateral]-center[lateral])
            old=sorted(root,key=angle);new=sorted(rect,key=angle)
            i=j=0
            while i<len(old) or j<len(new):
                a=old[i%len(old)];b=new[j%len(new)]
                ni=(i+1)/len(old) if i<len(old) else 2
                nj=(j+1)/len(new) if j<len(new) else 2
                if abs(ni-nj)<1e-8:
                    faces.append((a,old[(i+1)%len(old)],new[(j+1)%len(new)],b));i+=1;j+=1
                elif ni<nj:
                    faces.append((a,old[(i+1)%len(old)],b));i+=1
                else:
                    faces.append((a,new[(j+1)%len(new)],b));j+=1
            root=rect
        top=sorted(sorted(root,key=lambda i:verts[i][2])[-2:],key=lambda i:verts[i][lateral])
        bottom=sorted(sorted(root,key=lambda i:verts[i][2])[:2],key=lambda i:verts[i][lateral])
        n=4 if kind=='hand' else 5
        top=split_edge(*top,n);bottom=split_edge(*bottom,n)
        for i in range(n):
            opening=[top[i],top[i+1],bottom[i+1],bottom[i]]
            c=sum((Vector(verts[v]) for v in opening),Vector())/4
            if kind=='hand':
                length=[.075,.085,.078,.061][i]
                spread=(i-1.5)*.006
                keys=[(c.x+side*.012,c.y+spread*.2,c.z,.0085,.011),
                      (c.x+side*length*.58,c.y+spread*.65,c.z-.001,.008,.010),
                      (c.x+side*length,c.y+spread,c.z-.003,.0065,.008)]
                limb(opening,keys,1,(0,1,0))
            else:
                rank=i if side>0 else n-1-i
                length=[.061,.058,.049,.042,.034][rank]
                keys=[(c.x+(i-2)*.001,c.y-.014,c.z-.001,.009,.012),
                      (c.x+(i-2)*.002,c.y-length,c.z-.006,.0075,.010)]
                limb(opening,keys,1,(1,0,0))

    def limb(root, keys, samples, reference, thumb_side=None, digits=None):
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
            if thumb_side and k == len(data)-2:
                candidates = list(range(len(faces)-n, len(faces)))
                fi = min(candidates, key=lambda i: sum(verts[v][1] for v in faces[i]))
                thumb_root = list(faces.pop(fi))
            previous = ring
        if digits:
            terminal_digits(previous,digits[0],digits[1])
        else:
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
                    (s * .12, -.18, .065, .057, .038)], 1, (1, 0, 0), digits=('foot',s))
        limb(arm_loops[s], [(s * .215, 0, 1.40, .070, .070),
                    (s * .32, 0, 1.40, .069, .065),
                    (s * .445, 0, 1.40, .045, .045),
                    (s * .475, 0, 1.40, .045, .045),
                    (s * .57, 0, 1.40, .053, .050),
                    (s * .70, 0, 1.40, .029, .030),
                    (s * .74, 0, 1.40, .028, .028),
                    (s * .78, 0, 1.40, .041, .025),
                    (s * .795, 0, 1.40, .043, .025)], 1, (0, 1, 0), thumb_side=s, digits=('hand',s))
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
                p.y -= .029*math.exp(-(p.x/.017)**2-((p.z-1.655)/.019)**2)
                p.y -= .010*math.exp(-(p.x/.014)**2-((p.z-1.68)/.026)**2)
                p.y += .007*math.exp(-((abs(p.x)-.035)/.022)**2-((p.z-1.684)/.012)**2)
                p.y -= .006*math.exp(-(p.x/.035)**2-((p.z-1.628)/.019)**2)
                p.y -= .006*math.exp(-(p.x/.035)**2-((p.z-1.597)/.016)**2)
                p.y -= .007*math.exp(-((abs(p.x)-.044)/.025)**2-((p.z-1.648)/.026)**2)
        # Continuous muscle fields sculpt the existing surface. Amplitudes are
        # metres; Gaussian envelopes vanish around wrists/ankles and joints.
        a=abs(p.x)
        def g(value,center,width):return math.exp(-((value-center)/width)**2)
        if .20<a<.71 and abs(p.z-1.40)<.115:
            radial=max(math.hypot(p.y,p.z-1.40),1e-6)
            deltoid=g(a,.248,.046)
            upper=g(a,.34,.073)
            forearm=g(a,.56,.061)
            facing_front=max(0,-p.y/radial)
            facing_back=max(0,p.y/radial)
            p.y += (p.y/radial)*(.010*deltoid+.010*upper*facing_front+.008*upper*facing_back+.004*forearm)
            p.z += ((p.z-1.40)/radial)*(.012*deltoid+.004*upper+.003*forearm)
        if .16<p.z<.89:
            center_x=.12 if p.x>=0 else -.12
            dx=p.x-center_x
            radial=max(math.hypot(dx,p.y),1e-6)
            quad=g(p.z,.72,.12)
            calf=g(p.z,.355,.085)
            front=max(0,-p.y/radial);back=max(0,p.y/radial)
            p.x += dx/radial*(.010*quad+.005*calf)
            p.y += p.y/radial*(.014*quad*front+.014*calf*back)
            # Patellar prominence and a shallow tibial ridge, not spheres.
            if p.y<0:
                p.y -= .005*g(p.z,.525,.025)*g(dx,0,.045)
                p.y -= .003*g(p.z,.30,.12)*g(dx,0,.018)
        if a<.19 and 1.065<p.z<1.25 and p.y<-.035:
            abs_field=sum(g(p.z,z,.018) for z in (1.105,1.155,1.205))
            p.y -= .004*abs_field*g(a,.037,.025)
            p.y += .0025*g(p.x,0,.012)*g(p.z,1.15,.10)
            p.y += .003*g(p.x,0,.009)*g(p.z,1.10,.012)
            p.y -= .003*g(a,.10,.025)*g(p.z,1.13,.08)
        if .90<p.z<1.06 and p.y>0:
            p.y += .014*g(a,.085,.07)*g(p.z,.975,.065)
        if 1.22<p.z<1.40 and p.y>0:
            p.y += .006*g(a,.10,.06)*g(p.z,1.30,.075)
    low = min(v.co.z for v in obj.data.vertices)
    high = max(v.co.z for v in obj.data.vertices)
    scale = 1.8 / (high - low)
    for v in obj.data.vertices:
        v.co = Vector((v.co.x * scale, v.co.y * scale, (v.co.z - low) * scale))
    for p in obj.data.polygons:
        p.use_smooth = False
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
                take=.81<z<1.06 and abs(x)<.215
            else:
                band=1.255<z<(1.365+.025*min(abs(x)/.14,1)**1.5) and abs(x)<.183
                straps=1.365<=z<1.487 and .09<abs(x)<.135
                take=band or straps
            if take:chosen.append(face)
        indices=sorted({i for face in chosen for i in face.vertices})
        remap={v:i for i,v in enumerate(indices)}
        mesh=bpy.data.meshes.new(name+'_Quads')
        mesh.from_pydata([body.data.vertices[i].co+body.data.vertices[i].normal*.007 for i in indices],[],[tuple(remap[i] for i in f.vertices) for f in chosen]);mesh.update()
        obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj);mesh.materials.append(black)
        for g in body.vertex_groups:obj.vertex_groups.new(name=g.name)
        for i in indices:
            for group in body.data.vertices[i].groups:obj.vertex_groups[group.group].add([remap[i]],group.weight,'REPLACE')
        activate(obj)
        relax=obj.modifiers.new('Smooth garment boundaries','SMOOTH');relax.factor=.3;relax.iterations=2
        bpy.ops.object.modifier_apply(modifier=relax.name)
        # Opaque fitted clothes need the outer surface and a real opening rim,
        # not a hidden duplicate of every cloth face on the inside.
        surface=BVHTree.FromPolygons([v.co for v in body.data.vertices],
                    [tuple(f.vertices) for f in body.data.polygons])
        for v in mesh.vertices:
            hit=surface.find_nearest(v.co)
            v.co=hit[0]+hit[1]*.007
        bm=bmesh.new();bm.from_mesh(mesh);bm.normal_update()
        # Laplacian relax the boundary *along the fitted body* before adding
        # thickness. This softens neckline/strap stair-steps without hiding gaps.
        for iteration in range(7):
            updates={}
            for v in bm.verts:
                neighbors=[e.other_vert(v) for e in v.link_edges if e.is_boundary]
                if len(neighbors)==2:
                    p=v.co*.4+(neighbors[0].co+neighbors[1].co)*.3
                    hit=surface.find_nearest(p);updates[v]=hit[0]+hit[1]*.007
            for v,p in updates.items():v.co=p
        # Close tiny accidental islands in the face-selection mask, while
        # preserving the actual neckline, armholes, waistband and leg openings.
        pending={e for e in bm.edges if e.is_boundary}
        while pending:
            component={pending.pop()};stack=list(component)
            while stack:
                edge=stack.pop()
                for v in edge.verts:
                    for other in v.link_edges:
                        if other in pending:
                            pending.remove(other);component.add(other);stack.append(other)
            if len(component)<=12 and sum(e.calc_length() for e in component)<.075:
                bmesh.ops.holes_fill(bm,edges=list(component),sides=0)
        bm.normal_update()
        original=set(bm.verts)
        normals={tuple(v.co):v.normal.copy() for v in bm.verts}
        edges=[e for e in bm.edges if e.is_boundary]
        bmesh.ops.extrude_edge_only(bm,edges=edges)
        for v in bm.verts:
            if v not in original:v.co-=normals[tuple(v.co)]*.0015
        bm.to_mesh(mesh);bm.free()
        for f in mesh.polygons:f.use_smooth=True
        mod=obj.modifiers.new('Female armature','ARMATURE');mod.object=rig;obj.parent=rig
        result.append(obj)
    return result


def head_details(body,rig,coord,skin):
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
    surface=BVHTree.FromPolygons([v.co for v in body.data.vertices],
                [tuple(f.vertices) for f in body.data.polygons])
    origin=Vector(coord((0,0,0)))
    def front_point(x,z,offset=0):
        hit=surface.ray_cast(Vector(coord((x,-.4,z))),Vector((0,1,0)))
        if hit[0] is None:return (x,-.075-offset,z)
        p=(hit[0]-origin)/scale
        return (p.x,p.y-offset,p.z)
    def feature_tube(name,points,radii,mat,project=False):
        centers=[Vector(coord(p)) for p in points]
        if project:
            centers=[surface.find_nearest(p)[0]+surface.find_nearest(p)[1]*.004 for p in centers]
        vertices=[];faces=[];n=4
        for k,c in enumerate(centers):
            tangent=(centers[min(k+1,len(centers)-1)]-centers[max(0,k-1)]).normalized()
            ref=Vector((0,1,0)) if abs(tangent.y)<.9 else Vector((1,0,0))
            u=(ref-tangent*ref.dot(tangent)).normalized();v=tangent.cross(u)
            radius=radii[k]*scale
            vertices.extend(c+radius*(u*math.cos(i*math.tau/n)+v*math.sin(i*math.tau/n)) for i in range(n))
            if k:
                for i in range(n):
                    j=(i+1)%n;faces.append(((k-1)*n+i,(k-1)*n+j,k*n+j,k*n+i))
        faces.extend([tuple(reversed(range(n))),tuple((len(centers)-1)*n+i for i in range(n))])
        mesh=bpy.data.meshes.new(name+'_Quads');mesh.from_pydata(vertices,[],faces);mesh.update()
        obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj);mesh.materials.append(mat)
        bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
        for f in mesh.polygons:f.use_smooth=True
        objects.append(obj)
        return obj
    for s in (-1,1):
        sphere('Ear',(s*.087,-.002,1.665),(.011,.014,.022),skin)
        sphere('Eye',front_point(s*.035,1.681,.001),(.016,.0055,.007),white)
        sphere('Iris',front_point(s*.035,1.681,.006),(.0048,.002,.005),iris,10,6)
        for upper in (-1,1):
            points=[]
            for i in range(7):
                t=math.pi*i/6
                points.append(front_point(s*.035+.016*math.cos(t),1.681+upper*.007*math.sin(t),.003))
            feature_tube('Upper_Eyelid' if upper>0 else 'Lower_Eyelid',points,[.0017]*7,skin)
        brow_points=[front_point(s*(.016+.04*i/4),1.701+.004*math.sin(math.pi*i/4),.003) for i in range(5)]
        feature_tube('Eyebrow',brow_points,[.0015,.0025,.003,.002,.001],hair)
        sphere('Nostril',front_point(s*.008,1.649,.0015),(.0035,.0018,.0015),iris,8,4)
    sphere('Upper_Lip',front_point(0,1.623,.001),(.023,.004,.003),lips,12,6)
    sphere('Lower_Lip',front_point(0,1.616,.001),(.021,.004,.0035),lips,12,6)
    # Quad hair cap: the front hairline is high, back extends below ears.
    verts=[];faces=[];n=20;rows=7
    for j in range(rows):
        t=j/(rows-1)
        for i in range(n):
            phi=i*math.tau/n
            front=(1+math.cos(phi))/2
            end=1.36+.65*(1-front)
            theta=.04+t*end
            verts.append(coord((.117*math.sin(theta)*math.sin(phi),-.108*math.sin(theta)*math.cos(phi)+.006,1.698+.128*math.cos(theta))))
    for j in range(rows-1):
        for i in range(n):
            k=(i+1)%n;a=j*n;b=(j+1)*n;faces.append((a+i,a+k,b+k,b+i))
    faces.append(tuple(reversed(range(n))))
    mesh=bpy.data.meshes.new('HairCapQuads');mesh.from_pydata(verts,[],faces);mesh.update()
    for v in mesh.vertices:
        hit=surface.find_nearest(v.co);v.co=hit[0]+hit[1]*.0035
    cap=bpy.data.objects.new('Tied_Back_Hair',mesh);bpy.context.collection.objects.link(cap);mesh.materials.append(hair);objects.append(cap)
    for f in mesh.polygons:f.use_smooth=True
    sphere('Hair_Tie',(0,.095,1.77),(.025,.022,.026),hair)
    # Individually swept locks follow the skull towards the ponytail tie.
    for strand in range(12):
        initial=-1.4+2.8*strand/11
        sign=-1 if initial<0 else 1
        points=[]
        for k in range(7):
            t=k/6
            theta=1.36*(1-t)+.90*t-.78*math.sin(math.pi*t)
            phi=initial*(1-t)+sign*math.pi*t
            points.append((.117*math.sin(theta)*math.sin(phi),-.108*math.sin(theta)*math.cos(phi)+.006,1.698+.128*math.cos(theta)))
        feature_tube('Swept_Hair_Lock',points,[.0018,.0028,.0032,.003,.0028,.0025,.0018],hair,project=True)
    for strand in range(4):
        angle=strand*math.tau/4
        points=[]
        for k in range(7):
            t=k/6
            points.append((.013*math.cos(angle)*(1-t)+.015*math.sin(t*math.pi),.10+.045*math.sin(t*math.pi)+.009*math.sin(angle),1.77-.205*t))
        feature_tube('Ponytail_Lock',points,[.009,.010,.010,.009,.007,.005,.0015],hair)
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


def anatomy_checks(body,clothing,rig):
    """Quantitative rest checks: pivots lie inside skin; sampled cloth stays out.
    Not a certification of intersections under every possible animation pose.
    """
    tree=BVHTree.FromPolygons([v.co for v in body.data.vertices],
                           [tuple(f.vertices) for f in body.data.polygons])
    pivots=[]
    for side in ('L','R'):
        for part in ('SHOULDER','ELBOW','WRIST','HIP','KNEE','ANKLE'):
            name=part+'_'+side
            point=rig.data.bones[name].head_local
            hit=tree.find_nearest(point)
            signed=(point-hit[0]).dot(hit[1])
            assert signed<-.005,(name,signed)
            pivots.append(dict(bone=name,inside_clearance_m=-signed))
    fabric=[]
    for obj in clothing:
        minimum=float('inf');samples=0
        obj.data.calc_loop_triangles()
        for triangle in obj.data.loop_triangles:
            a,b,c=[obj.data.vertices[i].co for i in triangle.vertices]
            for i in range(7):
                for j in range(7-i):
                    u,v=i/6,j/6
                    p=a*u+b*v+c*(1-u-v)
                    hit=tree.find_nearest(p)
                    minimum=min(minimum,(p-hit[0]).dot(hit[1]));samples+=1
        assert minimum>=-1e-4,(obj.name,minimum)
        fabric.append(dict(mesh=obj.name,rest_samples=samples,minimum_signed_clearance_m=minimum))
    return dict(joint_pivots=pivots,clothing=fabric)


def main():
    BONES.clear()
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    body,coord=build_body()
    report=topology(body)
    rig,smoothed=create_rig(body,coord)
    clothing=garments(body,rig,coord)
    accessories=head_details(body,rig,coord,body.data.materials[0])
    report['pose_checks']=pose_checks(body,rig)
    report['anatomy_checks']=anatomy_checks(body,clothing,rig)
    meshes=[body]+clothing+accessories
    for obj in meshes:obj.data.calc_loop_triangles()
    report.update(total_triangles=sum(len(o.data.loop_triangles) for o in meshes),
                  binding='ARMATURE_AUTO',max_influences=4,unweighted_vertices=0,
                  smoothed_joint_vertices=smoothed,bones=BONES,bone_count=len(BONES),
                  pose='T-pose',height_m=1.8,anatomy_revision='athletic-sculpt-v2',
                  muscle_regions=['deltoid','biceps','triceps','forearm','quadriceps','calf','abdominals','gluteal','latissimus'],
                  hand_digits=10,foot_digits=10,shading='faceted body, smooth fitted sportswear',blender=bpy.app.version_string,
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
