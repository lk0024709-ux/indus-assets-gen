#!/usr/bin/env python3
"""Fail deployment if legacy models return or viewer links become stale."""
from html.parser import HTMLParser
from pathlib import Path
import json
from urllib.parse import urlsplit

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
                assert (DOCS / urlsplit(a[key]).path[2:]).is_file(), a[key]
        if tag == 'model-viewer':
            self.sources.append(urlsplit(a.get('src')).path)
        if tag == 'button' and a.get('class') == 'asset':
            self.assets += 1
        if 'data-animation' in a:
            self.animations.append(a['data-animation'])


index_html = (DOCS / 'index.html').read_text()
parser = ViewerParser()
parser.feed(index_html)
assert './block17.html' in index_html, 'character landing page must link to building viewer'
house_html = (DOCS / 'block17.html').read_text()
block_files = ('Block15_OpenHouse.glb', 'Block16_OpenShop.glb',
               'Block17_OpenFamilyHouse.glb', 'Block18_OpenCornerHouse.glb')
assert all(filename in house_html for filename in block_files)
assert 'src="./models/buildings/Block17_OpenFamilyHouse.glb"' in house_html
assert 'href="./models/buildings/Block17_OpenFamilyHouse.glb"' in house_html
assert house_html.count('data-block=') == 4
assert 'id="reset-view"' in house_html and 'id="rotate"' in house_html
assert parser.sources == ['./models/characters/body_base_female_midpoly.glb']
assert parser.assets == 3
assert parser.animations == ['Idle', 'Walk']
report = json.loads((DOCS / 'models/characters/body_base_midpoly.validation.json').read_text())
assert 15000 <= report['triangles'] <= 25000
print('Site valid: character assets and controls pass; Blocks 15–18 viewer is linked with four model entries.')

female = json.loads((DOCS / 'models/characters/body_base_female_midpoly.validation.json').read_text())
assert female['anatomy_revision'] == 'athletic-sculpt-v2'
assert f"{female['total_triangles']:,}" in (DOCS / 'viewer.js').read_text()
assert 'v=athletic-sculpt-v2' in (DOCS / 'index.html').read_text()
