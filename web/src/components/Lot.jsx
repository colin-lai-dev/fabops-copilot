import React, { useEffect, useMemo, useRef, useState } from "react";
import { useT, userName } from "../i18n.js";
import { verdict } from "../verdict.js";
import Clearance from "./Clearance.jsx";
import { CELL, Disc, layout } from "./WaferMap.jsx";

// The lot: six wafers, one per identity, for the same question. It is the identity switcher,
// the permission picture and the six-way comparison in one row. When a question is asked the
// six wafers go through the same three phases as the system does, left to right: the
// permission filter (dies this identity may not see shrink to dots), retrieval (amber), then
// the cited die gets its ring.

const square = (c) => `M${c.x} ${c.y}h${CELL}v${CELL}h${-CELL}z`;
const dot = (c) => `M${c.x + 5} ${c.y + 5}h4v4h-4z`;

function MiniWafer({ slot, cells, size, phase }) {
  const paths = useMemo(() => {
    const seen = new Set(slot.visible);
    const all = cells.slice(0, slot.total);
    return {
      open: all.filter((_, i) => seen.has(i)).map(square).join(""),
      lockedFull: all.filter((_, i) => !seen.has(i)).map(square).join(""),
      lockedDot: all.filter((_, i) => !seen.has(i)).map(dot).join(""),
      retrieved: slot.retrieved.map((i) => square(cells[i])).join(""),
      cited: slot.cited.map((i) => square(cells[i])).join(""),
    };
  }, [slot, cells]);
  return (
    <svg className="mini" viewBox={`-4 -4 ${size + 8} ${size + 8}`} aria-hidden="true" focusable="false">
      <Disc size={size} />
      <path d={paths.open} className="m-open" />
      {/* before the filter every die looks the same; after it, locked dies are only dots */}
      <path d={paths.lockedFull} className={`m-open m-fade ${phase >= 1 ? "off" : ""}`} />
      <path d={paths.lockedDot} className={`m-dot m-fade ${phase >= 1 ? "" : "off"}`} />
      <path d={paths.retrieved} className={`m-ret m-fade ${phase >= 2 ? "" : "off"}`} />
      <path d={paths.cited} className={`m-cit m-fade ${phase >= 3 ? "" : "off"}`} />
    </svg>
  );
}

function CompareCell({ slot }) {
  const t = useT();
  const [full, setFull] = useState(false);
  const v = verdict(slot);
  const run = slot.run;
  if (!run) return <p className="cmp-none">{t("v.noneLong")}</p>;
  const long = (run.answer || "").length > 150;
  return (
    <div className={`cmp cmp-${v.tone}`}>
      {run.proposal && (
        <p className="cmp-proposal">
          {t(`action.${run.proposal.action}`)} <span className="code">{run.proposal.target_id}</span>
        </p>
      )}
      {v.why && <p className="cmp-why">{t(v.why)}</p>}
      <p className={`cmp-answer ${long && !full ? "clamped" : ""}`}>{run.answer}</p>
      {long && (
        <button type="button" className="link" aria-expanded={full} onClick={() => setFull(!full)}>
          {full ? t("six.less") : t("six.more")}
        </button>
      )}
      {run.citations?.length > 0 && (
        <p className="cmp-cites">
          {run.citations.map((c) => (
            <span key={c} className="chip chip-cite code">
              {c}
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

export default function Lot({ lot, uid, onPick, phase, playing, playKey, compare, live = false }) {
  const t = useT();
  const total = lot[0]?.total || 192;
  const { size, cells } = useMemo(() => layout(total), [total]);
  // Phones: the lot scrolls sideways; keep the current identity's wafer in view (this moves the
  // strip only, never the page).
  const strip = useRef(null);
  useEffect(() => {
    const el = strip.current;
    const col = el?.querySelector(".col-on");
    if (!el || !col || el.scrollWidth <= el.clientWidth) return;
    const left = Math.max(0, col.offsetLeft - (el.clientWidth - col.offsetWidth) / 2);
    el.scrollTo({ left, behavior: "auto" });
  }, [uid, lot.length]);
  return (
    <section
      ref={strip}
      className={`lot ${playing ? "playing" : ""} ${compare ? "lot-compare" : ""}`}
      aria-label={t("lot.label")}
    >
      {playing && <span key={playKey} className="sweep" aria-hidden="true" />}
      {lot.map((slot, i) => {
        const u = slot.user;
        const on = u.user_id === uid;
        const v = verdict(slot);
        return (
          <div key={u.user_id} className={`col ${on ? "col-on" : ""}`} style={{ "--i": i }}>
            <button
              type="button"
              className={`slot ${on ? "slot-on" : ""}`}
              aria-pressed={on}
              onClick={() => onPick(u.user_id)}
            >
              <span className="slot-no" aria-hidden="true">
                {String(i + 1).padStart(2, "0")}
              </span>
              <MiniWafer slot={slot} cells={cells} size={size} phase={phase} />
              {/* both languages share one cell: the name may wrap, and a language switch moves nothing */}
              <span className="slot-name">
                <span>{userName(t.lang, u)}</span>
                <span className="slot-name-ghost" aria-hidden="true">
                  {userName(t.lang === "en" ? "zh" : "en", u)}
                </span>
              </span>
              <span className="slot-id code">{u.user_id}</span>
              <span className="slot-meta">
                <Clearance level={u.clearance} />
                <span className="slot-vis">
                  <b>{slot.visible.length}</b>/{slot.total}
                </span>
              </span>
              <span className={`slot-verdict tone-${v.tone} ${phase >= 3 ? "" : "off"}`}>
                {t(live && !slot.run ? "v.notAsked" : v.key)}
              </span>
              {on && <span className="sr-only">{t("lot.you")}</span>}
            </button>
            {compare && <CompareCell slot={slot} />}
          </div>
        );
      })}
    </section>
  );
}
