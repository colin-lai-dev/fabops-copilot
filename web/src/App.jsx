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
import DocDrawer from "./components/DocDrawer.jsx";
import SixWay from "./components/SixWay.jsx";
import Clearance from "./components/Clearance.jsx";

// VITE_DEMO_MODE=replay builds the static demo site: no backend, recorded answers only.
const REPLAY = import.meta.env.VITE_DEMO_MODE === "replay";
const api = REPLAY ? replay : live;

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

// Light / dark: follows the system until the visitor picks one; the pick is remembered.
const THEME_KEY = "fabops-theme";
const systemDark = () => window.matchMedia?.("(prefers-color-scheme: dark)").matches;
function readTheme() {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

function ThemeToggle() {
  const t = useT();
  const [chosen, setChosen] = useState(readTheme);
  const [sys, setSys] = useState(systemDark);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    const on = () => setSys(mq.matches);
    mq?.addEventListener?.("change", on);
    return () => mq?.removeEventListener?.("change", on);
  }, []);
  const dark = chosen ? chosen === "dark" : sys;
  function flip() {
    const next = dark ? "light" : "dark";
    setChosen(next);
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      /* private mode: the choice lasts for this page only */
    }
  }
  return (
    <button type="button" className="quiet theme-switch" title={t("theme.label")} aria-pressed={dark} onClick={flip}>
      <span aria-hidden="true">{dark ? "☀" : "☾"}</span> {dark ? t("theme.toLight") : t("theme.toDark")}
    </button>
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
      <Clearance level={u.clearance} />
    </button>
  );
}

// Agent / fixed-workflow answers are long: show the conclusion and the action waiting for
// approval first, and fold the caveats and details (display only; the text is unchanged).
const NOTE_START = /(?<=[。！？])\s*(?=注意|另外|此外|提醒|補充|但|不過)/;

export function splitAgentAnswer(text) {
  const at = text.search(NOTE_START);
  if (at > 0) return [text.slice(0, at).trim(), text.slice(at).trim()];
  const sents = text.split(/(?<=[。！？])/);
  if (sents.length <= 2) return [text, ""];
  return [sents.slice(0, 2).join("").trim(), sents.slice(2).join("").trim()];
}

