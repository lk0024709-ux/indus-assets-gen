#!/usr/bin/env python3
"""Explicit anatomical pieces, quad swept surfaces and rigid per-piece skinning.
Blender 4.5: blender -b --python tools/generate_skeleton_midpoly.py
Alternatively python with bpy==4.5.3. Clears the scene; writes only named outputs.
"""
from pathlib import Path
import math
import json
import bpy
import bmesh
from mathutils import Vector

OUT = Path(__file__).resolve().parents[1] / 'docs/models/characters/skeleton'
V, F, PIECES, BONES = [], [], [], {}
TAU = math.tau


def bone(name, a, b, parent='Root'):
    BONES[name] = (tuple(a), tuple(b), parent)
    return name


def piece(name, joint, verts, faces):
    start = len(V)
    V.extend(tuple(v) for v in verts)
    F.extend(tuple(start + i for i in f) for f in faces)
    PIECES.append(dict(name=name, bone=joint, start=start, count=len(verts)))


def sweep(name, joint, points, radii, sides=8, elliptical=1):
    points = [Vector(p) for p in points]
    verts, faces = [], []
    old_u = None
    for k, p in enumerate(points):
        tangent = (points[min(k+1,len(points)-1)]-points[max(0,k-1)]).normalized()
        if old_u is None:
            ref = Vector((0,1,0)) if abs(tangent.y)<.85 else Vector((1,0,0))
        else:
            ref = old_u
        u = (ref - tangent*ref.dot(tangent)).normalized()
        v = tangent.cross(u).normalized()
        old_u = u
        r = radii[k] if isinstance(radii,(list,tuple)) else radii
        verts.extend(p + r*(math.cos(i*TAU/sides)*u + elliptical*math.sin(i*TAU/sides)*v) for i in range(sides))
        if k:
            for i in range(sides):
                j=(i+1)%sides
                faces.append(((k-1)*sides+i,(k-1)*sides+j,k*sides+j,k*sides+i))
    faces.extend([tuple(reversed(range(sides))),tuple((len(points)-1)*sides+i for i in range(sides))])
    piece(name,joint,verts,faces)


def ellipsoid(name, joint, c, r, sides=8, rings=4):
    # A low-resolution UV surface: quads except the two polar fans.
    verts=[(c[0],c[1],c[2]+r[2])]
    for j in range(1,rings):
        t=math.pi*j/rings
        for i in range(sides):
            p=TAU*i/sides
            verts.append((c[0]+r[0]*math.sin(t)*math.cos(p),c[1]+r[1]*math.sin(t)*math.sin(p),c[2]+r[2]*math.cos(t)))
    bottom=len(verts);verts.append((c[0],c[1],c[2]-r[2]))
    faces=[]
    for i in range(sides):
        k=(i+1)%sides
        faces.extend([(0,1+i,1+k),(bottom,1+(rings-2)*sides+k,1+(rings-2)*sides+i)])
    for j in range(rings-2):
        for i in range(sides):
            k=(i+1)%sides;a=1+j*sides;b=a+sides
            faces.append((a+i,b+i,b+k,a+k))
    piece(name,joint,verts,faces)


def longbone(name, a, b, radius, parent, sides=8, detail=True):
    joint=bone(name,a,b,parent)
    a,b=Vector(a),Vector(b)
    d=b-a
    profile=[(0,.9),(.06,1.45),(.14,1.12),(.28,.68),(.5,.55),(.73,.65),(.88,1.12),(.96,1.5),(1,.95)]
    if radius < .007:
        profile=[(0,1),(.12,1.3),(.5,.65),(.88,1.3),(1,1)]
    sweep(name,joint,[a+d*t for t,r in profile],[radius*r for t,r in profile],sides)
    if detail:
        for k,p in enumerate((a+d*.05,a+d*.95)):
            for s in (-1,1):
                ellipsoid(f'{name}_condyle{k}_{s}',joint,p+Vector((s*radius*.65,0,0)),(radius*.9,radius*1.15,radius*.9),8,4)
    return joint


