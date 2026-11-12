import React, { useState } from "react";
import { useT } from "../i18n.js";
import Clearance from "./Clearance.jsx";

// "One question, six identities": the same question answered once per demo user, side by side.
// Replay columns are six real recordings (scripts/record_replay.py GROUPS); live columns are
// six real requests, each with that user's own session token. The only variable is permission.


// What a column's answer amounts to. RAG: answered / declined / cut off by the 512-token cap.
// Agent: `refused` means "no action recommended", so the verdict is the proposal or the status.
export function verdict(col) {
  const { run, cutOff } = col;
  if (!run) return { key: "six.refused", tone: "bad" };
  if (cutOff) return { key: "six.cutOff", tone: "warn", why: "six.cutOffWhy" };
  if (run.mode === "rag") return run.refused ? { key: "six.refused", tone: "bad" } : { key: "six.answered", tone: "good" };
  if (run.proposal) return { key: "six.proposed", tone: "violet" };
  if (run.status === "incomplete") return { key: "six.incomplete", tone: "bad", why: "six.incompleteWhy" };
  return run.refused ? { key: "six.noAction", tone: "bad" } : { key: "six.answered", tone: "good" };
}

function Column({ col }) {
  const t = useT();
  const { user, run, visible, total, targetVisible } = col;
  const v = verdict(col);
  const refused = v.tone !== "good" && v.tone !== "violet";
  const [full, setFull] = useState(false);
  const long = (run?.answer || "").length > 160;
  return (
    <article className={`six-col six-tone-${v.tone}`}>
      <header className="six-head">
        <b>{t.user(user)}</b>
        <span className="code fine">{user.user_id}</span>
        <Clearance level={user.clearance} />
      </header>
      {visible != null && (
        <div className="six-vis" title={t("six.visible", { n: visible, total })}>
          <span className="six-bar">
            <i style={{ width: `${(visible / total) * 100}%` }} />
          </span>
          <span className="fine">{t("six.visible", { n: visible, total })}</span>
        </div>
      )}
      {col.target && targetVisible != null && (
        <div className={`fine six-target ${targetVisible ? "ok" : "no"}`}>
          {t("six.targetShort")}
          <b>{targetVisible ? t("six.targetOk") : t("six.targetNo")}</b>
        </div>
      )}
      <div className={`six-verdict ${v.tone}`}>{t(v.key)}</div>
      {run?.proposal && (
        <div className="six-proposal fine">
          {t(`action.${run.proposal.action}`)} <span className="code">{run.proposal.target_id}</span>
        </div>
      )}
      {v.why && <p className="fine six-why">{t(v.why)}</p>}
      {!v.why && refused && run?.mode === "rag" && targetVisible && (
        <p className="fine six-why">{t("six.refusedVisible")}</p>
      )}
      <p className={`six-answer ${long && !full ? "clamped" : ""}`}>{run?.answer}</p>
      {long && (
        <button type="button" className="quiet six-more" aria-expanded={full} onClick={() => setFull(!full)}>
          {full ? t("six.less") : t("six.more")}
        </button>
      )}
      <div className="six-cites">
        <span className="fine">{t("six.cites")}</span>
        {run?.citations?.length ? (
          run.citations.map((c) => (
            <span key={c} className="chip chip-cite code">
              {c}
            </span>
          ))
        ) : (
          <span className="fine">{t("answer.none")}</span>
        )}
      </div>
    </article>
  );
}

export default function SixWay({ data, onClose }) {
  const t = useT();
  if (!data) return <p className="fine">{t("doc.loading")}</p>;
  if (data.unavailable) return <p className="fine six-unavailable">{t("six.unavailable")}</p>;
  if (!data.columns?.length) return <p className="fine">{t("six.none")}</p>;
  const answered = data.columns.filter((c) => ["good", "violet"].includes(verdict(c).tone)).length;
  return (
    <section className="panel six" aria-label={t("six.title")}>
      <div className="panel-head">
        <h2>{t("six.title")}</h2>
        <span className="fine">
          {answered} / {data.columns.length} · {t("six.answered")}
        </span>
        {onClose && (
          <button type="button" className="quiet six-close" onClick={onClose}>
            {t("ask.sixClose")}
          </button>
        )}
      </div>
      {data.title && <div className="panel-sub">{t.pick(data, "title")}</div>}
      <p className="question">{data.question}</p>
      <p className="fine">
        {t("six.hint")}
        {data.target && (
          <>
            {" "}
            {t("six.target", { id: data.target })}
          </>
        )}
      </p>
      {t.lang === "en" && <p className="fine zh-note">{t("answer.zhNote")}</p>}
      <p className="fine six-scroll-hint">{t("six.scroll")}</p>
      <div className="six-grid">
        {data.columns.map((c) => (
          <Column key={c.user.user_id} col={{ ...c, target: data.target }} />
        ))}
      </div>
    </section>
  );
}
