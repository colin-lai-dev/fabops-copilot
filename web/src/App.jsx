import React, { useEffect, useMemo, useRef, useState } from "react";
import { live } from "./api.js";
import { replay } from "./replay.js";
import { TOUR } from "./tour.js";
import WaferMap from "./components/WaferMap.jsx";
import Timeline from "./components/Timeline.jsx";
import Approvals from "./components/Approvals.jsx";
import Injection from "./components/Injection.jsx";
import Results from "./components/Results.jsx";

// VITE_DEMO_MODE=replay builds the static demo site: no backend, recorded answers only.
const REPLAY = import.meta.env.VITE_DEMO_MODE === "replay";
const api = REPLAY ? replay : live;

const CLEARANCE = ["public", "internal", "confidential", "restricted"];
const MODES = { rag: "只用 RAG", fixed: "固定 workflow", agent: "Agent" };
const STATUS = {
  done: "完成",
  awaiting_approval: "等待核准",
  executed: "已執行",
  rejected: "已駁回",
  incomplete: "未完成",
};

// Two lines at the top of the page; once the page scrolls it shrinks to a slim one-line strip
// (<= 32 px) so it never covers the question or the wafer map.
function Banner() {
  const [slim, setSlim] = useState(false);
  useEffect(() => {
    const scroller = document.querySelector(".app-scroll");
    const onScroll = () => {
      const y = Math.max(scroller?.scrollTop || 0, window.scrollY);
      setSlim((was) => (was ? y > 10 : y > 80)); // hysteresis: no flicker when the height changes
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    scroller?.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      scroller?.removeEventListener("scroll", onScroll);
    };
  }, []);
  return (
    <div className={`banner ${slim ? "banner-slim" : ""}`} role="note">
      {slim ? (
        <span>
          <b>錄製的示範</b>・回答事先以真實系統產生・合成資料
        </span>
      ) : (
        <>
          <b>錄製的示範</b>：回答為事先以真實系統產生，資料全部為虛構工廠的合成資料。
          <span className="banner-en">
            Recorded demo: answers were produced beforehand by the real system; all data is
            synthetic, from a fictional fab.
          </span>
        </>
      )}
    </div>
  );
}

function Badge({ u, active, onPick }) {
  return (
    <button
      type="button"
      className={`badge ${active ? "badge-on" : ""}`}
      aria-pressed={active}
      onClick={() => onPick(u.user_id)}
    >
      <span className="badge-name">{u.display_name}</span>
      <span className="code badge-id">{u.user_id}</span>
      <span className="badge-scope">
        {u.fabs.join("·")} · {u.departments.length > 2 ? `${u.departments.length} 部門` : u.departments.join("·")}
      </span>
      <span className={`clr clr-${u.clearance}`}>{CLEARANCE[u.clearance]}</span>
    </button>
  );
}

function Answer({ run, onCite }) {
  if (!run) return null;
  return (
    <section className="panel answer" aria-live="polite">
      <div className="panel-head">
        <h2>回答</h2>
        <span className={`state state-${run.status}`}>{STATUS[run.status] || run.status}</span>
        {run.refused && <span className="state state-refused">不給建議</span>}
      </div>
      <p className="answer-text">{run.answer}</p>
      <div className="cites">
        <span className="fine">引用</span>
        {run.citations?.length ? (
          run.citations.map((c) => (
            <button key={c} type="button" className="chip chip-cite code" onClick={() => onCite(c)}>
              {c}
            </button>
          ))
        ) : (
          <span className="fine">無</span>
        )}
      </div>
      <p className="fine meta-line">
        {MODES[run.mode] || run.mode} · 工具呼叫 {run.steps} · LLM 呼叫 {run.usage?.llm_calls ?? 0} · token{" "}
        {(run.usage?.input_tokens || 0) + (run.usage?.output_tokens || 0)}
      </p>
    </section>
  );
}

