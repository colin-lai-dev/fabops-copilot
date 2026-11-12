// Layout shift of the page's anchors (identity row, step rail, step card top, ask card top,
// wafer panel top) around common interactions (handoff 021). Prints px deltas per interaction.
//   node scripts/measure-shift.mjs <url> <width>
import { chromium } from "playwright";

const [, , url, w = "1280"] = process.argv;
const width = Number(w);
const ANCHORS = {
  badges: ".badges",
  rail: ".rail ol",
  step: ".step-card",
  ask: ".panel.ask",
  wafer: ".evidence .ev-block:has(.wafer)",
};
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width, height: width < 600 ? 812 : 860 } });
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
const click = (sel) => page.evaluate((s) => document.querySelector(s).click(), sel); // no auto-scroll
const settle = () => page.waitForTimeout(700);
const out = [];
async function measure(label, action) {
  const a = await tops();
  await action();
  await settle();
  out.push([label, delta(a, await tops())]);
}

await page.goto(url + "#step=sop");
await page.waitForSelector(".panel.ask");
await page.waitForTimeout(1500);
await measure("click a badge (leave the tour)", () => click(".badge:not(.badge-on)"));
await measure("click step 1 (back into the tour)", () => click(".rail-item"));
await measure("click step 2", () => page.evaluate(() => document.querySelectorAll(".rail-item")[1].click()));
await measure("ask (answer appears)", async () => {
  await click("button.send");
  await page.waitForSelector(".answer-text");
});
await measure("open six identities", async () => {
  await click("button.six-open");
  await page.waitForSelector(".six-col");
});
await measure("close six identities", () => click(".six-close"));
await page.goto("about:blank");
await page.goto(url + "#step=sop");
await page.waitForSelector("button.send");
await click("button.send");
await page.waitForSelector(".chip-cite");
await settle();
await measure("open citation drawer", async () => {
  await click(".answer .chip-cite");
  await page.waitForSelector(".drawer");
});
await measure("close citation drawer", () => page.keyboard.press("Escape"));
await measure("toggle agent-steps panel", () => click(".evidence details:nth-of-type(2) > summary"));
await browser.close();
console.log(JSON.stringify({ width, shifts: out }, null, 1));
