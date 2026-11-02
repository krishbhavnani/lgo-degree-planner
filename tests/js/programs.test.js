// Program files are valid: they parse, every reference resolves, and ids are unique.
const test = require("node:test");
const assert = require("node:assert/strict");
const Engine = require("../../app/engine.js");
const { programFiles, knownCourses } = require("./helpers.js");

const files = programFiles();
const BASE = "lgo";
const KINDS = ["primary", "addon", "special"];
const TYPES = ["sum", "count", "from_set"];
const DESIGNATIONS = ["aags", "design"];
const majors = Object.values(files).filter(p => p.id !== BASE);
const isMarker = x => x && x.program === true;
const dupes = ids => ids.filter((id, i) => ids.indexOf(id) !== i);

test("every program file parses and is named after its id", () => {
  for (const [name, p] of Object.entries(files)) assert.equal(p.id, name);
  assert.ok(files[BASE], "programs/lgo.json is missing");
  assert.ok(majors.length >= 1, "no major extends lgo");
  for (const m of majors) assert.equal(m.extends, BASE, `${m.id} must extend ${BASE}`);
});

test("lgo.json sets the graduation-year window", () => {
  const g = files[BASE].grad_year_options;
  assert.ok(Number.isInteger(g.back) && g.back >= 2, "back");
  assert.ok(Number.isInteger(g.new_class_month) && g.new_class_month >= 1 && g.new_class_month <= 12, "new_class_month");
});

test("lgo.json marks where a major's entries go, once per section", () => {
  for (const key of ["categories", "classify", "requirements"])
    assert.equal(files[BASE][key].filter(isMarker).length, 1, `lgo.json ${key} needs one {"program": true}`);
});

test("the course lists in lgo.json's not_in_catalog really aren't in the catalog", () => {
  const known = knownCourses();
  const nowListed = Object.keys(files[BASE].not_in_catalog || {}).filter(n => known.has(n));
  assert.deepEqual(nowListed, [], "now in the catalog: remove from not_in_catalog");
});

for (const major of majors) {
  const base = files[BASE];
  const p = Engine.resolve(base, major);
  const cats = p.categories.map(c => c.id);
  const reqIds = p.requirements.map(r => r.id);
  const slots = p.terms.map(t => t.slot);
  const hasList = id => Object.prototype.hasOwnProperty.call(p.lists, id);
  const hasCat = id => cats.includes(id);

  test(`${major.id}: ids are unique and lists aren't redefined`, () => {
    assert.deepEqual(dupes(cats), []);
    assert.deepEqual(dupes(reqIds), []);
    assert.deepEqual(dupes(p.bundles.map(b => b.id)), []);
    assert.deepEqual(Object.keys(major.lists || {}).filter(k => k in (base.lists || {})), []);
    assert.ok(!(major.categories || []).some(isMarker) && !(major.requirements || []).some(isMarker));
  });

  test(`${major.id}: categories, lists and default-category rules are well formed`, () => {
    for (const c of p.categories) assert.ok(KINDS.includes(c.kind), `${c.id}: kind ${c.kind}`);
    for (const [id, l] of Object.entries(p.lists)) {
      if (Array.isArray(l)) assert.ok(l.every(n => typeof n === "string"), id);
      else if (l.pattern != null) assert.doesNotThrow(() => new RegExp(l.pattern), id);
      else {
        assert.ok(DESIGNATIONS.includes(l.designation), `${id}: designation ${l.designation}`);
        assert.ok((l.prefix != null) !== (l.value != null), `${id}: needs prefix or value`);
      }
    }
    for (const r of p.classify) {
      assert.ok(hasCat(r.then), `classify -> unknown category ${r.then}`);
      assert.ok(r.if.in ? hasList(r.if.in) : Array.isArray(r.if.dept), JSON.stringify(r.if));
    }
  });

  test(`${major.id}: requirements reference real categories, lists, bundles and requirements`, () => {
    for (const r of p.requirements) {
      assert.ok(TYPES.includes(r.type), `${r.id}: type ${r.type}`);
      assert.ok(r.group && r.label, `${r.id}: group and label`);
      for (const c of [...r.pool, ...(r.exclude || [])]) assert.ok(hasCat(c), `${r.id}: category ${c}`);
      if (r.type === "count") assert.ok(Number.isInteger(r.min_courses), `${r.id}: min_courses`);
      else assert.ok(typeof r.min_units === "number", `${r.id}: min_units`);
      if (r.type === "from_set") {
        assert.ok(hasList(r.list) && Number.isInteger(r.min_courses), `${r.id}: list and min_courses`);
        for (const b of r.bundles || []) assert.ok(p.bundles.some(x => x.id === b), `${r.id}: bundle ${b}`);
      }
      if (r.or_in) assert.ok(hasList(r.or_in), `${r.id}: or_in ${r.or_in}`);
      if (r.exclude_claimed) {
        const src = p.requirements.find(x => x.id === r.exclude_claimed);
        assert.ok(src && src.type === "from_set", `${r.id}: exclude_claimed ${r.exclude_claimed}`);
      }
    }
    for (const b of p.bundles) {
      assert.ok(hasList(b.partners), `bundle ${b.id}: partners`);
      for (const k of ["no_partner", "extra_partners", "partner_alone"]) assert.ok(b.notes[k], `bundle ${b.id}: note ${k}`);
    }
  });

  test(`${major.id}: the base plan uses real categories and term slots`, () => {
    assert.deepEqual(dupes(p.base_plan.map(b => b.id)), [], "base_plan ids must be unique");
    for (const b of p.base_plan) {
      assert.ok(typeof b.id === "string" && b.id, `${b.course}: needs an id`);
      assert.ok(hasCat(b.category), `${b.course}: category ${b.category}`);
      assert.ok(typeof b.units === "number", `${b.course}: units`);
      if (b.required) assert.ok(b.allowed_slots.length && b.allowed_slots.every(s => slots.includes(s)), `${b.course}: allowed_slots`);
      else assert.ok(slots.includes(b.slot), `${b.course}: slot ${b.slot}`);
    }
  });

  test(`${major.id}: every course named in the rules is in the catalog (or listed as not)`, () => {
    const known = knownCourses();
    const notInCatalog = new Set(Object.keys(base.not_in_catalog || {}));
    const named = new Set();
    for (const l of Object.values(p.lists)) {
      if (Array.isArray(l)) l.forEach(n => named.add(n));
      else (l.except || []).forEach(n => named.add(n));
    }
    p.bundles.forEach(b => named.add(b.lead));
    p.base_plan.forEach(b => named.add(b.course));
    const unknown = [...named].filter(n => !known.has(n) && !notInCatalog.has(n));
    assert.deepEqual(unknown, []);
  });
}
