/**
 * Record a walkthrough of the whole product.
 *
 * Drives a real browser against the running services and captures video, so
 * what lands on screen is the actual application answering actual questions,
 * not a storyboard. Every number that appears was computed by the service
 * during the take.
 *
 * The pacing matters more than it looks. Assistant answers need time to stream
 * and the map needs time to fly, so each beat waits on a condition where one
 * exists and on a generous timeout where it does not. A demo that races ahead
 * of its own answers is worse than no demo.
 *
 *   node scripts/record_demo.mjs [--out docs/video] [--fast]
 */
import { chromium } from 'playwright';
import { mkdir, readdir, rename, rm } from 'node:fs/promises';
import path from 'node:path';

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
};
const FAST = args.includes('--fast');
const OUT = flag('out', 'docs/video');
const URL = flag('url', 'http://localhost:5173');
const API = flag('api', 'http://localhost:8000');

const WIDTH = 1600;
const HEIGHT = 900;

/** Scale every pause together, so the whole take can be rehearsed quickly. */
const beat = (ms) => Math.round(ms * (FAST ? 0.35 : 1));

async function main() {
  await rm(OUT, { recursive: true, force: true });
  await mkdir(OUT, { recursive: true });

  // start from a known moment so the take is reproducible: a weekday morning
  // when the commute is visibly under way
  await fetch(`${API}/api/clock?weekday=tuesday&hour=8&minute=10`, { method: 'POST' }).catch(
    () => undefined,
  );
  await fetch(`${API}/api/control?action=speed&value=8`, { method: 'POST' }).catch(() => undefined);
  await fetch(`${API}/api/control?action=play`, { method: 'POST' }).catch(() => undefined);

  const browser = await chromium.launch({
    args: ['--use-gl=angle', '--enable-unsafe-swiftshader', '--hide-scrollbars'],
  });
  const context = await browser.newContext({
    viewport: { width: WIDTH, height: HEIGHT },
    recordVideo: { dir: OUT, size: { width: WIDTH, height: HEIGHT } },
    // a warm cache replays whichever bundle was built before the last fix
    bypassCSP: true,
  });
  await context.clearCookies();
  const page = await context.newPage();

  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e).slice(0, 160)));

  const log = (msg) => console.log(`  ${msg}`);

  // ---- helpers ----------------------------------------------------------

  const clickText = async (text, within) =>
    page.evaluate(
      ({ text, within }) => {
        const scope = within ? document.querySelector(within) ?? document : document;
        const button = [...scope.querySelectorAll('button')].find((b) =>
          (b.textContent || '').includes(text),
        );
        if (button) button.click();
        return Boolean(button);
      },
      { text, within },
    );

  const setView = (center, zoom) =>
    page.evaluate(
      ({ center, zoom }) => window.__setView && window.__setView(center, zoom),
      { center, zoom },
    );

  /** Wait until the assistant stops streaming, or until patience runs out. */
  const waitForAnswer = async (timeout = 150_000) => {
    const started = Date.now();
    let stableFor = 0;
    let previous = '';
    while (Date.now() - started < timeout) {
      await page.waitForTimeout(1500);
      const current = await page.evaluate(() => {
        const panels = [...document.querySelectorAll('div')];
        const dock = panels.find((d) => (d.textContent || '').includes('Ask about the city'));
        return dock ? (dock.textContent || '').slice(-4000) : '';
      });
      if (current === previous && current.length > 400) {
        stableFor += 1500;
        if (stableFor >= 4500) return true;
      } else {
        stableFor = 0;
      }
      previous = current;
    }
    return false;
  };

  /** Click a suggestion card while they are still on screen. */
  const askByCard = async (cardText) => {
    const found = await clickText(cardText);
    if (!found) {
      log(`could not find the card "${cardText}"`);
      return false;
    }
    await page.waitForTimeout(beat(1500));
    await waitForAnswer();
    await page.waitForTimeout(beat(3500)); // let the viewer read
    return true;
  };

  /**
   * Type a question. The suggestion cards vanish once a conversation has
   * started, so every beat after the first has to use the box, which is also
   * what a viewer would actually do.
   */
  const askByTyping = async (question) => {
    const box = await page.$('textarea');
    if (!box) {
      log('no question box found');
      return false;
    }
    // Filling the bulk and typing only the tail keeps the on-camera feel of
    // typing without spending thirty seconds per question, which is longer
    // than Playwright's default action timeout allows anyway.
    const tail = question.slice(-28);
    await box.click();
    await box.fill(question.slice(0, -28));
    await page.waitForTimeout(beat(400));
    await page.keyboard.type(tail, { delay: FAST ? 6 : 45 });
    await page.waitForTimeout(beat(900));
    await page.keyboard.press('Enter');
    await page.waitForTimeout(beat(1500));
    await waitForAnswer();
    await page.waitForTimeout(beat(3500));
    return true;
  };

  /**
   * Put the clock back near the present.
   *
   * The take runs six minutes at eight simulated minutes per second, so
   * without this the header drifts five days ahead of real time and every
   * later chapter is labelled with a date nobody asked about.
   */
  const reanchor = async (hour) => {
    await fetch(`${API}/api/clock?hour=${hour}&minute=15`, { method: 'POST' }).catch(
      () => undefined,
    );
    await page.waitForTimeout(beat(1200));
  };

  const openTrail = async () => {
    if (await clickText('How this was answered')) {
      await page.waitForTimeout(beat(4000));
      await clickText('How this was answered'); // collapse again
      await page.waitForTimeout(beat(800));
    }
  };

  // ---- the take ---------------------------------------------------------

  log('opening the application');
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.waitForSelector('canvas', { timeout: 45_000 });
  await page.waitForTimeout(beat(9000)); // basemap, agents and places settle

  log('1/9  the whole city at commute hour');
  await page.waitForTimeout(beat(5000));

  log('2/9  pushing in on downtown');
  // step the camera rather than cutting, so the dots visibly resolve into
  // people; at city zoom an agent is a single pixel and proves nothing
  await setView([-122.4041, 37.7879], 13.6);
  await page.waitForTimeout(beat(3500));
  await setView([-122.4058, 37.7867], 15.0);
  await page.waitForTimeout(beat(4000));

  log('3/9  street level: characters, vehicles and place signs');
  await setView([-122.4076, 37.7855], 16.4);
  await page.waitForTimeout(beat(6000));
  await setView([-122.4076, 37.7855], 17.4);
  await page.waitForTimeout(beat(9000)); // walk cycles are the point here
  await setView([-122.4096, 37.7841], 17.4); // drift along the street
  await page.waitForTimeout(beat(7000));

  await reanchor(17); // early evening, when complaints and activity overlap
  log('4/9  city data layers, close enough to read');
  await setView([-122.4139, 37.7840], 14.4);
  await page.waitForTimeout(beat(3000));
  for (const layer of ['311 complaints', 'Police incidents', 'Commercial vacancy']) {
    await clickText(layer);
    await page.waitForTimeout(beat(4000));
  }
  await setView([-122.4139, 37.7840], 15.4); // push in on the clustering
  await page.waitForTimeout(beat(4500));
  for (const layer of ['311 complaints', 'Police incidents', 'Commercial vacancy']) {
    await clickText(layer);
    await page.waitForTimeout(beat(600));
  }

  log('5/9  clicking a block for its report');
  await setView([-122.4192, 37.7599], 15.2);
  await page.waitForTimeout(beat(3000));
  await page.mouse.click(WIDTH / 2 + 40, HEIGHT / 2 - 30);
  await page.waitForTimeout(beat(8000));

  await reanchor(13);
  log('6/9  business: where to sign a lease');
  await clickText('Business');
  await page.waitForTimeout(beat(1500));
  await askByCard('Where should I sign a lease');
  await openTrail();

  log('7/9  planner: complaints, walkability and permits');
  await clickText('Planner');
  await page.waitForTimeout(beat(1500));
  await askByTyping(
    'I am a planner looking at the Tenderloin. What do residents complain about ' +
      'most, how walkable is it, and what is being built? Turn on the complaint ' +
      'and permit layers and show me.',
  );
  await openTrail();

  await reanchor(18); // just before doors, which is what the answer is about
  log('8/9  events: a sold-out game');
  await clickText('Events');
  await page.waitForTimeout(beat(1500));
  await askByTyping(
    'There is a sold-out Warriors game at Chase Center on Friday at 7pm. I run ' +
      'city operations. What should I prepare for, which blocks get worst, and ' +
      'how do people arrive and leave? Show the crowd on the map.',
  );
  await page.waitForTimeout(beat(3000));

  log('9/9  time travel, then back to the city');
  await clickText('Explore');
  await page.waitForTimeout(beat(1200));
  await clickText('San Francisco time');
  await page.waitForTimeout(beat(1800));
  await clickText('+7d');
  await page.waitForTimeout(beat(4000));
  await clickText('-7d');
  await page.waitForTimeout(beat(3000));
  await clickText('Back to now');
  await page.waitForTimeout(beat(3000));

  // finish on the city, then push back in so the last frame has life in it
  await setView([-122.4183, 37.7775], 12.4);
  await page.waitForTimeout(beat(5000));
  await setView([-122.4076, 37.7855], 16.0);
  await page.waitForTimeout(beat(6000));

  if (errors.length) {
    console.log('\n  page errors during the take:');
    for (const e of [...new Set(errors)].slice(0, 5)) console.log('   ', e);
  }

  await context.close(); // flushes the video file
  await browser.close();

  const files = await readdir(OUT);
  const video = files.find((f) => f.endsWith('.webm'));
  if (video) {
    const target = path.join(OUT, 'streetlight-demo.webm');
    await rename(path.join(OUT, video), target);
    console.log(`\nwrote ${target}`);
  } else {
    console.log('\nno video file was produced');
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
