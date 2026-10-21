import { useSyncExternalStore } from "react";

// The home page's engraving: a ruled frame like an atlas plate, and a wireframe globe whose
// meridians turn slowly while a small citation graph draws itself across it. Pure SVG/CSS in
// the theme's accent (gold on black, olive on beige); decorative only, hidden from AT.

const R = 230; // globe radius in viewBox units

// a small citation graph on the globe — two clusters above and below the title band,
// joined by a few long edges (the "bridges" ATLAS looks for)
const NODES: Record<string, [number, number, number]> = {
  a: [-150, -120, 3], b: [-60, -175, 4.5], c: [50, -150, 3], d: [140, -110, 3.5], e: [-10, -95, 2.5],
  f: [-130, 120, 3.5], g: [-30, 160, 3], h: [80, 130, 4.5], i: [160, 90, 3], j: [20, 205, 2.5],
};
const EDGES = ["ab", "bc", "cd", "be", "ec", "ae", "fg", "gh", "hi", "gj", "hj", "eg", "di", "af"];
const PULSING = new Set(["b", "h"]);
const MERIDIANS = 6;
const PARALLELS = [-60, -35, 0, 35, 60];
const TICKS = Array.from({ length: 120 }, (_, k) => k * 3);

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (l) => {
      reducedMotion.addEventListener("change", l);
      return () => reducedMotion.removeEventListener("change", l);
    },
    () => reducedMotion.matches,
  );
}

function Orbit({ rx, ry, tilt, dur, reverse, still }: {
  rx: number; ry: number; tilt: number; dur: number; reverse?: boolean; still: boolean;
}) {
  const sweep = reverse ? 0 : 1;
  const path = `M ${-rx} 0 A ${rx} ${ry} 0 1 ${sweep} ${rx} 0 A ${rx} ${ry} 0 1 ${sweep} ${-rx} 0`;
  return (
    <g transform={`rotate(${tilt})`}>
      <ellipse rx={rx} ry={ry} fill="none" stroke="currentColor" strokeOpacity={0.35} strokeWidth={0.8} strokeDasharray="1 6" strokeLinecap="round" />
      <circle r={3.5} fill="currentColor" fillOpacity={0.9} cx={still ? rx : undefined}>
        {!still && <animateMotion dur={`${dur}s`} repeatCount="indefinite" path={path} />}
      </circle>
    </g>
  );
}

function Globe() {
  const still = useReducedMotion();
  return (
    <svg viewBox="-320 -320 640 640" className="h-full w-full text-accent-500" aria-hidden="true">
      {/* astrolabe ring with degree ticks */}
      <circle r={300} fill="none" stroke="currentColor" strokeOpacity={0.45} strokeWidth={1} pathLength={1} className="atlas-draw" />
      <circle r={290} fill="none" stroke="currentColor" strokeOpacity={0.22} strokeWidth={0.6} />
      <g stroke="currentColor" strokeOpacity={0.3} strokeWidth={0.7} className="atlas-fade-slow">
        {TICKS.map((deg) => {
          const len = deg % 30 === 0 ? 14 : deg % 15 === 0 ? 9 : 5;
          const t = (deg * Math.PI) / 180;
          return (
            <line key={deg} x1={290 * Math.cos(t)} y1={290 * Math.sin(t)} x2={(290 - len) * Math.cos(t)} y2={(290 - len) * Math.sin(t)} />
          );
        })}
      </g>

      {/* the sphere: outline, parallels, and meridians that turn */}
      <g fill="none" stroke="currentColor" className="atlas-fade-slow">
        <circle r={R} strokeOpacity={0.4} strokeWidth={0.9} />
        {PARALLELS.map((lat) => {
          const t = (lat * Math.PI) / 180;
          const rx = R * Math.cos(t);
          return (
            <ellipse key={lat} cy={R * Math.sin(t)} rx={rx} ry={rx * 0.16} strokeOpacity={lat === 0 ? 0.32 : 0.18} strokeWidth={0.7} />
          );
        })}
        {Array.from({ length: MERIDIANS }, (_, k) => (
          <ellipse
            key={k}
            rx={R}
            ry={R}
            strokeOpacity={0.2}
            strokeWidth={0.7}
            vectorEffect="non-scaling-stroke"
            className="atlas-meridian"
            style={{
              animationDelay: `${(-36 / (2 * MERIDIANS)) * k}s`,
              ["--sx" as string]: Math.cos((k * Math.PI) / MERIDIANS).toFixed(3),
            }}
          />
        ))}
      </g>

      {/* citation graph: edges draw in, two "read" papers pulse */}
      <g stroke="currentColor" strokeOpacity={0.45} strokeWidth={0.9}>
        {EDGES.map((pair, k) => {
          const [x1, y1] = NODES[pair[0]];
          const [x2, y2] = NODES[pair[1]];
          return (
            <line key={pair} x1={x1} y1={y1} x2={x2} y2={y2} pathLength={1} className="atlas-draw" style={{ animationDelay: `${0.6 + k * 0.12}s` }} />
          );
        })}
      </g>
      <g fill="currentColor">
        {Object.entries(NODES).map(([id, [x, y, r]]) => (
          <g key={id} transform={`translate(${x} ${y})`}>
            {PULSING.has(id) && <circle r={r + 5} fill="none" stroke="currentColor" strokeOpacity={0.6} strokeWidth={0.8} className="atlas-pulse" />}
            <circle r={r} fillOpacity={0.85} className="atlas-fade-slow" />
          </g>
        ))}
      </g>

      <Orbit rx={300} ry={84} tilt={-18} dur={48} still={still} />
      <Orbit rx={262} ry={58} tilt={22} dur={64} reverse still={still} />
    </svg>
  );
}

function Diamond({ className }: { className: string }) {
  return <span className={`absolute h-2 w-2 rotate-45 border border-accent-500 bg-ink-950 ${className}`} />;
}

/** The ruled frame. Its top-left corner is where the sidebar's menu button sits (32px). */
function Frame() {
  return (
    <div aria-hidden="true" className="atlas-fade-slow pointer-events-none fixed inset-0 z-0">
      <div className="absolute inset-8 border border-ink-700/80" />
      <div className="absolute inset-[38px] border border-ink-800" />
      <div className="atlas-ruler-x absolute top-[39px] right-16 left-16 h-1 text-ink-700" />
      <div className="atlas-ruler-x-major absolute top-[39px] right-16 left-16 h-2.5 text-ink-600" />
      <div className="atlas-ruler-x absolute right-16 bottom-[39px] left-16 h-1 text-ink-700" />
      <div className="atlas-ruler-x-major absolute right-16 bottom-[39px] left-16 h-2.5 text-ink-600" />
      <div className="atlas-ruler-y absolute top-16 bottom-16 left-[39px] hidden w-1 text-ink-700 sm:block" />
      <div className="atlas-ruler-y absolute top-16 right-[39px] bottom-16 hidden w-1 text-ink-700 sm:block" />
      <Diamond className="top-8 right-8 translate-x-1/2 -translate-y-1/2" />
      <Diamond className="bottom-8 left-8 -translate-x-1/2 translate-y-1/2" />
      <Diamond className="right-8 bottom-8 translate-x-1/2 translate-y-1/2" />
    </div>
  );
}

export { Frame, Globe };
