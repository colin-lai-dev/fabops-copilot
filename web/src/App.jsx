import React, { useEffect, useMemo, useRef, useState } from "react";
import { live } from "./api.js";
import { replay } from "./replay.js";
import { TOUR } from "./tour.js";
import { LangContext, translate, useT } from "./i18n.js";
import WaferMap from "./components/WaferMap.jsx";
import Timeline from "./components/Timeline.jsx";
import Approvals from "./components/Approvals.jsx";
import Injection from "./components/Injection.jsx";
import Results from "./components/Results.jsx";

// VITE_DEMO_MODE=replay builds the static demo site: no backend, recorded answers only.
const REPLAY = import.meta.env.VITE_DEMO_MODE === "replay";
const api = REPLAY ? replay : live;

const CLEARANCE = ["public", "internal", "confidential", "restricted"];
const MODES = ["rag", "fixed", "agent"];

// Two lines at the top of the page; once the page scrolls it shrinks to a slim one-line strip
// (<= 32 px) so it never covers the question or the wafer map.
function Banner() {
  const t = useT();
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
          <b>{t("banner.title")}</b>・{t("banner.slim")}
        </span>
      ) : (
        <>
          <b>{t("banner.title")}</b>
          {t.lang === "en" ? ": " : "："}
          {t("banner.body")}
          {t.lang === "zh" && (
            <span className="banner-en">
              {translate("en", "banner.title")}: {translate("en", "banner.body")}
            </span>
          )}
        </>
      )}
    </div>
  );
}

function Badge({ u, active, onPick }) {
  const t = useT();
  return (
    <button
      type="button"
      className={`badge ${active ? "badge-on" : ""}`}
      aria-pressed={active}
      onClick={() => onPick(u.user_id)}
    >
      <span className="badge-name">{t.user(u)}</span>
      <span className="code badge-id">{u.user_id}</span>
      <span className="badge-scope">
        {u.fabs.join("·")} ·{" "}
        {u.departments.length > 2 ? t("badge.depts", { n: u.departments.length }) : u.departments.join("·")}
      </span>
      <span className={`clr clr-${u.clearance}`}>{CLEARANCE[u.clearance]}</span>
    </button>
  );
}

function Answer({ run, onCite }) {
  const t = useT();
  if (!run) return null;
  return (
    <section className="panel answer" aria-live="polite">
      <div className="panel-head">
        <h2>{t("answer.title")}</h2>
        <span className={`state state-${run.status}`}>{t(`status.${run.status}`)}</span>
        {run.refused && <span className="state state-refused">{t("answer.refused")}</span>}
      </div>
      {t.lang === "en" && <p className="fine zh-note">{t("answer.zhNote")}</p>}
      <p className="answer-text">{run.answer}</p>
      <div className="cites">
        <span className="fine">{t("answer.cites")}</span>
        {run.citations?.length ? (
          run.citations.map((c) => (
            <button key={c} type="button" className="chip chip-cite code" onClick={() => onCite(c)}>
              {c}
            </button>
          ))
        ) : (
          <span className="fine">{t("answer.none")}</span>
        )}
      </div>
      <p className="fine meta-line">
        {t("answer.meta", {
          mode: t(`mode.${run.mode}`),
          steps: run.steps,
          calls: run.usage?.llm_calls ?? 0,
          tokens: (run.usage?.input_tokens || 0) + (run.usage?.output_tokens || 0),
        })}
      </p>
    </section>
  );
}

export default function App() {
  const [lang, setLang] = useState(() =>
    new URLSearchParams(window.location.hash.slice(1)).get("lang") === "en" ? "en" : "zh",
  );
  useEffect(() => {
    document.documentElement.lang = lang === "en" ? "en" : "zh-Hant-TW";
  }, [lang]);
  return (
    <LangContext.Provider value={lang}>
      <Console lang={lang} setLang={setLang} />
    </LangContext.Provider>
  );
}

