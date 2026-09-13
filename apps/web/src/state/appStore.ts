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

export interface ToolSource {
  label: string;
  kind: 'recorded' | 'modelled' | 'derived' | 'reference';
  detail?: string;
  count?: number;
  window?: string;
}

/** One tool call, with what it was asked and what it actually read. */
export interface ToolStep {
  name: string;
  status: 'start' | 'ok' | 'error';
  input?: Record<string, unknown>;
  summary?: string;
  sources?: ToolSource[];
}

export interface AssistantMessage {
  role: 'user' | 'assistant';
  text: string;
  steps?: ToolStep[];
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
  noteTool: (step: ToolStep) => void;
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
  noteTool: (step) =>
    set((s) => {
      const messages = s.messages.slice();
      const last = messages[messages.length - 1];
      if (last && last.role === 'assistant') {
        const steps = (last.steps ?? []).slice();
        // a call announces itself, then reports back; merge the two into one row
        const open = steps.findIndex((t) => t.name === step.name && t.status === 'start');
        if (open >= 0 && step.status !== 'start') steps[open] = { ...steps[open], ...step };
        else steps.push(step);
        messages[messages.length - 1] = { ...last, steps };
      }
      return { messages };
    }),
  setAssistantBusy: (assistantBusy) => set({ assistantBusy }),
}));

/** A question worth clicking: a headline, and the text actually sent. */
export interface Suggestion {
  label: string;
  detail: string;
  prompt: string;
}

/**
 * Questions phrased the way the good answers need.
 *
 * Short prompts get a clarifying question back, which is correct behaviour but
 * a poor demonstration. Each of these carries the detail that produced a strong
 * answer in testing: a budget and a customer, a day and a time, a named place.
 */
export const SUGGESTIONS: Record<Mode, Suggestion[]> = {
  explore: [
    {
      label: 'What is this corner actually like?',
      detail: 'Footfall, complaints, incidents and what trades there',
      prompt:
        'What is 16th and Mission like right now? Cover modelled footfall through ' +
        'the day, what residents report to 311, what the police record, and which ' +
        'businesses are there. Show it on the map with the complaint layer on.',
    },
    {
      label: 'Compare two neighbourhoods',
      detail: 'The Marina against the Tenderloin, side by side',
      prompt:
        'Compare the Marina with the Tenderloin on modelled footfall, 311 ' +
        'complaints, police incidents and the mix of businesses. Say plainly which ' +
        'is busier and which has more reported problems, and mark both on the map.',
    },
    {
      label: 'Who actually lives in a neighbourhood?',
      detail: 'Census population, income, language and commute',
      prompt:
        'Who lives in the Mission? Give me the census picture: population, median ' +
        'income and rent, what share were born abroad, what languages are spoken ' +
        'at home, how many households have no car, and how that compares with the ' +
        'city as a whole. Say which figures carry a wide margin of error.',
    },
    {
      label: 'Where do complaints cluster?',
      detail: 'The worst blocks, and what people are reporting',
      prompt:
        'Which parts of San Francisco get the most 311 complaints, and what are ' +
        'people actually complaining about there? Turn the complaint layer on and ' +
        'take me to the worst area.',
    },
  ],
  business: [
    {
      label: 'Where should I sign a lease?',
      detail: 'A chai house, with budget and customer, down to the address',
      prompt:
        'I have a 200 thousand dollar budget, my customers are young professionals ' +
        'and students, and I am open to any neighbourhood. Where exactly should I ' +
        'sign a lease for an Indian chai house? Give me real vacant addresses, not ' +
        'just a neighbourhood, and tell me what would change your mind.',
    },
    {
      label: 'Is this concept already saturated?',
      detail: 'What trades now, what customers say, where the gap is',
      prompt:
        'I am thinking about a natural wine bar in San Francisco. Research what ' +
        'already trades, what customers say about those places in their reviews, ' +
        'and what people say online. Then tell me whether the market is saturated ' +
        'and which two neighbourhoods still have room.',
    },
    {
      label: 'Rank vacant sites for a cafe',
      detail: 'Real vacancy filings in the Mission, scored',
      prompt:
        'Rank the real vacant commercial parcels in the Mission for a cafe. Show ' +
        'them on the map, and explain what separates the top one from the second.',
    },
  ],
  planner: [
    {
      label: 'Read a neighbourhood as a planner',
      detail: 'Complaints, walkability and what is being built',
      prompt:
        'I am a planner looking at the Tenderloin. What do residents complain ' +
        'about most, how walkable is it, and what is being built? Turn on the ' +
        'complaint and permit layers and show me.',
    },
    {
      label: 'Who can actually reach this?',
      detail: 'A ten-minute walk measured along real streets',
      prompt:
        'How far can someone actually walk from Civic Center in ten minutes, ' +
        'measured along the street network rather than as a circle? Draw it on ' +
        'the map and tell me how many people live inside it.',
    },
    {
      label: 'Where is housing being added?',
      detail: 'Permits filed, and the units they propose',
      prompt:
        'Which parts of San Francisco have the most building permits filed in the ' +
        'last three years, and how many homes do they propose? Turn the permit ' +
        'layer on and take me to the busiest area.',
    },
    {
      label: 'Who lives here, and who is being squeezed?',
      detail: 'Census population, income, rent burden and car access',
      prompt:
        'Using census data, which San Francisco neighbourhoods have the highest ' +
        'share of renters paying over 30 percent of their income on rent, and what ' +
        'are the population, median income and car ownership in the worst three? ' +
        'Quote the margins of error and say where the estimates are too imprecise ' +
        'to act on.',
    },
  ],
  events: [
    {
      label: 'Prepare for a sold-out game',
      detail: 'Transit surge, crowding and the worst blocks',
      prompt:
        'There is a sold-out Warriors game at Chase Center on Friday at 7pm. I run ' +
        'city operations. What should I prepare for, which blocks get worst, and ' +
        'how do people arrive and leave? Show the crowd on the map.',
    },
    {
      label: 'What does an event do to local trade?',
      detail: 'Which businesses absorb the crowd, and how many',
      prompt:
        'During a Giants game at Oracle Park, which nearby bars, restaurants and ' +
        'cafes see the most extra people, and roughly how many each? Put the venue ' +
        'and the crowd on the map.',
    },
    {
      label: 'Compare two venues on the same night',
      detail: 'Chase Center against Oracle Park',
      prompt:
        'Compare a 18,000 person event at Chase Center with a 41,000 person event ' +
        'at Oracle Park, both at 7pm. Which one puts more pressure on transit and ' +
        'on the surrounding blocks, and why?',
    },
  ],
};
