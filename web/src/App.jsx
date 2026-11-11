import React, { useEffect, useState } from "react";
import { api, setToken } from "./api.js";

const CLEARANCE = ["public", "internal", "confidential", "restricted"];
const ACTION_LABEL = {
  hold_lot: "hold 批號",
  inhibit_chamber: "暫停腔體派貨",
  request_pm: "開立保養工單",
};
const MODES = [
  ["agent", "Agent（LLM 決定下一步）"],
  ["fixed", "固定 workflow"],
  ["rag", "只用 RAG"],
];

function UserPicker({ users, me, onPick }) {
  return (
    <div className="userpicker">
      <label>
        目前身分{" "}
        <select value={me?.user_id || ""} onChange={(e) => onPick(e.target.value)}>
          <option value="" disabled>
            選擇 demo 使用者
          </option>
          {users.map((u) => (
            <option key={u.user_id} value={u.user_id}>
              {u.display_name}（{u.user_id}）
            </option>
          ))}
        </select>
      </label>
      {me && (
        <span className="scope">
          廠區 {me.fabs.join(", ")} · 部門 {me.departments.join(", ")} · 等級{" "}
          {CLEARANCE[me.clearance]}
        </span>
      )}
    </div>
  );
}

function Trace({ calls }) {
  if (!calls?.length) return null;
  return (
    <section className="card">
      <h3>Agent trace（{calls.length} 次工具呼叫）</h3>
      <ol className="trace">
        {calls.map((c) => (
          <li key={c.step} className={c.ok ? "ok" : "err"}>
            <div>
              <b>{c.tool}</b> <code>{JSON.stringify(c.args)}</code>
            </div>
            {c.ok ? (
              <pre>{c.preview}</pre>
            ) : (
              <div className="error">錯誤：{c.error}</div>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

function Result({ run }) {
  if (!run) return null;
  const u = run.usage || {};
  return (
    <section className="card">
      <h3>
        回答 <span className={`badge ${run.status}`}>{run.status}</span>
        {run.refused && <span className="badge refused">不給建議</span>}
      </h3>
      <p className="answer">{run.answer}</p>
      {run.citations?.length > 0 && (
        <p className="meta">引用：{run.citations.join("、")}</p>
      )}
      {run.proposal && (
        <p className="meta">
          建議：{ACTION_LABEL[run.proposal.action]} <code>{run.proposal.target_id}</code>（
          {run.proposal.status}）
        </p>
      )}
      <p className="meta">
        模式 {run.mode} · 工具呼叫 {run.steps} · LLM 呼叫 {u.llm_calls ?? 0} · token{" "}
        {(u.input_tokens || 0) + (u.output_tokens || 0)} · US$
        {(u.cost_usd || 0).toFixed(5)}
      </p>
    </section>
  );
}

function Approvals({ me, refreshKey }) {
  const [items, setItems] = useState([]);
  const [audit, setAudit] = useState({});
  const [msg, setMsg] = useState("");

  const load = () =>
    api.pending().then(setItems).catch((e) => setMsg(e.message));

  useEffect(() => {
    if (me) load();
  }, [me, refreshKey]);

  async function decide(p, approved) {
    setMsg("");
    try {
      const run = await api.decide(p.proposal_id, approved, "");
      setMsg(`${p.proposal_id}：${run.status}`);
    } catch (e) {
      setMsg(`${p.proposal_id}：被拒絕（${e.message}）`);
    }
    setAudit({ ...audit, [p.proposal_id]: await api.audit(p.proposal_id) });
    load();
  }

  return (
    <section className="card">
      <h3>
        待核准的建議 <button onClick={load}>重新整理</button>
      </h3>
      <p className="hint">
        規則：不能核准自己提出的建議；核准者等級需 ≥ confidential；必須看得到目標。
        切換身分來核准。
      </p>
      {items.length === 0 && <p className="meta">沒有你看得到的待核准建議。</p>}
      {items.map((p) => (
        <div key={p.proposal_id} className="proposal">
          <div>
            <b>{ACTION_LABEL[p.action]}</b> <code>{p.target_id}</code> · 提出者 {p.requester}
          </div>
          <div className="meta">理由：{p.reason}</div>
          <button disabled={!p.can_decide} onClick={() => decide(p, true)}>
            核准
          </button>
          <button disabled={!p.can_decide} onClick={() => decide(p, false)}>
            駁回
          </button>
          {!p.can_decide && <span className="error">不能決定：{p.why_not}</span>}
        </div>
      ))}
      {msg && <p className="meta">{msg}</p>}
      {Object.entries(audit).map(([id, rows]) => (
        <div key={id} className="audit">
          <b>Audit log {id}</b>
          <ul>
            {rows.map((a, i) => (
              <li key={i}>
                {a.ts.slice(0, 19)} · {a.event} · {a.actor}
                {a.detail?.reason ? ` · ${a.detail.reason}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

export default function App() {
  const [users, setUsers] = useState([]);
  const [me, setMe] = useState(null);
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState("agent");
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    api.users().then(setUsers).catch((e) => setError(e.message));
  }, []);

  async function pick(userId) {
    const s = await api.login(userId); // switching identity re-issues the token
    setToken(s.token);
    setMe(s.user);
    setRun(null);
  }

  async function ask(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      setRun(await api.ask(question, mode));
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <header>
        <h1>FabOps Copilot</h1>
        <span className="hint">虛構晶圓廠 Fab-X · 全部為合成資料</span>
      </header>
      <UserPicker users={users} me={me} onPick={pick} />
      {me && (
        <form className="card" onSubmit={ask}>
          <textarea
            rows={3}
            value={question}
            placeholder="例如：FX1-ETCHER-02-CHA 剛發生 ETC-PRS-0412，請先確認腔體狀態，再依 SOP 處理。"
            onChange={(e) => setQuestion(e.target.value)}
          />
          <div className="row">
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              {MODES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
            <button disabled={busy || !question.trim()}>{busy ? "查詢中…" : "送出"}</button>
          </div>
        </form>
      )}
      {error && <p className="error">{error}</p>}
      <Result run={run} />
      <Trace calls={run?.calls} />
      {me && <Approvals me={me} refreshKey={refreshKey} />}
    </main>
  );
}
