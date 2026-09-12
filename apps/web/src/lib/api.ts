/** Typed access to the simulation service. */
import { API_URL } from '../sim/connection';

async function get<T>(path: string, params: Record<string, unknown> = {}): Promise<T> {
  const url = new URL(`${API_URL}${path}`);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${path} responded ${res.status}`);
  return (await res.json()) as T;
}

export interface LayerInfo {
  id: string;
  label: string;
  description: string;
  count: number;
  categories: { value: string; count: number }[];
}

export interface LayerPoints {
  id: string;
  label: string;
  count: number;
  total: number;
  thinned: boolean;
  lon: number[];
  lat: number[];
  category: string[];
}

export interface AreaSection {
  label: string;
  window?: string;
  total?: number;
  stillOpen?: number;
  top?: { name: string; count: number }[];
  addresses?: string[];
  reportedVacant?: number;
  proposedUnits?: number;
  parcels?: number;
  residentialUnits?: number;
  retailSqFt?: number;
  officeSqFt?: number;
  commercialSqFt?: number;
  medianYearBuilt?: number;
  mix?: { name: string; parcels: number }[];
}

export interface AreaReport {
  centre: [number, number];
  radiusMetres: number;
  sections: Record<string, AreaSection>;
  footfall: {
    byHour: number[];
    peakHour: number;
    peopleAtPeak: number;
    hoursSimulated: number[];
    note?: string;
  };
  places: {
    name: string;
    category: string;
    metres: number;
    lon: number;
    lat: number;
    rating?: number;
    reviews?: number;
  }[];
  placeMix: { category: string; count: number }[];
}

export interface RankedSite {
  rank: number;
  candidateId: number;
  address: string;
  location: [number, number];
  score: number;
  components: Record<string, { relative: number; weight: number }>;
  modelledPeakFootfall: number;
  peakHour: number;
  footfallByHour: number[];
  walkCatchmentResidents: number;
  competitorsWithinRadius: number;
  complementaryPlaces: number;
  catchmentMethod: string;
  reading: string;
  /** set when the site came from an opportunity search rather than a panel query */
  area?: string;
}

export interface EventReport {
  event: { name: string; venue: [number, number]; attendance: number };
  method: string;
  modelledFromResidents: number;
  assumedFromOutsideTheCity: number;
  originBands: { band: string; people: number; share: number }[];
  likelyMode: Record<string, number>;
  arrivalByQuarterHour: { minute: number; people: number }[];
  crowding: {
    ring: string;
    people: number;
    peoplePerSquareMetre: number;
    comfort: string;
  }[];
  businessUplift: {
    category: string;
    places: number;
    peoplePerPlace: number;
    peopleAcrossAll: number;
  }[];
  attendeeHomeSample?: [number, number][];
}

export interface LiveEvent {
  source: string;
  kind: string;
  name: string;
  venue: string;
  startsAt: string;
  lon: number;
  lat: number;
  expectedAttendance: number | null;
}

export const api = {
  liveEvents: (days = 45) =>
    get<{ count: number; sources: string[]; events: LiveEvent[]; note: string }>(
      '/api/live-events',
      { days },
    ),
  layers: () => get<{ layers: LayerInfo[] }>('/api/layers'),
  layerPoints: (name: string, category?: string) =>
    get<LayerPoints>(`/api/layer/${name}`, { category }),
  area: (lon: number, lat: number, radius = 300) =>
    get<AreaReport>('/api/area', { lon, lat, radius }),
  sites: (category: string, near?: string, limit = 8) =>
    get<{ category: string; ranked: RankedSite[] }>('/api/sites', { category, near, limit }),
  catchment: (lon: number, lat: number, minutes = 10) =>
    get<{ method: string; minutes: number; hull: [number, number][] }>('/api/catchment', {
      lon,
      lat,
      minutes,
    }),
  geocode: (place: string) =>
    get<{ lon: number; lat: number; resolved: string }>('/api/geocode', { place }),
  event: async (venue: string, attendance = 15000, startHour = 19) => {
    const url = new URL(`${API_URL}/api/event`);
    url.searchParams.set('venue', venue);
    url.searchParams.set('attendance', String(attendance));
    url.searchParams.set('start_hour', String(startHour));
    const res = await fetch(url, { method: 'POST' });
    if (!res.ok) throw new Error(`event responded ${res.status}`);
    return (await res.json()) as EventReport;
  },
  pois: (limit = 60000) =>
    get<{
      count: number;
      lon: number[];
      lat: number[];
      cat: number[];
      attr: number[];
      name: string[];
      categories: string[];
    }>('/api/pois', { limit }),
};
