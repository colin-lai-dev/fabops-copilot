import React, { useEffect, useState } from "react";
import { useT } from "../i18n.js";


// One-line summary of a (truncated, permission-filtered) tool result.
function summary(c, t) {
  if (!c.ok) return t("tl.error", { e: c.error });
  const p = c.preview || "";
  if (p.startsWith('{"found": false')) return t("tl.notFound");
  const docs = [...p.matchAll(/"doc_id": "([^"]+)"/g)].map((m) => m[1]);
  if (docs.length) return t("tl.found", { ids: [...new Set(docs)].slice(0, 3).join(t.lang === "en" ? ", " : "、") });
  const ch = [...p.matchAll(/"chamber_id": "([^"]+)", "equipment_id": "[^"]+", "status": "(\w+)"/g)];
  if (ch.length) return ch.slice(0, 4).map((m) => `${m[1].split("-").pop()} ${m[2]}`).join(" · ");
  const lot = p.match(/"lot_id": "([^"]+)"[^}]*"status": "(\w+)"/);
  if (lot) return t("tl.lot", { lot: lot[1], status: lot[2] });
  return t("tl.got");
}

export default function Timeline({ calls = [], proposal, runKey }) {
  const t = useT();
  const total = calls.length + (proposal ? 1 : 0);
  const [shown, setShown] = useState(0);
  const [auto, setAuto] = useState(false);
  const [open, setOpen] = useState(null);

  useEffect(() => {
    setShown(total ? 1 : 0);
    setAuto(false);
    setOpen(null);
  }, [runKey, total]);

  useEffect(() => {
    if (!auto) return undefined;
    if (shown >= total) {
      setAuto(false);
      return undefined;
    }
    const timer = setTimeout(() => setShown((s) => s + 1), 1100);
    return () => clearTimeout(timer);
  }, [auto, shown, total]);

  if (!total) return <p className="fine">{t("tl.none")}</p>;

  return (
    <div className="timeline">
      <div className="timeline-controls">
        <span className="fine">{t("tl.pos", { n: shown, total })}</span>
        <button type="button" onClick={() => setShown((s) => Math.min(total, s + 1))} disabled={shown >= total}>
          {t("tl.next")}
        </button>
        <button type="button" onClick={() => setAuto(!auto)} disabled={shown >= total}>
          {auto ? t("tl.pause") : t("tl.play")}
        </button>
        <button type="button" className="quiet" onClick={() => setShown(total)} disabled={shown >= total}>
          {t("tl.all")}
        </button>
      </div>
      <ol>
        {calls.slice(0, shown).map((c, i) => (
          <li key={c.step} className={`step ${c.ok ? "" : "step-error"} ${i === shown - 1 ? "step-current" : ""}`}>
            <button
              type="button"
              className="step-head"
              aria-expanded={open === i}
              onClick={() => setOpen(open === i ? null : i)}
            >
              <span className="step-n">{c.step}</span>
              <span className="step-tool">{t(`tool.${c.tool}`)}</span>
              <span className="code step-args">{Object.values(c.args || {}).filter((v) => typeof v === "string").join(" · ")}</span>
            </button>
            <div className="step-sum">{summary(c, t)}</div>
            {open === i && (
              <div className="step-detail">
                <div className="fine">{t("tl.args", { tool: c.tool })}</div>
                <pre>{JSON.stringify(c.args, null, 1)}</pre>
                <div className="fine">{t("tl.result")}</div>
                <pre>{c.ok ? c.preview : c.error}</pre>
              </div>
            )}
          </li>
        ))}
        {proposal && shown > calls.length && (
          <li className="step step-proposal step-current">
            <div className="step-head static">
              <span className="step-n">→</span>
              <span className="step-tool">{t("tl.propose")}</span>
            </div>
            <div className="step-sum">
              {t(`action.${proposal.action}`)} <span className="code">{proposal.target_id}</span>
            </div>
            <div className="fine">{proposal.reason}</div>
          </li>
        )}
      </ol>
    </div>
  );
}
