import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const packageRoot = process.env.THREE_PACKAGE;
if (!packageRoot) throw new Error('Set THREE_PACKAGE to an installed Three.js package directory.');
const THREE = await import(pathToFileURL(path.join(packageRoot, 'build/three.module.js')).href);
const { FBXLoader } = await import(pathToFileURL(path.join(packageRoot, 'examples/jsm/loaders/FBXLoader.js')).href);
const { GLTFLoader } = await import(pathToFileURL(path.join(packageRoot, 'examples/jsm/loaders/GLTFLoader.js')).href);
const { normalizedBoneName, retargetMixamoClip } = await import('../procedural_asset_app/frontend/motion-retarget.js');
const { combineCharacterAndOutfitGlb, parseGlbChunks, recolorOutfitGlb } = await import('../procedural_asset_app/frontend/glb-combine.js');
const { WEB_RECIPES, generateRecipeGlbInBrowser } = await import('../procedural_asset_app/frontend/web-recipes.js');

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

function findBone(root, normalizedName) {
  let result = null;
  root.traverse(node => {
    if (node.isBone && normalizedBoneName(node.name) === normalizedName) result = node;
  });
  return result;
}

function restoreTargetBindPose() {
  for (const [bone, pose] of bindPose) {
    bone.position.copy(pose.position);
    bone.quaternion.copy(pose.quaternion);
    bone.scale.copy(pose.scale);
  }
  targetRoot.updateMatrixWorld(true);
}

