"""Headless procedural prop generation. Run inside Blender 3.3 or 4.x."""

from __future__ import annotations

import argparse
import inspect
import json
import logging
import math
from pathlib import Path
import random
import re
import sys
from tempfile import TemporaryDirectory
from typing import Callable, Iterable, Sequence

import bpy
import bmesh
from mathutils import Matrix, Vector, noise

BM = bmesh.types.BMesh
RNG = random.Random
Generator = Callable[..., None]
REGISTRY: dict[str, Generator] = {}
LOG = logging.getLogger("factory")


def register(name: str) -> Callable[[Generator], Generator]:
    """Register a generator; fail early on accidental duplicate types."""

    def add(fn: Generator) -> Generator:
        if name in REGISTRY:
            raise ValueError(f"duplicate generator: {name}")
        REGISTRY[name] = fn
        return fn

    return add


def box(bm: BM, size: Sequence[float], center: Sequence[float]) -> None:
    """Create a box about its center."""
    if min(size) <= 0:
        raise ValueError("box dimensions must be positive")
    transform = Matrix.Translation(Vector(center)) @ Matrix.Diagonal(Vector((*size, 1)))
    bmesh.ops.create_cube(bm, size=1, matrix=transform)


def cone(
    bm: BM, lower: float, upper: float, depth: float, z: float = 0, segments: int = 16
) -> None:
    """Add a capped cylinder or tapered cone starting at z."""
    if depth <= 0 or min(lower, upper) < 0 or max(lower, upper) == 0:
        raise ValueError("invalid cone dimensions")
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=lower,
        radius2=upper,
        depth=depth,
        matrix=Matrix.Translation((0, 0, z + depth / 2)),
    )


def lathe(bm: BM, profile: Iterable[tuple[float, float]], segments: int) -> None:
    """Revolve connected (radius, z) rings and cap both ends."""
    rings = []
    for r, z in profile:
        if r <= 0:
            raise ValueError("profile radii must be positive")
        rings.append(
            [
                bm.verts.new(
                    (
                        r * math.cos(math.tau * i / segments),
                        r * math.sin(math.tau * i / segments),
                        z,
                    )
                )
                for i in range(segments)
            ]
        )
    for a, b in zip(rings, rings[1:]):
        for i in range(segments):
            bm.faces.new((a[i - 1], a[i], b[i], b[i - 1]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])


def displace(verts: Iterable, rng: RNG, strength: float, freq: float) -> None:
    """Radial coherent noise with a reproducible sampling offset."""
    offset = Vector([rng.uniform(-100, 100) for _ in range(3)])
    for v in verts:
        v.co *= 1 + strength * noise.noise(v.co * freq + offset)


@register("crate")
def crate(bm: BM, rng: RNG, size: float = 1.0, post: float = 0.08) -> None:
    """Framed shipping crate."""
    h = (size - post) / 2
    for i in range(5):
        box(
            bm,
            (size * 0.18, size * 0.94, size * 0.94),
            ((i - 2) * size * 0.185, 0, size / 2),
        )
    for x in (-h, h):
        for y in (-h, h):
            box(bm, (post, post, size), (x, y, size / 2))
    for z in (post / 2, size - post / 2):
        for s in (-h, h):
            box(bm, (size - 2 * post, post, post), (0, s, z))
            box(bm, (post, size - 2 * post, post), (s, 0, z))


@register("barrel")
def barrel(
    bm: BM,
    rng: RNG,
    radius: float = 0.35,
    height: float = 1.0,
    bulge: float = 0.12,
    segments: int = 20,
    hoops: bool = True,
) -> None:
    """Turn a barrel profile, including proud hoop ridges."""
    profile = []
    for i in range(21):
        t = i / 20
        r = radius * (1 + bulge * math.sin(math.pi * t))
        ring = hoops and (4 <= i <= 5 or 15 <= i <= 16)
        if ring and i in (4, 15):
            profile.append((r, height * t))
        profile.append((r * (1.04 if ring else 1), height * t))
        if ring and i in (5, 16):
            profile.append((r, height * t))
    lathe(bm, profile, segments)


