import json
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "procedural_asset_app" / "frontend"


class PageElements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.select_ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "select" and "id" in attrs:
            self.select_ids.add(attrs["id"])


class CharacterMotionUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (FRONTEND / "characters.html").read_text(encoding="utf-8")
        cls.js = (FRONTEND / "character-viewer.js").read_text(encoding="utf-8")
        cls.css = (FRONTEND / "character-viewer.css").read_text(encoding="utf-8")
        cls.manifest = json.loads((FRONTEND / "assets/motion-manifest.json").read_text(encoding="utf-8"))
        cls.page = PageElements()
        cls.page.feed(cls.html)

    def test_manifest_has_74_unique_motion_buttons_to_render(self):
        motions = self.manifest["motions"]
        self.assertEqual(self.manifest["count"], 74)
        self.assertEqual(len(motions), 74)
        self.assertEqual(len({motion["id"] for motion in motions}), 74)
        self.assertEqual({motion["category"] for motion in motions}, {"Movement", "Stance", "Combat", "Special"})

    def test_player_has_library_and_keeps_transport_controls(self):
        for element_id in (
            "motionLibrary", "motionPlay", "motionStop", "motionSpeed", "motionSeek", "motionStatus",
            "outfitModes", "outfitGroups", "outfitPieceCount", "downloadModel", "downloadOutfit",
        ):
            self.assertIn(element_id, self.page.ids)
        self.assertNotIn("motionSelect", self.page.select_ids)
        self.assertIn('aria-describedby="motionLibraryHelp"', self.html)

    def test_motion_buttons_are_generated_grouped_and_play_on_activation(self):
        for marker in (
            "function populateMotionLibrary()",
            "button.className = 'motion-choice'",
            "button.dataset.motionId = motion.id",
            "button.setAttribute('aria-pressed'",
            "buttonGroup.setAttribute('role', 'group')",
            "$('motionLibrary').addEventListener('click'",
            "playMotion(button.dataset.motionId)",
        ):
            self.assertIn(marker, self.js)

    def test_motion_list_is_scrollable_responsive_and_keyboard_focusable(self):
        self.assertIn("overflow:auto", self.css)
        self.assertIn("@media(max-width:720px)", self.css)
        self.assertIn("@media(max-width:360px)", self.css)
        self.assertIn(".motion-choice:focus-visible", self.css)
        self.assertIn(".motion-choice[aria-pressed=\"true\"]", self.css)
        self.assertNotIn(".motion-category-heading{position:sticky", self.css)


if __name__ == "__main__":
    unittest.main()
