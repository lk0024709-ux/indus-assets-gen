// Browser-native procedural 3D recipe schemas and binary glTF 2.0 (.glb) generator.
// Enables all 6 recipes in the Procedural Asset Generator to run 100% client-side on
// static hosts (GitHub Pages) when no Python + Blender backend is reachable.

const GLB_MAGIC = 0x46546C67;
const JSON_CHUNK = 0x4E4F534A;
const BIN_CHUNK = 0x004E4942;

export const WEB_RECIPES = [
  {
    id: 'battle_royale_outfit',
    name: 'Battle Royale Outfit',
    description: 'Low-poly modular Battle Royale tactical tee, cargo pants, belt, pouches, thigh holster, and combat boots.',
    parameters: {
      height: { label: 'Character height (m)', type: 'float', min: 1.50, max: 2.10, step: 0.05, default: 1.75 },
      tee_color: { label: 'Tee color', type: 'color', default: '#6E7847' },
      pants_color: { label: 'Cargo pants color', type: 'color', default: '#7E6E4B' },
      gear_color: { label: 'Tactical gear color', type: 'color', default: '#27272B' },
      include_holster: { label: 'Thigh holster', type: 'bool', default: true },
      include_pouches: { label: 'Belt pouches + ammo', type: 'bool', default: true },
      include_boots: { label: 'Combat boots', type: 'bool', default: true },
    },
  },
  {
    id: 'chair',
    name: 'Chair',
    description: 'A low-poly chair with adjustable proportions and a solid seat.',
    parameters: {
      seat_width: { label: 'Seat width', type: 'float', min: 0.7, max: 1.8, step: 0.05, default: 1.0 },
      seat_depth: { label: 'Seat depth', type: 'float', min: 0.65, max: 1.6, step: 0.05, default: 0.9 },
      seat_height: { label: 'Seat height', type: 'float', min: 0.35, max: 1.0, step: 0.05, default: 0.55 },
      back_height: { label: 'Back height', type: 'float', min: 0.5, max: 1.8, step: 0.05, default: 1.1 },
      leg_count: { label: 'Leg count', type: 'enum', options: ['3', '4'], default: '4' },
      color: { label: 'Material color', type: 'color', default: '#B87843' },
    },
  },
  {
    id: 'table',
    name: 'Table',
    description: 'A configurable dining or work table with round or rectangular top.',
    parameters: {
      width: { label: 'Width', type: 'float', min: 0.8, max: 3.0, step: 0.1, default: 1.8 },
      depth: { label: 'Depth / diameter', type: 'float', min: 0.7, max: 2.5, step: 0.1, default: 1.2 },
      height: { label: 'Height', type: 'float', min: 0.5, max: 1.5, step: 0.05, default: 0.85 },
      top_shape: { label: 'Top shape', type: 'enum', options: ['rectangular', 'round'], default: 'rectangular' },
      leg_style: { label: 'Leg style', type: 'enum', options: ['straight', 'tapered'], default: 'straight' },
      color: { label: 'Material color', type: 'color', default: '#8A5A3B' },
    },
  },
  {
    id: 'lamp',
    name: 'Lamp',
    description: 'A stylized table lamp with a configurable shade silhouette.',
    parameters: {
      base_radius: { label: 'Base radius', type: 'float', min: 0.12, max: 0.55, step: 0.02, default: 0.3 },
      pole_height: { label: 'Pole height', type: 'float', min: 0.3, max: 1.5, step: 0.05, default: 0.8 },
      shade_size: { label: 'Shade size', type: 'float', min: 0.25, max: 0.9, step: 0.05, default: 0.55 },
      shade_type: { label: 'Shade type', type: 'enum', options: ['cone', 'cylinder', 'sphere'], default: 'cone' },
      segments: { label: 'Radial detail', type: 'int', min: 8, max: 32, step: 4, default: 16 },
      color: { label: 'Material color', type: 'color', default: '#E6B85C' },
    },
  },
  {
    id: 'rock',
    name: 'Rock',
    description: 'A seeded, irregular low-poly boulder with controllable surface variation.',
    parameters: {
      seed: { label: 'Random seed', type: 'int', min: 0, max: 999999, step: 1, default: 42 },
      size: { label: 'Overall size', type: 'float', min: 0.5, max: 2.5, step: 0.1, default: 1.3 },
      noise: { label: 'Shape irregularity', type: 'float', min: 0.0, max: 0.65, step: 0.05, default: 0.28 },
      subdivision: { label: 'Detail level', type: 'int', min: 1, max: 3, step: 1, default: 2 },
      smoothness: { label: 'Smoothing', type: 'float', min: 0.0, max: 1.0, step: 0.1, default: 0.2 },
      color: { label: 'Material color', type: 'color', default: '#777B78' },
    },
  },
  {
    id: 'barrel',
    name: 'Barrel',
    description: 'A faceted wooden barrel with adjustable bulge, stave count and hoops.',
    parameters: {
      radius: { label: 'Radius', type: 'float', min: 0.25, max: 0.9, step: 0.05, default: 0.48 },
      height: { label: 'Height', type: 'float', min: 0.5, max: 2.0, step: 0.1, default: 1.15 },
      bulge: { label: 'Bulge', type: 'float', min: 0.0, max: 0.35, step: 0.05, default: 0.15 },
      staves: { label: 'Stave count', type: 'int', min: 8, max: 24, step: 2, default: 12 },
      hoops: { label: 'Metal hoops', type: 'int', min: 0, max: 4, step: 1, default: 2 },
      color: { label: 'Material color', type: 'color', default: '#96613D' },
    },
  },
];

