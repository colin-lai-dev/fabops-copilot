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

// Dev server proxies the API (python -m fabops.api.app, port 8000).
// `--mode replay` (web/.env.replay) builds the static demo for GitHub Pages under /fabops-copilot/.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  define: { __SITE_VERSION__: JSON.stringify(siteVersion()) },
  base: mode === "replay" ? "/fabops-copilot/" : "/",
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
}));
