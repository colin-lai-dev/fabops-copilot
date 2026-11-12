// Drive the replay site through the guided tour and record it (handoff 011 D / 012).
//
//   node scripts/record-demo.mjs video <url> <outDir>   # ~3 min, 1920x1080 webm, subtitles on
//   node scripts/record-demo.mjs gif   <url> <outFile>  # ~30 s GIF for the README (960x540)
//
// <url> is the replay build, e.g. http://localhost:4174/fabops-copilot/ (vite preview --mode replay).
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import gifenc from "gifenc";
import { PNG } from "pngjs";

const { GIFEncoder, quantize, applyPalette } = gifenc;
const [, , kind, url, out] = process.argv;
if (!kind || !url || !out) {
  console.error("usage: record-demo.mjs video|gif <url> <out>");
  process.exit(2);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// the step card's "next scene" link is the only forward control (handoff 017 #7)
const tourNext = (page) => page.locator(".step-next").click();
async function send(page) {
  await page.getByRole("button", { name: "送出問題" }).click();
  await page.waitForFunction(() => !document.querySelector(".send")?.textContent.includes("查詢中"));
  await page.waitForSelector(".answer-text");
  await sleep(400);
}
async function stepAll(page, after) {
  const next = page.locator(".timeline-controls button").first();
  while (await next.isEnabled()) {
    await next.click();
    await after();
  }
}
const into = (page, sel) => page.locator(sel).first().scrollIntoViewIfNeeded();
const toTop = (page) =>
  page.evaluate(() => document.querySelector(".app-scroll")?.scrollTo({ top: 0, behavior: "smooth" }));

// The storyboard; `hold(ms)` is the pause after each action.
async function tour(page, hold) {
  // 1 SOP question
  await hold(9000);
  await send(page);
  await hold(6000);
  await page.locator(".chip-cite").first().click();
  await hold(11000);
  // 2 permission
  await tourNext(page);
  await hold(3500);
  await send(page);
  await hold(14000);
  // 3 one question, six identities
  await tourNext(page);
  await hold(4000);
  await into(page, ".six-grid");
  await hold(16000);
  await toTop(page);
  // 4 agent, step by step
  await tourNext(page);
  await hold(3000);
  await send(page);
  await hold(3000);
  await into(page, ".timeline");
  await stepAll(page, () => hold(2300));
  await page.locator(".step-head").first().click();
  await hold(7000);
  // 4 approval: the requester is refused, the admin approves
  await tourNext(page);
  await hold(2500);
  await toTop(page);
  await hold(3000);
  await page.locator(".proposal-card button.approve").click(); // the requester: refused
  await page.waitForSelector(".proposal-card .msg-bad");
  await hold(7000);
  await page.locator(".guide-switch").first().click(); // FX1 lead: not even listed
  await hold(7000);
  await page.locator(".guide-switch").first().click(); // administrator
  await hold(2500);
  await page.locator(".proposal-card button.approve").click();
  await page.waitForSelector(".ev-executed");
  await hold(11000);
  // 5 injection with the control
  await toTop(page);
  await tourNext(page);
  await hold(3000);
  await send(page);
  await hold(3000);
  await into(page, ".injection");
  await hold(5000);
  await page.getByRole("button", { name: "看對照組" }).click();
  await into(page, ".compare");
  await hold(18000);
  // 6 results
  await toTop(page);
  await tourNext(page);
  await hold(4000);
  for (const c of [0, 1, 2, 3]) {
    const chart = page.locator(".chart").nth(c);
    await chart.scrollIntoViewIfNeeded();
    await chart.locator(".bar-line").nth(1).hover();
    await hold(c < 2 ? 5000 : 7000);
  }
  await hold(6000);
}

async function open(viewport, extra = {}) {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport, colorScheme: "light", ...extra });
  const page = await context.newPage();
  await page.goto(`${url}?subs=1`);
  await page.waitForSelector(".badge-on");
  await sleep(1200);
  return { browser, context, page };
}

