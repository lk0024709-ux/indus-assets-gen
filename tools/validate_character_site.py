#!/usr/bin/env python3
"""Fail deployment if legacy models return or viewer links become stale."""
from html.parser import HTMLParser
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
EXPECTED = {'characters/body_base_midpoly.glb', 'characters/body_base_female_midpoly.glb', 'characters/skeleton_base_midpoly.glb'}
models = {p.relative_to(DOCS / 'models').as_posix()
          for p in (DOCS / 'models').rglob('*')
          if p.is_file() and p.suffix.lower() in {'.glb', '.gltf', '.obj'}}
assert models == EXPECTED, f'Unexpected/missing published models: {models ^ EXPECTED}'


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
                assert (DOCS / a[key][2:]).is_file(), a[key]
        if tag == 'model-viewer':
            self.sources.append(a.get('src'))
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
print('Site valid: exactly three mid-poly GLBs, three asset selectors, Idle/Walk controls, no stale local links.')
