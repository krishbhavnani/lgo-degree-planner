// Shared loaders for the JS tests: program files, and the built db.js run against a stub window.
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.join(__dirname, "..", "..");
const readJson = p => JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf8"));

// Every programs/*.json, keyed by file name (without .json).
function programFiles() {
  const dir = path.join(ROOT, "programs");
  return Object.fromEntries(fs.readdirSync(dir).filter(f => f.endsWith(".json"))
    .map(f => [f.slice(0, -5), readJson(path.join("programs", f))]));
}

// Course numbers that resolve: everything in db.js, plus old numbers from aliases.json.
function knownCourses() {
  const file = path.join(ROOT, "db.js");
  if (!fs.existsSync(file)) throw new Error("db.js not found: run `python3 scrape.py --from-archive` first");
  const window = {};
  vm.runInNewContext(fs.readFileSync(file, "utf8"), { window });
  const known = new Set(window.COURSE_DB.courses.map(c => c.number));
  for (const a of readJson("aliases.json").aliases) if (known.has(a.new)) known.add(a.old);
  return known;
}

module.exports = { ROOT, readJson, programFiles, knownCourses };
