// Replay backend for the static demo site (VITE_DEMO_MODE=replay). Same interface as api.js.
// Every answer, trace, proposal, decision and audit entry comes from
// public/replay/scenes.json, recorded from the real system (scripts/record_replay.py).
// Nothing is generated here, and only recorded questions can be asked.

let data = null;
let me = null;
let askedTriage = false;
let lastDecision = null; // index into the triage scene's decision steps

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
  ask: async ({ sceneId }) => {
    const s = (await load()).scenes.find((x) => x.id === sceneId);
    if (!s || s.user !== me?.user_id) throw new Error("這個問題不是由目前身分錄製的");
    if (s.approval_steps?.length) askedTriage = true;
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
