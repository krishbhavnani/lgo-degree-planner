// Golden tests: the engine, reading programs/*.json, must reproduce what the app showed before the
// rules moved out of code (tests/js/golden/, captured from the live app on 2026-11-02).
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Engine = require("../../app/engine.js");

const ROOT = path.join(__dirname, "..", "..");
const GOLDEN = path.join(__dirname, "golden");
const readJson = p => JSON.parse(fs.readFileSync(p, "utf8"));
const program = Engine.resolve(readJson(path.join(ROOT, "programs/lgo.json")), readJson(path.join(ROOT, "programs/eecs.json")));
const frozen = readJson(path.join(GOLDEN, "courses.json")).courses;
const info = n => { const c = frozen[n] || {}; return { aags: c.aags, design: c.design_approved, department: c.department }; };
const START_YEAR = 2026;

// The fields the app shows, in the shape the fixtures recorded them.
const shown = r => ({ id: r.id, n: r.value, courses: r.courses, target: r.target, met: r.met,
  info: r.counted && r.counted.length ? ["Counted: " + r.counted.join(", ")] : [], notes: r.notes });
const summaryText = res => `${res.scheduled} courses scheduled` + res.summary.map(s => ` · ${s.label} ${s.value}/${s.target}u`).join("");

const goldens = fs.readdirSync(GOLDEN).filter(f => /^[a-z]\d*_\w+\.json$/.test(f));

test("there are golden plans", () => assert.ok(goldens.length >= 9));

for (const file of goldens) {
  const g = readJson(path.join(GOLDEN, file));
  test(`golden ${file}: ${g.description}`, () => {
    const res = Engine.evaluate(program, g.plan, info, g.targets);
    assert.deepEqual(res.requirements.map(shown), g.expected.requirements);
    assert.equal(summaryText(res), g.expected.summary);
    for (const t of g.expected.terms) {
      const got = res.terms[t.term] || { units: 0, over: false };
      assert.deepEqual({ term: t.term, units: got.units, over: got.over }, t);
    }
  });
}

test("the base plan from lgo.json is today's default plan, item for item", () => {
  const golden = readJson(path.join(GOLDEN, "a_base_plan.json"));
  assert.deepEqual(Engine.basePlan(program, START_YEAR), golden.plan);
});

test("term labels follow the start year", () => {
  assert.deepEqual(Engine.termLabels(program, 2026),
    ["Summer 2026", "Fall 2026", "IAP 2027", "Spring 2027", "Summer 2027", "Fall 2027", "IAP 2028", "Spring 2028"]);
  assert.equal(Engine.termLabels(program, 2027)[0], "Summer 2027");
});

test("every course gets the same default category as before", () => {
  const rows = readJson(path.join(GOLDEN, "classify.json")).courses;
  const wrong = [];
  for (const [number, department, expected] of rows) {
    const got = Engine.classify(program, number, n => n === number ? { department } : {});
    // Designations don't affect default categories, so the department alone reproduces them.
    if ((got[0] || null) !== expected) wrong.push(`${number}: ${got[0] || "none"}, expected ${expected || "none"}`);
  }
  assert.deepEqual(wrong, []);
  assert.ok(rows.length > 700);
});

test("targets the user didn't change come from the program", () => {
  const res = Engine.evaluate(program, [], info, {});
  const byId = Object.fromEntries(res.requirements.map(r => [r.id, r.target]));
  assert.equal(byId.mba_total, 156);
  assert.equal(byId.python, 1);
  assert.equal(Engine.evaluate(program, [], info, { mba_total: 150 }).summary[0].target, 150);
});
