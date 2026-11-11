import React, { useEffect, useState } from "react";

const ACTION_LABEL = { hold_lot: "hold 批號", inhibit_chamber: "暫停腔體派貨", request_pm: "開立保養工單" };
const EVENT_LABEL = {
  proposed: "提出",
  denied: "拒絕",
  approved: "核准",
  rejected: "駁回",
  executed: "執行（模擬）",
};
const WHY = {
  "the requester cannot decide their own proposal": "提出者不能決定自己的提案",
  "approver clearance below confidential": "核准者等級需 ≥ confidential",
  "approver cannot see the target": "核准者看不到這個目標",
};

export default function Approvals({ api, me, refreshKey }) {
  const [items, setItems] = useState([]);
  const [audit, setAudit] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = () => api.pending().then(setItems).catch(() => setItems([]));
  useEffect(() => {
    setMsg(null);
    load();
  }, [me?.user_id, refreshKey]);

  async function decide(p, approved) {
    try {
      const run = await api.decide(p.proposal_id, approved);
      setMsg({ ok: true, text: `${approved ? "已核准" : "已駁回"}，狀態：${run.status}` });
    } catch (e) {
      setMsg({ ok: false, text: `被拒絕：${WHY[e.message] || e.message}` });
    }
    setAudit({ id: p.proposal_id, rows: await api.audit(p.proposal_id) });
    load();
  }

  return (
    <div className="approvals">
      <p className="fine">規則：不能決定自己的提案；核准者等級需 ≥ confidential；必須看得到目標。執行為模擬，只寫入 audit log。</p>
      {items.length === 0 && <p className="fine">目前身分沒有看得到的待核准建議。</p>}
      {items.map((p) => (
        <div key={p.proposal_id} className="proposal-card">
          <div>
            <b>{ACTION_LABEL[p.action]}</b> <span className="code">{p.target_id}</span>
          </div>
          <div className="fine">提出者 {p.requester} · 提案 {p.proposal_id}</div>
          <div className="row">
            <button type="button" className="approve" onClick={() => decide(p, true)}>
              核准
            </button>
            <button type="button" className="quiet" onClick={() => decide(p, false)}>
              駁回
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
                <span className="ev-name">{EVENT_LABEL[a.event] || a.event}</span>
                <span className="code">{a.actor}</span>
                {a.detail?.reason && <span className="fine">{WHY[a.detail.reason] || a.detail.reason}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