function AgentAnswer({ run }) {
  const t = useT();
  const [head, notes] = splitAgentAnswer(run.answer || "");
  const p = run.proposal;
  return (
    <div className="agent-answer">
      <div className="panel-sub">{t("answer.conclusion")}</div>
      <p className="answer-text">{head}</p>
      {p && (
        <div className="pending-action">
          <div className="panel-sub">{t("answer.pending")}</div>
          <div>
            <b>{t(`action.${p.action}`)}</b> <span className="code">{p.target_id}</span>
            <span className={`state state-${p.status === "pending" ? "awaiting_approval" : p.status}`}>
              {p.status === "pending" ? t("status.awaiting_approval") : t(`status.${p.status}`)}
            </span>
          </div>
        </div>
      )}
      {notes && (
        <details className="answer-notes">
          <summary>{t("answer.notes")}</summary>
          <p className="answer-text">{notes}</p>
        </details>
      )}
    </div>
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
      {run.mode === "rag" ? (
        <p className="answer-text">{run.answer}</p>
      ) : (
        <AgentAnswer run={run} />
      )}
      <div className="cites">
        <span className="fine">{t("answer.cites")}</span>
        {run.citations?.length ? (
          run.citations.map((c) => (
            <button
              key={c}
              type="button"
              className="chip chip-cite code"
              title={t("answer.openDoc")}
              onClick={() => onCite(c)}
            >
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
  const [openDoc, setOpenDoc] = useState(null); // cited document shown in the drawer
  const [six, setSix] = useState(null); // six-identity view: group id (replay) or "live"
  const [sixData, setSixData] = useState(null);
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

  // Deep links (handoff 015 F): the URL hash names a tour step, a recorded scene (optionally
  // seen as another identity, e.g. the approver), or a six-identity group, plus the language:
  //   #step=approval   #scene=triage-approval&as=admin_all&lang=en   #six=comp
  const hashReady = useRef(false);
  async function applyHash() {
    const h = new URLSearchParams(window.location.hash.slice(1));
    if (h.get("lang") === "en" || h.get("lang") === "zh") setLang(h.get("lang"));
    const as = users.find((u) => u.user_id === h.get("as"))?.user_id;
    const stepAt = TOUR.findIndex((s) => s.key === h.get("step"));
    const target = scenes.find((s) => s.id === h.get("scene"));
    const group = h.get("six");
    if (stepAt >= 0) return goTo(stepAt);
    if (target) {
      setTour(null);
      setSix(null);
      setShowResults(false);
      await login(target.user);
      setPick(target.id);
      await ask(target.id, null);
      if (as && as !== target.user) await login(as); // e.g. the approver of this proposal
      return undefined;
    }
    if (group && REPLAY) {
      setTour(null);
      setShowResults(false);
      await login(as || users[0].user_id);
      return openSix(group);
    }
    if (as) {
      setTour(null);
      setShowResults(false);
      await login(as);
      setPick(scenes.find((s) => s.user === as)?.id || "");
      return undefined;
    }
    return goTo(tour ?? 0);
  }

  useEffect(() => {
    if (!users.length || (REPLAY && !scenes.length) || hashReady.current) return;
    applyHash().finally(() => {
      hashReady.current = true;
    });
  }, [users.length, scenes.length]);

  useEffect(() => {
    const onHash = () => applyHash();
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  });

  // Keep the hash in step with what is on screen (replaceState: no history spam, no hashchange).
  useEffect(() => {
    if (!hashReady.current) return;
    const h = new URLSearchParams();
    if (tour !== null) h.set("step", TOUR[tour].key);
    else if (six && REPLAY) h.set("six", six);
    else if (runScene) h.set("scene", runScene);
    if (me && tour === null) h.set("as", me.user_id);
    if (lang === "en") h.set("lang", "en");
    const next = h.toString() ? `#${h.toString()}` : " ";
    if (next.trim() !== window.location.hash) {
      window.history.replaceState(null, "", next === " " ? window.location.pathname + window.location.search : next);
    }
  }, [tour, six, runScene, me, lang]);

  async function login(userId) {
    setOpenDoc(null);
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
    setSix(null);
    if (s.results) {
      setShowResults(true);
      return;
    }
    setShowResults(false);
    if (s.six) openSix(s.six);
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

  async function openSix(groupOrQuestion) {
    setSix(groupOrQuestion);
    setSixData(null);
    try {
      setSixData(await api.sixWay(groupOrQuestion));
    } catch (e) {
      setError(e.message);
      setSix(null);
    }
  }

  async function switchUser(userId) {
    setSix(null);
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
            <ThemeToggle />
            <button
              type="button"
              className="quiet lang-switch"
              title={t("lang.label")}
              lang={lang === "en" ? "zh-Hant-TW" : "en"}
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

          {six ? (
            <main className="main main-wide">
              {step && (
                <section className="panel step-card">
                  <div className="panel-sub">{t("step.n", { n: tour + 1, title: t.pick(step, "title") })}</div>
                  <p>{t.pick(step, "explain")}</p>
                </section>
              )}
              <SixWay data={sixData} onClose={step?.six ? null : () => setSix(null)} />
            </main>
          ) : showResults ? (
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
                          {MODES.filter((m) => mine.some((s) => s.mode === m)).map((m) => (
                            // the mode is the group label, never glued to the question text
                            <optgroup key={m} label={t(`mode.${m}`)}>
                              {mine
                                .filter((s) => s.mode === m)
                                .map((s) => (
                                  <option key={s.id} value={s.id}>
                                    {s.question}
                                  </option>
                                ))}
                            </optgroup>
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
                      {REPLAY && scene?.six_unavailable && (
                        <p className="fine six-unavailable">{t("six.unavailable")}</p>
                      )}
                      {(REPLAY ? scene?.groups?.length > 0 : question.trim()) && (
                        <button
                          type="button"
                          className="six-open"
                          disabled={busy}
                          onClick={() => openSix(REPLAY ? scene.groups[0] : question)}
                        >
                          {t("ask.six")}
                        </button>
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
                <Answer
                  run={run}
                  onCite={(c) => {
                    setFocusId(c);
                    setOpenDoc(c);
                  }}
                />
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
                  {me && (
                    <Approvals
                      api={api}
                      me={me}
                      refreshKey={refreshKey}
                      onDecided={(d) =>
                        setRun((r) => (r ? { ...r, status: d.status, proposal: d.proposal ?? r.proposal } : r))
                      }
                    />
                  )}
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
      {openDoc && run && (
        <DocDrawer docId={openDoc} load={api.doc} answer={run.answer} onClose={() => setOpenDoc(null)} />
      )}
      {subs && caption && (
        <div className="subtitles" data-testid="subtitles">
          <div>{caption.zh}</div>
          <div className="en">{caption.en}</div>
        </div>
      )}
    </div>
  );
}
