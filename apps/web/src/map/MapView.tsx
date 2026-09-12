/**
 * The map.
 *
 * MapLibre draws the paper basemap; deck.gl draws everything that moves. The
 * animation loop never goes through React: it blends the two newest position
 * snapshots into a reusable buffer and hands that buffer to the GPU as a binary
 * attribute, so per-agent cost stays off the main thread.
 *
 * Density is drawn as a halftone dot screen rather than a smooth heat blur —
 * one dot per grid cell, area proportional to the people standing in it.
 */
import { useEffect, useRef } from 'react';
import { Map as MapLibreMap, NavigationControl } from 'maplibre-gl';
import { MapboxOverlay } from '@deck.gl/mapbox';
import type { Layer } from '@deck.gl/core';
import { IconLayer, ScatterplotLayer } from '@deck.gl/layers';
import 'maplibre-gl/dist/maplibre-gl.css';

import { loadBasemapStyle } from './basemapStyle';
import { connection, gridCellsToPoints, interpolator, startConnection } from '../sim/connection';
import { useSim } from '../state/simStore';
import {
  collectSprites,
  iconNameFor,
  loadAtlas,
  makeSpriteBuffer,
  SPRITE_ZOOM,
  type SpriteAtlas,
} from './sprites';

/** Agent colours, indexed by the interpolator's kind byte. */
const AGENT_COLOURS: [number, number, number, number][] = [
  [26, 26, 224, 255], // travelling: the only fully saturated thing on screen
  [88, 88, 236, 150], // dwelling
  [138, 138, 226, 78], // at home: dim, but still shows where people live
];

/** Cell side is roughly 100 m, so this keeps neighbouring dots from merging. */
const MAX_DOT_METRES = 52;

/**
 * Density and individuals trade places as you zoom.
 *
 * Far out, the halftone screen is the subject and agents are texture. Close in,
 * the screen would balloon into soft overlapping blobs, so it fades and the
 * individual people take over.
 */
const DENSITY_FADE_START = 13.0;
const DENSITY_FADE_END = 14.8;

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

/** Agent dot radius in pixels, growing as the viewer zooms in. */
function agentRadiusForZoom(zoom: number): number {
  if (zoom < 12) return 1.15;
  if (zoom > 16) return 3.6;
  return 1.15 + ((zoom - 12) / 4) * 2.45;
}

const INITIAL_VIEW = {
  center: [-122.4183, 37.7775] as [number, number],
  zoom: 12.4,
};

