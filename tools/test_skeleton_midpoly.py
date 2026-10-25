"""Regression tests for the inspected CGTrader export, not the old generator."""
from pathlib import Path
import hashlib
import struct
import json
import unittest

BASE = Path(__file__).resolve().parents[1] / 'docs/models/characters'


class SkeletonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = (BASE / 'skeleton_base_midpoly.glb').read_bytes()
        assert struct.unpack_from('<4sII', raw) == (b'glTF', 2, len(raw))
        n = struct.unpack_from('<I', raw, 12)[0]
        cls.doc = json.loads(raw[20:20+n])
        cls.binary = raw[28+n:]
        cls.report = json.loads((BASE / 'skeleton_base_midpoly.inspection.json').read_text())

    def values(self, index):
        a = self.doc['accessors'][index]
        v = self.doc['bufferViews'][a['bufferView']]
        size = {'SCALAR': 1, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
        fmt = '<' + {5121: 'B', 5123: 'H', 5125: 'I', 5126: 'f'}[a['componentType']] * size
        start = v.get('byteOffset', 0) + a.get('byteOffset', 0)
        stride = v.get('byteStride', struct.calcsize(fmt))
        return [struct.unpack_from(fmt, self.binary, start+i*stride) for i in range(a['count'])]

    def test_source_findings_and_unchanged_source(self):
        r = self.report
        self.assertEqual(r['source_triangles'], 112361)
        self.assertEqual(r['source_evaluated_triangles'], 112361)
        self.assertEqual([(a['name'], a['bones']) for a in r['armatures']], [('metarig', 63), ('rig', 388)])
        self.assertEqual(r['source_mesh_objects'], 158)
        self.assertEqual(r['source_surface_mesh_objects'], 28)
        self.assertEqual(len(r['actions']), 1)
        action = r['actions'][0]
        self.assertEqual(action['name'], 'BézierCircleAction')
        self.assertEqual(action['keyframes'], 0)
        self.assertEqual(action['paths'], ['eval_time'])
        self.assertEqual(r['armature_actions'], [])
        source = BASE / 'skeleton/skeleton_A_pose.blend'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), r['source_sha256'])

    def test_optimized_geometry(self):
        tri = sum(len(self.values(p['indices']))//3 for m in self.doc['meshes'] for p in m['primitives'])
        self.assertEqual(tri, self.report['export_triangles'])
        self.assertEqual(tri, 24970)
        self.assertTrue(self.report['decimation_applied'])
        self.assertTrue(24000 <= tri <= 26000)
        self.assertEqual(len(self.doc['meshes']), 28)
        self.assertEqual(len(self.doc['materials']), 1)
        self.assertFalse(self.doc.get('animations'))
        self.assertFalse(self.doc.get('textures'))

    def test_existing_rig_and_normalized_weights(self):
        self.assertEqual(len(self.doc['skins']), 1)
        joints = self.doc['skins'][0]['joints']
        self.assertEqual(len(joints), 65)
        self.assertEqual(self.report['exported_armatures'], ['rig'])
        self.assertEqual(self.report['excluded_armatures'], ['metarig'])
        self.assertEqual(self.report['export_animations'], [])
        # No procedural skeleton rig has been substituted.
        names = {self.doc['nodes'][i]['name'] for i in joints}
        self.assertTrue(all(name.startswith('DEF-') for name in names))
        parents = {i for n in self.doc['nodes'] for i in n.get('children', [])}
        for i, node in enumerate(self.doc['nodes']):
            if 'mesh' in node:
                self.assertNotIn(i, parents)
                self.assertEqual(node['skin'], 0)
        for mesh in self.doc['meshes']:
            for primitive in mesh['primitives']:
                self.assertNotIn('WEIGHTS_1', primitive['attributes'])
                weights = self.values(primitive['attributes']['WEIGHTS_0'])
                self.assertTrue(all(abs(sum(w)-1) < 1e-5 for w in weights))
                self.assertTrue(all(0 <= c <= 1 for w in weights for c in w))
                indices = self.values(primitive['attributes']['JOINTS_0'])
                self.assertTrue(all(0 <= i < len(joints) for js in indices for i in js))


if __name__ == '__main__':
    unittest.main()
