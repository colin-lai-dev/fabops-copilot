import React from "react";

// Clearance as a four-step meter plus a filled chip with its name: public fills one step,
// restricted all four. One colour per level everywhere on the page (tokens --clr-N-bg /
// --clr-N-ink, both themes AA); the ramp avoids the state colours, and the name and the steps
// mean colour is never the only cue.

export const CLEARANCE = ["public", "internal", "confidential", "restricted"];

export default function Clearance({ level }) {
  return (
    <span className={`clr clr-${level}`}>
      <span className="clr-pips" aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <i key={i} className={i <= level ? "on" : ""} />
        ))}
      </span>
      <span className="clr-chip">{CLEARANCE[level]}</span>
    </span>
  );
}
