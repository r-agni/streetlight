/**
 * Layer switches and the legend.
 *
 * Each city dataset gets its own ink, so a map with two layers on is still
 * readable. Counts are shown next to every switch, and a layer that had to be
 * thinned to draw says so, because a sparse-looking map that is actually a
 * sample would be read as a quiet neighbourhood.
 */
import { useEffect } from 'react';

import { api } from '../lib/api';
import { CATEGORY_GROUPS, INK } from '../lib/palette';
import { useApp } from '../state/appStore';

const LAYER_INK: Record<string, string> = {
  complaints: INK.complaints,
  incidents: INK.incidents,
  vacancy: INK.vacancy,
  permits: INK.permits,
};

function Switch({
  on,
  colour,
  label,
  detail,
  onClick,
}: {
  on: boolean;
  colour: string;
  label: string;
  detail?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'flex w-full items-center gap-2.5 rounded-[9px] px-2 py-1.5 text-left transition-colors',
        on ? 'bg-white' : 'hover:bg-white/60',
      ].join(' ')}
    >
      <span
        className="h-2.5 w-2.5 shrink-0 rounded-full border"
        style={{
          background: on ? colour : 'transparent',
          borderColor: colour,
        }}
      />
      <span className="flex-1 text-[12px] leading-tight">{label}</span>
      {detail && (
        <span className="tnum text-[10px] text-[var(--color-ink-soft)]">{detail}</span>
      )}
    </button>
  );
}

export function LayerPanel() {
  const {
    layers,
    layerData,
    activeLayers,
    showPlaces,
    setLayers,
    setLayerData,
    toggleLayer,
    setShowPlaces,
  } = useApp();

  useEffect(() => {
    api.layers().then((r) => setLayers(r.layers)).catch(() => undefined);
  }, [setLayers]);

  // fetch a layer's points the first time it is switched on
  useEffect(() => {
    for (const id of activeLayers) {
      if (!layerData[id]) {
        api.layerPoints(id).then((d) => setLayerData(id, d)).catch(() => undefined);
      }
    }
  }, [activeLayers, layerData, setLayerData]);

  return (
    <div className="card-paper px-4 py-3">
      <div className="eyebrow mb-2 text-[var(--color-ink-soft)]">City data</div>

      <div className="space-y-0.5">
        {layers.map((layer) => {
          const data = layerData[layer.id];
          return (
            <Switch
              key={layer.id}
              on={activeLayers.has(layer.id)}
              colour={LAYER_INK[layer.id] ?? INK.people}
              label={layer.label}
              detail={
                activeLayers.has(layer.id) && data?.thinned
                  ? `${data.count.toLocaleString()} of ${layer.count.toLocaleString()}`
                  : layer.count.toLocaleString()
              }
              onClick={() => toggleLayer(layer.id)}
            />
          );
        })}
        <Switch
          on={showPlaces}
          colour="#6b6b73"
          label="Places by type"
          onClick={() => setShowPlaces(!showPlaces)}
        />
      </div>

      {showPlaces && (
        <div className="mt-3 border-t border-[var(--color-hairline)] pt-2.5">
          <div className="eyebrow mb-1.5 text-[var(--color-ink-soft)]">Place types</div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1">
            {Object.entries(CATEGORY_GROUPS).map(([key, group]) => (
              <div key={key} className="flex items-center gap-1.5">
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ background: group.colour }}
                />
                <span className="text-[10.5px] text-[var(--color-ink-soft)]">
                  {group.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {[...activeLayers].some((id) => layerData[id]?.thinned) && (
        <p className="mt-2.5 text-[10px] leading-snug text-[var(--color-ink-soft)]">
          Dense layers are drawn from an evenly spaced sample. Counts in reports
          use every record.
        </p>
      )}
    </div>
  );
}
