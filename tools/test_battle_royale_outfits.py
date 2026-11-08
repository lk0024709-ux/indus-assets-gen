import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

from build_battle_royale_outfits import (
    DEFAULT_OUTPUT,
    build_standalone_outfit_glb,
    pack_character_with_outfit,
    parse_glb_chunks,
    read_gltf_accessor,
)
from build_superhero_characters import DEFAULT_OUTPUT as CHAR_OUTPUT, validate_glb

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "procedural_asset_app" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
import registry  # noqa: E402


EXPECTED_FITTED_PIECES = {
    "Tee", "Cargo_Pants", "Boots",
    "Belt", "Belt_Buckle", "Pouch_R", "Pouch_L",
    "Bullet_0", "Bullet_1", "Bullet_2", "Carabiner",
    "KneePad_R", "Holster", "Holster_Strap_0", "Holster_Strap_1",
    "KneePad_L", "Cargo_Pocket", "Cargo_Flap",
    "Tee_ChestPatch", "Tee_ChestStar",
}

EXPECTED_STANDALONE_PIECES = {
    "Tee_Body", "Tee_Collar", "Tee_Sleeve_R", "Tee_Sleeve_L", "Tee_ChestPatch", "Tee_ChestStar",
    "Pants_Hips", "Pants_Leg_R", "KneePad_R", "Pants_Leg_L", "KneePad_L", "Cargo_Pocket", "Cargo_Flap",
    "Holster", "Holster_Strap_0", "Holster_Strap_1",
    "Belt", "Belt_Buckle", "Pouch_R", "Pouch_L", "Bullet_0", "Bullet_1", "Bullet_2", "Carabiner",
    "Boot_Shaft_R", "Boot_Foot_R", "Boot_Sole_R", "Boot_Shaft_L", "Boot_Foot_L", "Boot_Sole_L",
}


def check_closed_manifold(positions: list[tuple[float, ...]], indices: list[int]) -> tuple[int, int]:
    weld: dict[tuple[int, int, int], int] = {}
    vid = []
    for x, y, z in positions:
        key = (round(x * 100_000), round(y * 100_000), round(z * 100_000))
        if key not in weld:
            weld[key] = len(weld)
        vid.append(weld[key])
    edge_counts: dict[tuple[int, int], int] = {}
    for k in range(0, len(indices), 3):
        a, b, c = vid[indices[k]], vid[indices[k + 1]], vid[indices[k + 2]]
        if a == b or b == c or a == c:
            continue
        for u, v in ((a, b), (b, c), (c, a)):
            e = (min(u, v), max(u, v))
            edge_counts[e] = edge_counts.get(e, 0) + 1
    boundary = sum(1 for c in edge_counts.values() if c == 1)
    nonmanifold = sum(1 for c in edge_counts.values() if c > 2)
    return boundary, nonmanifold


class BattleRoyaleOutfitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((DEFAULT_OUTPUT / "outfits.json").read_text(encoding="utf-8"))
        cls.records = {item["id"]: item for item in cls.manifest["outfits"]}

    def test_manifest_contains_both_fitted_rigs_and_standalone_kit(self):
        self.assertEqual(
            set(self.records),
            {"outfit_br_female", "outfit_br_male", "outfit_battle_royale"},
        )
        self.assertTrue((ROOT / "tools" / "outfit_fit_character.py").is_file())
        self.assertTrue((ROOT / "tools" / "outfit_battle_royale.py").is_file())

    def test_fitted_outfits_are_watertight_and_match_character_65_joint_skins(self):
        pairs = (
            ("outfit_br_female", "superhero_female_dark.glb"),
            ("outfit_br_male", "superhero_male_dark.glb"),
        )
        for outfit_id, hero_file in pairs:
            with self.subTest(outfit=outfit_id):
                outfit_path = DEFAULT_OUTPUT / self.records[outfit_id]["file"]
                self.assertTrue(outfit_path.is_file())
                out_gltf, out_bin = parse_glb_chunks(outfit_path)
                hero_gltf, _ = parse_glb_chunks(CHAR_OUTPUT / hero_file)

                out_joints = [out_gltf["nodes"][j]["name"] for j in out_gltf["skins"][0]["joints"]]
                hero_joints = [hero_gltf["nodes"][j]["name"] for j in hero_gltf["skins"][0]["joints"]]
                self.assertEqual(len(out_joints), 65)
                self.assertEqual(out_joints, hero_joints)

                mesh_names = {m["name"] for m in out_gltf["meshes"]}
                self.assertEqual(mesh_names, EXPECTED_FITTED_PIECES)

                for mesh in out_gltf["meshes"]:
                    prim = mesh["primitives"][0]
                    pos = read_gltf_accessor(out_gltf, out_bin, prim["attributes"]["POSITION"])
                    nrm = read_gltf_accessor(out_gltf, out_bin, prim["attributes"]["NORMAL"])
                    jts = read_gltf_accessor(out_gltf, out_bin, prim["attributes"]["JOINTS_0"])
                    wts = read_gltf_accessor(out_gltf, out_bin, prim["attributes"]["WEIGHTS_0"])
                    idx = [t[0] for t in read_gltf_accessor(out_gltf, out_bin, prim["indices"])]

                    boundary, nonmanifold = check_closed_manifold(pos, idx)
                    self.assertEqual(boundary, 0, f"{mesh['name']} has open boundary edges")
                    self.assertEqual(nonmanifold, 0, f"{mesh['name']} has non-manifold edges")

                    for nx, ny, nz in nrm[:25]:
                        self.assertAlmostEqual(math.sqrt(nx * nx + ny * ny + nz * nz), 1.0, places=3)
                    for j4, w4 in zip(jts[:50], wts[:50]):
                        self.assertTrue(all(0 <= j < 65 for j in j4))
                        self.assertAlmostEqual(sum(w4), 1.0, places=4)

    def test_standalone_outfit_has_all_30_modular_pieces(self):
        path = DEFAULT_OUTPUT / self.records["outfit_battle_royale"]["file"]
        gltf, binary = parse_glb_chunks(path)
        self.assertNotIn("skins", gltf)
        self.assertEqual({m["name"] for m in gltf["meshes"]}, EXPECTED_STANDALONE_PIECES)
        for mesh in gltf["meshes"]:
            prim = mesh["primitives"][0]
            pos = read_gltf_accessor(gltf, binary, prim["attributes"]["POSITION"])
            idx = [t[0] for t in read_gltf_accessor(gltf, binary, prim["indices"])]
            boundary, nonmanifold = check_closed_manifold(pos, idx)
            self.assertEqual(boundary, 0, mesh["name"])
            self.assertEqual(nonmanifold, 0, mesh["name"])

    def test_character_and_outfit_combiner_preserves_textures_and_filters_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            full_out = tmp_dir / "female_full_br.glb"
            info_full = pack_character_with_outfit(
                CHAR_OUTPUT / "superhero_female_dark.glb",
                DEFAULT_OUTPUT / "outfit_br_female.glb",
                full_out,
            )
            self.assertEqual(info_full["added_pieces"], 20)
            merged_gltf = validate_glb(full_out)
            self.assertEqual(len(merged_gltf["images"]), 7)
            self.assertEqual(len(merged_gltf["skins"][0]["joints"]), 65)
            self.assertEqual(len(merged_gltf["meshes"]), 23)

            subset_out = tmp_dir / "male_subset_br.glb"
            info_sub = pack_character_with_outfit(
                CHAR_OUTPUT / "superhero_male_light.glb",
                DEFAULT_OUTPUT / "outfit_br_male.glb",
                subset_out,
                included_groups={"tee", "boots"},
            )
            self.assertEqual(info_sub["added_pieces"], 4)  # Tee, Tee_ChestPatch, Tee_ChestStar, Boots
            validate_glb(subset_out)

    def test_procedural_recipe_validation_and_standalone_options(self):
        validated = registry.validate_params(
            "battle_royale_outfit",
            {"height": 1.85, "include_holster": False, "include_boots": False},
        )
        self.assertEqual(validated["height"], 1.85)
        self.assertFalse(validated["include_holster"])
        self.assertFalse(validated["include_boots"])
        with tempfile.TemporaryDirectory() as tmp:
            custom_glb = Path(tmp) / "custom_br.glb"
            rec = build_standalone_outfit_glb(
                custom_glb,
                height=validated["height"],
                include_holster=False,
                include_pouches=False,
                include_boots=False,
            )
            # 30 - 3 (holster) - 5 (pouches+bullets) - 6 (boots) = 16 pieces
            self.assertEqual(rec["pieces"], 16)


if __name__ == "__main__":
    unittest.main()
