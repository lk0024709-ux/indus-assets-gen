import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';
import { retargetMixamoClip } from './motion-retarget.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const $ = id => document.getElementById(id);
const modelDescriptions = {
  superhero_female_dark: 'Full-body superhero character with the original dark skin BaseColor, eye and hair maps, and the source rig.',
  superhero_female_light: 'Full-body superhero character with the alternate light skin BaseColor from the source texture set, plus the original eye, hair and rig assets.',
  superhero_male_dark: 'Full-body superhero character with the original male dark BaseColor, eye and hair maps, and the source rig.',
  superhero_male_light: 'Full-body superhero character with the alternate male light BaseColor from the source texture set, plus the original eye, hair and rig assets.'
};
const assetUrl = filename => new URL(`./assets/characters/${encodeURIComponent(filename)}`, document.baseURI).href;
const manifest = await fetch(assetUrl('characters.json')).then(response => {
  if (!response.ok) throw new Error('The character manifest could not be loaded.');
  return response.json();
});
const models = new Map(manifest.models.map(model => [model.id, model]));
const motionManifestResponse = await fetch(new URL('./assets/motion-manifest.json', document.baseURI)).catch(() => null);
const motionManifest = motionManifestResponse?.ok ? await motionManifestResponse.json() : { motions: [], count: 0 };
const motions = motionManifest.motions || [];
const motionById = new Map(motions.map(motion => [motion.id, motion]));
let renderer, scene, camera, controls, activeModel = null, activeId = '', frameSize = 1;
let mixer = null, activeAction = null, bindPose = null, selectedMotionId = '';
let motionRequest = 0;
const motionCache = new Map();
let autoRotate = true;
const host = $('viewport');
const loader = new GLTFLoader();
const motionUrl = filename => new URL(`./assets/motions/${encodeURIComponent(filename)}`, document.baseURI).href;
const clock = new THREE.Clock();

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
    if (mixer) mixer.update(delta);
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
function setSelected(id) {
  const record = models.get(id);
  if (!record || id === activeId) return;
  activeId = id;
  motionRequest++;
  if (mixer) {
    mixer.stopAllAction();
    if (activeModel) mixer.uncacheRoot(activeModel);
  }
  mixer = null;
  activeAction = null;
  bindPose = null;
  $('motionPlay').disabled = true;
  $('motionStop').disabled = true;
  $('motionSeek').disabled = true;
  $('motionPlay').innerHTML = '▶ <span>Play</span>';
  $('errorBanner').classList.add('hidden');
  $('loading').classList.remove('done');
  $('loading').querySelector('span:last-child').textContent = 'Loading character…';
  $('downloadModel').disabled = true;
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
  $('selectedName').textContent = record.label;
  $('selectedDescription').textContent = modelDescriptions[id] || 'Rigged full-body superhero character using repository source assets.';
  $('vertexCount').textContent = Number(record.vertices).toLocaleString();
  $('jointCount').textContent = String(record.joints || 65);
  $('mapCount').textContent = String(record.textures.length);
  $('viewportLabel').textContent = record.label.toUpperCase();
  $('modelFile').textContent = record.file;

  loader.load(assetUrl(record.file), gltf => {
    if (id !== activeId) {
      disposeModel(gltf.scene);
      return;
    }
    activeModel = gltf.scene;
    activeModel.traverse(node => {
      if (node.isMesh) {
        node.castShadow = true;
        node.receiveShadow = true;
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
    $('motionPlay').disabled = !motions.length;
    $('downloadModel').disabled = false;
    $('loading').classList.add('done');
    if (selectedMotionId) playMotion(selectedMotionId);
  }, undefined, error => {
    console.error('Character model load failed:', error);
    if (id !== activeId) return;
    $('loading').classList.add('done');
    $('errorBanner').classList.remove('hidden');
    $('downloadModel').disabled = true;
  });
}

function resetCamera() {
  if (!activeModel) return;
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
  $('motionStatus').textContent = 'Choose a motion button to play it. Idle starts automatically on the selected character.';
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

populateMotionLibrary();
document.querySelectorAll('.hero-option').forEach(button => {
  button.addEventListener('click', () => setSelected(button.dataset.model));
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
$('downloadModel').addEventListener('click', () => {
  const record = models.get(activeId);
  if (!record) return;
  const link = document.createElement('a');
  link.href = assetUrl(record.file);
  link.download = record.file;
  document.body.append(link);
  link.click();
  link.remove();
});
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
