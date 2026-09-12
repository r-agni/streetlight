/**
 * Generate the character, vehicle and place sprite atlas.
 *
 * The style is deliberately Gather-Town-ish: chunky pixel art on a small
 * logical grid, scaled up with hard edges, four facing directions and a short
 * walk cycle. Characters carry real colour - skin, hair, clothing - because a
 * city drawn in one colour tells you nothing about who is in it, and because
 * telling a student from a commuter at a glance is the point of drawing
 * people rather than dots.
 *
 * Everything is drawn procedurally rather than sourced. Free pixel-art packs
 * exist, but they arrive in mismatched palettes and proportions; generating
 * them means one palette, one proportion system, and frame count as a
 * parameter instead of a redraw.
 *
 *   node scripts/make_sprites.mjs
 */
import { createCanvas } from '@napi-rs/canvas';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const OUT_DIR = path.join('apps', 'web', 'public', 'sprites');

const CELL = 64; // atlas cell in pixels
const UNIT = 3; // screen pixels per logical pixel
const GRID_W = 16; // logical character width
const GRID_H = 20; // logical character height
const FRAMES = 4; // frames in one walk cycle
const DIRECTIONS = ['down', 'up', 'left', 'right'];
const COLUMNS = 16;

/* ── palette ─────────────────────────────────────────────────────────── */

const SKIN = ['#f4cba4', '#e8ab7d', '#c58a5c', '#9c6440', '#6f4326'];
const HAIR = ['#241f1c', '#5b3a21', '#a8712f', '#d8c07a', '#8e3b2f', '#b8b8bd'];
const PANTS = ['#2f3b52', '#3e3e48', '#5c4a38', '#26303f'];
const SHOE = '#22222a';
const OUTLINE = 'rgba(20,20,28,0.55)';

/**
 * One persona per simulated segment, in the same order as the engine's
 * segment byte, so the sprite follows from the agent rather than from chance.
 */
const PERSONAS = [
  { id: 'office', shirt: '#2323e5', hair: 0, skin: 0, accessory: 'briefcase' },
  { id: 'tech', shirt: '#00a6c0', hair: 1, skin: 1, accessory: 'backpack' },
  { id: 'student', shirt: '#f5b301', hair: 2, skin: 2, accessory: 'backpack' },
  { id: 'service', shirt: '#00a878', hair: 0, skin: 3, accessory: 'apron' },
  { id: 'remote', shirt: '#8b3dff', hair: 3, skin: 0, accessory: 'none' },
  { id: 'retiree', shirt: '#b8b8bd', hair: 5, skin: 1, accessory: 'none' },
  { id: 'visitor', shirt: '#ff6a13', hair: 4, skin: 4, accessory: 'camera' },
  { id: 'resident', shirt: '#e8384f', hair: 1, skin: 2, accessory: 'none' },
];

/** Vehicles, drawn from directly above so they rotate correctly with heading. */
const VEHICLES = [
  { id: 'bus', body: '#e8384f', length: 17, width: 8, windows: 4 },
  { id: 'tram', body: '#8b3dff', length: 18, width: 7, windows: 5 },
  { id: 'car', body: '#2f3b52', length: 10, width: 6, windows: 2 },
  { id: 'bike', body: '#00a878', length: 7, width: 3, windows: 0 },
];

/** Place markers, one per catalog category, as little pixel signs. */
const PLACES = {
  cafe: { ink: '#8b5a2b', glyph: 'cup' },
  restaurant: { ink: '#e8384f', glyph: 'plate' },
  fast_food: { ink: '#f2683c', glyph: 'burger' },
  bar: { ink: '#8b3dff', glyph: 'glass' },
  nightclub: { ink: '#6d1fd6', glyph: 'note' },
  grocery: { ink: '#00a878', glyph: 'cart' },
  convenience: { ink: '#3fb98a', glyph: 'bag' },
  retail: { ink: '#f5b301', glyph: 'bag' },
  clothing: { ink: '#e0a21a', glyph: 'shirt' },
  pharmacy: { ink: '#1fa6a6', glyph: 'cross' },
  office: { ink: '#2323e5', glyph: 'tower' },
  school: { ink: '#00a6c0', glyph: 'book' },
  university: { ink: '#0087a8', glyph: 'cap' },
  library: { ink: '#3a6ea5', glyph: 'book' },
  park: { ink: '#2f8f4e', glyph: 'tree' },
  gym: { ink: '#e8384f', glyph: 'weight' },
  museum: { ink: '#8b3dff', glyph: 'frame' },
  theatre: { ink: '#a63ddb', glyph: 'masks' },
  cinema: { ink: '#7a2fc4', glyph: 'film' },
  hotel: { ink: '#ff6a13', glyph: 'bed' },
  clinic: { ink: '#d9455f', glyph: 'cross' },
  bank: { ink: '#5b6b7a', glyph: 'coin' },
  worship: { ink: '#6b6b73', glyph: 'spire' },
  transit_stop: { ink: '#00a6c0', glyph: 'stop' },
};