const files = fs.readdirSync(motionDir).filter(file => file.toLowerCase().endsWith('.fbx')).sort();
const representativeFiles = new Set([
  'idle.fbx', 'running.fbx', 'run right.fbx', 'dive roll.fbx',
  'crouch walking.fbx', 'firing rifle.fbx', 'death crouching headshot front.fbx'
]);
let totalTracks = 0;
let footerFixed = 0;
const playbackSamplesValidated = new Set();
let maxRunRightFootError = 0;
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
    if (representativeFiles.has(file.toLowerCase())) {
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

      if (file.toLowerCase() === 'run right.fbx') {
        const sourceHipsTrack = clip.tracks.find(track => track.name.toLowerCase().endsWith('hips.position'));
        const targetHipsTrack = retargeted.tracks.find(track => track.name === 'pelvis.position');
        if (!sourceHipsTrack || !targetHipsTrack || sourceHipsTrack.values.length < 6 || targetHipsTrack.values.length < 6) {
          throw new Error('Root-motion tracks are missing from the source or retargeted Run Right clip.');
        }
        const pointAt = (values, index) => new THREE.Vector3(values[index * 3], values[index * 3 + 1], values[index * 3 + 2]);
        const sourceTravel = pointAt(sourceHipsTrack.values, sourceHipsTrack.values.length / 3 - 1)
          .sub(pointAt(sourceHipsTrack.values, 0)).multiplyScalar(0.01).length();
        const targetTravel = pointAt(targetHipsTrack.values, targetHipsTrack.values.length / 3 - 1)
          .sub(pointAt(targetHipsTrack.values, 0)).length();
        if (Math.abs(sourceTravel - targetTravel) > 0.02) {
          throw new Error(`Run Right root travel changed during retargeting (${sourceTravel.toFixed(3)}m source vs ${targetTravel.toFixed(3)}m target).`);
        }

        const sourceHips = findBone(source, 'hips');
        const sourceFeet = [findBone(source, 'leftfoot'), findBone(source, 'rightfoot')];
        const targetHips = findBone(targetRoot, 'pelvis');
        const targetFeet = [findBone(targetRoot, 'footl'), findBone(targetRoot, 'footr')];
        if (!sourceHips || !targetHips || sourceFeet.some(bone => !bone) || targetFeet.some(bone => !bone)) {
          throw new Error('Could not find pelvis/foot bones for root-relative pose fidelity check.');
        }
        const sourceMixer = new THREE.AnimationMixer(source);
        sourceMixer.clipAction(clip).play();
        const targetMixer = new THREE.AnimationMixer(targetRoot);
        targetMixer.clipAction(retargeted).play();
        for (const time of [0, 0.1, 0.2, 0.4]) {
          sourceMixer.setTime(time);
          targetMixer.setTime(time);
          source.updateMatrixWorld(true);
          targetRoot.updateMatrixWorld(true);
          const sourceHipY = sourceHips.getWorldPosition(new THREE.Vector3()).y;
          const targetHipY = targetHips.getWorldPosition(new THREE.Vector3()).y;
          for (let side = 0; side < 2; side++) {
            const sourceFootOffset = (sourceFeet[side].getWorldPosition(new THREE.Vector3()).y - sourceHipY) * 0.01;
            const targetFootOffset = targetFeet[side].getWorldPosition(new THREE.Vector3()).y - targetHipY;
            const error = Math.abs(sourceFootOffset - targetFootOffset);
            maxRunRightFootError = Math.max(maxRunRightFootError, error);
            if (error > 0.18) {
              throw new Error(`Run Right ${side ? 'right' : 'left'} foot deviates ${error.toFixed(3)}m from source-relative motion at ${time.toFixed(2)}s.`);
            }
          }
        }
        sourceMixer.stopAllAction();
        targetMixer.stopAllAction();
        sourceMixer.uncacheRoot(source);
        targetMixer.uncacheRoot(targetRoot);
        restoreTargetBindPose();
      }
      playbackSamplesValidated.add(file.toLowerCase());
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
const missingSamples = [...representativeFiles].filter(file => !playbackSamplesValidated.has(file));
if (missingSamples.length) {
  console.error(`Representative AnimationMixer samples were not validated: ${missingSamples.join(', ')}.`);
  process.exitCode = 1;
}
console.log(`Retargeted ${files.length} FBX clips; ${totalTracks} bone tracks total; ${footerFixed} footer-padding files normalized at load.`);
console.log(`AnimationMixer samples validated across four categories: ${[...playbackSamplesValidated].join(', ')}.`);
console.log(`Run Right root travel preserved; max pelvis-relative foot offset error ${maxRunRightFootError.toFixed(3)}m (limit 0.180m).`);
if (files.length !== 74) {
  console.error(`Expected 74 source FBX clips, found ${files.length}.`);
  process.exitCode = 1;
}

// Validate fitted Battle Royale outfits + client-side GLB combiner against retargeted motion
for (const outfitName of ['outfit_br_female.glb', 'outfit_br_male.glb']) {
  const outfitBytes = fs.readFileSync(path.join(root, 'procedural_asset_app/frontend/assets/outfits', outfitName));
  const parsedOutfit = await new Promise((resolve, reject) => {
    new GLTFLoader().parse(toArrayBuffer(outfitBytes), '', resolve, reject);
  });
  parsedOutfit.scene.updateMatrixWorld(true);
  const outfitBind = new Map();
  parsedOutfit.scene.traverse(node => {
    if (node.isBone) outfitBind.set(node, {
      position: node.position.clone(), quaternion: node.quaternion.clone(), scale: node.scale.clone()
    });
  });
  const runFbx = new FBXLoader().parse(toArrayBuffer(fs.readFileSync(path.join(motionDir, 'Running.fbx'))), '');
  const runClip = retargetMixamoClip(THREE, runFbx, parsedOutfit.scene, outfitBind, runFbx.animations[0]);
  const outfitMixer = new THREE.AnimationMixer(parsedOutfit.scene);
  outfitMixer.clipAction(runClip).play();
  outfitMixer.update(0.25);
  parsedOutfit.scene.updateMatrixWorld(true);
  for (const piece of ['Tee', 'Cargo_Pants', 'Boots', 'Holster', 'KneePad_R', 'Tee_ChestStar']) {
    const sm = parsedOutfit.scene.getObjectByName(piece);
    if (!sm?.isSkinnedMesh) throw new Error(`${outfitName}: missing SkinnedMesh ${piece}`);
    const restPos = new THREE.Vector3().fromBufferAttribute(sm.geometry.attributes.position, 0);
    const animPos = sm.applyBoneTransform(0, restPos.clone());
    if (!Number.isFinite(animPos.x) || animPos.distanceTo(restPos) < 1e-4) {
      throw new Error(`${outfitName}: ${piece} failed skeletal deformation check`);
    }
  }
}
const heroBytes = fs.readFileSync(path.join(root, 'procedural_asset_app/frontend/assets/characters/superhero_female_dark.glb'));
const fitBytes = fs.readFileSync(path.join(root, 'procedural_asset_app/frontend/assets/outfits/outfit_br_female.glb'));
const mergedGlb = combineCharacterAndOutfitGlb(heroBytes, fitBytes, null, { tee: '#262D38', pants: '#1C2029', gear: '#12141A' });
const { gltf: mergedJson } = parseGlbChunks(mergedGlb);
if (mergedJson.meshes.length !== 23 || mergedJson.skins[0].joints.length !== 65) {
  throw new Error(`Combined GLB mismatch: meshes=${mergedJson.meshes.length}`);
}
const recoloredFit = recolorOutfitGlb(fitBytes, { tee: '#8F2933', pants: '#2B2B33', gear: '#18181D' });
const { gltf: recoloredJson } = parseGlbChunks(recoloredFit);
const teeMat = recoloredJson.materials.find(m => m.name.endsWith('_tee'));
if (!teeMat || teeMat.pbrMetallicRoughness.baseColorFactor[0] <= teeMat.pbrMetallicRoughness.baseColorFactor[1]) {
  throw new Error('Crimson tee colorway override was not applied to outfit GLB.');
}
for (const recipe of WEB_RECIPES) {
  const { glb } = generateRecipeGlbInBrowser(recipe.id, {});
  const parsedWeb = await new Promise((resolve, reject) => {
    new GLTFLoader().parse(toArrayBuffer(glb), '', resolve, reject);
  });
  const bounds = new THREE.Box3().setFromObject(parsedWeb.scene).getSize(new THREE.Vector3());
  if (bounds.x <= 0.1 || bounds.y <= 0.1 || bounds.z <= 0.1) {
    throw new Error(`Browser web recipe ${recipe.id} produced invalid bounds`);
  }
}
console.log('Validated Battle Royale fitted outfit GLBs, color-customized GLB combiner, and all 6 browser Web GLB recipes.');
