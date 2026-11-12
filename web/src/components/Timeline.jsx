import React, { useState } from "react";
import { useT } from "../i18n.js";

// The agent's run as one thread: each read-only tool call, then its conclusion, then the only
// thing it may do with it, a proposal that waits for a person. Arguments never carry an
// identity (the server injects it from the token); results are already permission-filtered.

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

// Long agent answers: the conclusion first, caveats folded (display only; text unchanged).
const NOTE_START = /(?<=[。！？])\s*(?=注意|另外|此外|提醒|補充|但|不過)/;
export function splitAgentAnswer(text) {
  const at = text.search(NOTE_START);
  if (at > 0) return [text.slice(0, at).trim(), text.slice(at).trim()];
  const sents = text.split(/(?<=[。！？])/);
  if (sents.length <= 2) return [text, ""];
  return [sents.slice(0, 2).join("").trim(), sents.slice(2).join("").trim()];
}

export default function Timeline({ run, playing, proposalState, proposalNote }) {
  const t = useT();
  const [open, setOpen] = useState(null);
  const calls = run.calls || [];
  const [head, notes] = splitAgentAnswer(run.answer || "");
  const p = run.proposal;
  return (
    <ol className={`trace ${playing ? "trace-playing" : ""}`}>
      {calls.map((c, i) => (
        <li key={c.step} className={`node ${c.ok ? "" : "node-error"}`} style={{ "--n": i }}>
          <button
            type="button"
            className="node-head"
            aria-expanded={open === i}
            onClick={() => setOpen(open === i ? null : i)}
          >
            <span className="node-n">{c.step}</span>
            <span className="node-tool">{t(`tool.${c.tool}`)}</span>
            <span className="code node-args">
              {Object.values(c.args || {})
                .filter((v) => typeof v === "string")
                .join(" · ")}
            </span>
          </button>
          <div className="node-sum">{summary(c, t)}</div>
          {open === i && (
            <div className="node-detail">
              <div className="fine">{t("tl.args", { tool: c.tool })}</div>
              <pre>{JSON.stringify(c.args, null, 1)}</pre>
              <div className="fine">{t("tl.result")}</div>
              <pre>{c.ok ? c.preview : c.error}</pre>
            </div>
          )}
        </li>
      ))}
      <li className="node node-answer" style={{ "--n": calls.length }}>
        <div className="node-head static">
          <span className="node-n">=</span>
          <span className="node-tool">{t("answer.conclusion")}</span>
        </div>
        <p className="answer-text">{head}</p>
        {notes && (
          <details className="answer-notes">
            <summary>{t("answer.notes")}</summary>
            <p>{notes}</p>
          </details>
        )}
      </li>
      {p && (
        <li className="node node-proposal" style={{ "--n": calls.length + 1 }}>
          <div className="node-head static">
            <span className="node-n">→</span>
            <span className="node-tool">{t("tl.propose")}</span>
          </div>
          <p className="proposal-line">
            <b>{t(`action.${p.action}`)}</b> <span className="code">{p.target_id}</span>
            <span className={`state state-${proposalState}`}>{t(`status.${proposalState}`)}</span>
          </p>
          {proposalNote && <p className="fine">{proposalNote}</p>}
        </li>
      )}
    </ol>
  );
}
