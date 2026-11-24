// Course data from db.js (courses x term offerings): lookups, a course's status in a given term,
// the term badges, and the fields Browse shows. Pure (no DOM), so node tests load it too.
//
//   const cat = Catalog.load(window.COURSE_DB)
//   cat.get(id) / cat.byNumber(number) / cat.resolve(number, term)
//   cat.info(id)            {aags, design, department}  (what the degree rules read)
//   cat.offering(id, term)  that term's offering, or the course's reference offering
//   cat.status(id, term)    {code, symbol, label, tip}  (see LEGEND)
//   cat.coverage(term)      "before" | "after" | null   (why a term has no schedule data)
//   cat.row(course)         the flat fields Browse renders
const Catalog = (() => {
  // Within a calendar year: IAP (January), Spring, Summer, Fall.
  const SEASONS = ["IAP", "Spring", "Summer", "Fall"];
  const termKey = t => { const [s, y] = String(t).split(" "); return +y * 4 + SEASONS.indexOf(s); };
  // Academic year of a term: Fall 2026 .. Summer 2027 is "2026–27".
  const ayOf = t => { const [s, y] = t.split(" "); const start = s === "Fall" ? +y : +y - 1; return `${start}–${String(start + 1).slice(2)}`; };

  // One set of badges for Browse, the add-course search and the plan. Students see four marks
  // (✓ ~ ? ✕); the codes stay distinct so the tooltip can say exactly why. A term with no
  // schedule data (before tracking began, or beyond the published catalog) gets no mark at all:
  // the plan says so once in the term's header instead of on every course.
  const LEGEND = {
    listed:      { symbol: "✓", label: "Offered", tip: "On MIT's schedule for this term." },
    ran:         { symbol: "✓", label: "Offered", tip: "Was offered this term." },
    expected:    { symbol: "~", label: "Likely offered", tip: "Usually offered this term; MIT hasn't posted the schedule yet." },
    unverified:  { symbol: "?", label: "Check with dept.", tip: "Offered irregularly; confirm with the department before counting on it." },
    not_offered: { symbol: "✕", label: "Not offered", tip: "MIT's catalog says it isn't offered this term." },
    removed:     { symbol: "✕", label: "Not offered", tip: "Was on this term's schedule, then removed from the catalog." },
    not_listed:  { symbol: "✕", label: "Not offered", tip: "Not on MIT's schedule for this term." },
    didnt_run:   { symbol: "✕", label: "Not offered", tip: "Wasn't offered this term, so it can't be added here." },
    no_record:   { symbol: "", label: "No data", tip: "No schedule data this far back: any course can be planned here." },
    not_projected: { symbol: "", label: "No data", tip: "MIT hasn't published schedules this far ahead." },
  };
  const badge = code => ({ code, ...LEGEND[code] });
  const AVAILABLE = new Set(["listed", "expected", "unverified"]);

  function load(db) {
    const courses = db.courses, meta = db.meta;
    const byId = new Map(courses.map(c => [c.id, c]));
    const byNum = new Map();
    for (const c of courses) { if (!byNum.has(c.number)) byNum.set(c.number, []); byNum.get(c.number).push(c); }
    const first = termKey(meta.terms[0]), last = termKey(meta.terms[meta.terms.length - 1]);
    const current = termKey(meta.current_term);
    // Departments the AAGS list covers (from the pipeline's config): there, a course not on the
    // list is "Not approved"; elsewhere AAGS doesn't apply.
    const aagsDepts = new Set(meta.aags_departments || []);

    const get = id => byId.get(id) || null;
    const byNumber = n => byNum.get(n) || [];
    const termsOf = c => Object.keys(c.offerings).sort((a, b) => termKey(a) - termKey(b));
    // A number to a course id; a special subject's number can have several topics, so prefer the
    // one running in `term`.
    function resolve(number, term) {
      const cs = byNumber(number);
      if (!cs.length) return null;
      const running = term && cs.find(c => c.offerings[term] && AVAILABLE.has(c.offerings[term].status));
      return (running || cs.find(c => c.offerings[term]) || cs[0]).id;
    }
    // The offering Browse describes: the current term's, else the next one, else the latest.
    function reference(c) {
      const ts = termsOf(c);
      return ts.find(t => termKey(t) >= current) || ts[ts.length - 1];
    }
    function offering(id, term) {
      const c = get(id);
      if (!c) return null;
      return (term && c.offerings[term]) || c.offerings[reference(c)] || null;
    }
    const title = (id, term) => { const c = get(id), o = c && term && c.offerings[term]; return c ? (o && o.title) || c.title : null; };
    function info(id) {
      const c = get(id);
      if (!c) return {};
      const d = c.designations || {};
      return { aags: aagsLabel(c), design: d.design ? d.design.value : null, department: c.department };
    }
    // EECS's "Satisfies: AAGS in ..." wording on a subject that isn't on the AAGS list reads
    // "Needs approval": the student decides whether to count it (never automatic).
    const aagsLabel = c => (c.designations && c.designations.aags) ? c.designations.aags.value
      : (c.designations && c.designations.aags_note) ? "Needs approval"
      : aagsDepts.has(c.department) ? "Not approved" : "N/A";
    // Courses a student may count toward AAGS on their own call: special subjects and courses
    // with EECS's AAGS wording, unless already on the AAGS list.
    const claimable = id => { const c = get(id), d = (c && c.designations) || {};
      return !!c && !d.aags && (c.kind === "special" || !!d.aags_note); };

    function status(id, term) {
      const k = termKey(term);
      if (k < first) return badge("no_record");
      if (k > last) return badge("not_projected");
      const o = get(id) && get(id).offerings[term];
      if (k < current) return badge(o && o.status === "listed" ? "ran" : "didnt_run");
      if (!o) return badge("not_listed");
      return badge(o.status);
    }
    // Past terms inside tracking only take courses that ran; anything else can be planned.
    const addable = (id, term) => status(id, term).code !== "didnt_run";
    const isPastTracked = term => termKey(term) < current && termKey(term) >= first;
    // Inside the terms the catalog covers (not before tracking began, not beyond it).
    const tracked = term => termKey(term) >= first && termKey(term) <= last;
    // Why a term has no schedule data: "before" tracking began, "after" the published catalog,
    // or null when the catalog covers it.
    const coverage = term => termKey(term) < first ? "before" : termKey(term) > last ? "after" : null;

    // Offered in a term now or later? If not, why not (for the dimmed rows in Browse).
    function availability(c) {
      const later = termsOf(c).filter(t => termKey(t) >= current);
      if (later.some(t => AVAILABLE.has(c.offerings[t].status))) return { now: true, reason: "" };
      const removed = later.find(t => c.offerings[t].status === "removed");
      if (removed) return { now: false, reason: `No longer listed since ${c.offerings[removed].last_seen}` };
      return { now: false, reason: `Not offered ${ayOf(meta.current_term)}` };
    }

    function row(c) {
      const o = c.offerings[reference(c)] || {}, u = o.units || {}, d = c.designations || {}, ev = c.evals || {};
      const al = d.action_learning;
      return {
        id: c.id, number: c.number, kind: c.kind, title: c.title, department: c.department || "",
        category: c.category || "", description: c.description || "", url: c.url,
        prereq_raw: c.prereq_raw || "",
        prereqs: (c.prereq_numbers || []).map(n => ({ number: n, name: (byNumber(n)[0] || {}).title || "" })),
        units_raw: u.raw || (u.kind === "arranged" ? "arranged" : ""), units_total: u.total ?? null,
        half_term: o.half || null, instructor: o.instructor || "", schedule_summary: o.schedule_summary || "",
        aags: aagsLabel(c), aags_note: d.aags_note ? d.aags_note.text : null,
        design_approved: d.design ? d.design.value : null,
        action_learning: al ? al.code : null, al_term: al ? al.term : null, al_name: al ? al.name : null,
        eval_hours_in: ev.hours_in ?? null, eval_hours_out: ev.hours_out ?? null, eval_responses: ev.responses ?? null,
        eval_term: ev.term || null, eval_instructor: ev.instructor || null,
        eval_instructor_match: ev.instructor_match ?? null, eval_status: c.evals ? "ok" : null,
        available: availability(c),
      };
    }

    return { meta, courses, get, byNumber, resolve, offering, title, info, status, addable, isPastTracked, tracked, coverage, claimable, row, termKey };
  }

  return { load, LEGEND, termKey };
})();

if (typeof module !== "undefined") module.exports = Catalog;
