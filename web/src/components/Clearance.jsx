import React from "react";

// Clearance as a four-step meter plus its name: public fills one step, restricted all four.
// One ink colour (no hue per level), so colour on the page is left to mean retrieval and
// verdicts; the level name is always written.

export const CLEARANCE = ["public", "internal", "confidential", "restricted"];

export default function Clearance({ level }) {
  return (
    <span className={`clr clr-${level}`}>
      <span className="clr-pips" aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <i key={i} className={i <= level ? "on" : ""} />
        ))}
      </span>
      {CLEARANCE[level]}
    </span>
  );
}
