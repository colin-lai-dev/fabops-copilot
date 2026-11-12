import React, { useMemo, useState } from "react";
import { useT } from "../i18n.js";

// The permission wafer map: one die per document (192), laid out on a round wafer.
// Visible dies are lit, locked dies are grey with a hatch; retrieved dies are amber and the
// cited ones get an outline. Switching identity re-lights the wafer (the page's only
// choreographed animation, ~600 ms, radial, skipped under prefers-reduced-motion).

const CELL = 14;
const GAP = 2;

function layout(count) {
  for (let n = 10; n < 40; n++) {
    const r = n / 2 - 0.15;
    const cells = [];
    for (let y = 0; y < n; y++)
      for (let x = 0; x < n; x++) {
        const dx = x + 0.5 - n / 2;
        const dy = y + 0.5 - n / 2;
        if (dx * dx + dy * dy <= r * r) cells.push({ x, y, d: Math.hypot(dx, dy) / r });
      }
    if (cells.length >= count) return { n, cells };
  }
  throw new Error("too many dies");
}

const CLEARANCE = ["public", "internal", "confidential", "restricted"];

export default function WaferMap({ docs, retrieved = [], cited = [], focusId, onFocus }) {
  const t = useT();
  const { n, cells } = useMemo(() => layout(docs.length || 192), [docs.length]);
  const [hover, setHover] = useState(null);
  const size = n * (CELL + GAP) + GAP;
  const retrievedSet = new Set(retrieved);
  const citedSet = new Set(cited);
  const visibleCount = docs.filter((d) => d.visible).length;
  const extra = retrieved.filter((id) => !docs.some((d) => d.doc_id === id));
  const shown = hover !== null ? docs[hover] : focusId ? docs.find((d) => d.doc_id === focusId) : null;

  return (
    <div className="wafer">
      <div className="wafer-stage">
        <svg
          viewBox={`0 0 ${size} ${size + 10}`}
          role="img"
          aria-label={t("wafer.aria", { total: docs.length, visible: visibleCount, retrieved: retrievedSet.size })}
          onMouseLeave={() => setHover(null)}
        >
          <defs>
            <pattern id="hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="4" className="hatch-line" />
            </pattern>
          </defs>
          <circle cx={size / 2} cy={size / 2} r={size / 2 - 1} className="wafer-disc" />
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
              ? "locked"
              : citedSet.has(doc.doc_id)
                ? "cited"
                : retrievedSet.has(doc.doc_id)
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
                  className={`die die-${state} ${doc.doc_type === "sop" ? "die-sop" : ""} ${focus ? "die-focus" : ""}`}
                  style={{ transitionDelay: `${Math.round(c.d * 300)}ms` }}
                />
                {state === "locked" && (
                  <rect x={x} y={y} width={CELL} height={CELL} rx="2" fill="url(#hatch)" className="die-hatch" style={{ transitionDelay: `${Math.round(c.d * 300)}ms` }} />
                )}
              </g>
            );
          })}
        </svg>
      </div>
      <div className="wafer-info" aria-live="polite">
        {shown ? (
          shown.visible ? (
            <>
              <span className="code">{shown.doc_id}</span>
              <span>
                {shown.doc_type === "sop" ? t("wafer.sop") : t("wafer.incident")} · {shown.fab} · {shown.department} ·{" "}
                {CLEARANCE[shown.clearance]}
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
      {extra.length > 0 && (
        <p className="fine">{t("wafer.extra", { n: extra.length, ids: extra.join(", ") })}</p>
      )}
    </div>
  );
}
