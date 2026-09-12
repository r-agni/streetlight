/**
 * Generate the character and vehicle sprite atlas.
 *
 * The artwork is drawn here rather than sourced, for one reason: nothing free
 * and pre-made matches a flat, single-weight, electric-blue poster aesthetic,
 * and pixel art actively fights it. Drawing the figures procedurally also means
 * the walk cycle is a function of phase rather than a set of hand-authored
 * frames, so frame count and figure size are parameters instead of redraws.
 *
 * Everything is drawn white-on-transparent and marked as a mask in the icon
 * mapping, so deck.gl tints each instance from the agent's persona and state.
 * One atlas therefore serves every colour in the product.
 *
 *   node scripts/make_sprites.mjs
 */
import { createCanvas } from '@napi-rs/canvas';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const OUT_DIR = path.join('apps', 'web', 'public', 'sprites');

const CELL = 64; // atlas cell, drawn at twice the size it is displayed
const FRAMES = 6; // frames in one walk cycle
const COLUMNS = 12;

/** Persona figures. Small silhouette cues are what make them tell apart. */
const PEOPLE = [
  { id: 'office', build: 1.0, accessory: 'briefcase' },
  { id: 'tech', build: 1.0, accessory: 'backpack' },
  { id: 'student', build: 0.92, accessory: 'backpack' },
  { id: 'service', build: 1.0, accessory: 'apron' },
  { id: 'remote', build: 0.98, accessory: 'none' },
  { id: 'retiree', build: 0.94, accessory: 'cane' },
  { id: 'visitor', build: 1.0, accessory: 'camera' },
];

const VEHICLES = ['bus', 'car', 'tram', 'bike'];

const ink = (ctx, alpha = 1) => {
  ctx.strokeStyle = `rgba(255,255,255,${alpha})`;
  ctx.fillStyle = `rgba(255,255,255,${alpha})`;
};

/** One walking figure, seen from the side, facing right. */
function drawPerson(ctx, { build, accessory }, phase) {
  const swing = Math.sin(phase * Math.PI * 2);
  const counter = Math.sin(phase * Math.PI * 2 + Math.PI);
  // the body rises and falls twice per stride
  const bob = Math.abs(Math.cos(phase * Math.PI * 2)) * 1.6;

  const cx = CELL / 2;
  const ground = 57;
  const scale = build;
  const hipY = ground - 17 * scale - bob;
  const shoulderY = hipY - 15 * scale;
  const headR = 5.6 * scale;
  const headY = shoulderY - headR - 2.5;

  ink(ctx);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  // legs
  ctx.lineWidth = 4.6 * scale;
  for (const dir of [swing, counter]) {
    const kneeX = cx + dir * 4.5;
    const footX = cx + dir * 8.5;
    ctx.beginPath();
    ctx.moveTo(cx, hipY);
    ctx.lineTo(kneeX, (hipY + ground) / 2);
    ctx.lineTo(footX, ground);
    ctx.stroke();
  }

  // torso
  ctx.lineWidth = 7.4 * scale;
  ctx.beginPath();
  ctx.moveTo(cx, hipY);
  ctx.lineTo(cx, shoulderY);
  ctx.stroke();

  if (accessory === 'apron') {
    ink(ctx, 0.55);
    ctx.lineWidth = 8.6 * scale;
    ctx.beginPath();
    ctx.moveTo(cx, hipY + 1);
    ctx.lineTo(cx, hipY - 7 * scale);
    ctx.stroke();
    ink(ctx);
  }

  if (accessory === 'backpack') {
    ctx.beginPath();
    ctx.roundRect(cx - 8.2 * scale, shoulderY + 1.5, 5.2 * scale, 11 * scale, 2);
    ctx.fill();
  }

  // arms, swinging opposite the legs
  ctx.lineWidth = 3.7 * scale;
  ctx.beginPath();
  ctx.moveTo(cx, shoulderY + 2);
  ctx.lineTo(cx + counter * 6.5, shoulderY + 11 * scale);
  ctx.stroke();

  const handX = cx + swing * 6.5;
  const handY = shoulderY + 11 * scale;
  ctx.beginPath();
  ctx.moveTo(cx, shoulderY + 2);
  ctx.lineTo(handX, handY);
  ctx.stroke();

  if (accessory === 'briefcase') {
    ctx.beginPath();
    ctx.roundRect(handX - 3.4, handY + 1, 7, 5.4, 1.2);
    ctx.fill();
  }
  if (accessory === 'cane') {
    ctx.lineWidth = 2.1;
    ctx.beginPath();
    ctx.moveTo(handX, handY);
    ctx.lineTo(handX + 2.5, ground);
    ctx.stroke();
  }

  // head
  ctx.beginPath();
  ctx.arc(cx, headY, headR, 0, Math.PI * 2);
  ctx.fill();

  if (accessory === 'camera') {
    ctx.beginPath();
    ctx.roundRect(cx + 2, shoulderY + 4, 6, 4.4, 1.2);
    ctx.fill();
  }
}

