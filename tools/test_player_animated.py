"""Dependency-free checks for the retargeted, animated player GLB.

These run against the build products of ``tools/retarget_animations.py``:

    characters/player_animated.glb
    characters/clothing/*.glb
    characters/player_animated.report.json

Those files are generated, not committed, so the whole module skips when they
are absent -- that keeps a plain ``python -m unittest discover tools`` green on
a fresh clone. Set ``REQUIRE_ANIMATED=1`` (the build workflow does) to turn the
skip into a hard failure instead.
"""
from pathlib import Path
import json
import os
import struct
import unittest

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / 'characters'
PLAYER = BASE / 'player_animated.glb'
REPORT = BASE / 'player_animated.report.json'
CLOTHING = BASE / 'clothing'
MIRROR = REPO / 'docs/models/characters'

REQUIRED = os.environ.get('REQUIRE_ANIMATED') == '1'
HAVE = PLAYER.exists() and REPORT.exists()
if REQUIRED and not HAVE:
    raise SystemExit(f'REQUIRE_ANIMATED=1 but {PLAYER} is missing; run '
                     f'tools/retarget_animations.py first')

# The 27-bone contract, rebuilt here rather than imported so that a rig change
# has to be made deliberately in two places.
EXPECTED = {'HIPS': None, 'SPINE_NAVAL': 'HIPS', 'SPINE_CHEST': 'SPINE_NAVAL',
            'NECK': 'SPINE_CHEST', 'HEAD': 'NECK'}
for _side in ('L', 'R'):
    _prev = 'SPINE_CHEST'
    for _part in ('CLAVICLE', 'SHOULDER', 'ELBOW', 'WRIST', 'HAND'):
        EXPECTED[f'{_part}_{_side}'] = _prev
        _prev = f'{_part}_{_side}'
    EXPECTED[f'THUMB_{_side}'] = f'HAND_{_side}'
    EXPECTED[f'HANDTIP_{_side}'] = f'HAND_{_side}'
    _prev = 'HIPS'
    for _part in ('HIP', 'KNEE', 'ANKLE', 'FOOT'):
        EXPECTED[f'{_part}_{_side}'] = _prev
        _prev = f'{_part}_{_side}'

# Clips the game actually needs; the manifest may grow, but never shrink below
# this set without someone noticing.
CORE_CLIPS = {
    'Idle', 'IdleAiming', 'IdleCrouch', 'ProneIdle',
    'Walk_F', 'Walk_B', 'Walk_L', 'Walk_R',
    'Run_F', 'Run_B', 'Run_L', 'Run_R',
    'Sprint', 'CrouchWalk', 'DiveRoll', 'TossGrenade', 'FireRifle', 'Reload',
    'HitReaction', 'JumpUp', 'JumpLoop', 'JumpDown',
    'Dying', 'DeathFront', 'DeathBack', 'TurnLeft90', 'TurnRight90',
}

# Must match the constants in tools/retarget_animations.py.
CONTACT_FLOAT_LIMIT = 0.020
FLOOR_TOL_BELOW = 0.010
BODY_STRETCH_LIMIT = 1.75
BODY_GROWTH_LIMIT = 0.030
MAX_INFLUENCES = 4


class Glb:
    """Minimal glTF-binary reader: just enough to audit what we shipped."""

    def __init__(self, path: Path):
        raw = path.read_bytes()
        magic, version, total = struct.unpack_from('<4sII', raw)
        assert magic == b'glTF' and version == 2, f'{path} is not glTF 2 binary'
        assert total == len(raw), f'{path} header length {total} != {len(raw)}'
        n = struct.unpack_from('<I', raw, 12)[0]
        self.doc = json.loads(raw[20:20 + n])
        self.bin = raw[28 + n:]
        self.path = path

    def accessor(self, index):
        a = self.doc['accessors'][index]
        comps = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
        ctype = {5120: 'b', 5121: 'B', 5122: 'h', 5123: 'H', 5125: 'I', 5126: 'f'}
        fmt = '<' + ctype[a['componentType']] * comps
        size = struct.calcsize(fmt)
        if 'bufferView' not in a:                       # all-zero sparse base
            return [(0,) * comps] * a['count']
        view = self.doc['bufferViews'][a['bufferView']]
        stride = view.get('byteStride') or size
        off = view.get('byteOffset', 0) + a.get('byteOffset', 0)
        out = [struct.unpack_from(fmt, self.bin, off + i * stride)
               for i in range(a['count'])]
        if a.get('normalized'):
            scale = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}
            d = scale[a['componentType']]
            out = [tuple(max(v / d, 0.0) for v in row) for row in out]
        return out

    def joint_names(self):
        joints = {i for skin in self.doc['skins'] for i in skin['joints']}
        return {self.doc['nodes'][i]['name'] for i in joints}

    def parentage(self):
        joints = {i for skin in self.doc['skins'] for i in skin['joints']}
        parents = {c: i for i, node in enumerate(self.doc['nodes'])
                   for c in node.get('children', [])}
        out = {}
        for i in joints:
            p = parents.get(i)
            while p is not None and p not in joints:
                p = parents.get(p)
            out[self.doc['nodes'][i]['name']] = (
                self.doc['nodes'][p]['name'] if p is not None else None)
        return out


@unittest.skipUnless(HAVE, 'player_animated.glb not built; run '
                           'tools/retarget_animations.py')
class PlayerAnimatedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.glb = Glb(PLAYER)
        cls.doc = cls.glb.doc
        cls.report = json.loads(REPORT.read_text())

    # --- rig ----------------------------------------------------------------

    def test_single_skeleton_of_exactly_27_named_bones(self):
        names = self.glb.joint_names()
        self.assertEqual(len(names), 27, 'the rig must stay at 27 bones')
        self.assertEqual(names, set(EXPECTED))
        self.assertEqual(self.glb.parentage(), EXPECTED)
        skins = self.doc['skins']
        self.assertEqual(len({tuple(s['joints']) for s in skins}), 1,
                         'every mesh must share one skeleton')

    def test_no_vertex_exceeds_four_influences_and_none_is_unweighted(self):
        for mesh in self.doc['meshes']:
            for prim in mesh['primitives']:
                attrs = prim['attributes']
                self.assertIn('JOINTS_0', attrs, f"{mesh['name']} is not skinned")
                self.assertNotIn('JOINTS_1', attrs,
                                 f"{mesh['name']} exceeds {MAX_INFLUENCES} influences")
                for w in self.glb.accessor(attrs['WEIGHTS_0']):
                    nonzero = [v for v in w if v > 1e-6]
                    self.assertLessEqual(len(nonzero), MAX_INFLUENCES)
                    self.assertGreater(sum(w), 0.5,
                                       f'unweighted vertex in {mesh["name"]}')
                    self.assertAlmostEqual(sum(w), 1.0, places=2)

    # --- animation ----------------------------------------------------------

    def test_every_clip_is_embedded_and_core_clips_are_present(self):
        anims = [a.get('name') for a in self.doc.get('animations', [])]
        self.assertEqual(len(anims), len(set(anims)), 'duplicate animation names')
        self.assertEqual(set(anims),
                         {c['name'] for c in self.report['clips']},
                         'GLB animations and report clips disagree')
        self.assertLessEqual(CORE_CLIPS, set(anims),
                             f'missing clips: {sorted(CORE_CLIPS - set(anims))}')

    def test_animations_drive_only_rig_joints(self):
        joints = {i for skin in self.doc['skins'] for i in skin['joints']}
        for anim in self.doc['animations']:
            self.assertTrue(anim['channels'], f"{anim['name']} has no channels")
            paths = set()
            for ch in anim['channels']:
                node = ch['target']['node']
                self.assertIn(node, joints,
                              f"{anim['name']} animates non-joint node {node}")
                paths.add(ch['target']['path'])
            self.assertIn('rotation', paths, f"{anim['name']} has no rotation")

    def test_no_quaternion_flips_in_any_rotation_track(self):
        """Consecutive keys on a track must stay in the same hemisphere.

        A sign flip between neighbouring quaternions is invisible as a pose but
        makes every runtime slerp take the long way round -- the limb snaps
        through a full rotation on a single frame.
        """
        worst = (1.0, None)
        for anim in self.doc['animations']:
            for ch in anim['channels']:
                if ch['target']['path'] != 'rotation':
                    continue
                keys = self.glb.accessor(
                    anim['samplers'][ch['sampler']]['output'])
                name = self.doc['nodes'][ch['target']['node']]['name']
                for i in range(1, len(keys)):
                    dot = sum(a * b for a, b in zip(keys[i - 1], keys[i]))
                    if dot < worst[0]:
                        worst = (dot, f"{anim['name']}/{name} key {i}")
        self.assertGreaterEqual(worst[0], 0.0, f'quaternion flip at {worst[1]}')

    # --- measured quality gates ---------------------------------------------

    def test_report_shows_feet_planted_and_mesh_above_the_floor(self):
        for clip in self.report['clips']:
            with self.subTest(clip=clip['name']):
                self.assertLessEqual(clip['contact_float_m'], CONTACT_FLOAT_LIMIT,
                                     'planted foot floats')
                self.assertGreaterEqual(clip['min_z'], -FLOOR_TOL_BELOW,
                                        'mesh sinks through the floor')
                self.assertGreaterEqual(clip['min_quaternion_dot'], 0.0)

    def test_report_shows_the_body_shell_is_not_stretched(self):
        body = self.report['deformation']['body_shell']
        self.assertLessEqual(body['max_edge_stretch'], BODY_STRETCH_LIMIT)
        self.assertLessEqual(body['max_edge_growth_mm'] / 1000.0,
                             BODY_GROWTH_LIMIT)
        self.assertGreater(self.report['deformation']['poses_sampled'], 0)

    # --- clothing -----------------------------------------------------------

    def test_clothing_shares_the_player_skeleton_bone_for_bone(self):
        garments = sorted(CLOTHING.glob('*.glb'))
        self.assertTrue(garments, 'no clothing GLBs were exported')
        for path in garments:
            with self.subTest(garment=path.name):
                g = Glb(path)
                self.assertEqual(g.joint_names(), set(EXPECTED))
                self.assertEqual(g.parentage(), EXPECTED)

    def test_clothing_is_reported_as_identically_weighted(self):
        self.assertTrue(self.report['clothing'])
        for garment in self.report['clothing']:
            with self.subTest(garment=garment['name']):
                self.assertTrue(garment['weights_identical_to_body'],
                                'clothing must deform exactly like the body')
                self.assertGreater(garment['min_offset_mm'], 0.0)

    # --- publication --------------------------------------------------------

    def test_pages_mirror_matches_the_build_output(self):
        self.assertTrue((MIRROR / 'player_animated.glb').exists())
        self.assertEqual((MIRROR / 'player_animated.glb').read_bytes()[:64],
                         PLAYER.read_bytes()[:64])
        for path in sorted(CLOTHING.glob('*.glb')):
            self.assertTrue((MIRROR / 'clothing' / path.name).exists(),
                            f'{path.name} was not mirrored for Pages')


if __name__ == '__main__':
    unittest.main()
