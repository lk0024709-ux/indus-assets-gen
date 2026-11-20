# Procedural Asset Factory

Generate standalone game props in a background Blender process. The factory is one Python file and uses Blender's bundled Python modules; no pip installs are required. Target: Blender 3.3+ and 4.x, with the bundled glTF and FBX exporters enabled for those formats.

```sh
# See the registered generators, without creating files
blender -b -P asset_factory.py -- --list

# No spec: generate one GLB of each built-in prop
blender -b -P asset_factory.py -- --out ./out

# Example spec: a large crate, five rock variations and a cottage
blender -b --python-exit-code 1 -P asset_factory.py -- --spec assets.json --out ./out --formats glb,fbx,blend --thumbs
```

`--` separates Blender flags from factory flags. Use a dedicated background process: the in-memory scene is reset for every asset. Workbench thumbnails are optional, 512×512 RGBA PNGs. On Linux without a physical GPU, Workbench still requires a functioning graphics context: install Mesa with EGL/llvmpipe and, if needed, set `LIBGL_ALWAYS_SOFTWARE=1`. Some Blender/platform combinations require a virtual display. Omit `--thumbs` on export-only runners.

## Asset spec

See [assets.json](assets.json) for a runnable batch. The root object contains an `assets` array. Only `type` is required: `crate`, `barrel`, `table`, `chair`, `rock`, `tree`, `house`, `vase` or `pillar`.

| Field | Behavior |
|---|---|
| `name` | Defaults to `type`. Use 1–56 ASCII letters, digits, underscores or hyphens, starting with a letter or digit. Names must be unique within a batch. |
| `params` | Generator keyword arguments; see the decorated function signatures for names and defaults. Dimensions use Blender units. |
| `count`, `seed` | Default to `1`, `0`. Repeats get `_01`, `_02`, … and seeds `seed`, `seed+1`, … . A seed varies stochastic geometry (rocks, trees) or color jitter; it does not change fixed furniture dimensions. |
| `material` | Principled `color` (linear RGB triple), `metallic`, `roughness`, `color_jitter` (independent ± offset per channel, clamped). All components are in [0,1]. |
| `shade` | `flat` (default) or `smooth`. Both modes receive smart-projected UVs. |

The same spec and Blender version reproduce geometry and material values, not necessarily byte-identical exported files. Each asset is a single grounded mesh object; compound props can contain disconnected pieces. Exports are staged before publication, and `.blend` files are saved before the preview camera is created. `manifest.json` lists **successful** assets: `name`, `type`, `tris`, XYZ `dimensions`, and relative `files`. A failed entry is logged; the batch continues and signals failure at the end. Existing matching outputs are replaced; unrelated or old files are not deleted. Use a fresh output directory when an exact batch snapshot is needed.

## Extending

Place a generator above `main()` in `asset_factory.py`. Geometry helpers append to the supplied BMesh. Use the passed `rng`, not global random state.

```python
@register('lamp')
def lamp(bm: BM, rng: RNG, height: float = 1.6) -> None:
    """A floor lamp with a tapered shade."""
    cone(bm, .22, .20, .05)
    cone(bm, .025, .025, height, z=.05)
    cone(bm, .30, .16, .28, z=height+.05)
```

Then use `{"type":"lamp","params":{"height":1.8}}` as a spec entry. For **LODs**, copy the finished mesh, evaluate a Decimate modifier at each target ratio, and record each level's own triangle count and filename. For **multi-material** props, assign `BMFace.material_index` while building and append matching material slots in `build`. For **textures**, connect Image Texture nodes to Principled using the generated UVs; bake procedural nodes to images for interchange and pack or copy the images for the chosen export format.

## Smoke checks

```sh
blender -b --python-exit-code 1 -P tests/smoke.py
```

Checks seeded geometry, grounding, shading, UVs, invalid-entry isolation, count expansion, all three output formats, and single-object `.blend` contents in a temporary directory.
