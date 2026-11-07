import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const packageRoot = process.env.THREE_PACKAGE;
if (!packageRoot) throw new Error('Set THREE_PACKAGE to an installed Three.js package directory.');
const THREE = await import(pathToFileURL(path.join(packageRoot, 'build/three.module.js')).href);
const { FBXLoader } = await import(pathToFileURL(path.join(packageRoot, 'examples/jsm/loaders/FBXLoader.js')).href);
const { retargetMixamoClip } = await import('../procedural_asset_app/frontend/motion-retarget.js');

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const characterFile = path.join(root, 'Base model ', 'Character', 'Superhero_Female_FullBody.gltf');
const motionDir = path.join(root, 'Base model ', 'Motion');
const gltf = JSON.parse(fs.readFileSync(characterFile, 'utf8'));
const jointSet = new Set(gltf.skins[0].joints);
const objects = gltf.nodes.map((node, index) => {
  const object = jointSet.has(index) ? new THREE.Bone() : new THREE.Group();
  object.name = node.name || `node_${index}`;
  if (node.matrix) {
    new THREE.Matrix4().fromArray(node.matrix).decompose(object.position, object.quaternion, object.scale);
  } else {
    if (node.translation) object.position.fromArray(node.translation);
    if (node.rotation) object.quaternion.fromArray(node.rotation);
    if (node.scale) object.scale.fromArray(node.scale);
  }
  return object;
});
for (let i = 0; i < gltf.nodes.length; i++) {
  for (const child of gltf.nodes[i].children || []) objects[i].add(objects[child]);
}
const targetRoot = new THREE.Group();
for (const nodeIndex of gltf.scenes[gltf.scene || 0].nodes) targetRoot.add(objects[nodeIndex]);
targetRoot.updateMatrixWorld(true);
const bindPose = new Map();
targetRoot.traverse(node => {
  if (node.isBone) bindPose.set(node, {
    position: node.position.clone(), quaternion: node.quaternion.clone(), scale: node.scale.clone()
  });
});

function toArrayBuffer(buffer) {
  return buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
}

const files = fs.readdirSync(motionDir).filter(file => file.toLowerCase().endsWith('.fbx')).sort();
let totalTracks = 0;
let footerFixed = 0;
for (const file of files) {
  const bytes = fs.readFileSync(path.join(motionDir, file));
  const loader = new FBXLoader();
  let source;
  try {
    try {
      source = loader.parse(toArrayBuffer(bytes), '');
    } catch (error) {
      source = loader.parse(toArrayBuffer(bytes.subarray(0, -1)), '');
      footerFixed++;
    }
    const clip = source.animations?.[0];
    if (!clip) throw new Error('no AnimationClip found');
    const retargeted = retargetMixamoClip(THREE, source, targetRoot, bindPose, clip);
    if (retargeted.tracks.length < 30 || retargeted.duration <= 0) {
      throw new Error(`only ${retargeted.tracks.length} mapped tracks, duration ${retargeted.duration}`);
    }
    let hasMotion = false;
    for (const track of retargeted.tracks) {
      if (!Array.from(track.values).every(Number.isFinite)) throw new Error(`non-finite keys in ${track.name}`);
      const stride = track.getValueSize();
      for (let i = stride; i < track.values.length; i += stride) {
        let delta = 0;
        for (let j = 0; j < stride; j++) delta = Math.max(delta, Math.abs(track.values[i + j] - track.values[j]));
        if (delta > 1e-4) { hasMotion = true; break; }
      }
    }
    if (!hasMotion) throw new Error('all retargeted keys are static');
    if (['idle.fbx', 'running.fbx', 'dive roll.fbx'].includes(file.toLowerCase())) {
      const mixer = new THREE.AnimationMixer(targetRoot);
      const action = mixer.clipAction(retargeted);
      action.play();
      mixer.update(Math.min(0.2, retargeted.duration * 0.4));
      let changedPose = false;
      for (const [bone, pose] of bindPose) {
        if (1 - Math.abs(bone.quaternion.dot(pose.quaternion)) > 1e-5 || bone.position.distanceTo(pose.position) > 1e-5) {
          changedPose = true;
          break;
        }
      }
      mixer.stopAllAction();
      for (const [bone, pose] of bindPose) {
        bone.position.copy(pose.position);bone.quaternion.copy(pose.quaternion);bone.scale.copy(pose.scale);
      }
      targetRoot.updateMatrixWorld(true);
      mixer.uncacheRoot(targetRoot);
      if (!changedPose) throw new Error('AnimationMixer playback did not move the target skeleton.');
    }
    totalTracks += retargeted.tracks.length;
    source.traverse(node => {
      node.geometry?.dispose();
      if (node.material) for (const material of (Array.isArray(node.material) ? node.material : [node.material])) material?.dispose();
    });
  } catch (error) {
    console.error(`FAIL ${file}: ${error.message}`);
    process.exitCode = 1;
  }
}
console.log(`Retargeted ${files.length} FBX clips; ${totalTracks} bone tracks total; ${footerFixed} footer-padding files normalized at load.`);
if (files.length !== 74) {
  console.error(`Expected 74 source FBX clips, found ${files.length}.`);
  process.exitCode = 1;
}
