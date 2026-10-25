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


if __name__ == '__main__':
    unittest.main()