/* ── pixel helpers ───────────────────────────────────────────────────── */

function painter(ctx, originX, originY) {
  return (x, y, w, h, colour) => {
    if (!colour) return;
    ctx.fillStyle = colour;
    ctx.fillRect(originX + x * UNIT, originY + y * UNIT, w * UNIT, h * UNIT);
  };
}

/* ── characters ──────────────────────────────────────────────────────── */

/**
 * A walking figure on the logical grid.
 *
 * `direction` selects the view; `frame` steps the legs. Proportions are
 * deliberately large-headed, which is what reads as a character rather than a
 * stick at sixteen pixels tall.
 */
function drawCharacter(px, persona, direction, frame) {
  const skin = SKIN[persona.skin % SKIN.length];
  const hair = HAIR[persona.hair % HAIR.length];
  const shirt = persona.shirt;
  const pants = PANTS[persona.hair % PANTS.length];

  const side = direction === 'left' || direction === 'right';
  const facingLeft = direction === 'left';
  const back = direction === 'up';

  // legs swing on frames 1 and 3; 0 and 2 are the passing position
  const step = frame === 1 ? 1 : frame === 3 ? -1 : 0;

  const bodyX = side ? 6 : 5;
  const bodyW = side ? 5 : 6;

  // shadow grounds the figure on the street
  px(5, 19, 6, 1, 'rgba(20,20,28,0.18)');

  // legs
  const legY = 14;
  if (side) {
    px(bodyX + 1, legY, 2, 4, pants);
    px(bodyX + 1 + step, legY + 1, 2, 3, pants);
    px(bodyX + 1 + step, 18, 2, 1, SHOE);
  } else {
    px(5, legY, 2, 4, pants);
    px(9, legY, 2, 4, pants);
    px(5, legY + 3 + Math.max(0, step), 2, 1, SHOE);
    px(9, legY + 3 + Math.max(0, -step), 2, 1, SHOE);
  }

  // torso
  px(bodyX, 8, bodyW, 6, shirt);
  if (persona.accessory === 'apron') px(bodyX + 1, 10, bodyW - 2, 4, '#f7f4ee');

  // arms swing opposite the legs
  if (side) {
    px(facingLeft ? bodyX - 1 : bodyX + bodyW, 9, 1, 4, shirt);
    px(facingLeft ? bodyX - 1 : bodyX + bodyW, 12 - step, 1, 1, skin);
  } else {
    px(4, 9, 1, 4, shirt);
    px(11, 9, 1, 4, shirt);
    px(4, 13 - step, 1, 1, skin);
    px(11, 13 + step, 1, 1, skin);
  }

  if (persona.accessory === 'backpack') {
    if (back) px(6, 8, 4, 5, '#3c3c46');
    else if (side) px(facingLeft ? bodyX + bodyW : bodyX - 1, 9, 1, 4, '#3c3c46');
  }

  // head
  px(5, 2, 6, 6, skin);
  px(5, 1, 6, 2, hair); // fringe
  px(4, 2, 1, 4, hair); // sides
  px(11, 2, 1, 4, hair);
  if (back) px(5, 2, 6, 5, hair); // seen from behind it is all hair

  if (!back) {
    if (side) {
      px(facingLeft ? 6 : 9, 4, 1, 1, '#241f1c');
    } else {
      px(6, 4, 1, 1, '#241f1c');
      px(9, 4, 1, 1, '#241f1c');
      px(7, 6, 2, 1, 'rgba(120,60,50,0.45)');
    }
  }

  if (persona.accessory === 'briefcase' && !back) {
    px(facingLeft ? 3 : 12, 12, 2, 3, '#5b3a21');
  }
  if (persona.accessory === 'camera' && !back) {
    px(7, 9, 3, 2, '#241f1c');
  }
}

