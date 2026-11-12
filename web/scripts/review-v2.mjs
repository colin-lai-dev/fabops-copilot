// Self-check of the replay site (handoff 015 step 0.3): walks the tour, every recorded scene,
// every six-identity group, the citation drawer and English mode; saves screenshots and fails on
// page errors, horizontal overflow, or a permission mismatch on screen.
//   node scripts/review-v2.mjs <url> <outDir> <width> [light|dark]
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const [, , url, out, w = "1280", scheme = "light"] = process.argv;
const width = Number(w);
fs.mkdirSync(out, { recursive: true });
const data = JSON.parse(fs.readFileSync(new URL("../public/replay/scenes.json", import.meta.url), "utf8"));
const visibleIds = (u) => new Set(data.visible_by_user[u].map((i) => data.docs[i].doc_id));

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width, height: width < 600 ? 812 : 860 },
  deviceScaleFactor: 1,
  colorScheme: scheme,
});
const problems = [];
page.on("pageerror", (e) => problems.push(`pageerror: ${e}`));
page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text()}`));

const shot = (name) => page.screenshot({ path: path.join(out, `${scheme}-${width}-${name}.png`), fullPage: true });
async function check(label, user) {
  const sw = await page.evaluate(() => document.documentElement.scrollWidth);
  if (sw > width + 1) problems.push(`${label}: horizontal overflow ${sw}px`);
  if (!user) return;
  const locked = await page.locator(".die-locked").count();
  const expect = data.docs.length - data.visible_by_user[user].length;
  if (locked !== expect) problems.push(`${label}: ${locked} locked dies, expected ${expect}`);
  const seen = visibleIds(user);
  for (const c of await page.locator(".answer .chip-cite").allInnerTexts())
    if (!seen.has(c.trim()) && !c.startsWith("INJ-")) problems.push(`${label}: cites ${c}, not visible to ${user}`);
}
async function open(hash) {
  await page.goto("about:blank");
  await page.goto(url + hash);
  await page.waitForSelector(".badge");
  await page.waitForTimeout(1900); // answer + the 1.4 s wafer sequence
}

// 1. guided tour
await open("");
const steps = await page.locator(".rail-item").count();
for (let i = 0; i < steps; i++) {
  await page.locator(".rail-item").nth(i).click();
  await page.waitForTimeout(700);
  const send = page.locator("button.send");
  if (await send.count()) {
    await send.click();
    await page.waitForSelector(".answer-text");
    await page.waitForTimeout(1600);
  }
  await shot(`tour-${i + 1}`);
  await check(`tour ${i + 1}`, null);
  if (await page.locator(".proposal-card button.approve").count()) {
    await page.locator(".proposal-card button.approve").click(); // requester: refused
    await page.waitForSelector(".msg-bad");
    await shot(`tour-${i + 1}-a-denied`);
    await page.getByRole("button", { name: /lead_fx1_multi/ }).click(); // cannot see the target
    await page.waitForTimeout(600);
    if (!(await page.locator(".proposal-card.blind").count())) problems.push("lead: blind attempt not shown");
    if (await page.locator(".proposal-card button.approve").count()) problems.push("lead: can see the FX2 proposal");
    if (await page.locator(".audit").count()) problems.push("lead: an audit log is on screen");
    await shot(`tour-${i + 1}-b-lead`);
    await page.getByRole("button", { name: /admin_all/ }).click();
    await page.waitForTimeout(600);
    await page.locator(".proposal-card button.approve").click();
    await page.waitForSelector(".ev-executed");
    await page.waitForTimeout(1500); // the audit log must stay (handoff 019)
    if (!(await page.locator(".ev-executed").count())) problems.push("approval: audit log gone after 1.5 s");
    await shot(`tour-${i + 1}-c-approved`);
    if ((await page.locator(".audit li").count()) < 5) problems.push("approval: audit log gone after a full-page screenshot");
  }
}

// 2. every recorded scene, as its own asker (deep link), plus the drawer for the first citation
for (const s of data.scenes) {
  await open(`#scene=${s.id}`);
  await shot(`scene-${s.id}`);
  await check(`scene ${s.id}`, s.user);
  const chip = page.locator(".answer .chip-cite").first();
  if (await chip.count()) {
    await chip.click();
    await page.waitForSelector(".drawer-title, .drawer .msg-bad");
    if (await page.locator(".drawer .msg-bad").count()) problems.push(`scene ${s.id}: cited doc shows no access`);
    if (s.id === "comp-lead" || s.id === "sop-latest") await shot(`scene-${s.id}-drawer`);
    await page.keyboard.press("Escape");
  }
}

// 3. six identities
for (const g of data.groups) {
  await open(`#six=${g.id}`);
  const cols = await page.locator(".six-col").count();
  const expect = g.unavailable ? 0 : 6; // an unavailable group says why instead of showing columns
  if (cols !== expect) problems.push(`six ${g.id}: ${cols} columns, expected ${expect}`);
  if (g.unavailable && !(await page.locator(".six-unavailable").count())) problems.push(`six ${g.id}: no reason shown`);
  await shot(`six-${g.id}`);
  await check(`six ${g.id}`, null);
}

// 4. English
for (const h of ["#step=sop&lang=en", "#step=six&lang=en", "#scene=triage-approval&as=admin_all&lang=en", "#step=results&lang=en"]) {
  await open(h);
  await shot(`en-${h.split("&")[0].slice(1).replace("=", "-")}`);
  await check(`en ${h}`, null);
}

await browser.close();
console.log(JSON.stringify({ width, scheme, scenes: data.scenes.length, groups: data.groups.length, problems }, null, 1));
process.exit(problems.length ? 1 : 0);
