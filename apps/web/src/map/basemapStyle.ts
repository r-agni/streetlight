/**
 * Build the basemap style.
 *
 * We start from OpenFreeMap's Positron (free, no key, no request limit) and
 * repaint it so the city reads as printed paper: a warm grey ground, near-white
 * streets, quiet labels, and no competing colour anywhere. The agents supply the
 * only saturated colour on screen.
 */
import type { StyleSpecification } from 'maplibre-gl';

export const BASEMAP_URL = 'https://tiles.openfreemap.org/styles/positron';

export const PALETTE = {
  ground: '#e7e5e0',
  water: '#dadde3',
  building: '#dedbd5',
  buildingLine: '#d4d1ca',
  road: '#ffffff',
  roadMajor: '#ffffff',
  roadCasing: '#dbd8d1',
  park: '#e0e3d9',
  label: '#77767d',
  labelHalo: '#f7f6f3',
  blue: '#2323e5',
} as const;

/** Layers that add noise without adding meaning at city scale. */
const DROP = new Set([
  'landcover_ice_shelf',
  'landcover_glacier',
  'landcover_wood',
  'aeroway-taxiway',
  'aeroway-runway-casing',
  'aeroway-runway',
  'aeroway-area',
  'boundary_disputed',
  'boundary_3',
  'waterway_line_label',
  'water_name_point_label',
  'water_name_line_label',
  'highway-name-path',
  'highway-shield',
  'airport_label',
  'poi_z16_subclass',
  'poi_z16',
  'poi_z15',
  'poi_z14',
  'poi_transit',
]);

const isRoadCasing = (id: string) => id.includes('casing');
const isMotorway = (id: string) => id.includes('motorway');
const isMajor = (id: string) => id.includes('major') || id.includes('trunk');

/** Fetch Positron and repaint it. Falls back to a flat style if the fetch fails. */
export async function loadBasemapStyle(): Promise<StyleSpecification> {
  let style: StyleSpecification;
  try {
    const res = await fetch(BASEMAP_URL);
    if (!res.ok) throw new Error(`basemap ${res.status}`);
    style = (await res.json()) as StyleSpecification;
  } catch (err) {
    console.warn('basemap fetch failed, using flat fallback', err);
    return flatFallback();
  }
  return repaint(style);
}

function repaint(style: StyleSpecification): StyleSpecification {
  const layers = (style.layers ?? []).filter((l) => !DROP.has(l.id));

  for (const layer of layers) {
    const id = layer.id;
    const paint = ((layer as any).paint ??= {});

    if (layer.type === 'background') {
      paint['background-color'] = PALETTE.ground;
      continue;
    }
    if (id === 'water') {
      paint['fill-color'] = PALETTE.water;
      paint['fill-opacity'] = 1;
      continue;
    }
    if (id === 'waterway') {
      paint['line-color'] = PALETTE.water;
      continue;
    }
    if (id === 'park') {
      paint['fill-color'] = PALETTE.park;
      paint['fill-opacity'] = 0.9;
      continue;
    }
    if (id === 'landuse_residential') {
      // residential shading only muddies a grey map
      paint['fill-opacity'] = 0;
      continue;
    }
    if (id === 'building') {
      paint['fill-color'] = PALETTE.building;
      paint['fill-opacity'] = ['interpolate', ['linear'], ['zoom'], 13, 0, 14.5, 0.85];
      paint['fill-outline-color'] = PALETTE.buildingLine;
      continue;
    }
    if (layer.type === 'line' && (id.startsWith('highway') || id.startsWith('tunnel') || id.startsWith('road'))) {
      paint['line-color'] = isRoadCasing(id)
        ? PALETTE.roadCasing
        : isMotorway(id) || isMajor(id)
          ? PALETTE.roadMajor
          : PALETTE.road;
      // hold the street network back so moving agents stay dominant
      paint['line-opacity'] = isRoadCasing(id) ? 0.5 : 1;
      continue;
    }
    if (layer.type === 'line' && id.startsWith('railway')) {
      paint['line-color'] = PALETTE.roadCasing;
      paint['line-opacity'] = 0.55;
      continue;
    }
    if (layer.type === 'line' && id.startsWith('boundary')) {
      paint['line-color'] = '#b9b7b1';
      paint['line-opacity'] = 0.6;
      continue;
    }
    if (layer.type === 'symbol') {
      paint['text-color'] = PALETTE.label;
      paint['text-halo-color'] = PALETTE.labelHalo;
      paint['text-halo-width'] = 1.2;
      const lay = ((layer as any).layout ??= {});
      lay['text-font'] = ['Noto Sans Regular'];
      lay['text-letter-spacing'] = 0.04;
      // hold every label back until the viewer is actually reading streets
      if (id.startsWith('highway-name')) lay['text-size'] = 10;
    }
  }

  // Positron ships a shaded-relief raster that fights the flat aesthetic
  const cleaned = layers.filter((l) => (l as any).source !== 'ne2_shaded');

  return { ...style, layers: cleaned } as StyleSpecification;
}

/** Minimal offline style so the app still renders if the tile host is down. */
function flatFallback(): StyleSpecification {
  return {
    version: 8,
    glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sources: {},
    layers: [
      {
        id: 'background',
        type: 'background',
        paint: { 'background-color': PALETTE.ground },
      },
    ],
  } as StyleSpecification;
}
