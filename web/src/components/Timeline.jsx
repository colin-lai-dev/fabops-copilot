import React, { useEffect, useState } from "react";

const ACTION_LABEL = { hold_lot: "hold 批號", inhibit_chamber: "暫停腔體派貨", request_pm: "開立保養工單" };
const TOOL_LABEL = {
  get_lot_history: "查批號履歷",
  get_equipment_status: "查機台狀態",
  get_dispatch_log: "查派貨紀錄",
  search_sop: "搜尋 SOP",
  search_similar_incidents: "搜尋類似異常",
};

// One-line summary of a (truncated, permission-filtered) tool result.
function summary(c) {
  if (!c.ok) return `錯誤：${c.error}`;
  const p = c.preview || "";
  if (p.startsWith('{"found": false')) return "查無資料，或沒有權限查看";
  const docs = [...p.matchAll(/"doc_id": "([^"]+)"/g)].map((m) => m[1]);
  if (docs.length) return `找到 ${[...new Set(docs)].slice(0, 3).join("、")}`;
  const ch = [...p.matchAll(/"chamber_id": "([^"]+)", "equipment_id": "[^"]+", "status": "(\w+)"/g)];
  if (ch.length) return ch.slice(0, 4).map((m) => `${m[1].split("-").pop()} ${m[2]}`).join(" · ");
  const lot = p.match(/"lot_id": "([^"]+)"[^}]*"status": "(\w+)"/);
  if (lot) return `批號 ${lot[1]}：${lot[2]}`;
  return "已取得資料";
}

export default function Timeline({ calls = [], proposal, runKey }) {
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
    const t = setTimeout(() => setShown((s) => s + 1), 1100);
    return () => clearTimeout(t);
  }, [auto, shown, total]);

  if (!total) return <p className="fine">這一題沒有呼叫工具（只用 RAG 或直接回答）。</p>;

  return (
    <div className="timeline">
      <div className="timeline-controls">
        <span className="fine">
          第 {shown} / {total} 步
        </span>
        <button type="button" onClick={() => setShown((s) => Math.min(total, s + 1))} disabled={shown >= total}>
          下一步
        </button>
        <button type="button" onClick={() => setAuto(!auto)} disabled={shown >= total}>
          {auto ? "暫停" : "自動播放"}
        </button>
        <button type="button" className="quiet" onClick={() => setShown(total)} disabled={shown >= total}>
          全部展開
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
              <span className="step-tool">{TOOL_LABEL[c.tool] || c.tool}</span>
              <span className="code step-args">{Object.values(c.args || {}).filter((v) => typeof v === "string").join(" · ")}</span>
            </button>
            <div className="step-sum">{summary(c)}</div>
            {open === i && (
              <div className="step-detail">
                <div className="fine">工具 <span className="code">{c.tool}</span>，參數（不含身分；身分由伺服器從 token 注入）：</div>
                <pre>{JSON.stringify(c.args, null, 1)}</pre>
                <div className="fine">回傳（已依權限過濾，截斷顯示）：</div>
                <pre>{c.ok ? c.preview : c.error}</pre>
              </div>
            )}
          </li>
        ))}
        {proposal && shown > calls.length && (
          <li className="step step-proposal step-current">
            <div className="step-head static">
              <span className="step-n">→</span>
              <span className="step-tool">提出建議（等待人工核准）</span>
            </div>
            <div className="step-sum">
              {ACTION_LABEL[proposal.action]} <span className="code">{proposal.target_id}</span>
            </div>
            <div className="fine">{proposal.reason}</div>
          </li>
        )}
      </ol>
    </div>
  );
}
