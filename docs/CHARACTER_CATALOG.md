# Current published catalog

The available assets are **Base Body** and **Skeleton**:

- `models/characters/body_base_midpoly.glb`
- `models/characters/skeleton/skeleton_base_midpoly.glb` — 24,816 triangles, 151 rigid rig bones, 375 anatomical pieces; static rest pose. See its [anatomy/rig documentation](models/characters/skeleton/README.md).
- 15,408 triangles, 1.8 m, 20 bones, Idle and Walk animation clips.

The four proposed clothing GLBs are not present and are not advertised or replaced by low-poly placeholders. No clothing overlay or Z-fighting validation is claimed for unavailable garments.

The previous OBJ roster, low-poly characters, clothing prototypes, buildings, terrain, trees, and vehicle models have been removed from `docs/models/`. Their historical generators remain in `tools/` but are no longer run during Pages deployment. Older repository documentation/examples referring to those hosted models are historical and their old download URLs no longer form part of the catalog.

## Publishing

`.github/workflows/deploy.yml` validates the model allowlist and GLB tests, runs a real Chromium browser test, then stages **only** `index.html`, `viewer.js`, the vendored viewer runtime/license, and the two approved GLBs. Editable `.blend` source and validation documentation remain in Git but are not uploaded in the Pages artifact.

Pages deploys from **main**, not a feature-branch push. Branch changes become live only after they are merged and the Pages workflow completes successfully.

Target site: https://lk0024709-ux.github.io/indus-assets-gen/

## Validation

```sh
python tools/validate_character_site.py
python -m unittest discover -s tools -p 'test_*midpoly.py' -v
npm ci --prefix tools/viewer-tests
cd tools/viewer-tests
npx playwright install --with-deps chromium
npm test
```

The browser test serves the actual `docs/` page and verifies the model loads, both animation clips advance and keep playing beyond a full cycle, pause/resume works, mobile layout has no horizontal overflow, and no page errors or failed HTTP responses occur. These checks passed locally with headless Chromium; there are no clothing tests because no approved clothing is available.

`docs/vendor/model-viewer.min.js` is the unmodified distribution from `@google/model-viewer@4.0.0` (BSD-3-Clause); its license is included alongside it. Local hosting avoids CDN availability or import-map dependencies. To refresh it, install that exact npm package and copy its `dist/model-viewer.min.js` and `LICENSE` into `docs/vendor/`.
