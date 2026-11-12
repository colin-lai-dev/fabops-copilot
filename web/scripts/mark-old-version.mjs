// Marks a built copy of an older site version (used for /v8/ by the pages workflow): adds
// noindex and one line at the top that says it is the previous version and links to the
// current one. Only the built index.html is touched; the old version's source is not.
//   node scripts/mark-old-version.mjs <path to dist/index.html>
import fs from "node:fs";

const file = process.argv[2];
let html = fs.readFileSync(file, "utf8");
const bar =
  '<div style="font:13px/1.7 system-ui,sans-serif;padding:3px 16px;background:#131922;color:#fff;text-align:center">' +
  '舊版（v8）· <a href="../" style="color:#f2b33d">前往新版</a>' +
  '<span lang="en" style="opacity:.75"> — Previous version (v8) · <a href="../" style="color:#f2b33d">go to the current site</a></span>' +
  "</div>";
if (!html.includes('name="robots"')) html = html.replace("<head>", '<head>\n    <meta name="robots" content="noindex" />');
if (!html.includes("舊版（v8）")) html = html.replace('<div id="root">', `${bar}\n    <div id="root">`);
fs.writeFileSync(file, html);
console.log("marked", file);
