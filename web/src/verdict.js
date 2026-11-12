// What one identity's recorded run amounts to, as a key + tone (+ an optional one-line reason).
// RAG: answered / declined / cut off by the 512-token cap. Agent: `refused` means "no action
// recommended", so the verdict is the proposal, incomplete, or no action.
export function verdict(slot) {
  const run = slot?.run;
  if (!run) return { key: "v.none", tone: "mute" };
  if (slot.cutOff) return { key: "six.cutOff", tone: "warn", why: "six.cutOffWhy" };
  if (run.mode === "rag") {
    if (!run.refused) return { key: "six.answered", tone: "good" };
    return slot.targetVisible
      ? { key: "six.refused", tone: "bad", why: "six.refusedVisible" }
      : { key: "six.refused", tone: "bad" };
  }
  if (run.proposal) return { key: "six.proposed", tone: "violet" };
  if (run.status === "incomplete") return { key: "six.incomplete", tone: "bad", why: "six.incompleteWhy" };
  return run.refused ? { key: "six.noAction", tone: "bad" } : { key: "six.answered", tone: "good" };
}
