import React from "react";

// Clearance level as a filled chip. One colour per level everywhere on the page, cool to warm
// from public to restricted (tokens --clr-N-bg / --clr-N-ink in style.css, both themes AA); the
// level name is always written, so colour is never the only cue.

export const CLEARANCE = ["public", "internal", "confidential", "restricted"];

export default function Clearance({ level }) {
  return <span className={`clr clr-${level}`}>{CLEARANCE[level]}</span>;
}
