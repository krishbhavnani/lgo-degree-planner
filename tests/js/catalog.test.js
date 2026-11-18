// Catalog: db.js lookups, term status and Browse rows, on a small db.js-shaped fixture.
const test = require("node:test");
const assert = require("node:assert/strict");
const Catalog = require("../../app/catalog.js");

const units = total => ({ raw: total == null ? null : `${total / 3}-0-${(2 * total) / 3}`, total, kind: total == null ? "arranged" : "fixed" });
const off = (status, total = 12, extra = {}) => ({ status, units: units(total), first_seen: "2026-10-28", last_seen: "2026-11-02", ...extra });
const db = {
  meta: { updated: "2026-11-02", current_term: "Fall 2026", academic_year: "2026-2027", aags_departments: ["Course 6 — EECS"],
    terms: ["Fall 2026", "IAP 2027", "Spring 2027", "Summer 2027", "Fall 2027", "IAP 2028", "Spring 2028", "Summer 2028"] },
  courses: [
    { id: "6.5060", number: "6.5060", kind: "regular", title: "Algorithm Engineering", department: "Course 6 — EECS",
      designations: { aags: { value: "Approved-Offered" } }, prereq_numbers: ["6.1220"],
      evals: { hours_in: 3, hours_out: 7, responses: 20, term: "Fall 2025", instructor: null, instructor_match: true },
      offerings: { "Fall 2026": off("listed", 12, { instructor: "J. Shun", schedule_summary: "MW 1-2:30" }), "Fall 2027": off("expected") } },
    { id: "6.1220", number: "6.1220", kind: "regular", title: "Design and Analysis of Algorithms", department: "Course 6 — EECS",
      offerings: { "Spring 2027": off("listed"), "Spring 2028": off("unverified") } },
    { id: "6.5130", number: "6.5130", kind: "regular", title: "Not offered this year", department: "Course 6 — EECS",
      offerings: { "Fall 2026": off("not_offered"), "Fall 2027": off("not_offered") } },
    { id: "15.007", number: "15.007", kind: "regular", title: "Dropped", department: "Course 15 — Management",
      offerings: { "IAP 2027": off("removed", 6, { last_seen: "2026-10-30" }) } },
    { id: "15.005", number: "15.005", kind: "regular", title: "Half term", department: "Course 15 — Management",
      offerings: { "Spring 2027": off("listed", 6, { half: "H2" }) } },
    { id: "15.S04~generative-ai-lab", number: "15.S04", kind: "special", title: "Generative AI Lab", department: "Course 15 — Management",
      designations: { design: { value: "approved" }, action_learning: { code: "GENAI-LAB", name: "Generative AI Lab", term: "Spring" } },
      offerings: { "Spring 2027": off("listed", null) } },
    { id: "15.S04~special-seminar-in-management", number: "15.S04", kind: "special", title: "Special Seminar in Management",
      department: "Course 15 — Management", offerings: { "Fall 2026": off("listed", 9) } },
  ],
};
const cat = Catalog.load(db);

test("term order: IAP, Spring, Summer, Fall within a year", () => {
  const ts = ["Fall 2027", "IAP 2027", "Summer 2026", "Spring 2027", "Fall 2026"];
  assert.deepEqual([...ts].sort((a, b) => Catalog.termKey(a) - Catalog.termKey(b)),
    ["Summer 2026", "Fall 2026", "IAP 2027", "Spring 2027", "Fall 2027"]);
});

test("status in every kind of term", () => {
  const code = (id, t) => cat.status(id, t).code;
  assert.equal(code("6.5060", "Summer 2026"), "no_record");      // before tracking began
  assert.equal(code("6.5060", "Fall 2028"), "not_projected");    // beyond the catalog
  assert.equal(code("6.5060", "Fall 2026"), "listed");
  assert.equal(code("6.5060", "Spring 2027"), "not_listed");
  assert.equal(code("6.5060", "Fall 2027"), "expected");
  assert.equal(code("6.1220", "Spring 2028"), "unverified");
  assert.equal(code("6.5130", "Fall 2027"), "not_offered");
  assert.equal(code("15.007", "IAP 2027"), "removed");
  assert.equal(cat.status("6.5060", "Fall 2026").symbol, "✓");
  for (const k of Object.keys(Catalog.LEGEND)) assert.ok(Catalog.LEGEND[k].tip, k);
});

