"""Run: blender -b --python-exit-code 1 -P tests/smoke.py"""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asset_factory as factory


def snapshot(seed):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj = factory.build({"type": "rock", "shade": "smooth"}, "TestRock", seed)
    assert obj.data.uv_layers.active and all(
        face.use_smooth for face in obj.data.polygons
    )
    coords = tuple(tuple(v.co) for v in obj.data.vertices)
    assert min(z for _, _, z in coords) == 0
    return coords


assert snapshot(7) == snapshot(7) != snapshot(8)
with TemporaryDirectory() as tmp:
    root = Path(tmp)
    spec = root / "assets.json"
    spec.write_text(
        json.dumps(
            {
                "assets": [
                    {"type": "tree", "params": {"segments": 2}},
                    {"type": "crate", "name": "../escape"},
                    {"type": "rock", "count": 2, "seed": 7},
                ]
            }
        )
    )
    with patch.object(
        sys,
        "argv",
        [
            "blender",
            "--",
            "--spec",
            str(spec),
            "--out",
            tmp,
            "--formats",
            "glb,fbx,blend",
        ],
    ):
        assert factory.main() == 1
    records = json.loads((root / "manifest.json").read_text())
    assert [r["name"] for r in records] == ["rock_01", "rock_02"]
    for r in records:
        assert r["tris"] > 0 and min(r["dimensions"]) > 0
        assert all((root / f).stat().st_size > 0 for f in r["files"])
        bpy.ops.wm.open_mainfile(filepath=str(root / (r["name"] + ".blend")))
        assert list(bpy.data.objects.keys()) == [r["name"]]
print("Factory smoke checks passed.")
