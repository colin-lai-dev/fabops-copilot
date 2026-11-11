import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies the API (python -m fabops.api.app, port 8000).
// `--mode replay` (web/.env.replay) builds the static demo for GitHub Pages under /fabops-copilot/.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === "replay" ? "/fabops-copilot/" : "/",
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
}));
