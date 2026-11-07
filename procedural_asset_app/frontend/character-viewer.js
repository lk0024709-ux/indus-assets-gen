import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
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
let renderer, scene, camera, controls, activeModel = null, activeId = '', frameSize = 1;
let autoRotate = true;
const host = $('viewport');
const loader = new GLTFLoader();

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
    if (controls) controls.update();
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

function setSelected(id) {
  const record = models.get(id);
  if (!record || id === activeId) return;
  activeId = id;
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
    $('downloadModel').disabled = false;
    $('loading').classList.add('done');
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

document.querySelectorAll('.hero-option').forEach(button => {
  button.addEventListener('click', () => setSelected(button.dataset.model));
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
