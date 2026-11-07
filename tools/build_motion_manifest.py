#!/usr/bin/env python3
"""Create the browser library manifest for every supplied FBX motion."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MOTION_DIR = ROOT / "Base model " / "Motion"
DEFAULT_OUTPUT = ROOT / "procedural_asset_app" / "frontend" / "assets" / "motion-manifest.json"


def category_for(name: str) -> str:
    value = name.casefold()
    if any(word in value for word in ("death", "dying", "dive roll", "swimming", "skateboarding")):
        return "Special"
    if any(word in value for word in ("rifle", "firing", "grenade", "reloading", "reaction", "grab", "toss")):
        return "Combat"
    if any(word in value for word in ("idle", "crouch", "prone")):
        return "Stance"
    return "Movement"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")


def build_manifest(output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    files = sorted(MOTION_DIR.glob("*.fbx"), key=lambda path: (path.stem.casefold(), path.name.casefold()))
    if not files:
        raise FileNotFoundError(f"No FBX motions found in {MOTION_DIR}")
    motions = []
    for path in files:
        motions.append({
            "id": slug(path.stem),
            "label": path.stem.title(),
            "category": category_for(path.stem),
            "file": path.name,
            "bytes": path.stat().st_size,
        })
    ids = [motion["id"] for motion in motions]
    if len(ids) != len(set(ids)):
        raise ValueError("Motion file names produce duplicate manifest IDs")
    manifest = {
        "source": "Base model /Motion",
        "format": "FBX",
        "rig": "Mixamo 65-bone skeleton; retargeted onto the existing 65-joint superhero rig in the browser",
        "count": len(motions),
        "motions": motions,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(motions)} FBX motions to {output}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build_manifest(args.output)


if __name__ == "__main__":
    main()
