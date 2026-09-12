/**
 * Colour system.
 *
 * The identity stays a printed one: a warm-grey ground and a single electric
 * ultramarine for living people. Everything else on the map is a distinct spot
 * ink, the way a risograph print separates plates. That keeps the poster feel
 * while making complaints, incidents, vacancy and permits tell apart at a
 * glance, which one colour never could.
 *
 * Hues are assigned by meaning, not by prettiness: red reads as a problem,
 * amber as caution, green as investment, violet as policy.
 */

export const INK = {
  people: '#2323e5', // the accent; only living agents use it
  complaints: '#e8384f', // reported problems
  incidents: '#ff6a13', // safety
  vacancy: '#8b3dff', // empty commercial space
  permits: '#00a878', // building activity
  transit: '#00a6c0',
  events: '#ff4fa3',
  sites: '#f5b301', // candidate locations
} as const;

export type InkName = keyof typeof INK;

/** Convert a hex colour to the RGBA array deck.gl wants. */
export function rgba(hex: string, alpha = 255): [number, number, number, number] {
  const v = hex.replace('#', '');
  return [
    parseInt(v.slice(0, 2), 16),
    parseInt(v.slice(2, 4), 16),
    parseInt(v.slice(4, 6), 16),
    alpha,
  ];
}

/**
 * Place categories, grouped so that a street reads as a pattern of uses
 * rather than forty unrelated colours.
 */
export const CATEGORY_GROUPS: Record<string, { label: string; colour: string; members: string[] }> = {
  food: {
    label: 'Food and drink',
    colour: '#e8384f',
    members: ['cafe', 'restaurant', 'fast_food'],
  },
  nightlife: {
    label: 'Nightlife',
    colour: '#8b3dff',
    members: ['bar', 'nightclub'],
  },
  shopping: {
    label: 'Shops',
    colour: '#f5b301',
    members: ['retail', 'clothing', 'grocery', 'convenience', 'pharmacy'],
  },
  work: {
    label: 'Work and study',
    colour: '#2323e5',
    members: ['office', 'university', 'school', 'library'],
  },
  leisure: {
    label: 'Leisure',
    colour: '#00a878',
    members: ['park', 'gym', 'museum', 'theatre', 'cinema'],
  },
  services: {
    label: 'Services',
    colour: '#6b6b73',
    members: ['clinic', 'bank', 'worship'],
  },
  stay: {
    label: 'Hotels',
    colour: '#ff6a13',
    members: ['hotel'],
  },
  transit: {
    label: 'Transit',
    colour: '#00a6c0',
    members: ['transit_stop'],
  },
};

const GROUP_OF = new Map<string, string>();
for (const [group, spec] of Object.entries(CATEGORY_GROUPS)) {
  for (const member of spec.members) GROUP_OF.set(member, group);
}

export function categoryColour(category: string): string {
  const group = GROUP_OF.get(category);
  return group ? CATEGORY_GROUPS[group].colour : '#9a9aa2';
}

export function categoryGroup(category: string): string | undefined {
  return GROUP_OF.get(category);
}

/** Agent colours by movement state, used when drawing dots rather than figures. */
export const AGENT_STATE_COLOUR: Record<number, [number, number, number, number]> = {
  0: rgba(INK.people, 255), // travelling
  1: [88, 88, 236, 150], // at a place
  2: [138, 138, 226, 70], // at home
};

/**
 * Persona colours, matching the shirt each sprite wears so the dot view and
 * the figure view agree about who is who.
 */
export const PERSONA_COLOURS = [
  '#2323e5', // office worker
  '#00a6c0', // tech commuter
  '#f5b301', // student
  '#00a878', // service worker
  '#8b3dff', // remote worker
  '#b8b8bd', // retiree
  '#ff6a13', // visitor
  '#e8384f', // other resident
];

/** A five-step ramp from the ground colour to full ink, for density screens. */
export function densityRamp(ink: string): [number, number, number][] {
  const [r, g, b] = rgba(ink);
  return [0.22, 0.4, 0.58, 0.78, 1].map((t) => [
    Math.round(231 + (r - 231) * t),
    Math.round(229 + (g - 229) * t),
    Math.round(224 + (b - 224) * t),
  ]) as [number, number, number][];
}