def skull():
    bone('Skull',(0,0,1.55),(0,0,1.8),'C1')
    # Cranium has actual recessed sockets, not painted-on spheres. Build UV
    # shell, omit orbital/nasal patches, then bridge their boundary into wells.
    n,m=40,24
    verts=[];faces=[]; holes={'orbit.L':[],'orbit.R':[],'nasal':[]}
    for j in range(m+1):
        t=.035+(math.pi-.07)*j/m
        for i in range(n):
            p=TAU*i/n
            verts.append((.103*math.sin(t)*math.sin(p),-.09*math.sin(t)*math.cos(p),1.675+.126*math.cos(t)))
    for j in range(m):
        for i in range(n):
            ids=(j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i)
            c=sum((Vector(verts[k]) for k in ids),Vector())/4
            h=None
            if c.y<-.035:
                if 1.655<c.z<1.705 and .022<abs(c.x)<.078:
                    h='orbit.L' if c.x>0 else 'orbit.R'
                elif 1.605<c.z<1.65 and abs(c.x)<.018:
                    h='nasal'
            if h: holes[h].append(ids)
            else: faces.append(ids)
    faces.extend([tuple(reversed(range(n))),tuple(m*n+i for i in range(n))])
    for label,removed in holes.items():
        counts={}
        for f in removed:
            for a,b in zip(f,f[1:]+f[:1]):
                e=tuple(sorted((a,b)));counts[e]=counts.get(e,0)+1
        boundary=[e for e,c in counts.items() if c==1]
        adjacent={}
        for a,b in boundary:
            adjacent.setdefault(a,[]).append(b);adjacent.setdefault(b,[]).append(a)
        first=next(iter(adjacent));loop=[first];prev=None;cur=first
        while True:
            nxt=next(v for v in adjacent[cur] if v!=prev)
            if nxt==first:break
            loop.append(nxt);prev,cur=cur,nxt
        c=sum((Vector(verts[k]) for k in loop),Vector())/len(loop)
        # Round the orbital rim instead of leaving a rectangular UV cutout.
        if label.startswith('orbit'):
            for k in loop:
                delta=Vector(verts[k])-c
                angle=math.atan2(delta.z/.027,delta.x/.029)
                x=c.x+.031*math.cos(angle);z=c.z+.029*math.sin(angle)
                y=-.09*math.sqrt(max(.06,1-(x/.103)**2-((z-1.675)/.126)**2))
                verts[k]=(x,y,z)
        inner=[]
        for k in loop:
            p=c+(Vector(verts[k])-c)*.78;p.y+=.038 if label!='nasal' else .026
            inner.append(len(verts));verts.append(tuple(p))
        for i in range(len(loop)):
            j=(i+1)%len(loop);faces.append((loop[i],loop[j],inner[j],inner[i]))
        faces.append(tuple(reversed(inner)))
    # Remove unused socket-patch vertices so every vertex is incident on faces.
    used=sorted({i for f in faces for i in f});remap={v:i for i,v in enumerate(used)}
    piece('Cranium_with_orbital_and_nasal_cavities','Skull',[verts[i] for i in used],[tuple(remap[i] for i in f) for f in faces])
    # Cheek arches and maxilla surround the actual recessed cavities.
    for s in (-1,1):
        sweep(f'Zygomatic_{s}','Skull',[(s*.081,-.025,1.64),(s*.081,-.067,1.63),(s*.054,-.083,1.612)], [.012,.011,.014],8)
    arch=[(.051*math.sin(t),-.059-.023*math.cos(t),1.603) for t in [(-math.pi/2+i*math.pi/12) for i in range(13)]]
    sweep('Maxilla','Skull',arch,.012,8)
    bone('Mandible',(0,-.01,1.605),(0,-.065,1.55),'Skull')
    jaw=[(-.075,-.003,1.637),(-.072,-.027,1.57),(-.05,-.064,1.55),(0,-.083,1.545),(.05,-.064,1.55),(.072,-.027,1.57),(.075,-.003,1.637)]
    sweep('Mandible','Mandible',jaw,[.009,.012,.012,.014,.012,.012,.009],8)
    for row,z in [('Upper',1.584),('Lower',1.568)]:
        for i in range(14):
            t=-1.42+2.84*i/13
            c=(.050*math.sin(t),-.062-.026*math.cos(t),z)
            ellipsoid(f'{row}_tooth_{i+1}', 'Skull' if row=='Upper' else 'Mandible',c,(.0058,.0065,.010),8,4)