@register("table")
def table(
    bm: BM,
    rng: RNG,
    width: float = 1.4,
    depth: float = 0.8,
    height: float = 0.75,
    top: float = 0.05,
    leg: float = 0.06,
) -> None:
    """Four-legged rectangular table."""
    box(bm, (width, depth, top), (0, 0, height - top / 2))
    if 2 * leg >= min(width, depth):
        raise ValueError("legs too wide")
    for x in (-1, 1):
        for y in (-1, 1):
            box(
                bm,
                (leg, leg, height - top),
                (x * (width / 2 - leg), y * (depth / 2 - leg), (height - top) / 2),
            )


@register("chair")
def chair(
    bm: BM,
    rng: RNG,
    seat: float = 0.45,
    seat_h: float = 0.45,
    back_h: float = 0.5,
    leg: float = 0.04,
) -> None:
    """Square seat and slatted back."""
    table(bm, rng, seat, seat, seat_h, leg, leg)
    o = seat / 2 - leg
    for x in (-o, o):
        box(bm, (leg, leg, back_h), (x, o, seat_h + back_h / 2))
    for t in (0.4, 0.65, 0.9):
        box(bm, (2 * o - leg, leg * 0.65, back_h * 0.14), (0, o, seat_h + back_h * t))


@register("rock")
def rock(
    bm: BM,
    rng: RNG,
    radius: float = 0.5,
    roughness: float = 0.35,
    subdivisions: int = 2,
    flatten: float = 0.7,
    freq: float = 1.6,
) -> None:
    """Flatten a seeded, radially displaced icosphere."""
    verts = bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=1)["verts"]
    displace(verts, rng, roughness, freq)
    for v in verts:
        v.co *= radius
        v.co.z *= flatten


@register("tree")
def tree(
    bm: BM,
    rng: RNG,
    trunk_h: float = 1.2,
    trunk_r: float = 0.12,
    layers: int = 3,
    crown_r: float = 0.8,
    segments: int = 8,
) -> None:
    """Low-poly evergreen with layered foliage."""
    cone(bm, trunk_r, trunk_r * 0.7, trunk_h, segments=segments)
    z = trunk_h * 0.65
    for i in range(layers):
        r = crown_r * 0.76**i
        h = r * rng.uniform(1.35, 1.65)
        cone(bm, r, 0, h, z, segments)
        z += h * 0.55


@register("house")
def house(
    bm: BM,
    rng: RNG,
    width: float = 3.0,
    depth: float = 2.5,
    height: float = 2.2,
    roof_h: float = 1.2,
    overhang: float = 0.2,
) -> None:
    """Small gabled cottage with a front door."""
    box(bm, (width, depth, height), (0, 0, height / 2))
    box(bm, (width * 0.22, depth * 0.04, height * 0.7), (0, -depth / 2, height * 0.35))
    w, d = width / 2 + overhang, depth / 2 + overhang
    ends = [
        [
            bm.verts.new((x, y, z))
            for x, z in ((-w, height), (w, height), (0, height + roof_h))
        ]
        for y in (-d, d)
    ]
    a, b = ends
    bm.faces.new(a)
    bm.faces.new(b[::-1])
    for i in range(3):
        bm.faces.new((a[i], a[i - 1], b[i - 1], b[i]))


@register("vase")
def vase(
    bm: BM, rng: RNG, height: float = 0.5, radius: float = 0.15, segments: int = 24
) -> None:
    """Hollow vessel with a lip and an interior floor."""
    contour = [
        (0.55, 0),
        (0.65, 0.08),
        (1, 0.4),
        (0.9, 0.62),
        (0.44, 0.84),
        (0.44, 0.95),
        (0.52, 1),
    ]
    outer = [(radius * r, height * t) for r, t in contour]
    inner = [
        (radius * (r - 0.08), height * max(0.045, t)) for r, t in reversed(contour)
    ]
    lathe(bm, outer + inner, segments)


@register("pillar")
def pillar(
    bm: BM, rng: RNG, height: float = 3.0, radius: float = 0.3, segments: int = 16
) -> None:
    """Continuous profile from plinth through capital."""
    lathe(
        bm,
        [
            (radius * r, height * t)
            for r, t in (
                (1.4, 0),
                (1.4, 0.06),
                (1, 0.1),
                (0.88, 0.89),
                (1.35, 0.94),
                (1.4, 0.95),
                (1.4, 1),
            )
        ],
        segments,
    )


