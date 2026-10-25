#!/usr/bin/env python3
"""Fail deployment if legacy models return or viewer links become stale."""
from html.parser import HTMLParser
from pathlib import Path
import json
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'

# The base kit the viewer itself links to. These must always be published.
REQUIRED = {'characters/body_base_midpoly.glb', 'characters/body_base_female_midpoly.glb', 'characters/skeleton_base_midpoly.glb'}
# Build products of tools/retarget_animations.py. They are generated, not
# committed, so they are present on a CI run that built them and absent on a
# plain checkout -- either way the site is valid. Anything *else* is still a
# hard failure, which is the point of this check: legacy models must not
# quietly come back.
OPTIONAL = {'characters/player_animated.glb'}
PLAYER = 'characters/player_animated.glb'


def optional(rel: str) -> bool:
    return rel in OPTIONAL or (rel.startswith('characters/clothing/') and rel.endswith('.glb'))


models = {p.relative_to(DOCS / 'models').as_posix()
          for p in (DOCS / 'models').rglob('*')
          if p.is_file() and p.suffix.lower() in {'.glb', '.gltf', '.obj'}}
missing = REQUIRED - models
unexpected = {m for m in models - REQUIRED if not optional(m)}
assert not missing, f'Missing published models: {sorted(missing)}'
assert not unexpected, f'Unexpected published models: {sorted(unexpected)}'

if PLAYER in models:
    # Published alongside its machine-readable proof; keep the two in step.
    animated = json.loads((DOCS / 'models/characters/player_animated.report.json').read_text())
    assert animated['rig']['bones'] == 27, animated['rig']['bones']
    assert animated['clips'], 'player_animated.glb published with no clips'
    worst_float = max(c['contact_float_m'] for c in animated['clips'])
    worst_dot = min(c['min_quaternion_dot'] for c in animated['clips'])
    assert worst_float <= 0.020, f'planted foot floats {worst_float * 1000:.1f} mm'
    assert worst_dot >= 0.0, f'quaternion flip (dot {worst_dot})'
    print(f"Animated player published: {len(animated['clips'])} clips, "
          f"foot float <= {worst_float * 1000:.1f} mm.")


class ViewerParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []
        self.assets = 0
        self.animations = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for key in ('href', 'src'):
            if a.get(key, '').startswith('./'):
                assert (DOCS / urlsplit(a[key]).path[2:]).is_file(), a[key]
        if tag == 'model-viewer':
            self.sources.append(urlsplit(a.get('src')).path)
        if tag == 'button' and a.get('class') == 'asset':
            self.assets += 1
        if 'data-animation' in a:
            self.animations.append(a['data-animation'])


parser = ViewerParser()
parser.feed((DOCS / 'index.html').read_text())
assert parser.sources == ['./models/characters/body_base_female_midpoly.glb']
assert parser.assets == 3
assert parser.animations == ['Idle', 'Walk']
report = json.loads((DOCS / 'models/characters/body_base_midpoly.validation.json').read_text())
assert 15000 <= report['triangles'] <= 25000
print('Site valid: required mid-poly GLBs present, three asset selectors, Idle/Walk controls, no stale local links.')

female = json.loads((DOCS / 'models/characters/body_base_female_midpoly.validation.json').read_text())
assert female['anatomy_revision'] == 'athletic-sculpt-v2'
assert f"{female['total_triangles']:,}" in (DOCS / 'viewer.js').read_text()
assert 'v=athletic-sculpt-v2' in (DOCS / 'index.html').read_text()
