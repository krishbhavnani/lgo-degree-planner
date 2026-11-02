// ===========================================================================
// PLAN VIEW — schedule sandbox + degree-requirement tracker
// ===========================================================================
// The degree rules come from programs/*.json (loaded as programs.js): the major, plus the shared
// LGO file it extends. The student's plan is saved as State v2 (app/state.js).
const MAJOR=Object.values(window.PROGRAMS||{}).find(p=>p.extends);
const PROGRAM=Engine.resolve(window.PROGRAMS[MAJOR.extends],MAJOR);
const CATEGORIES=PROGRAM.categories.filter(c=>c.kind!=="addon");   // one per course
const ADDONS=PROGRAM.categories.filter(c=>c.kind==="addon");        // on top of the category
const ADDON_IDS=new Set(ADDONS.map(c=>c.id));
const TAGCLASS=Object.fromEntries(PROGRAM.categories.map(c=>[c.id,c.style?"t-"+c.style:""]));
const courseByNum={}; COURSES.forEach(c=>{courseByNum[c.number]=c;});
// What the rules read about a course.
const courseInfo=n=>{const c=courseByNum[n]||{};return {aags:c.aags,design:c.design_approved,department:c.department};};
const CTX={program:PROGRAM,course:n=>courseByNum[n]||null};
const PLS={state:"lgo-dp.state",unreadable:"lgo-dp.state-unreadable",view:"lgo-dp.view",
  v1plan:"lgo-dp.plan",v1reqs:"lgo-dp.reqs",v1backup:"lgo-dp.v1-backup"};
// Graduation years on offer today; a new plan starts as the class now in its first year.
const GRAD_YEARS=State.gradYearOptions(PROGRAM,new Date());
const DEFAULT_GRAD_YEAR=GRAD_YEARS[GRAD_YEARS.length-2];

let notices=[];  // shown once above the term grid
function loadPlanState(){
  const saved=load(PLS.state,null);
  if(saved){
    try{ const s=State.validate(CTX,saved); notices.push(...State.reconcile(CTX,s)); return s; }
    catch(e){ save(PLS.unreadable,saved);
      notices.push(`Your saved plan couldn't be read (${e.message}), so the planner started again from the LGO base plan. The old copy is kept in this browser.`); }
  }
  // A plan saved by the earlier version: convert it once, keep the original as a backup.
  const v1={plan:load(PLS.v1plan,null),reqs:load(PLS.v1reqs,null)};
  if(v1.plan||v1.reqs){
    const m=State.migrateV1(CTX,v1);
    notices.push(...m.notes,...State.reconcile(CTX,m.state));
    save(PLS.v1backup,v1); save(PLS.state,m.state);
    localStorage.removeItem(PLS.v1plan); localStorage.removeItem(PLS.v1reqs);
    return m.state;
  }
  return State.newState(PROGRAM,DEFAULT_GRAD_YEAR);
}
let STATE=loadPlanState();
// Derived from STATE on every change: the items the grid and engine use, and the term names.
let planItems=[], PLAN_TERMS=[], SLOT_OF={};
function refreshItems(){
  const labels=State.slotLabels(PROGRAM,STATE.gradYear);
  PLAN_TERMS=PROGRAM.terms.map(t=>labels[t.slot]);
  SLOT_OF=Object.fromEntries(Object.entries(labels).map(([slot,label])=>[label,slot]));
  SLOT_OF[Engine.UNASSIGNED]=State.UNASSIGNED;
  planItems=State.toItems(CTX,STATE);
}
function planSave(){save(PLS.state,STATE); refreshItems();}
if(notices.length) save(PLS.state,STATE);
refreshItems();
let hideAudit=false;

// From Browse or the add-course box. A title or units means a course typed in by hand.
function addPlanItem(number,title,units,term){
  const slot=SLOT_OF[term||Engine.UNASSIGNED];
  if(title!=null||units!=null) State.addCustom(CTX,STATE,{number,title,units},slot);
  else State.addCourse(STATE,number,slot);
  planSave(); renderPlan(); track("course-added");
}

