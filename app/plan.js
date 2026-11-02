// ===========================================================================
// PLAN VIEW — schedule sandbox + degree-requirement tracker
// ===========================================================================
// The degree rules come from programs/*.json (loaded as programs.js): the major, plus the shared
// LGO file it extends.
const MAJOR=Object.values(window.PROGRAMS||{}).find(p=>p.extends);
const PROGRAM=Engine.resolve(window.PROGRAMS[MAJOR.extends],MAJOR);
const START_YEAR=2026;  // first summer of the plan (a grad-year picker replaces this in Phase 2a)
const PLAN_TERMS=Engine.termLabels(PROGRAM,START_YEAR);
const TAGS=PROGRAM.categories.map(c=>c.id);
const TAGCLASS=Object.fromEntries(PROGRAM.categories.map(c=>[c.id,c.style?"t-"+c.style:""]));
const courseByNum={}; COURSES.forEach(c=>{courseByNum[c.number]=c;});
// What the rules read about a course.
const courseInfo=n=>{const c=courseByNum[n]||{};return {aags:c.aags,design:c.design_approved,department:c.department};};
// The LGO base plan (required courses only); students add their own electives.
const PLAN_DEFAULT=Engine.basePlan(PROGRAM,START_YEAR);

const PLS={plan:"lgo-dp.plan",reqs:"lgo-dp.reqs",view:"lgo-dp.view"};
const newId=()=>"p"+Date.now().toString(36)+Math.random().toString(36).slice(2,7);
let planItems=(load(PLS.plan,null)||PLAN_DEFAULT).map(x=>({...x,tags:[...x.tags],term:migTerm(x.term)}));
// Repair any historical duplicate ids (older builds reused a counter that reset on reload).
(()=>{const seen=new Set();planItems.forEach(it=>{if(!it.id||seen.has(it.id))it.id=newId();seen.add(it.id);});})();
// Requirement settings hold only the targets the user changed, by requirement id. Older saves
// stored whole requirement copies ({key, target, tags, ...}); only key and target are read.
function loadTargets(saved){
  const t={};
  (Array.isArray(saved)?saved:[]).forEach(r=>{const req=PROGRAM.requirements.find(x=>x.id===r.key);
    if(req && r.target!=null && +r.target!==Engine.defaultTarget(req)) t[r.key]=+r.target;});
  return t;
}
let targets=loadTargets(load(PLS.reqs,null));
let hideAudit=false;
function planSave(){save(PLS.plan,planItems);}
function savedTargets(){return Object.entries(targets).map(([key,target])=>({key,target}));}
function reqSave(){save(PLS.reqs,savedTargets());}

function addPlanItem(number,title,units,term){
  const c=courseByNum[number];
  planItems.push({id:newId(),number,title:title||(c?c.title:number),
    units:units!=null?units:(c&&c.units_total!=null?c.units_total:0),
    tags:Engine.classify(PROGRAM,number,courseInfo),term:term||"Unassigned",audit:false});
  planSave(); renderPlan(); track("course-added");
}

