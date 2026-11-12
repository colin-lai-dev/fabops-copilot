// Self-check of the design-lab replay site: the guided steps, every recorded question as every
// identity, the six-answer comparison, the citation drawer, the approval outcomes and English.
// Saves screenshots and fails on page errors, horizontal overflow, or a permission mismatch.
//   node scripts/review-lab.mjs <url> <outDir> <width> [light|dark]
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const [, , url, out, w = "1280", scheme = "light"] = process.argv;
const width = Number(w);
fs.mkdirSync(out, { recursive: true });
const data = JSON.parse(fs.readFileSync(new URL("../public/replay/scenes.json", import.meta.url), "utf8"));
const visibleIds = (u) => new Set(data.visible_by_user[u].map((i) => data.docs[i].doc_id));
const users = data.users.map((u) => u.user_id);

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width, height: width < 600 ? 812 : 800 },
  deviceScaleFactor: 1,
  colorScheme: scheme,
});
const problems = [];
page.on("pageerror", (e) => problems.push(`pageerror: ${e}`));
page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text()}`));

const shot = (name) => page.screenshot({ path: path.join(out, `${scheme}-${width}-${name}.png`), fullPage: true });
const click = (sel, n = 0) => page.evaluate(([s, i]) => document.querySelectorAll(s)[i].click(), [sel, n]);
async function open(hash) {
  await page.goto("about:blank");
  await page.goto(url + hash);
  await page.waitForSelector(".step-tab");
  await page.waitForTimeout(2900); // data + the 2.5 s sequence
}
async function check(label, user) {
  const sw = await page.evaluate(() => document.documentElement.scrollWidth);
  if (sw > width + 1) problems.push(`${label}: horizontal overflow ${sw}px`);
  if (!user) return;
  const locked = await page.locator(".wafer-stage .die-locked").count();
  const expect = data.docs.length - data.visible_by_user[user].length;
  if (locked !== expect) problems.push(`${label}: ${locked} locked dies, expected ${expect}`);
  const seen = visibleIds(user);
  for (const c of await page.locator(".detail .chip-cite").allInnerTexts())
    if (!seen.has(c.trim()) && !c.startsWith("INJ-")) problems.push(`${label}: cites ${c}, not visible to ${user}`);
}

// 1. the guided steps
await open("");
const steps = await page.locator(".step-tab").count();
for (let i = 0; i < steps; i++) {
  await click(".step-tab", i);
  await page.waitForTimeout(i === 3 ? 2900 : 900);
  await shot(`step-${i + 1}`);
  await check(`step ${i + 1}`, null);
}

// 2. approval: requester refused, FX1 lead not listed, administrator approves; audit log stays
await open("#step=approval");
await click(".proposal-card button.approve");
await page.waitForSelector(".proposal-card .msg-bad");
await shot("approval-a-requester");
await click(".slot", users.indexOf("lead_fx1_multi"));
await page.waitForTimeout(500);
if (!(await page.locator(".proposal-card.blind").count())) problems.push("lead: recorded 403 not shown");
if (await page.locator(".proposal-card button.approve").count()) problems.push("lead: can see the FX2 proposal");
if (await page.locator(".audit").count()) problems.push("lead: an audit log is on screen");
if (!(await page.locator(".step-on").innerText()).includes("5")) problems.push("lead: left the approval step");
await shot("approval-b-lead");
await click(".slot", users.indexOf("admin_all"));
await page.waitForTimeout(500);
await click(".proposal-card button.approve");
await page.waitForSelector(".ev-executed");
await page.waitForTimeout(1500);
if (!(await page.locator(".ev-executed").count())) problems.push("approval: audit log gone after 1.5 s");
await shot("approval-c-approved");
if ((await page.locator(".audit li").count()) < 5) problems.push("approval: audit log gone after a full-page screenshot");
if (!(await page.locator(".node-proposal .state-executed").count())) problems.push("approval: proposal not shown as executed");

// 3. every recorded question as every identity; the drawer for the first citation
for (const g of data.groups) {
  await open(`#q=${g.id}`);
  for (let i = 0; i < users.length; i++) {
    const u = users[i];
    const recorded = g.scenes.length
      ? data.scenes.some((s) => g.scenes.includes(s.id) && s.user === u)
      : data.scenes.some((s) => !s.id.startsWith("six-") && s.user === u && s.question === g.question && s.mode === g.mode);
    await click(".slot", i);
    await page.waitForTimeout(160);
    const pressed = await page.locator(".slot").nth(i).getAttribute("aria-pressed");
    if (pressed !== "true") problems.push(`${g.id}/${u}: slot not selected`);
    const has = (await page.locator(".detail .answer-text").count()) > 0;
    if (has !== recorded) problems.push(`${g.id}/${u}: answer shown=${has}, recorded=${recorded}`);
    await check(`${g.id}/${u}`, u);
    const chip = page.locator(".detail button.chip-cite").first();
    if (await chip.count()) {
      await chip.evaluate((e) => e.click());
      await page.waitForSelector(".drawer-title, .drawer .msg-bad, .drawer .fine");
      if (!(await page.locator(".drawer-title").count())) problems.push(`${g.id}/${u}: cited document did not open`);
      if (i === 1 && g.id === "epd") await shot("drawer");
      await page.keyboard.press("Escape");
    }
  }
  await shot(`q-${g.id}`);
  // six answers side by side
  await click(".compare-toggle");
  await page.waitForTimeout(200);
  const cols = await page.locator(".col .cmp, .col .cmp-none").count();
  if (cols !== 6) problems.push(`compare ${g.id}: ${cols} columns`);
  await shot(`compare-${g.id}`);
  await check(`compare ${g.id}`, null);
}

// 4. older deep links and English
for (const h of ["#scene=comp-lead", "#six=comp", "#step=sop&lang=en", "#step=approval&as=admin_all&lang=en", "#step=results&lang=en"]) {
  await open(h);
  await shot(`link-${h.slice(1).replace(/[=&]/g, "-")}`);
  await check(`link ${h}`, null);
}
await open("#scene=comp-lead");
if ((await page.locator(".slot[aria-pressed=true] .slot-id").innerText()) !== "lead_fx1_multi") problems.push("#scene= did not select its asker");
await open("#six=comp");
if ((await page.locator(".col .cmp").count()) !== 6) problems.push("#six= did not open the comparison");

await browser.close();
console.log(JSON.stringify({ width, scheme, scenes: data.scenes.length, groups: data.groups.length, problems }, null, 1));
process.exit(problems.length ? 1 : 0);
