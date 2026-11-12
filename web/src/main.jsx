import React from "react";
import { createRoot } from "react-dom/client";
// Self-hosted fonts (no CDN): Barlow for Latin, Noto Sans TC for Chinese, JetBrains Mono for codes.
import "@fontsource/barlow/400.css";
import "@fontsource/barlow/500.css";
import "@fontsource/barlow/600.css";
import "@fontsource/noto-sans-tc/400.css";
import "@fontsource/noto-sans-tc/500.css";
import "@fontsource/noto-sans-tc/700.css";
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