/* ── vehicles ────────────────────────────────────────────────────────── */

/** Seen from above, nose pointing up; the layer rotates it by heading. */
function drawVehicle(px, spec) {
  const { length, width, body, windows } = spec;
  const x0 = Math.round((GRID_W - width) / 2);
  const y0 = Math.round((GRID_H - length) / 2);

  px(x0 - 1, y0 + 1, width + 2, length - 2, 'rgba(20,20,28,0.16)'); // shadow

  if (spec.id === 'bike') {
    px(x0 + 1, y0, 1, length, body);
    px(x0, y0 + 1, 3, 1, '#241f1c');
    px(x0, y0 + length - 2, 3, 1, '#241f1c');
    px(x0 + 1, y0 + 3, 1, 2, '#f4cba4');
    return;
  }

  px(x0, y0, width, length, body);
  px(x0, y0, width, 1, 'rgba(255,255,255,0.35)'); // roof highlight
  px(x0, y0 + length - 1, width, 1, 'rgba(20,20,28,0.35)');

  // windscreen and side windows, which is what makes it read as a vehicle
  px(x0 + 1, y0 + 1, width - 2, 2, '#cfe3f2');
  for (let i = 0; i < windows; i++) {
    const wy = y0 + 4 + i * 2;
    if (wy < y0 + length - 2) {
      px(x0, wy, 1, 1, '#cfe3f2');
      px(x0 + width - 1, wy, 1, 1, '#cfe3f2');
    }
  }
  px(x0 + 1, y0 + length - 2, width - 2, 1, '#ffd36b'); // tail lights
}

/* ── place markers ───────────────────────────────────────────────────── */

function drawPlace(px, spec) {
  const ink = spec.ink;
  // a rounded sign on a short post, so it reads as a marker not a building
  px(4, 3, 8, 8, '#ffffff');
  px(4, 3, 8, 1, ink);
  px(4, 10, 8, 1, ink);
  px(4, 3, 1, 8, ink);
  px(11, 3, 1, 8, ink);
  px(7, 11, 2, 4, ink);
  px(6, 15, 4, 1, 'rgba(20,20,28,0.25)');

  const g = (x, y, w, h, c = ink) => px(4 + x, 3 + y, w, h, c);
  switch (spec.glyph) {
    case 'cup':
      g(2, 2, 4, 4);
      g(6, 3, 1, 2);
      break;
    case 'plate':
      g(2, 2, 4, 1);
      g(2, 4, 4, 1);
      g(3, 3, 2, 1);
      break;
    case 'glass':
      g(2, 2, 4, 1);
      g(3, 3, 2, 2);
      g(2, 5, 4, 1);
      break;
    case 'bag':
      g(2, 3, 4, 3);
      g(3, 2, 1, 1);
      g(4, 2, 1, 1);
      break;
    case 'tower':
      g(2, 1, 4, 5);
      g(3, 2, 1, 1, '#ffffff');
      g(5, 2, 1, 1, '#ffffff');
      g(3, 4, 1, 1, '#ffffff');
      break;
    case 'tree':
      g(3, 1, 2, 3);
      g(2, 2, 4, 2);
      g(3, 4, 2, 2, '#5b3a21');
      break;
    case 'book':
      g(2, 2, 4, 3);
      g(4, 2, 1, 3, '#ffffff');
      break;
    case 'bed':
      g(2, 3, 4, 2);
      g(2, 2, 2, 1);
      break;
    case 'stop':
      g(3, 1, 2, 5);
      g(2, 1, 4, 2);
      break;
    case 'burger':
      g(2, 2, 4, 1);
      g(2, 3, 4, 1, '#ffffff');
      g(2, 4, 4, 1);
      break;
    case 'note':
      g(4, 1, 1, 4);
      g(2, 4, 3, 2);
      g(4, 1, 2, 1);
      break;
    case 'cart':
      g(2, 2, 4, 2);
      g(2, 5, 1, 1);
      g(5, 5, 1, 1);
      break;
    case 'shirt':
      g(2, 2, 4, 4);
      g(1, 2, 1, 2);
      g(6, 2, 1, 2);
      g(3, 2, 2, 1, '#ffffff');
      break;
    case 'cross':
      g(3, 1, 2, 5);
      g(1, 3, 6, 1);
      break;
    case 'cap':
      g(1, 3, 6, 1);
      g(3, 2, 2, 1);
      g(6, 3, 1, 3);
      break;
    case 'frame':
      g(1, 1, 6, 5);
      g(2, 2, 4, 3, '#ffffff');
      g(3, 3, 2, 1);
      break;
    case 'masks':
      g(1, 2, 3, 4);
      g(4, 2, 3, 4);
      g(2, 3, 1, 1, '#ffffff');
      g(5, 3, 1, 1, '#ffffff');
      break;
    case 'film':
      g(1, 2, 6, 4);
      g(2, 3, 1, 1, '#ffffff');
      g(4, 3, 1, 1, '#ffffff');
      g(2, 5, 1, 1, '#ffffff');
      break;
    case 'coin':
      g(2, 2, 4, 4);
      g(3, 3, 2, 2, '#ffffff');
      break;
    case 'spire':
      g(3, 0, 2, 6);
      g(2, 3, 4, 1);
      break;
    case 'weight':
      g(2, 3, 1, 2);
      g(5, 3, 1, 2);
      g(3, 3, 2, 1);
      break;
  }
}

