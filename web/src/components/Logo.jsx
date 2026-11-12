import React from "react";

// FabOps Copilot mark: a wafer with its orientation notch and a few lit dies, the same picture as
// the permission wafer map. Colours come from theme tokens (outline = ink, dies, lit = amber), so
// one drawing serves light and dark; public/favicon.svg is the same shape. Original artwork.

// 12 dies of a 4 x 4 grid (corners left out so every die sits inside the wafer edge)
const DIES = [
  [1, 0], [2, 0],
  [0, 1], [1, 1], [2, 1], [3, 1],
  [0, 2], [1, 2], [2, 2], [3, 2],
  [1, 3], [2, 3],
]; // prettier-ignore
const LIT = new Set(["2,0", "1,1", "3,2"]);

export default function Logo({ size = 36 }) {
  return (
    <svg className="brand-logo" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <path
        d="M13.6 29.29 A13.5 13.5 0 1 1 18.4 29.29 A2.4 2.4 0 0 0 13.6 29.29 Z"
        className="logo-wafer"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      {DIES.map(([x, y]) => (
        <rect
          key={`${x},${y}`}
          x={5.5 + x * 5.6}
          y={5.5 + y * 5.6}
          width="4.2"
          height="4.2"
          rx="0.8"
          className={LIT.has(`${x},${y}`) ? "logo-die-lit" : "logo-die"}
        />
      ))}
    </svg>
  );
}
