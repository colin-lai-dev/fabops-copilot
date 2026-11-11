// Screenshots of the replay site at a given width, walking the guided tour (for review).
//   node scripts/review-shots.mjs <url> <outDir> <width>
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const [, , url, out, w = "1280"] = process.argv;
const width = Number(w);
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width, height: width < 600 ? 812 : 800 },
  deviceScaleFactor: 1,
});
const shot = (name, full = true) =>
  page.screenshot({ path: path.join(out, `${width}-${name}.png`), fullPage: full });
const next = () => page.getByRole("button", { name: "下一步", exact: true }).first().click();
const send = async () => {
  await page.getByRole("button", { name: "送出問題" }).click();
  await page.waitForSelector(".answer-text");
  await page.waitForTimeout(900);
};

await page.goto(url);
await page.waitForSelector(".badge");
await page.waitForTimeout(800);
await shot("0-start");
await send(); // 1 SOP
await shot("1-sop");
await next(); // 2 permission
await page.waitForTimeout(900);
await send();
await shot("2-permission");
await next(); // 3 agent
await page.waitForTimeout(500);
await send();
await page.getByRole("button", { name: "全部展開" }).click();
await page.locator(".step-head").first().click();
await shot("3-agent");
await next(); // 4 approval
await page.waitForTimeout(600);
await page.locator(".proposal-card button.approve").click();
await page.waitForSelector(".msg-bad");
await shot("4a-denied");
await page.getByRole("button", { name: /系統管理員/ }).click();
await page.waitForTimeout(700);
await page.locator(".proposal-card button.approve").click();
await page.waitForSelector(".ev-executed");
await shot("4b-approved");
await next(); // 5 injection
await page.waitForTimeout(600);
await send();
await page.getByRole("button", { name: "看對照組" }).click();
await shot("5-injection");
await next(); // 6 results
await page.waitForTimeout(500);
await page.locator(".bar-line").nth(1).hover();
await shot("6-results");
await browser.close();
console.log("done", width);
