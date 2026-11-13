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
// Each card of the lot: name, id and verdict have a size and lie wholly inside the card and the
// lot (not clipped); the name is not truncated, does not touch the wafer, and is what the browser
// hits at its centre (nothing covers it). Each card is scrolled into view first (phones scroll
// the lot sideways).
async function lotCheck(label) {
  const n = await page.locator(".slot").count();
  for (let i = 0; i < n; i++) {
    await page.locator(".slot").nth(i).evaluate((s) => s.scrollIntoView({ block: "center", inline: "nearest" }));
    const r = await page.locator(".slot").nth(i).evaluate((s) => {
      const out = [];
      const box = (e) => e.getBoundingClientRect();
      const inside = (a, b) => a.left >= b.left - 0.5 && a.right <= b.right + 0.5 && a.top >= b.top - 0.5 && a.bottom <= b.bottom + 0.5;
      const card = box(s);
      const lot = box(s.closest(".lot"));
      for (const sel of [".slot-name", ".slot-id", ".slot-verdict"]) {
        const e = s.querySelector(sel);
        const b = e && box(e);
        if (!b || b.width < 1 || b.height < 1) out.push(`${sel} has no size`);
        else if (!inside(b, card) || b.top < lot.top - 0.5 || b.bottom > lot.bottom + 0.5) out.push(`${sel} clipped`);
      }
      const name = s.querySelector(".slot-name");
      const nb = box(name);
      const m = box(s.querySelector(".mini"));
      if (nb.left < m.right && nb.right > m.left && nb.top < m.bottom && nb.bottom > m.top) out.push("name over the wafer");
      if (name.scrollWidth > name.clientWidth + 1) out.push("name truncated");
      const hit = document.elementFromPoint(nb.left + nb.width / 2, nb.top + nb.height / 2);
      if (!hit || !(hit === name || name.contains(hit))) out.push(`name covered by ${hit ? hit.className || hit.tagName : "nothing"}`);
      return out;
    });
    if (r.length) problems.push(`${label}: wafer ${i + 1}: ${r.join("; ")}`);
  }
  // one row of cards: name, id, clearance row and verdict each at the same height (handoff 030)
  const tops = await page.$$eval(".slot", (ss) =>
    Object.fromEntries(
      [".slot-name", ".slot-id", ".slot-meta", ".slot-verdict"].map((sel) => [
        sel,
        ss.map((s) => s.querySelector(sel).getBoundingClientRect().top - s.getBoundingClientRect().top),
      ]),
    ),
  );
  for (const [sel, t] of Object.entries(tops))
    if (Math.max(...t) - Math.min(...t) > 1) problems.push(`${label}: ${sel} not aligned across the row (${t.map(Math.round).join(", ")})`);
  await page.evaluate(() => window.scrollTo(0, 0));
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
// the audit hint (handoff 025): hidden while the audit log is on screen; when shown it sits in the
// page flow and overlaps no other element's box; once the log is scrolled into view it goes away
const hintState = () =>
  page.evaluate(() => {
    const h = document.querySelector(".audit-hint");
    const a = document.querySelector(".audit");
    if (!h || !a) return { missing: true };
    const on = !h.classList.contains("audit-hint-off");
    const ar = a.getBoundingClientRect();
    const auditOn = ar.top < innerHeight - 24 && ar.bottom > 24;
    const hr = h.getBoundingClientRect();
    const hit = (r) => r.left < hr.right && r.right > hr.left && r.top < hr.bottom && r.bottom > hr.top;
    const covers = on && getComputedStyle(h).position !== "static" ? "not in flow" : null;
    const overlap = on
      ? [...document.querySelectorAll("p, li, b, span, a, button")]
          .filter((e) => e !== h && !h.contains(e) && !e.contains(h) && e.offsetParent && hit(e.getBoundingClientRect()))
          .map((e) => e.className || e.tagName)
      : [];
    return { on, auditOn, covers, overlap };
  });
{
  const s1 = await hintState();
  if (s1.missing) problems.push("approval: no audit hint slot");
  else {
    if (s1.on && s1.auditOn) problems.push("approval: hint shown while the audit log is on screen");
    if (!s1.on && !s1.auditOn) problems.push("approval: audit log off screen but no hint");
    if (s1.covers) problems.push(`approval: hint ${s1.covers}`);
    if (s1.overlap.length) problems.push(`approval: hint overlaps ${s1.overlap.join(", ")}`);
    if (s1.on) {
      await page.locator(".audit").scrollIntoViewIfNeeded();
      await page.waitForTimeout(300);
      if ((await hintState()).on) problems.push("approval: hint still shown after the audit log came into view");
      await page.evaluate(() => window.scrollTo(0, 0));
    }
  }
  console.log(`audit hint at decision: ${JSON.stringify(s1)}`);
}
await shot("approval-c-approved");
if ((await page.locator(".audit li").count()) < 5) problems.push("approval: audit log gone after a full-page screenshot");
if (!(await page.locator(".node-proposal .state-executed").count())) problems.push("approval: proposal not shown as executed");

// every wafer in the lot (handoff 029, replacing 028's overlap-only check), both languages
await lotCheck("approval");
await open("#step=approval&lang=en");
await lotCheck("approval en");

// the clearance legend: its four chips on one row, inside the column (handoff 027)
{
  const rows = await page.$$eval(".clr-legend ul", (us) =>
    us.map((u) => ({ rows: new Set([...u.children].map((c) => Math.round(c.getBoundingClientRect().top))).size, over: u.scrollWidth > u.clientWidth + 1 })),
  );
  if (!rows.length) problems.push("legend: missing");
  if (rows.some((r) => r.rows !== 1 || r.over)) problems.push(`legend: chips not on one row ${JSON.stringify(rows)}`);
  if (await page.locator(".step-on").count() && !(await page.locator(".step-on").innerText()).includes("7")) {
    if (!(await page.locator(".caption-next .step-n").count())) problems.push("next-scene button missing");
  }
}

// the question picker (handoff 031): scrolled to its middle, every visible group label is what the
// browser hits across its width (no option text shows through); moving with the keys never leaves
// the active option under a stuck label
{
  await page.locator(".pick-button").click();
  await page.waitForSelector(".pick-opt");
  await page.locator(".pick-list").evaluate((l) => l.scrollIntoView({ block: "nearest" }));
  const covered = async () =>
    page.$$eval(".pick-group", (gs) =>
      gs.flatMap((g) => {
        const r = g.getBoundingClientRect();
        const l = g.closest(".pick-list").getBoundingClientRect();
        const y = Math.max(r.top, l.top) + 4;
        // the test point must be inside both the list's visible part and the viewport
        if (r.bottom <= l.top + 1 || y >= Math.min(l.bottom, innerHeight) - 1 || y < 0) return [];
        return [0.05, 0.3, 0.6, 0.95]
          .map((fx) => document.elementFromPoint(r.left + r.width * fx, y))
          .filter((e) => !(e && (e === g || g.contains(e))))
          .map((e) => `${g.textContent}: ${e ? e.className || e.tagName : "nothing"}`);
      }),
    );
  for (const f of [0.35, 0.5, 0.75]) {
    await page.$eval(".pick-list", (l, x) => (l.scrollTop = (l.scrollHeight - l.clientHeight) * x), f);
    await page.waitForTimeout(100);
    const bad = await covered();
    if (bad.length) problems.push(`picker at ${f}: label covered by ${[...new Set(bad)].join(", ")}`);
  }
  const hidden = [];
  const n = await page.locator(".pick-opt").count();
  for (const key of [...Array(n).fill("ArrowDown"), ...Array(n).fill("ArrowUp")]) {
    await page.keyboard.press(key);
    const r = await page.evaluate(() => {
      const a = document.querySelector(".pick-active");
      const l = document.querySelector(".pick-list").getBoundingClientRect();
      const ar = a.getBoundingClientRect();
      const stuck = [...document.querySelectorAll(".pick-group")]
        .map((g) => g.getBoundingClientRect())
        .filter((g) => g.top <= l.top + 1 && g.bottom > l.top);
      const under = stuck.some((g) => ar.top < g.bottom - 1);
      return under || ar.bottom > l.bottom + 1 ? a.textContent.slice(0, 20) : null;
    });
    if (r) hidden.push(r);
  }
  if (hidden.length) problems.push(`picker keys: active option hidden (${hidden.length}×, e.g. ${hidden[0]})`);
  await page.keyboard.press("Escape");
}

// text selection (handoff 031): controls are not selectable, content is
{
  const us = (sel) =>
    page.$$eval(sel, (es) => es.map((e) => getComputedStyle(e).userSelect || getComputedStyle(e).webkitUserSelect));
  const controls = [".step-tab", ".slot", ".die", ".pick-button", ".theme-switch", ".lang-seg button", ".replay", ".compare-toggle", ".clr-legend ul", ".wafer-legend"];
  const content = [".answer-text", ".pick-button .pick-q", ".foot p", ".caption-stack p:not(.caption-off)"];
  await open("#step=agent");
  for (const sel of [...controls, ".caption-next", ".node button, .timeline button", "summary"]) {
    const v = await us(sel);
    if (!v.length && !sel.includes(",") && sel !== "summary") problems.push(`select: no ${sel} on screen`);
    if (v.some((x) => x !== "none")) problems.push(`select: ${sel} is selectable (${[...new Set(v)].join("/")})`);
  }
  for (const sel of content) {
    const v = await us(sel);
    if (!v.length) problems.push(`select: no ${sel} on screen`);
    if (v.some((x) => x === "none")) problems.push(`select: ${sel} cannot be selected`);
  }
  await page.locator(".pick-button").click();
  await page.waitForSelector(".pick-opt");
  if ((await us(".pick-opt")).some((x) => x !== "none")) problems.push("select: picker options are selectable");
  await page.keyboard.press("Escape");
  await open("#step=approval&as=admin_all");
  await click(".proposal-card button.approve");
  await page.waitForSelector(".audit");
  if ((await us(".audit li")).some((x) => x === "none")) problems.push("select: audit log cannot be selected");
  if ((await us(".approvals button")).some((x) => x !== "none")) problems.push("select: approval buttons are selectable");
  await click(".detail button.chip-cite");
  const d = await page.waitForSelector(".drawer-body", { timeout: 3000 }).catch(() => null);
  if (d && (await us(".drawer-body")).some((x) => x === "none")) problems.push("select: drawer text cannot be selected");
  await page.keyboard.press("Escape");
}

// footer links (handoff 032): hovered, a link's box (its hover background) touches no visible text
// outside it, and hovering moves no footer text
{
  await open("#step=sop");
  await page.locator(".foot").scrollIntoViewIfNeeded();
  const textRects = () =>
    page.$eval(".foot", (foot) => {
      const out = [];
      const w = document.createTreeWalker(foot, NodeFilter.SHOW_TEXT);
      for (let t = w.nextNode(); t; t = w.nextNode()) {
        if (!t.textContent.trim() || t.parentElement.closest(".sr-only")) continue;
        const rg = document.createRange();
        rg.selectNodeContents(t);
        for (const q of rg.getClientRects()) out.push(`${t.textContent.trim()}@${Math.round(q.left)},${Math.round(q.top)}`);
      }
      return out.join("|");
    });
  const before = await textRects();
  const n = await page.locator(".foot a").count();
  for (let i = 0; i < n; i++) {
    const link = page.locator(".foot a").nth(i);
    await link.hover();
    await page.waitForTimeout(200);
    const hits = await link.evaluate((a) => {
      const ar = a.getBoundingClientRect();
      const w = document.createTreeWalker(a.closest(".foot"), NodeFilter.SHOW_TEXT);
      const out = [];
      for (let t = w.nextNode(); t; t = w.nextNode()) {
        if (a.contains(t) || !t.textContent.trim() || t.parentElement.closest(".sr-only")) continue;
        const rg = document.createRange();
        rg.selectNodeContents(t);
        for (const q of rg.getClientRects())
          if (q.left < ar.right && q.right > ar.left && q.top < ar.bottom && q.bottom > ar.top) out.push(t.textContent.trim());
      }
      return out;
    });
    if (hits.length) problems.push(`footer: hovering link ${i + 1} covers "${hits.join('", "')}"`);
    if ((await textRects()) !== before) problems.push(`footer: hovering link ${i + 1} moved footer text`);
  }
  await page.mouse.move(0, 0);
}

// outside the guided steps the caption shows the current identity, not an empty band
await open("#q=comp&as=admin_all");
if (await page.locator(".step-on").count()) problems.push("free question: a guided step is selected");
if (!(await page.locator(".caption .caption-me .clr-chip").count())) problems.push("free question: no identity in the caption");

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
  await lotCheck(`link ${h}`); // English names, and the comparison layout (#six=)
}
await open("#scene=comp-lead");
if ((await page.locator(".slot[aria-pressed=true] .slot-id").innerText()) !== "lead_fx1_multi") problems.push("#scene= did not select its asker");
await open("#six=comp");
if ((await page.locator(".col .cmp").count()) !== 6) problems.push("#six= did not open the comparison");

await browser.close();
console.log(JSON.stringify({ width, scheme, scenes: data.scenes.length, groups: data.groups.length, problems }, null, 1));
process.exit(problems.length ? 1 : 0);
