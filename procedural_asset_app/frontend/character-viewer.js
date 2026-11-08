import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { retargetMixamoClip } from './motion-retarget.js';
import { combineCharacterAndOutfitGlb } from './glb-combine.js';

const $ = id => document.getElementById(id);
const modelDescriptions = {
  superhero_female_dark: 'Full-body superhero character with the original dark skin BaseColor, eye and hair maps, and the 65-joint source rig.',
  superhero_female_light: 'Full-body superhero character with the alternate light skin BaseColor from the source texture set, plus the original eye, hair and rig assets.',
  superhero_male_dark: 'Full-body superhero character with the original male dark BaseColor, eye and hair maps, and the 65-joint source rig.',
  superhero_male_light: 'Full-body superhero character with the alternate male light BaseColor from the source texture set, plus the original eye, hair and rig assets.'
};
const pieceGroupByMeshName = {
  Tee: 'tee', Tee_Body: 'tee', Tee_Collar: 'tee', Tee_Sleeve_R: 'tee', Tee_Sleeve_L: 'tee',
  Tee_ChestPatch: 'tee', Tee_ChestStar: 'tee',
  Cargo_Pants: 'pants', Pants_Hips: 'pants', Pants_Leg_R: 'pants', Pants_Leg_L: 'pants',
  Cargo_Pocket: 'pants', Cargo_Flap: 'pants', KneePad_R: 'pants', KneePad_L: 'pants',
  Belt: 'gear', Belt_Buckle: 'gear', Pouch_R: 'gear', Pouch_L: 'gear',
  Bullet_0: 'gear', Bullet_1: 'gear', Bullet_2: 'gear', Carabiner: 'gear',
  Holster: 'gear', Holster_Strap_0: 'gear', Holster_Strap_1: 'gear',
  Boots: 'boots', Boot_Shaft_R: 'boots', Boot_Shaft_L: 'boots',
  Boot_Foot_R: 'boots', Boot_Foot_L: 'boots', Boot_Sole_R: 'boots', Boot_Sole_L: 'boots'
};

const assetUrl = filename => new URL(`./assets/characters/${encodeURIComponent(filename)}`, document.baseURI).href;
const outfitUrl = filename => new URL(`./assets/outfits/${encodeURIComponent(filename)}`, document.baseURI).href;
const motionUrl = filename => new URL(`./assets/motions/${encodeURIComponent(filename)}`, document.baseURI).href;

const manifest = await fetch(assetUrl('characters.json')).then(response => {
  if (!response.ok) throw new Error('The character manifest could not be loaded.');
  return response.json();
});
const models = new Map(manifest.models.map(model => [model.id, model]));

const outfitManifestResponse = await fetch(outfitUrl('outfits.json')).catch(() => null);
const outfitManifest = outfitManifestResponse?.ok ? await outfitManifestResponse.json() : { outfits: [] };
const outfitsById = new Map((outfitManifest.outfits || []).map(item => [item.id, item]));

const motionManifestResponse = await fetch(new URL('./assets/motion-manifest.json', document.baseURI)).catch(() => null);
const motionManifest = motionManifestResponse?.ok ? await motionManifestResponse.json() : { motions: [], count: 0 };
const motions = motionManifest.motions || [];
const motionById = new Map(motions.map(motion => [motion.id, motion]));

let renderer, scene, camera, controls, activeModel = null, activeId = '', frameSize = 1;
let activeHeroMeshes = [], attachedOutfitGroup = null, standaloneOutfitModel = null;
let mixer = null, activeAction = null, bindPose = null, selectedMotionId = '';
let motionRequest = 0, loadToken = 0;
let outfitMode = 'equipped'; // 'equipped' | 'none' | 'outfit-only' | 'standalone'
const enabledGroups = new Set(['tee', 'pants', 'gear', 'boots']);

const motionCache = new Map();
const outfitBufferCache = new Map();
const outfitTemplateCache = new Map();
const characterBufferCache = new Map();

let autoRotate = true;
const host = $('viewport');
const loader = new GLTFLoader();
const clock = new THREE.Clock();

function outfitIdForHero(heroId) {
  return heroId.includes('female') ? 'outfit_br_female' : 'outfit_br_male';
}

function getMeshPieceGroup(node) {
  return node.userData?.pieceGroup || pieceGroupByMeshName[node.name] || 'gear';
}

