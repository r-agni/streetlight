/**
 * Everything the interface holds that is not an agent position.
 *
 * Kept separate from the simulation store because these values change on human
 * timescales - a click, a question, a panel switch - while that one changes
 * with the clock.
 */
import { create } from 'zustand';

import type { AreaReport, EventReport, LayerInfo, LayerPoints, RankedSite } from '../lib/api';

export type Mode = 'explore' | 'business' | 'planner' | 'events';

export interface AssistantMessage {
  role: 'user' | 'assistant';
  text: string;
  tools?: { name: string; status: string }[];
}

export interface MapMarker {
  label: string;
  lon: number;
  lat: number;
  kind?: string;
}

export interface AppState {
  mode: Mode;
  setMode: (mode: Mode) => void;

  // city data layers
  layers: LayerInfo[];
  layerData: Record<string, LayerPoints>;
  activeLayers: Set<string>;
  showPlaces: boolean;
  setLayers: (layers: LayerInfo[]) => void;
  setLayerData: (id: string, data: LayerPoints) => void;
  toggleLayer: (id: string) => void;
  setLayerOn: (id: string, on: boolean) => void;
  setShowPlaces: (on: boolean) => void;

  // the click-anywhere report
  report: AreaReport | null;
  reportLoading: boolean;
  reportPoint: [number, number] | null;
  setReport: (report: AreaReport | null, point: [number, number] | null) => void;
  setReportLoading: (loading: boolean) => void;

  // business mode
  siteCategory: string;
  siteNear: string;
  sites: RankedSite[];
  sitesLoading: boolean;
  selectedSite: number | null;
  setSiteQuery: (category: string, near: string) => void;
  setSites: (sites: RankedSite[]) => void;
  setSitesLoading: (loading: boolean) => void;
  selectSite: (rank: number | null) => void;

  // events mode
  eventVenue: string;
  eventAttendance: number;
  eventHour: number;
  eventReport: EventReport | null;
  eventLoading: boolean;
  setEventQuery: (venue: string, attendance: number, hour: number) => void;
  setEventReport: (report: EventReport | null) => void;
  setEventLoading: (loading: boolean) => void;

  // drawing driven by the assistant and the panels
  markers: MapMarker[];
  catchmentHull: [number, number][] | null;
  eventOrigins: [number, number][];
  setMarkers: (markers: MapMarker[]) => void;
  setCatchmentHull: (hull: [number, number][] | null) => void;
  setEventOrigins: (origins: [number, number][]) => void;

  // assistant
  messages: AssistantMessage[];
  assistantBusy: boolean;
  pushMessage: (message: AssistantMessage) => void;
  appendToLast: (text: string) => void;
  noteTool: (name: string, status: string) => void;
  setAssistantBusy: (busy: boolean) => void;
}

export const useApp = create<AppState>((set) => ({
  mode: 'explore',
  setMode: (mode) => set({ mode }),

  layers: [],
  layerData: {},
  activeLayers: new Set<string>(),
  showPlaces: true,
  setLayers: (layers) => set({ layers }),
  setLayerData: (id, data) => set((s) => ({ layerData: { ...s.layerData, [id]: data } })),
  toggleLayer: (id) =>
    set((s) => {
      const next = new Set(s.activeLayers);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { activeLayers: next };
    }),
  setLayerOn: (id, on) =>
    set((s) => {
      const next = new Set(s.activeLayers);
      if (on) next.add(id);
      else next.delete(id);
      return { activeLayers: next };
    }),
  setShowPlaces: (showPlaces) => set({ showPlaces }),

  report: null,
  reportLoading: false,
  reportPoint: null,
  setReport: (report, reportPoint) => set({ report, reportPoint, reportLoading: false }),
  setReportLoading: (reportLoading) => set({ reportLoading }),

  siteCategory: 'cafe',
  siteNear: 'mission',
  sites: [],
  sitesLoading: false,
  selectedSite: null,
  setSiteQuery: (siteCategory, siteNear) => set({ siteCategory, siteNear }),
  setSites: (sites) => set({ sites, sitesLoading: false }),
  setSitesLoading: (sitesLoading) => set({ sitesLoading }),
  selectSite: (selectedSite) => set({ selectedSite }),

  eventVenue: 'Chase Center',
  eventAttendance: 18000,
  eventHour: 19,
  eventReport: null,
  eventLoading: false,
  setEventQuery: (eventVenue, eventAttendance, eventHour) =>
    set({ eventVenue, eventAttendance, eventHour }),
  setEventReport: (eventReport) => set({ eventReport, eventLoading: false }),
  setEventLoading: (eventLoading) => set({ eventLoading }),

  markers: [],
  catchmentHull: null,
  eventOrigins: [],
  setMarkers: (markers) => set({ markers }),
  setCatchmentHull: (catchmentHull) => set({ catchmentHull }),
  setEventOrigins: (eventOrigins) => set({ eventOrigins }),

  messages: [],
  assistantBusy: false,
  pushMessage: (message) => set((s) => ({ messages: [...s.messages, message] })),
  appendToLast: (text) =>
    set((s) => {
      const messages = s.messages.slice();
      const last = messages[messages.length - 1];
      if (last && last.role === 'assistant') {
        messages[messages.length - 1] = { ...last, text: last.text + text };
      }
      return { messages };
    }),
  noteTool: (name, status) =>
    set((s) => {
      const messages = s.messages.slice();
      const last = messages[messages.length - 1];
      if (last && last.role === 'assistant') {
        const tools = (last.tools ?? []).slice();
        const existing = tools.findIndex((t) => t.name === name);
        if (existing >= 0) tools[existing] = { name, status };
        else tools.push({ name, status });
        messages[messages.length - 1] = { ...last, tools };
      }
      return { messages };
    }),
  setAssistantBusy: (assistantBusy) => set({ assistantBusy }),
}));

/** Questions offered per mode, so the box is never a blank prompt. */
export const SUGGESTIONS: Record<Mode, string[]> = {
  explore: [
    'What is 16th and Mission like right now?',
    'Compare the Marina with the Tenderloin',
    'Where are the most complaints in the city?',
  ],
  business: [
    'Where should I open a cafe in the Mission?',
    'Best place for a gym near Hayes Valley?',
    'Why is the top site better than the second?',
  ],
  planner: [
    'What is the land use around Dogpatch?',
    'Which blocks have the most building permits?',
    'How far can someone walk from Civic Center in 10 minutes?',
  ],
  events: [
    'Model a sold-out Warriors game at Chase Center',
    'What happens to nearby bars during an Oracle Park game?',
    'Which blocks get crowded before a 7pm concert?',
  ],
};