export function srgbHexToLinear(hex) {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const toLin = c => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  return [toLin(r), toLin(g), toLin(b)];
}

export function validateWebParams(recipeId, incoming = {}) {
  const recipe = WEB_RECIPES.find(r => r.id === recipeId);
  if (!recipe) throw new Error(`Unknown recipe: ${recipeId}`);
  const out = {};
  for (const [key, spec] of Object.entries(recipe.parameters)) {
    let val = incoming[key] !== undefined ? incoming[key] : spec.default;
    if (spec.type === 'int') val = Math.round(Number(val));
    else if (spec.type === 'float') val = Number(val);
    else if (spec.type === 'bool') val = Boolean(val);
    else if (spec.type === 'enum') {
      val = String(val);
      if (!spec.options.includes(val)) val = String(spec.default);
    } else if (spec.type === 'color') {
      val = typeof val === 'string' && /^#[0-9a-fA-F]{6}$/.test(val) ? val : spec.default;
    }
    if (spec.min !== undefined) val = Math.max(spec.min, val);
    if (spec.max !== undefined) val = Math.min(spec.max, val);
    out[key] = val;
  }
  return out;
}

function blenderToGltf([x, y, z]) {
  return [x, z, -y];
}

function rotateEulerXYZ([vx, vy, vz], [rx, ry, rz]) {
  let x = vx, y = vy, z = vz;
  if (rx) {
    const c = Math.cos(rx), s = Math.sin(rx);
    [y, z] = [y * c - z * s, y * s + z * c];
  }
  if (ry) {
    const c = Math.cos(ry), s = Math.sin(ry);
    [x, z] = [x * c + z * s, -x * s + z * c];
  }
  if (rz) {
    const c = Math.cos(rz), s = Math.sin(rz);
    [x, y] = [x * c - y * s, x * s + y * c];
  }
  return [x, y, z];
}

function transformVerts(localVerts, scale = [1, 1, 1], rot = [0, 0, 0], loc = [0, 0, 0]) {
  return localVerts.map(([vx, vy, vz]) => {
    const s = [vx * scale[0], vy * scale[1], vz * scale[2]];
    const r = rotateEulerXYZ(s, rot);
    return blenderToGltf([r[0] + loc[0], r[1] + loc[1], r[2] + loc[2]]);
  });
}

