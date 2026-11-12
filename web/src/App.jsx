import React, { useCallback, useEffect, useRef, useState } from "react";
import { live } from "./api.js";
import { replay } from "./replay.js";
import { TOUR } from "./tour.js";
import { LangContext, translate, useT } from "./i18n.js";
import { verdict } from "./verdict.js";
import Lot from "./components/Lot.jsx";
import WaferMap from "./components/WaferMap.jsx";
import Timeline from "./components/Timeline.jsx";
import Approvals from "./components/Approvals.jsx";
import Injection from "./components/Injection.jsx";
import Results from "./components/Results.jsx";
import DocDrawer from "./components/DocDrawer.jsx";
import ScenePicker from "./components/ScenePicker.jsx";
import Logo from "./components/Logo.jsx";

// Design lab (handoff 022). The page is built around "the lot": six wafers, one per identity,
// for the same question. Picking a wafer keeps the question and shows that identity's own
// recorded run, so switching identity is itself the demonstration of permission.
//
// VITE_DEMO_MODE=replay builds the static demo site: no backend, recorded answers only.
const REPLAY = import.meta.env.VITE_DEMO_MODE === "replay";
const api = REPLAY ? replay : live;
const REPO = "https://github.com/colin-lai-dev/fabops-copilot";
const APPROVAL = TOUR.findIndex((s) => s.approval);
const NO_AP = { audit: null, msg: null };

// The one choreographed sequence: 0 unfiltered -> 1 permission filter -> 2 retrieval -> 3 cited.
// It plays by itself once, on first load; afterwards only when the visitor changes the question
// or presses Replay. Reduced motion shows the result at once.
const SEQ = [200, 520, 840];
const SEQ_END = 2500; // last wafer: 840 + 5 x 250 ms stagger + 320 ms fade
const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
function useSequence() {
  const [state, set] = useState({ phase: 3, playing: false, key: 0 });
  const timers = useRef([]);
  const play = useCallback(() => {
    timers.current.forEach(clearTimeout);
    if (reducedMotion()) {
      set((s) => ({ phase: 3, playing: false, key: s.key + 1 }));
      return;
    }
    set((s) => ({ phase: 0, playing: true, key: s.key + 1 }));
    timers.current = [
      ...SEQ.map((ms, i) => setTimeout(() => set((s) => ({ ...s, phase: i + 1 })), ms)),
      setTimeout(() => set((s) => ({ ...s, playing: false })), SEQ_END),
    ];
  }, []);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);
  return [state, play];
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
    <button
      type="button"
      className="tool-btn theme-switch"
      title={dark ? t("theme.toLight") : t("theme.toDark")}
      aria-label={t("theme.dark")}
      aria-pressed={dark}
      onClick={flip}
    >
      {dark ? (
        <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
          <circle cx="10" cy="10" r="3.6" fill="currentColor" />
          <g stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
            <path d="M10 1.8v2.2M10 16v2.2M1.8 10H4M16 10h2.2M4.2 4.2l1.6 1.6M14.2 14.2l1.6 1.6M4.2 15.8l1.6-1.6M14.2 5.8l1.6-1.6" />
          </g>
        </svg>
      ) : (
        <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
          <path d="M15.6 12.6A6.6 6.6 0 0 1 7.4 4.4a6.6 6.6 0 1 0 8.2 8.2z" fill="currentColor" />
        </svg>
      )}
    </button>
  );
}

// Text in the current language with the other language laid invisibly in the same grid cell:
// the box takes the taller of the two, so switching language does not reflow the page.
function Bi({ zh, en }) {
  const t = useT();
  const [cur, other] = t.lang === "en" ? [en, zh] : [zh, en];
  return (
    <span className="bi">
      <span>{cur}</span>
      <span className="bi-ghost" aria-hidden="true" lang={t.lang === "en" ? "zh-Hant-TW" : "en"}>
        {other}
      </span>
    </span>
  );
}

