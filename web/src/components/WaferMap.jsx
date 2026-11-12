import React, { useEffect, useMemo, useState } from "react";
import { useT } from "../i18n.js";
import Clearance from "./Clearance.jsx";

// The permission wafer map: one die per document (192), laid out on a round wafer.
// Visible dies are lit, locked dies are grey with a hatch; retrieved dies are amber and the
// cited ones get an outline. After each question the map plays the page's only automatic
// animation, in the order the system works (~1.4 s): first the permission pre-filter dims the
// locked dies, then the retrieved dies light up, then the cited ones get their outline.
// Under prefers-reduced-motion, and on identity switches, the final state is shown at once.

const PHASE_AT = [0, 60, 560, 1060]; // ms after a new answer: 0 unfiltered, 1 filtered, 2 retrieved, 3 cited
const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

const CELL = 14;
const GAP = 2;

// Every document die lies entirely inside the wafer edge (all four corners), as on a real wafer
// where only complete dies are usable. Grid cells whose centre is inside but a corner is not are
// drawn as partial edge dies, clipped to the wafer, and carry no document.
const EDGE = 2; // px kept clear inside the wafer outline

function layout(count) {
  for (let n = 10; n < 40; n++) {
      const size = n * (CELL + GAP) + GAP;
    const c = size / 2;
    const R = size / 2 - EDGE;
    const inside = (px, py) => (px - c) ** 2 + (py - c) ** 2 <= R * R;
    const cells = [];
    const partial = [];
    for (let y = 0; y < n; y++)
      for (let x = 0; x < n; x++) {
        const x0 = GAP + x * (CELL + GAP);
        const y0 = GAP + y * (CELL + GAP);
        const corners = [
          [x0, y0],
          [x0 + CELL, y0],
          [x0, y0 + CELL],
          [x0 + CELL, y0 + CELL],
        ];
        if (corners.every(([a, b]) => inside(a, b))) cells.push({ x, y });
        else if (inside(x0 + CELL / 2, y0 + CELL / 2)) partial.push({ x, y });
      }
    if (cells.length >= count) return { n, size, cells, partial };
  }
  throw new Error("too many dies");
}


