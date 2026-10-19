#!/usr/bin/env python3
"""Test-asset generator for the Indus : Battle Royale 3D pipeline.

Runs headless through the pip-installable ``bpy`` module (Blender as a Python
module) and performs the full pipeline loop on a dummy asset:

1. Clear the default scene.
2. Create a 1x1x1 cube with a brown Principled BSDF material
   (Roughness 0.8) - our stand-in "test crate".
3. Export the scene as binary glTF to ``docs/models/test_crate.glb``.

Usage:
    pip install bpy
    python tools/generate_test.py
"""

from __future__ import annotations

import os
import sys

import bpy

# --- Asset parameters -------------------------------------------------------
# Brown crate colour (linear RGBA accepted by the Principled BSDF node).
CRATE_COLOR = (0.28, 0.145, 0.06, 1.0)
CRATE_ROUGHNESS = 0.8
CRATE_METALLIC = 0.0
CRATE_SIZE = 1.0

# --- Paths -----------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "docs", "models", "test_crate.glb")


def clear_scene() -> None:
    """Reset Blender to a completely empty scene (no default cube/camera/light)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


def create_test_crate() -> bpy.types.Object:
    """Create a 1x1x1 cube with the brown crate material and return it."""
    bpy.ops.mesh.primitive_cube_add(size=CRATE_SIZE, location=(0.0, 0.0, 0.0))
    cube = bpy.context.active_object
    cube.name = "TestCrate"
    cube.data.name = "TestCrateMesh"

    material = bpy.data.materials.new(name="TestCrateBrown")
    # Node-based materials are mandatory since Blender 5.0 (use_nodes deprecated).
    if bpy.app.version < (5, 0, 0):
        material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        raise RuntimeError("Principled BSDF node not found in new material")
    bsdf.inputs["Base Color"].default_value = CRATE_COLOR
    bsdf.inputs["Roughness"].default_value = CRATE_ROUGHNESS
    bsdf.inputs["Metallic"].default_value = CRATE_METALLIC
    cube.data.materials.append(material)

    print(f"Created cube: {cube.name} ({CRATE_SIZE}x{CRATE_SIZE}x{CRATE_SIZE})")
    return cube


def export_glb(output_path: str) -> None:
    """Export the current scene as binary glTF (.glb)."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=output_path, export_format="GLB")
    if not os.path.isfile(output_path):
        raise RuntimeError(f"Export failed, file not written: {output_path}")
    print(f"Exported: {output_path} ({os.path.getsize(output_path)} bytes)")


def main() -> int:
    """Entry point used both locally and by the GitHub Actions pipeline."""
    print(f"Blender (bpy) version: {bpy.app.version_string}")
    clear_scene()
    create_test_crate()
    export_glb(OUTPUT_PATH)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
