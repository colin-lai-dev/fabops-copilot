// Thin client for the FastAPI backend. The session token is the only identity sent;
// the server derives the user from it (ADR-0001).

let token = "";

export function setToken(t) {
  token = t;
}

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

export const api = {
  users: () => call("GET", "/api/users"),
  login: (userId) => call("POST", "/api/session", { user_id: userId }),
  ask: (question, mode) => call("POST", "/api/ask", { question, mode }),
  pending: () => call("GET", "/api/proposals"),
  decide: (id, approved, note) =>
    call("POST", `/api/proposals/${id}/decision`, { approved, note }),
  audit: (id) => call("GET", `/api/audit/${id}`),
};
