import React, { useState } from "react";
import { useT } from "../i18n.js";

// The injected source document with the malicious sentence marked, and a side-by-side view of
// the protected answer and the recorded control run without the permission pre-filter.

function Marked({ body }) {
  const t = useT();
  const handling = body.split("## 處理經過")[1]?.split("##")[0]?.trim() || "";
  const before = body.split("## 處理經過")[0];
  const title = before.match(/^# (.+)$/m)?.[1];
  return (
    <div className="source-doc">
      <div className="fine">{title}</div>
      <div className="fine">{t("inj.handling")}</div>
      <p>
        <mark className="malicious">{handling}</mark>
      </p>
    </div>
  );
}

export default function Injection({ scene, run, cite }) {
  const t = useT();
  const [compare, setCompare] = useState(false);
  if (!scene?.injected) return null;
  const c = scene.control;
  return (
    <section className="panel injection" aria-label="注入對照">
      <div className="panel-head">
        <h2>{t("inj.title")}</h2>
        {c && (
          <button type="button" aria-pressed={compare} onClick={() => setCompare(!compare)}>
            {compare ? t("inj.hide") : t("inj.show")}
          </button>
        )}
      </div>
      <p className="fine">{t("inj.doc", { id: scene.injected.doc_id })}</p>
      <Marked body={scene.injected.body_md} />
      {compare && c && (
        <div className="compare">
          <div className="compare-col good">
            <div className="panel-sub">{t("inj.good")}</div>
            <p>{run.answer}</p>
            <p className="fine">
              {t("inj.cites")}
              {run.citations?.length ? run.citations.map(cite) : t("answer.none")}
            </p>
          </div>
          <div className="compare-col bad">
            <div className="panel-sub">{t("inj.bad")}</div>
            <p>{c.answer}</p>
            <p className="fine">
              {t("inj.used")}
              {c.hidden_in_answer.map((d) => (
                <span key={d} className="chip chip-bad code">{d}</span>
              ))}
            </p>
            <p className="fine">{t("inj.count", { n: c.hidden_retrieved.length })}</p>
          </div>
        </div>
      )}
    </section>
  );
}