async function fetchOutfitBuffer(outfitId) {
  if (outfitBufferCache.has(outfitId)) return outfitBufferCache.get(outfitId);
  const record = outfitsById.get(outfitId);
  const file = record ? record.file : `${outfitId}.glb`;
  const response = await fetch(outfitUrl(file));
  if (!response.ok) throw new Error(`Could not load outfit ${file} (${response.status}).`);
  const buffer = await response.arrayBuffer();
  outfitBufferCache.set(outfitId, buffer);
  return buffer;
}

async function fetchCharacterBuffer(heroId) {
  if (characterBufferCache.has(heroId)) return characterBufferCache.get(heroId);
  const record = models.get(heroId);
  if (!record) throw new Error(`Unknown character ${heroId}.`);
  const response = await fetch(assetUrl(record.file));
  if (!response.ok) throw new Error(`Could not load ${record.file} (${response.status}).`);
  const buffer = await response.arrayBuffer();
  characterBufferCache.set(heroId, buffer);
  return buffer;
}

async function getParsedOutfitTemplate(outfitId) {
  if (outfitTemplateCache.has(outfitId)) return outfitTemplateCache.get(outfitId);
  const buffer = await fetchOutfitBuffer(outfitId);
  const parsed = await new Promise((resolve, reject) => {
    loader.parse(buffer.slice(0), '', resolve, reject);
  });
  parsed.scene.traverse(node => {
    if (node.isMesh) {
      node.userData.pieceGroup = node.userData?.pieceGroup || pieceGroupByMeshName[node.name] || 'gear';
    }
  });
  outfitTemplateCache.set(outfitId, parsed.scene);
  return parsed.scene;
}

function init() {
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(36, 1, 0.01, 100);
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.18;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.domElement.setAttribute('aria-label', 'Drag to orbit the 3D superhero character. Scroll to zoom.');
  host.prepend(renderer.domElement);

  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  pmrem.dispose();
  scene.add(new THREE.HemisphereLight(0xe2eaff, 0x33343d, 1.65));
  const key = new THREE.DirectionalLight(0xffedcf, 3.1);
  key.position.set(-3.4, 6.5, 4.2);
  key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.camera.left = -3;
  key.shadow.camera.right = 3;
  key.shadow.camera.top = 4;
  key.shadow.camera.bottom = -1;
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x8eaaff, 1.35);
  fill.position.set(4, 3.4, -3.8);
  scene.add(fill);
  const rim = new THREE.DirectionalLight(0xb1ffd5, 1.35);
  rim.position.set(0.5, 4, -5);
  scene.add(rim);

  const floor = new THREE.Mesh(
    new THREE.CircleGeometry(5, 80),
    new THREE.MeshStandardMaterial({ color: 0x10151d, roughness: 0.84, metalness: 0.08 })
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -0.035;
  floor.receiveShadow = true;
  scene.add(floor);

  const pedestal = new THREE.Mesh(
    new THREE.CylinderGeometry(0.54, 0.6, 0.065, 64),
    new THREE.MeshStandardMaterial({ color: 0x242a32, roughness: 0.38, metalness: 0.56 })
  );
  pedestal.position.y = 0.003;
  pedestal.receiveShadow = true;
  pedestal.castShadow = true;
  scene.add(pedestal);
  const rimRing = new THREE.Mesh(
    new THREE.TorusGeometry(0.535, 0.009, 8, 96),
    new THREE.MeshStandardMaterial({ color: 0xb6ec6b, emissive: 0x354d19, metalness: 0.55, roughness: 0.3 })
  );
  rimRing.rotation.x = Math.PI / 2;
  rimRing.position.y = 0.037;
  scene.add(rimRing);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.055;
  controls.enablePan = false;
  controls.minPolarAngle = 0.16;
  controls.maxPolarAngle = Math.PI * 0.49;
  controls.minDistance = 1.4;
  controls.maxDistance = 9;
  controls.autoRotate = autoRotate;
  controls.autoRotateSpeed = 0.7;
  controls.addEventListener('start', () => { if (autoRotate) controls.autoRotate = false; });
  controls.addEventListener('end', () => { if (autoRotate) controls.autoRotate = true; });
  resize();
  new ResizeObserver(resize).observe(host);
  window.addEventListener('resize', resize, { passive: true });
  renderer.setAnimationLoop(() => {
    const delta = Math.min(clock.getDelta(), 0.05);
    if (mixer && outfitMode !== 'standalone') mixer.update(delta);
    if (controls) controls.update();
    updateMotionTimeline();
    renderer.render(scene, camera);
  });
}

function resize() {
  if (!renderer || !camera) return;
  const width = Math.max(host.clientWidth, 1);
  const height = Math.max(host.clientHeight, 1);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height, false);
}