function evaluatePlan(){return Engine.evaluate(PROGRAM,planItems,courseInfo,STATE.targets);}
function renderReqPanel(res=evaluatePlan()){
  const groups={}; res.requirements.forEach(b=>{(groups[b.group]=groups[b.group]||[]).push(b);});
  let h="";
  for(const g of Object.keys(groups)){
    h+=`<div class="reqgroup"><h4>${esc(g)}</h4>`;
    for(const b of groups[g]){
      const met=b.met, n=b.value;
      let label, pct;
      if(b.type==="from_set"){ label=`${n} / ${b.target}u · ${b.courses}/${b.min_courses} courses`; pct=Math.min(100,100*n/b.target);}
      else if(b.type==="count"){ label=`${n} / ${b.target}`; pct=Math.min(100,100*n/(b.target||1));}
      else { label=`${n} / ${b.target}u`; pct=Math.min(100,100*n/(b.target||1));}
      const info=b.counted&&b.counted.length?["Counted: "+b.counted.join(", ")]:[];
      if(b.headline){
        h+=`<div class="reqtotal ${met?'met':''}">
            <span class="rt-l">${esc(b.label)}</span>
            <span class="rt-v">${met?'✓ ':''}${n}<span class="rt-t">/ ${b.target}u</span></span></div>`;
        continue;
      }
      h+=`<div class="reqrow ${met?'met':''}">
        <div class="rl"><span class="rn">${esc(b.label)}</span>
        <span class="rv ${met?'':'short'}">${met?'✓ ':''}${label}</span></div>
        <div class="bar ${met?'done':''}"><i style="width:${pct}%"></i></div>
        ${info.map(n=>`<div class="hint" style="margin-top:3px">${esc(n)}</div>`).join("")}
        ${b.notes.map(n=>`<div class="hint" style="margin-top:3px">⚠ ${esc(n)}</div>`).join("")}</div>`;
    }
    h+="</div>";
  }
  document.getElementById("reqpanel").innerHTML=h;
}

