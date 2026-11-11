import React, { useMemo, useState } from "react";

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
          aria-label={`權限晶圓圖：192 份文件中可見 ${visibleCount} 份，本次檢索 ${retrievedSet.size} 份`}
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
                {shown.doc_type === "sop" ? "SOP" : "異常報告"} · {shown.fab} · {shown.department} · {CLEARANCE[shown.clearance]}
                {shown.superseded_by ? " · 已被新版取代" : ""}
                {citedSet.has(shown.doc_id) ? " · 被引用" : retrievedSet.has(shown.doc_id) ? " · 被檢索" : ""}
              </span>
            </>
          ) : (
            <span>無權限查看：這份文件不會進入此身分的檢索，也不顯示任何屬性。</span>
          )
        ) : (
          <span>滑過或點選 die 查看文件屬性（只有屬性，沒有內文）。</span>
        )}
      </div>
      <ul className="wafer-legend">
        <li><i className="sw sw-visible" />可見 {visibleCount}</li>
        <li><i className="sw sw-locked" />無權限 {docs.length - visibleCount}</li>
        <li><i className="sw sw-retrieved" />本次檢索 {retrieved.length - extra.length}</li>
        <li><i className="sw sw-cited" />被引用</li>
        <li className="legend-shape">方形 SOP · 圓角 異常報告</li>
      </ul>
      {extra.length > 0 && (
        <p className="fine">另檢索到 {extra.length} 份測試用注入文件（{extra.join("、")}），不在 192 份語料中。</p>
      )}
    </div>
  );
}
