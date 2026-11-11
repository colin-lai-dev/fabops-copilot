// Drive the replay site through docs/demo-script.md and record it (handoff 011 D).
//
//   node scripts/record-demo.mjs video <url> <outDir>   # ~3 min, 1920x1080 webm, subtitles on
//   node scripts/record-demo.mjs gif   <url> <outFile>  # ~30 s GIF for the README (960x540)
//   node scripts/record-demo.mjs shots <url> <outDir>   # checkpoint screenshots for review
//
// <url> is the replay build, e.g. http://127.0.0.1:4173/fabops-copilot/ (vite preview --mode replay).
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import gifenc from "gifenc";
import { PNG } from "pngjs";

const { GIFEncoder, quantize, applyPalette } = gifenc;

const [, , kind, url, out] = process.argv;
if (!kind || !url || !out) {
  console.error("usage: record-demo.mjs video|gif|shots <url> <out>");
  process.exit(2);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function as(page, user) {
  await page.selectOption(".userpicker select", user);
  await sleep(700);
}

async function ask(page, sceneId) {
  await page.selectOption(".scene-select", sceneId);
  await sleep(600);
  await page.click("form button");
  await page.waitForFunction(() => document.querySelector("form button")?.textContent === "送出");
  await page.waitForSelector(".answer");
  await sleep(500);
}

async function show(page, selector) {
  const el = page.locator(selector).first();
  if (await el.count()) await el.scrollIntoViewIfNeeded();
}

async function top(page) {
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
}

// One walk through the storyboard; `hold(ms)` lets the GIF pass shorten every pause.
async function walk(page, hold, snap = async () => {}) {
  await hold(9000); // 0:00 intro caption
  await snap("00-intro");
  // 0:20 SOP question, current version cited
  await as(page, "eng_fx1_etch");
  await ask(page, "sop-latest");
  await snap("01-sop-latest");
  await hold(20000);
  // 0:50 same question, low privilege
  await as(page, "op_fx1_etch");
  await ask(page, "low-privilege");
  await snap("02-low-privilege");
  await hold(13000);
  // 1:05 role spoofing and an injected report
  await as(page, "eng_fx1_etch");
  await ask(page, "role-spoofing");
  await show(page, ".trace");
  await snap("03-role-spoofing");
  await hold(12000);
  await top(page);
  await ask(page, "injection-blocked");
  await show(page, ".injected");
  await snap("04-injection");
  await hold(13000);
  // 1:20 RAG vs agent on a question that needs MES data, then triage with approval
  await top(page);
  await as(page, "mgr_fx2_all");
  await ask(page, "cross-doc-rag");
  await snap("05-cross-doc-rag");
  await hold(9000);
  await top(page);
  await ask(page, "cross-doc-agent");
  await show(page, ".trace");
  await snap("06-cross-doc-agent");
  await hold(12000);
  await top(page);
  await ask(page, "triage-approval");
  await hold(7000);
  await show(page, ".trace");
  await hold(8000);
  await show(page, ".proposal");
  await snap("07-triage-pending");
  await hold(9000);
  await top(page);
  await as(page, "admin_all");
  await show(page, ".proposal");
  await hold(4000);
  await page.locator(".proposal button", { hasText: "核准" }).first().click();
  await page.waitForSelector(".audit");
  await show(page, ".audit");
  await snap("08-approved-audit");
  await hold(12000);
  // 2:10 results
  await top(page);
  await page.click(".results-toggle");
  await page.waitForSelector("[data-testid=results]");
  await snap("09-results");
  await hold(24000);
}

async function launch(viewport, recordDir) {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 1,
    colorScheme: "light",
    ...(recordDir ? { recordVideo: { dir: recordDir, size: viewport } } : {}),
  });
  const page = await context.newPage();
  await page.goto(`${url}?subs=1`);
  if (viewport.width >= 1920) await page.addStyleTag({ content: "html { zoom: 1.25; }" });
  await page.waitForSelector(".userpicker select option[value=eng_fx1_etch]", { state: "attached" });
  return { browser, context, page };
}

if (kind === "video") {
  fs.mkdirSync(out, { recursive: true });
  const t0 = Date.now();
  const { browser, context, page } = await launch({ width: 1920, height: 1080 }, out);
  await walk(page, sleep);
  const video = page.video();
  await context.close();
  await browser.close();
  const file = await video.path();
  const target = path.join(out, "fabops-copilot-demo.webm");
  fs.renameSync(file, target);
  console.log(`video ${target} ${((Date.now() - t0) / 1000).toFixed(0)} s`);
} else if (kind === "shots") {
  fs.mkdirSync(out, { recursive: true });
  const { browser, page } = await launch({ width: 1920, height: 1080 });
  await walk(page, (ms) => sleep(Math.min(ms, 300)), (name) =>
    page.screenshot({ path: path.join(out, `${name}.png`) }),
  );
  await browser.close();
  console.log(`shots in ${out}`);
} else if (kind === "gif") {
  // ~30 s: SOP answer, operator refused, agent triage, approval. 2 frames per second, 960x540.
  const viewport = { width: 960, height: 540 };
  const { browser, page } = await launch(viewport);
  const gif = GIFEncoder();
  const frame = async (n = 1) => {
    for (let i = 0; i < n; i++) {
      const png = PNG.sync.read(await page.screenshot({ clip: { x: 0, y: 0, ...viewport } }));
      const rgba = new Uint8Array(png.data);
      const palette = quantize(rgba, 128);
      gif.writeFrame(applyPalette(rgba, palette), viewport.width, viewport.height, {
        palette,
        delay: 500,
      });
    }
  };
  await frame(4);
  await as(page, "eng_fx1_etch");
  await ask(page, "sop-latest");
  await frame(12);
  await as(page, "op_fx1_etch");
  await ask(page, "low-privilege");
  await frame(10);
  await as(page, "mgr_fx2_all");
  await ask(page, "triage-approval");
  await frame(6);
  await show(page, ".trace");
  await frame(6);
  await show(page, ".proposal");
  await frame(6);
  await top(page);
  await as(page, "admin_all");
  await show(page, ".proposal");
  await frame(2);
  await page.locator(".proposal button", { hasText: "核准" }).first().click();
  await page.waitForSelector(".audit");
  await show(page, ".audit");
  await frame(14);
  gif.finish();
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, gif.bytes());
  await browser.close();
  console.log(`gif ${out} ${(fs.statSync(out).size / 1e6).toFixed(1)} MB`);
} else {
  console.error(`unknown kind ${kind}`);
  process.exit(2);
}