export function MapView() {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);

  useEffect(() => {
    if (!host.current) return;

    let disposed = false;
    let raf = 0;
    let overlay: MapboxOverlay | null = null;
    const cleanups: Array<() => void> = [];

    // reusable GPU-bound buffers
    let colours = new Uint8Array(0);
    let gridPoints: Float32Array<ArrayBuffer> = new Float32Array(0);
    let gridRadii: Float32Array<ArrayBuffer> = new Float32Array(0);
    let gridCount = 0;
    let gridStamp = -1;

    // sprite state
    let atlas: SpriteAtlas | null = null;
    const spriteIndices = makeSpriteBuffer();
    let spriteData: { i: number }[] = [];

    // frame telemetry
    let frames = 0;
    let fpsWindow = performance.now();
    let sampleAge = 0;

    startConnection();

    void (async () => {
      const [style, loadedAtlas] = await Promise.all([loadBasemapStyle(), loadAtlas()]);
      atlas = loadedAtlas;
      if (disposed || !host.current) return;

      const map = new MapLibreMap({
        container: host.current,
        style,
        center: INITIAL_VIEW.center,
        zoom: INITIAL_VIEW.zoom,
        attributionControl: { compact: true },
        dragRotate: false,
      });
      mapRef.current = map;
      map.addControl(new NavigationControl({ showCompass: false }), 'bottom-right');

      // camera hook used by the screenshot harness and, later, by the assistant
      // when it wants to point the viewer at something it just computed
      (window as unknown as Record<string, unknown>).__setView = (
        center: [number, number],
        zoom: number,
      ) => map.jumpTo({ center, zoom });

      overlay = new MapboxOverlay({ interleaved: false, layers: [] });
      map.addControl(overlay);

      // the container is often still collapsing into place when the map is
      // constructed, so take its final size once layout settles
      const fit = () => map.resize();
      map.once('load', fit);
      const observer = new ResizeObserver(fit);
      observer.observe(host.current!);
      cleanups.push(() => observer.disconnect());

      const tick = () => {
        if (disposed) return;
        raf = requestAnimationFrame(tick);

        const now = performance.now();
        const state = useSim.getState();
        const zoom = map.getZoom();
        const densityOpacity = clamp01(
          (DENSITY_FADE_END - zoom) / (DENSITY_FADE_END - DENSITY_FADE_START),
        );
        const agentRadius = agentRadiusForZoom(zoom);
        const sample = interpolator.sample(connection.prev, connection.next, now);
        sampleAge = sample?.age ?? sampleAge;

        frames++;
        if (now - fpsWindow >= 500) {
          state.setPerf(Math.round((frames * 1000) / (now - fpsWindow)), Math.round(sampleAge));
          frames = 0;
          fpsWindow = now;
        }

        const layers: Layer[] = [];

        // ---- density: a halftone dot screen ------------------------------
        if (state.showDensity && densityOpacity > 0.01 && connection.grid && state.grid) {
          if (connection.gridAt !== gridStamp) {
            gridStamp = connection.gridAt;
            const { indices, values } = connection.grid;
            gridPoints = gridCellsToPoints(indices, state.grid) as Float32Array<ArrayBuffer>;
            gridCount = values.length;
            if (gridRadii.length !== gridCount) gridRadii = new Float32Array(gridCount);
            let max = 1;
            for (let i = 0; i < gridCount; i++) if (values[i] > max) max = values[i];
            // area, not radius, carries the count, so the dot reads as a quantity
            for (let i = 0; i < gridCount; i++) {
              gridRadii[i] = Math.sqrt(values[i] / max) * MAX_DOT_METRES;
            }
          }
          if (gridCount > 0) {
            layers.push(
              new ScatterplotLayer({
                id: 'density',
                data: {
                  length: gridCount,
                  attributes: {
                    getPosition: { value: gridPoints, size: 2 },
                    getRadius: { value: gridRadii, size: 1 },
                  },
                },
                radiusUnits: 'meters',
                radiusMinPixels: 0.6,
                // capped so the screen stays a screen instead of becoming blobs
                radiusMaxPixels: 9,
                getFillColor: [35, 35, 229, 105],
                opacity: densityOpacity,
                stroked: false,
                pickable: false,
                updateTriggers: { getPosition: gridStamp, getRadius: gridStamp },
              }),
            );
          }
        }

        // ---- agents as dots ----------------------------------------------
        // dots and figures cross-fade rather than switching, so there is no pop
        const spritesActive = atlas !== null && zoom >= SPRITE_ZOOM;
        const dotOpacity = spritesActive ? clamp01((SPRITE_ZOOM + 1.1 - zoom) / 1.1) : 1;

        if (state.showAgents && dotOpacity > 0.01 && sample && sample.count > 0) {
          if (colours.length !== sample.count * 4) colours = new Uint8Array(sample.count * 4);
          const kind = sample.kind;
          for (let i = 0; i < sample.count; i++) {
            const c = AGENT_COLOURS[kind[i]];
            const o = i * 4;
            colours[o] = c[0];
            colours[o + 1] = c[1];
            colours[o + 2] = c[2];
            colours[o + 3] = c[3];
          }
          layers.push(
            new ScatterplotLayer({
              id: 'agents',
              data: {
                length: sample.count,
                attributes: {
                  getPosition: { value: sample.positions, size: 2 },
                  getFillColor: { value: colours, size: 4, normalized: true },
                },
              },
              getRadius: agentRadius,
              radiusUnits: 'pixels',
              radiusMinPixels: 1,
              radiusMaxPixels: 6,
              opacity: dotOpacity,
              stroked: false,
              pickable: false,
              updateTriggers: {
                getPosition: interpolator.revision,
                getFillColor: interpolator.revision,
              },
            }),
          );
        }

        // ---- agents as walking figures -----------------------------------
        if (state.showAgents && spritesActive && sample && sample.count > 0) {
          const b = map.getBounds();
          const padLon = (b.getEast() - b.getWest()) * 0.08;
          const padLat = (b.getNorth() - b.getSouth()) * 0.08;
          const found = collectSprites(
            sample,
            [
              b.getWest() - padLon,
              b.getSouth() - padLat,
              b.getEast() + padLon,
              b.getNorth() + padLat,
            ],
            spriteIndices,
          );

          if (spriteData.length !== found) {
            spriteData = Array.from({ length: found }, () => ({ i: 0 }));
          }
          for (let k = 0; k < found; k++) spriteData[k].i = spriteIndices[k];

          const seconds = now / 1000;
          const figureSize = zoom < 16 ? 17 : zoom < 17.5 ? 26 : 36;
          const positions = sample.positions;
          const segment = sample.segment;
          const kinds = sample.kind;
          const angles = sample.angle;

          layers.push(
            new IconLayer({
              id: 'figures',
              data: spriteData,
              iconAtlas: '/sprites/atlas.png',
              iconMapping: atlas!.mapping,
              getPosition: (d: { i: number }) => [positions[d.i * 2], positions[d.i * 2 + 1]],
              getIcon: (d: { i: number }) =>
                iconNameFor(atlas!, segment[d.i], kinds[d.i], angles[d.i], d.i, seconds),
              getSize: figureSize,
              sizeUnits: 'pixels',
              getColor: (d: { i: number }) =>
                kinds[d.i] === 0 ? [26, 26, 224, 255] : [90, 90, 216, 190],
              billboard: false,
              alphaCutoff: 0.04,
              opacity: clamp01((zoom - SPRITE_ZOOM) / 0.8),
              pickable: false,
              updateTriggers: {
                getPosition: interpolator.revision,
                getIcon: Math.floor(seconds * 12),
                getColor: interpolator.revision,
              },
            }),
          );
        }

        overlay?.setProps({ layers });
      };

      raf = requestAnimationFrame(tick);
    })();

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      for (const fn of cleanups) fn();
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  return (
    <div className="map-root absolute inset-0">
      {/* maplibre-gl.css forces position:relative on this element, which would
          defeat absolute insets, so size it explicitly instead */}
      <div ref={host} className="h-full w-full" />
      {/* printed-paper grain: a static tiled gradient, so it costs nothing per frame */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.11] mix-blend-multiply"
        style={{
          backgroundImage: 'radial-gradient(rgba(35,35,229,0.32) 0.5px, transparent 0.6px)',
          backgroundSize: '3px 3px',
        }}
      />
    </div>
  );
}
