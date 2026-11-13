// Drive the replay site through its seven steps and record it.
//
//   node scripts/record-demo.mjs video <url> <outDir>   # ~3 min, 1920x1080 webm, subtitles on
//   node scripts/record-demo.mjs gif   <url> <outFile>  # ~30 s GIF for the README (960x540)
//
// <url> is the replay build, e.g. http://localhost:4173/fabops-copilot/ (vite preview --mode replay).
// The site is "the lot": six wafers (one per identity) for the same question; picking a wafer
// keeps the question and shows that identity's own recorded run.
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
const SEQ = 2600; // the filter -> retrieve -> cite sequence

const step = (page, n) => page.locator(".step-tab").nth(n - 1).click();
const slot = (page, n) => page.locator(".slot").nth(n - 1).click();
const into = (page, sel) => page.locator(sel).first().scrollIntoViewIfNeeded();
const toTop = (page) =>
  page.evaluate(() => (document.querySelector(".app-subs .app-scroll") || window).scrollTo({ top: 0 }));

// The storyboard. `hold(ms)` pauses (video) or captures frames (gif); `brief` trims the holds.
async function story(page, hold) {
  // 1 SOP: six wafers, six results, no click needed
  await hold(SEQ + 2500);
  await page.locator(".detail button.chip-cite").first().click(); // the cited passage
  await page.waitForSelector(".drawer-title");
  await page.locator(".cite-mark").first().scrollIntoViewIfNeeded();
  await hold(4000);
  await page.keyboard.press("Escape");
  // 2 the operator: same question, 1 of 192 documents
  await step(page, 2);
  await hold(3500);
  // 3 six answers under their wafers
  await step(page, 3);
  await hold(1000);
  await into(page, ".cmp");
  await hold(5000);
  await toTop(page);
  // 4 the agent's run as one thread
  await step(page, 4);
  await hold(SEQ);
  await into(page, ".node-proposal");
  await hold(4500);
  // 5 approval: the requester is refused, the FX1 lead is not listed, the administrator approves
  await toTop(page);
  await step(page, 5);
  await hold(1500);
  await into(page, ".approve-panel");
  await page.locator(".proposal-card button.approve").click();
  await page.waitForSelector(".proposal-card .msg-bad");
  await hold(3000);
  await page.locator(".guide-links button").first().click(); // act as the FX1 process lead
  await page.waitForSelector(".proposal-card.blind");
  await hold(3000);
  await page.locator(".guide-links button").first().click(); // act as the administrator
  await page.locator(".proposal-card button.approve").click();
  await page.waitForSelector(".ev-executed");
  await into(page, ".audit");
  await hold(4500);
  // 6 injection, next to the control without the permission filter
  await toTop(page);
  await step(page, 6);
  await hold(SEQ);
  await into(page, ".compare");
  await hold(5000);
  // 7 results
  await toTop(page);
  await step(page, 7);
  await hold(4500);
}

async function open(viewport, extra = {}) {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport, colorScheme: "light", ...extra });
  const page = await context.newPage();
  await page.goto(`${url}?subs=1`);
  await page.waitForSelector(".slot");
  return { browser, context, page };
}

if (kind === "video") {
  fs.mkdirSync(out, { recursive: true });
  const t0 = Date.now();
  const size = { width: 1920, height: 1080 };
  const { browser, context, page } = await open(size, { recordVideo: { dir: out, size } });
  // larger text for a 1080p video: zoom the scrolling content, not the 100vh frame
  await page.addStyleTag({ content: ".app-scroll > * { zoom: 1.25; } .subtitles { font-size: 23px; } .subtitles .en { font-size: 17px; }" });
  await story(page, (ms) => sleep(ms * 3.3)); // the video lingers so a first-time viewer can read the subtitles; the GIF does not
  const video = page.video();
  await context.close();
  await browser.close();
  const target = path.join(out, "fabops-copilot-demo.webm");
  fs.renameSync(await video.path(), target);
  console.log(`video ${target} ${((Date.now() - t0) / 1000).toFixed(0)} s`);
} else if (kind === "gif") {
  // 2 frames per second, 1280x720 at 1.5x averaged down to 960x540
  const { browser, page } = await open({ width: 1280, height: 720 }, { deviceScaleFactor: 1.5 });
  const gif = GIFEncoder();
  const W = 960;
  const H = 540;
  let frames = 0;
  const frame = async () => {
    const png = PNG.sync.read(await page.screenshot());
    const sw = png.width;
    const rgba = new Uint8Array(W * H * 4);
    for (let y = 0; y < H; y++)
      for (let x = 0; x < W; x++)
        for (let c = 0; c < 4; c++) {
          const a = (2 * y * sw + 2 * x) * 4 + c;
          const b = ((2 * y + 1) * sw + 2 * x) * 4 + c;
          rgba[(y * W + x) * 4 + c] = (png.data[a] + png.data[a + 4] + png.data[b] + png.data[b + 4]) >> 2;
        }
    const palette = quantize(rgba, 128);
    gif.writeFrame(applyPalette(rgba, palette), W, H, { palette, delay: 500 });
    frames++;
  };
  // capture in real time, one frame every 500 ms of the hold
  const hold = async (ms) => {
    const end = Date.now() + ms * 0.55;
    do {
      const t = Date.now();
      await frame();
      await sleep(Math.max(0, 500 - (Date.now() - t)));
    } while (Date.now() < end);
  };
  await story(page, hold);
  gif.finish();
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, gif.bytes());
  await browser.close();
  console.log(`gif ${out} ${(fs.statSync(out).size / 1e6).toFixed(1)} MB, ${frames} frames, ${frames / 2} s`);
} else {
  console.error(`unknown kind ${kind}`);
  process.exit(2);
}
