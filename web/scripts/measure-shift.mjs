// Layout shift of the page's anchors (step tabs, question bar, the lot, detail top, wafer top)
// around common interactions, in px. Content that itself gets longer may push what is below it;
// the anchors above must not move.
//   node scripts/measure-shift.mjs <url> <width>
import { chromium } from "playwright";

const [, , url, w = "1280"] = process.argv;
const width = Number(w);
const ANCHORS = { steps: ".steps", qbar: ".qbar", lot: ".lot", detail: ".detail", wafer: ".wafer-stage" };
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width, height: width < 600 ? 812 : 800 } });
const tops = () =>
  page.evaluate((A) => {
    const o = {};
    for (const [k, s] of Object.entries(A)) {
      const el = document.querySelector(s);
      o[k] = el ? Math.round(el.getBoundingClientRect().top + window.scrollY) : null;
    }
    return o;
  }, ANCHORS);
const delta = (a, b) =>
  Object.fromEntries(Object.keys(ANCHORS).map((k) => [k, a[k] === null || b[k] === null ? "n/a" : b[k] - a[k]]));
const click = (sel, n = 0) => page.evaluate(([s, i]) => document.querySelectorAll(s)[i].click(), [sel, n]);
const out = [];
async function measure(label, action, wait = 500) {
  const a = await tops();
  await action();
  await page.waitForTimeout(wait);
  out.push([label, delta(a, await tops())]);
}

await page.goto(url + "#step=sop");
await page.waitForSelector(".detail");
await page.waitForTimeout(2600);
await measure("pick another identity", () => click(".slot", 0));
await measure("pick a third identity", () => click(".slot", 5));
await measure("step 2 (same question)", () => click(".step-tab", 1));
await measure("step 4 (another question)", () => click(".step-tab", 3), 2600);
await measure("step 5 (approval)", () => click(".step-tab", 4));
await measure("approve as the requester", () => click(".proposal-card button.approve"));
await measure("act as the administrator", () => click(".slot", 5));
await measure("step 6 (injection)", () => click(".step-tab", 5), 2600);
await measure("step 1 again", () => click(".step-tab", 0), 2600);
await measure("another question from the picker", async () => {
  await click(".pick-button");
  await page.waitForSelector(".pick-opt");
  await click(".pick-opt", 2);
}, 2600);
await measure("compare on", () => click(".compare-toggle"));
await measure("compare off", () => click(".compare-toggle"));
await click(".step-tab", 0);
await page.waitForTimeout(2600);
await measure("open citation drawer", async () => {
  await click(".detail button.chip-cite");
  await page.waitForSelector(".drawer");
});
await measure("close citation drawer", () => page.keyboard.press("Escape"));
await measure("language to English", () => click(".lang-seg button", 1));
await measure("language back", () => click(".lang-seg button", 0));
await measure("theme", () => click(".theme-switch"));
await browser.close();
const worst = Math.max(0, ...out.flatMap(([, d]) => Object.values(d).filter((v) => typeof v === "number").map(Math.abs)));
console.log(JSON.stringify({ width, worst, moved: out.filter(([, d]) => Object.values(d).some((v) => typeof v === "number" && v !== 0)) }));
