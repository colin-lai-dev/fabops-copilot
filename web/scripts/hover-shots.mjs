// Hover-state screenshots (handoff 021): identity card, theme button and an open picker with a
// hovered option, desktop light and dark; plus a touch check that a tap leaves no hover style.
//   node scripts/hover-shots.mjs <url> <outDir>
import { chromium, devices } from "playwright";
import fs from "node:fs";
import path from "node:path";

const [, , url, out] = process.argv;
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
for (const scheme of ["light", "dark"]) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, colorScheme: scheme });
  await page.goto(url + "#as=mgr_fx2_all");
  await page.waitForSelector(".pick-button");
  await page.waitForTimeout(800);
  await page.locator(".pick-button").click();
  await page.waitForSelector(".pick-opt");
  await page.locator(".pick-opt").nth(2).hover();
  await page.waitForTimeout(200);
  await page.screenshot({ path: path.join(out, `hover-${scheme}-picker.png`), clip: { x: 0, y: 0, width: 1280, height: 720 } });
  await page.keyboard.press("Escape");
  await page.locator(".badge").nth(1).hover();
  await page.waitForTimeout(200);
  await page.screenshot({ path: path.join(out, `hover-${scheme}-badge.png`), clip: { x: 0, y: 40, width: 1280, height: 210 } });
  await page.locator(".theme-switch").hover();
  await page.waitForTimeout(200);
  await page.screenshot({ path: path.join(out, `hover-${scheme}-tools.png`), clip: { x: 900, y: 50, width: 380, height: 80 } });
  await page.close();
}
// touch: after tapping the theme button, it must not keep a hover background
const ctx = await browser.newContext({ ...devices["iPhone 13"] });
const page = await ctx.newPage();
await page.goto(url + "#step=sop");
await page.waitForSelector(".theme-switch");
const hoverNone = await page.evaluate(() => matchMedia("(hover: none)").matches);
const before = await page.locator(".theme-switch").evaluate((e) => getComputedStyle(e).backgroundColor);
await page.locator(".theme-switch").tap();
await page.waitForTimeout(400);
await page.locator(".theme-switch").tap(); // back to the first theme
await page.waitForTimeout(400);
const after = await page.locator(".theme-switch").evaluate((e) => getComputedStyle(e).backgroundColor);
console.log(JSON.stringify({ touchHoverNone: hoverNone, stickyHover: before !== after, before, after }));
await browser.close();