function primBox(loc, dim, rot = [0, 0, 0]) {
  const local = [
    [-0.5, -0.5, -0.5], [0.5, -0.5, -0.5], [0.5, 0.5, -0.5], [-0.5, 0.5, -0.5],
    [-0.5, -0.5,  0.5], [0.5, -0.5,  0.5], [0.5, 0.5,  0.5], [-0.5, 0.5,  0.5],
  ];
  const quads = [
    [0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
    [2, 3, 7, 6], [1, 2, 6, 5], [3, 0, 4, 7],
  ];
  const tris = [];
  for (const [a, b, c, d] of quads) tris.push([a, b, c], [a, c, d]);
  return { verts: transformVerts(local, dim, rot, loc), tris };
}

function primCylinder(loc, rBot, rTop, depth, segs = 12, scale = [1, 1, 1], rot = [0, 0, 0]) {
  const hz = depth * 0.5;
  const local = [];
  for (let k = 0; k < segs; k++) {
    const a = (2 * Math.PI * k) / segs;
    local.push([rBot * Math.cos(a), rBot * Math.sin(a), -hz]);
  }
  for (let k = 0; k < segs; k++) {
    const a = (2 * Math.PI * k) / segs;
    local.push([rTop * Math.cos(a), rTop * Math.sin(a), hz]);
  }
  const tris = [];
  for (let k = 0; k < segs; k++) {
    const k1 = (k + 1) % segs;
    tris.push([k, k1, segs + k1], [k, segs + k1, segs + k]);
  }
  for (let k = 1; k < segs - 1; k++) {
    tris.push([segs, segs + k, segs + k + 1], [0, k + 1, k]);
  }
  return { verts: transformVerts(local, scale, rot, loc), tris };
}

function primTorus(loc, majorR, minorR, majorSegs = 12, minorSegs = 6, scale = [1, 1, 1], rot = [0, 0, 0]) {
  const local = [];
  for (let i = 0; i < majorSegs; i++) {
    const phi = (2 * Math.PI * i) / majorSegs;
    const cp = Math.cos(phi), sp = Math.sin(phi);
    for (let j = 0; j < minorSegs; j++) {
      const psi = (2 * Math.PI * j) / minorSegs;
      const rr = majorR + minorR * Math.cos(psi);
      local.push([rr * cp, rr * sp, minorR * Math.sin(psi)]);
    }
  }
  const tris = [];
  for (let i = 0; i < majorSegs; i++) {
    const i1 = (i + 1) % majorSegs;
    for (let j = 0; j < minorSegs; j++) {
      const j1 = (j + 1) % minorSegs;
      const p00 = i * minorSegs + j, p10 = i1 * minorSegs + j;
      const p11 = i1 * minorSegs + j1, p01 = i * minorSegs + j1;
      tris.push([p00, p10, p11], [p00, p11, p01]);
    }
  }
  return { verts: transformVerts(local, scale, rot, loc), tris };
}

function primUvSphere(loc, scale, segs = 16, rings = 10) {
  const local = [[0, 0, -1]];
  for (let r = 1; r < rings; r++) {
    const phi = -Math.PI / 2 + (Math.PI * r) / rings;
    const cp = Math.cos(phi), sp = Math.sin(phi);
    for (let s = 0; s < segs; s++) {
      const th = (2 * Math.PI * s) / segs;
      local.push([cp * Math.cos(th), cp * Math.sin(th), sp]);
    }
  }
  const topIdx = local.length;
  local.push([0, 0, 1]);
  const tris = [];
  for (let s = 0; s < segs; s++) {
    const s1 = (s + 1) % segs;
    tris.push([0, 1 + s1, 1 + s]);
  }
  for (let r = 0; r < rings - 2; r++) {
    const row0 = 1 + r * segs;
    const row1 = 1 + (r + 1) * segs;
    for (let s = 0; s < segs; s++) {
      const s1 = (s + 1) % segs;
      tris.push([row0 + s, row0 + s1, row1 + s1], [row0 + s, row1 + s1, row1 + s]);
    }
  }
  const lastRow = 1 + (rings - 2) * segs;
  for (let s = 0; s < segs; s++) {
    const s1 = (s + 1) % segs;
    tris.push([lastRow + s, lastRow + s1, topIdx]);
  }
  return { verts: transformVerts(local, scale, [0, 0, 0], loc), tris };
}

function primRock(seed, size, noise, subdiv, smoothness) {
  // Deterministic mulberry32 PRNG
  let state = (seed >>> 0) || 1;
  const rand = () => {
    state = (state + 0x6D2B79F5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const gold = (1 + Math.sqrt(5)) / 2;
  const norm = v => {
    const l = Math.hypot(v[0], v[1], v[2]) || 1;
    return [v[0] / l, v[1] / l, v[2] / l];
  };
  let verts = [
    [-1, gold, 0], [1, gold, 0], [-1, -gold, 0], [1, -gold, 0],
    [0, -1, gold], [0, 1, gold], [0, -1, -gold], [0, 1, -gold],
    [gold, 0, -1], [gold, 0, 1], [-gold, 0, -1], [-gold, 0, 1],
  ].map(norm);
  let tris = [
    [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
    [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
    [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
    [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1],
  ];
  for (let s = 0; s < subdiv; s++) {
    const midCache = new Map();
    const mid = (i, j) => {
      const k = i < j ? `${i}:${j}` : `${j}:${i}`;
      if (midCache.has(k)) return midCache.get(k);
      const idx = verts.length;
      verts.push(norm([(verts[i][0] + verts[j][0]) / 2, (verts[i][1] + verts[j][1]) / 2, (verts[i][2] + verts[j][2]) / 2]));
      midCache.set(k, idx);
      return idx;
    };
    const nextTris = [];
    for (const [a, b, c] of tris) {
      const ab = mid(a, b), bc = mid(b, c), ca = mid(c, a);
      nextTris.push([a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]);
    }
    tris = nextTris;
  }
  verts = verts.map(([x, y, z]) => {
    const f = size * (1 + (rand() * 2 - 1) * noise);
    return [x * f, y * f, z * f * 0.72];
  });
  if (smoothness > 0.05) {
    const adj = Array.from({ length: verts.length }, () => new Set());
    for (const [a, b, c] of tris) {
      adj[a].add(b); adj[a].add(c);
      adj[b].add(a); adj[b].add(c);
      adj[c].add(a); adj[c].add(b);
    }
    const alpha = smoothness * 0.42;
    for (let iter = 0; iter < 2; iter++) {
      verts = verts.map((v, i) => {
        const nbrs = [...adj[i]];
        if (!nbrs.length) return v;
        const avg = [0, 0, 0];
        for (const n of nbrs) { avg[0] += verts[n][0]; avg[1] += verts[n][1]; avg[2] += verts[n][2]; }
        avg[0] /= nbrs.length; avg[1] /= nbrs.length; avg[2] /= nbrs.length;
        return [
          v[0] * (1 - alpha) + avg[0] * alpha,
          v[1] * (1 - alpha) + avg[1] * alpha,
          v[2] * (1 - alpha) + avg[2] * alpha,
        ];
      });
    }
  }
  return { verts: transformVerts(verts, [1, 1, 1], [0, 0, 0], [0, 0, size * 0.72]), tris };
}

function primBarrelBody(radius, height, bulge, staves) {
  const rings = 7;
  const local = [];
  for (let j = 0; j < rings; j++) {
    const z = (height * j) / (rings - 1);
    const prof = radius * (1 + bulge * Math.sin((Math.PI * j) / (rings - 1)));
    for (let i = 0; i < staves; i++) {
      const a = (2 * Math.PI * i) / staves;
      local.push([prof * Math.cos(a), prof * Math.sin(a), z]);
    }
  }
  const tris = [];
  for (let j = 0; j < rings - 1; j++) {
    for (let i = 0; i < staves; i++) {
      const i1 = (i + 1) % staves;
      const a = j * staves + i, b = j * staves + i1;
      const c = (j + 1) * staves + i1, d = (j + 1) * staves + i;
      tris.push([a, b, c], [a, c, d]);
    }
  }
  const topBase = (rings - 1) * staves;
  for (let i = 1; i < staves - 1; i++) {
    tris.push([0, i + 1, i], [topBase, topBase + i, topBase + i + 1]);
  }
  return { verts: transformVerts(local), tris };
}

function computeFaceNormal(p0, p1, p2) {
  const ux = p1[0] - p0[0], uy = p1[1] - p0[1], uz = p1[2] - p0[2];
  const vx = p2[0] - p0[0], vy = p2[1] - p0[1], vz = p2[2] - p0[2];
  const cx = uy * vz - uz * vy;
  const cy = uz * vx - ux * vz;
  const cz = ux * vy - uy * vx;
  const len = Math.hypot(cx, cy, cz) || 1;
  return [cx / len, cy / len, cz / len];
}

function packSceneToGlb(rootName, parts, materialsSpec) {
  const materials = [];
  const matIdxByKey = new Map();
  for (const [key, spec] of Object.entries(materialsSpec)) {
    matIdxByKey.set(key, materials.length);
    materials.push({
      name: spec.name || key,
      doubleSided: true,
      pbrMetallicRoughness: {
        baseColorFactor: [...spec.rgb, 1.0],
        metallicFactor: spec.metallic ?? 0.0,
        roughnessFactor: spec.roughness ?? 0.72,
      },
    });
  }

  const chunks = [];
  let byteOffset = 0;
  const bufferViews = [];
  const accessors = [];
  const meshes = [];
  const nodes = [{ name: rootName, children: [] }];

  const pushBytes = (typedArray, target) => {
    const raw = new Uint8Array(typedArray.buffer, typedArray.byteOffset, typedArray.byteLength);
    const pad = (4 - (byteOffset % 4)) % 4;
    if (pad) {
      chunks.push(new Uint8Array(pad));
      byteOffset += pad;
    }
    const bvIdx = bufferViews.length;
    const bv = { buffer: 0, byteOffset, byteLength: raw.byteLength };
    if (target) bv.target = target;
    bufferViews.push(bv);
    chunks.push(raw);
    byteOffset += raw.byteLength;
    return bvIdx;
  };

  for (const part of parts) {
    const triCount = part.tris.length;
    const vCount = triCount * 3;
    const posArr = new Float32Array(vCount * 3);
    const nrmArr = new Float32Array(vCount * 3);
    const idxArr = vCount >= 65535 ? new Uint32Array(vCount) : new Uint16Array(vCount);
    let minX = Infinity, minY = Infinity, minZ = Infinity;
    let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;

    for (let t = 0; t < triCount; t++) {
      const [ia, ib, ic] = part.tris[t];
      const p0 = part.verts[ia], p1 = part.verts[ib], p2 = part.verts[ic];
      const fn = computeFaceNormal(p0, p1, p2);
      const pts = [p0, p1, p2];
      for (let k = 0; k < 3; k++) {
        const vi = t * 3 + k;
        const p = pts[k];
        posArr[vi * 3] = p[0]; posArr[vi * 3 + 1] = p[1]; posArr[vi * 3 + 2] = p[2];
        nrmArr[vi * 3] = fn[0]; nrmArr[vi * 3 + 1] = fn[1]; nrmArr[vi * 3 + 2] = fn[2];
        idxArr[vi] = vi;
        if (p[0] < minX) minX = p[0]; if (p[1] < minY) minY = p[1]; if (p[2] < minZ) minZ = p[2];
        if (p[0] > maxX) maxX = p[0]; if (p[1] > maxY) maxY = p[1]; if (p[2] > maxZ) maxZ = p[2];
      }
    }

    const posBv = pushBytes(posArr, 34962);
    const posAcc = accessors.length;
    accessors.push({
      bufferView: posBv, componentType: 5126, count: vCount, type: 'VEC3',
      min: [minX, minY, minZ], max: [maxX, maxY, maxZ],
    });

    const nrmBv = pushBytes(nrmArr, 34962);
    const nrmAcc = accessors.length;
    accessors.push({ bufferView: nrmBv, componentType: 5126, count: vCount, type: 'VEC3' });

    const idxBv = pushBytes(idxArr, 34963);
    const idxAcc = accessors.length;
    accessors.push({
      bufferView: idxBv,
      componentType: vCount >= 65535 ? 5125 : 5123,
      count: vCount,
      type: 'SCALAR',
    });

    const meshIdx = meshes.length;
    meshes.push({
      name: part.name,
      primitives: [{
        attributes: { POSITION: posAcc, NORMAL: nrmAcc },
        indices: idxAcc,
        material: matIdxByKey.get(part.matKey) ?? 0,
        mode: 4,
      }],
    });
    const nodeIdx = nodes.length;
    nodes.push({ name: part.name, mesh: meshIdx });
    nodes[0].children.push(nodeIdx);
  }

  const binPad = (4 - (byteOffset % 4)) % 4;
  const binChunkLen = byteOffset + binPad;
  const binBytes = new Uint8Array(binChunkLen);
  let cursor = 0;
  for (const ch of chunks) {
    binBytes.set(ch, cursor);
    cursor += ch.byteLength;
  }

  const gltf = {
    asset: { version: '2.0', generator: 'Indus Browser Procedural GLB Builder' },
    scene: 0,
    scenes: [{ name: 'Scene', nodes: [0] }],
    nodes,
    meshes,
    materials,
    accessors,
    bufferViews,
    buffers: [{ byteLength: byteOffset }],
  };

  const jsonRaw = new TextEncoder().encode(JSON.stringify(gltf));
  const jsonPad = (4 - (jsonRaw.byteLength % 4)) % 4;
  const jsonChunkLen = jsonRaw.byteLength + jsonPad;
  const totalBytes = 12 + 8 + jsonChunkLen + 8 + binChunkLen;
  const glb = new Uint8Array(totalBytes);
  const dv = new DataView(glb.buffer);
  dv.setUint32(0, GLB_MAGIC, true);
  dv.setUint32(4, 2, true);
  dv.setUint32(8, totalBytes, true);
  dv.setUint32(12, jsonChunkLen, true);
  dv.setUint32(16, JSON_CHUNK, true);
  glb.set(jsonRaw, 20);
  if (jsonPad) glb.fill(0x20, 20 + jsonRaw.byteLength, 20 + jsonChunkLen);
  const binHeader = 20 + jsonChunkLen;
  dv.setUint32(binHeader, binChunkLen, true);
  dv.setUint32(binHeader + 4, BIN_CHUNK, true);
  glb.set(binBytes, binHeader + 8);
  return glb;
}

function buildBattleRoyaleParts(p) {
  const k = p.height / 1.75;
  const materials = {
    tee: { name: 'Outfit_BR_M_tee', rgb: srgbHexToLinear(p.tee_color), roughness: 0.9 },
    pants: { name: 'Outfit_BR_M_pants', rgb: srgbHexToLinear(p.pants_color), roughness: 0.9 },
    kneepad: { name: 'Outfit_BR_M_kneepad', rgb: [0.09, 0.11, 0.05], roughness: 0.9 },
    black: { name: 'Outfit_BR_M_black', rgb: srgbHexToLinear(p.gear_color), roughness: 0.9 },
    boot: { name: 'Outfit_BR_M_boot', rgb: [0.015, 0.015, 0.02], roughness: 0.9 },
    steel: { name: 'Outfit_BR_M_steel', rgb: [0.65, 0.65, 0.68], metallic: 1.0, roughness: 0.3 },
    gold: { name: 'Outfit_BR_M_gold', rgb: [0.8, 0.55, 0.08], metallic: 1.0, roughness: 0.3 },
    brass: { name: 'Outfit_BR_M_brass', rgb: [0.7, 0.45, 0.1], metallic: 1.0, roughness: 0.3 },
  };
  const parts = [];
  const addCyl = (name, matKey, loc, r, h, sc = [1, 1, 1], rot = [0, 0, 0], v = 8, r2 = null) => {
    const g = primCylinder([loc[0] * k, loc[1] * k, loc[2] * k], r * k, (r2 ?? r) * k, h * k, v, sc, rot);
    parts.push({ name, matKey, ...g });
  };
  const addBox = (name, matKey, loc, dim, rot = [0, 0, 0]) => {
    const g = primBox([loc[0] * k, loc[1] * k, loc[2] * k], [dim[0] * k, dim[1] * k, dim[2] * k], rot);
    parts.push({ name, matKey, ...g });
  };

  addCyl('Tee_Body', 'tee', [0, 0, 1.275], 0.18, 0.51, [1.1, 0.7, 1]);
  addCyl('Tee_Collar', 'tee', [0, 0, 1.53], 0.085, 0.035, [1, 0.9, 1]);
  for (const [s, side] of [[1, 'R'], [-1, 'L']]) {
    addCyl(`Tee_Sleeve_${side}`, 'tee', [s * 0.285, 0, 1.429], 0.075, 0.2, [1, 1, 1], [0, (s * 110 * Math.PI) / 180, 0]);
  }
  addBox('Tee_ChestPatch', 'black', [0.075, -0.118, 1.38], [0.07, 0.012, 0.08]);
  addBox('Tee_ChestStar', 'gold', [0.075, -0.125, 1.38], [0.03, 0.006, 0.03], [0, Math.PI / 4, 0]);

  addCyl('Pants_Hips', 'pants', [0, 0, 0.97], 0.21, 0.2, [1, 0.65, 1]);
  for (const [s, side] of [[1, 'R'], [-1, 'L']]) {
    addCyl(`Pants_Leg_${side}`, 'pants', [s * 0.1, 0, 0.65], 0.10, 0.74, [1, 1, 1], [0, 0, 0], 8, 0.105);
    addBox(`KneePad_${side}`, 'kneepad', [s * 0.1, -0.1, 0.52], [0.13, 0.05, 0.15]);
  }
  addBox('Cargo_Pocket', 'pants', [0.215, -0.01, 0.74], [0.045, 0.12, 0.16]);
  addBox('Cargo_Flap', 'pants', [0.22, -0.01, 0.82], [0.05, 0.125, 0.04]);

  if (p.include_holster) {
    addBox('Holster', 'black', [-0.215, 0, 0.78], [0.05, 0.08, 0.2]);
    [0.88, 0.72].forEach((z, i) => addCyl(`Holster_Strap_${i}`, 'black', [-0.1, 0, z], 0.108, 0.03));
  }

  addCyl('Belt', 'black', [0, 0, 1.04], 0.225, 0.07, [1, 0.7, 1], [0, 0, 0], 12);
  addBox('Belt_Buckle', 'black', [0, -0.16, 1.04], [0.06, 0.02, 0.05]);
  if (p.include_pouches) {
    addBox('Pouch_R', 'black', [0.25, -0.01, 1.0], [0.05, 0.1, 0.11]);
    addBox('Pouch_L', 'black', [-0.25, -0.01, 1.0], [0.05, 0.09, 0.1]);
    for (let i = 0; i < 3; i++) {
      addCyl(`Bullet_${i}`, 'brass', [0.25, -0.04 + i * 0.03, 1.07], 0.008, 0.04, [1, 1, 1], [0, 0, 0], 6);
    }
  }
  parts.push({
    name: 'Carabiner',
    matKey: 'steel',
    ...primTorus([0, -0.15 * k, 0.975 * k], 0.025 * k, 0.005 * k, 8, 4, [1, 1, 1], [Math.PI / 2, 0, 0]),
  });

  if (p.include_boots) {
    for (const [s, side] of [[1, 'R'], [-1, 'L']]) {
      addCyl(`Boot_Shaft_${side}`, 'boot', [s * 0.1, 0, 0.16], 0.086, 0.28, [1, 1, 1], [0, 0, 0], 8, 0.096);
      addBox(`Boot_Foot_${side}`, 'boot', [s * 0.1, -0.065, 0.06], [0.178, 0.26, 0.06]);
      addBox(`Boot_Sole_${side}`, 'black', [s * 0.1, -0.065, 0.015], [0.188, 0.28, 0.03]);
    }
  }
  return { rootName: 'Outfit_BR', parts, materials };
}

function hashStringHex(text) {
  let h1 = 0xdeadbeef ^ text.length, h2 = 0x41c6ce57 ^ text.length;
  for (let i = 0; i < text.length; i++) {
    const ch = text.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (h2 >>> 0).toString(16).padStart(8, '0') + (h1 >>> 0).toString(16).padStart(8, '0');
}

export function generateRecipeGlbInBrowser(recipeId, rawParams = {}) {
  const params = validateWebParams(recipeId, rawParams);
  const hash = hashStringHex(JSON.stringify({ recipe: recipeId, params }));

  if (recipeId === 'battle_royale_outfit') {
    const { rootName, parts, materials } = buildBattleRoyaleParts(params);
    return { glb: packSceneToGlb(rootName, parts, materials), hash, params, filename: `${recipeId}_${hash}.glb` };
  }

  const baseMat = { main: { name: 'AssetMaterial', rgb: srgbHexToLinear(params.color), roughness: 0.68 } };
  const parts = [];

  if (recipeId === 'chair') {
    const { seat_width: w, seat_depth: d, seat_height: h, back_height: bh } = params;
    const count = parseInt(params.leg_count, 10);
    parts.push({ name: 'Seat', matKey: 'main', ...primBox([0, 0, h], [w, d, 0.12]) });
    for (const x of [-w * 0.42, w * 0.42]) {
      for (const y of [-d * 0.42, d * 0.42]) {
        if (count === 3 && x < 0 && y > 0) continue;
        parts.push({ name: 'Leg', matKey: 'main', ...primBox([x, y, h / 2], [0.09, 0.09, h]) });
      }
    }
    parts.push({ name: 'Backrest', matKey: 'main', ...primBox([0, d * 0.43, h + bh / 2], [w * 0.88, 0.09, bh]) });
    for (const x of [-w * 0.38, w * 0.38]) {
      parts.push({ name: 'BackPost', matKey: 'main', ...primBox([x, d * 0.42, h + bh * 0.42], [0.07, 0.08, bh * 0.85]) });
    }
  } else if (recipeId === 'table') {
    const { width: w, depth: d, height: h, top_shape, leg_style } = params;
    if (top_shape === 'round') {
      parts.push({ name: 'RoundTop', matKey: 'main', ...primCylinder([0, 0, h], Math.min(w, d) / 2, Math.min(w, d) / 2, 0.12, 32) });
    } else {
      parts.push({ name: 'Tabletop', matKey: 'main', ...primBox([0, 0, h], [w, d, 0.12]) });
    }
    for (const x of [-w * 0.42, w * 0.42]) {
      for (const y of [-d * 0.42, d * 0.42]) {
        if (leg_style === 'tapered') {
          parts.push({ name: 'TaperedLeg', matKey: 'main', ...primCylinder([x, y, h / 2], 0.065, 0.095, h, 12) });
        } else {
          parts.push({ name: 'TableLeg', matKey: 'main', ...primBox([x, y, h / 2], [0.1, 0.1, h]) });
        }
      }
    }
  } else if (recipeId === 'lamp') {
    const { base_radius: r, pole_height: ph, shade_size: sh, shade_type, segments } = params;
    parts.push({ name: 'Base', matKey: 'main', ...primCylinder([0, 0, 0.08], r, r, 0.16, Math.max(12, segments)) });
    parts.push({ name: 'Stem', matKey: 'main', ...primCylinder([0, 0, 0.16 + ph / 2], r * 0.13, r * 0.13, ph, 12) });
    const z = 0.16 + ph + sh * 0.48;
    if (shade_type === 'cone') {
      parts.push({ name: 'Shade', matKey: 'main', ...primCylinder([0, 0, z], sh * 0.5, sh * 0.9, sh, segments) });
    } else if (shade_type === 'cylinder') {
      parts.push({ name: 'Shade', matKey: 'main', ...primCylinder([0, 0, z], sh * 0.6, sh * 0.6, sh, segments) });
    } else {
      parts.push({ name: 'Shade', matKey: 'main', ...primUvSphere([0, 0, z], [sh * 0.58, sh * 0.58, sh * 0.52], segments, Math.max(6, Math.floor(segments / 2))) });
    }
  } else if (recipeId === 'rock') {
    parts.push({ name: 'Rock', matKey: 'main', ...primRock(params.seed, params.size, params.noise, params.subdivision, params.smoothness) });
  } else if (recipeId === 'barrel') {
    baseMat.hoop = { name: 'BarrelHoop', rgb: [0.22, 0.23, 0.25], metallic: 0.85, roughness: 0.35 };
    parts.push({ name: 'BarrelBody', matKey: 'main', ...primBarrelBody(params.radius, params.height, params.bulge, params.staves) });
    for (let i = 0; i < params.hoops; i++) {
      const z = (params.height * (i + 1)) / (params.hoops + 1);
      const rr = params.radius * (1 + params.bulge * Math.sin((Math.PI * z) / params.height)) * 1.025;
      parts.push({ name: `Hoop_${i}`, matKey: 'hoop', ...primTorus([0, 0, z], rr, params.radius * 0.045, params.staves, 6) });
    }
  }

  return { glb: packSceneToGlb('GeneratedAsset', parts, baseMat), hash, params, filename: `${recipeId}_${hash}.glb` };
}