def spine_and_ribs():
    bone('Root',(0,0,0),(0,0,.08),None)
    bone('Sacrum',(0,.025,.91),(0,.025,1.02),'Root')
    # Bottom-up hierarchy, individually modelled bodies, arches and processes.
    levels=[(f'L{i}',1.025+(5-i)*.033,.020) for i in range(5,0,-1)]
    levels += [(f'T{i}',1.19+(12-i)*.021,.016) for i in range(12,0,-1)]
    levels += [(f'C{i}',1.45+(7-i)*.018,.012) for i in range(7,0,-1)]
    parent='Sacrum'
    for name,z,r in levels:
        y=.035 if name[0]!='C' else .018
        bone(name,(0,y,z-.012),(0,y,z+.012),parent);parent=name
        sweep(name+'_body',name,[(0,y,z-.011),(0,y,z-.008),(0,y,z+.008),(0,y,z+.011)],[r*.9,r,r,r*.9],10)
        sweep(name+'_neural_arch',name,[(-r*.7,y,z),(-r,y+.017,z),(0,y+.029,z),(r,y+.017,z),(r*.7,y,z)],.005,6)
        sweep(name+'_spinous',name,[(0,y+.022,z),(0,y+.048,z-.008)],[.007,.003],6)
        for s in (-1,1):
            sweep(name+f'_transverse{s}',name,[(s*r*.6,y+.007,z),(s*r*1.8,y+.013,z-.003)],[.005,.0035],6)
    # Five fused sacral segments are still individually identifiable pieces.
    for i in range(5):
        ellipsoid(f'Sacral_segment_{i+1}','Sacrum',(0,.027,.99-i*.018),(.035-i*.005,.018,.012),10,4)
    sweep('Coccyx','Sacrum',[(0,.028,.91),(0,.032,.885),(0,.018,.873)],[.009,.006,.003],6)
    bone('Sternum',(0,-.10,1.37),(0,-.12,1.205),'T6')
    sweep('Manubrium','Sternum',[(0,-.10,1.39),(0,-.118,1.36)],[.022,.017],6, .55)
    sweep('Sternal_body','Sternum',[(0,-.118,1.36),(0,-.13,1.28),(0,-.12,1.22)],[.015,.014,.009],8,.6)
    sweep('Xiphoid','Sternum',[(0,-.12,1.22),(0,-.113,1.192)],[.008,.002],6)
    for i in range(1,13):
        z=1.42-(i-1)*.023
        width=.092+.075*math.sin(math.pi*(i-1)/11)
        front=-.093-.035*math.sin(math.pi*(i-1)/12)
        # 11/12 are floating ribs, with free anterior ends.
        end_angle=math.pi*(.80 if i==11 else .65 if i==12 else 1)
        for s,side in ((1,'L'),(-1,'R')):
            name=f'Rib_{i:02}.{side}';joint=bone(name,(s*.014,.04,z),(s*width,0,z-.035),f'T{i}')
            pts=[]
            for k in range(19):
                t=end_angle*k/18
                x=s*(.014+width*math.sin(t))
                y=.04+(front-.04)*(1-math.cos(t))/2
                zz=z-.025*math.sin(t)-.055*(t/math.pi)
                # lower costal margin returns upwards towards xiphoid.
                if i>=8 and t>math.pi*.65:zz+=.012*(i-7)*(t/math.pi-.65)/.35
                pts.append((x,y,zz))
            sweep(name,joint,pts,[.0055 if i<9 else .0048]*19,6,1.35)


def pelvis():
    for s,side in ((1,'L'),(-1,'R')):
        name='Ilium.'+side;bone(name,(s*.035,.02,.96),(s*.13,0,.97),'Sacrum')
        # Quad fan-like iliac wing with inner/outer surfaces and crest rim.
        verts=[];faces=[];steps=12
        for layer in (-1,1):
            for j in range(4):
                t=.08+.92*j/3
                for i in range(steps+1):
                    a=-1.1+2.5*i/steps
                    x=s*(.102*(1-t)+(.09+.055*math.sin(a))*t)
                    y=.005*(1-t)+(.008+.055*math.cos(a))*t+layer*.005
                    z=.914*(1-t)+(.99+.065*math.cos(a))*t
                    verts.append((x,y,z))
        stride=steps+1;size=4*stride
        for layer in range(2):
            for j in range(3):
                for i in range(steps):
                    a=layer*size+j*stride+i;faces.append((a,a+1,a+stride+1,a+stride))
        perimeter=list(range(stride))+[j*stride+steps for j in range(1,4)]+list(range(4*stride-2,3*stride-1,-1))+[j*stride for j in (2,1)]
        for a,b in zip(perimeter,perimeter[1:]+perimeter[:1]):faces.append((a,b,b+size,a+size))
        piece(name,name,verts,faces)
        # Obturator opening is bounded by separate pubic/ischial rami.
        pts=[(s*.108,0,.91),(s*.13,.008,.87),(s*.09,-.025,.825),(s*.035,-.063,.84),(s*.015,-.07,.89),(s*.06,-.04,.92),(s*.108,0,.91)]
        sweep('Pubis_Ischium.'+side,name,pts,[.014,.016,.013,.010,.009,.012,.014],8)
        ellipsoid('Acetabulum.'+side,name,(s*.112,0,.905),(.023,.024,.022),10,5)
    sweep('Pubic_symphysis','Sacrum',[(-.018,-.07,.89),(.018,-.07,.89)],.009,8)


