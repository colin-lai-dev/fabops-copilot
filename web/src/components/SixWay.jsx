import React from "react";
import { useT } from "../i18n.js";

// "One question, six identities": the same question answered once per demo user, side by side.
// Replay columns are six real recordings (scripts/record_replay.py GROUPS); live columns are
// six real requests, each with that user's own session token. The only variable is permission.

const CLEARANCE = ["public", "internal", "confidential", "restricted"];

function Column({ col }) {
  const t = useT();
  const { user, run, visible, total, targetVisible } = col;
  const refused = !run || run.refused;
  return (
    <article className={`six-col ${refused ? "six-refused" : "six-answered"}`}>
      <header className="six-head">
        <b>{t.user(user)}</b>
        <span className="code fine">{user.user_id}</span>
        <span className={`clr clr-${user.clearance}`}>{CLEARANCE[user.clearance]}</span>
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
      <div className={`six-verdict ${refused ? "bad" : "good"}`}>
        {refused ? t("six.refused") : t("six.answered")}
      </div>
      {refused && targetVisible && <p className="fine six-why">{t("six.refusedVisible")}</p>}
      <p className="six-answer">{run?.answer}</p>
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
  if (!data.columns?.length) return <p className="fine">{t("six.none")}</p>;
  const answered = data.columns.filter((c) => c.run && !c.run.refused).length;
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