function disposeModel(model) {
  const textures = new Set();
  model.traverse(node => {
    if (!node.isMesh) return;
    node.geometry?.dispose();
    for (const material of (Array.isArray(node.material) ? node.material : [node.material])) {
      if (!material) continue;
      for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
      material.dispose();
    }
    node.skeleton?.dispose();
  });
  textures.forEach(texture => texture.dispose());
}

function frameCharacter(model) {
  const bounds = new THREE.Box3().setFromObject(model);
  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  frameSize = Math.max(size.x, size.y, size.z, 1);
  model.position.x -= center.x;
  model.position.z -= center.z;
  model.position.y += 0.035 - bounds.min.y;
  controls.target.set(0, Math.max(size.y * 0.52, 0.7), 0);
  const distance = Math.max(frameSize * 2.45, 3.8);
  camera.position.set(frameSize * 0.15, size.y * 0.64, distance);
  camera.near = 0.01;
  camera.far = 100;
  camera.updateProjectionMatrix();
  controls.minDistance = frameSize * 1.15;
  controls.maxDistance = frameSize * 5.2;
  controls.update();
}

function captureBindPose() {
  bindPose = new Map();
  activeModel?.traverse(node => {
    if (node.isBone) bindPose.set(node, {
      position: node.position.clone(), quaternion: node.quaternion.clone(), scale: node.scale.clone()
    });
  });
}

function restoreBindPose() {
  if (!bindPose) return;
  for (const [bone, pose] of bindPose) {
    bone.position.copy(pose.position);
    bone.quaternion.copy(pose.quaternion);
    bone.scale.copy(pose.scale);
  }
  activeModel?.updateMatrixWorld(true);
}

function formatTime(seconds) {
  const value = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
}

function updateMotionTimeline() {
  const seek = $('motionSeek');
  if (!activeAction || !seek) return;
  const duration = activeAction.getClip().duration || 0;
  const time = Math.min(activeAction.time, duration);
  if (!seek.matches(':active') && !seek.matches(':focus')) seek.value = String(Math.round(duration ? (time / duration) * 1000 : 0));
  $('motionTime').textContent = `${formatTime(time)} / ${formatTime(duration)}`;
}

async function attachFittedOutfitToHero(heroModel, heroId, currentToken) {
  const outfitId = outfitIdForHero(heroId);
  if (!outfitsById.has(outfitId)) return null;
  let primarySkinnedMesh = null;
  let maxVerts = 0;
  heroModel.traverse(node => {
    if (node.isSkinnedMesh && node.skeleton?.bones?.length) {
      const count = node.geometry?.attributes?.position?.count || 0;
      if (count > maxVerts) {
        maxVerts = count;
        primarySkinnedMesh = node;
      }
    }
  });
  if (!primarySkinnedMesh || !primarySkinnedMesh.parent) return null;

  const templateScene = await getParsedOutfitTemplate(outfitId);
  if (currentToken !== loadToken || activeModel !== heroModel) return null;

  const group = new THREE.Group();
  group.name = 'Outfit_BR_Fit';
  templateScene.traverse(node => {
    if (!node.isSkinnedMesh) return;
    const mat = Array.isArray(node.material)
      ? node.material.map(m => m.clone())
      : node.material.clone();
    for (const m of (Array.isArray(mat) ? mat : [mat])) {
      m.side = THREE.DoubleSide;
      m.needsUpdate = true;
    }
    const skinnedClone = new THREE.SkinnedMesh(node.geometry.clone(), mat);
    skinnedClone.name = node.name;
    skinnedClone.castShadow = true;
    skinnedClone.receiveShadow = true;
    skinnedClone.frustumCulled = false;
    skinnedClone.userData.pieceGroup = getMeshPieceGroup(node);
    skinnedClone.bind(primarySkinnedMesh.skeleton, primarySkinnedMesh.bindMatrix);
    group.add(skinnedClone);
  });
  primarySkinnedMesh.parent.add(group);
  return group;
}

async function ensureStandaloneOutfitLoaded() {
  if (standaloneOutfitModel) return standaloneOutfitModel;
  const templateScene = await getParsedOutfitTemplate('outfit_battle_royale');
  const rootClone = templateScene.clone(true);
  rootClone.traverse(node => {
    if (!node.isMesh) return;
    node.geometry = node.geometry.clone();
    node.material = Array.isArray(node.material)
      ? node.material.map(m => m.clone())
      : node.material.clone();
    for (const m of (Array.isArray(node.material) ? node.material : [node.material])) {
      m.side = THREE.DoubleSide;
    }
    node.castShadow = true;
    node.receiveShadow = true;
    node.userData.pieceGroup = getMeshPieceGroup(node);
  });
  frameCharacter(rootClone);
  standaloneOutfitModel = rootClone;
  scene.add(standaloneOutfitModel);
  return standaloneOutfitModel;
}

