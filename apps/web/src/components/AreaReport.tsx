/**
 * The click-anywhere report.
 *
 * One panel answering what a place is like: how busy it gets, what people
 * complain about, what the police record, what is being built, what is empty,
 * and what is already there. Modelled and recorded numbers are labelled
 * separately throughout, because mixing them is how a model starts being
 * quoted as measurement.
 */
import { Loader2 } from 'lucide-react';

import type { AreaReport as Report } from '../lib/api';
import { categoryColour, INK } from '../lib/palette';
import { useApp } from '../state/appStore';

function HourBars({ values, peak }: { values: number[]; peak: number }) {
  const max = Math.max(...values, 1);
  return (
    <div className="flex h-12 items-end gap-[2px]">
      {values.map((v, h) => (
        <div
          key={h}
          title={`${String(h).padStart(2, '0')}:00 — ${v.toLocaleString()} people`}
          className="flex-1 rounded-t-[2px] transition-all"
          style={{
            height: `${Math.max(2, (v / max) * 100)}%`,
            background: h === peak ? INK.people : 'rgba(35,35,229,0.28)',
          }}
        />
      ))}
    </div>
  );
}

function Section({
  colour,
  title,
  window,
  total,
  children,
}: {
  colour: string;
  title: string;
  window?: string;
  total?: number;
  children?: React.ReactNode;
}) {
  return (
    <div className="border-t border-[var(--color-hairline)] pt-2.5">
      <div className="flex items-baseline gap-2">
        <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: colour }} />
        <span className="text-[12px] font-semibold">{title}</span>
        {total !== undefined && (
          <span className="tnum ml-auto text-[13px] font-semibold">
            {total.toLocaleString()}
          </span>
        )}
      </div>
      {window && (
        <div className="mb-1 pl-4 text-[10px] text-[var(--color-ink-soft)]">{window}</div>
      )}
      <div className="pl-4">{children}</div>
    </div>
  );
}

function TopList({ items }: { items?: { name: string; count: number }[] }) {
  if (!items?.length) return null;
  return (
    <div className="space-y-0.5">
      {items.slice(0, 4).map((t) => (
        <div key={t.name} className="flex justify-between gap-2 text-[11px]">
          <span className="truncate text-[var(--color-ink-soft)]">{t.name}</span>
          <span className="tnum shrink-0">{t.count.toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
}

export function AreaReportCard({ report }: { report: Report }) {
  const s = report.sections;
  const land = s.landUse;

  return (
    <div className="space-y-3">
      <div>
        <div className="eyebrow text-[var(--color-ink-soft)]">
          Modelled footfall, peak {String(report.footfall.peakHour).padStart(2, '0')}:00
        </div>
        <div className="tnum mb-1 text-[22px] font-semibold leading-tight">
          {report.footfall.peopleAtPeak.toLocaleString()}
          <span className="ml-1.5 text-[11px] font-normal text-[var(--color-ink-soft)]">
            people at peak
          </span>
        </div>
        <HourBars values={report.footfall.byHour} peak={report.footfall.peakHour} />
        <div className="mt-1 text-[10px] leading-snug text-[var(--color-ink-soft)]">
          Simulation output within 150 m, averaged per simulated minute. Hours not
          yet reached read zero.
        </div>
      </div>

      {s.complaints && (
        <Section
          colour={INK.complaints}
          title="311 complaints"
          window={`${s.complaints.window}${
            s.complaints.stillOpen ? ` · ${s.complaints.stillOpen.toLocaleString()} still open` : ''
          }`}
          total={s.complaints.total}
        >
          <TopList items={s.complaints.top} />
        </Section>
      )}

      {s.incidents && (
        <Section
          colour={INK.incidents}
          title="Police incidents"
          window={s.incidents.window}
          total={s.incidents.total}
        >
          <TopList items={s.incidents.top} />
        </Section>
      )}

      {s.vacancy && (
        <Section
          colour={INK.vacancy}
          title="Commercial vacancy"
          window={s.vacancy.window}
          total={s.vacancy.total}
        >
          {!!s.vacancy.addresses?.length && (
            <div className="space-y-0.5">
              {s.vacancy.addresses.slice(0, 3).map((a) => (
                <div key={a} className="truncate text-[11px] text-[var(--color-ink-soft)]">
                  {a}
                </div>
              ))}
            </div>
          )}
        </Section>
      )}

      {s.permits && (
        <Section
          colour={INK.permits}
          title="Building permits"
          window={s.permits.window}
          total={s.permits.total}
        >
          {!!s.permits.proposedUnits && (
            <div className="text-[11px] text-[var(--color-ink-soft)]">
              {s.permits.proposedUnits.toLocaleString()} homes proposed
            </div>
          )}
        </Section>
      )}

      {land && (
        <Section colour="#6b6b73" title="Land use and property" total={land.parcels}>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
            <Fact label="Homes" value={land.residentialUnits} />
            <Fact label="Retail sq ft" value={land.retailSqFt} />
            <Fact label="Office sq ft" value={land.officeSqFt} />
            <Fact label="Built" value={land.medianYearBuilt} plain />
          </div>
        </Section>
      )}

      {!!report.places.length && (
        <Section colour={INK.people} title="Places nearby">
          <div className="space-y-1">
            {report.places.slice(0, 6).map((p) => (
              <div key={`${p.name}-${p.lon}`} className="flex items-baseline gap-2 text-[11px]">
                <span
                  className="h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ background: categoryColour(p.category) }}
                />
                <span className="truncate">{p.name}</span>
                {p.rating !== undefined && (
                  <span className="tnum ml-auto shrink-0 text-[var(--color-ink-soft)]">
                    {p.rating.toFixed(1)}
                    {p.reviews ? ` · ${p.reviews.toLocaleString()}` : ''}
                  </span>
                )}
              </div>
            ))}
          </div>
          {report.places.some((p) => p.rating === undefined) && (
            <div className="mt-1 text-[10px] text-[var(--color-ink-soft)]">
              Ratings appear once Google enrichment has been run.
            </div>
          )}
        </Section>
      )}
    </div>
  );
}

function Fact({ label, value, plain }: { label: string; value?: number; plain?: boolean }) {
  if (value === undefined || (!plain && !value)) return null;
  return (
    <>
      <span className="text-[var(--color-ink-soft)]">{label}</span>
      <span className="tnum text-right">{plain ? value : value.toLocaleString()}</span>
    </>
  );
}

export function AreaPanel() {
  const { report, reportLoading, reportPoint } = useApp();

  if (reportLoading) {
    return (
      <div className="card-paper flex items-center gap-2 px-4 py-4 text-[12px] text-[var(--color-ink-soft)]">
        <Loader2 size={13} className="animate-spin" /> Reading this block…
      </div>
    );
  }

  if (!report) {
    return (
      <div className="card-paper px-4 py-4">
        <div className="text-[12px] font-semibold">Click anywhere on the map</div>
        <p className="mt-1 text-[11.5px] leading-relaxed text-[var(--color-ink-soft)]">
          You will get modelled footfall by hour, what people report to 311, what
          the police record, what is being built, what sits empty, and the places
          already there.
        </p>
      </div>
    );
  }

  return (
    <div className="card-paper px-4 py-3">
      <div className="mb-2 flex items-baseline justify-between">
        <div className="text-[12px] font-semibold">This block</div>
        {reportPoint && (
          <div className="tnum text-[10px] text-[var(--color-ink-soft)]">
            {reportPoint[1].toFixed(4)}, {reportPoint[0].toFixed(4)}
          </div>
        )}
      </div>
      <AreaReportCard report={report} />
    </div>
  );
}
