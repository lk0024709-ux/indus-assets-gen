import json
import unittest
from pathlib import Path

from build_motion_manifest import DEFAULT_OUTPUT, MOTION_DIR


class MotionManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))

    def test_manifest_covers_every_source_fbx(self):
        source_files = {path.name for path in MOTION_DIR.glob("*.fbx")}
        manifest_files = {motion["file"] for motion in self.manifest["motions"]}
        self.assertEqual(self.manifest["count"], len(source_files))
        self.assertEqual(manifest_files, source_files)
        self.assertEqual(len(manifest_files), 74)

    def test_motion_metadata_is_complete(self):
        for motion in self.manifest["motions"]:
            with self.subTest(file=motion["file"]):
                self.assertTrue((MOTION_DIR / motion["file"]).is_file())
                self.assertTrue(motion["label"])
                self.assertIn(motion["category"], {"Movement", "Stance", "Combat", "Special"})
                self.assertGreater(motion["bytes"], 0)


if __name__ == "__main__":
    unittest.main()
