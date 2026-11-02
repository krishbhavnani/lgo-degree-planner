// Guard: degree rules stay out of app code. Every string literal and piece of template text in
// app/*.js is checked: none may contain a course number from the catalog or the program files, or
// be exactly a program or category id. (Requirement and list ids aren't checked: some are ordinary
// words the UI also uses, like "aags" for a Browse column.)
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { ROOT, programFiles, knownCourses } = require("./helpers.js");

const REGEX_AFTER = new Set(["return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
  "throw", "case", "do", "else", "yield", "await"]);

// String literals and template text in JS source, skipping comments and regex literals. Only
// strings are returned, so numbers in code (0.25, 864e5) are never flagged.
function strings(src) {
  const out = [], braces = []; // braces: open-brace depth inside each ${ ... } being read
  let i = 0, last = "", word = "";
  const readTemplate = j => {
    let s = "";
    while (j < src.length) {
      const d = src[j];
      if (d === "\\") { s += src[j + 1]; j += 2; continue; }
      if (d === "`") { out.push(s); return j + 1; }
      if (d === "$" && src[j + 1] === "{") { out.push(s); braces.push(0); return j + 2; }
      s += d; j++;
    }
    throw new Error("unterminated template literal");
  };
  const template = j => { const depth = braces.length; i = readTemplate(j); last = braces.length > depth ? "op" : "str"; };
  while (i < src.length) {
    const c = src[i];
    if (c === "/" && src[i + 1] === "/") { const e = src.indexOf("\n", i); i = e < 0 ? src.length : e; continue; }
    if (c === "/" && src[i + 1] === "*") { i = src.indexOf("*/", i + 2) + 2; continue; }
    if (c === '"' || c === "'") {
      let j = i + 1, s = "";
      while (src[j] !== c) { if (src[j] === "\\") { s += src[j + 1]; j += 2; } else s += src[j++]; }
      out.push(s); i = j + 1; last = "str"; continue;
    }
    if (c === "`") { template(i + 1); continue; }
    const regexOk = !(last === "id" && !REGEX_AFTER.has(word)) && !["num", ")", "]", "str"].includes(last);
    if (c === "/" && regexOk) {
      let j = i + 1, inClass = false;
      while (src[j] !== "/" || inClass) {
        if (src[j] === "\\") j++; else if (src[j] === "[") inClass = true; else if (src[j] === "]") inClass = false;
        j++;
      }
      j++;
      while (/[a-z]/i.test(src[j] || "")) j++;
      i = j; last = "re"; continue;
    }
    if (c === "{") { if (braces.length) braces[braces.length - 1]++; last = "op"; i++; continue; }
    if (c === "}") {
      if (braces.length && braces[braces.length - 1] === 0) { braces.pop(); template(i + 1); continue; }
      if (braces.length) braces[braces.length - 1]--;
      last = "}"; i++; continue;
    }
    if (/[A-Za-z_$]/.test(c)) { let j = i; while (/[\w$]/.test(src[j] || "")) j++; word = src.slice(i, j); last = "id"; i = j; continue; }
    if (/[0-9]/.test(c)) { let j = i; while (/[\w.]/.test(src[j] || "")) j++; last = "num"; i = j; continue; }
    if (/\s/.test(c)) { i++; continue; }
    last = c === ")" ? ")" : c === "]" ? "]" : "op"; i++;
  }
  return out;
}

test("the string scanner reads strings, templates and regexes correctly", () => {
  const src = [
    "const a = 'one', b = \"t\\\"wo\"; // 'not this'",
    "/* \"nor this\" */ const r = /[\"']/g, d = x / 2 / y, n = 0.25;",
    "const t = `head ${a ? `in ${b}` : 'alt'} tail`;",
    "if (s.match(/a\\/b/)) return /c/.test(s);",
  ].join("\n");
  assert.deepEqual(strings(src), ["one", 't"wo', "head ", "in ", "", "alt", " tail"]);
});

const appDir = path.join(ROOT, "app");
const appStrings = fs.readdirSync(appDir).filter(f => f.endsWith(".js"))
  .flatMap(f => strings(fs.readFileSync(path.join(appDir, f), "utf8")).map(s => [f, s]));

test("app code has string literals to check", () => assert.ok(appStrings.length > 300));

test("no course numbers in app code", () => {
  const programs = Object.values(programFiles());
  const courses = knownCourses();
  for (const p of programs) {
    Object.keys(p.not_in_catalog || {}).forEach(n => courses.add(n));
    Object.values(p.lists || {}).filter(Array.isArray).flat().forEach(n => courses.add(n));
    (p.base_plan || []).forEach(b => courses.add(b.course));
    (p.bundles || []).forEach(b => courses.add(b.lead));
  }
  const hits = appStrings.filter(([, s]) => s.split(/[^A-Za-z0-9.]+/).some(t => courses.has(t.replace(/\.$/, ""))));
  assert.deepEqual(hits, []);
});

test("no program or category ids in app code", () => {
  const programs = Object.values(programFiles());
  const ids = new Set(programs.flatMap(p => [p.id, ...(p.categories || []).filter(c => c.id).map(c => c.id)]));
  assert.deepEqual(appStrings.filter(([, s]) => ids.has(s)), []);
});