function evaluatePlan(){return Engine.evaluate(PROGRAM,planItems,courseInfo,targets);}
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
      const req=!!it.required, lockTags=!!(it.base||it.required);  // base-plan designations are fixed
      const tagChips=(it.tags||[]).map(t=>lockTags?`<span class="tagchip ${TAGCLASS[t]||''}">${esc(t)}</span>`
          :`<span class="tagchip ${TAGCLASS[t]||''}" data-act="rmtag" data-id="${it.id}" data-tag="${esc(t)}" title="click to remove">${esc(t)} ✕</span>`).join("");
      const avail=TAGS.filter(t=>!(it.tags||[]).includes(t));
      const addsel=lockTags?'':`<select data-act="addtag" data-id="${it.id}"><option value="">+tag</option>${avail.map(t=>`<option>${esc(t)}</option>`).join("")}</select>`;
      const termOpts=req?["Unassigned",...(it.allowedTerms||[])]:order;
      const termsel=`<select data-act="term" data-id="${it.id}">${termOpts.map(t=>`<option ${t===it.term?'selected':''}>${esc(t)}</option>`).join("")}</select>`;
      h+=`<div class="pitem ${it.audit?'audit':''}">
        <div class="pi-top"><span class="pi-num">${esc(it.number)}</span>
          ${(courseByNum[it.number]||{}).design_approved?`<span class="dz" title="Pre-approved design class">🎨</span>`:''}
          <span class="pi-title" title="${esc(it.title)}">${esc(it.title)}</span>
          <input class="pi-u" type="number" min="0" value="${it.units}" data-act="units" data-id="${it.id}">
          ${req?'':`<span class="pi-x" data-act="rm" data-id="${it.id}" title="remove">✕</span>`}</div>
        <div class="pi-tags">${tagChips}${addsel}</div>
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
function renderPlan(){ const res=evaluatePlan(); renderReqPanel(res); renderTerms(res); renderPlanSummary(res); }

// ---- plan event handling ----
function itemById(id){return planItems.find(x=>x.id===id);}
document.getElementById("termgrid").addEventListener("change",e=>{
  const t=e.target, id=t.getAttribute("data-id"), act=t.getAttribute("data-act"); if(!id)return;
  const it=itemById(id); if(!it)return;
  if(act==="term"){ if(it.required && t.value!=="Unassigned" && !(it.allowedTerms||[]).includes(t.value)) return; it.term=t.value; }
  else if(act==="addtag" && (it.base||it.required)) return;   // designation locked
  else if(it.required && act!=="units") return;
  else if(act==="units"){ it.units=+t.value||0; }
  else if(act==="audit"){ it.audit=t.checked; }
  else if(act==="addtag"){ if(t.value && !it.tags.includes(t.value)) it.tags.push(t.value); }
  else return;
  planSave(); renderPlan();
});
document.getElementById("termgrid").addEventListener("click",e=>{
  const t=e.target.closest("[data-act]"); if(!t)return;
  const act=t.getAttribute("data-act"), id=t.getAttribute("data-id"), it=itemById(id); if(!it)return;
  if(act==="rm"){ if(it.required) return; planItems=planItems.filter(x=>x.id!==id); }
  else if(act==="rmtag" && (it.base||it.required)) return;   // designation locked
  else if(act==="rmtag"){ const tg=t.getAttribute("data-tag"); it.tags=it.tags.filter(x=>x!==tg); }
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
    <input type="number" data-req="${esc(b.id)}" value="${targets[b.id]??Engine.defaultTarget(b)}"> ${b.type==='count'?'courses':'units'}</div>`).join("");
  openModal("Requirement settings (editable)",
    `<div class="hint" style="margin-bottom:8px">Adjust the target for any requirement. These are your editable model of the LGO degree rules.</div>
     ${rows}<div style="margin-top:12px"><button id="req-reset">↺ Reset requirements to LGO defaults</button></div>`);
  document.getElementById("modal-body").addEventListener("change",e=>{
    const id=e.target.getAttribute("data-req"); if(id==null)return;
    const req=PROGRAM.requirements.find(x=>x.id===id), v=+e.target.value||0;
    if(v===Engine.defaultTarget(req)) delete targets[id]; else targets[id]=v;
    reqSave(); renderPlan();
  });
  document.getElementById("req-reset").addEventListener("click",()=>{
    targets={}; reqSave(); renderPlan(); settingsModal();
  });
}
document.getElementById("plan-add").addEventListener("click",addCourseModal);
document.getElementById("plan-settings").addEventListener("click",settingsModal);
document.getElementById("plan-export").addEventListener("click",()=>{
  const blob=new Blob([JSON.stringify({plan:planItems,reqs:savedTargets()},null,2)],{type:"application/json"});
  const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="lgo_plan.json";a.click();
});
document.getElementById("plan-import").addEventListener("click",()=>{
  const inp=document.createElement("input");inp.type="file";inp.accept=".json";
  inp.onchange=()=>{const f=inp.files[0];if(!f)return;const r=new FileReader();
    r.onload=()=>{try{const d=JSON.parse(r.result); if(d.plan)planItems=d.plan; if(d.reqs)targets=loadTargets(d.reqs); planSave();reqSave();renderPlan();}catch(err){alert("Could not parse JSON");}};
    r.readAsText(f);};
  inp.click();
});
document.getElementById("plan-reset").addEventListener("click",()=>{
  if(!confirm("Reset the schedule AND requirements to the LGO sample defaults? Your current plan will be lost."))return;
  planItems=PLAN_DEFAULT.map(x=>({...x,tags:[...x.tags]})); targets={};
  planSave();reqSave();renderPlan();
});

document.getElementById("plan-blank").addEventListener("click",()=>{
  if(!confirm("Clear your schedule and start from a blank plan? Your current plan will be lost (requirement settings stay; required courses go back to Unassigned)."))return;
  planItems=planItems.filter(it=>it.required).map(it=>({...it,term:"Unassigned"})); planSave(); renderPlan();
});
