import React, { useEffect, useRef, useState } from "react";
import { useT } from "../i18n.js";

// Pending proposals the current identity can see, with approve / reject. The page never jumps
// on a decision (handoff 017 #6): the result shows where the buttons were, the audit rows the
// decision added are briefly highlighted, and if the audit log is off screen a small hint offers
// to scroll there; the visitor decides.

const inView = (el) => {
  if (!el) return true;
  const r = el.getBoundingClientRect();
  return r.top < window.innerHeight && r.bottom > 0;
};

export default function Approvals({ api, me, refreshKey, onDecided, onAttempt }) {
  const t = useT();
  const why = (r) => t(`why.${r}`);
  const [blind, setBlind] = useState([]);
  const [items, setItems] = useState([]);
  const [audit, setAudit] = useState(null); // { id, rows, fresh: number of newest rows to mark }
  const [msg, setMsg] = useState(null); // { id, ok, text }: shown in place of that proposal's buttons
  const [hint, setHint] = useState(false);
  const auditRef = useRef(null);

  const load = () => {
    api.pending().then(setItems).catch(() => setItems([]));
    Promise.resolve(api.blindAttempts?.() ?? []).then(setBlind);
  };
  useEffect(() => {
    setMsg(null);
    load();
  }, [me?.user_id, refreshKey]);
  // An audit log belongs to the identity that fetched it: never carry it over to another one
  // (the API answers 404 to someone who cannot see the target).
  useEffect(() => {
    setAudit(null);
    setHint(false);
  }, [me?.user_id]);

  useEffect(() => {
    if (!audit) return undefined;
    if (inView(auditRef.current)) return undefined;
    setHint(true);
    const timer = setTimeout(() => setHint(false), 8000);
    return () => clearTimeout(timer);
  }, [audit]);

  async function decide(p, approved) {
    let ok = false;
    try {
      const run = await api.decide(p.proposal_id, approved);
      ok = true;
      onDecided?.(run);
      onAttempt?.({ ok, approved });
      setMsg({ id: p.proposal_id, ok, text: t(approved ? "ap.approved" : "ap.rejected", { s: run.status }) });
    } catch (e) {
      setMsg({ id: p.proposal_id, ok, text: t("ap.denied", { why: why(e.message) }) });
      onAttempt?.({ ok, approved, reason: e.message });
    }
    const rows = await api.audit(p.proposal_id);
    // a refusal adds one row; an approval adds "approved" and "executed"
    setAudit({ id: p.proposal_id, rows, fresh: ok && approved ? 2 : 1 });
    load();
  }

  const decided = msg && !items.some((p) => p.proposal_id === msg.id); // its card is gone
  return (
    <div className="approvals">
      {items.length === 0 && !decided && <p className="fine">{t("ap.none")}</p>}
      {items.length === 0 &&
        blind.map((b) => (
          <div key={b.proposal_id} className="proposal-card blind">
            <p className="fine">{t("ap.blind", { name: t.user(me) })}</p>
            <p className="msg-bad">
              HTTP {b.status_code} · <span className="code">{b.proposal_id}</span> · {why(b.detail)}
            </p>
          </div>
        ))}
      {items.map((p) => (
        <div key={p.proposal_id} className="proposal-card">
          <div>
            <b>{t(`action.${p.action}`)}</b> <span className="code">{p.target_id}</span>
          </div>
          <div className="fine">{t("ap.by", { who: p.requester, id: p.proposal_id })}</div>
          <div className="row">
            <button type="button" className="approve" onClick={() => decide(p, true)}>
              {t("ap.approve")}
            </button>
            <button type="button" className="quiet" onClick={() => decide(p, false)}>
              {t("ap.reject")}
            </button>
          </div>
          {msg?.id === p.proposal_id && (
            <p className={msg.ok ? "msg-ok" : "msg-bad"} role="status">
              {msg.text}
            </p>
          )}
        </div>
      ))}
      {decided && (
        <div className="proposal-card proposal-done">
          <p className={msg.ok ? "msg-ok" : "msg-bad"} role="status">
            {msg.text}
          </p>
        </div>
      )}
      <p className="fine ap-rules">{t("ap.rules")}</p>
      {audit && audit.rows.length > 0 && (
        <div className="audit" ref={auditRef}>
          <div className="panel-sub">
            Audit log · <span className="code">{audit.id}</span>
          </div>
          <ol>
            {audit.rows.map((a, i) => (
              <li
                key={`${audit.id}-${i}-${audit.rows.length}`}
                className={`ev ev-${a.event} ${i >= audit.rows.length - audit.fresh ? "ev-new" : ""}`}
              >
                <span className="code">{a.ts.slice(11, 19)}</span>
                <span className="ev-name">{t(`ev.${a.event}`)}</span>
                <span className="code">{a.actor}</span>
                {a.detail?.reason && <span className="fine">{why(a.detail.reason)}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}
      {hint && (
        <button
          type="button"
          className="audit-hint"
          onClick={() => {
            setHint(false);
            const smooth = !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
            auditRef.current?.scrollIntoView({ block: "nearest", behavior: smooth ? "smooth" : "auto" });
          }}
        >
          {t("ap.hint")} ↓
        </button>
      )}
    </div>
  );
}
