// Saved state v2: defaults, "store only what changed", base-plan reconciliation and validation.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const Engine = require("../../app/engine.js");
const State = require("../../app/state.js");
const { readJson } = require("./helpers.js");

const program = Engine.resolve(readJson("programs/lgo.json"), readJson("programs/eecs.json"));
const Catalog = require("../../app/catalog.js");
const cat = Catalog.load(readJson("tests/js/golden/db.json"));   // frozen db.js subset
const ctx = { program, cat };
const info = key => cat.get(key) ? cat.info(key) : {};
const golden = name => readJson(path.join("tests/js/golden", name + ".json"));
const clone = x => JSON.parse(JSON.stringify(x));

test("a new plan is the base plan, item for item (ids and titles aside)", () => {
  const items = State.toItems(ctx, State.newState(program, 2028));
  const strip = its => its.map(({ id, title, course, ...rest }) => rest);
  assert.deepEqual(strip(items), strip(golden("a_base_plan").plan));
  // Titles come from the catalog, or the base plan for a course the catalog doesn't list.
  assert.equal(items.find(it => it.number === "15.317").title, "Leadership and Organizational Change");
  assert.equal(items.find(it => it.number === "6.S090").title, "Python Workshop");
  assert.equal(items.find(it => it.number === "15.066").course, "15.066");
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
  p2.base_plan.push({ id: "new-course", course: "15.016", units: 6, category: "LGO Required MBA", slot: "Y1 IAP" });
  const changes = State.reconcile({ ...ctx, program: p2 }, s);
  assert.deepEqual(changes, ["No longer in the LGO base plan, so removed from your plan: 15.876.",
    "Added from the LGO base plan: 15.016 Climate and Energy in the Global Economy."]);
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

test("older saves holding a course number point at the catalog id, by term for special subjects", () => {
  const s = State.newState(program, 2028);
  s.items.push({ id: "a", course: "15.S04", slot: "Y1 Spring" }, { id: "b", course: "15.S04", slot: "Y1 Fall" },
    { id: "c", course: "6.5060", slot: "Y1 Fall" }, { id: "d", course: "99.999", slot: "Y1 Fall" });
  assert.equal(State.fixCourseIds(ctx, s), 2);
  assert.deepEqual(s.items.slice(-4).map(it => it.course),
    ["15.S04~generative-ai-lab", "15.S04~special-seminar-in-management", "6.5060", "99.999"]);
  const shown = State.toItems(ctx, s);
  assert.equal(shown.find(it => it.id === "a").title, "Generative AI Lab");
  assert.equal(shown.find(it => it.id === "a").number, "15.S04");
});

test("a placeholder counts toward its requirement like a course", () => {
  const s = State.newState(program, 2028);
  const before = Engine.evaluate(program, State.toItems(ctx, s), info).requirements.find(r => r.id === "mba_elec").value;
  const p = State.addPlaceholder(s, { category: "MBA Elective", units: 9 }, "Y1 Spring");
  const item = State.toItems(ctx, s).find(it => it.id === p.id);
  assert.deepEqual([item.number, item.tags, item.units, item.term], ["", ["MBA Elective"], 9, "Spring 2027"]);
  const after = Engine.evaluate(program, State.toItems(ctx, s), info).requirements.find(r => r.id === "mba_elec").value;
  assert.equal(after - before, 9);
  assert.deepEqual(State.validate(ctx, JSON.parse(JSON.stringify(s))), s);
});

test("a Class of 2026 plan sits entirely before tracking began: every term is 'no record'", () => {
  const items = State.toItems(ctx, State.newState(program, 2026));
  const codes = new Set(items.filter(it => it.term !== "Unassigned" && it.course).map(it => cat.status(it.course, it.term).code));
  assert.deepEqual([...codes], ["no_record"]);
  assert.ok(cat.addable("6.5060", "Fall 2025"));
});

test("a course's default units come from that term's offering; arranged units default to 0", () => {
  const s = State.newState(program, 2028);
  const a = State.addCourse(s, "6.5060", "Y1 Fall");
  const b = State.addCourse(s, "15.S04~special-seminar-in-management", "Y1 Fall");
  const units = id => State.toItems(ctx, s).find(x => x.id === id).units;
  assert.equal(units(a.id), cat.offering("6.5060", "Fall 2026").units.total);
  assert.equal(cat.offering(b.course, "Fall 2026").units.kind, "arranged");
  assert.equal(units(b.id), 0);
});

test("a student's AAGS claim is stored only when on, reaches the engine and is validated", () => {
  const s = State.newState(program, 2028);
  const it = State.addCourse(s, "15.S04~generative-ai-lab", "Y1 Spring");
  State.toggleClaim(s, it.id, "aags");
  assert.deepEqual(it.claims, ["aags"]);
  assert.deepEqual(State.toItems(ctx, s).find(x => x.id === it.id).claims, ["aags"]);
  assert.deepEqual(State.validate(ctx, JSON.parse(JSON.stringify(s))), s);
  State.toggleClaim(s, it.id, "aags");
  assert.ok(!("claims" in it));
  assert.ok(!("claims" in State.toItems(ctx, s).find(x => x.id === it.id)));
  const bad = JSON.parse(JSON.stringify(s));
  bad.items.find(x => x.id === it.id).claims = ["mba_core"];
  assert.throws(() => State.validate(ctx, bad), /by hand/);
});
