// The caption band under the step tabs, per width: its height for every step and outside the
// tour, in both languages (must be one value per width: zero shift), the stage's top (likewise),
// and the blank space under the visible text (handoff 028: at most one line, 24 px).
//   node scripts/measure-caption.mjs <url>
import { chromium } from "playwright";
const b = await chromium.launch();
for (const w of [320, 375, 414, 1024, 1280]) {
  const p = await b.newPage({ viewport: { width: w, height: 812 } });
  const rows = [];
  for (const lang of ["zh", "en"]) for (const h of ["sop", "permission", "six", "agent", "approval", "injection", "results", "FREE"]) {
    await p.goto("about:blank");
    await p.goto(process.argv[2] + (h === "FREE" ? `#q=comp&as=admin_all&lang=${lang}` : `#step=${h}&lang=${lang}`));
    await p.waitForTimeout(1300);
    rows.push(await p.evaluate(() => {
      const c = document.querySelector(".caption"), cr = c.getBoundingClientRect();
      const vis = [...c.querySelectorAll(".caption-stack > p:not(.caption-off)")][0];
      const span = vis.querySelector(".bi > span:not(.bi-ghost)") || vis; // the visible text itself
      const btn = [...c.querySelectorAll("button")].find((x) => x.offsetParent);
      const textBottom = vis.classList.contains("caption-me") ? Math.max(...[...vis.children].map((k) => k.getBoundingClientRect().bottom)) : span.getBoundingClientRect().bottom;
      const stackBottom = c.querySelector(".caption-stack").getBoundingClientRect().bottom;
      return { cap: Math.round(cr.height), gap: Math.round(stackBottom - textBottom), btn: btn ? 1 : 0, q: Math.round(document.querySelector(".stage").getBoundingClientRect().top + scrollY) };
    }));
  }
  const caps = new Set(rows.map((r) => r.cap)), qs = new Set(rows.map((r) => r.q));
  console.log(w, "caption heights", [...caps], "stage tops", [...qs], "blank under text (px):", rows.map((r) => r.gap).join(","), "max", Math.max(...rows.map((r) => r.gap)));
}
await b.close();