// ---- term grid ----
function renderTerms(res=evaluatePlan()){
  const grid=document.getElementById("termgrid");
  const order=["Unassigned",...PLAN_TERMS];
  let h="";
  for(const term of order){
    const items=planItems.filter(it=>it.term===term && (!hideAudit||!it.audit));
    items.sort((a,b)=>(a.audit-b.audit) || ((+b.units||0)-(+a.units||0)));  // size desc; audits last
    if(term==="Unassigned" && items.length===0) continue;
    const tot=(res.terms[term]||{units:0}).units;  // every unit counts
    const limit=PROGRAM.term_unit_limit, cap=term==="Unassigned"?Infinity:limit;
    h+=`<div class="term ${term==='Unassigned'?'unassigned':''}"><div class="term-h">${esc(term)}${term==='Unassigned'?' <span class="hint" style="font-weight:400">· not counted toward requirements</span>':''}
        <span class="tu ${tot>cap?'over':''}" ${tot>cap?`title="Over the limit of ${limit} units per term"`:''}>${term==='Unassigned'?'':`${tot}u${tot>cap?` · over ${limit}u limit`:''}`}</span></div><div class="term-body">`;
    for(const it of items){
      const req=!!it.required, lockTags=!!(it.base||it.required);  // base-plan categories are fixed
      const cat=(it.tags||[]).find(t=>!ADDON_IDS.has(t))||"";
      const tagChips=lockTags?(it.tags||[]).map(t=>`<span class="tagchip ${TAGCLASS[t]||''}">${esc(t)}</span>`).join(""):
        `<select class="catsel ${TAGCLASS[cat]||''}" data-act="cat" data-id="${it.id}" title="Which requirement this course counts toward"><option value="">no category</option>${CATEGORIES.map(c=>`<option ${c.id===cat?'selected':''}>${esc(c.id)}</option>`).join("")}</select>`+
        ADDONS.map(a=>{const on=(it.tags||[]).includes(a.id);
          return `<span class="tagchip ${TAGCLASS[a.id]||''} ${on?'':'off'}" data-act="addon" data-id="${it.id}" data-tag="${esc(a.id)}" title="${on?'click to remove':'click to add'}">${on?'':'+ '}${esc(a.id)}${on?' ✕':''}</span>`;}).join("");
      const termOpts=req?["Unassigned",...(it.allowedTerms||[])]:order;
      const termsel=`<select data-act="term" data-id="${it.id}">${termOpts.map(t=>`<option ${t===it.term?'selected':''}>${esc(t)}</option>`).join("")}</select>`;
      h+=`<div class="pitem ${it.audit?'audit':''}">
        <div class="pi-top"><span class="pi-num">${esc(it.number)}</span>
          ${(courseByNum[it.number]||{}).design_approved?`<span class="dz" title="Pre-approved design class">🎨</span>`:''}
          <span class="pi-title" title="${esc(it.title)}">${esc(it.title)}</span>
          <input class="pi-u" type="number" min="0" value="${it.units}" data-act="units" data-id="${it.id}">
          ${req?'':`<span class="pi-x" data-act="rm" data-id="${it.id}" title="remove">✕</span>`}</div>
        <div class="pi-tags">${tagChips}</div>
        <div class="pi-controls">${termsel}
          ${req?'':`<label><input type="checkbox" data-act="audit" data-id="${it.id}" ${it.audit?'checked':''}> audit</label>`}</div>
      </div>`;
    }
    h+="</div></div>";
  }
  grid.innerHTML=h;
}
function renderPlanSummary(res=evaluatePlan()){
  document.getElementById("plan-summary").innerHTML=`<b>${res.scheduled}</b> courses scheduled`+
    res.summary.map(s=>` · ${esc(s.label)} <b>${s.value}</b>/${s.target}u`).join("");
}
function renderNotice(){
  const box=document.getElementById("plan-notice");
  box.hidden=!notices.length;
  box.innerHTML=notices.map(n=>`<div>${esc(n)}</div>`).join("")+`<button class="notice-x" title="dismiss">✕</button>`;
}
// "Graduating: [2028]  Starts Summer 2026 · Graduates Spring 2028". A saved year outside today's
// window (an older plan) stays in the list.
function yearOptions(){
  const ys=[...new Set([...GRAD_YEARS,STATE.gradYear])].sort((a,b)=>a-b);
  return ys.map(y=>`<option ${y===STATE.gradYear?'selected':''}>${y}</option>`).join("");
}
const yearSpan=()=>`Starts ${PLAN_TERMS[0]} · Graduates ${PLAN_TERMS[PLAN_TERMS.length-1]}`;
function renderGradYear(){
  document.getElementById("grad-year").innerHTML=yearOptions();
  document.getElementById("grad-span").textContent=yearSpan();
}
// Counted (gradyear/<year>) when the question is answered or Plan opens, not on every change.
function setGradYear(year){
  STATE.gradYear=year; STATE.yearChosen=true; planSave(); renderPlan();
}
document.getElementById("grad-year").addEventListener("change",e=>setGradYear(+e.target.value));
// The first time someone opens Plan, ask which class they're in (once; the header picker stays).
function askGradYearOnce(){
  if(STATE.yearChosen){ track("gradyear/"+STATE.gradYear); return; }
  STATE.yearChosen=true; planSave();
  openModal("Which class are you in?",
    `<div class="setrow">Graduating: <select id="ask-year">${yearOptions()}</select></div>
     <div class="hint" id="ask-span" style="margin:4px 0 12px">${esc(yearSpan())}</div>
     <div class="hint" style="margin-bottom:12px">Every term in your plan follows this year. You can change it any time from the Plan header.</div>
     <button class="primary" id="ask-done">Done</button>`);
  document.getElementById("ask-year").addEventListener("change",e=>{
    setGradYear(+e.target.value); document.getElementById("ask-span").textContent=yearSpan();});
  document.getElementById("ask-done").addEventListener("click",()=>{track("gradyear/"+STATE.gradYear); closeModal();});
}
function renderPlan(){ const res=evaluatePlan(); renderGradYear(); renderReqPanel(res); renderTerms(res); renderPlanSummary(res); renderNotice(); }
document.getElementById("plan-notice").addEventListener("click",e=>{if(e.target.closest(".notice-x")){notices=[]; renderNotice();}});

