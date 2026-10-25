import {loadRig, clearRig} from './rig-viewer.js';
const viewer = document.querySelector('#character');
const status = document.querySelector('#status');
const buttons = [...document.querySelectorAll('[data-animation]')];
const playback = document.querySelector('#playback');
let rigRequest = new AbortController();
const assets = {
  female: {name:'Athletic Female', src:'./models/characters/body_base_female_midpoly.glb', triangles:'24,954', bones:27, height:'1.80 m', animated:false, pose:'T-pose', detail:'Custom hierarchy · no motion clips'},
  body: { name: 'Base Body', src: './models/characters/body_base_midpoly.glb', triangles: '15,408', bones: 20, height: '1.80 m', animated: true },
  skeleton: { name: 'Skeleton', src: './models/characters/skeleton_base_midpoly.glb', triangles: '24,970', bones: 65, height: '1.84 m', animated: false },
};
let selected = 'female';
let ready = false;

function updateDetails() {
  const asset = assets[selected];
  document.querySelector('.download').href = asset.src;
  document.querySelector('#facts').innerHTML = `<div><strong>${asset.triangles}</strong>triangles</div><div><strong>${asset.height}</strong>height</div><div><strong>${asset.bones} bones</strong>articulated rig</div>`;
}
function disablePlayback() {
  for (const button of buttons) { button.disabled = true; button.setAttribute('aria-pressed', 'false'); }
  playback.disabled = true;
  playback.textContent = 'Play';
}
function selectAnimation(name) {
  if (!ready || !assets[selected].animated || !viewer.availableAnimations.includes(name)) return;
  viewer.animationName = name;
  viewer.currentTime = 0;
  viewer.play();
  for (const button of buttons) button.setAttribute('aria-pressed', String(button.dataset.animation === name));
  playback.textContent = 'Pause';
  status.textContent = `${assets[selected].name} · ${name} playing · ${assets[selected].triangles} triangles`;
}
function onLoad() {
  const asset = assets[selected];
  // Ignore a superseded load event when switching assets rapidly.
  if (!viewer.loaded || viewer.src !== asset.src) return;
  ready = true;
  viewer.cameraOrbit = selected === 'female' ? '0deg 90deg 5.5m' : '0deg 90deg 4.5m';
  viewer.jumpCameraToGoal();
  if (asset.animated) {
    const missing = ['Idle', 'Walk'].filter(name => !viewer.availableAnimations.includes(name));
    if (missing.length) {
      disablePlayback();
      status.textContent = `Asset loaded, but clips are missing: ${missing.join(', ')}`;
      return;
    }
    for (const button of buttons) button.disabled = false;
    playback.disabled = false;
    selectAnimation('Idle');
  } else {
    viewer.pause();
    disablePlayback();
    status.textContent = selected === 'female' ? 'Athletic Female · T-pose · 24,954 triangles · 27 named joints' : 'Skeleton · A-pose · 24,970 triangles · 65 deform joints · No animation clips';
  }
}
viewer.addEventListener('load', onLoad);
viewer.addEventListener('error', () => {
  ready = false;
  status.textContent = `Unable to load ${assets[selected].name}. Reload or download the GLB directly.`;
  disablePlayback();
});
for (const button of document.querySelectorAll('[data-asset]')) {
  button.addEventListener('click', () => {
    if (button.dataset.asset === selected) return;
    selected = button.dataset.asset;
    ready = false;
    rigRequest.abort();
    rigRequest = new AbortController();
    clearRig();
    loadRig(viewer, assets[selected].src, rigRequest.signal, selected === 'female').catch(rigError);
    viewer.pause();
    disablePlayback();
    updateDetails();
    for (const b of document.querySelectorAll('[data-asset]')) b.setAttribute('aria-pressed', String(b === button));
    status.textContent = `Loading ${assets[selected].name}…`;
    viewer.alt = selected === 'female' ? 'Athletic female in T-pose wearing black sports bra and shorts' : selected === 'skeleton' ? 'Stylized anatomical skeleton with individual ribs, vertebrae and phalanges' : 'Neutral stylized humanoid base body';
    viewer.src = assets[selected].src;
  });
}
for (const button of buttons) button.addEventListener('click', () => selectAnimation(button.dataset.animation));
playback.addEventListener('click', () => {
  if (!ready || !assets[selected].animated) return;
  if (viewer.paused) {
    viewer.play(); playback.textContent = 'Pause';
    status.textContent = `${assets[selected].name} · ${viewer.animationName} playing · ${assets[selected].triangles} triangles`;
  } else {
    viewer.pause(); playback.textContent = 'Play';
    status.textContent = `${assets[selected].name} · ${viewer.animationName} paused`;
  }
});
updateDetails();
disablePlayback();
if (viewer.loaded) onLoad();

function rigError(error) {
  if (error.name !== 'AbortError') document.querySelector('#rig-count').textContent = 'Hierarchy unavailable — reload to retry';
}
loadRig(viewer, assets[selected].src, rigRequest.signal, true).catch(rigError);
