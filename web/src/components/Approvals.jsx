import React, { useEffect, useState } from "react";
import { useT } from "../i18n.js";


export default function Approvals({ api, me, refreshKey }) {
  const t = useT();
  const why = (r) => t(`why.${r}`);
  const [blind, setBlind] = useState([]);
  const [items, setItems] = useState([]);
  const [audit, setAudit] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = () => {
    api.pending().then(setItems).catch(() => setItems([]));
    Promise.resolve(api.blindAttempts?.() ?? []).then(setBlind);
  };
  useEffect(() => {
    setMsg(null);
    load();
  }, [me?.user_id, refreshKey]);

  async function decide(p, approved) {
    try {
      const run = await api.decide(p.proposal_id, approved);
      setMsg({ ok: true, text: t(approved ? "ap.approved" : "ap.rejected", { s: run.status }) });
    } catch (e) {
      setMsg({ ok: false, text: t("ap.denied", { why: why(e.message) }) });
    }
    setAudit({ id: p.proposal_id, rows: await api.audit(p.proposal_id) });
    load();
  }

  return (
    <div className="approvals">
      <p className="fine">{t("ap.rules")}</p>
      {items.length === 0 && <p className="fine">{t("ap.none")}</p>}
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
        </div>
      ))}
      {msg && <p className={msg.ok ? "msg-ok" : "msg-bad"} role="status">{msg.text}</p>}
      {audit && audit.rows.length > 0 && (
        <div className="audit">
          <div className="panel-sub">Audit log · <span className="code">{audit.id}</span></div>
          <ol>
            {audit.rows.map((a, i) => (
              <li key={i} className={`ev ev-${a.event}`}>
                <span className="code">{a.ts.slice(11, 19)}</span>
                <span className="ev-name">{t(`ev.${a.event}`)}</span>
                <span className="code">{a.actor}</span>
                {a.detail?.reason && <span className="fine">{why(a.detail.reason)}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
