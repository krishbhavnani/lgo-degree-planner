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
  for (const k of Object.keys(Catalog.LEGEND)) assert.ok(Catalog.LEGEND[k].tip && Catalog.LEGEND[k].label, k);
});

test("students see four marks; a term with no schedule data gets none", () => {
  const sym = code => Catalog.LEGEND[code].symbol;
  assert.deepEqual([...new Set(Object.keys(Catalog.LEGEND).map(sym))].sort(), ["", "?", "~", "✓", "✕"].sort());
  for (const c of ["not_offered", "removed", "not_listed", "didnt_run"]) assert.equal(Catalog.LEGEND[c].label, "Not offered", c);
  assert.equal(sym("no_record"), "");
  assert.equal(sym("not_projected"), "");
  assert.equal(cat.coverage("Summer 2026"), "before");
  assert.equal(cat.coverage("Fall 2026"), null);
  assert.equal(cat.coverage("Summer 2028"), null);
  assert.equal(cat.coverage("Fall 2028"), "after");
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

test("Term scope: now or later by default; 'all' or the past term shows a past-only course", () => {
  const db2 = JSON.parse(JSON.stringify(db));
  db2.meta.current_term = "IAP 2027";                     // after the flip: Fall 2026 is past
  db2.courses.push({ id: "6.S978~engineering-ai", number: "6.S978", kind: "special", title: "Engineering AI",
    department: "Course 6 — EECS", offerings: { "Fall 2026": off("listed") } });
  const c2 = Catalog.load(db2), r = c2.row(c2.get("6.S978~engineering-ai"));
  assert.deepEqual(r.available, { now: false, reason: "Last offered Fall 2026" });
  assert.equal(c2.inScope(r, ""), false);
  assert.equal(c2.inScope(r, "all"), true);
  assert.equal(c2.inScope(r, "Fall 2026"), true);
  assert.equal(c2.inScope(r, "Spring 2027"), false);
  const now = c2.row(c2.get("6.1220"));                   // Spring 2027 listed
  assert.equal(c2.inScope(now, ""), true);
});

test("Your terms: chips for the student's remaining terms, or why there are none", () => {
  const db2 = JSON.parse(JSON.stringify(db));
  db2.courses.push({ id: "15.010", number: "15.010", kind: "regular", title: "Economic Analysis", department: "Course 15 — Management",
    offerings: { "Fall 2027": off("expected") } });
  const c2 = Catalog.load(db2), s = (id, terms) => c2.termsSummary(c2.row(c2.get(id)), terms);
  // Class of 2027, current term Fall 2026: Summer 2025 .. Spring 2027, of which Fall 2026 on remain.
  const class27 = ["Summer 2025", "Fall 2025", "IAP 2026", "Spring 2026", "Summer 2026", "Fall 2026", "IAP 2027", "Spring 2027"];
  assert.deepEqual(c2.remaining(class27), ["Fall 2026", "IAP 2027", "Spring 2027"]);
  const alg = s("6.5060", class27);
  assert.deepEqual([alg.chips.map(x => x.term + " " + x.badge.symbol), alg.reason, alg.first], [["Fall 2026 ✓"], "", "Fall 2026"]);
  assert.deepEqual(s("15.010", class27), { chips: [], reason: "Next offered Fall 2027", first: "Fall 2027" });
  assert.deepEqual(s("6.5130", class27), { chips: [], reason: "Not offered 2026–27", first: null });
  assert.deepEqual(s("15.007", class27).reason, "No longer listed since 2026-10-30");
  // Class of 2028 reaches Fall 2027, so the same course gets a chip.
  const class28 = ["Summer 2026", "Fall 2026", "IAP 2027", "Spring 2027", "Summer 2027", "Fall 2027", "IAP 2028", "Spring 2028"];
  assert.deepEqual(s("15.010", class28).chips.map(x => x.term + " " + x.badge.symbol), ["Fall 2027 ~"]);
  assert.deepEqual(s("15.010", []).reason, "Next offered Fall 2027");          // nothing left: next from now
});

test("departments and course numbers sort in MIT order, not as text", () => {
  const depts = ["Common Ground — other depts", "Course 21M — Music", "Course 15 — Management", "Course 2 — MechE",
    "Course 18 — Mathematics", "Course 14 — Economics", "Course 6 — EECS", "Course 16 — Aero/Astro"];
  assert.deepEqual([...depts].sort(Catalog.mitCompare), ["Course 2 — MechE", "Course 6 — EECS", "Course 14 — Economics",
    "Course 15 — Management", "Course 16 — Aero/Astro", "Course 18 — Mathematics", "Course 21M — Music", "Common Ground — other depts"]);
  const nums = ["21M.301", "15.S12", "6.C51", "15.401", "2.001", "14.01", "6.100A", "6.1010", "15.990"];
  assert.deepEqual([...nums].sort(Catalog.mitCompare), ["2.001", "6.100A", "6.1010", "6.C51", "14.01", "15.401", "15.990", "15.S12", "21M.301"]);
  assert.deepEqual(["21W.1", "21M.1", "21A.1"].sort(Catalog.mitCompare), ["21A.1", "21M.1", "21W.1"]);
});