/** Vehicles, also facing right. `phase` only animates the wheels. */
function drawVehicle(ctx, kind, phase) {
  const cx = CELL / 2;
  const ground = 54;
  ink(ctx);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  const spin = phase * Math.PI * 2;
  const wheels = (xs, r) => {
    for (const x of xs) {
      ctx.beginPath();
      ctx.arc(x, ground, r, 0, Math.PI * 2);
      ctx.fill();
      // a spoke, so motion is visible even when the body is a plain block
      ink(ctx, 0.25);
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(x, ground);
      ctx.lineTo(x + Math.cos(spin) * r, ground + Math.sin(spin) * r);
      ctx.stroke();
      ink(ctx);
    }
  };

  if (kind === 'bus' || kind === 'tram') {
    const top = ground - 22;
    ctx.beginPath();
    ctx.roundRect(cx - 25, top, 50, 22, kind === 'tram' ? 4 : 3);
    ctx.fill();
    // windows punched out so the silhouette reads as a vehicle, not a slab
    ctx.globalCompositeOperation = 'destination-out';
    for (let i = 0; i < 4; i++) {
      ctx.beginPath();
      ctx.roundRect(cx - 21 + i * 11, top + 4, 8, 8, 1.5);
      ctx.fill();
    }
    ctx.globalCompositeOperation = 'source-over';
    ink(ctx);
    wheels(kind === 'tram' ? [cx - 15, cx + 15] : [cx - 15, cx + 14], 4.4);
  } else if (kind === 'car') {
    const top = ground - 15;
    ctx.beginPath();
    ctx.moveTo(cx - 19, ground - 1);
    ctx.lineTo(cx - 17, top + 4);
    ctx.quadraticCurveTo(cx - 8, top - 4, cx + 3, top + 2);
    ctx.lineTo(cx + 18, top + 5);
    ctx.lineTo(cx + 19, ground - 1);
    ctx.closePath();
    ctx.fill();
    ctx.globalCompositeOperation = 'destination-out';
    ctx.beginPath();
    ctx.roundRect(cx - 12, top + 1, 9, 6, 1.5);
    ctx.fill();
    ctx.globalCompositeOperation = 'source-over';
    ink(ctx);
    wheels([cx - 11, cx + 11], 4.2);
  } else {
    // bicycle, with the rider pedalling
    const wheelY = ground - 2;
    ctx.lineWidth = 2.2;
    for (const x of [cx - 11, cx + 11]) {
      ctx.beginPath();
      ctx.arc(x, wheelY, 7, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.moveTo(cx - 11, wheelY);
    ctx.lineTo(cx - 1, wheelY - 9);
    ctx.lineTo(cx + 11, wheelY);
    ctx.moveTo(cx - 1, wheelY - 9);
    ctx.lineTo(cx + 5, wheelY - 11);
    ctx.stroke();
    ctx.lineWidth = 3.4;
    const pedal = Math.sin(spin) * 3;
    ctx.beginPath();
    ctx.moveTo(cx - 1, wheelY - 9 - pedal);
    ctx.lineTo(cx - 2, wheelY - 19);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx - 2, wheelY - 23, 4.2, 0, Math.PI * 2);
    ctx.fill();
  }
}

async function main() {
  const cells = [];
  for (const person of PEOPLE) {
    for (let f = 0; f < FRAMES; f++) {
      cells.push({ name: `${person.id}_${f}`, kind: 'person', spec: person, phase: f / FRAMES });
    }
  }
  for (const vehicle of VEHICLES) {
    for (let f = 0; f < 2; f++) {
      cells.push({ name: `${vehicle}_${f}`, kind: 'vehicle', spec: vehicle, phase: f / 2 });
    }
  }

  // each cell is drawn twice: facing right, then mirrored facing left
  const total = cells.length * 2;
  const rows = Math.ceil(total / COLUMNS);
  const canvas = createCanvas(COLUMNS * CELL, rows * CELL);
  const ctx = canvas.getContext('2d');

  const mapping = {};
  let index = 0;
  for (const facing of ['r', 'l']) {
    for (const cell of cells) {
      const col = index % COLUMNS;
      const row = Math.floor(index / COLUMNS);
      const x = col * CELL;
      const y = row * CELL;

      ctx.save();
      ctx.translate(x, y);
      ctx.beginPath();
      ctx.rect(0, 0, CELL, CELL);
      ctx.clip();
      if (facing === 'l') {
        ctx.translate(CELL, 0);
        ctx.scale(-1, 1);
      }
      if (cell.kind === 'person') drawPerson(ctx, cell.spec, cell.phase);
      else drawVehicle(ctx, cell.spec, cell.phase);
      ctx.restore();

      mapping[`${cell.name}_${facing}`] = {
        x,
        y,
        width: CELL,
        height: CELL,
        // anchor at the feet so figures stand on the street, not float over it
        anchorX: CELL / 2,
        anchorY: CELL - 6,
        mask: true,
      };
      index++;
    }
  }

  await mkdir(OUT_DIR, { recursive: true });
  await writeFile(path.join(OUT_DIR, 'atlas.png'), canvas.toBuffer('image/png'));
  await writeFile(
    path.join(OUT_DIR, 'atlas.json'),
    JSON.stringify(
      {
        cell: CELL,
        frames: FRAMES,
        people: PEOPLE.map((p) => p.id),
        vehicles: VEHICLES,
        mapping,
      },
      null,
      1,
    ),
  );

  console.log(
    `atlas ${canvas.width}x${canvas.height}, ${total} icons ` +
      `(${PEOPLE.length} personas x ${FRAMES} frames + ${VEHICLES.length} vehicles, both facings)`,
  );
  console.log(`-> ${path.join(OUT_DIR, 'atlas.png')}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