def limbs():
    for s,side in ((1,'L'),(-1,'R')):
        def p(x,y,z):return (s*x,y,z)
        clav='Clavicle.'+side;bone(clav,p(.02,-.09,1.405),p(.192,0,1.405),'T1')
        sweep(clav,clav,[p(.02,-.09,1.405),p(.08,-.07,1.416),p(.14,-.035,1.411),p(.192,0,1.405)],[.008,.009,.008,.011],8)
        # Thin triangular scapular blade, not a shoulder sphere stand-in.
        a=[p(.075,.07,1.405),p(.19,.035,1.405),p(.13,.075,1.28),p(.075,.08,1.405),p(.19,.045,1.405),p(.13,.085,1.28)]
        piece('Scapula.'+side,clav,a,[(0,1,2),(3,5,4),(0,3,4,1),(1,4,5,2),(2,5,3,0)])
        sweep('Scapular_spine.'+side,clav,[p(.08,.085,1.39),p(.155,.075,1.39),p(.198,.035,1.414)],.008,6)
        hum=longbone('Humerus.'+side,p(.198,0,1.385),p(.23,0,1.12),.015,clav)
        rad=longbone('Radius.'+side,p(.242,-.004,1.10),p(.273,-.01,.887),.0085,hum,8,False)
        ulna=longbone('Ulna.'+side,p(.219,.006,1.115),p(.25,.004,.883),.008,hum,8,False)
        ellipsoid('Olecranon.'+side,ulna,p(.22,.014,1.115),(.013,.013,.016),8,4)
        wrist=bone('Carpals.'+side,p(.263,0,.885),p(.267,0,.858),rad)
        for row in range(2):
            for col in range(4):
                ellipsoid(f'Carpal_{row}_{col}.{side}',wrist,p(.246+col*.010,-.002,.883-row*.012),(.006,.008,.006),8,4)
        for digit in range(5):
            # Thumb is opposed laterally; all digits have metacarpal and
            # separate phalanges (2 thumb, 3 each other finger).
            x=.243+digit*.012
            if digit==0:
                start=p(.248,-.006,.865);end=p(.218,-.015,.827)
            else:
                start=p(x,0,.857);end=p(x+(digit-2.5)*.003,-.003,.806)
            meta=longbone(f'Metacarpal_{digit+1}.{side}',start,end,.0048,wrist,6,False)
            prev=Vector(end);parent=meta
            lengths=[.029,.023] if digit==0 else [.032,.022,.017]
            for k,length in enumerate(lengths):
                direction=Vector((s*(-.42 if digit==0 else (digit-2.5)*.075),-.12,-1)).normalized()
                tip=prev+direction*length*(.8 if digit==4 else 1)
                parent=longbone(f'Finger_{digit+1}_Phalanx_{k+1}.{side}',prev,tip,.0039-k*.0007,parent,6,False)
                ellipsoid(f'Finger_joint_{digit+1}_{k+1}.{side}',parent,prev,(.0048,.005,.0048),6,3)
                prev=tip
        fem=longbone('Femur.'+side,p(.108,0,.883),p(.105,0,.535),.019,'Sacrum')
        ellipsoid('Femoral_head.'+side,fem,p(.094,0,.887),(.023,.023,.023),10,5)
        pat=bone('Patella.'+side,p(.105,-.03,.54),p(.105,-.035,.51),fem)
        ellipsoid('Patella.'+side,pat,p(.105,-.03,.53),(.019,.011,.022),10,5)
        tib=longbone('Tibia.'+side,p(.102,0,.51),p(.108,0,.11),.015,fem)
        fib=longbone('Fibula.'+side,p(.135,.01,.504),p(.138,.008,.105),.007,fem,8,False)
        foot=bone('Tarsals.'+side,p(.11,0,.10),p(.11,-.065,.065),tib)
        for i,(x,y,z,rx,ry,rz) in enumerate([(.11,.025,.055,.025,.028,.025),(.11,0,.093,.022,.022,.018),(.11,-.038,.07,.025,.022,.018),(.138,-.047,.06,.014,.021,.013),(.09,-.061,.065,.013,.018,.012),(.11,-.068,.062,.012,.017,.012),(.13,-.07,.06,.011,.016,.011)]):
            ellipsoid(f'Tarsal_{i+1}.{side}',foot,p(x,y,z),(rx,ry,rz),8,4)
        for digit in range(5):
            x=.078+digit*.016
            start=p(x,-.065,.062);end=p(x+(digit-2)*.003,-.13+digit*.004,.035)
            meta=longbone(f'Metatarsal_{digit+1}.{side}',start,end,.0055,foot,6,False)
            prev=Vector(end);parent=meta
            for k in range(2 if digit==0 else 3):
                tip=prev+Vector((s*(digit-2)*.001,-(.022 if k==0 else .014)*(1-digit*.08),-.003))
                parent=longbone(f'Toe_{digit+1}_Phalanx_{k+1}.{side}',prev,tip,.0048-k*.0008,parent,6,False)
                prev=tip