export default function WaferMap({ docs, retrieved = [], cited = [], focusId, onFocus, runKey }) {
  const t = useT();
  const [phase, setPhase] = useState(3);
  useEffect(() => {
    if (!runKey || reducedMotion()) {
      setPhase(3);
      return undefined;
    }
    setPhase(0);
    const timers = PHASE_AT.slice(1).map((ms, i) => setTimeout(() => setPhase(i + 1), ms));
    return () => timers.forEach(clearTimeout);
  }, [runKey]);
  const { size, cells, partial } = useMemo(() => layout(docs.length || 192), [docs.length]);
  const [hover, setHover] = useState(null);
  const retrievedSet = new Set(retrieved);
  const citedSet = new Set(cited);
  const visibleCount = docs.filter((d) => d.visible).length;
  const extra = retrieved.filter((id) => !docs.some((d) => d.doc_id === id));
  const shown = hover !== null ? docs[hover] : focusId ? docs.find((d) => d.doc_id === focusId) : null;

  return (
    <div className="wafer">
      <div className="wafer-stage">
        <svg
          className={phase < 3 ? "wafer-animating" : ""}
          viewBox={`0 0 ${size} ${size + 10}`}
          role="img"
          aria-label={t("wafer.aria", { total: docs.length, visible: visibleCount, retrieved: retrievedSet.size })}
          onMouseLeave={() => setHover(null)}
        >
          <defs>
            <pattern id="hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="4" className="hatch-line" />
            </pattern>
            <clipPath id="wafer-clip">
              <circle cx={size / 2} cy={size / 2} r={size / 2 - EDGE} />
            </clipPath>
          </defs>
          <circle cx={size / 2} cy={size / 2} r={size / 2 - 1} className="wafer-disc" />
          <g clipPath="url(#wafer-clip)" aria-hidden="true">
            {partial.map((c) => (
              <rect
                key={`p${c.x}-${c.y}`}
                x={GAP + c.x * (CELL + GAP)}
                y={GAP + c.y * (CELL + GAP)}
                width={CELL}
                height={CELL}
                rx="1.5"
                className="die-partial"
              />
            ))}
          </g>
          <path
            d={`M ${size / 2 - 7} ${size - 1} a 7 7 0 0 1 14 0`}
            className="wafer-notch"
          />
          {cells.map((c, i) => {
            const doc = docs[i];
            const x = GAP + c.x * (CELL + GAP);
            const y = GAP + c.y * (CELL + GAP);
            if (!doc) return <rect key={i} x={x} y={y} width={CELL} height={CELL} rx="2" className="die die-edge" />;
            const state = !doc.visible
              ? phase >= 1
                ? "locked"
                : "visible"
              : citedSet.has(doc.doc_id) && phase >= 2
                ? phase >= 3
                  ? "cited"
                  : "retrieved"
                : retrievedSet.has(doc.doc_id) && phase >= 2
                  ? "retrieved"
                  : "visible";
            const focus = doc.doc_id && doc.doc_id === focusId;
            return (
              <g key={i} onMouseEnter={() => setHover(i)} onClick={() => doc.visible && onFocus?.(doc.doc_id)}>
                <rect
                  x={x}
                  y={y}
                  width={CELL}
                  height={CELL}
                  rx={doc.doc_type === "incident" ? 5 : 1.5}
                  className={`die die-${state} ${doc.doc_type === "sop" ? "die-sop" : ""} ${focus && phase >= 3 ? "die-focus" : ""}`}
                />
                {!doc.visible && (
                  <rect
                    x={x}
                    y={y}
                    width={CELL}
                    height={CELL}
                    rx="2"
                    fill="url(#hatch)"
                    className={`die-hatch ${phase >= 1 ? "" : "die-hatch-off"}`}
                  />
                )}
              </g>
            );
          })}
        </svg>
      </div>
      {runKey && (
        <ol className="wafer-phases" aria-hidden="true">
          {[1, 2, 3].map((p) => (
            <li key={p} className={phase >= p ? "on" : ""}>
              {t(`wafer.phase${p}`)}
            </li>
          ))}
        </ol>
      )}
      <div className="wafer-info" aria-live="polite">
        {shown ? (
          shown.visible ? (
            <>
              <span className="code">{shown.doc_id}</span>
              <span>
                {shown.doc_type === "sop" ? t("wafer.sop") : t("wafer.incident")} · {shown.fab} · {shown.department}{" "}
                <Clearance level={shown.clearance} />
                {shown.superseded_by ? t("wafer.superseded") : ""}
                {citedSet.has(shown.doc_id) ? t("wafer.cited") : retrievedSet.has(shown.doc_id) ? t("wafer.retrieved") : ""}
              </span>
            </>
          ) : (
            <span>{t("wafer.locked")}</span>
          )
        ) : (
          <span>{t("wafer.hint")}</span>
        )}
      </div>
      <ul className="wafer-legend">
        <li><i className="sw sw-visible" />{t("wafer.visible", { n: visibleCount })}</li>
        <li><i className="sw sw-locked" />{t("wafer.lockedN", { n: docs.length - visibleCount })}</li>
        <li><i className="sw sw-retrieved" />{t("wafer.retrievedN", { n: retrieved.length - extra.length })}</li>
        <li><i className="sw sw-cited" />{t("wafer.citedL")}</li>
        <li className="legend-shape">{t("wafer.shape")}</li>
      </ul>
      <ul className="clr-legend" aria-label={t("clr.legend")}>
        <li className="fine">{t("clr.legend")}</li>
        {[0, 1, 2, 3].map((l) => (
          <li key={l}>
            <Clearance level={l} />
          </li>
        ))}
      </ul>
      {extra.length > 0 && (
        <p className="fine">{t("wafer.extra", { n: extra.length, ids: extra.join(", ") })}</p>
      )}
    </div>
  );
}
