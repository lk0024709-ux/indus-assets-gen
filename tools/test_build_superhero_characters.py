import json
import unittest
from pathlib import Path

from build_superhero_characters import DEFAULT_OUTPUT, validate_glb


class SuperheroCharacterBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((DEFAULT_OUTPUT / "characters.json").read_text(encoding="utf-8"))
        cls.records = {entry["id"]: entry for entry in cls.manifest["models"]}

    def test_all_four_self_contained_models_are_published(self):
        self.assertEqual(
            set(self.records),
            {
                "superhero_female_dark",
                "superhero_female_light",
                "superhero_male_dark",
                "superhero_male_light",
            },
        )
        for record in self.records.values():
            path = DEFAULT_OUTPUT / record["file"]
            self.assertTrue(path.is_file(), record["file"])
            gltf = validate_glb(path)
            self.assertEqual(len(gltf["skins"][0]["joints"]), 65)
            self.assertEqual(len(gltf["images"]), 7)
            self.assertTrue(all("uri" not in image for image in gltf["images"]))
            self.assertTrue(record["skinned"])
            self.assertGreater(record["vertices"], 8_000)

    def test_female_basecolor_variants_use_the_matching_source_map(self):
        expected = {
            "superhero_female_dark": "T_Superhero_Female_Dark_BaseColor",
            "superhero_female_light": "T_Superhero_Female_Light_BaseColor",
        }
        for model_id, expected_name in expected.items():
            gltf = validate_glb(DEFAULT_OUTPUT / self.records[model_id]["file"])
            material = next(item for item in gltf["materials"] if item["name"] == "MI_Superhero_Female")
            texture = gltf["textures"][material["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
            image = gltf["images"][texture["source"]]
            self.assertEqual(image["name"], expected_name)

    def test_male_basecolor_variants_use_the_matching_source_map(self):
        expected = {
            "superhero_male_dark": "T_Superhero_Male_Dark",
            "superhero_male_light": "T_Superhero_Male_Light",
        }
        for model_id, expected_name in expected.items():
            gltf = validate_glb(DEFAULT_OUTPUT / self.records[model_id]["file"])
            material = next(item for item in gltf["materials"] if item["name"] == "MI_Superhero_Male")
            texture = gltf["textures"][material["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
            image = gltf["images"][texture["source"]]
            self.assertEqual(image["name"], expected_name)


if __name__ == "__main__":
    unittest.main()
