/**
 * The map.
 *
 * MapLibre draws the paper basemap; deck.gl draws everything else. The
 * animation loop never goes through React: it blends the two newest position
 * snapshots into reusable buffers and hands those to the GPU as binary
 * attributes, so per-agent cost stays off the main thread.
 *
 * Layer order is deliberate. Density sits underneath as a halftone screen,
 * then city data, then places, then people, then anything a panel or the
 * assistant asked to draw. Whatever is alive stays on top.
 */
import { useEffect, useRef } from 'react';
import { Map as MapLibreMap, NavigationControl } from 'maplibre-gl';
import { MapboxOverlay } from '@deck.gl/mapbox';
import type { Layer } from '@deck.gl/core';
import { IconLayer, PathLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import 'maplibre-gl/dist/maplibre-gl.css';

import { loadBasemapStyle } from './basemapStyle';
import { connection, gridCellsToPoints, interpolator, startConnection } from '../sim/connection';
import { useSim } from '../state/simStore';
import { useApp } from '../state/appStore';
import { api } from '../lib/api';
import { AGENT_STATE_COLOUR, categoryColour, INK, rgba } from '../lib/palette';
import {
  collectSprites,
  iconNameFor,
  isVehicle,
  loadAtlas,
  makeSpriteBuffer,
  SPRITE_ZOOM,
  vehicleAngle,
  type SpriteAtlas,
} from './sprites';

const LAYER_INK: Record<string, string> = {
  complaints: INK.complaints,
  incidents: INK.incidents,
  vacancy: INK.vacancy,
  permits: INK.permits,
};

/** Cell side is roughly 100 m, so this keeps neighbouring dots from merging. */
const MAX_DOT_METRES = 52;

/** Above this zoom a place is drawn as a pixel sign rather than a dot. */
const PLACE_SIGN_ZOOM = 15.2;

/** More signs than this on screen and the street is unreadable. */
const MAX_PLACE_SIGNS = 900;

/** Density and individuals trade places as the viewer zooms. */
const DENSITY_FADE_START = 13.0;
const DENSITY_FADE_END = 14.8;

const INITIAL_VIEW = { center: [-122.4183, 37.7775] as [number, number], zoom: 12.4 };

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

function agentRadiusForZoom(zoom: number): number {
  if (zoom < 12) return 1.15;
  if (zoom > 16) return 3.6;
  return 1.15 + ((zoom - 12) / 4) * 2.45;
}

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

    // sprites
    let atlas: SpriteAtlas | null = null;
    const spriteIndices = makeSpriteBuffer();
    let spriteData: { i: number }[] = [];

    // places, fetched once
    let placeCount = 0;
    let placeColours = new Uint8Array(0);
    let placePositions: Float32Array<ArrayBuffer> = new Float32Array(0);
    let placeCategories: string[] = [];
    let placeSigns: { i: number }[] = [];

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
      });
      mapRef.current = map;
      map.addControl(new NavigationControl({ showCompass: false }), 'bottom-right');

      // camera hooks used by panels, the assistant and the screenshot harness
      (window as unknown as Record<string, unknown>).__setView = (
        center: [number, number],
        zoom: number,
      ) => map.flyTo({ center, zoom, duration: 900 });

      // the assistant can also rotate and tilt, so it gets the fuller form
      (window as unknown as Record<string, unknown>).__setCamera = (
        p: Record<string, unknown>,
      ) => {
        const options: Record<string, unknown> = { duration: 900 };
        if (p.lon !== undefined && p.lat !== undefined) {
          options.center = [Number(p.lon), Number(p.lat)];
        }
        if (p.zoom !== undefined) options.zoom = Number(p.zoom);
        if (p.bearing !== undefined) options.bearing = Number(p.bearing);
        if (p.pitch !== undefined) options.pitch = Number(p.pitch);
        map.flyTo(options as never);
      };

      overlay = new MapboxOverlay({ interleaved: false, layers: [] });
      map.addControl(overlay);

      // maplibre-gl.css forces position:relative on the container, so the size
      // has to be taken once layout settles rather than assumed from insets
      const fit = () => map.resize();
      map.once('load', fit);
      const observer = new ResizeObserver(fit);
      observer.observe(host.current);
      cleanups.push(() => observer.disconnect());

      // clicking anywhere asks the service what that block is like
      map.on('click', async (e) => {
        const { lng, lat } = e.lngLat;
        useApp.getState().setReportLoading(true);
        useApp.getState().setReport(null, [lng, lat]);
        try {
          const report = await api.area(lng, lat, 300);
          useApp.getState().setReport(report, [lng, lat]);
        } catch {
          useApp.getState().setReport(null, [lng, lat]);
        }
      });

      api
        .pois(40000)
        .then((p) => {
          placeCount = p.lon.length;
          placePositions = new Float32Array(placeCount * 2);
          placeColours = new Uint8Array(placeCount * 4);
          placeCategories = new Array(placeCount);
          for (let i = 0; i < placeCount; i++) {
            placeCategories[i] = p.categories[p.cat[i]] ?? '';
            placePositions[i * 2] = p.lon[i];
            placePositions[i * 2 + 1] = p.lat[i];
            const [r, g, b] = rgba(categoryColour(p.categories[p.cat[i]] ?? ''));
            placeColours[i * 4] = r;
            placeColours[i * 4 + 1] = g;
            placeColours[i * 4 + 2] = b;
            placeColours[i * 4 + 3] = 190;
          }
        })
        .catch(() => undefined);

      const tick = () => {
        if (disposed) return;
        raf = requestAnimationFrame(tick);

        const now = performance.now();
        const sim = useSim.getState();
        const app = useApp.getState();
        const zoom = map.getZoom();
        const sample = interpolator.sample(connection.prev, connection.next, now);
        sampleAge = sample?.age ?? sampleAge;

        frames++;
        if (now - fpsWindow >= 500) {
          sim.setPerf(Math.round((frames * 1000) / (now - fpsWindow)), Math.round(sampleAge));
          frames = 0;
          fpsWindow = now;
        }

        const densityOpacity = clamp01(
          (DENSITY_FADE_END - zoom) / (DENSITY_FADE_END - DENSITY_FADE_START),
        );
        const layers: Layer[] = [];

        // ---- density as a halftone screen --------------------------------
        if (sim.showDensity && densityOpacity > 0.01 && connection.grid && sim.grid) {
          if (connection.gridAt !== gridStamp) {
            gridStamp = connection.gridAt;
            const { indices, values } = connection.grid;
            gridPoints = gridCellsToPoints(indices, sim.grid) as Float32Array<ArrayBuffer>;
            gridCount = values.length;
            if (gridRadii.length !== gridCount) gridRadii = new Float32Array(gridCount);
            let max = 1;
            for (let i = 0; i < gridCount; i++) if (values[i] > max) max = values[i];
            // area, not radius, carries the count, so a dot reads as a quantity
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
                radiusMinPixels: 0.5,
                radiusMaxPixels: 9,
                getFillColor: rgba(INK.people, 105),
                opacity: densityOpacity,
                stroked: false,
                pickable: false,
                updateTriggers: { getPosition: gridStamp, getRadius: gridStamp },
              }),
            );
          }
        }

        // ---- city data layers --------------------------------------------
        for (const id of app.activeLayers) {
          const data = app.layerData[id];
          if (!data?.lon?.length) continue;
          layers.push(
            new ScatterplotLayer({
              id: `layer-${id}`,
              data: data.lon.map((lon, i) => [lon, data.lat[i]] as [number, number]),
              getPosition: (d: [number, number]) => d,
              getRadius: 26,
              radiusUnits: 'meters',
              radiusMinPixels: 1.6,
              radiusMaxPixels: 7,
              getFillColor: rgba(LAYER_INK[id] ?? INK.people, 150),
              stroked: false,
              pickable: false,
            }),
          );
        }

        // ---- places -------------------------------------------------------
        // Dots while the whole city is in view, because a sign at that size is
        // an unreadable smudge. Pixel signs once a street is legible, because
        // by then the category matters more than the density.
        if (app.showPlaces && placeCount > 0 && zoom >= 13.2) {
          const signsActive = atlas !== null && zoom >= PLACE_SIGN_ZOOM;
          const placeDotOpacity = signsActive
            ? clamp01((PLACE_SIGN_ZOOM + 0.9 - zoom) / 0.9)
            : 1;

          if (placeDotOpacity > 0.01) {
            layers.push(
              new ScatterplotLayer({
                id: 'places',
                data: {
                  length: placeCount,
                  attributes: {
                    getPosition: { value: placePositions, size: 2 },
                    getFillColor: { value: placeColours, size: 4, normalized: true },
                  },
                },
                getRadius: 1,
                radiusUnits: 'pixels',
                radiusMinPixels: zoom < 15 ? 1.4 : 2.6,
                radiusMaxPixels: 5,
                opacity: clamp01((zoom - 13.2) / 1.2) * placeDotOpacity,
                stroked: false,
                pickable: false,
              }),
            );
          }

          if (signsActive && placeCategories.length) {
            const b = map.getBounds();
            const padLon = (b.getEast() - b.getWest()) * 0.06;
            const padLat = (b.getNorth() - b.getSouth()) * 0.06;
            const west = b.getWest() - padLon;
            const east = b.getEast() + padLon;
            const south = b.getSouth() - padLat;
            const north = b.getNorth() + padLat;

            // only what is on screen, and only as many as stay readable
            if (placeSigns.length !== MAX_PLACE_SIGNS) {
              placeSigns = Array.from({ length: MAX_PLACE_SIGNS }, () => ({ i: 0 }));
            }
            let found = 0;
            for (let i = 0; i < placeCount && found < MAX_PLACE_SIGNS; i++) {
              const lon = placePositions[i * 2];
              const lat = placePositions[i * 2 + 1];
              if (lon < west || lon > east || lat < south || lat > north) continue;
              if (!atlas!.mapping[`p_${placeCategories[i]}`]) continue;
              placeSigns[found++].i = i;
            }
            const visible = placeSigns.slice(0, found);

            layers.push(
              new IconLayer({
                id: 'place-signs',
                data: visible,
                iconAtlas: '/sprites/atlas.png',
                iconMapping: atlas!.mapping,
                getPosition: (d: { i: number }) => [
                  placePositions[d.i * 2],
                  placePositions[d.i * 2 + 1],
                ],
                getIcon: (d: { i: number }) => `p_${placeCategories[d.i]}`,
                getSize: zoom < 16 ? 20 : zoom < 17.5 ? 27 : 34,
                sizeUnits: 'pixels',
                billboard: false,
                alphaCutoff: 0.05,
                opacity: clamp01((zoom - PLACE_SIGN_ZOOM) / 0.7),
                pickable: false,
                updateTriggers: { getIcon: found, getPosition: found },
              }),
            );
          }
        }

        // ---- agents as dots ----------------------------------------------
        const spritesActive = atlas !== null && zoom >= SPRITE_ZOOM;
        const dotOpacity = spritesActive ? clamp01((SPRITE_ZOOM + 1.1 - zoom) / 1.1) : 1;

        if (sim.showAgents && dotOpacity > 0.01 && sample && sample.count > 0) {
          if (colours.length !== sample.count * 4) colours = new Uint8Array(sample.count * 4);
          const kind = sample.kind;
          for (let i = 0; i < sample.count; i++) {
            const c = AGENT_STATE_COLOUR[kind[i]];
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
              getRadius: agentRadiusForZoom(zoom),
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
        if (sim.showAgents && spritesActive && sample && sample.count > 0) {
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
          const figureSize = zoom < 16 ? 22 : zoom < 17.5 ? 34 : 46;
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
              // only vehicles rotate; people change sprite instead, which is
              // what keeps a pixel figure from shearing
              getAngle: (d: { i: number }) =>
                isVehicle(segment[d.i]) ? vehicleAngle(angles[d.i]) : 0,
              getSize: figureSize,
              sizeUnits: 'pixels',
              billboard: false,
              alphaCutoff: 0.05,
              opacity: clamp01((zoom - SPRITE_ZOOM) / 0.8),
              pickable: false,
              updateTriggers: {
                getPosition: interpolator.revision,
                getIcon: Math.floor(seconds * 8),
                getAngle: interpolator.revision,
              },
            }),
          );
        }

        // ---- drawn by a panel or by the assistant -------------------------
        if (app.catchmentHull?.length) {
          layers.push(
            new PathLayer({
              id: 'catchment',
              data: [{ path: app.catchmentHull }],
              getPath: (d: { path: [number, number][] }) => d.path,
              getColor: rgba(INK.sites, 220),
              getWidth: 3,
              widthUnits: 'pixels',
              pickable: false,
            }),
          );
        }

        if (app.eventOrigins.length) {
          layers.push(
            new ScatterplotLayer({
              id: 'event-origins',
              data: app.eventOrigins,
              getPosition: (d: [number, number]) => d,
              getRadius: 40,
              radiusUnits: 'meters',
              radiusMinPixels: 1.5,
              radiusMaxPixels: 6,
              getFillColor: rgba(INK.events, 140),
              stroked: false,
              pickable: false,
            }),
          );
        }

        if (app.markers.length) {
          layers.push(
            new ScatterplotLayer({
              id: 'markers',
              data: app.markers,
              getPosition: (d: { lon: number; lat: number }) => [d.lon, d.lat],
              getRadius: 9,
              radiusUnits: 'pixels',
              radiusMinPixels: 7,
              getFillColor: (d: { kind?: string }) =>
                rgba(d.kind === 'event' ? INK.events : INK.sites, 255),
              stroked: true,
              getLineColor: [255, 255, 255, 255],
              getLineWidth: 2,
              lineWidthUnits: 'pixels',
              pickable: false,
            }),
            new TextLayer({
              id: 'marker-labels',
              data: app.markers,
              getPosition: (d: { lon: number; lat: number }) => [d.lon, d.lat],
              getText: (d: { label: string }) => d.label,
              getSize: 11,
              getColor: [255, 255, 255, 255],
              getTextAnchor: 'middle',
              getAlignmentBaseline: 'center',
              pickable: false,
            }),
          );
        }

        if (app.reportPoint) {
          layers.push(
            new ScatterplotLayer({
              id: 'report-pin',
              data: [app.reportPoint],
              getPosition: (d: [number, number]) => d,
              getRadius: 300,
              radiusUnits: 'meters',
              filled: false,
              stroked: true,
              getLineColor: rgba(INK.people, 170),
              getLineWidth: 2,
              lineWidthUnits: 'pixels',
              pickable: false,
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