// What to try next in the approval step, for the identity on screen: the requester is refused,
// someone who cannot see the target never sees the proposal, a qualified approver executes it.
function ApprovalGuide({ run, me, users, attempts, onSwitch }) {
  const t = useT();
  const p = run.proposal;
  const user = (id) => users.find((u) => u.user_id === id);
  const go = (id) => (
    <button type="button" className="link" onClick={() => onSwitch(id)}>
      {t("apx.switchTo", { name: t.user(user(id)) })}
    </button>
  );
  const done = run.status === "executed" || attempts.some((a) => a.ok && a.approved);
  const deniedHere = attempts.some((a) => a.user === me?.user_id && !a.ok);
  let text;
  let next = null;
  if (done) text = t("apx.done");
  else if (me?.user_id === p.requester) {
    text = deniedHere ? t("apx.requesterDone") : t("apx.requester");
    if (deniedHere) next = "lead_fx1_multi";
  } else if (me?.user_id === "lead_fx1_multi") {
    text = t("apx.lead");
    next = "admin_all";
  } else if (me?.user_id === "admin_all") text = t("apx.admin");
  else {
    text = t("apx.other");
    next = "admin_all";
  }
  return (
    <div className="guide">
      <p>
        <b>{t.user(me)}</b>
        {t.lang === "en" ? ": " : "："}
        {text}
      </p>
      <p className="guide-links">
        {next && go(next)}
        {!done && me?.user_id !== p.requester && go(p.requester)}
      </p>
    </div>
  );
}

function Cites({ run, onCite }) {
  const t = useT();
  return (
    <div className="cites">
      <span className="fine">{t("answer.cites")}</span>
      {run.citations?.length ? (
        run.citations.map((c) => (
          <button key={c} type="button" className="chip chip-cite code" title={t("answer.openDoc")} onClick={() => onCite(c)}>
            {c}
          </button>
        ))
      ) : (
        <span className="fine">{t("answer.none")}</span>
      )}
    </div>
  );
}

