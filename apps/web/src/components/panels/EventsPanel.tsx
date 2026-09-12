/**
 * Plan for a big event.
 *
 * Answers the operational questions: how many people, coming from where, by
 * what mode, arriving when, which blocks fill up, and which businesses sit in
 * the crowd. The method is stated in the panel because it is a gravity model
 * over the simulated population, not a re-run of everyone's day.
 */
import { useEffect, useState } from 'react';
import { CalendarDays, Loader2, Play } from 'lucide-react';

import { api, type LiveEvent } from '../../lib/api';
import { INK } from '../../lib/palette';
import { useApp } from '../../state/appStore';

const VENUES = ['Chase Center', 'Oracle Park', 'Moscone Center', 'Civic Center', 'Union Square'];

const COMFORT_INK: Record<string, string> = {
  'free flowing': INK.permits,
  'busy but walkable': '#f5b301',
  'constrained, slow walking': INK.incidents,
  'congested, queuing likely': INK.complaints,
};

export function EventsPanel() {
  const {
    eventVenue, eventAttendance, eventHour, eventReport, eventLoading,
    setEventQuery, setEventReport, setEventLoading, setEventOrigins, setMarkers,
  } = useApp();

  const run = async () => {
    setEventLoading(true);
    try {
      const report = await api.event(eventVenue, eventAttendance, eventHour);
      setEventReport(report);
      setEventOrigins(report.attendeeHomeSample ?? []);
      setMarkers([
        {
          label: eventVenue,
          lon: report.event.venue[0],
          lat: report.event.venue[1],
          kind: 'event',
        },
      ]);
      (window as unknown as Record<string, unknown> & {
        __setView?: (c: [number, number], z: number) => void;
      }).__setView?.([report.event.venue[0], report.event.venue[1]], 14.2);
    } catch {
      setEventReport(null);
    }
  };

  const [live, setLive] = useState<LiveEvent[]>([]);
  const [liveNote, setLiveNote] = useState('');

  useEffect(() => {
    api
      .liveEvents(45)
      .then((r) => {
        setLive(r.events ?? []);
        setLiveNote(r.note ?? '');
      })
      .catch(() => undefined);
  }, []);

  const arrivals = eventReport?.arrivalByQuarterHour ?? [];
  const peakArrival = Math.max(...arrivals.map((a) => a.people), 1);

  return (
    <div className="card-paper flex flex-col px-4 py-3">
      <div className="eyebrow mb-2 text-[var(--color-ink-soft)]">Plan an event</div>

      <div className="space-y-1.5">
        <input
          value={eventVenue}
          onChange={(e) => setEventQuery(e.target.value, eventAttendance, eventHour)}
          list="venues"
          placeholder="Venue"
          className="w-full rounded-[8px] border border-[var(--color-hairline)] bg-white px-2 py-1.5 text-[12px] outline-none focus:border-[var(--color-ink-blue)]"
        />
        <datalist id="venues">
          {VENUES.map((v) => (
            <option key={v} value={v} />
          ))}
        </datalist>

        <div className="flex gap-1.5">
          <label className="flex flex-1 items-center gap-1.5 rounded-[8px] border border-[var(--color-hairline)] bg-white px-2 py-1.5">
            <span className="text-[10px] text-[var(--color-ink-soft)]">People</span>
            <input
              type="number"
              step={1000}
              value={eventAttendance}
              onChange={(e) =>
                setEventQuery(eventVenue, Number(e.target.value), eventHour)
              }
              className="tnum w-full min-w-0 bg-transparent text-right text-[12px] outline-none"
            />
          </label>
          <label className="flex items-center gap-1.5 rounded-[8px] border border-[var(--color-hairline)] bg-white px-2 py-1.5">
            <span className="text-[10px] text-[var(--color-ink-soft)]">Start</span>
            <input
              type="number"
              min={0}
              max={23}
              value={eventHour}
              onChange={(e) =>
                setEventQuery(eventVenue, eventAttendance, Number(e.target.value))
              }
              className="tnum w-9 bg-transparent text-right text-[12px] outline-none"
            />
          </label>
          <button
            type="button"
            onClick={run}
            disabled={eventLoading}
            className="flex items-center gap-1 rounded-[8px] bg-[var(--color-ink-blue)] px-2.5 text-[12px] font-medium text-white disabled:opacity-40"
          >
            {eventLoading ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
          </button>
        </div>
      </div>

      {!!live.length && (
        <div className="mt-3 border-t border-[var(--color-hairline)] pt-2.5">
          <div className="eyebrow mb-1.5 flex items-center gap-1.5 text-[var(--color-ink-soft)]">
            <CalendarDays size={11} /> Real fixtures coming up
          </div>
          <div className="max-h-[132px] space-y-0.5 overflow-y-auto">
            {live.slice(0, 8).map((e) => (
              <button
                key={`${e.name}-${e.startsAt}`}
                type="button"
                onClick={() => {
                  setEventQuery(
                    e.venue,
                    e.expectedAttendance ?? 15000,
                    new Date(e.startsAt).getHours(),
                  );
                }}
                className="flex w-full items-baseline gap-2 rounded-[8px] px-1.5 py-1 text-left text-[11px] hover:bg-white"
              >
                <span className="tnum shrink-0 text-[var(--color-ink-soft)]">
                  {new Date(e.startsAt).toLocaleDateString(undefined, {
                    month: 'short',
                    day: 'numeric',
                  })}
                </span>
                <span className="truncate">{e.name}</span>
                <span className="tnum ml-auto shrink-0 text-[var(--color-ink-soft)]">
                  {(e.expectedAttendance ?? 0).toLocaleString()}
                </span>
              </button>
            ))}
          </div>
          {liveNote && (
            <p className="mt-1.5 text-[10px] leading-snug text-[var(--color-ink-soft)]">
              {liveNote}
            </p>
          )}
        </div>
      )}

      {!eventReport && !eventLoading && (
        <p className="mt-3 text-[11.5px] leading-relaxed text-[var(--color-ink-soft)]">
          Pick a fixture or type a venue, then run it to see who would come, from
          where, and which blocks fill up before the doors open.
        </p>
      )}

      {eventReport && (
        <div className="mt-3 max-h-[44vh] space-y-3 overflow-y-auto">
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
            <span className="text-[var(--color-ink-soft)]">From within the city</span>
            <span className="tnum text-right">
              {eventReport.modelledFromResidents.toLocaleString()}
            </span>
            <span className="text-[var(--color-ink-soft)]">Assumed from outside</span>
            <span className="tnum text-right">
              {eventReport.assumedFromOutsideTheCity.toLocaleString()}
            </span>
          </div>

          <div>
            <div className="eyebrow mb-1 text-[var(--color-ink-soft)]">Likely mode</div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
              {Object.entries(eventReport.likelyMode).map(([mode, people]) => (
                <>
                  <span key={`${mode}-l`} className="text-[var(--color-ink-soft)]">
                    {mode === 'fromOutside' ? 'from outside' : mode}
                  </span>
                  <span key={`${mode}-v`} className="tnum text-right">
                    {people.toLocaleString()}
                  </span>
                </>
              ))}
            </div>
          </div>

          <div>
            <div className="eyebrow mb-1 text-[var(--color-ink-soft)]">Arrivals</div>
            <div className="flex h-10 items-end gap-[2px]">
              {arrivals.map((a) => (
                <div
                  key={a.minute}
                  title={`${String(Math.floor(a.minute / 60)).padStart(2, '0')}:${String(
                    a.minute % 60,
                  ).padStart(2, '0')} — ${a.people.toLocaleString()}`}
                  className="flex-1 rounded-t-[2px]"
                  style={{
                    height: `${Math.max(3, (a.people / peakArrival) * 100)}%`,
                    background: INK.events,
                  }}
                />
              ))}
            </div>
          </div>

          <div>
            <div className="eyebrow mb-1 text-[var(--color-ink-soft)]">Crowding</div>
            <div className="space-y-1">
              {eventReport.crowding.map((ring) => (
                <div key={ring.ring} className="flex items-baseline gap-2 text-[11px]">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ background: COMFORT_INK[ring.comfort] ?? INK.people }}
                  />
                  <span className="truncate text-[var(--color-ink-soft)]">{ring.ring}</span>
                  <span className="tnum ml-auto shrink-0">
                    {ring.people.toLocaleString()}
                  </span>
                </div>
              ))}
              <div className="text-[10px] text-[var(--color-ink-soft)]">
                {eventReport.crowding[0]?.comfort} at the doors
              </div>
            </div>
          </div>

          {!!eventReport.businessUplift.length && (
            <div>
              <div className="eyebrow mb-1 text-[var(--color-ink-soft)]">
                Businesses in the crowd
              </div>
              <div className="space-y-0.5">
                {eventReport.businessUplift.slice(0, 5).map((b) => (
                  <div key={b.category} className="flex justify-between gap-2 text-[11px]">
                    <span className="text-[var(--color-ink-soft)]">
                      {b.category.replace('_', ' ')} ({b.places})
                    </span>
                    <span className="tnum">~{b.peoplePerPlace.toLocaleString()} each</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <p className="border-t border-[var(--color-hairline)] pt-2 text-[10px] leading-snug text-[var(--color-ink-soft)]">
            {eventReport.method}
          </p>
        </div>
      )}
    </div>
  );
}