def unit(value: float, label: str) -> float:
    """Validate a normalized material property."""
    if type(value) not in (int, float) or not 0 <= value <= 1:
        raise ValueError(f"{label} must be a number in [0, 1]")
    return value


def material(name: str, settings: dict, rng: RNG) -> bpy.types.Material:
    """Assign identical linear base color to the shader and Workbench."""
    color = settings.get("color", [0.7] * 3)
    if len(color) != 3:
        raise ValueError("material.color needs three channels")
    jitter = unit(settings.get("color_jitter", 0), "color_jitter")
    rgba = [
        max(0, min(1, unit(c, "color") + rng.uniform(-jitter, jitter))) for c in color
    ] + [1]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    mat.diffuse_color = shader.inputs["Base Color"].default_value = rgba
    for key, default in [("metallic", 0.0), ("roughness", 0.6)]:
        shader.inputs[key.title()].default_value = unit(settings.get(key, default), key)
    return mat


def geometry_params(fn: Generator, params: dict) -> dict:
    """Check generator keywords and bound high-cost mesh resolutions before allocation."""
    sig = inspect.signature(fn)
    sig.bind(None, None, **params)
    for key, value in params.items():
        default = sig.parameters[key].default
        if type(default) is bool:
            if type(value) is not bool:
                raise ValueError(f"{key} must be boolean")
        elif type(default) is int:
            lo, hi = {
                "subdivisions": (1, 6),
                "segments": (3, 512),
                "layers": (1, 32),
            }.get(key, (1, 1024))
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError(f"{key} must be an integer in [{lo}, {hi}]")
        elif type(default) is float:
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{key} must be finite and nonnegative")
            if value == 0 and key not in ("bulge", "overhang", "roughness", "freq"):
                raise ValueError(f"{key} must be positive")
    return params


def finished(result: set[str]) -> None:
    """Blender operators can cancel without raising an exception."""
    if "FINISHED" not in result:
        raise RuntimeError(f"Blender operator returned {result}")


def build(item: dict, name: str, seed: int) -> bpy.types.Object:
    """Build a grounded mesh in an empty scene and smart-project all faces."""
    fn = REGISTRY[item["type"]]
    rng = RNG(seed)
    shade = item.get("shade", "flat")
    if shade not in ("smooth", "flat"):
        raise ValueError("shade must be flat or smooth")
    bm = bmesh.new()
    try:
        fn(bm, rng, **geometry_params(fn, item.get("params", {})))
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        base = min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.z -= base
        for f in bm.faces:
            f.smooth = shade == "smooth"
        mesh = bpy.data.meshes.new(name)
        bm.to_mesh(mesh)
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.materials.append(material(name + "_mat", item.get("material", {}), rng))
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    finished(bpy.ops.object.mode_set(mode="EDIT"))
    try:
        finished(bpy.ops.mesh.select_all(action="SELECT"))
        finished(
            bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
        )
    finally:
        finished(bpy.ops.object.mode_set(mode="OBJECT"))
    bpy.context.view_layer.update()
    return obj


