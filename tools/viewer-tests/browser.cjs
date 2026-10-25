// Integration test against a real browser and the checked-in runtime bundle.
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const server = spawn('python3', ['-m', 'http.server', '8765', '--bind', '127.0.0.1', '--directory', path.join(root, 'docs')], { stdio: 'ignore' });
let browser;
(async () => {
  for (let n = 0; ; n++) {
    try { await fetch('http://127.0.0.1:8765/'); break; }
    catch (e) { if (n === 50) throw e; await new Promise(r => setTimeout(r, 100)); }
  }
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('response', r => { if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`); });
  await page.goto('http://127.0.0.1:8765/');
  await page.waitForFunction(() => document.querySelector('#status').textContent.includes('Idle playing'), null, { timeout: 60000 });
  assert.equal(await page.locator('.asset').count(), 1);
  const state = () => page.$eval('#character', m => ({ clips: m.availableAnimations, time: m.currentTime, paused: m.paused, name: m.animationName }));
  for (const name of ['Idle', 'Walk']) {
    await page.click(`[data-animation="${name}"]`);
    const before = await state();
    await page.waitForFunction(time => document.querySelector('#character').currentTime !== time,
      before.time, { timeout: 15000 });
    const after = await state();
    assert.equal(after.name, name);
    assert.equal(after.paused, false);
    assert.notEqual(before.time, after.time, `${name} must advance`);
    assert.deepEqual([...after.clips].sort(), ['Idle', 'Walk']);
    await page.waitForTimeout(2200);
    assert.equal((await state()).paused, false, `${name} must keep looping`);
  }
  await page.click('#playback');
  assert.equal((await state()).paused, true);
  await page.click('#playback');
  assert.equal((await state()).paused, false);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  assert.deepEqual(errors, []);
  console.log('PASS: model loading, Idle/Walk playback, looping, pause/resume, mobile layout, HTTP/browser errors');
})().catch(e => { console.error(e); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  server.kill();
});
