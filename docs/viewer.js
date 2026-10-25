const viewer = document.querySelector('#character');
const status = document.querySelector('#status');
const buttons = [...document.querySelectorAll('[data-animation]')];
const playback = document.querySelector('#playback');
const assets = {
  body: { name: 'Base Body', src: './models/characters/body_base_midpoly.glb', triangles: '15,408', bones: 20, animated: true },
  skeleton: { name: 'Skeleton', src: './models/characters/skeleton/skeleton_base_midpoly.glb', triangles: '24,816', bones: 151, animated: false },
};
let selected = 'skeleton';
let ready = false;

function updateDetails() {
  const asset = assets[selected];
  document.querySelector('.download').href = asset.src;
  document.querySelector('#facts').innerHTML = `<div><strong>${asset.triangles}</strong>triangles</div><div><strong>1.80 m</strong>height</div><div><strong>${asset.bones} bones</strong>articulated rig</div>`;
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
    status.textContent = 'Skeleton · Rest pose · 24,816 triangles · 375 rigid bone pieces';
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
    viewer.pause();
    disablePlayback();
    updateDetails();
    for (const b of document.querySelectorAll('[data-asset]')) b.setAttribute('aria-pressed', String(b === button));
    status.textContent = `Loading ${assets[selected].name}…`;
    viewer.alt = selected === 'skeleton' ? 'Stylized anatomical skeleton with individual ribs, vertebrae and phalanges' : 'Neutral stylized humanoid base body';
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
