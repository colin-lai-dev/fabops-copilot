import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { execSync } from "node:child_process";

// Site version for the footer: VITE_SITE_VERSION, else the nearest site-vN tag, else "dev".
function siteVersion() {
  if (process.env.VITE_SITE_VERSION) return process.env.VITE_SITE_VERSION;
  try {
    return execSync('git describe --tags --match "site-v*" --abbrev=0', { stdio: ["ignore", "pipe", "ignore"] })
      .toString()
      .trim();
  } catch {
    return "dev";
  }
}

// Design-lab build (handoff 022): VITE_LAB=1 VITE_BASE=/fabops-copilot/lab/ serves the experiment
// under /lab/ next to the released site, marked noindex.
const LAB = process.env.VITE_LAB === "1";
const noindex = {
  name: "lab-noindex",
  transformIndexHtml: (html) =>
    LAB ? html.replace("<head>", '<head><meta name="robots" content="noindex" />') : html,
};

// Dev server proxies the API (python -m fabops.api.app, port 8000).
// `--mode replay` (web/.env.replay) builds the static demo for GitHub Pages under /fabops-copilot/.
export default defineConfig(({ mode }) => ({
  plugins: [react(), noindex],
  define: { __SITE_VERSION__: JSON.stringify(siteVersion()), __LAB__: JSON.stringify(LAB) },
  base: process.env.VITE_BASE || (mode === "replay" ? "/fabops-copilot/" : "/"),
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
}));
