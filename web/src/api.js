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

export const live = {
  replay: false,
  users: () => call("GET", "/api/users"),
  login: async (userId) => {
    const s = await call("POST", "/api/session", { user_id: userId });
    token = s.token; // switching identity re-issues the token
    return s.user;
  },
  docs: () => call("GET", "/api/docs"),
  scenes: async () => [],
  ask: ({ question, mode }) => call("POST", "/api/ask", { question, mode }),
  pending: () => call("GET", "/api/proposals"),
  decide: (id, approved) => call("POST", `/api/proposals/${id}/decision`, { approved, note: "" }),
  audit: (id) => call("GET", `/api/audit/${id}`),
  results: async () => (await fetch(`${import.meta.env.BASE_URL}replay/results.json`)).json(),
};
