// Saved state v2: defaults, "store only what changed", base-plan reconciliation and validation.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const Engine = require("../../app/engine.js");
const State = require("../../app/state.js");
const { readJson } = require("./helpers.js");

const program = Engine.resolve(readJson("programs/lgo.json"), readJson("programs/eecs.json"));
const frozen = readJson("tests/js/golden/courses.json").courses;
const ctx = { program, course: n => frozen[n] || null };
const info = n => { const c = frozen[n] || {}; return { aags: c.aags, design: c.design_approved, department: c.department }; };
const golden = name => readJson(path.join("tests/js/golden", name + ".json"));
const withoutId = items => items.map(({ id, ...rest }) => rest);
const clone = x => JSON.parse(JSON.stringify(x));

test("a new plan is the base plan, item for item (ids aside)", () => {
  const items = State.toItems(ctx, State.newState(program, 2028));
  assert.deepEqual(withoutId(items), withoutId(golden("a_base_plan").plan));
});

test("a new plan stores nothing but slots and base ids", () => {
  const s = State.newState(program, 2028);
  for (const it of s.items) assert.deepEqual(Object.keys(it).sort(), ["base", "course", "id", "slot"]);
  assert.deepEqual(s.targets, {});
  assert.deepEqual(s.removedBase, []);
});

test("the base plan gives the same results for every graduation year; only term names move", () => {
  const ref = Engine.evaluate(program, State.toItems(ctx, State.newState(program, 2028)), info);
  for (const year of [2026, 2027, 2028, 2029]) {
    const items = State.toItems(ctx, State.newState(program, year));
    const res = Engine.evaluate(program, items, info);
    const shift = t => t.replace(/\d{4}/, y => String(+y - (year - 2028)));
    assert.deepEqual(res.requirements.map(r => ({ ...r, notes: r.notes.map(n => n.replace(/\d{4}/g, y => String(+y - (year - 2028)))) })),
      ref.requirements, `year ${year}`);
    assert.deepEqual(Object.fromEntries(Object.entries(res.terms).map(([t, v]) => [shift(t), v])), ref.terms, `year ${year}`);
    assert.equal(items.find(it => it.number === "15.316").term, `Summer ${year - 2}`);
    assert.equal(items.find(it => it.number === "15.317" && it.term.startsWith("Spring")).term, `Spring ${year}`);
  }
});

test("edits keep only what differs from the default", () => {
  const s = State.newState(program, 2028);
  const base = s.items.find(it => it.course === "15.794" && it.slot === "Y2 Fall");
  State.setUnits(ctx, s, base.id, 10);
  assert.equal(base.units, 10);
  State.setUnits(ctx, s, base.id, 12);              // back to the base_plan value
  assert.ok(!("units" in base));

  const it = State.addCourse(s, "6.5060", "Y1 Fall");
  State.setUnits(ctx, s, it.id, 12);                // catalog units: not stored
  State.setCategory(ctx, s, it.id, "Eng Elective"); // classify default: not stored
  assert.deepEqual(Object.keys(it).sort(), ["course", "id", "slot"]);
  State.setCategory(ctx, s, it.id, "MBA Elective");
  State.toggleAddon(s, it.id, "LGO Design");
  State.setAudit(s, it.id, true);
  assert.deepEqual({ category: it.category, addons: it.addons, audit: it.audit }, { category: "MBA Elective", addons: ["LGO Design"], audit: true });
  State.setCategory(ctx, s, it.id, null);
  assert.equal(it.category, null);                   // "no category" is a choice, so it's stored
  State.toggleAddon(s, it.id, "LGO Design");
  State.setAudit(s, it.id, false);
  assert.ok(!("addons" in it) && !("audit" in it));

  State.setTarget(program, s, "mba_total", 150);
  State.setTarget(program, s, "python", 1);         // default: not stored
  assert.deepEqual(s.targets, { mba_total: 150 });
});

test("hand-typed courses: catalog numbers become courses, others stay custom", () => {
  const s = State.newState(program, 2028);
  const a = State.addCustom(ctx, s, { number: "15.016", title: "My title", units: 9 }, "Y1 Fall");
  assert.deepEqual({ course: a.course, units: a.units, custom: a.custom }, { course: "15.016", units: 9, custom: undefined });
  const b = State.addCustom(ctx, s, { number: "15.S99", title: "Special seminar", units: 6 }, "unassigned");
  const shown = State.toItems(ctx, s).find(it => it.id === b.id);
  assert.deepEqual({ number: shown.number, title: shown.title, units: shown.units, tags: shown.tags, term: shown.term },
    { number: "15.S99", title: "Special seminar", units: 6, tags: [], term: "Unassigned" });  // no department: no default category, as before
  State.setUnits(ctx, s, b.id, 3);
  assert.equal(b.custom.units, 3);
});