test("past terms inside tracking: ran or didn't run, and only courses that ran can be added", () => {
  const later = Catalog.load({ ...db, meta: { ...db.meta, current_term: "Spring 2027" } });
  assert.equal(later.status("6.5060", "Fall 2026").code, "ran");
  assert.equal(later.status("6.1220", "Fall 2026").code, "didnt_run");
  assert.equal(later.addable("6.1220", "Fall 2026"), false);
  assert.equal(later.addable("6.1220", "Summer 2026"), true);   // before tracking: anything
  assert.equal(later.isPastTracked("Fall 2026"), true);
  assert.equal(later.isPastTracked("Summer 2026"), false);
  assert.deepEqual(["Summer 2026", "Fall 2026", "Summer 2028", "Fall 2028"].map(cat.tracked), [false, true, true, false]);
});

test("a special subject's number resolves to the topic running that term", () => {
  assert.equal(cat.resolve("15.S04", "Spring 2027"), "15.S04~generative-ai-lab");
  assert.equal(cat.resolve("15.S04", "Fall 2026"), "15.S04~special-seminar-in-management");
  assert.equal(cat.resolve("6.5060", "Spring 2027"), "6.5060");
  assert.equal(cat.resolve("99.999", "Fall 2026"), null);
});

test("what the rules read about a course", () => {
  assert.deepEqual(cat.info("6.5060"), { aags: "Approved-Offered", design: null, department: "Course 6 — EECS" });
  assert.equal(cat.info("6.1220").aags, "Not approved");          // AAGS department, not on the list
  assert.equal(cat.info("15.005").aags, "N/A");                    // not a department the list covers
  assert.equal(cat.info("15.S04~generative-ai-lab").design, "approved");
});

test("Browse rows come from the current or next offering", () => {
  const r = cat.row(cat.get("6.5060"));
  assert.deepEqual([r.units_total, r.instructor, r.schedule_summary, r.eval_hours_out, r.prereqs[0].name, r.available.now],
    [12, "J. Shun", "MW 1-2:30", 7, "Design and Analysis of Algorithms", true]);
  assert.equal(cat.row(cat.get("15.005")).half_term, "H2");
  const lab = cat.row(cat.get("15.S04~generative-ai-lab"));
  assert.deepEqual([lab.units_raw, lab.units_total, lab.action_learning, lab.design_approved], ["arranged", null, "GENAI-LAB", "approved"]);
  assert.deepEqual(cat.row(cat.get("6.5130")).available, { now: false, reason: "Not offered 2026–27" });
  assert.deepEqual(cat.row(cat.get("15.007")).available, { now: false, reason: "No longer listed since 2026-10-30" });
});

test("titles and offerings by term", () => {
  assert.equal(cat.title("6.5060", "Fall 2027"), "Algorithm Engineering");
  assert.equal(cat.offering("15.005", "Spring 2027").half, "H2");
  assert.equal(cat.offering("6.5060", "Spring 2027").status, "listed");   // no offering then: reference one
  assert.equal(cat.get("nope"), null);
});

test("EECS's AAGS wording reads 'Needs approval' and makes a course claimable; approval doesn't", () => {
  const db2 = JSON.parse(JSON.stringify(db));
  db2.courses.push({ id: "6.S978~engineering-ai", number: "6.S978", kind: "special", title: "Engineering AI", department: "Course 6 — EECS",
    designations: { aags_note: { text: "AUS, AAGS in Computer Systems", source: "EECS subject updates", scope: "Fall 2026" } },
    offerings: { "Fall 2026": off("listed") } });
  const c2 = Catalog.load(db2);
  const r = c2.row(c2.get("6.S978~engineering-ai"));
  assert.deepEqual([r.aags, r.aags_note], ["Needs approval", "AUS, AAGS in Computer Systems"]);
  assert.equal(c2.info("6.S978~engineering-ai").aags, "Needs approval");     // not "Approved…": rules won't count it
  assert.equal(c2.claimable("6.S978~engineering-ai"), true);
  assert.equal(c2.claimable("15.S04~special-seminar-in-management"), true);   // any special subject
  assert.equal(c2.claimable("6.5060"), false);                                  // already approved
  assert.equal(c2.claimable("6.1220"), false);                                  // regular, no EECS wording
});