def main():
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    spine_and_ribs();skull();pelvis();limbs()
    mesh=bpy.data.meshes.new('AnatomicalBoneSurfaces');mesh.from_pydata(V,[],F);mesh.update()
    obj=bpy.data.objects.new('Skeleton_Anatomical',mesh);bpy.context.collection.objects.link(obj)
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
    mat=bpy.data.materials.new('Ivory_Bone');mat.use_nodes=True
    bs=mat.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(.73,.75,.68,1);bs.inputs['Roughness'].default_value=.4;bs.inputs['Subsurface Weight'].default_value=.035
    mesh.materials.append(mat)
    # Flat shading intentionally matches the faceted reference.
    arm=bpy.data.armatures.new('AnatomicalRig');rig=bpy.data.objects.new('Skeleton_Rig',arm);bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
    for name,(a,b,parent) in BONES.items():
        eb=arm.edit_bones.new(name);eb.head=a;eb.tail=b
    for name,(a,b,parent) in BONES.items():
        if parent:arm.edit_bones[name].parent=arm.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    for name in BONES:obj.vertex_groups.new(name=name)
    for part in PIECES:obj.vertex_groups[part['bone']].add(list(range(part['start'],part['start']+part['count'])),1,'REPLACE')
    mod=obj.modifiers.new('Rigid skeletal articulation','ARMATURE');mod.object=rig
    obj.parent=rig;rig.show_in_front=True
    mesh.calc_loop_triangles();tris=len(mesh.loop_triangles)
    report=dict(triangles=tris,vertices=len(mesh.vertices),faces=len(mesh.polygons),quads=sum(len(p.vertices)==4 for p in mesh.polygons),rig_bones=len(BONES),pieces=len(PIECES),vertebrae=24,rib_pairs=12,teeth=28,finger_phalanges=28,toe_phalanges=28,material='Ivory_Bone',roughness=.4,rigid_weight=1.0,blender=bpy.app.version_string)
    print(json.dumps(report,indent=2),flush=True)
    assert 15000<=tris<=25000,report
    assert all(len(v.groups)==1 and v.groups[0].weight==1 for v in mesh.vertices)
    assert all(math.isfinite(c) for v in mesh.vertices for c in v.co)
    OUT.mkdir(parents=True,exist_ok=True)
    # Pose smoke test: distal phalanges move without any per-piece stretching.
    test=rig.pose.bones['Finger_2_Phalanx_1.L'];test.rotation_mode='XYZ';test.rotation_euler.x=.5;bpy.context.view_layer.update()
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());posed=evaluated.to_mesh()
    part=next(p for p in PIECES if p['name']=='Finger_2_Phalanx_1.L');ids=list(range(part['start'],part['start']+part['count']))
    a,b=ids[0],ids[-1]
    assert abs((posed.vertices[a].co-posed.vertices[b].co).length-(mesh.vertices[a].co-mesh.vertices[b].co).length)<1e-6
    evaluated.to_mesh_clear();test.rotation_euler.x=0;bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);rig.select_set(True);bpy.context.view_layer.objects.active=rig
    bpy.context.scene.unit_settings.system='METRIC'
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'skeleton_base_midpoly.blend'))
    obj.parent=None
    bpy.ops.export_scene.gltf(filepath=str(OUT/'skeleton_base_midpoly.glb'),export_format='GLB',use_selection=True,export_animations=False,export_skins=True,export_yup=True,export_materials='EXPORT',export_all_influences=False)
    report['parts']=PIECES
    (OUT/'skeleton_base_midpoly.validation.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
