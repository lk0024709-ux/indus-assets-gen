"""Dependency-free export and anatomical inventory regression tests."""
from pathlib import Path
import struct
import json
import unittest

BASE = Path(__file__).resolve().parents[1] / 'docs/models/characters/skeleton'


class SkeletonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=(BASE/'skeleton_base_midpoly.glb').read_bytes()
        assert struct.unpack_from('<4sII',raw)==(b'glTF',2,len(raw))
        n=struct.unpack_from('<I',raw,12)[0]
        cls.doc=json.loads(raw[20:20+n]);cls.binary=raw[28+n:]
        cls.report=json.loads((BASE/'skeleton_base_midpoly.validation.json').read_text())

    def values(self,index):
        a=self.doc['accessors'][index];v=self.doc['bufferViews'][a['bufferView']]
        size={'SCALAR':1,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']]
        fmt='<'+{5121:'B',5123:'H',5125:'I',5126:'f'}[a['componentType']]*size
        start=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',struct.calcsize(fmt))
        return [struct.unpack_from(fmt,self.binary,start+i*stride) for i in range(a['count'])]

    def test_budget_and_material(self):
        self.assertEqual(len(self.doc['meshes']),1)
        tri=sum(len(self.values(p['indices']))//3 for p in self.doc['meshes'][0]['primitives'])
        self.assertEqual(tri,24816)
        self.assertTrue(15000<=tri<=25000)
        self.assertGreater(self.report['quads']/self.report['faces'],.8)
        self.assertEqual(len(self.doc['materials']),1)
        self.assertAlmostEqual(self.doc['materials'][0]['pbrMetallicRoughness']['roughnessFactor'],.4)
        self.assertFalse(self.doc.get('textures'))

    def test_rigid_weights_and_hierarchy(self):
        skin=self.doc['skins'][0];joints=skin['joints'];self.assertEqual(len(joints),151)
        for primitive in self.doc['meshes'][0]['primitives']:
            self.assertNotIn('WEIGHTS_1',primitive['attributes'])
            weights=self.values(primitive['attributes']['WEIGHTS_0'])
            self.assertTrue(all(sorted(w)==[0,0,0,1] for w in weights))
            indices=self.values(primitive['attributes']['JOINTS_0'])
            self.assertTrue(all(0<=i<len(joints) for js in indices for i in js))
        names={self.doc['nodes'][i]['name'] for i in joints}
        for prefix,count in [('C',7),('T',12),('L',5)]:
            self.assertTrue({f'{prefix}{i}' for i in range(1,count+1)}<=names)
        for side in ('L','R'):
            for digit in range(1,6):
                for i in range(1,3 if digit==1 else 4):
                    self.assertIn(f'Finger_{digit}_Phalanx_{i}.{side}',names)
                    self.assertIn(f'Toe_{digit}_Phalanx_{i}.{side}',names)

    def test_anatomical_inventory(self):
        names={p['name'] for p in self.report['parts']}
        self.assertEqual(len(names),375)
        for side in ('L','R'):
            for rib in range(1,13):self.assertIn(f'Rib_{rib:02}.{side}',names)
            for i in range(7):self.assertIn(f'Tarsal_{i+1}.{side}',names)
            for row in range(2):
                for col in range(4):self.assertIn(f'Carpal_{row}_{col}.{side}',names)
        self.assertIn('Cranium_with_orbital_and_nasal_cavities',names)
        self.assertEqual(sum('_tooth_' in n for n in names),28)
        self.assertTrue({'Mandible','Maxilla','Sternal_body','Coccyx'}<=names)


if __name__=='__main__':unittest.main()