if (kind === "video") {
  fs.mkdirSync(out, { recursive: true });
  const t0 = Date.now();
  const size = { width: 1920, height: 1080 };
  const { browser, context, page } = await open(size, { recordVideo: { dir: out, size } });
  // larger text for a 1080p video: zoom the scrolling content, not the 100vh frame
  await page.addStyleTag({ content: ".app-scroll > * { zoom: 1.25; } .subtitles { font-size: 23px; } .subtitles .en { font-size: 17px; }" });
  await sleep(500);
  await tour(page, sleep);
  const video = page.video();
  await context.close();
  await browser.close();
  const target = path.join(out, "fabops-copilot-demo.webm");
  fs.renameSync(await video.path(), target);
  console.log(`video ${target} ${((Date.now() - t0) / 1000).toFixed(0)} s`);
} else if (kind === "gif") {
  // ~25 s at 2 fps: filter -> retrieve -> cite on the wafer, the cited passage, the operator
  // blocked, six identities side by side, agent steps, refused then approved, injection control.
  const { browser, page } = await open({ width: 1280, height: 720 }, { deviceScaleFactor: 1.5 });
  const gif = GIFEncoder();
  const W = 960;
  const H = 540;
  const frame = async (n = 1) => {
    for (let k = 0; k < n; k++) {
      const png = PNG.sync.read(await page.screenshot());
      const sw = png.width; // 1920: average 2x2 blocks down to 960x540
      const rgba = new Uint8Array(W * H * 4);
      for (let y = 0; y < H; y++)
        for (let x = 0; x < W; x++)
          for (let c = 0; c < 4; c++) {
            const a = (2 * y * sw + 2 * x) * 4 + c;
            const b = ((2 * y + 1) * sw + 2 * x) * 4 + c;
            rgba[(y * W + x) * 4 + c] =
              (png.data[a] + png.data[a + 4] + png.data[b] + png.data[b + 4]) >> 2;
          }
      const palette = quantize(rgba, 128);
      gif.writeFrame(applyPalette(rgba, palette), W, H, { palette, delay: 500 });
    }
  };
  await frame(3);
  await page.getByRole("button", { name: "送出問題" }).click();
  await page.waitForSelector(".answer-text");
  await frame(4); // the wafer sequence plays here
  await page.locator(".chip-cite").first().click();
  await page.waitForSelector(".drawer-title");
  await page.locator(".cite-mark").first().scrollIntoViewIfNeeded();
  await frame(5);
  await page.keyboard.press("Escape");
  await tourNext(page);
  await frame(1);
  await send(page);
  await frame(4);
  await tourNext(page); // six identities
  await page.waitForSelector(".six-col");
  await into(page, ".six-grid");
  await frame(8);
  await toTop(page);
  await tourNext(page);
  await send(page);
  await into(page, ".timeline");
  await stepAll(page, () => frame(1));
  await frame(1);
  // approval: three outcomes without leaving the step (handoff 018)
  await tourNext(page);
  await toTop(page);
  await page.waitForSelector(".proposal-card button.approve");
  await frame(2);
  await page.locator(".proposal-card button.approve").click(); // the requester: refused
  await page.waitForSelector(".proposal-card .msg-bad");
  await frame(3);
  await page.locator(".guide-switch").first().click(); // FX1 lead: not even listed
  await page.waitForSelector(".proposal-card.blind");
  await frame(3);
  await page.locator(".guide-switch").first().click(); // administrator: approves
  await page.locator(".proposal-card button.approve").click();
  await page.waitForSelector(".ev-executed");
  await frame(5);
  await toTop(page);
  await tourNext(page);
  await send(page);
  await page.getByRole("button", { name: "看對照組" }).click();
  await into(page, ".compare");
  await frame(10);
  await toTop(page);
  await tourNext(page);
  await frame(5);
  gif.finish();
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, gif.bytes());
  await browser.close();
  console.log(`gif ${out} ${(fs.statSync(out).size / 1e6).toFixed(1)} MB`);
} else {
  console.error(`unknown kind ${kind}`);
  process.exit(2);
}
