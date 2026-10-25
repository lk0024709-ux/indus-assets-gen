#!/usr/bin/env python3
"""Dependency-free regression checks for the shipped character GLB.
Run: python -m unittest discover -s tools -p test_body_base_midpoly.py -v
Source quad/manifold/intersection checks run inside the bpy generator itself.
"""
from pathlib import Path
import json
import math
import struct
import unittest

PATH = Path(__file__).resolve().parents[1] / 'docs/models/characters/body_base_midpoly.glb'


class BodyBaseExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = PATH.read_bytes()
        magic, version, length = struct.unpack_from('<4sII', raw)
        assert (magic, version, length) == (b'glTF', 2, len(raw))
        size, kind = struct.unpack_from('<I4s', raw, 12)
        assert kind == b'JSON'
        cls.doc = json.loads(raw[20:20 + size])
        offset = 20 + size
        binsize, kind = struct.unpack_from('<I4s', raw, offset)
        assert kind == b'BIN\x00'
        cls.binary = raw[offset + 8:offset + 8 + binsize]

    def accessor(self, index):
        a = self.doc['accessors'][index]
        view = self.doc['bufferViews'][a['bufferView']]
        count = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
        fmt = '<' + {5121: 'B', 5123: 'H', 5125: 'I', 5126: 'f'}[a['componentType']] * count
        stride = view.get('byteStride', struct.calcsize(fmt))
        offset = view.get('byteOffset', 0) + a.get('byteOffset', 0)
        return [struct.unpack_from(fmt, self.binary, offset + i * stride) for i in range(a['count'])]

    def test_single_mesh_material_and_skin(self):
        d = self.doc
        self.assertEqual(len(d['meshes']), 1)
        self.assertEqual(len(d['meshes'][0]['primitives']), 1)
        self.assertEqual(len(d['skins']), 1)
        self.assertEqual(len(d['skins'][0]['joints']), 20)
        self.assertEqual(len(d['materials']), 1)
        self.assertFalse(d.get('textures'))
        pbr = d['materials'][0]['pbrMetallicRoughness']
        self.assertAlmostEqual(pbr['roughnessFactor'], .6)
        self.assertEqual(pbr.get('metallicFactor', 1), 0)

    def test_geometry_and_weights(self):
        p = self.doc['meshes'][0]['primitives'][0]
        self.assertEqual(p.get('mode', 4), 4)
        triangles = len(self.accessor(p['indices'])) // 3
        self.assertTrue(15000 <= triangles <= 25000)
        positions = self.accessor(p['attributes']['POSITION'])
        self.assertTrue(all(math.isfinite(c) for v in positions for c in v))
        self.assertAlmostEqual(max(v[1] for v in positions) - min(v[1] for v in positions), 1.8, places=5)
        weights = self.accessor(p['attributes']['WEIGHTS_0'])
        self.assertEqual(len(weights), len(positions))
        self.assertTrue(all(abs(sum(w) - 1) < 1e-5 for w in weights))
        self.assertTrue(all(0 <= c <= 1 for w in weights for c in w))
        self.assertNotIn('WEIGHTS_1', p['attributes'])
        joints = self.accessor(p['attributes']['JOINTS_0'])
        self.assertTrue(all(0 <= j < 20 for v in joints for j in v))

    def test_looped_animations(self):
        animations = self.doc['animations']
        self.assertEqual({a['name'] for a in animations}, {'Idle', 'Walk'})
        for a in animations:
            duration = 2 if a['name'] == 'Idle' else 1
            changed = False
            for sampler in a['samplers']:
                times = self.accessor(sampler['input'])
                values = self.accessor(sampler['output'])
                self.assertAlmostEqual(times[-1][0] - times[0][0], duration, places=5)
                self.assertTrue(all(abs(x - y) < 1e-5 for x, y in zip(values[0], values[-1])))
                changed |= any(abs(x - y) > 1e-5 for v in values[1:-1] for x, y in zip(values[0], v))
            self.assertTrue(changed, f'{a["name"]} must actually animate')


if __name__ == '__main__':
    unittest.main()