// ---- plan event handling ----
function itemById(id){return planItems.find(x=>x.id===id);}
document.getElementById("termgrid").addEventListener("change",e=>{
  const t=e.target, id=t.getAttribute("data-id"), act=t.getAttribute("data-act"); if(!id)return;
  const it=itemById(id); if(!it)return;
  if(act==="term"){ if(!State.moveTo(CTX,STATE,id,SLOT_OF[t.value])) return; }
  else if(act==="cat"){ if(it.base||it.required) return; State.setCategory(CTX,STATE,id,t.value||null); }   // category locked
  else if(it.required && act!=="units") return;
  else if(act==="units"){ State.setUnits(CTX,STATE,id,+t.value||0); }
  else if(act==="audit"){ State.setAudit(STATE,id,t.checked); }
  else return;
  planSave(); renderPlan();
});
document.getElementById("termgrid").addEventListener("click",e=>{
  const t=e.target.closest("[data-act]"); if(!t)return;
  const act=t.getAttribute("data-act"), id=t.getAttribute("data-id"), it=itemById(id); if(!it)return;
  if(act==="rm"){ if(!State.removeItem(CTX,STATE,id)) return; }
  else if(act==="addon"){ if(it.base||it.required) return; State.toggleAddon(STATE,id,t.getAttribute("data-tag")); }
  else return;
  planSave(); renderPlan();
});
document.getElementById("hide-audit").addEventListener("change",e=>{hideAudit=e.target.checked; renderTerms();});

// ---- modal (add course + settings) ----
const modal=document.getElementById("modal");
function openModal(title,bodyHTML){document.getElementById("modal-title").textContent=title;document.getElementById("modal-body").innerHTML=bodyHTML;modal.hidden=false;}
function closeModal(){modal.hidden=true;}
document.getElementById("modal-x").addEventListener("click",closeModal);
modal.addEventListener("click",e=>{if(e.target===modal)closeModal();});