test("required courses only move to their allowed terms and can't be removed", () => {
  const s = State.newState(program, 2028);
  const req = s.items.find(it => it.base === "ops-strategy");
  assert.equal(State.moveTo(ctx, s, req.id, "Y1 Fall"), false);
  assert.equal(State.moveTo(ctx, s, req.id, "Y2 Spring"), true);
  assert.equal(State.removeItem(ctx, s, req.id), false);
});

test("removing a base course is remembered; Start blank keeps only required courses", () => {
  const s = State.newState(program, 2028);
  State.removeItem(ctx, s, "leadership-challenges-y1fall");
  assert.deepEqual(s.removedBase, ["leadership-challenges-y1fall"]);
  assert.deepEqual(State.reconcile(ctx, s), []);     // not re-added
  State.startBlank(ctx, s);
  assert.deepEqual(s.items.map(it => [it.base, it.slot]), [["ops-strategy", "unassigned"], ["ops-seminar-spring", "unassigned"]]);
  assert.equal(s.removedBase.length, 21);
});

test("reconciliation adds new base courses and drops retired ones", () => {
  const s = State.newState(program, 2028);
  const p2 = clone(program);
  p2.base_plan = p2.base_plan.filter(b => b.id !== "lean-ops-y1summer");
  p2.base_plan.push({ id: "new-course", course: "15.016", title: "A new LGO course", units: 6, category: "LGO Required MBA", slot: "Y1 IAP" });
  const changes = State.reconcile({ ...ctx, program: p2 }, s);
  assert.deepEqual(changes, ["No longer in the LGO base plan, so removed from your plan: 15.876.",
    "Added from the LGO base plan: 15.016 A new LGO course."]);
  assert.ok(s.items.some(it => it.base === "new-course") && !s.items.some(it => it.base === "lean-ops-y1summer"));
  assert.deepEqual(State.reconcile({ ...ctx, program: p2 }, s), []);
});

test("validation accepts a saved plan and rejects broken ones with a reason", () => {
  const s = State.newState(program, 2027);
  State.addCourse(s, "6.5060", "Y1 Fall");
  s.targets = { mba_total: 150, not_a_requirement: 3 };
  const ok = State.validate(ctx, clone(s));
  assert.deepEqual(ok.targets, { mba_total: 150 });
  assert.equal(ok.gradYear, 2027);
  const bad = (change, msg) => {
    const x = clone(s); change(x);
    assert.throws(() => State.validate(ctx, x), msg);
  };
  bad(x => { x.v = 1; }, /isn't a saved plan/);
  bad(x => { x.program = "meche"; }, /different program/);
  bad(x => { delete x.gradYear; }, /graduation year/);
  bad(x => { x.items[0].slot = "Y3 Fall"; }, /unknown term/);
  bad(x => { x.items.push({ ...x.items[0] }); }, /unique/);
  bad(x => { x.items[0].category = "Underwater Basket Weaving"; }, /unknown category/);
  bad(x => { x.items[0].units = "nine"; }, /aren't a number/);
  assert.throws(() => State.validate(ctx, null), /isn't a saved plan/);
});

test("an export round-trips exactly", () => {
  const s = State.newState(program, 2029);
  State.addCustom(ctx, s, { number: "15.S99", title: "Seminar", units: 6 }, "Y2 Fall");
  State.setTarget(program, s, "aags", 24);
  const back = State.validate(ctx, JSON.parse(JSON.stringify(s)));
  assert.deepEqual(back, s);
});

test("graduation years on offer: the incoming class back three years, rolling over in June", () => {
  const at = (y, m) => State.gradYearOptions(program, new Date(y, m - 1, 15));
  assert.deepEqual(at(2026, 11), [2026, 2027, 2028, 2029]);
  assert.deepEqual(at(2027, 5), [2026, 2027, 2028, 2029]);
  assert.deepEqual(at(2027, 6), [2027, 2028, 2029, 2030]);
  assert.deepEqual(at(2027, 1), [2026, 2027, 2028, 2029]);
});

test("changing the graduation year moves every course with its slot", () => {
  const s = State.newState(program, 2028);
  const it = State.addCourse(s, "6.5060", "Y2 Fall");
  const termOf = () => State.toItems(ctx, s).find(x => x.id === it.id).term;
  assert.equal(termOf(), "Fall 2027");
  s.gradYear = 2026;
  assert.equal(termOf(), "Fall 2025");
  assert.deepEqual(Object.values(State.slotLabels(program, 2026)),
    ["Summer 2024", "Fall 2024", "IAP 2025", "Spring 2025", "Summer 2025", "Fall 2025", "IAP 2026", "Spring 2026"]);
});