function Console({ lang, setLang }) {
  const t = useT();
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
              <p className="fine">{t("brand.sub")}</p>
            </div>
          </div>
          <nav className="tour-nav" aria-label={t("tour.nav")}>
            <button
              type="button"
              className="quiet lang-switch"
              aria-label={t("lang.label")}
              onClick={() => setLang(lang === "en" ? "zh" : "en")}
            >
              {t("lang.switch")}
            </button>
            {tour === null ? (
              <button type="button" className="primary" onClick={() => goTo(0)}>
                {t("tour.start")}
              </button>
            ) : (
              <>
                <button type="button" onClick={() => goTo(Math.max(0, tour - 1))} disabled={tour === 0}>
                  {t("tour.prev")}
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
                  {t("tour.next")}
                </button>
                <button type="button" className="quiet" onClick={() => setTour(null)}>
                  {t("tour.free")}
                </button>
              </>
            )}
          </nav>
        </header>

        <section className="badges" aria-label={t("badges.label")}>
          {users.map((u) => (
            <Badge key={u.user_id} u={u} active={me?.user_id === u.user_id} onPick={switchUser} />
          ))}
        </section>

        <div className="grid">
          <nav className="rail" aria-label={t("rail.label")}>
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
                    {t.pick(s, "title")}
                  </button>
                </li>
              ))}
            </ol>
            <p className="fine rail-note">{t("rail.note")}</p>
          </nav>

          {showResults ? (
            <main className="main main-wide">
              {step && (
                <section className="panel step-card">
                  <div className="panel-sub">{t("step.n", { n: tour + 1, title: t.pick(step, "title") })}</div>
                  <p>{t.pick(step, "explain")}</p>
                </section>
              )}
              <Results results={results} />
            </main>
          ) : (
            <>
              <main className="main">
                {step && (
                  <section className="panel step-card">
                    <div className="panel-sub">{t("step.n", { n: tour + 1, title: t.pick(step, "title") })}</div>
                    <p>{t.pick(step, "explain")}</p>
                  </section>
                )}
                {me && (
                  <section className="panel ask">
                    <div className="panel-head">
                      <h2>{t("ask.title")}</h2>
                      <span className="fine">{t("ask.as", { name: t.user(me) })}</span>
                    </div>
                    {REPLAY ? (
                      step?.sceneId ? (
                        <p className="question">{scene?.question}</p>
                      ) : (
                        <select
                          className="scene-select"
                          value={pick}
                          onChange={(e) => setPick(e.target.value)}
                          aria-label={t("ask.recorded")}
                        >
                          {mine.length === 0 && <option value="">{t("ask.none")}</option>}
                          {mine.map((s) => (
                            <option key={s.id} value={s.id}>
                              [{t(`mode.${s.mode}`)}] {s.question}
                            </option>
                          ))}
                        </select>
                      )
                    ) : (
                      <textarea
                        rows={3}
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                        aria-label={t("ask.question")}
                      />
                    )}
                    <div className="row">
                      {REPLAY ? (
                        <span className="fine">
                          {t("ask.mode", { mode: scene?.mode ? t(`mode.${scene.mode}`) : "—" })}
                        </span>
                      ) : (
                        <select value={mode} onChange={(e) => setMode(e.target.value)} aria-label={t("ask.modeSel")}>
                          {MODES.map((v) => (
                            <option key={v} value={v}>
                              {t(`mode.${v}`)}
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
                          {busy ? t("ask.busy") : t("ask.send")}
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

              <aside className="evidence" aria-label={t("ev.label")}>
                <details open className="ev-block">
                  <summary>{t("ev.wafer")}</summary>
                  <WaferMap
                    docs={docs}
                    retrieved={run?.retrieved || []}
                    cited={run?.citations || []}
                    focusId={focusId}
                    onFocus={setFocusId}
                    runKey={run ? `${runScene}-${refreshKey}` : null}
                  />
                </details>
                <details open className="ev-block">
                  <summary>{t("ev.steps")}</summary>
                  <Timeline
                    calls={run?.calls}
                    proposal={run?.proposal}
                    runKey={`${runScene}-${refreshKey}`}
                  />
                </details>
                <details open className="ev-block" ref={approvalsRef}>
                  <summary>{t("ev.approvals")}</summary>
                  {me && <Approvals api={api} me={me} refreshKey={refreshKey} />}
                </details>
              </aside>
            </>
          )}
        </div>
        <footer className="foot fine">
          {t("foot")}{" "}
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
