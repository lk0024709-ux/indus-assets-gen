const GLB_MAGIC = 0x46546C67; // "glTF"
const JSON_CHUNK = 0x4E4F534A; // "JSON"
const BIN_CHUNK = 0x004E4942;  // "BIN\0"

function align4Len(len) {
  return (4 - (len % 4)) % 4;
}

export function parseGlbChunks(arrayBuffer) {
  const bytes = arrayBuffer instanceof Uint8Array
    ? arrayBuffer
    : new Uint8Array(arrayBuffer);
  if (bytes.byteLength < 28) {
    throw new Error('GLB buffer is too short.');
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const magic = view.getUint32(0, true);
  const version = view.getUint32(4, true);
  const totalLen = view.getUint32(8, true);
  if (magic !== GLB_MAGIC || version !== 2 || totalLen > bytes.byteLength) {
    throw new Error('Invalid glTF 2.0 binary header.');
  }
  const jsonLen = view.getUint32(12, true);
  const jsonType = view.getUint32(16, true);
  if (jsonType !== JSON_CHUNK) {
    throw new Error('Missing GLB JSON chunk.');
  }
  const jsonText = new TextDecoder().decode(bytes.subarray(20, 20 + jsonLen)).replace(/[\0 ]+$/, '');
  const gltf = JSON.parse(jsonText);
  const binHeaderOffset = 20 + jsonLen;
  const binLen = view.getUint32(binHeaderOffset, true);
  const binType = view.getUint32(binHeaderOffset + 4, true);
  if (binType !== BIN_CHUNK) {
    throw new Error('Missing GLB BIN chunk.');
  }
  const bin = bytes.subarray(binHeaderOffset + 8, binHeaderOffset + 8 + binLen);
  return { gltf, bin };
}

/**
 * Merge a packed 65-joint superhero character GLB with its fitted Battle Royale outfit GLB
 * onto the shared `skin[0]` without re-encoding any embedded PBR PNG maps.
 */
export function combineCharacterAndOutfitGlb(characterBuffer, outfitBuffer, includedGroups = null) {
  const { gltf: charGltf, bin: charBin } = parseGlbChunks(characterBuffer);
  const { gltf: outGltf, bin: outBin } = parseGlbChunks(outfitBuffer);

  const charJoints = (charGltf.skins?.[0]?.joints || []).map(j => charGltf.nodes[j]?.name);
  const outJoints = (outGltf.skins?.[0]?.joints || []).map(j => outGltf.nodes[j]?.name);
  if (!charJoints.length || charJoints.length !== outJoints.length || charJoints.some((n, i) => n !== outJoints[i])) {
    throw new Error('Character and outfit skeletons do not share the same 65-joint order.');
  }

  const charPad = align4Len(charBin.byteLength);
  const binOffset = charBin.byteLength + charPad;
  const rawCombinedLen = binOffset + outBin.byteLength;
  const binPad = align4Len(rawCombinedLen);
  const combinedBin = new Uint8Array(rawCombinedLen + binPad);
  combinedBin.set(charBin, 0);
  combinedBin.set(outBin, binOffset);

  const bvOffset = charGltf.bufferViews.length;
  for (const bv of outGltf.bufferViews || []) {
    charGltf.bufferViews.push({
      ...bv,
      buffer: 0,
      byteOffset: (bv.byteOffset || 0) + binOffset,
    });
  }

  const accOffset = charGltf.accessors.length;
  for (const acc of outGltf.accessors || []) {
    charGltf.accessors.push({
      ...acc,
      bufferView: acc.bufferView + bvOffset,
    });
  }

  const matOffset = (charGltf.materials || []).length;
  charGltf.materials = charGltf.materials || [];
  for (const mat of outGltf.materials || []) {
    charGltf.materials.push(structuredClone(mat));
  }

  const sceneIdx = charGltf.scene ?? 0;
  const armatureIdx = charGltf.scenes[sceneIdx].nodes[0];
  charGltf.nodes[armatureIdx].children = charGltf.nodes[armatureIdx].children || [];

  const groupFilter = includedGroups ? new Set(includedGroups) : null;
  for (const nd of outGltf.nodes || []) {
    if (nd.mesh === undefined) continue;
    const srcMesh = outGltf.meshes[nd.mesh];
    const group = nd.extras?.pieceGroup || srcMesh?.extras?.pieceGroup || 'gear';
    if (groupFilter && !groupFilter.has(group)) continue;
    const clonedMesh = structuredClone(srcMesh);
    for (const prim of clonedMesh.primitives || []) {
      const nextAttrs = {};
      for (const [attrName, accIdx] of Object.entries(prim.attributes || {})) {
        nextAttrs[attrName] = accIdx + accOffset;
      }
      prim.attributes = nextAttrs;
      if (prim.indices !== undefined) prim.indices += accOffset;
      if (prim.material !== undefined) prim.material += matOffset;
    }
    const meshIdx = charGltf.meshes.length;
    charGltf.meshes.push(clonedMesh);
    const nodeIdx = charGltf.nodes.length;
    charGltf.nodes.push({
      name: nd.name,
      mesh: meshIdx,
      skin: 0,
      extras: { pieceGroup: group },
    });
    charGltf.nodes[armatureIdx].children.push(nodeIdx);
  }

  charGltf.buffers[0].byteLength = rawCombinedLen;
  charGltf.asset = {
    ...(charGltf.asset || {}),
    version: '2.0',
    generator: 'Indus Character Studio GLB Combiner (source PBR + 65-joint Battle Royale outfit)',
  };

  const jsonBytes = new TextEncoder().encode(JSON.stringify(charGltf));
  const jsonPad = align4Len(jsonBytes.byteLength);
  const jsonChunkLen = jsonBytes.byteLength + jsonPad;
  const binChunkLen = combinedBin.byteLength;
  const totalBytes = 12 + 8 + jsonChunkLen + 8 + binChunkLen;

  const out = new Uint8Array(totalBytes);
  const outView = new DataView(out.buffer);
  outView.setUint32(0, GLB_MAGIC, true);
  outView.setUint32(4, 2, true);
  outView.setUint32(8, totalBytes, true);
  outView.setUint32(12, jsonChunkLen, true);
  outView.setUint32(16, JSON_CHUNK, true);
  out.set(jsonBytes, 20);
  if (jsonPad) out.fill(0x20, 20 + jsonBytes.byteLength, 20 + jsonChunkLen);

  const binChunkHeader = 20 + jsonChunkLen;
  outView.setUint32(binChunkHeader, binChunkLen, true);
  outView.setUint32(binChunkHeader + 4, BIN_CHUNK, true);
  out.set(combinedBin, binChunkHeader + 8);
  return out;
}
