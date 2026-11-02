// Saved state in the browser: the load/save helpers every tab uses, and State, the planner's saved
// plan. State is pure (no DOM, no storage), so node tests load this file too.
function load(k,def){try{const v=JSON.parse(localStorage.getItem(k));return v??def;}catch(e){return def;}}
function save(k,v){localStorage.setItem(k,JSON.stringify(v));}
function esc(s){return (s==null?'':String(s)).replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));}

// Saved plan, v2: only the student's own choices. Everything else comes from the program files
// (base plan, rules) and the course data (titles, units), so fixes reach returning users.
//   {v:2, program, gradYear, yearChosen?, items, removedBase, targets}
//   item: {id, course|null, slot ("Y1 Fall" ... or "unassigned"), base?, units?, category?,
//          addons?, audit?, custom?: {number, title, units}}
// units/category are stored only when they differ from the default; targets only when edited.
//
// ctx = {program (resolved), course(number) -> {title, units_total, department, aags,
//        design_approved} or null}
const State = (() => {
  const E = typeof Engine !== "undefined" ? Engine : require("./engine.js");
  const V = 2;
  const UNASSIGNED = "unassigned";

  const info = ctx => n => { const c = ctx.course(n) || {}; return { aags: c.aags, design: c.design_approved, department: c.department }; };
  const baseOf = (ctx, it) => it.base ? ctx.program.base_plan.find(b => b.id === it.base) || null : null;
  const numberOf = it => it.course || (it.custom && it.custom.number) || "";
  const find = (state, id) => state.items.find(x => x.id === id);
  const newId = () => "p" + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

  // The plan's first summer is (grad year - the last term's year offset).
  function slotLabels(program, gradYear) {
    const last = Math.max(...program.terms.map(t => t.year_offset));
    const labels = E.termLabels(program, gradYear - last);
    return Object.fromEntries(program.terms.map((t, i) => [t.slot, labels[i]]));
  }

  // Graduation years to offer on `today`: from the incoming class (the one starting next summer;
  // from new_class_month on, "next summer" is next year's) back `back` years.
  function gradYearOptions(program, today) {
    const o = program.grad_year_options;
    const last = Math.max(...program.terms.map(t => t.year_offset));
    const nextStart = today.getFullYear() + (today.getMonth() + 1 >= o.new_class_month ? 1 : 0);
    const newest = nextStart + last;
    return Array.from({ length: o.back + 1 }, (_, i) => newest - o.back + i);
  }

  function newState(program, gradYear) {
    return { v: V, program: program.id, gradYear, items: program.base_plan.map(b =>
      ({ id: b.id, course: b.course, slot: b.slot || UNASSIGNED, base: b.id })), removedBase: [], targets: {} };
  }

  // What an item is when the student hasn't changed it.
  function defaults(ctx, it) {
    const b = baseOf(ctx, it);
    if (b) return { title: b.title, units: b.units, category: b.category };
    const n = numberOf(it);
    const category = n ? E.classify(ctx.program, n, info(ctx))[0] || null : null;
    if (it.custom) return { title: it.custom.title || n, units: it.custom.units ?? 0, category };
    const c = ctx.course(it.course);
    return { title: c ? c.title : n, units: c && c.units_total != null ? c.units_total : 0, category };
  }

  // The items the engine and the term grid use: calendar terms for the grad year, tags =
  // category + addons, and the base plan's locks.
  function toItems(ctx, state) {
    const labels = slotLabels(ctx.program, state.gradYear);
    return state.items.map(it => {
      const d = defaults(ctx, it), b = baseOf(ctx, it);
      const category = "category" in it ? it.category : d.category;
      const out = { id: it.id, number: numberOf(it), title: d.title, units: it.units ?? d.units,
        tags: [category, ...(it.addons || [])].filter(Boolean),
        term: it.slot === UNASSIGNED ? E.UNASSIGNED : labels[it.slot], audit: !!it.audit, base: !!it.base };
      if (b && b.required) { out.required = true; out.allowedTerms = (b.allowed_slots || []).map(s => labels[s]); }
      return out;
    });
  }

  // ---- edits: each keeps only what differs from the default ----
  function setUnits(ctx, state, id, units) {
    const it = find(state, id);
    if (it.custom) { it.custom.units = units; return; }
    if (units === defaults(ctx, it).units) delete it.units; else it.units = units;
  }
  function setCategory(ctx, state, id, category) {
    const it = find(state, id);
    if (category === defaults(ctx, it).category) delete it.category; else it.category = category;
  }
  function toggleAddon(state, id, addon) {
    const it = find(state, id), a = new Set(it.addons || []);
    if (a.has(addon)) a.delete(addon); else a.add(addon);
    if (a.size) it.addons = [...a]; else delete it.addons;
  }
  function setAudit(state, id, on) { const it = find(state, id); if (on) it.audit = true; else delete it.audit; }
  // Required base courses may only go to their allowed terms (or back to unassigned).
  function moveTo(ctx, state, id, slot) {
    const it = find(state, id), b = baseOf(ctx, it);
    if (b && b.required && slot !== UNASSIGNED && !(b.allowed_slots || []).includes(slot)) return false;
    it.slot = slot;
    return true;
  }
  function addCourse(state, number, slot) {
    const it = { id: newId(), course: number, slot };
    state.items.push(it);
    return it;
  }
  // A course typed in by hand: a catalog number becomes a normal course (with its units if
  // given); anything else is kept as a custom item with its own title and units.
  function addCustom(ctx, state, { number, title, units }, slot) {
    if (number && ctx.course(number)) {
      const it = addCourse(state, number, slot);
      if (units != null) setUnits(ctx, state, it.id, units);
      return it;
    }
    const it = { id: newId(), course: null, slot, custom: { number, title: title || number, units: units || 0 } };
    state.items.push(it);
    return it;
  }
  function removeItem(ctx, state, id) {
    const it = find(state, id), b = baseOf(ctx, it);
    if (b && b.required) return false;
    if (it.base) state.removedBase.push(it.base);
    state.items = state.items.filter(x => x.id !== id);
    return true;
  }
  // Clear the schedule: required courses go back to unassigned, everything else is removed.
  function startBlank(ctx, state) {
    for (const it of [...state.items]) {
      const b = baseOf(ctx, it);
      if (b && b.required) it.slot = UNASSIGNED; else removeItem(ctx, state, it.id);
    }
  }
  function setTarget(program, state, reqId, value) {
    const req = program.requirements.find(r => r.id === reqId);
    if (value === E.defaultTarget(req)) delete state.targets[reqId]; else state.targets[reqId] = value;
  }

  // Bring a saved plan up to date with the current base plan: add base courses the student hasn't
  // removed, drop retired ones. Returns at most two lines (removed, added) for the notice.
  function reconcile(ctx, state) {
    const ids = new Set(ctx.program.base_plan.map(b => b.id));
    const removed = [], added = [];
    state.items = state.items.filter(it => {
      if (!it.base || ids.has(it.base)) return true;
      removed.push(numberOf(it));
      return false;
    });
    state.removedBase = (state.removedBase || []).filter(id => ids.has(id));
    const have = new Set(state.items.filter(it => it.base).map(it => it.base));
    for (const b of ctx.program.base_plan) {
      if (have.has(b.id) || state.removedBase.includes(b.id)) continue;
      state.items.push({ id: b.id, course: b.course, slot: b.slot || UNASSIGNED, base: b.id });
      added.push(`${b.course} ${b.title}`);
    }
    return [...(removed.length ? [`No longer in the LGO base plan, so removed from your plan: ${removed.join("; ")}.`] : []),
      ...(added.length ? [`Added from the LGO base plan: ${added.join("; ")}.`] : [])];
  }

  // Check a saved or imported v2 plan; throws an Error saying what's wrong.
  function validate(ctx, obj) {
    const fail = m => { throw new Error(m); };
    if (!obj || typeof obj !== "object" || obj.v !== V) fail("this isn't a saved plan (v2)");
    if (obj.program !== ctx.program.id) fail(`this plan is for a different program (${obj.program})`);
    if (!Number.isInteger(obj.gradYear)) fail("the graduation year is missing");
    if (!Array.isArray(obj.items)) fail("the plan has no course list");
    const slots = new Set([UNASSIGNED, ...ctx.program.terms.map(t => t.slot)]);
    const cats = new Set(ctx.program.categories.map(c => c.id));
    const seen = new Set();
    for (const it of obj.items) {
      if (!it || typeof it.id !== "string" || seen.has(it.id)) fail("course ids must be unique");
      seen.add(it.id);
      if (!slots.has(it.slot)) fail(`unknown term: ${it.slot}`);
      if (it.course == null && !(it.custom && typeof it.custom === "object")) fail("a course has no number or details");
      if (it.course != null && typeof it.course !== "string") fail("a course number isn't text");
      if (it.units != null && typeof it.units !== "number") fail(`units for ${numberOf(it)} aren't a number`);
      if (it.category != null && !cats.has(it.category)) fail(`unknown category: ${it.category}`);
      for (const a of it.addons || []) if (!cats.has(a)) fail(`unknown category: ${a}`);
    }
    const targets = {};
    for (const [k, v] of Object.entries(obj.targets || {})) {
      if (typeof v !== "number") fail(`the target for ${k} isn't a number`);
      if (ctx.program.requirements.some(r => r.id === k)) targets[k] = v;
    }
    return { v: V, program: obj.program, gradYear: obj.gradYear, ...(obj.yearChosen ? { yearChosen: true } : {}),
      items: obj.items, removedBase: Array.isArray(obj.removedBase) ? obj.removedBase : [], targets };
  }

  // ---- v1 (lgo-dp.plan + lgo-dp.reqs, and v1 export files) -> v2 ----
  // v1 saved whole items with calendar terms (always Summer 2026 - Spring 2028; older saves used
  // "1st Summer" ... "2nd Spring") and category tags; base items had ids p0, p1, ... in base_plan
  // order. Returns {state, notes}: notes say what the student should know.
  const V1_GRAD_YEAR = 2028;
  function migrateV1(ctx, { plan, reqs }) {
    const program = ctx.program;
    const state = newState(program, V1_GRAD_YEAR);   // no saved plan = the base plan
    const notes = [];
    const slotOf = Object.fromEntries(Object.entries(slotLabels(program, V1_GRAD_YEAR)).map(([s, l]) => [l, s]));
    const toSlot = term => {
      if (term === E.UNASSIGNED) return UNASSIGNED;
      const old = /^(1st|2nd) (\w+)$/.exec(term || "");
      const slot = old ? `Y${old[1][0]} ${old[2]}` : slotOf[term];
      return program.terms.some(t => t.slot === slot) ? slot : null;
    };
    const addonIds = new Set(program.categories.filter(c => c.kind === "addon").map(c => c.id));
    const known = new Set(program.categories.map(c => c.id));
    const usedBase = new Set(), usedIds = new Set();

    if (Array.isArray(plan)) state.items = [];
    for (const old of Array.isArray(plan) ? plan : []) {
      if (!old || !old.number) continue;
      let slot = toSlot(old.term);
      if (slot === null) { notes.push(`${old.number} was in an unknown term (${old.term}); it's now unassigned.`); slot = UNASSIGNED; }
      // Base items: by position id first, then by number and term.
      let b = null;
      if (old.base) {
        const m = /^p(\d+)$/.exec(old.id || "");
        const byPos = m ? program.base_plan[+m[1]] : null;
        b = byPos && byPos.course === old.number && !usedBase.has(byPos.id) ? byPos
          : program.base_plan.find(x => x.course === old.number && !usedBase.has(x.id) && (x.slot || UNASSIGNED) === slot)
          || program.base_plan.find(x => x.course === old.number && !usedBase.has(x.id)) || null;
      }
      let it;
      if (b) { usedBase.add(b.id); it = { id: b.id, course: b.course, slot, base: b.id }; }
      else if (ctx.course(old.number)) it = { id: old.id, course: old.number, slot };
      else it = { id: old.id, course: null, slot, custom: { number: old.number, title: old.title || old.number, units: +old.units || 0 } };
      if (!it.id || usedIds.has(it.id)) it.id = newId();
      usedIds.add(it.id);
      state.items.push(it);

      const tags = (old.tags || []).filter(t => known.has(t));
      const cats = tags.filter(t => !addonIds.has(t)), addons = tags.filter(t => addonIds.has(t));
      if (!b) {
        setCategory(ctx, state, it.id, cats[0] || null);
        if (addons.length) it.addons = addons;
        if (cats.length > 1)
          notes.push(`${old.number} counted toward ${cats.join(" and ")}. A course now counts toward one category, so it counts toward ${cats[0]}; change it with its category menu.`);
      }
      if (!it.custom && old.units != null) setUnits(ctx, state, it.id, +old.units || 0);
      if (old.audit) it.audit = true;
    }
    // Base courses the student had removed (v1 "remove" or "Start blank").
    if (Array.isArray(plan))
      for (const b of program.base_plan) if (!usedBase.has(b.id) && !b.required) state.removedBase.push(b.id);
    // Targets: v1 saved whole requirement copies, later [{key, target}]; keep edited ones only.
    for (const r of Array.isArray(reqs) ? reqs : []) {
      const req = r && program.requirements.find(x => x.id === r.key);
      if (req && r.target != null) setTarget(program, state, req.id, +r.target);
    }
    return { state, notes };
  }

  // An imported file: a v2 plan, or a v1 export ({plan, reqs}).
  function fromFile(ctx, obj) {
    if (obj && obj.v === V) return { state: validate(ctx, obj), notes: [] };
    if (obj && Array.isArray(obj.plan)) return migrateV1(ctx, obj);
    throw new Error("this isn't a plan export");
  }

  return { UNASSIGNED, slotLabels, gradYearOptions, newState, toItems, setUnits, setCategory, toggleAddon, setAudit, moveTo,
    addCourse, addCustom, removeItem, startBlank, setTarget, reconcile, validate, migrateV1, fromFile };
})();

if (typeof module !== "undefined") module.exports = State;
