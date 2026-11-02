// v1 -> v2 migration: a migrated plan must show what it showed before.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Engine = require("../../app/engine.js");
const State = require("../../app/state.js");
const { ROOT, readJson } = require("./helpers.js");

const program = Engine.resolve(readJson("programs/lgo.json"), readJson("programs/eecs.json"));
const frozen = readJson("tests/js/golden/courses.json").courses;
const ctx = { program, course: n => frozen[n] || null };
const info = n => { const c = frozen[n] || {}; return { aags: c.aags, design: c.design_approved, department: c.department }; };
const clone = x => JSON.parse(JSON.stringify(x));
const GOLDEN = path.join(ROOT, "tests/js/golden");
const goldens = fs.readdirSync(GOLDEN).filter(f => /^[a-z]\d*_\w+\.json$/.test(f)).map(f => [f, readJson(path.join("tests/js/golden", f))]);

const shown = r => ({ id: r.id, n: r.value, courses: r.courses, target: r.target, met: r.met,
  info: r.counted && r.counted.length ? ["Counted: " + r.counted.join(", ")] : [], notes: r.notes });
const evaluate = state => Engine.evaluate(program, State.toItems(ctx, state), info, state.targets);
// v1 requirement settings as older builds saved them: whole requirement copies.
const v1Reqs = targets => program.requirements.map(r => ({ key: r.id, group: r.group, name: r.label,
  target: targets[r.id] ?? Engine.defaultTarget(r), tags: r.pool }));

for (const [file, g] of goldens) {
  test(`migrated ${file} shows the same requirements as before`, () => {
    const { state, notes } = State.migrateV1(ctx, { plan: clone(g.plan), reqs: Object.keys(g.targets).length ? v1Reqs(g.targets) : null });
    const got = evaluate(state).requirements.map(shown);
    // The synthetic c-plans have no base courses at all; real v1 plans always kept the two
    // required ones (they couldn't be removed), so reconcile puts those back.
    const added = State.reconcile(ctx, clone(state));
    if (file.startsWith("c")) assert.deepEqual(added.map(a => a.split(" ")[1]), ["15.769", "15.792"]);
    else assert.deepEqual(added, []);
    if (file.startsWith("c6_")) {
      // 6.5130 had two categories (MBA Elective + Eng Elective); now it counts toward the first only.
      assert.equal(notes.length, 1);
      assert.match(notes[0], /^6\.5130 counted toward MBA Elective and Eng Elective/);
      const eng = got.find(r => r.id === "eng_elec"), want = g.expected.requirements.find(r => r.id === "eng_elec");
      assert.deepEqual([eng.n, eng.info], [want.n - 12, ["Counted: 6.5440"]]);
      // Its made-up "required" 15.THG isn't a base-plan course; v1 only ever marked base courses
      // required, and v2 takes "required" from the base plan, so that thesis note goes.
      assert.deepEqual(got.find(r => r.id === "thesis").notes, []);
      const rest = id => !["eng_elec", "eng_total", "thesis"].includes(id);
      assert.deepEqual(got.filter(r => rest(r.id)), g.expected.requirements.filter(r => rest(r.id)));
    } else {
      assert.deepEqual(notes, []);
      assert.deepEqual(got, g.expected.requirements);
    }
    assert.deepEqual(state.targets, g.targets);
  });
}

test("the migrated base plan stores nothing extra", () => {
  const g = readJson("tests/js/golden/a_base_plan.json");
  const { state } = State.migrateV1(ctx, { plan: clone(g.plan), reqs: null });
  assert.deepEqual(state, State.newState(program, 2028));
});

test("migration keeps removed base courses removed, units edits, old term names, custom courses", () => {
  const plan = clone(readJson("tests/js/golden/a_base_plan.json").plan)
    .filter(it => it.number !== "15.002")                              // removed by the student
    .map(it => it.id === "p18" ? { ...it, units: 10 } : it)            // 15.794 Y2 Fall: 12 -> 10
    .map(it => it.id === "p0" ? { ...it, term: "Fall 2026" } : it);   // moved a base course
  plan.push({ id: "pabc", number: "6.5060", title: "Algorithm Engineering", units: 12, tags: ["Eng Elective", "LGO Design"], term: "1st Fall", audit: false });
  plan.push({ id: "pabc", number: "15.S99", title: "Seminar on X", units: 6, tags: ["MBA Elective"], term: "2nd Spring", audit: true });
  plan.push({ id: "pdef", number: "15.016", title: "old title", units: 9, tags: [], term: "Winter 2027", audit: false });
  const { state, notes } = State.migrateV1(ctx, { plan, reqs: [{ key: "python", target: 2 }, { key: "nope", target: 4 }] });

  assert.deepEqual(state.removedBase, ["leadership-challenges-y1fall"]);
  assert.equal(state.items.find(it => it.base === "ops-research-y2fall").units, 10);
  assert.equal(state.items.find(it => it.base === "teams-y1summer").slot, "Y1 Fall");
  const added = state.items.filter(it => !it.base);
  assert.deepEqual(added[0], { id: "pabc", course: "6.5060", slot: "Y1 Fall", addons: ["LGO Design"] });
  assert.notEqual(added[1].id, "pabc", "duplicate ids get a new one");
  assert.deepEqual({ ...added[1], id: "x" }, { id: "x", course: null, slot: "Y2 Spring", audit: true,
    custom: { number: "15.S99", title: "Seminar on X", units: 6 }, category: "MBA Elective" });
  assert.deepEqual({ ...added[2] }, { id: "pdef", course: "15.016", slot: "unassigned", category: null, units: 9 });
  assert.deepEqual(notes, ["15.016 was in an unknown term (Winter 2027); it's now unassigned."]);
  assert.deepEqual(state.targets, { python: 2 });
  assert.deepEqual(State.validate(ctx, clone(state)), state);
});

test("a v1 save with targets but no plan keeps the base plan", () => {
  const { state } = State.migrateV1(ctx, { plan: null, reqs: [{ key: "mba_total", target: 150 }] });
  assert.equal(state.items.length, program.base_plan.length);
  assert.deepEqual(state.removedBase, []);
  assert.deepEqual(state.targets, { mba_total: 150 });
});

test("Start blank in v1 migrates to removed base courses", () => {
  const g = readJson("tests/js/golden/a_base_plan.json");
  const plan = g.plan.filter(it => it.required).map(it => ({ ...it, term: "Unassigned" }));
  const { state } = State.migrateV1(ctx, { plan, reqs: null });
  assert.equal(state.items.length, 2);
  assert.equal(state.removedBase.length, 21);
});

test("import takes a v2 plan or a v1 export, and refuses anything else", () => {
  const v2 = State.newState(program, 2027);
  assert.deepEqual(State.fromFile(ctx, clone(v2)).state, v2);
  const g = readJson("tests/js/golden/b_complete_eecs.json");
  const v1 = State.fromFile(ctx, { plan: clone(g.plan), reqs: [] });
  assert.deepEqual(evaluate(v1.state).requirements.map(shown), g.expected.requirements);
  assert.throws(() => State.fromFile(ctx, { hello: 1 }), /isn't a plan export/);
});
