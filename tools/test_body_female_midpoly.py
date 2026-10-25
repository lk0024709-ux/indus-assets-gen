"""Dependency-free checks for the exact custom female rig and runtime GLB."""
from pathlib import Path
import json
import math
import struct
import unittest

BASE = Path(__file__).resolve().parents[1] / 'docs/models/characters'
EXPECTED = {'HIPS': None, 'SPINE_NAVAL': 'HIPS', 'SPINE_CHEST': 'SPINE_NAVAL',
            'NECK': 'SPINE_CHEST', 'HEAD': 'NECK'}
for side in ('L', 'R'):
    previous = 'SPINE_CHEST'
    for part in ('CLAVICLE', 'SHOULDER', 'ELBOW', 'WRIST', 'HAND'):
        EXPECTED[f'{part}_{side}'] = previous
        previous = f'{part}_{side}'
    EXPECTED[f'THUMB_{side}'] = f'HAND_{side}'
    EXPECTED[f'HANDTIP_{side}'] = f'HAND_{side}'
    previous = 'HIPS'
    for part in ('HIP', 'KNEE', 'ANKLE', 'FOOT'):
        EXPECTED[f'{part}_{side}'] = previous
        previous = f'{part}_{side}'


class FemaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = (BASE / 'body_base_female_midpoly.glb').read_bytes()
        assert struct.unpack_from('<4sII', raw) == (b'glTF', 2, len(raw))
        n = struct.unpack_from('<I', raw, 12)[0]
        cls.doc = json.loads(raw[20:20+n])
        cls.binary = raw[28+n:]
        cls.report = json.loads((BASE / 'body_base_female_midpoly.validation.json').read_text())

    def accessor(self, index):
        a = self.doc['accessors'][index]
        view = self.doc['bufferViews'][a['bufferView']]
        count = {'SCALAR': 1, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
        fmt = '<' + {5121: 'B', 5123: 'H', 5125: 'I', 5126: 'f'}[a['componentType']] * count
        stride = view.get('byteStride', struct.calcsize(fmt))
        offset = view.get('byteOffset', 0) + a.get('byteOffset', 0)
        return [struct.unpack_from(fmt, self.binary, offset+i*stride) for i in range(a['count'])]

    def test_exact_joint_names_and_parentage(self):
        joints = {i for skin in self.doc['skins'] for i in skin['joints']}
        self.assertEqual({self.doc['nodes'][i]['name'] for i in joints}, set(EXPECTED))
        parents = {child: i for i, node in enumerate(self.doc['nodes']) for child in node.get('children', [])}
        for i in joints:
            p = parents.get(i)
            while p is not None and p not in joints:
                p = parents.get(p)
            name = self.doc['nodes'][i]['name']
            self.assertEqual(self.doc['nodes'][p]['name'] if p is not None else None, EXPECTED[name])
        sidecar = json.loads((BASE / 'body_base_female_midpoly.hierarchy.json').read_text())
        self.assertEqual({b['name']: b['parent'] for b in sidecar['bones']}, EXPECTED)

    def test_t_pose_and_joint_alignment(self):
        bones = {b['name']: b for b in self.report['bones']}
        for side in ('L', 'R'):
            for part in ('SHOULDER', 'ELBOW', 'WRIST', 'HAND', 'HANDTIP'):
                b = bones[f'{part}_{side}']
                self.assertAlmostEqual(b['head'][2], b['tail'][2], places=6)
                self.assertAlmostEqual(b['head'][1], b['tail'][1], places=6)
            for a, b in [('SHOULDER', 'ELBOW'), ('ELBOW', 'WRIST'), ('WRIST', 'HAND'), ('HIP', 'KNEE'), ('KNEE', 'ANKLE'), ('ANKLE', 'FOOT')]:
                for x, y in zip(bones[f'{a}_{side}']['tail'], bones[f'{b}_{side}']['head']):
                    self.assertAlmostEqual(x, y, places=6)
        self.assertEqual(self.report['pose'], 'T-pose')
        self.assertFalse(self.doc.get('animations'))

    def test_budget_quads_materials_and_weights(self):
        tri = 0
        for mesh in self.doc['meshes']:
            for p in mesh['primitives']:
                tri += len(self.accessor(p['indices'])) // 3
                attr = p['attributes']
                self.assertNotIn('WEIGHTS_1', attr)
                weights = self.accessor(attr['WEIGHTS_0'])
                self.assertTrue(all(abs(sum(w)-1) < 1e-5 for w in weights))
                self.assertTrue(all(0 <= c <= 1 for w in weights for c in w))
                self.assertTrue(all(math.isfinite(c) for v in self.accessor(attr['POSITION']) for c in v))
        self.assertEqual(tri, self.report['total_triangles'])
        self.assertTrue(15000 <= tri <= 25000)
        self.assertEqual(self.report['quads'], self.report['faces'])
        self.assertEqual(self.report['connected_components'], 1)
        self.assertEqual(self.report['non_manifold_edges'], 0)
        self.assertEqual(self.report['binding'], 'ARMATURE_AUTO')
        self.assertGreater(self.report['smoothed_joint_vertices'], 0)
        materials = {m['name']: m for m in self.doc['materials']}
        self.assertAlmostEqual(materials['Neutral_Skin']['pbrMetallicRoughness']['roughnessFactor'], .6)
        black = materials['Black_Sportswear']['pbrMetallicRoughness']['baseColorFactor']
        self.assertTrue(all(c < .02 for c in black[:3]))
        self.assertFalse(self.doc.get('textures'))

    def body_surface(self):
        node=next(n for n in self.doc['nodes'] if n.get('name')=='Athletic_Female_Body')
        primitive=self.doc['meshes'][node['mesh']]['primitives'][0]
        return self.accessor(primitive['attributes']['POSITION']), [i[0] for i in self.accessor(primitive['indices'])]

    def test_connected_individual_digits_in_export_geometry(self):
        positions,indices=self.body_surface()
        shoulder=next(b for b in self.report['bones'] if b['name']=='SHOULDER_L')
        scale=shoulder['head'][0]/.205
        def crossings(axis,value,lateral,positive_x=False):
            intervals=[]
            for k in range(0,len(indices),3):
                tri=[positions[i] for i in indices[k:k+3]]
                if positive_x and max(v[0] for v in tri)<.02:continue
                if min(v[axis] for v in tri)>value or max(v[axis] for v in tri)<value:continue
                hits=[]
                for a,b in zip(tri,tri[1:]+tri[:1]):
                    if abs(b[axis]-a[axis])<1e-8:continue
                    t=(value-a[axis])/(b[axis]-a[axis])
                    if 0<=t<=1:hits.append(a[lateral]+t*(b[lateral]-a[lateral]))
                if len(hits)>1:intervals.append((min(hits),max(hits)))
            merged=[]
            for lo,hi in sorted(intervals):
                if merged and lo<=merged[-1][1]+.0001:merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
                else:merged.append((lo,hi))
            return merged
        # Transverse cuts through the actual exported mesh must resolve four
        # fingers (the thumb ends before this cut) and five separate toes.
        self.assertEqual(len(crossings(0,.84*scale,2)),4)
        self.assertEqual(len(crossings(2,.213*scale,0,True)),5)
        self.assertEqual(self.report['hand_digits'],10)
        self.assertEqual(self.report['foot_digits'],10)

    def test_muscle_contours_and_anatomical_pivots(self):
        positions,_=self.body_surface()
        shoulder=next(b for b in self.report['bones'] if b['name']=='SHOULDER_L')
        scale=shoulder['head'][0]/.205
        arm_y=shoulder['head'][2]
        def arm_radius(x):
            selected=[math.hypot(p[1]-arm_y,p[2]) for p in positions if abs(p[0]-x*scale)<.014*scale]
            self.assertTrue(selected)
            return max(selected)
        self.assertGreater(arm_radius(.34),arm_radius(.46)*1.3)
        floor=arm_y-1.4*scale
        def leg_radius(z):
            selected=[math.hypot(p[0]-.12*scale,p[2]) for p in positions
                      if .03*scale<p[0]<.23*scale and abs(p[1]-(z*scale+floor))<.022*scale]
            self.assertTrue(selected)
            return max(selected)
        self.assertGreater(leg_radius(.355),leg_radius(.20)*1.3)
        checks=self.report['anatomy_checks']
        self.assertEqual(len(checks['joint_pivots']),12)
        self.assertTrue(all(j['inside_clearance_m']>.005 for j in checks['joint_pivots']))
        self.assertTrue(all(c['rest_samples']>1000 and c['minimum_signed_clearance_m']>=-1e-4 for c in checks['clothing']))
        self.assertEqual(self.report['anatomy_revision'],'athletic-sculpt-v2')



if __name__ == '__main__':
    unittest.main()