function Footer({ meta }) {
  const t = useT();
  const parts = [
    __SITE_VERSION__, // from the git tag (or lab commit) at build time
    meta.recorded_at && `${t("foot.recorded")} ${meta.recorded_at.slice(0, 10)}`,
    meta.model,
  ].filter(Boolean);
  return (
    <footer className="foot">
      <nav className="foot-links" aria-label={t("foot.label")}>
        <a href={REPO}>{t("foot.source")}</a>
        <a href={`${REPO}#eval-results`}>{t("foot.evals")}</a>
        <a href={`${REPO}/releases/tag/demo-v1`}>{t("foot.video")}</a>
        {REPLAY && <a href={`${import.meta.env.BASE_URL}v8/`}>{t("foot.v8")}</a>}
      </nav>
      <p>{t("foot.synthetic")}</p>
      <p className="foot-meta">
        <span>{parts.join(" · ")}</span>
        <span>
          {t("foot.by")} <a href="https://github.com/colin-lai-dev">Colin Lai</a>
        </span>
      </p>
    </footer>
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
  const [questions, setQuestions] = useState([]);
  const [scenes, setScenes] = useState([]);
  const [results, setResults] = useState(null);
  const [meta, setMeta] = useState({});
  const [ready, setReady] = useState(false);

  const [tour, setTour] = useState(0); // index into TOUR, or null outside the guided steps
  const [qid, setQid] = useState(null); // the question on screen (a six-identity group)
  const [lot, setLot] = useState([]); // per identity: what it may see, and its own run
  const [uid, setUid] = useState(null); // the current identity
  const [asker, setAsker] = useState(null); // whose run is on screen (differs from uid only while approving)
  const [docs, setDocs] = useState([]); // the current identity's wafer
  const [run, setRun] = useState(null);
  const [compare, setCompare] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [focusId, setFocusId] = useState(null);
  const [openDoc, setOpenDoc] = useState(null);
  const [attempts, setAttempts] = useState([]); // approval tries on screen: { user, ok, approved }
  const [apView, setApView] = useState(NO_AP); // approval result and audit log on screen
  const [refreshKey, setRefreshKey] = useState(0);
  const [liveQ, setLiveQ] = useState(TOUR[0].question); // live backend: free question
  const [liveMode, setLiveMode] = useState("rag");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [seq, play] = useSequence();
  const [subs] = useState(() => new URLSearchParams(window.location.search).get("subs") === "1");
  const cur = useRef({ lot: [], qid: null, uid: null }); // latest values for async chains

  useEffect(() => {
    Promise.all([api.users(), api.questions(), api.scenes()])
      .then(([u, q, s]) => {
        setUsers(u);
        setQuestions(q);
        setScenes(s);
        setReady(true);
      })
      .catch((e) => setError(e.message));
    api.results().then(setResults).catch(() => {});
    Promise.resolve(api.meta?.()).then((m) => m && setMeta(m)).catch(() => {});
  }, []);

  const step = tour !== null ? TOUR[tour] : null;
  const slot = lot.find((s) => s.user.user_id === asker) || null;
  const me = users.find((u) => u.user_id === uid) || null;
  const onMain = Boolean(slot?.main) || (!REPLAY && Boolean(run?.proposal)); // the run with the approval flow
  const approving = onMain && (Boolean(step?.approval) || attempts.length > 0 || uid !== asker);

  // ---- showing a question as an identity -------------------------------------------------
  async function signIn(u) {
    if (cur.current.uid !== u) setApView(NO_AP); // an audit log belongs to whoever fetched it
    cur.current.uid = u;
    await api.login(u);
    setUid(u);
    setDocs(await api.docs());
    setOpenDoc(null);
  }

  async function view(u, lotNow = cur.current.lot) {
    await signIn(u);
    setAsker(u);
    const s = lotNow.find((x) => x.user.user_id === u);
    const r = REPLAY ? (s?.sceneId ? await api.ask({ sceneId: s.sceneId }) : null) : (s?.run ?? null);
    setRun(r);
    setFocusId(r?.citations?.[0] || null);
    setRefreshKey((k) => k + 1);
  }

  async function enter(q, u, { cmp = false } = {}) {
    setError("");
    setShowResults(false);
    setCompare(cmp);
    let lotNow = cur.current.lot;
    const changed = q !== cur.current.qid || !lotNow.length;
    if (changed) {
      lotNow = await api.lot(q);
      cur.current.lot = lotNow;
      cur.current.qid = q;
      setLot(lotNow);
      setQid(q);
      setAttempts([]);
      setApView(NO_AP);
    }
    const has = (id) => lotNow.some((s) => s.user.user_id === id && (s.sceneId || !REPLAY));
    const who = u && has(u) ? u : has(cur.current.uid) ? cur.current.uid : lotNow.find((s) => s.sceneId)?.user.user_id;
    await view(who || lotNow[0].user.user_id, lotNow);
    if (changed && REPLAY) play();
    return who;
  }

  const stepFor = (q, u, cmp) => {
    const i = TOUR.findIndex((s) => s.q === q && !s.approval && Boolean(s.compare) === cmp && (cmp || s.as === u));
    return i >= 0 ? i : null;
  };

  async function goTo(i) {
    const s = TOUR[i];
    setTour(i);
    if (s.results) {
      setShowResults(true);
      return;
    }
    if (!REPLAY) {
      setLiveQ(s.question);
      setLiveMode(s.mode);
    }
    await enter(REPLAY ? s.q : "live", s.as, { cmp: Boolean(s.compare) });
  }

  async function actAs(u) {
    setTour(APPROVAL); // deciding the proposal on screen as someone else
    await signIn(u);
    setRefreshKey((k) => k + 1);
  }

  async function pick(u) {
    if (approving) return actAs(u);
    setCompare(false);
    await view(u);
    setTour(stepFor(cur.current.qid, u, false));
    return undefined;
  }

  async function pickQuestion(q) {
    const who = await enter(q, null);
    setTour(stepFor(q, who, false));
  }

  function toggleCompare() {
    setCompare(!compare);
    setTour(stepFor(qid, asker, !compare));
  }

  // ---- live backend only -------------------------------------------------------------------
  const fill = (s, r) => {
    const at = new Map((s.docs || []).map((d, i) => [d.doc_id, i]));
    const idx = (ids) => (ids || []).map((id) => at.get(id)).filter((i) => i !== undefined);
    return { ...s, run: r, retrieved: idx(r.retrieved), cited: idx(r.citations) };
  };
  async function send(all = false) {
    setBusy(true);
    setError("");
    try {
      const cleared = cur.current.lot.map((s) => ({ ...s, run: null, retrieved: [], cited: [] }));
      const mine = await api.ask({ question: liveQ, mode: liveMode });
      let next = cleared.map((s) => (s.user.user_id === uid ? fill(s, mine) : s));
      if (all)
        for (const s of cleared)
          if (s.user.user_id !== uid) {
            const r = await api.askAs(s.user.user_id, liveQ, liveMode);
            next = next.map((x) => (x.user.user_id === s.user.user_id ? fill(x, r) : x));
          }
      cur.current.lot = next;
      setLot(next);
      setRun(mine);
      setAsker(uid);
      setAttempts([]);
      setApView(NO_AP);
      setFocusId(mine.citations?.[0] || null);
      setRefreshKey((k) => k + 1);
      play();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  // ---- deep links ----------------------------------------------------------------------------
  //   #step=approval&as=admin_all   #q=comp&as=lead_fx1_multi   #q=epd&compare=1   #lang=en
  //   (older links still work: #scene=<recorded scene>, #six=<group>)
  const hashReady = useRef(false);
  async function applyHash() {
    const h = new URLSearchParams(window.location.hash.slice(1));
    if (h.get("lang") === "en" || h.get("lang") === "zh") setLang(h.get("lang"));
    const as = users.find((u) => u.user_id === h.get("as"))?.user_id;
    const stepAt = TOUR.findIndex((s) => s.key === h.get("step"));
    const scene = scenes.find((s) => s.id === h.get("scene"));
    const byScene = scene && questions.find((q) => q.question === scene.question && q.mode === scene.mode);
    const q = questions.find((x) => x.id === (h.get("q") || h.get("six"))) || byScene;
    if (stepAt >= 0) {
      await goTo(stepAt);
      if (as && TOUR[stepAt].approval && as !== TOUR[stepAt].as) await actAs(as);
      return;
    }
    if (q && REPLAY) {
      const cmp = Boolean(h.get("six")) || h.get("compare") === "1";
      const who = await enter(q.id, as || scene?.user || null, { cmp });
      setTour(stepFor(q.id, who, cmp));
      return;
    }
    await goTo(tour ?? 0);
    if (as) await pick(as);
  }

  useEffect(() => {
    if (!ready || hashReady.current) return;
    applyHash().finally(() => {
      hashReady.current = true;
    });
  }, [ready]);

  useEffect(() => {
    const onHash = () => applyHash();
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  });

  // Keep the hash in step with what is on screen (replaceState: no history spam, no hashchange).
  useEffect(() => {
    if (!hashReady.current) return;
    const h = new URLSearchParams();
    if (tour !== null) {
      h.set("step", TOUR[tour].key);
      if (TOUR[tour].approval && uid && uid !== TOUR[tour].as) h.set("as", uid);
    } else if (qid && REPLAY) {
      h.set("q", qid);
      if (uid) h.set("as", uid);
      if (compare) h.set("compare", "1");
    } else if (uid) h.set("as", uid);
    if (lang === "en") h.set("lang", "en");
    const next = `#${h.toString()}`;
    if (next !== window.location.hash) window.history.replaceState(null, "", next);
  }, [tour, qid, uid, compare, lang]);

  // ---- pieces ----------------------------------------------------------------------------------
  const nextStep = tour !== null && tour < TOUR.length - 1 ? TOUR[tour + 1] : null;
  const scene = slot?.sceneId ? scenes.find((s) => s.id === slot.sceneId) : null;
  const ownRun = uid === asker; // the big wafer shows retrieval only for the identity that asked
  const asked = users.find((u) => u.user_id === asker);
  const proposalState = run?.proposal
    ? slot?.rejectedAfter
      ? "rejected"
      : run.status === "executed"
        ? "executed"
        : run.proposal.status === "pending"
          ? "awaiting_approval"
          : run.proposal.status
    : null;
  const v = slot && run ? verdict({ ...slot, run }) : null;
  const onCite = (c) => {
    setFocusId(c);
    setOpenDoc(c);
  };
  const caption = step ? { zh: step.explain, en: step.caption_en } : null;

  return (
    <div className={`app ${subs ? "app-subs" : ""}`}>
      <div className="app-scroll">
        <header className="top">
          <div className="brand">
            <Logo size={34} />
            <div>
              <h1>FabOps Copilot</h1>
              <p className="brand-sub">{t("brand.sub")}</p>
            </div>
          </div>
          <div className="top-tools">
            <ThemeToggle />
            <div className="lang-seg" role="group" aria-label={t("lang.label")}>
              {[
                ["zh", "中", "zh-Hant-TW", "中文"],
                ["en", "EN", "en", "English"],
              ].map(([code, label, tag, full]) => (
                <button
                  key={code}
                  type="button"
                  lang={tag}
                  title={full}
                  aria-label={`${label} ${full}`}
                  aria-pressed={lang === code}
                  onClick={() => setLang(code)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </header>

        <p className="strip" role="note">
          {REPLAY && <span>{t("strip.recorded")}</span>}
        </p>

        <nav className="steps" aria-label={t("rail.label")}>
          <ol>
            {TOUR.map((s, i) => (
              <li key={s.key}>
                <button
                  type="button"
                  className={`step-tab ${tour === i ? "step-on" : ""}`}
                  aria-current={tour === i ? "step" : undefined}
                  onClick={() => goTo(i)}
                >
                  <span className="step-n">{i + 1}</span>
                  <span className="step-label">{t.pick(s, "title")}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>

        <div className="caption">
          <p>{step ? <Bi zh={step.explain} en={step.explain_en} /> : <Bi zh={" "} en={" "} />}</p>
          {nextStep && (
            <button type="button" className="link caption-next" onClick={() => goTo(tour + 1)}>
              <Bi
                zh={`${translate("zh", "step.next", { title: nextStep.title })} →`}
                en={`${translate("en", "step.next", { title: nextStep.title_en })} →`}
              />
            </button>
          )}
        </div>

        {showResults ? (
          <main className="stage">
            <Results results={results} />
          </main>
        ) : (
          <main className="stage">
            <section className="qbar" aria-label={t("q.label")}>
              {REPLAY ? (
                <ScenePicker scenes={questions} value={qid || ""} onChange={pickQuestion} />
              ) : (
                <textarea rows={2} value={liveQ} onChange={(e) => setLiveQ(e.target.value)} aria-label={t("ask.question")} />
              )}
              <div className="qbar-tools">
                {REPLAY ? (
                  <button type="button" className="replay" onClick={play} disabled={seq.playing}>
                    {t("q.replay")}
                  </button>
                ) : (
                  <>
                    <select value={liveMode} onChange={(e) => setLiveMode(e.target.value)} aria-label={t("ask.modeSel")}>
                      {["rag", "fixed", "agent"].map((m) => (
                        <option key={m} value={m}>
                          {t(`mode.${m}`)}
                        </option>
                      ))}
                    </select>
                    <button type="button" className="primary send" disabled={busy || !liveQ.trim()} onClick={() => send(false)}>
                      {busy ? t("ask.busy") : t("q.send")}
                    </button>
                    <button type="button" disabled={busy || !liveQ.trim()} onClick={() => send(true)}>
                      {t("q.askAll")}
                    </button>
                  </>
                )}
                <button type="button" className="compare-toggle" aria-pressed={compare} onClick={toggleCompare}>
                  {compare ? t("lot.single") : t("lot.compare")}
                </button>
              </div>
            </section>
            {error && <p className="msg-bad">{error}</p>}

            <Lot lot={lot} uid={uid} onPick={pick} phase={seq.phase} playing={seq.playing} playKey={seq.key} compare={compare} live={!REPLAY} />

            {!compare && me && (
              <section className="detail" aria-live="polite">
                <div className="detail-main">
                  <div className="detail-head">
                    <h2>{t("detail.answerOf", { name: t.user(asked) })}</h2>
                    {v && <span className={`tag tone-${v.tone}`}>{t(v.key)}</span>}
                  </div>
                  {!run ? (
                    <p className="empty">{t(REPLAY ? "detail.none" : "detail.ask", { name: t.user(asked) })}</p>
                  ) : (
                    <>
                      {v?.why && <p className="why">{t(v.why)}</p>}
                      {run.mode === "rag" ? (
                        <p className="answer-text">{run.answer}</p>
                      ) : (
                        <Timeline
                          run={run}
                          playing={seq.playing}
                          proposalState={proposalState}
                          proposalNote={slot?.rejectedAfter ? t("detail.rejectedAfter") : null}
                        />
                      )}
                      <Cites run={run} onCite={onCite} />
                      <p className="fine meta-line">
                        {t("answer.meta", {
                          mode: t(`mode.${run.mode}`),
                          steps: run.steps,
                          calls: run.usage?.llm_calls ?? 0,
                          tokens: (run.usage?.input_tokens || 0) + (run.usage?.output_tokens || 0),
                        })}
                      </p>
                      {/* always laid out (hidden in Chinese) so switching language moves nothing */}
                      <p className={`fine zh-note ${t.lang === "en" ? "" : "ghost"}`} aria-hidden={t.lang !== "en"}>
                        {translate("en", "answer.zhNote")}
                      </p>
                      {scene && (
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
                    </>
                  )}
                </div>

                <aside className="detail-side">
                  {onMain && run?.proposal && (
                    <section className="approve-panel">
                      <h2>{t("ap.title")}</h2>
                      {/* the proposal and its buttons first (in view on a 1280 x 800 screen), then
                          what to try next as this identity */}
                      <Approvals
                        guide={<ApprovalGuide run={run} me={me} users={users} attempts={attempts} onSwitch={actAs} />}
                        api={api}
                        me={me}
                        refreshKey={refreshKey}
                        onDecided={(d) => setRun((r) => (r ? { ...r, status: d.status, proposal: d.proposal ?? r.proposal } : r))}
                        onAttempt={(a) => setAttempts((xs) => [...xs, { user: me.user_id, ...a }])}
                        view={apView}
                        setView={setApView}
                      />
                    </section>
                  )}
                  <h2 className="side-title">{t("detail.wafer", { name: t.user(me) })}</h2>
                  <WaferMap
                    docs={docs}
                    retrieved={ownRun ? run?.retrieved || [] : []}
                    cited={ownRun ? run?.citations || [] : []}
                    focusId={ownRun ? focusId : null}
                    onFocus={setFocusId}
                    phase={seq.phase}
                    animating={seq.playing}
                  />
                </aside>
              </section>
            )}
          </main>
        )}
        <Footer meta={meta} />
      </div>
      {openDoc && run && <DocDrawer docId={openDoc} load={api.doc} answer={run.answer} onClose={() => setOpenDoc(null)} />}
      {subs && caption && (
        <div className="subtitles" data-testid="subtitles">
          <div>{caption.zh}</div>
          <div className="en">{caption.en}</div>
        </div>
      )}
    </div>
  );
}
