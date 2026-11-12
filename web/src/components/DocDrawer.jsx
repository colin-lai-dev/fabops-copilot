import React, { useEffect, useRef, useState } from "react";
import { useT } from "../i18n.js";
import Clearance from "./Clearance.jsx";

// Side drawer for an opened citation. The text comes from the API's permission-checked
// GET /api/docs/{doc_id} (live) or from what the recorder fetched with the asker's own token
// (replay): a locked document has no text anywhere in the page, only the "no access" state.
// Sentences that share enough wording with the answer are highlighted (simple overlap, labelled).

const N = 4; // character n-grams

function grams(text) {
  const s = text.replace(/[\s|*#>`\-—:：，。、（）()「」]/g, "");
  const out = new Set();
  for (let i = 0; i + N <= s.length; i++) out.add(s.slice(i, i + N));
  return out;
}

function sentences(text) {
  return text.split(/(?<=[。！？\n])/).filter((x) => x.length > 0);
}

// Each indexed chunk starts with a "[doc_id] type：title" context line (ADR-0010); the drawer
// already shows the title, so drop it.
function body(text, section) {
  let s = text.replace(/^\[[^\]]+\][^\n]*\n/, "");
  if (section) s = s.replace(new RegExp(`^#*\\s*${section.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\n`), "");
  return s.trim();
}

// A Markdown table becomes rows of cells; separator rows are dropped.
function Table({ lines }) {
  const rows = lines
    .filter((l) => !/^\|[\s:|-]+\|$/.test(l.trim()))
    .map((l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
  return (
    <table className="drawer-table">
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            {r.map((c, j) => (i === 0 ? <th key={j}>{c}</th> : <td key={j}>{c}</td>))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function matchScore(sentence, answerGrams) {
  let n = 0;
  for (const g of grams(sentence)) if (answerGrams.has(g)) n++;
  return n;
}

export default function DocDrawer({ docId, load, answer, onClose }) {
  const t = useT();
  const [doc, setDoc] = useState(undefined); // undefined: loading, null: no access, "nr": not recorded
  const closeRef = useRef(null);

  useEffect(() => {
    let alive = true;
    setDoc(undefined);
    Promise.resolve(load(docId))
      .then((d) => alive && setDoc(d || null))
      .catch((e) => alive && setDoc(e?.message === "not-recorded" ? "nr" : null));
    return () => {
      alive = false;
    };
  }, [docId]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const ans = grams(answer || "");
  const parts =
    doc && doc !== "nr"
      ? doc.sections.map((sec) => {
          const text = body(sec.text, sec.section);
          const table = text.split("\n").filter((l) => l.trim().startsWith("|"));
          const rest = text
            .split("\n")
            .filter((l) => !l.trim().startsWith("|"))
            .join("\n")
            .trim();
          return { table, sents: sentences(rest).map((x) => [x, matchScore(x, ans)]) };
        })
      : [];
  const best = Math.max(0, ...parts.flatMap((p) => p.sents.map(([, n]) => n)));
  const cut = Math.max(3, Math.ceil(best * 0.6)); // only sentences close to the best match
  return (
    <div className="drawer-wrap" onClick={onClose}>
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={t("doc.title")}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="drawer-head">
          <div>
            <div className="panel-sub">{t("doc.title")}</div>
            <div className="code">{docId}</div>
          </div>
          <button type="button" ref={closeRef} className="quiet" onClick={onClose}>
            {t("doc.close")}
          </button>
        </div>
        {doc === undefined && <p className="fine">{t("doc.loading")}</p>}
        {doc === null && <p className="msg-bad">{t("doc.locked")}</p>}
        {doc === "nr" && <p className="fine">{t("doc.notRecorded")}</p>}
        {doc && doc !== "nr" && (
          <>
            <h2 className="drawer-title">{doc.title}</h2>
            <p className="fine">
              {t("doc.meta", {
                type: doc.doc_type === "sop" ? t("wafer.sop") : t("wafer.incident"),
                fab: doc.fab,
                dept: doc.department,
              })}{" "}
              <Clearance level={doc.clearance} />
              {doc.superseded_by ? t("wafer.superseded") : ""}
            </p>
            {t.lang === "en" && <p className="fine zh-note">{t("answer.zhNote")}</p>}
            <div className="drawer-body">
              {doc.sections.map((sec, i) => (
                <section key={i} className="drawer-sec">
                  {sec.section && <div className="panel-sub">{sec.section}</div>}
                  {parts[i].table.length > 0 && <Table lines={parts[i].table} />}
                  <p>
                    {parts[i].sents.map(([x, n], j) =>
                      n >= cut ? (
                        <mark key={j} className="cite-mark">
                          {x}
                        </mark>
                      ) : (
                        <span key={j}>{x}</span>
                      ),
                    )}
                  </p>
                </section>
              ))}
            </div>
          </>
        )}
      </aside>
    </div>
  );
}
