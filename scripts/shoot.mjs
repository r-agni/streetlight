/**
 * Screenshot harness.
 *
 * Loads the running app in headless Chromium, waits for the map and the first
 * agent frames, then captures a few views. Console errors and failed requests
 * are reported, because a blank map usually means a network problem rather
 * than a rendering one.
 *
 *   node scripts/shoot.mjs [--url http://localhost:5173] [--out docs/shots]
 */
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
};

const URL = flag('url', 'http://localhost:5173');
const OUT = flag('out', 'docs/shots');
const WAIT_MS = Number(flag('wait', '9000'));

const VIEWS = [
  { name: '01-city', zoom: 12.4, center: [-122.4183, 37.7775], settle: 2500 },
  { name: '02-downtown', zoom: 14.2, center: [-122.4014, 37.7899], settle: 2200 },
  { name: '03-mission', zoom: 15.6, center: [-122.4192, 37.7599], settle: 2600 },
  { name: '04-street', zoom: 17.0, center: [-122.4076, 37.7855], settle: 2600 },
];

async function main() {
  await mkdir(OUT, { recursive: true });

  const browser = await chromium.launch({
    args: ['--use-gl=angle', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
  });
  const page = await browser.newPage({ viewport: { width: 1680, height: 1000 }, deviceScaleFactor: 2 });

  const errors = [];
  const failed = [];
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text().slice(0, 300));
  });
  page.on('pageerror', (e) => errors.push(`pageerror: ${String(e).slice(0, 300)}`));
  page.on('requestfailed', (r) => failed.push(`${r.failure()?.errorText} ${r.url().slice(0, 110)}`));

  // pin the clock so every capture shows the same moment of the week
  const API = flag('api', 'http://localhost:8000');
  const MINUTE = Number(flag('minute', String(1 * 1440 + 8 * 60 + 20))); // Tue 08:20
  try {
    await fetch(`${API}/api/control?action=seek&value=${MINUTE}`, { method: 'POST' });
    await fetch(`${API}/api/control?action=pause`, { method: 'POST' });
    console.log(`clock pinned to minute ${MINUTE} and paused`);
  } catch (err) {
    console.log('could not reach the simulation service:', String(err).slice(0, 120));
  }

  console.log(`opening ${URL}`);
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60_000 });

  // the map canvas appears only after the style resolves
  await page.waitForSelector('canvas', { timeout: 45_000 });
  console.log(`canvas present; letting ${WAIT_MS} ms of frames arrive`);
  await page.waitForTimeout(WAIT_MS);

  const report = await page.evaluate(() => {
    const canvases = [...document.querySelectorAll('canvas')].map((c) => ({
      w: c.width,
      h: c.height,
      cls: c.className || '(none)',
    }));
    const text = document.body.innerText.replace(/\s+/g, ' ').slice(0, 400);
    return { canvases, text };
  });
  console.log('canvases:', JSON.stringify(report.canvases));
  console.log('overlay text:', report.text);

  for (const view of VIEWS) {
    await page.evaluate(({ zoom, center }) => {
      // the map instance is not exported, so drive it through the DOM event
      const w = window;
      if (w.__setView) w.__setView(center, zoom);
    }, view);
    await page.waitForTimeout(view.settle);
    const file = path.join(OUT, `${view.name}.png`);
    await page.screenshot({ path: file });
    console.log(`wrote ${file}`);
  }

  if (errors.length) {
    console.log(`\n${errors.length} console error(s):`);
    for (const e of [...new Set(errors)].slice(0, 12)) console.log('  ', e);
  } else {
    console.log('\nno console errors');
  }
  if (failed.length) {
    console.log(`${failed.length} failed request(s):`);
    for (const f of [...new Set(failed)].slice(0, 10)) console.log('  ', f);
  }

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
