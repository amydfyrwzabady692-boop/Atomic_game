/* تست تطابق JS/Python: هر core.js باید روی لاگ‌های ورودی ثابت همان نتیجه‌ای را بدهد که
   شبیه‌ساز پایتون داده (fixtures/parity/<game>.json).  اجرا:  node arcade/jstests/parity.js */
"use strict";
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const staticDir = path.join(root, "static", "arcade");
const fixtureDir = path.join(root, "fixtures", "parity");
const { simulate } = require(path.join(staticDir, "common", "sim.js"));

let failed = 0;
let total = 0;
const only = process.argv.slice(2);

for (const file of fs.readdirSync(fixtureDir).sort()) {
  if (!file.endsWith(".json")) continue;
  const key = path.basename(file, ".json");
  if (only.length && !only.includes(key)) continue;
  const core = require(path.join(staticDir, key, "core.js"));
  const assets = {};
  for (const name of core.assets || []) {
    assets[name] = JSON.parse(fs.readFileSync(path.join(staticDir, key, name), "utf8"));
  }
  const cases = JSON.parse(fs.readFileSync(path.join(fixtureDir, file), "utf8"));
  let ok = 0;
  cases.forEach((c, i) => {
    total++;
    const config = Object.assign({ assets }, c.options || {});
    const got = simulate(core, c.seed, c.inputs, c.duration_ms, config);
    const want = c.expected;
    const same = ["score", "level", "duration_ms", "over", "cause"].every((k) => got[k] === want[k]);
    if (same) ok++;
    else {
      failed++;
      console.error(`MISMATCH ${key}[${i}] (${c.kind}) want=${JSON.stringify(want)} got=${JSON.stringify(got)}`);
    }
  });
  console.log(`${key}: ${ok}/${cases.length}`);
}

if (!total) {
  console.error("no fixtures found");
  process.exit(1);
}
console.log(failed ? `FAILED: ${failed}/${total}` : `OK: ${total} cases`);
process.exit(failed ? 1 : 0);