function updateSpecsAndLabels() {
  const heroRecord = models.get(activeId);
  if (!heroRecord) return;
  const fittedRecord = outfitsById.get(outfitIdForHero(activeId));
  const standaloneRecord = outfitsById.get('outfit_battle_royale');

  let activeOutfitPieces = 0;
  let activeOutfitVertices = 0;
  const countFromRecord = record => {
    if (!record?.piece_details) return;
    for (const piece of record.piece_details) {
      if (enabledGroups.has(piece.group)) {
        activeOutfitPieces++;
        activeOutfitVertices += piece.vertices || 0;
      }
    }
  };

  if (outfitMode === 'equipped' || outfitMode === 'outfit-only') {
    countFromRecord(fittedRecord);
  } else if (outfitMode === 'standalone') {
    countFromRecord(standaloneRecord);
  }

  const groupControlsDisabled = outfitMode === 'none';
  document.querySelectorAll('.outfit-group-pill').forEach(pill => {
    const active = enabledGroups.has(pill.dataset.outfitGroup);
    pill.disabled = groupControlsDisabled;
    pill.classList.toggle('active', active);
    pill.setAttribute('aria-pressed', String(active));
  });
  document.querySelectorAll('.outfit-mode').forEach(btn => {
    const selected = btn.dataset.outfitMode === outfitMode;
    btn.classList.toggle('active', selected);
    btn.setAttribute('aria-pressed', String(selected));
  });

  if (outfitMode === 'none') {
    $('outfitPieceCount').textContent = 'OFF';
    $('selectedName').textContent = heroRecord.label;
    $('selectedDescription').textContent = modelDescriptions[activeId] || 'Rigged full-body superhero character using repository source assets.';
    $('vertexCount').textContent = Number(heroRecord.vertices).toLocaleString();
    $('jointCount').textContent = String(heroRecord.joints || 65);
    $('mapCount').textContent = String(heroRecord.textures.length);
    $('viewportLabel').textContent = heroRecord.label.toUpperCase();
    $('modelFile').textContent = heroRecord.file;
    $('downloadModelLabel').textContent = 'Download character GLB';
    $('downloadOutfitLabel').textContent = 'Download fitted outfit GLB';
  } else if (outfitMode === 'equipped') {
    $('outfitPieceCount').textContent = `${activeOutfitPieces} PCS`;
    $('selectedName').textContent = `${heroRecord.label} · Battle Royale`;
    $('selectedDescription').textContent = `${modelDescriptions[activeId]} Equipped with ${activeOutfitPieces} fitted Battle Royale tactical pieces skinned to the 65-joint rig.`;
    $('vertexCount').textContent = Number(heroRecord.vertices + activeOutfitVertices).toLocaleString();
    $('jointCount').textContent = String(heroRecord.joints || 65);
    $('mapCount').textContent = String(heroRecord.textures.length);
    $('viewportLabel').textContent = `${heroRecord.label.toUpperCase()} · BR OUTFIT`;
    $('modelFile').textContent = `${heroRecord.id} + ${fittedRecord?.file || 'outfit_br.glb'}`;
    $('downloadModelLabel').textContent = activeOutfitPieces > 0
      ? 'Download character + outfit GLB'
      : 'Download character GLB';
    $('downloadOutfitLabel').textContent = 'Download fitted outfit GLB';
  } else if (outfitMode === 'outfit-only') {
    $('outfitPieceCount').textContent = `${activeOutfitPieces} PCS`;
    $('selectedName').textContent = fittedRecord?.label || 'Battle Royale Outfit · Rigged Fit';
    $('selectedDescription').textContent = fittedRecord?.description || 'Rigged 20-piece Battle Royale outfit fitted to the 65-joint superhero skeleton.';
    $('vertexCount').textContent = Number(activeOutfitVertices).toLocaleString();
    $('jointCount').textContent = '65';
    $('mapCount').textContent = '0 · PBR';
    $('viewportLabel').textContent = `${heroRecord.id.includes('female') ? 'FEMALE' : 'MALE'} · RIGGED OUTFIT`;
    $('modelFile').textContent = fittedRecord?.file || 'outfit_br_female.glb';
    $('downloadModelLabel').textContent = 'Download fitted outfit GLB';
    $('downloadOutfitLabel').textContent = 'Download standalone kit GLB';
  } else {
    $('outfitPieceCount').textContent = `${activeOutfitPieces} PCS`;
    $('selectedName').textContent = standaloneRecord?.label || 'Battle Royale Outfit · Standalone Kit';
    $('selectedDescription').textContent = standaloneRecord?.description || 'Standalone low-poly modular Outfit_BR kit (no body, static pieces).';
    $('vertexCount').textContent = Number(activeOutfitVertices).toLocaleString();
    $('jointCount').textContent = '0 · Static';
    $('mapCount').textContent = '0 · PBR';
    $('viewportLabel').textContent = 'OUTFIT_BR · STANDALONE KIT';
    $('modelFile').textContent = standaloneRecord?.file || 'outfit_battle_royale.glb';
    $('downloadModelLabel').textContent = 'Download standalone outfit GLB';
    $('downloadOutfitLabel').textContent = 'Download fitted outfit GLB';
  }
}

