import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { WEB_RECIPES, generateRecipeGlbInBrowser } from './web-recipes.js';

const $ = id => document.getElementById(id);
const select = $('recipeSelect'), form = $('paramsForm'), fields = $('paramFields');
let recipes = [], currentRecipe = null, currentParams = {}, currentUrl = null, currentFilename = 'generated.glb';
let renderer, scene, camera, controls, currentModel = null;
let useBrowserBuilder = false;
const blobCache = new Map();

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || ('Request failed (' + response.status + ')'));
  return data;
}

function setMessage(text, error = false) {
  $('message').textContent = text;
  $('message').classList.toggle('error', error);
}

function initViewer() {
  const host = $('viewport');
  scene = new THREE.Scene();
  scene.background = new THREE.Color('#10151f');
  camera = new THREE.PerspectiveCamera(42, host.clientWidth / host.clientHeight, 0.1, 100);
  camera.position.set(4, 3, 5);
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  host.prepend(renderer.domElement);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  pmrem.dispose();
  scene.add(new THREE.HemisphereLight(0xdce8ff, 0x41404a, 2));
  const key = new THREE.DirectionalLight(0xffedcf, 3);
  key.position.set(4, 7, 5);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x8baeff, 1.5);
  fill.position.set(-5, 3, -3);
  scene.add(fill);
  const grid = new THREE.GridHelper(12, 24, 0x3d4a5c, 0x263140);
  grid.position.y = -0.015;
  scene.add(grid);
  const ground = new THREE.Mesh(
    new THREE.CircleGeometry(6, 64),
    new THREE.MeshStandardMaterial({ color: 0x111722, roughness: 0.9 })
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.025;
  scene.add(ground);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.target.set(0, 0.7, 0);
  const resize = () => {
    const w = Math.max(host.clientWidth, 1), h = Math.max(host.clientHeight, 1);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
  };
  new ResizeObserver(resize).observe(host);
  resize();
  const animate = () => {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  };
  animate();
}

function frameModel(model) {
  const box = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  model.position.x -= center.x;
  model.position.z -= center.z;
  model.position.y -= box.min.y;
  const max = Math.max(size.x, size.y, size.z) || 1;
  const targetY = Math.max(size.y * 0.48, 0.25);
  camera.position.set(max * 1.6, targetY + max * 0.65, max * 2.0);
  camera.near = Math.max(0.01, max / 100);
  camera.far = max * 100;
  camera.updateProjectionMatrix();
  controls.target.set(0, targetY, 0);
  controls.update();
}

function showModelBuffer(arrayBuffer, statusLabel) {
  $('loader').classList.remove('hidden');
  $('emptyState').classList.add('hidden');
  new GLTFLoader().parse(arrayBuffer.slice(0), '', gltf => {
    if (currentModel) scene.remove(currentModel);
    currentModel = gltf.scene;
    scene.add(currentModel);
    frameModel(currentModel);
    $('loader').classList.add('hidden');
    $('assetStatus').textContent = statusLabel || 'Model loaded successfully';
    $('download').disabled = false;
  }, error => {
    console.error(error);
    $('loader').classList.add('hidden');
    $('emptyState').classList.remove('hidden');
    setMessage('Could not load the exported GLB in the viewport.', true);
  });
}