export default function App() {
  const [users, setUsers] = useState([]);
  const [me, setMe] = useState(null);
  const [docs, setDocs] = useState([]);
  const [scenes, setScenes] = useState([]);
  const [tour, setTour] = useState(0); // index into TOUR, or null for free exploration
  const [pick, setPick] = useState(""); // free mode: chosen scene id
  const [question, setQuestion] = useState(""); // live mode
  const [mode, setMode] = useState("agent"); // live mode
  const [run, setRun] = useState(null);
  const [runScene, setRunScene] = useState(null);
  const [focusId, setFocusId] = useState(null);
  const [results, setResults] = useState(null);
  const [showResults, setShowResults] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [subs] = useState(() => new URLSearchParams(window.location.search).get("subs") === "1");
  const approvalsRef = useRef(null);

  useEffect(() => {
    api.users().then(setUsers).catch((e) => setError(e.message));
    api.scenes().then(setScenes);
    api.results().then(setResults).catch(() => {});
  }, []);

  useEffect(() => {
    if (users.length && tour !== null) goTo(tour);
  }, [users.length]);

  async function login(userId) {
    const u = await api.login(userId);
    setMe(u);
    setDocs(await api.docs());
    setFocusId(null);
    return u;
  }

  const step = tour !== null ? TOUR[tour] : null;
  const mine = useMemo(() => scenes.filter((s) => s.user === me?.user_id), [scenes, me]);
  const sceneId = step?.sceneId || pick;
  const scene = scenes.find((s) => s.id === sceneId);

  async function goTo(i) {
    setTour(i);
    setError("");
    const s = TOUR[i];
    if (s.results) {
      setShowResults(true);
      return;
    }
    setShowResults(false);
    if (me?.user_id !== s.user) await login(s.user);
    if (!REPLAY && s.question) {
      setQuestion(s.question);
      setMode(s.mode);
    }
    if (runScene !== s.sceneId) {
      setRun(null);
      setRunScene(null);
    }
    if (s.key === "approval" && runScene !== s.sceneId) await ask(s.sceneId, s);
    if (s.key === "approval") {
      setTimeout(() => approvalsRef.current?.scrollIntoView({ block: "center" }), 100);
    }
  }

  async function switchUser(userId) {
    await login(userId);
    const keep = tour !== null && TOUR[tour].key === "approval"; // approving needs the run
    if (!keep) {
      setTour(null); // leaving the script: free exploration
      setRun(null);
      setRunScene(null);
    }
    setPick(scenes.find((s) => s.user === userId)?.id || "");
  }

  async function ask(id = sceneId, s = step) {
    setBusy(true);
    setError("");
    try {
      let r;
      if (REPLAY) {
        await new Promise((res) => setTimeout(res, 500)); // a short pause, like a real request
        r = await api.ask({ sceneId: id });
      } else {
        r = await api.ask({ question: question || s?.question, mode });
      }
      setRun(r);
      setRunScene(id);
      setFocusId(r.citations?.[0] || null);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const caption = step
    ? { zh: step.explain, en: step.caption_en }
    : scene
      ? { zh: scene.caption_zh, en: scene.caption_en }
      : null;

  return (
    <div className={`app ${subs ? "app-subs" : ""}`}>
      <div className="app-scroll">
        {REPLAY && <Banner />}
        <header className="top">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true" />
            <div>
              <h1>FabOps Copilot</h1>
              <p className="fine">夜班異常處理助理 · 虛構晶圓廠 Fab-X · 全部為合成資料</p>
            </div>
          </div>
          <nav className="tour-nav" aria-label="導覽">
            {tour === null ? (
              <button type="button" className="primary" onClick={() => goTo(0)}>
                開始導覽
              </button>
            ) : (
              <>
                <button type="button" onClick={() => goTo(Math.max(0, tour - 1))} disabled={tour === 0}>
                  上一步
                </button>
                <span className="fine tour-pos">
                  {tour + 1} / {TOUR.length}
                </span>
                <button
                  type="button"
                  className="primary"
                  onClick={() => goTo(Math.min(TOUR.length - 1, tour + 1))}
                  disabled={tour === TOUR.length - 1}
                >
                  下一步
                </button>
                <button type="button" className="quiet" onClick={() => setTour(null)}>
                  自由探索
                </button>
              </>
            )}
          </nav>
        </header>

        <section className="badges" aria-label="切換身分（demo 使用者）">
          {users.map((u) => (
            <Badge key={u.user_id} u={u} active={me?.user_id === u.user_id} onPick={switchUser} />
          ))}
        </section>

        <div className="grid">
          <nav className="rail" aria-label="情境">
            <ol>
              {TOUR.map((s, i) => (
                <li key={s.key}>
                  <button
                    type="button"
                    className={`rail-item ${tour === i ? "rail-on" : ""}`}
                    aria-current={tour === i ? "step" : undefined}
                    onClick={() => goTo(i)}
                  >
                    <span className="rail-n">{i + 1}</span>
                    {s.title}
                  </button>
                </li>
              ))}
            </ol>
            <p className="fine rail-note">也可以直接點上方的識別證切換身分，自由探索錄製過的問題。</p>
          </nav>

          {showResults ? (
            <main className="main main-wide">
              {step && (
                <section className="panel step-card">
                  <div className="panel-sub">情境 {tour + 1} · {step.title}</div>
                  <p>{step.explain}</p>
                </section>
              )}
              <Results results={results} />
            </main>
          ) : (
            <>
              <main className="main">
                {step && (
                  <section className="panel step-card">
                    <div className="panel-sub">情境 {tour + 1} · {step.title}</div>
                    <p>{step.explain}</p>
                  </section>
                )}
                {me && (
                  <section className="panel ask">
                    <div className="panel-head">
                      <h2>提問</h2>
                      <span className="fine">身分：{me.display_name}</span>
                    </div>
                    {REPLAY ? (
                      step?.sceneId ? (
                        <p className="question">{scene?.question}</p>
                      ) : (
                        <select
                          className="scene-select"
                          value={pick}
                          onChange={(e) => setPick(e.target.value)}
                          aria-label="錄製過的問題"
                        >
                          {mine.length === 0 && <option value="">這個身分沒有錄製的問題</option>}
                          {mine.map((s) => (
                            <option key={s.id} value={s.id}>
                              [{MODES[s.mode]}] {s.question}
                            </option>
                          ))}
                        </select>
                      )
                    ) : (
                      <textarea
                        rows={3}
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                        aria-label="問題"
                      />
                    )}
                    <div className="row">
                      {REPLAY ? (
                        <span className="fine">模式：{MODES[scene?.mode] || "—"} · 回放版只能選錄製過的問題</span>
                      ) : (
                        <select value={mode} onChange={(e) => setMode(e.target.value)} aria-label="模式">
                          {Object.entries(MODES).map(([v, l]) => (
                            <option key={v} value={v}>
                              {l}
                            </option>
                          ))}
                        </select>
                      )}
                      {step?.key !== "approval" && (
                        <button
                          type="button"
                          className="primary send"
                          disabled={busy || (REPLAY ? !sceneId : !question.trim())}
                          onClick={() => ask()}
                        >
                          {busy ? "查詢中…" : "送出問題"}
                        </button>
                      )}
                    </div>
                  </section>
                )}
                {error && <p className="msg-bad">{error}</p>}
                <Answer run={run} onCite={setFocusId} />
                {run && runScene === scene?.id && (
                  <Injection
                    scene={scene}
                    run={run}
                    cite={(c) => (
                      <span key={c} className="code">
                        {c}{" "}
                      </span>
                    )}
                  />
                )}
              </main>

              <aside className="evidence" aria-label="證據">
                <details open className="ev-block">
                  <summary>權限晶圓圖</summary>
                  <WaferMap
                    docs={docs}
                    retrieved={run?.retrieved || []}
                    cited={run?.citations || []}
                    focusId={focusId}
                    onFocus={setFocusId}
                  />
                </details>
                <details open className="ev-block">
                  <summary>Agent 步驟</summary>
                  <Timeline
                    calls={run?.calls}
                    proposal={run?.proposal}
                    runKey={`${runScene}-${refreshKey}`}
                  />
                </details>
                <details open className="ev-block" ref={approvalsRef}>
                  <summary>核准與 audit log</summary>
                  {me && <Approvals api={api} me={me} refreshKey={refreshKey} />}
                </details>
              </aside>
            </>
          )}
        </div>
        <footer className="foot fine">
          FabOps Copilot · 原始碼與評估方法：
          <a href="https://github.com/colin-lai-dev/fabops-copilot">github.com/colin-lai-dev/fabops-copilot</a>
        </footer>
      </div>
      {subs && caption && (
        <div className="subtitles" data-testid="subtitles">
          <div>{caption.zh}</div>
          <div className="en">{caption.en}</div>
        </div>
      )}
    </div>
  );
}