async function syncOutfitVisibility() {
  if (outfitMode === 'standalone') {
    if (activeModel) activeModel.visible = false;
    try {
      const standalone = await ensureStandaloneOutfitLoaded();
      if (outfitMode !== 'standalone') return;
      standalone.visible = true;
      standalone.traverse(node => {
        if (node.isMesh) {
          node.visible = enabledGroups.has(getMeshPieceGroup(node));
        }
      });
      $('motionStatus').textContent = 'Viewing standalone Outfit_BR kit (unrigged). Switch to Equipped or Outfit Rig to animate.';
    } catch (error) {
      console.error('Standalone outfit load failed:', error);
    }
    updateSpecsAndLabels();
    return;
  }

  if (standaloneOutfitModel) standaloneOutfitModel.visible = false;
  if (activeModel) {
    activeModel.visible = true;
    const showBody = outfitMode !== 'outfit-only';
    for (const mesh of activeHeroMeshes) {
      mesh.visible = showBody;
    }
    if (attachedOutfitGroup) {
      const showOutfit = outfitMode === 'equipped' || outfitMode === 'outfit-only';
      attachedOutfitGroup.visible = showOutfit;
      attachedOutfitGroup.traverse(node => {
        if (node.isMesh) {
          node.visible = showOutfit && enabledGroups.has(getMeshPieceGroup(node));
        }
      });
    }
  }
  updateSpecsAndLabels();
}

