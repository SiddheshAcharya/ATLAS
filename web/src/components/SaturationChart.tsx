import type { TimelinePoint } from "../lib/types";

// Dependency-free inline SVG line chart — [S] stretch item (docs/ROADMAP.md Phase 6).
// Deliberately not pulling in a charting library for two lines over <=200 points.

function Sparkline({
  values, color, width, height,
}: { values: number[]; width: number; height: number; color: string }) {
  if (values.length < 2) return null;
  const max = Math.max(...values, 1e-9);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((v - min) / span) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <polyline
      points={points}
      fill="none"
      style={{ stroke: color }} // a CSS var — SVG presentation attributes cannot resolve var()
      strokeWidth={1.5}
      strokeLinejoin="round"
      strokeLinecap="round"
    />
  );
}

function Chart({
  title, values, color, format,
}: { title: string; values: number[]; color: string; format: (v: number) => string }) {
  const width = 260;
  const height = 64;
  const last = values[values.length - 1];
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between text-xs text-ink-500">
        <span>{title}</span>
        <span className="font-mono text-ink-300">{last !== undefined ? format(last) : "—"}</span>
      </div>
      <svg width={width} height={height} className="rounded bg-ink-900/60">
        <Sparkline values={values} width={width} height={height} color={color} />
      </svg>
    </div>
  );
}

export default function SaturationChart({ points }: { points: TimelinePoint[] }) {
  if (points.length < 2) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-ink-500">
        Not enough reads yet to chart saturation.
      </div>
    );
  }
  const emaValues = points.map((p) => p.ema ?? 0);
  const claimValues = points.map((p) => p.cumulative_claims);
  const usdValues = points.map((p) => p.cumulative_usd);
  const hasCost = usdValues.some((v) => v > 0);

  return (
    <div className="flex flex-col gap-4 p-3">
      <Chart
        title={`saturation (EMA of new info, ${points.length} reads)`}
        values={emaValues}
        color="var(--color-accent-500)"
        format={(v) => v.toFixed(2)}
      />
      <Chart
        title="cumulative claims"
        values={claimValues}
        color="var(--color-emerald-500)"
        format={(v) => String(Math.round(v))}
      />
      {hasCost ? (
        <Chart
          title="cumulative cost (USD)"
          values={usdValues}
          color="var(--color-amber-500)"
          format={(v) => `$${v.toFixed(4)}`}
        />
      ) : (
        <p className="text-xs text-ink-600">
          Cost data unavailable for this run (recorded before the timeline event carried it).
        </p>
      )}
    </div>
  );
}
