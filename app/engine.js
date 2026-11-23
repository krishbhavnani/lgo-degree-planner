// Requirements engine: pure functions over a program (programs/*.json), plan items and a course
// lookup. No DOM and no globals, so the same file runs in the page (<script>) and in node (tests).
//
//   resolve(base, major)        one program: the major's entries placed at the {"program": true}
//                               markers in the base (lgo.json); lists and bundles merged
//   termLabels(program, year)   ["Summer 2026", "Fall 2026", ...] for a plan starting in `year`
//   classify(program, number, courseInfo)          default category for a newly added course
//   evaluate(program, items, courseInfo, targets, known)  {requirements, terms, scheduled, summary}
//   listMembers(program, listId, numbers, courseInfo)  which of `numbers` are on a list
//
// courseInfo(key) -> {aags, design, department} (fields may be missing). key is an item's course
// id when it has one (a special subject's topics differ), else its number.
// targets: requirement id -> the user's own target, replacing min_units (min_courses for "count").
// known: every course number in the catalog, so notes can name a list's current members.
const Engine = (() => {
  const UNASSIGNED = "Unassigned";

  // Base entries in order, with the major's entries where the base has {"program": true}
  // (or at the end if it has no marker).
  function placeAt(base, major) {
    const out = [];
    let placed = false;
    for (const x of base || []) {
      if (x && x.program) { out.push(...(major || [])); placed = true; } else out.push(x);
    }
    if (!placed) out.push(...(major || []));
    return out;
  }

  function resolve(base, major) {
    return {
      id: major.id,
      name: major.name,
      terms: base.terms,
      term_unit_limit: base.term_unit_limit,
      grad_year_options: base.grad_year_options,
      categories: placeAt(base.categories, major.categories),
      lists: { ...base.lists, ...major.lists },
      classify: placeAt(base.classify, major.classify),
      bundles: [...(base.bundles || []), ...(major.bundles || [])],
      requirements: placeAt(base.requirements, major.requirements),
      base_plan: base.base_plan || [],
    };
  }

  function slotLabel(program, slot, year) {
    const t = program.terms.find(x => x.slot === slot);
    if (!t) throw new Error("unknown term slot: " + slot);
    return t.season + " " + (year + t.year_offset);
  }
  const termLabels = (program, year) => program.terms.map(t => slotLabel(program, t.slot, year));

  // A list is explicit numbers, a number pattern, or a course designation from the data.
  // infoOf() returns the course's designations; only designation lists call it.
  function inList(program, listId, number, infoOf) {
    const l = program.lists[listId];
    if (!l) throw new Error("unknown list: " + listId);
    if (Array.isArray(l)) return l.includes(number);
    if (l.pattern != null) return new RegExp(l.pattern).test(number) && !(l.except || []).includes(number);
    if (l.designation) {
      const v = (infoOf() || {})[l.designation];
      return l.prefix != null ? String(v || "").startsWith(l.prefix) : v === l.value;
    }
    throw new Error("list " + listId + " has no numbers, pattern or designation");
  }

  // The numbers on a list, in catalog order (1.C51, 2.C51, ..., 15.C51, SCM.C51).
  const listMembers = (program, listId, numbers, info) => [...new Set(numbers)]
    .filter(n => inList(program, listId, n, () => info(n)))
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));

  function classify(program, number, info) {
    const infoOf = () => info(number) || {};
    const dept = infoOf().department || "";
    for (const rule of program.classify) {
      const c = rule.if;
      if ((c.in && inList(program, c.in, number, infoOf)) || (c.dept && c.dept.some(d => dept.includes(d))))
        return [rule.then];
    }
    return [];
  }

  // Only scheduled courses count: audits and anything still in Unassigned don't.
  const counts = it => !it.audit && it.term !== UNASSIGNED;
  const keyOf = it => it.course || it.number;
  const unitsOf = it => +it.units || 0;
  const inPool = (it, pool) => (it.tags || []).some(t => (pool || []).includes(t));
  const fmtTerms = ts => ts.length > 1 ? ts.slice(0, -1).join(", ") + " or " + ts[ts.length - 1] : ts[0];
  const fill = (text, vars) => text.replace(/\{(\w+)\}/g, (m, k) => vars[k]);
  const defaultTarget = r => r.type === "count" ? r.min_courses : r.min_units;

  // from_set: candidates are bundles plus single courses on the list (bundle courses and the
  // `exclude` categories never count singly). The largest fill the requirement until it has both
  // its minimum courses and units; ties keep plan order. The courses used are claimed.
  function fromSet(program, r, scheduled, info, target, claimed, known) {
    const items = scheduled.filter(it => inPool(it, r.pool));
    const bundles = (r.bundles || []).map(id => program.bundles.find(b => b.id === id));
    const notes = [], cands = [];
    for (const b of bundles) {
      const lead = items.find(it => it.number === b.lead);
      const partners = items.filter(it => inList(program, b.partners, it.number, () => info(keyOf(it))));
      if (lead) {
        const used = partners.slice(0, b.max_partners);
        cands.push({ ids: [lead.id, ...used.map(p => p.id)],
          label: [lead.number, ...used.map(p => p.number)].join("+"),
          units: unitsOf(lead) + used.reduce((s, p) => s + unitsOf(p), 0) });
        if (!used.length && unitsOf(lead) < b.full_units)
          notes.push(fill(b.notes.no_partner, { modules: listMembers(program, b.partners, known, info).join(", ") || "none in the catalog right now" }));
        if (partners.length > b.max_partners)
          notes.push(fill(b.notes.extra_partners, { extra: partners.slice(b.max_partners).map(p => p.number).join(", ") }));
      } else if (partners.length) {
        notes.push(fill(b.notes.partner_alone, { partners: partners.map(p => p.number).join(", ") }));
      }
    }
    const inBundle = it => bundles.some(b => it.number === b.lead || inList(program, b.partners, it.number, () => info(keyOf(it))));
    // A claimable list (AAGS) also takes courses the student counts on their own call.
    const list = program.lists[r.list];
    for (const it of items) {
      if (inBundle(it) || inPool(it, r.exclude)) continue;
      const listed = inList(program, r.list, it.number, () => info(keyOf(it)));
      const claimed = !listed && !!list.claimable && (it.claims || []).includes(r.list);
      if (listed || claimed) cands.push({ ids: [it.id], label: it.number, units: unitsOf(it), claimed });
    }
    cands.sort((a, b) => b.units - a.units);
    const core = [];
    let total = 0;
    for (const c of cands) {
      if (core.length >= r.min_courses && total >= target) break;
      core.push(c);
      total += c.units;
    }
    claimed[r.id] = new Set(core.flatMap(c => c.ids));
    const onTheirCall = core.filter(c => c.claimed).map(c => c.label);
    if (onTheirCall.length) notes.push(fill(list.claim_note, { courses: onTheirCall.join(", ") }));
    return { value: total, courses: core.length, met: total >= target && core.length >= r.min_courses,
      counted: core.map(c => c.label), notes };
  }

  function evaluate(program, items, info, targets = {}, known = []) {
    const scheduled = items.filter(counts);
    const targetOf = r => targets[r.id] != null ? targets[r.id] : defaultTarget(r);
    const out = {}, claimed = {};
    // from_set first: other requirements can exclude the courses it claims.
    for (const r of program.requirements)
      if (r.type === "from_set") out[r.id] = { ...fromSet(program, r, scheduled, info, targetOf(r), claimed, known), target: targetOf(r) };
    for (const r of program.requirements) {
      if (r.type === "from_set") continue;
      const target = targetOf(r);
      if (r.type === "count") {
        const its = scheduled.filter(it => inPool(it, r.pool) || (r.or_in && inList(program, r.or_in, it.number, () => info(keyOf(it)))));
        out[r.id] = { value: its.length, courses: its.length, met: its.length >= target, counted: null, notes: [] };
      } else if (r.type === "sum" && r.exclude_claimed) {
        const used = claimed[r.exclude_claimed] || new Set();
        const its = scheduled.filter(it => !used.has(it.id) && inPool(it, r.pool));
        const value = its.reduce((s, it) => s + unitsOf(it), 0);
        out[r.id] = { value, courses: its.length, met: value >= target, counted: its.map(it => it.number), notes: [] };
      } else if (r.type === "sum") {
        const its = scheduled.filter(it => inPool(it, r.pool));
        const value = its.reduce((s, it) => s + unitsOf(it), 0);
        // Required courses still unscheduled are flagged on their own requirement, not on totals.
        const pending = r.headline ? [] : items.filter(it => it.required && it.term === UNASSIGNED && inPool(it, r.pool));
        out[r.id] = { value, courses: its.length, met: value >= target, counted: null,
          notes: pending.map(it => `${it.number} (${it.units}u) is required — schedule it in ${fmtTerms(it.allowedTerms || [])}.`) };
      } else {
        throw new Error("unknown requirement type: " + r.type);
      }
      out[r.id].target = target;
    }

    const requirements = program.requirements.map(r => ({ id: r.id, group: r.group, label: r.label, type: r.type,
      headline: !!r.headline, min_courses: r.min_courses, ...out[r.id] }));
    const terms = {};
    for (const it of items) {
      if (it.audit || it.term === UNASSIGNED) continue;
      (terms[it.term] = terms[it.term] || { units: 0 }).units += unitsOf(it);
    }
    for (const t of Object.values(terms)) t.over = t.units > program.term_unit_limit;
    const summary = program.requirements.filter(r => r.summary)
      .map(r => ({ label: r.summary, value: out[r.id].value, target: out[r.id].target }));
    return { requirements, terms, scheduled: scheduled.length, summary };
  }

  return { resolve, termLabels, classify, evaluate, listMembers, defaultTarget, UNASSIGNED };
})();

if (typeof module !== "undefined") module.exports = Engine;