function setSelected(id) {
  const record = models.get(id);
  if (!record || id === activeId) return;
  activeId = id;
  const currentToken = ++loadToken;
  motionRequest++;
  if (mixer) {
    mixer.stopAllAction();
    if (activeModel) mixer.uncacheRoot(activeModel);
  }
  mixer = null;
  activeAction = null;
  bindPose = null;
  activeHeroMeshes = [];
  attachedOutfitGroup = null;
  $('motionPlay').disabled = true;
  $('motionStop').disabled = true;
  $('motionSeek').disabled = true;
  $('motionPlay').innerHTML = '▶ <span>Play</span>';
  $('errorBanner').classList.add('hidden');
  $('loading').classList.remove('done');
  $('loading').querySelector('span:last-child').textContent = 'Loading character…';
  $('downloadModel').disabled = true;
  $('downloadOutfit').disabled = true;
  if (activeModel) {
    scene.remove(activeModel);
    disposeModel(activeModel);
    activeModel = null;
  }
  document.querySelectorAll('.hero-option').forEach(button => {
    const selected = button.dataset.model === id;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
  updateSpecsAndLabels();

  loader.load(assetUrl(record.file), async gltf => {
    if (id !== activeId || currentToken !== loadToken) {
      disposeModel(gltf.scene);
      return;
    }
    activeModel = gltf.scene;
    activeHeroMeshes = [];
    activeModel.traverse(node => {
      if (node.isMesh) {
        activeHeroMeshes.push(node);
        node.castShadow = true;
        node.receiveShadow = true;
        if (node.isSkinnedMesh) node.frustumCulled = false;
        if (node.material) {
          node.material.side = THREE.DoubleSide;
          node.material.needsUpdate = true;
        }
      }
    });
    frameCharacter(activeModel);
    scene.add(activeModel);
    mixer = new THREE.AnimationMixer(activeModel);
    mixer.addEventListener('finished', event => {
      if (event.action === activeAction) {
        activeAction = null;
        $('motionPlay').innerHTML = '▶ <span>Replay</span>';
        $('motionStop').disabled = true;
        $('motionStatus').textContent = 'Motion finished.';
      }
    });
    captureBindPose();

    try {
      attachedOutfitGroup = await attachFittedOutfitToHero(activeModel, id, currentToken);
    } catch (outfitErr) {
      console.warn('Could not attach Battle Royale outfit:', outfitErr);
    }
    if (id !== activeId || currentToken !== loadToken) return;

    await syncOutfitVisibility();
    $('motionPlay').disabled = !motions.length;
    $('downloadModel').disabled = false;
    $('downloadOutfit').disabled = false;
    $('loading').classList.add('done');
    if (selectedMotionId && outfitMode !== 'standalone') playMotion(selectedMotionId);
  }, undefined, error => {
    console.error('Character model load failed:', error);
    if (id !== activeId) return;
    $('loading').classList.add('done');
    $('errorBanner').classList.remove('hidden');
    $('downloadModel').disabled = true;
  });
}

function resetCamera() {
  if (!activeModel && !standaloneOutfitModel) return;
  const targetY = controls.target.y;
  camera.position.set(frameSize * 0.15, frameSize * 0.64, Math.max(frameSize * 2.45, 3.8));
  controls.target.set(0, targetY, 0);
  controls.update();
}

function updateMotionSelection() {
  document.querySelectorAll('.motion-choice').forEach(button => {
    const selected = button.dataset.motionId === selectedMotionId;
    button.setAttribute('aria-pressed', String(selected));
    button.classList.toggle('selected', selected);
  });
}

function populateMotionLibrary() {
  const library = $('motionLibrary');
  library.replaceChildren();
  library.setAttribute('aria-busy', 'false');
  if (!motions.length) {
    const empty = document.createElement('p');
    empty.className = 'motion-library-loading';
    empty.textContent = 'No source motions found.';
    library.append(empty);
    $('motionCount').textContent = 'Motion library unavailable';
    $('motionStatus').textContent = 'The source FBX motion manifest could not be loaded.';
    $('motionStatus').classList.add('error');
    $('motionPlay').disabled = true;
    return;
  }

  const idle = motions.find(motion => motion.file.toLowerCase() === 'idle.fbx') || motions[0];
  selectedMotionId = idle.id;
  const preferredCategories = ['Movement', 'Stance', 'Combat', 'Special'];
  const categories = [
    ...preferredCategories.filter(category => motions.some(motion => motion.category === category)),
    ...new Set(motions.map(motion => motion.category).filter(category => !preferredCategories.includes(category)))
  ];
  for (const category of categories) {
    const categoryMotions = motions.filter(motion => motion.category === category);
    const section = document.createElement('section');
    section.className = 'motion-category';
    const heading = document.createElement('h3');
    heading.className = 'motion-category-heading';
    heading.id = `motion-category-${category.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
    const title = document.createElement('span');
    title.className = 'motion-category-title';
    title.textContent = category;
    const count = document.createElement('span');
    count.className = 'motion-category-count';
    count.textContent = `${categoryMotions.length} motions`;
    heading.append(title, count);
    const buttonGroup = document.createElement('div');
    buttonGroup.className = 'motion-button-grid';
    buttonGroup.setAttribute('role', 'group');
    buttonGroup.setAttribute('aria-labelledby', heading.id);

    for (const motion of categoryMotions) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'motion-choice';
      button.dataset.motionId = motion.id;
      button.setAttribute('aria-pressed', String(motion.id === selectedMotionId));
      button.setAttribute('aria-label', `Play ${motion.label}`);
      button.title = motion.label;
      const label = document.createElement('span');
      label.className = 'motion-choice-label';
      label.textContent = motion.label;
      const icon = document.createElement('span');
      icon.className = 'motion-choice-icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = '▶';
      button.append(label, icon);
      buttonGroup.append(button);
    }
    section.append(heading, buttonGroup);
    library.append(section);
  }
  $('motionCount').textContent = `${motions.length} source clips · 65-joint rig`;
  $('motionStatus').textContent = 'Choose a motion button to play it. Idle starts automatically on the outfitted character.';
  $('motionStatus').classList.remove('error');
  updateMotionSelection();
}

function motionLoops(record) {
  return !/(death|dying|dive roll|to stop|jump up|jump down|reload|firing|hit reaction|grab|toss grenade|turn 90|turning right)/i.test(record.label);
}

async function getRetargetedMotion(record, targetModel, targetBindPose, targetModelId) {
  const cacheKey = `${targetModelId}:${record.id}`;
  if (motionCache.has(cacheKey)) return motionCache.get(cacheKey);
  const response = await fetch(motionUrl(record.file));
  if (!response.ok) throw new Error(`Could not load ${record.file} (${response.status}).`);
  const buffer = await response.arrayBuffer();
  if (activeModel !== targetModel || bindPose !== targetBindPose || activeId !== targetModelId) throw new Error('Character changed while this motion was loading.');
  const fbxLoader = new FBXLoader();
  let source;
  try {
    try {
      source = fbxLoader.parse(buffer, '');
    } catch (firstError) {
      // Two source FBX 7.7 files have one surplus footer-padding byte that trips
      // Three.js's footer-size heuristic; dropping that byte leaves their motion intact.
      source = fbxLoader.parse(buffer.slice(0, -1), '');
    }
    if (!source.animations?.length) throw new Error(`${record.file} contains no animation clip.`);
    const clip = retargetMixamoClip(THREE, source, targetModel, targetBindPose, source.animations[0]);
    clip.name = record.label;
    motionCache.set(cacheKey, clip);
    return clip;
  } finally {
    if (source) disposeModel(source);
  }
}

async function playMotion(id) {
  const record = motionById.get(id);
  if (!record) return;
  selectedMotionId = id;
  updateMotionSelection();
  if (outfitMode === 'standalone') {
    outfitMode = 'equipped';
    await syncOutfitVisibility();
  }
  if (!activeModel || !mixer) {
    $('motionStatus').textContent = `${record.label} selected · it will play when the character finishes loading.`;
    return;
  }
  const request = ++motionRequest;
  const targetModel = activeModel;
  const targetBindPose = bindPose;
  const targetModelId = activeId;
  mixer.stopAllAction();
  activeAction = null;
  restoreBindPose();
  $('motionPlay').disabled = true;
  $('motionStop').disabled = true;
  $('motionSeek').disabled = true;
  $('motionStatus').classList.remove('error');
  $('motionStatus').textContent = `Loading and retargeting “${record.label}”…`;
  try {
    const clip = await getRetargetedMotion(record, targetModel, targetBindPose, targetModelId);
    if (request !== motionRequest || activeModel !== targetModel || bindPose !== targetBindPose || activeId !== targetModelId || !mixer) return;
    activeAction = mixer.clipAction(clip);
    const looping = motionLoops(record);
    activeAction.setLoop(looping ? THREE.LoopRepeat : THREE.LoopOnce, looping ? Infinity : 1);
    activeAction.clampWhenFinished = !looping;
    activeAction.timeScale = Number($('motionSpeed').value) || 1;
    activeAction.reset().play();
    $('motionPlay').disabled = false;
    $('motionStop').disabled = false;
    $('motionSeek').disabled = false;
    $('motionPlay').innerHTML = 'Ⅱ <span>Pause</span>';
    $('motionStatus').textContent = `${record.label} · ${clip.tracks.length} retargeted bone tracks · ${formatTime(clip.duration)}${looping ? ' · looping' : ' · one-shot'}`;
    updateMotionTimeline();
  } catch (error) {
    if (request !== motionRequest) return;
    $('motionPlay').disabled = !activeModel;
    $('motionStop').disabled = true;
    $('motionSeek').disabled = true;
    $('motionStatus').textContent = error.message || `Could not play ${record.label}.`;
    $('motionStatus').classList.add('error');
  }
}

function stopMotion() {
  motionRequest++;
  if (mixer) mixer.stopAllAction();
  activeAction = null;
  restoreBindPose();
  $('motionPlay').innerHTML = '▶ <span>Play</span>';
  $('motionPlay').disabled = !activeModel || !motions.length;
  $('motionStop').disabled = true;
  $('motionSeek').disabled = true;
  $('motionSeek').value = '0';
  $('motionTime').textContent = '0:00 / 0:00';
  $('motionStatus').textContent = 'Stopped · character returned to its source bind pose.';
}

function triggerFileDownload(href, filename, revokeAfter = false) {
  const link = document.createElement('a');
  link.href = href;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  if (revokeAfter) setTimeout(() => URL.revokeObjectURL(href), 5000);
}

async function handlePrimaryDownload() {
  const record = models.get(activeId);
  if (!record) return;
  if (outfitMode === 'standalone') {
    triggerFileDownload(outfitUrl('outfit_battle_royale.glb'), 'outfit_battle_royale.glb');
    return;
  }
  if (outfitMode === 'outfit-only') {
    const outFile = `${outfitIdForHero(activeId)}.glb`;
    triggerFileDownload(outfitUrl(outFile), outFile);
    return;
  }
  if (outfitMode === 'none' || enabledGroups.size === 0) {
    triggerFileDownload(assetUrl(record.file), record.file);
    return;
  }

  // Equipped mode: pack character + active Battle Royale outfit pieces into a single self-contained GLB
  const button = $('downloadModel');
  const prevText = $('downloadModelLabel').textContent;
  button.disabled = true;
  $('downloadModelLabel').textContent = 'Packing outfitted GLB…';
  try {
    const [charBuf, outBuf] = await Promise.all([
      fetchCharacterBuffer(activeId),
      fetchOutfitBuffer(outfitIdForHero(activeId)),
    ]);
    const combined = combineCharacterAndOutfitGlb(charBuf, outBuf, enabledGroups);
    const blob = new Blob([combined], { type: 'model/gltf-binary' });
    const url = URL.createObjectURL(blob);
    triggerFileDownload(url, `${activeId}_battle_royale.glb`, true);
  } catch (error) {
    console.error('Combined GLB export failed:', error);
    triggerFileDownload(assetUrl(record.file), record.file);
  } finally {
    button.disabled = false;
    $('downloadModelLabel').textContent = prevText;
    updateSpecsAndLabels();
  }
}

function handleOutfitOnlyDownload() {
  if (outfitMode === 'outfit-only') {
    triggerFileDownload(outfitUrl('outfit_battle_royale.glb'), 'outfit_battle_royale.glb');
    return;
  }
  const outFile = `${outfitIdForHero(activeId || 'superhero_female_dark')}.glb`;
  triggerFileDownload(outfitUrl(outFile), outFile);
}

populateMotionLibrary();
document.querySelectorAll('.hero-option').forEach(button => {
  button.addEventListener('click', () => setSelected(button.dataset.model));
});
$('outfitModes').addEventListener('click', async event => {
  const btn = event.target.closest('button[data-outfit-mode]');
  if (!btn) return;
  const prevMode = outfitMode;
  outfitMode = btn.dataset.outfitMode;
  await syncOutfitVisibility();
  if (prevMode === 'standalone' && outfitMode !== 'standalone' && selectedMotionId && !activeAction) {
    playMotion(selectedMotionId);
  }
});
$('outfitGroups').addEventListener('click', async event => {
  const pill = event.target.closest('button[data-outfit-group]');
  if (!pill || pill.disabled) return;
  const grp = pill.dataset.outfitGroup;
  if (enabledGroups.has(grp)) enabledGroups.delete(grp);
  else enabledGroups.add(grp);
  await syncOutfitVisibility();
});
$('motionLibrary').addEventListener('click', event => {
  const button = event.target.closest('button[data-motion-id]');
  if (!button || !event.currentTarget.contains(button)) return;
  playMotion(button.dataset.motionId);
});
$('motionPlay').addEventListener('click', () => {
  if (!activeModel) return;
  if (activeAction?.paused) {
    activeAction.paused = false;
    $('motionPlay').innerHTML = 'Ⅱ <span>Pause</span>';
    $('motionStatus').textContent = `Playing ${motionById.get(selectedMotionId)?.label || 'motion'}.`;
  } else if (activeAction?.isRunning()) {
    activeAction.paused = true;
    $('motionPlay').innerHTML = '▶ <span>Resume</span>';
    $('motionStatus').textContent = 'Motion paused.';
  } else {
    playMotion(selectedMotionId);
  }
});
$('motionStop').addEventListener('click', stopMotion);
$('motionSpeed').addEventListener('change', event => {
  if (activeAction) activeAction.timeScale = Number(event.currentTarget.value) || 1;
});
$('motionSeek').addEventListener('input', event => {
  if (!activeAction) return;
  activeAction.paused = true;
  activeAction.time = (Number(event.currentTarget.value) / 1000) * (activeAction.getClip().duration || 0);
  mixer.update(0);
  $('motionPlay').innerHTML = '▶ <span>Resume</span>';
  updateMotionTimeline();
});
$('downloadModel').addEventListener('click', handlePrimaryDownload);
$('downloadOutfit').addEventListener('click', handleOutfitOnlyDownload);
$('resetView').addEventListener('click', resetCamera);
$('toggleTurntable').addEventListener('click', event => {
  autoRotate = !autoRotate;
  controls.autoRotate = autoRotate;
  const button = event.currentTarget;
  button.classList.toggle('active', autoRotate);
  button.setAttribute('aria-pressed', String(autoRotate));
});
$('fullscreen').addEventListener('click', async () => {
  const wrapper = $('viewport-wrap');
  try {
    if (!document.fullscreenElement) await wrapper.requestFullscreen();
    else await document.exitFullscreen();
  } catch (error) { console.warn('Fullscreen is unavailable:', error); }
});

document.querySelectorAll('.hero-option').forEach(button => {
  const record = models.get(button.dataset.model);
  if (!record) button.disabled = true;
});
init();
const initial = document.querySelector('.hero-option.active')?.dataset.model || manifest.models[0]?.id;
if (initial) setSelected(initial);
