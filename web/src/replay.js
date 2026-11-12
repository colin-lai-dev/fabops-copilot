// Replay backend for the static demo site (VITE_DEMO_MODE=replay). Same interface as api.js.
// Every answer, trace, proposal, decision and audit entry comes from
// public/replay/scenes.json, recorded from the real system (scripts/record_replay.py).
// Nothing is generated here, and only recorded questions can be asked.

let data = null;
let me = null;
let askedTriage = false;
let lastDecision = null; // index into the triage scene's decision steps
let lastScene = null; // the scene whose answer is on screen

async function load() {
  if (!data) data = await (await fetch(`${import.meta.env.BASE_URL}replay/scenes.json`)).json();
  return data;
}

const triage = () => data.scenes.find((s) => s.approval_steps?.length);
const decisions = () => triage().approval_steps.filter((s) => s.kind === "decision");

export const replay = {
  replay: true,
  users: async () => (await load()).users,
  login: async (userId) => {
    me = (await load()).users.find((u) => u.user_id === userId);
    return me;
  },
  // Same shape as GET /api/docs: locked dies carry no metadata.
  docs: async () => {
    const d = await load();
    const seen = new Set(d.visible_by_user[me.user_id]);
    return d.docs.map((doc, i) =>
      seen.has(i) ? { ...doc, visible: true } : { visible: false, doc_type: null },
    );
  },
  scenes: async () => (await load()).scenes,
  // The recorded questions (one per six-identity group).
  questions: async () =>
    (await load()).groups.map((g) => ({
      id: g.id,
      question: g.question,
      mode: g.mode,
      title: g.title_zh,
      title_en: g.title_en,
      target: g.target_doc || null,
    })),
  // The lot view (design lab): one question, and per identity what it may see and its own
  // recorded run. Only index sets leave this module: a locked document's id or attributes are
  // never handed to the page for an identity that cannot see it.
  lot: async (qid) => {
    const d = await load();
    const g = d.groups.find((x) => x.id === qid);
    if (!g) return [];
    const at = new Map(d.docs.map((doc, i) => [doc.doc_id, i]));
    const sceneOf = (u) =>
      g.scenes.length
        ? d.scenes.find((s) => g.scenes.includes(s.id) && s.user === u)
        : d.scenes.find(
            (s) => !s.id.startsWith("six-") && s.user === u && s.question === g.question && s.mode === g.mode,
          );
    const idx = (ids) => (ids || []).map((id) => at.get(id)).filter((i) => i !== undefined);
    return d.users.map((user) => {
      const s = sceneOf(user.user_id);
      const seen = d.visible_by_user[user.user_id];
      return {
        user,
        sceneId: s?.id ?? null,
        run: s?.response ?? null,
        cutOff: Boolean(s?.answer_cut_off),
        rejectedAfter: Boolean(s?.proposal_rejected_after_recording),
        main: Boolean(s?.approval_steps?.length),
        visible: seen,
        total: d.docs.length,
        retrieved: idx(s?.response?.retrieved),
        cited: idx(s?.response?.citations),
        targetVisible: g.target_doc ? seen.includes(at.get(g.target_doc)) : null,
      };
    });
  },
  meta: async () => {
    const d = await load();
    return { recorded_at: d.recorded_at, model: d.system.match(/Claude [A-Za-z]+ [\d.]+/)?.[0] };
  },
  // "One question, six identities": the recorded group, one column per demo user.
  sixWay: async (groupId) => {
    const d = await load();
    const g = d.groups?.find((x) => x.id === groupId);
    if (!g) return { columns: [] };
    if (g.unavailable) return { question: g.question, title: g.title_zh, title_en: g.title_en, unavailable: g.unavailable, columns: [] };
    const idx = d.docs.findIndex((doc) => doc.doc_id === g.target_doc);
    const columns = d.users.map((user) => {
      const s = d.scenes.find((x) => g.scenes.includes(x.id) && x.user === user.user_id);
      const seen = d.visible_by_user[user.user_id];
      return {
        user,
        run: s?.response,
        cutOff: Boolean(s?.answer_cut_off),
        visible: seen.length,
        total: d.docs.length,
        targetVisible: g.target_doc ? seen.includes(idx) : null,
      };
    });
    return { question: g.question, title: g.title_zh, title_en: g.title_en, target: g.target_doc, columns };
  },
  // A cited document as the asker saw it at recording time (fetched with their token from the
  // permission-checked API). Anything else, including every locked document, is "not found".
  doc: async (docId) => {
    if (!lastScene) return null;
    if (lastScene.user !== me?.user_id) throw new Error("not-recorded"); // asked by someone else
    return lastScene.cited_docs?.[docId] ?? null;
  },
  ask: async ({ sceneId }) => {
    const s = (await load()).scenes.find((x) => x.id === sceneId);
    if (!s || s.user !== me?.user_id) throw new Error("這個問題不是由目前身分錄製的");
    if (s.approval_steps?.length) askedTriage = true;
    lastScene = s;
    return s.response;
  },
  pending: async () => {
    const s = triage();
    if (!s || !me || !askedTriage) return [];
    if (lastDecision !== null && decisions()[lastDecision].status_code === 200) return [];
    return s.approval_steps.find((x) => x.kind === "pending").by_user[me.user_id] ?? [];
  },
  decide: async (pid, approved) => {
    const i = decisions().findIndex((d) => d.user === me.user_id && d.approved === approved);
    if (i < 0) throw new Error("這個操作沒有錄製（回放版只重現錄製過的決定）");
    lastDecision = i;
    const d = decisions()[i];
    if (d.status_code !== 200) throw new Error(d.detail);
    return d.run;
  },
  // Recorded direct API calls by an identity the proposal is not even listed for (it cannot
  // see the target): shown as what happened, there is nothing to click.
  blindAttempts: async () => {
    const s = triage();
    if (!s || !me || !askedTriage) return [];
    const listed = s.approval_steps.find((x) => x.kind === "pending").by_user[me.user_id] ?? [];
    if (listed.length) return [];
    return decisions()
      .filter((d) => d.user === me.user_id && d.status_code !== 200)
      .map((d) => ({ ...d, proposal_id: s.response.proposal.proposal_id }));
  },
  audit: async () => (lastDecision === null ? [] : decisions()[lastDecision].audit),
  results: async () => (await fetch(`${import.meta.env.BASE_URL}replay/results.json`)).json(),
};
