const viewer = document.querySelector('#character');
const status = document.querySelector('#status');
const buttons = [...document.querySelectorAll('[data-animation]')];
const playback = document.querySelector('#playback');

function selectAnimation(name) {
  if (!viewer.availableAnimations.includes(name)) return;
  viewer.animationName = name;
  viewer.currentTime = 0;
  viewer.play();
  for (const button of buttons) button.setAttribute('aria-pressed', String(button.dataset.animation === name));
  playback.textContent = 'Pause';
  status.textContent = `Base Body · ${name} playing · 15,408 triangles`;
}
viewer.addEventListener('load', () => {
  const missing = ['Idle', 'Walk'].filter(name => !viewer.availableAnimations.includes(name));
  if (missing.length) {
    status.textContent = `Asset loaded, but animation clips are missing: ${missing.join(', ')}`;
    return;
  }
  for (const button of buttons) button.disabled = false;
  playback.disabled = false;
  selectAnimation('Idle');
});
viewer.addEventListener('error', () => {
  status.textContent = 'Unable to load the character. Reload the page or download the GLB directly.';
  for (const button of buttons) button.disabled = true;
  playback.disabled = true;
});
for (const button of buttons) button.addEventListener('click', () => selectAnimation(button.dataset.animation));
playback.addEventListener('click', () => {
  if (viewer.paused) {
    viewer.play();
    playback.textContent = 'Pause';
    status.textContent = `Base Body · ${viewer.animationName} playing · 15,408 triangles`;
  } else {
    viewer.pause();
    playback.textContent = 'Play';
    status.textContent = `Base Body · ${viewer.animationName} paused`;
  }
});
