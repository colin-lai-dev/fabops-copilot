// Replay backend for the static demo site (VITE_DEMO_MODE=replay).
// Same interface as api.js, but every answer, trace, proposal, decision and audit entry comes
// from web/public/replay/scenes.json, recorded from the real system (scripts/record_replay.py).
// Nothing is generated here, and only recorded questions can be asked.

let data = null;
let me = null;
let current = null; // scene id of the last answer
const decided = {}; // proposal_id -> index of the last applied decision step

async function load() {
  if (!data) {
    const res = await fetch(`${import.meta.env.BASE_URL}replay/scenes.json`);
    data = await res.json();
  }
  return data;
}

function triageScene() {
  return data.scenes.find((s) => s.approval_steps?.length);
}

function stepsOf(scene) {
  return scene.approval_steps.filter((s) => s.kind === "decision");
}

export function setToken() {}

export const replay = {
  meta: async () => {
    const d = await load();
    return { recorded_at: d.recorded_at, system: d.system };
  },
  users: async () => (await load()).users,
  login: async (userId) => {
    const d = await load();
    me = d.users.find((u) => u.user_id === userId);
    return { token: "", user: me };
  },
  scenes: async () => (await load()).scenes,
  results: async () => (await fetch(`${import.meta.env.BASE_URL}replay/results.json`)).json(),
  sceneById: (id) => data?.scenes.find((s) => s.id === id),
  currentScene: () => (current ? data.scenes.find((s) => s.id === current) : null),
  ask: async (sceneId) => {
    const s = (await load()).scenes.find((x) => x.id === sceneId);
    if (!s || s.user !== me?.user_id) throw new Error("這個問題不是由目前身分錄製的");
    current = s.id;
    return s.response;
  },
  pending: async () => {
    const s = triageScene();
    if (!s || !me) return [];
    const pid = s.response.proposal?.proposal_id;
    const last = decided[pid] ?? -1;
    const executed = last >= 0 && stepsOf(s)[last].status_code === 200;
    const asked = Object.prototype.hasOwnProperty.call(decided, pid) || current === s.id;
    if (!asked || executed) return [];
    const listed = s.approval_steps.find((x) => x.kind === "pending").by_user[me.user_id];
    return listed ?? [];
  },
  decide: async (pid, approved) => {
    const s = triageScene();
    const steps = stepsOf(s);
    const i = steps.findIndex((d) => d.user === me.user_id && d.approved === approved);
    if (i < 0) throw new Error("這個決定沒有錄製（回放版只提供錄製過的操作）");
    decided[pid] = i;
    const d = steps[i];
    if (d.status_code !== 200) throw new Error(d.detail);
    return d.run;
  },
  audit: async (pid) => {
    const s = triageScene();
    const i = decided[pid];
    return i === undefined ? [] : stepsOf(s)[i].audit;
  },
};
