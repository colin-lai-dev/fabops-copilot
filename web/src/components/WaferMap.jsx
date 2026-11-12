import React, { useMemo, useState } from "react";
import { useT } from "../i18n.js";
import Clearance, { CLEARANCE } from "./Clearance.jsx";

// The permission wafer map of one identity: one die per document (192). A document this
// identity may see is a solid die; one it may not see is only a small dot, with no id or
// attribute behind it. Retrieved dies are amber, cited dies get a ring.
// `phase` (0 unfiltered, 1 filtered, 2 retrieved, 3 cited) is driven by the page, in step with
// the six small wafers of the lot.

export const CELL = 14;
export const GAP = 2;
const EDGE = 2; // px kept clear inside the wafer outline

// Every document die lies entirely inside the wafer edge (all four corners), as on a real wafer
// where only complete dies are usable.
export function layout(count) {
  for (let n = 10; n < 40; n++) {
    const size = n * (CELL + GAP) + GAP;
    const c = size / 2;
    const R = size / 2 - EDGE;
    const inside = (px, py) => (px - c) ** 2 + (py - c) ** 2 <= R * R;
    const cells = [];
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
        if (corners.every(([a, b]) => inside(a, b))) cells.push({ x: x0, y: y0 });
      }
    if (cells.length >= count) return { size, cells };
  }
  throw new Error("too many dies");
}

export function Disc({ size }) {
  return (
    <path
      className="wafer-disc"
      d={`M ${size / 2 - 7} ${size - 1.6} A ${size / 2 - 1} ${size / 2 - 1} 0 1 1 ${size / 2 + 7} ${size - 1.6} A 7 7 0 0 0 ${size / 2 - 7} ${size - 1.6} Z`}
    />
  );
}

export default function WaferMap({ docs, retrieved = [], cited = [], focusId, onFocus, phase = 3, animating = false }) {
  const t = useT();
  const { size, cells } = useMemo(() => layout(docs.length || 192), [docs.length]);
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
          className={animating ? "wafer-animating" : ""}
          viewBox={`0 0 ${size} ${size}`}
          role="img"
          aria-label={t("wafer.aria", { total: docs.length, visible: visibleCount, retrieved: retrievedSet.size })}
          onMouseLeave={() => setHover(null)}
        >
          <Disc size={size} />
          {cells.slice(0, docs.length).map((c, i) => {
            const doc = docs[i];
            const locked = !doc.visible && phase >= 1;
            const state = !doc.visible
              ? locked
                ? "locked"
                : "visible"
              : citedSet.has(doc.doc_id) && phase >= 2
                ? phase >= 3
                  ? "cited"
                  : "retrieved"
                : retrievedSet.has(doc.doc_id) && phase >= 2
                  ? "retrieved"
                  : "visible";
            const focus = doc.doc_id && doc.doc_id === focusId && phase >= 3;
            return (
              <g key={i} onMouseEnter={() => setHover(i)} onClick={() => doc.visible && onFocus?.(doc.doc_id)}>
                <title>
                  {doc.visible
                    ? `${doc.doc_id} · ${doc.fab} · ${doc.department} · ${CLEARANCE[doc.clearance]}`
                    : t("wafer.lockedTip")}
                </title>
                {/* the full cell is the hover target; a locked die only draws a dot */}
                <rect x={c.x - 1} y={c.y - 1} width={CELL + 2} height={CELL + 2} fill="transparent" />
                <rect
                  x={locked ? c.x + 5 : c.x}
                  y={locked ? c.y + 5 : c.y}
                  width={locked ? 4 : CELL}
                  height={locked ? 4 : CELL}
                  rx={locked ? 2 : doc.doc_type === "incident" ? 5 : 1.5}
                  className={`die die-${state} ${doc.doc_type === "sop" ? "die-sop" : ""} ${focus ? "die-focus" : ""}`}
                />
              </g>
            );
          })}
        </svg>
      </div>
      <div className="wafer-side">
        <ul className="wafer-legend">
          <li>
            <i className="sw sw-visible" />
            {t("wafer.visible", { n: visibleCount })}
          </li>
          <li>
            <i className="sw sw-locked" />
            {t("wafer.lockedN", { n: docs.length - visibleCount })}
          </li>
          <li>
            <i className="sw sw-retrieved" />
            {t("wafer.retrievedN", { n: retrieved.length - extra.length })}
          </li>
          <li>
            <i className="sw sw-cited" />
            {t("wafer.citedL")}
          </li>
        </ul>
        <ul className="clr-legend" aria-label={t("clr.legend")}>
          <li className="fine">{t("clr.legend")}</li>
          {[0, 1, 2, 3].map((l) => (
            <li key={l}>
              <Clearance level={l} />
            </li>
          ))}
        </ul>
        <div className="wafer-info" aria-live="polite">
          {shown ? (
            shown.visible ? (
              <>
                <span className="code">{shown.doc_id}</span>
                <span>
                  {shown.doc_type === "sop" ? t("wafer.sop") : t("wafer.incident")} · {shown.fab} · {shown.department}
                  {shown.superseded_by ? t("wafer.superseded") : ""}
                  {citedSet.has(shown.doc_id) ? t("wafer.cited") : retrievedSet.has(shown.doc_id) ? t("wafer.retrieved") : ""}
                </span>
                <Clearance level={shown.clearance} />
              </>
            ) : (
              <span>{t("wafer.locked")}</span>
            )
          ) : null}
        </div>
        {extra.length > 0 && <p className="fine">{t("wafer.extra", { n: extra.length, ids: extra.join(", ") })}</p>}
      </div>
    </div>
  );
}
