// Live backend client (FastAPI). The session token is the only identity sent; the server
// derives the user from it (ADR-0001). Same interface as replay.js.

let token = "";

async function call(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

// Six real requests for the six-identity view, each with that user's own session token
// (the page's own session is untouched).
async function sixWay(question) {
  const users = await call("GET", "/api/users");
  const columns = await Promise.all(
    users.map(async (user) => {
      const s = await call("POST", "/api/session", { user_id: user.user_id });
      const auth = { Authorization: `Bearer ${s.token}`, "Content-Type": "application/json" };
      const [run, docs] = await Promise.all([
        fetch("/api/ask", { method: "POST", headers: auth, body: JSON.stringify({ question, mode: "rag" }) }).then((r) => r.json()),
        fetch("/api/docs", { headers: auth }).then((r) => r.json()),
      ]);
      return { user, run, visible: docs.filter((d) => d.visible).length, total: docs.length, targetVisible: null };
    }),
  );
  return { question, columns };
}

export const live = {
  sixWay,
  replay: false,
  users: () => call("GET", "/api/users"),
  login: async (userId) => {
    const s = await call("POST", "/api/session", { user_id: userId });
    token = s.token; // switching identity re-issues the token
    return s.user;
  },
  docs: () => call("GET", "/api/docs"),
  doc: (docId) => call("GET", `/api/docs/${encodeURIComponent(docId)}`).catch(() => null),
  scenes: async () => [],
  ask: ({ question, mode }) => call("POST", "/api/ask", { question, mode }),
  pending: () => call("GET", "/api/proposals"),
  decide: (id, approved) => call("POST", `/api/proposals/${id}/decision`, { approved, note: "" }),
  audit: (id) => call("GET", `/api/audit/${id}`),
  results: async () => (await fetch(`${import.meta.env.BASE_URL}replay/results.json`)).json(),
};
