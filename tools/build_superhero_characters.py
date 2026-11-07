#!/usr/bin/env python3
"""Pack the repository's superhero GLTFs and source PBR maps into self-contained GLBs.

This intentionally uses only Python's standard library so the character assets can be
rebuilt in CI or on a workstation without Blender or an external glTF package.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "Base model " / "Character"
TEXTURE_DIR = ROOT / "Base model " / "Texture"
DEFAULT_OUTPUT = ROOT / "procedural_asset_app" / "frontend" / "assets" / "characters"
GLB_MAGIC = b"glTF"
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def align4(data: bytes | bytearray, pad: bytes = b"\0") -> bytes:
    return bytes(data) + pad * ((-len(data)) % 4)


def find_texture(image: dict[str, Any]) -> Path:
    """Resolve exporter URI quirks using both the URI and its human-readable name."""
    raw_candidates = [image.get("uri", ""), image.get("name", "")]
    candidates: list[str] = []
    for raw in raw_candidates:
        name = Path(raw).name
        if not name:
            continue
        candidates.append(name)
        if name.lower().endswith(".png.png"):
            candidates.append(name[:-4])
        if name.lower().endswith("_png.png"):
            candidates.append(name[:-8] + ".png")
        if not Path(name).suffix:
            candidates.append(name + ".png")
    files = {p.name.casefold(): p for p in TEXTURE_DIR.iterdir() if p.is_file()}
    for candidate in candidates:
        if candidate.casefold() in files:
            return files[candidate.casefold()]
    raise FileNotFoundError(
        f"Could not map glTF image {image!r} to a file in {TEXTURE_DIR}; "
        f"tried {candidates!r}"
    )


def pack_gltf(source: Path, destination: Path, *, basecolor_variant: str = "dark") -> dict[str, Any]:
    gltf = json.loads(source.read_text(encoding="utf-8"))
    if len(gltf.get("buffers", [])) != 1 or gltf["buffers"][0].get("uri") is None:
        raise ValueError(f"Expected one external binary buffer in {source}")

    source_buffer_path = source.parent / gltf["buffers"][0]["uri"]
    binary = bytearray(source_buffer_path.read_bytes())
    expected_bytes = gltf["buffers"][0]["byteLength"]
    if len(binary) < expected_bytes:
        raise ValueError(f"Truncated geometry buffer: {source_buffer_path}")
    if len(binary) > expected_bytes:
        # Preserve only the declared glTF payload; exporters can leave trailing bytes.
        del binary[expected_bytes:]

    texture_names: list[str] = []
    if basecolor_variant not in {"dark", "light"}:
        raise ValueError(f"Unsupported BaseColor variant: {basecolor_variant}")
    is_female = "Female" in source.name
    if basecolor_variant == "light":
        if is_female:
            source_basecolor_name = "T_Superhero_Female_Dark_BaseColor"
            output_basecolor_name = "T_Superhero_Female_Light_BaseColor"
            basecolor_path = TEXTURE_DIR / "T_Superhero_Female_Light_BaseColor.png"
        else:
            source_basecolor_name = "T_Superhero_Male_Dark"
            output_basecolor_name = "T_Superhero_Male_Light"
            # The source repository spells this filename "Ligh".
            basecolor_path = TEXTURE_DIR / "T_Superhero_Male_Ligh.png"
        if not basecolor_path.is_file():
            raise FileNotFoundError(f"Missing alternate BaseColor PNG: {basecolor_path}")
    else:
        source_basecolor_name = output_basecolor_name = ""
        basecolor_path = None

    for image in gltf.get("images", []):
        if basecolor_path and image.get("name") == source_basecolor_name:
            texture_path = basecolor_path
            image["name"] = output_basecolor_name
        else:
            texture_path = find_texture(image)
        payload = texture_path.read_bytes()
        if image.get("mimeType") == "image/png" and not payload.startswith(PNG_SIGNATURE):
            raise ValueError(f"Expected a PNG image at {texture_path}")
        binary.extend(b"\0" * ((-len(binary)) % 4))
        image_view = len(gltf.setdefault("bufferViews", []))
        gltf["bufferViews"].append({
            "buffer": 0,
            "byteOffset": len(binary),
            "byteLength": len(payload),
        })
        binary.extend(payload)
        image.pop("uri", None)
        image["bufferView"] = image_view
        image["mimeType"] = "image/png"
        texture_names.append(texture_path.name)

    gltf["buffers"][0].pop("uri", None)
    gltf["buffers"][0]["byteLength"] = len(binary)
    gltf.setdefault("asset", {})["generator"] = "Indus Superhero GLB packer (source rig and PBR maps preserved)"
    destination.parent.mkdir(parents=True, exist_ok=True)
    json_chunk = align4(json.dumps(gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), b" ")
    binary_chunk = align4(binary)
    total_length = 12 + 8 + len(json_chunk) + 8 + len(binary_chunk)
    with destination.open("wb") as out:
        out.write(struct.pack("<4sII", GLB_MAGIC, 2, total_length))
        out.write(struct.pack("<II", len(json_chunk), JSON_CHUNK))
        out.write(json_chunk)
        out.write(struct.pack("<II", len(binary_chunk), BIN_CHUNK))
        out.write(binary_chunk)

    validate_glb(destination)
    vertices = sum(
        gltf["accessors"][primitive["attributes"]["POSITION"]]["count"]
        for mesh in gltf.get("meshes", [])
        for primitive in mesh.get("primitives", [])
    )
    return {
        "file": destination.name,
        "bytes": destination.stat().st_size,
        "meshes": len(gltf.get("meshes", [])),
        "vertices": vertices,
        "materials": [material.get("name", "") for material in gltf.get("materials", [])],
        "textures": texture_names,
        "skinned": bool(gltf.get("skins")),
        "joints": len(gltf.get("skins", [{}])[0].get("joints", [])),
        "animations": [animation.get("name", "") for animation in gltf.get("animations", [])],
        "basecolor_variant": basecolor_variant,
    }


def validate_glb(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) < 28:
        raise ValueError(f"GLB is too short: {path}")
    magic, version, declared_length = struct.unpack_from("<4sII", raw, 0)
    if magic != GLB_MAGIC or version != 2 or declared_length != len(raw):
        raise ValueError(f"Invalid GLB header or length in {path}")
    json_length, json_type = struct.unpack_from("<II", raw, 12)
    if json_type != JSON_CHUNK:
        raise ValueError(f"GLB JSON chunk missing: {path}")
    gltf = json.loads(raw[20:20 + json_length].decode("utf-8").rstrip(" \0"))
    bin_header = 20 + json_length
    bin_length, bin_type = struct.unpack_from("<II", raw, bin_header)
    if bin_type != BIN_CHUNK or bin_header + 8 + bin_length != len(raw):
        raise ValueError(f"GLB BIN chunk missing or malformed: {path}")
    binary = raw[bin_header + 8:]
    if gltf.get("buffers", [{}])[0].get("byteLength", len(binary)) > len(binary):
        raise ValueError(f"GLB binary chunk is shorter than declared buffer: {path}")
    for image in gltf.get("images", []):
        if "uri" in image or "bufferView" not in image:
            raise ValueError(f"Image is not embedded in {path}: {image.get('name')}")
        view = gltf["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        end = start + view["byteLength"]
        if end > len(binary) or not binary[start:end].startswith(PNG_SIGNATURE):
            raise ValueError(f"Invalid embedded PNG in {path}: {image.get('name')}")
    if not gltf.get("skins"):
        raise ValueError(f"Rig missing from {path}")
    return gltf


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    models = [
        ("Superhero_Female_FullBody.gltf", "superhero_female_dark.glb", "dark"),
        ("Superhero_Female_FullBody.gltf", "superhero_female_light.glb", "light"),
        ("Superhero_Male_FullBody.gltf", "superhero_male_dark.glb", "dark"),
        ("Superhero_Male_FullBody.gltf", "superhero_male_light.glb", "light"),
    ]
    manifest: dict[str, Any] = {
        "title": "Indus Superhero Character Collection",
        "source": "Base model /Character and Base model /Texture",
        "units": "metres",
        "models": [],
    }
    for source_name, output_name, color_variant in models:
        source = SOURCE_DIR / source_name
        if not source.is_file():
            raise FileNotFoundError(f"Missing character source model: {source}")
        record = pack_gltf(source, args.output_dir / output_name, basecolor_variant=color_variant)
        record["id"] = output_name.removesuffix(".glb")
        record["label"] = {
            "superhero_female_dark.glb": "Female · Dark",
            "superhero_female_light.glb": "Female · Light",
            "superhero_male_dark.glb": "Male · Dark",
            "superhero_male_light.glb": "Male · Light",
        }[output_name]
        manifest["models"].append(record)
        print(f"Built {output_name}: {record['vertices']:,} vertices, {record['bytes']:,} bytes, "
              f"{len(record['textures'])} embedded maps")
    manifest_path = args.output_dir / "characters.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()
