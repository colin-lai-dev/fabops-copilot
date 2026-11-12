import React from "react";
import { createRoot } from "react-dom/client";
// Self-hosted Latin faces (no CDN): Barlow for text, Barlow Condensed for numerals and slot
// numbers, JetBrains Mono for ids. Chinese uses the system face (PingFang TC / Microsoft
// JhengHei): bundling a CJK web font cost 425 KB of render-blocking CSS.
import "@fontsource/barlow/400.css";
import "@fontsource/barlow/500.css";
import "@fontsource/barlow/600.css";
import "@fontsource/barlow-condensed/500.css";
import "@fontsource/barlow-condensed/600.css";
import "@fontsource/jetbrains-mono/400.css";
import App from "./App.jsx";
import "./style.css";

// Last input type, for focus styling (style.css): pointer focus shows no ring, keyboard does.
const root = document.documentElement;
root.dataset.input = "pointer";
window.addEventListener("pointerdown", () => (root.dataset.input = "pointer"), true);
window.addEventListener(
  "keydown",
  (e) => {
    if (!e.metaKey && !e.ctrlKey && !e.altKey) root.dataset.input = "keyboard";
  },
  true,
);

createRoot(document.getElementById("root")).render(<App />);