function showModelUrl(url) {
  $('loader').classList.remove('hidden');
  $('emptyState').classList.add('hidden');
  const resolved = new URL(url.replace(/^\//, './'), document.baseURI).href;
  new GLTFLoader().load(resolved + (resolved.includes('?') ? '&' : '?') + 't=' + Date.now(), gltf => {
    if (currentModel) scene.remove(currentModel);
    currentModel = gltf.scene;
    scene.add(currentModel);
    frameModel(currentModel);
    $('loader').classList.add('hidden');
    $('assetStatus').textContent = 'Model loaded successfully';
    $('download').disabled = false;
  }, undefined, error => {
    console.error(error);
    $('loader').classList.add('hidden');
    $('emptyState').classList.remove('hidden');
    setMessage('Could not load the exported GLB in the viewport.', true);
  });
}

function buildFields(recipe) {
  fields.innerHTML = '';
  currentRecipe = recipe;
  currentParams = {};
  $('recipeDescription').textContent = recipe.description;
  $('viewerLabel').textContent = `3D VIEWPORT · ${recipe.name.toUpperCase()}`;
  for (const [key, spec] of Object.entries(recipe.parameters)) {
    let value = spec.default;
    if (spec.type === 'enum' && key === 'leg_count') value = String(value);
    currentParams[key] = value;
    const wrap = document.createElement('div');
    wrap.className = 'parameter';
    const head = document.createElement('div');
    head.className = 'parameter-head';
    const label = document.createElement('label');
    label.htmlFor = 'p_' + key;
    label.textContent = spec.label;
    const output = document.createElement('output');
    output.id = 'out_' + key;
    output.textContent = String(value);
    head.append(label, output);
    wrap.append(head);
    let input;
    if (spec.type === 'enum') {
      input = document.createElement('select');
      for (const option of spec.options) {
        const o = document.createElement('option');
        o.value = option;
        o.textContent = option;
        input.append(o);
      }
      input.value = String(value);
    } else if (spec.type === 'bool') {
      input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = Boolean(value);
    } else if (spec.type === 'color') {
      input = document.createElement('input');
      input.type = 'color';
      input.value = value;
    } else {
      input = document.createElement('input');
      input.type = 'range';
      input.min = spec.min;
      input.max = spec.max;
      input.step = spec.step || 1;
      input.value = value;
    }
    input.id = 'p_' + key;
    input.addEventListener('input', () => {
      let v = spec.type === 'bool' ? input.checked : input.value;
      if (spec.type === 'int') v = parseInt(v, 10);
      if (spec.type === 'float') v = parseFloat(v);
      currentParams[key] = v;
      output.textContent = String(v);
    });
    wrap.append(input);
    fields.append(wrap);
  }
}

async function generateCurrentAsset() {
  if (!currentRecipe) return;
  $('download').disabled = true;
  $('loader').classList.remove('hidden');
  $('emptyState').classList.add('hidden');
  $('assetStatus').textContent = 'Generating…';

  if (!useBrowserBuilder) {
    setMessage('Building your 3D asset…');
    try {
      const result = await api('./api/generate', {
        method: 'POST',
        body: JSON.stringify({ recipe: currentRecipe.id, params: currentParams }),
      });
      currentUrl = new URL(result.url.replace(/^\//, './'), document.baseURI).href;
      currentFilename = result.url.split('/').pop();
      $('cacheKey').textContent = result.hash;
      $('generationMode').textContent = result.cached ? 'Cached output' : 'Server build';
      setMessage(result.cached ? 'Loaded cached asset.' : 'Asset generated and exported as GLB.');
      showModelUrl(result.url);
      return;
    } catch (err) {
      // Automatically fall back to browser GLB builder if backend lacks Blender or is unreachable
      useBrowserBuilder = true;
      $('healthDot').className = 'ok';
      $('healthText').textContent = 'Web GLB Builder';
      $('generationBackendNote').textContent = 'In-browser glTF 2.0 binary builder';
    }
  }

  try {
    const built = generateRecipeGlbInBrowser(currentRecipe.id, currentParams);
    const cacheKey = `${currentRecipe.id}:${built.hash}`;
    const cached = blobCache.has(cacheKey);
    let entry = blobCache.get(cacheKey);
    if (!entry) {
      const blob = new Blob([built.glb], { type: 'model/gltf-binary' });
      entry = { url: URL.createObjectURL(blob), buffer: built.glb.buffer.slice(built.glb.byteOffset, built.glb.byteOffset + built.glb.byteLength), filename: built.filename };
      blobCache.set(cacheKey, entry);
    }
    currentUrl = entry.url;
    currentFilename = entry.filename;
    $('cacheKey').textContent = built.hash;
    $('generationMode').textContent = cached ? 'Cached (Web)' : 'Browser GLB build';
    setMessage(cached ? `Loaded cached ${currentRecipe.name} GLB.` : `Built ${currentRecipe.name} (${(built.glb.byteLength / 1024).toFixed(1)} KB GLB) in browser.`);
    showModelBuffer(entry.buffer, `${currentRecipe.name} ready · ${(built.glb.byteLength / 1024).toFixed(1)} KB`);
  } catch (err) {
    $('loader').classList.add('hidden');
    $('emptyState').classList.remove('hidden');
    $('assetStatus').textContent = 'Generation failed';
    setMessage(err.message, true);
  }
}

select.addEventListener('change', () => {
  buildFields(recipes.find(r => r.id === select.value));
  generateCurrentAsset();
});
form.addEventListener('submit', event => {
  event.preventDefault();
  generateCurrentAsset();
});
$('randomize').addEventListener('click', () => {
  for (const [key, spec] of Object.entries(currentRecipe.parameters)) {
    const input = $('p_' + key);
    let v;
    if (spec.type === 'enum') v = spec.options[Math.floor(Math.random() * spec.options.length)];
    else if (spec.type === 'bool') v = Math.random() > 0.25;
    else if (spec.type === 'color') v = '#' + Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, '0');
    else {
      const step = spec.step || 1;
      const count = Math.floor((spec.max - spec.min) / step);
      v = spec.min + Math.floor(Math.random() * (count + 1)) * step;
      v = spec.type === 'int' ? Math.round(v) : Number(v.toFixed(3));
    }
    if (spec.type === 'bool') input.checked = v;
    else input.value = String(v);
    currentParams[key] = v;
    $('out_' + key).textContent = String(v);
  }
  generateCurrentAsset();
});
$('download').addEventListener('click', () => {
  if (!currentUrl) return;
  const a = document.createElement('a');
  a.href = currentUrl;
  a.download = currentFilename || 'generated_asset.glb';
  document.body.append(a);
  a.click();
  a.remove();
});
$('resetView').addEventListener('click', () => {
  if (currentModel) frameModel(currentModel);
  else {
    camera.position.set(4, 3, 5);
    controls.target.set(0, 0.7, 0);
    controls.update();
  }
});

async function start() {
  initViewer();
  try {
    const h = await api('./api/health');
    const serverRecipes = await api('./api/recipes');
    recipes = serverRecipes;
    useBrowserBuilder = !h.blender_configured;
    $('healthDot').className = 'ok';
    $('healthText').textContent = h.blender_configured ? 'Blender / API ready' : 'Web GLB Builder';
    $('generationBackendNote').textContent = h.blender_configured ? 'Server / headless worker' : 'In-browser glTF 2.0 binary builder';
  } catch {
    recipes = WEB_RECIPES;
    useBrowserBuilder = true;
    $('healthDot').className = 'ok';
    $('healthText').textContent = 'Web GLB Builder';
    $('generationBackendNote').textContent = 'In-browser glTF 2.0 binary builder';
  }
  select.innerHTML = '';
  for (const r of recipes) {
    const o = document.createElement('option');
    o.value = r.id;
    o.textContent = r.name;
    select.append(o);
  }
  buildFields(recipes[0]);
  await generateCurrentAsset();
}
start();