def thumbnail(obj: bpy.types.Object, path: Path) -> None:
    """Frame all eight bounds corners in an orthographic transparent preview."""
    scene = bpy.context.scene
    for engine in ("BLENDER_WORKBENCH", "BLENDER_WORKBENCH_NEXT"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    else:
        raise RuntimeError("Workbench renderer unavailable")
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.light = "STUDIO"
    scene.render.film_transparent = True
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = scene.render.resolution_y = 512
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = str(path)
    corners = [obj.matrix_world @ Vector(p) for p in obj.bound_box]
    center = sum(corners, Vector((0, 0, 0))) / 8
    distance = max((p - center).length for p in corners) * 3
    data = bpy.data.cameras.new("Preview")
    cam = bpy.data.objects.new("Preview", data)
    scene.collection.objects.link(cam)
    try:
        cam.location = center + Vector((1, -1, 0.72)).normalized() * distance
        rotation = (center - cam.location).to_track_quat("-Z", "Y")
        cam.rotation_euler = rotation.to_euler()
        local = [rotation.inverted() @ (p - center) for p in corners]
        data.type = "ORTHO"
        data.ortho_scale = 2.2 * max(max(abs(p.x), abs(p.y)) for p in local)
        data.clip_start, data.clip_end = distance * 0.01, distance * 2
        scene.camera = cam
        finished(bpy.ops.render.render(write_still=True))
    finally:
        bpy.data.objects.remove(cam, do_unlink=True)
        bpy.data.cameras.remove(data)


def produce(
    item: dict, name: str, seed: int, out: Path, formats: list[str], thumbs: bool
) -> dict:
    """Isolate each asset and stage files before publishing successful exports."""
    finished(bpy.ops.wm.read_factory_settings(use_empty=True))
    obj = build(item, name, seed)
    obj.data.calc_loop_triangles()
    record = dict(
        name=name,
        type=item["type"],
        tris=len(obj.data.loop_triangles),
        dimensions=list(obj.dimensions),
        files=[],
    )
    with TemporaryDirectory(dir=out) as tmp:
        for fmt in formats:
            path = str(Path(tmp) / f"{name}.{fmt}")
            if fmt == "glb":
                finished(
                    bpy.ops.export_scene.gltf(
                        filepath=path, export_format="GLB", use_selection=True
                    )
                )
            elif fmt == "fbx":
                finished(bpy.ops.export_scene.fbx(filepath=path, use_selection=True))
            else:
                finished(bpy.ops.wm.save_as_mainfile(filepath=path, copy=True))
            record["files"].append(f"{name}.{fmt}")
        if thumbs:
            thumbnail(obj, Path(tmp) / f"{name}.png")
            record["files"].append(f"{name}.png")
        for filename in record["files"]:
            (Path(tmp) / filename).replace(out / filename)
    return record


def main() -> int:
    """Process a batch; keep successful assets even if another entry fails."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list generators and exit")
    parser.add_argument(
        "--spec", type=Path, help="JSON asset list (default: one of each type)"
    )
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument(
        "--formats", default="glb", help="comma-separated: glb,fbx,blend"
    )
    parser.add_argument(
        "--thumbs", action="store_true", help="render 512px transparent previews"
    )
    args = parser.parse_args(
        sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    )
    if args.list:
        print(", ".join(sorted(REGISTRY)))
        return 0
    formats = list(dict.fromkeys(s.strip().lower() for s in args.formats.split(",")))
    if set(formats) - {"glb", "fbx", "blend"}:
        parser.error("formats must be glb, fbx or blend")
    if not bpy.app.background:
        parser.error("use blender -b: this script replaces the current scene")
    try:
        assets = (
            json.loads(args.spec.read_text(encoding="utf8"))["assets"]
            if args.spec
            else [{"type": key} for key in REGISTRY]
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(f"invalid spec {args.spec}: {exc}")
    if not isinstance(assets, list):
        parser.error("spec.assets must be an array")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    seen, records, failures = set(), [], 0
    for index, item in enumerate(assets):
        try:
            kind = item["type"]
            if kind not in REGISTRY:
                raise ValueError(f"unknown generator: {kind}")
            base, count, seed = (
                item.get("name", kind),
                item.get("count", 1),
                item.get("seed", 0),
            )
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,55}", base):
                raise ValueError(
                    "name must be a short ASCII filename (letters, digits, _ or -)"
                )
            if (
                type(count) is not int
                or not 1 <= count <= 10000
                or type(seed) is not int
            ):
                raise ValueError("expected integer seed and count (1..10000)")
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            LOG.error("assets[%d]: %s", index, exc)
            failures += 1
            continue
        for i in range(count):
            name = base if count == 1 else f"{base}_{i + 1:02d}"
            try:
                if name.lower() in seen:
                    raise ValueError(f"duplicate output name: {name}")
                seen.add(name.lower())
                records.append(produce(item, name, seed + i, out, formats, args.thumbs))
                LOG.info("%s: %d triangles", name, records[-1]["tris"])
            except Exception:
                LOG.exception("assets[%d] %s failed", index, name)
                failures += 1
    with TemporaryDirectory(dir=out) as tmp:
        manifest = Path(tmp) / "manifest.json"
        manifest.write_text(json.dumps(records, indent=2) + "\n", encoding="utf8")
        manifest.replace(out / manifest.name)
    LOG.info(
        "%d succeeded, %d failed. Manifest: %s",
        len(records),
        failures,
        out / "manifest.json",
    )
    return int(bool(failures))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    if main():
        sys.exit(1)