function addCourseModal(){
  const termOpts=["Unassigned",...PLAN_TERMS].map(t=>`<option>${esc(t)}</option>`).join("");
  openModal("Add course to plan",
    `<div class="setrow">Add to term: <select id="add-term">${termOpts}</select></div>
     <input id="add-search" placeholder="Search catalog by number or title…" style="width:100%;padding:7px;border:1px solid var(--line);border-radius:7px;margin:6px 0">
     <div id="add-results" style="max-height:300px;overflow:auto;border:1px solid var(--line);border-radius:7px"></div>
     <div class="hint" style="margin-top:10px">Not in the catalog? Add a custom course:</div>
     <div class="setrow"><input id="cu-num" placeholder="Number (e.g. 15.S99)" style="width:120px;padding:4px;border:1px solid var(--line);border-radius:6px">
       <input id="cu-title" placeholder="Title" style="flex:1;padding:4px;border:1px solid var(--line);border-radius:6px">
       <input id="cu-u" type="number" placeholder="units" style="width:60px;padding:4px;border:1px solid var(--line);border-radius:6px">
       <button id="cu-add">Add</button></div>`);
  const resBox=document.getElementById("add-results");
  const doSearch=()=>{
    const q=document.getElementById("add-search").value.trim().toLowerCase();
    if(!q){resBox.innerHTML='<div class="hint" style="padding:8px">Type to search '+COURSES.length+' courses…</div>';return;}
    const inPlan=new Set(planItems.map(it=>it.number));
    const hits=COURSES.filter(c=>(c.number+" "+c.title).toLowerCase().includes(q)).slice(0,40);
    resBox.innerHTML=hits.map(c=>{const added=inPlan.has(c.number);
      return `<div class="addresult ${added?'added':''}" data-add="${added?'':c.number}"><b>${esc(c.number)}</b> ${esc(c.title)}
      <span class="hint">${c.units_total!=null?c.units_total+'u':''}</span>${added?'<span class="ar-in">✓ in plan</span>':'<span class="ar-add">＋ add</span>'}</div>`;}).join("")||'<div class="hint" style="padding:8px">no matches</div>';
  };
  document.getElementById("add-search").addEventListener("input",doSearch); doSearch();
  resBox.addEventListener("click",e=>{const r=e.target.closest("[data-add]");if(!r)return;
    const num=r.getAttribute("data-add"); if(!num)return; const term=document.getElementById("add-term").value;
    addPlanItem(num,null,null,term); doSearch();});
  document.getElementById("cu-add").addEventListener("click",()=>{
    const num=document.getElementById("cu-num").value.trim(); if(!num)return;
    addPlanItem(num,document.getElementById("cu-title").value.trim()||num,+document.getElementById("cu-u").value||0,document.getElementById("add-term").value);
    closeModal();});
}
function settingsModal(){
  const rows=PROGRAM.requirements.map(b=>`<div class="setrow"><span class="sn">${esc(b.label)} <span class="hint">(${esc(b.group)}, counts: ${b.pool.join(', ')||'—'})</span></span>
    <input type="number" data-req="${esc(b.id)}" value="${STATE.targets[b.id]??Engine.defaultTarget(b)}"> ${b.type==='count'?'courses':'units'}</div>`).join("");
  openModal("Requirement settings (editable)",
    `<div class="hint" style="margin-bottom:8px">Adjust the target for any requirement. These are your editable model of the LGO degree rules.</div>
     ${rows}<div style="margin-top:12px"><button id="req-reset">↺ Reset requirements to LGO defaults</button></div>`);
  document.getElementById("modal-body").addEventListener("change",e=>{
    const id=e.target.getAttribute("data-req"); if(id==null)return;
    State.setTarget(PROGRAM,STATE,id,+e.target.value||0); planSave(); renderPlan();
  });
  document.getElementById("req-reset").addEventListener("click",()=>{
    STATE.targets={}; planSave(); renderPlan(); settingsModal();
  });
}
document.getElementById("plan-add").addEventListener("click",addCourseModal);
document.getElementById("plan-settings").addEventListener("click",settingsModal);
document.getElementById("plan-export").addEventListener("click",()=>{
  const blob=new Blob([JSON.stringify(STATE,null,2)],{type:"application/json"});
  const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="lgo_plan.json";a.click();
});
document.getElementById("plan-import").addEventListener("click",()=>{
  const inp=document.createElement("input");inp.type="file";inp.accept=".json";
  inp.onchange=()=>{const f=inp.files[0];if(!f)return;const r=new FileReader();
    r.onload=()=>{let d;
      try{d=JSON.parse(r.result);}catch(err){alert("Could not read that file: it isn't a plan export (JSON).");return;}
      try{const m=State.fromFile(CTX,d); notices=[...m.notes,...State.reconcile(CTX,m.state)]; STATE=m.state; planSave(); renderPlan();}
      catch(err){alert("Could not import that plan: "+err.message+".");}};
    r.readAsText(f);};
  inp.click();
});
document.getElementById("plan-reset").addEventListener("click",()=>{
  if(!confirm("Reset the schedule AND requirements to the LGO sample defaults? Your current plan will be lost."))return;
  const year=STATE.gradYear, chosen=STATE.yearChosen;
  STATE=State.newState(PROGRAM,year); if(chosen) STATE.yearChosen=true;
  planSave(); renderPlan();
});

document.getElementById("plan-blank").addEventListener("click",()=>{
  if(!confirm("Clear your schedule and start from a blank plan? Your current plan will be lost (requirement settings stay; required courses go back to Unassigned)."))return;
  State.startBlank(CTX,STATE); planSave(); renderPlan();
});