/* ── atlas ───────────────────────────────────────────────────────────── */

async function main() {
  const cells = [];

  for (const persona of PERSONAS) {
    for (const direction of DIRECTIONS) {
      for (let f = 0; f < FRAMES; f++) {
        cells.push({
          name: `${persona.id}_${direction}_${f}`,
          draw: (px) => drawCharacter(px, persona, direction, f),
        });
      }
    }
  }
  for (const vehicle of VEHICLES) {
    cells.push({ name: `v_${vehicle.id}`, draw: (px) => drawVehicle(px, vehicle) });
  }
  for (const [key, spec] of Object.entries(PLACES)) {
    cells.push({ name: `p_${key}`, draw: (px) => drawPlace(px, spec) });
  }

  const rows = Math.ceil(cells.length / COLUMNS);
  const canvas = createCanvas(COLUMNS * CELL, rows * CELL);
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = false;

  const originX = Math.round((CELL - GRID_W * UNIT) / 2);
  const originY = Math.round((CELL - GRID_H * UNIT) / 2);

  const mapping = {};
  cells.forEach((cell, index) => {
    const col = index % COLUMNS;
    const row = Math.floor(index / COLUMNS);
    const x = col * CELL;
    const y = row * CELL;

    ctx.save();
    ctx.beginPath();
    ctx.rect(x, y, CELL, CELL);
    ctx.clip();
    cell.draw(painter(ctx, x + originX, y + originY));
    ctx.restore();

    mapping[cell.name] = {
      x,
      y,
      width: CELL,
      height: CELL,
      anchorX: CELL / 2,
      // characters stand on their feet; vehicles and signs pivot at centre
      anchorY: cell.name.startsWith('v_') ? CELL / 2 : CELL - originY - UNIT,
      mask: false,
    };
  });

  await mkdir(OUT_DIR, { recursive: true });
  await writeFile(path.join(OUT_DIR, 'atlas.png'), canvas.toBuffer('image/png'));
  await writeFile(
    path.join(OUT_DIR, 'atlas.json'),
    JSON.stringify(
      {
        cell: CELL,
        frames: FRAMES,
        directions: DIRECTIONS,
        people: PERSONAS.map((p) => p.id),
        personaColours: Object.fromEntries(PERSONAS.map((p) => [p.id, p.shirt])),
        vehicles: VEHICLES.map((v) => v.id),
        places: Object.fromEntries(
          Object.entries(PLACES).map(([k, v]) => [k, v.ink]),
        ),
        mapping,
      },
      null,
      1,
    ),
  );

  console.log(
    `atlas ${canvas.width}x${canvas.height}: ${cells.length} sprites ` +
      `(${PERSONAS.length} personas x ${DIRECTIONS.length} directions x ${FRAMES} frames, ` +
      `${VEHICLES.length} vehicles, ${Object.keys(PLACES).length} place markers)`,
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
