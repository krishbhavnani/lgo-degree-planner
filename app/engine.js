// Requirement math. Reads planItems, reqs and courseByNum from plan.js (until Phase 1 step 4).
// ---- requirement computation ----
// Only scheduled courses count: audits and anything still in "Unassigned" don't.
const TERM_LIMIT=72;  // units per term (per Krish, 2026-10-27)
const counts=it=>!it.audit && it.term!=="Unassigned";
const fmtTerms=ts=>ts.length>1?ts.slice(0,-1).join(", ")+" or "+ts[ts.length-1]:ts[0];
// LGO EECS handbook: 6.C51 (6u) taken with exactly one 6u co-req module counts as ONE 12u AAGS course.
const C51_MODULES=["1.C51","2.C51","3.C51","6.C511","7.C51","10.C51","11.C51","15.C51","20.C51","22.C51","SCM.C51"];
// Allocate engineering courses: AAGS-approved courses fill the AAGS core first (largest first)
// until it has its minimum courses AND units; every other engineering course — including extra
// AAGS courses — counts as an eng elective. Each course counts toward exactly one bucket.
function engAllocation(){
  const aagsB=reqs.find(x=>x.type==="aags");
  const tags=aagsB?aagsB.tags:["Eng Elective","LGO Required Eng"];
  const target=aagsB?aagsB.target:36, minC=aagsB?(aagsB.minCourses||3):3;
  const items=planItems.filter(it=>counts(it) && (it.tags||[]).some(t=>tags.includes(t)));
  const isAags=it=>((courseByNum[it.number]||{}).aags||"").startsWith("Approved");
  const notes=[], cands=[];
  const c51=items.find(it=>it.number==="6.C51");
  const mods=items.filter(it=>C51_MODULES.includes(it.number));
  if(c51){
    const mod=mods[0];
    cands.push({ids:[c51.id].concat(mod?[mod.id]:[]), label:mod?"6.C51+"+mod.number:"6.C51",
                units:(+c51.units||0)+(mod?(+mod.units||0):0)});
    if(!mod && (+c51.units||0)<12) notes.push("6.C51 needs a 6u co-req module (e.g. 15.C51 or SCM.C51) to count as a full 12u AAGS course.");
    if(mods.length>1) notes.push("Only one co-req module pairs with 6.C51; "+mods.slice(1).map(m=>m.number).join(", ")+" counted as eng electives instead.");
  } else if(mods.length){
    notes.push(mods.map(m=>m.number).join(", ")+" only counts toward AAGS when paired with 6.C51.");
  }
  for(const it of items){
    if(it.number==="6.C51" || C51_MODULES.includes(it.number)) continue;
    if((it.tags||[]).includes("LGO Required Eng")) continue;   // LGO-required eng has its own bucket
    if(isAags(it)) cands.push({ids:[it.id], label:it.number, units:+it.units||0});
  }
  cands.sort((a,b)=>b.units-a.units);
  const core=[]; let coreUnits=0;
  for(const c of cands){ if(core.length>=minC && coreUnits>=target) break; core.push(c); coreUnits+=c.units; }
  const used=new Set(); core.forEach(c=>c.ids.forEach(id=>used.add(id)));
  return {coreUnits, coreCourses:core.length, coreLabels:core.map(c=>c.label), used, notes};
}
function reqEarned(b){
  if(b.type==="aags"){
    const a=engAllocation();
    return {n:a.coreUnits, courses:a.coreCourses, notes:a.notes,
            info:a.coreLabels.length?["Counted: "+a.coreLabels.join(", ")]:[]};
  }
  if(b.type==="elec_beyond_aags"){
    const a=engAllocation();
    const elec=planItems.filter(it=>counts(it) && !a.used.has(it.id) && (it.tags||[]).some(t=>b.tags.includes(t)));
    return {n:elec.reduce((s,it)=>s+(+it.units||0),0), courses:elec.length,
            info:elec.length?["Counted: "+elec.map(it=>it.number).join(", ")]:[]};
  }
  // Design is satisfied by any planned pre-approved design course OR a manual "LGO Design" tag.
  if(b.key==="design"){
    const items=planItems.filter(it=>counts(it) && ((it.tags||[]).includes("LGO Design") ||
        (courseByNum[it.number]||{}).design_approved==="approved"));
    return {n:items.length, courses:items.length};
  }
  const items=planItems.filter(it=>counts(it) && (it.tags||[]).some(t=>b.tags.includes(t)));
  if(b.type==="count") return {n:items.length, courses:items.length};
  // flag required courses that are still unscheduled (on the specific bucket, not the totals)
  const pending=b.headline?[]:planItems.filter(it=>it.required && it.term==="Unassigned" && (it.tags||[]).some(t=>b.tags.includes(t)));
  if(pending.length) return {n:items.reduce((s,it)=>s+(+it.units||0),0), courses:items.length,
      notes:pending.map(it=>`${it.number} (${it.units}u) is required — schedule it in ${fmtTerms(it.allowedTerms||[])}.`)};
  return {n:items.reduce((s,it)=>s+(+it.units||0),0), courses:items.length};
}
