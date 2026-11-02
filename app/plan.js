// ===========================================================================
// PLAN VIEW — schedule sandbox + degree-requirement tracker
// ===========================================================================
const PLAN_TERMS=["Summer 2026","Fall 2026","IAP 2027","Spring 2027","Summer 2027","Fall 2027","IAP 2028","Spring 2028"];
const TAGS=["MBA Core","LGO Required MBA","MBA Elective","LGO Required Eng","Eng Elective","Thesis","Python","LGO Design"];
const TAGCLASS={"MBA Core":"t-core","LGO Required MBA":"t-lgo","MBA Elective":"t-elec","LGO Required Eng":"t-lgo","Eng Elective":"t-elec","Thesis":"t-thesis","Python":"t-python","LGO Design":"t-design"};
const MBA_CORE_SET=["15.010","15.280","15.311","15.515"];
const LGO_REQ_MBA_SET=["15.316","15.317","15.761","15.876","15.S21","15.086","15.792","15.766","15.S23","15.794","15.769"];
const courseByNum={}; COURSES.forEach(c=>{courseByNum[c.number]=c;});

// Sample 2-year LGO plan (from the Excel) — the default schedule.
const PLAN_DEFAULT=[
 // Base plan = LGO-required courses only; students add their own electives.
 // Summer 2026
 ["15.316","Building & Leading Effective Teams",4,["LGO Required MBA"],"Summer 2026"],
 ["15.317","Organizational Leadership & Change",6,["LGO Required MBA"],"Summer 2026"],
 ["15.761","Intro to Operations Management",9,["LGO Required MBA"],"Summer 2026"],
 ["15.876","Lean Operations",3,["LGO Required MBA"],"Summer 2026"],
 ["15.086","Engineering Probability",3,["LGO Required MBA"],"Summer 2026"],
 ["6.S090","Python Workshop",3,["Python"],"Summer 2026"],
 ["15.066","Systems Optimization & Analysis for Ops",12,["LGO Required Eng"],"Summer 2026"],
 ["15.087","Engineering Statistics & Data Science",12,["LGO Required Eng"],"Summer 2026"],
 // Fall 2026
 ["15.010","Economic Analysis for Business Decisions",9,["MBA Core"],"Fall 2026"],
 ["15.280","Communication for Leaders",9,["MBA Core"],"Fall 2026"],
 ["15.311","Organizational Processes",9,["MBA Core"],"Fall 2026"],
 ["15.515","Financial Accounting",9,["MBA Core"],"Fall 2026"],
 ["15.792","Global Operations Leadership Seminar",2,["LGO Required MBA"],"Fall 2026"],
 ["15.002","Leadership Challenges for an Inclusive World",1,["MBA Elective"],"Fall 2026"],
 // IAP 2027
 ["15.766","Domestic Plant Trek & Partner Integration",9,["LGO Required MBA"],"IAP 2027"],
 // Spring 2027
 // Required, flexible-term courses: start in Unassigned, locked (can't be removed), and can only be
 // scheduled in their allowed terms.
 ["15.769","Operations Strategy",9,["LGO Required MBA"],"Unassigned",{required:true,allowedTerms:["Spring 2027","Spring 2028"]}],
 ["15.792","Global Operations Leadership Seminar",2,["LGO Required MBA"],"Unassigned",{required:true,allowedTerms:["Spring 2027","Spring 2028"]}],
 // Summer 2027
 ["15.794","Research Project in Operations",1,["LGO Required MBA"],"Summer 2027"],
 // Fall 2027
 ["15.794","Research Project in Operations",12,["LGO Required MBA"],"Fall 2027"],
 ["15.THG","Graduate Thesis",9,["Thesis"],"Fall 2027"],
 // Spring 2028
 ["15.THG","Graduate Thesis",15,["Thesis"],"Spring 2028"],
 ["15.317","Organizational Leadership & Change",6,["LGO Required MBA"],"Spring 2028"],
 ["15.794","Research Project in Operations",5,["LGO Required MBA"],"Spring 2028"],
].map((a,i)=>({id:"p"+i,number:a[0],title:a[1],units:a[2],tags:a[3],term:migTerm(a[4]),audit:false,base:true,...(a[5]||{})}));

const REQ_DEFAULT=[
 {key:"mba_core",group:"MBA",name:"MBA Core",target:36,type:"units",tags:["MBA Core"]},
 {key:"mba_lgo",group:"MBA",name:"LGO Required MBA",target:71,type:"units",tags:["LGO Required MBA"]},
 {key:"mba_elec",group:"MBA",name:"MBA Free Electives",target:49,type:"units",tags:["MBA Elective"]},
 {key:"mba_total",group:"MBA",name:"MBA Total Coursework",target:156,type:"units",tags:["MBA Core","LGO Required MBA","MBA Elective"],headline:true},
 {key:"aags",group:"EECS",name:"AAGS Core (3 AAGS courses)",target:36,minCourses:3,type:"aags",tags:["Eng Elective","LGO Required Eng"]},
 {key:"eng_lgo",group:"EECS",name:"LGO Required Eng",target:24,type:"units",tags:["LGO Required Eng"]},
 {key:"eng_elec",group:"EECS",name:"Eng Electives (beyond AAGS core)",target:6,type:"elec_beyond_aags",tags:["Eng Elective"]},
 {key:"eng_total",group:"EECS",name:"EECS Total Coursework",target:66,type:"units",tags:["LGO Required Eng","Eng Elective"],headline:true},
 {key:"thesis",group:"Thesis & extras",name:"SM Thesis",target:24,type:"units",tags:["Thesis"]},
 {key:"python",group:"Thesis & extras",name:"Python (6.S090)",target:1,type:"count",tags:["Python"]},
 {key:"design",group:"Thesis & extras",name:"LGO Design",target:1,type:"count",tags:["LGO Design"]},
];

const PLS={plan:"lgo-dp.plan",reqs:"lgo-dp.reqs",view:"lgo-dp.view"};
const newId=()=>"p"+Date.now().toString(36)+Math.random().toString(36).slice(2,7);
let planItems=(load(PLS.plan,null)||PLAN_DEFAULT).map(x=>({...x,tags:[...x.tags],term:migTerm(x.term)}));
// Repair any historical duplicate ids (older builds reused a counter that reset on reload).
(()=>{const seen=new Set();planItems.forEach(it=>{if(!it.id||seen.has(it.id))it.id=newId();seen.add(it.id);});})();
let reqs=load(PLS.reqs,null)||REQ_DEFAULT.map(x=>({...x,tags:[...x.tags]}));
let hideAudit=false;
function planSave(){save(PLS.plan,planItems);}
function reqSave(){save(PLS.reqs,reqs);}

function defaultTagsFor(number,dept){
  if(MBA_CORE_SET.includes(number)) return ["MBA Core"];
  if(LGO_REQ_MBA_SET.includes(number)) return ["LGO Required MBA"];
  if(number==="15.066"||number==="15.087") return ["LGO Required Eng"];
  if(number.indexOf("6.S090")===0) return ["Python"];
  if(/THG/.test(number)) return ["Thesis"];
  if(C51_MODULES.includes(number)) return ["Eng Elective"];  // pairs with 6.C51 → counts toward EECS
  const d=dept||"";
  if(d.includes("Course 15")) return ["MBA Elective"];
  if(d.includes("Course 6")||d.includes("Course 2")) return ["Eng Elective"];  // non-EECS eng also = Eng Elective
  return [];
}
function addPlanItem(number,title,units,term){
  const c=courseByNum[number];
  planItems.push({id:newId(),number,title:title||(c?c.title:number),
    units:units!=null?units:(c&&c.units_total!=null?c.units_total:0),
    tags:defaultTagsFor(number,c?c.department:""),term:term||"Unassigned",audit:false});
  planSave(); renderPlan(); track("course-added");
}

function renderReqPanel(){
  const groups={}; reqs.forEach(b=>{(groups[b.group]=groups[b.group]||[]).push(b);});
  let h="";
  for(const g of Object.keys(groups)){
    h+=`<div class="reqgroup"><h4>${esc(g)}</h4>`;
    for(const b of groups[g]){
      const e=reqEarned(b);
      let met, label, pct;
      if(b.type==="aags"){ const mc=b.minCourses||3; met=e.n>=b.target && e.courses>=mc; label=`${e.n} / ${b.target}u · ${e.courses}/${mc} courses`; pct=Math.min(100,100*e.n/b.target);}
      else if(b.type==="count"){ met=e.n>=b.target; label=`${e.n} / ${b.target}`; pct=Math.min(100,100*e.n/(b.target||1));}
      else { met=e.n>=b.target; label=`${e.n} / ${b.target}u`; pct=Math.min(100,100*e.n/(b.target||1));}
      if(b.headline){
        h+=`<div class="reqtotal ${met?'met':''}">
            <span class="rt-l">${esc(b.name)}</span>
            <span class="rt-v">${met?'✓ ':''}${e.n}<span class="rt-t">/ ${b.target}u</span></span></div>`;
        continue;
      }
      h+=`<div class="reqrow ${met?'met':''}">
        <div class="rl"><span class="rn">${esc(b.name)}</span>
        <span class="rv ${met?'':'short'}">${met?'✓ ':''}${label}</span></div>
        <div class="bar ${met?'done':''}"><i style="width:${pct}%"></i></div>
        ${(e.info||[]).map(n=>`<div class="hint" style="margin-top:3px">${esc(n)}</div>`).join("")}
        ${(e.notes||[]).map(n=>`<div class="hint" style="margin-top:3px">⚠ ${esc(n)}</div>`).join("")}</div>`;
    }
    h+="</div>";
  }
  document.getElementById("reqpanel").innerHTML=h;
}

// ---- term grid ----
function renderTerms(){
  const grid=document.getElementById("termgrid");
  const order=["Unassigned",...PLAN_TERMS];
  let h="";
  for(const term of order){
    const items=planItems.filter(it=>it.term===term && (!hideAudit||!it.audit));
    items.sort((a,b)=>(a.audit-b.audit) || ((+b.units||0)-(+a.units||0)));  // size desc; audits last
    if(term==="Unassigned" && items.length===0) continue;
    const tot=items.filter(it=>!it.audit).reduce((s,it)=>s+(+it.units||0),0);  // every unit counts
    const cap=term==="Unassigned"?Infinity:TERM_LIMIT;
    h+=`<div class="term ${term==='Unassigned'?'unassigned':''}"><div class="term-h">${esc(term)}${term==='Unassigned'?' <span class="hint" style="font-weight:400">· not counted toward requirements</span>':''}
        <span class="tu ${tot>cap?'over':''}" ${tot>cap?`title="Over the limit of ${TERM_LIMIT} units per term"`:''}>${term==='Unassigned'?'':`${tot}u${tot>cap?` · over ${TERM_LIMIT}u limit`:''}`}</span></div><div class="term-body">`;
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
function renderPlanSummary(){
  const active=planItems.filter(counts);
  const mba=reqEarned(reqs.find(b=>b.key==="mba_total")).n;
  const eng=reqEarned(reqs.find(b=>b.key==="eng_total")).n;
  const th=reqEarned(reqs.find(b=>b.key==="thesis")).n;
  document.getElementById("plan-summary").innerHTML=
    `<b>${active.length}</b> courses scheduled · MBA <b>${mba}</b>/156u · EECS <b>${eng}</b>/66u · Thesis <b>${th}</b>/24u`;
}
function renderPlan(){ renderReqPanel(); renderTerms(); renderPlanSummary(); }

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
  const rows=reqs.map((b,i)=>`<div class="setrow"><span class="sn">${esc(b.name)} <span class="hint">(${esc(b.group)}, counts: ${b.tags.join(', ')||'—'})</span></span>
    <input type="number" data-req="${i}" value="${b.target}"> ${b.type==='count'?'courses':'units'}</div>`).join("");
  openModal("Requirement settings (editable)",
    `<div class="hint" style="margin-bottom:8px">Adjust the target for any requirement. These are your editable model of the LGO degree rules.</div>
     ${rows}<div style="margin-top:12px"><button id="req-reset">↺ Reset requirements to LGO defaults</button></div>`);
  document.getElementById("modal-body").addEventListener("change",e=>{
    const i=e.target.getAttribute("data-req"); if(i==null)return;
    reqs[+i].target=+e.target.value||0; reqSave(); renderReqPanel();
  });
  document.getElementById("req-reset").addEventListener("click",()=>{
    reqs=REQ_DEFAULT.map(x=>({...x,tags:[...x.tags]})); reqSave(); renderReqPanel(); settingsModal();
  });
}
document.getElementById("plan-add").addEventListener("click",addCourseModal);
document.getElementById("plan-settings").addEventListener("click",settingsModal);
document.getElementById("plan-export").addEventListener("click",()=>{
  const blob=new Blob([JSON.stringify({plan:planItems,reqs},null,2)],{type:"application/json"});
  const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="lgo_plan.json";a.click();
});
document.getElementById("plan-import").addEventListener("click",()=>{
  const inp=document.createElement("input");inp.type="file";inp.accept=".json";
  inp.onchange=()=>{const f=inp.files[0];if(!f)return;const r=new FileReader();
    r.onload=()=>{try{const d=JSON.parse(r.result); if(d.plan)planItems=d.plan; if(d.reqs)reqs=d.reqs; planSave();reqSave();renderPlan();}catch(err){alert("Could not parse JSON");}};
    r.readAsText(f);};
  inp.click();
});
document.getElementById("plan-reset").addEventListener("click",()=>{
  if(!confirm("Reset the schedule AND requirements to the LGO sample defaults? Your current plan will be lost."))return;
  planItems=PLAN_DEFAULT.map(x=>({...x,tags:[...x.tags]})); reqs=REQ_DEFAULT.map(x=>({...x,tags:[...x.tags]}));
  planSave();reqSave();renderPlan();
});

document.getElementById("plan-blank").addEventListener("click",()=>{
  if(!confirm("Clear your schedule and start from a blank plan? Your current plan will be lost (requirement settings stay; required courses go back to Unassigned)."))return;
  planItems=planItems.filter(it=>it.required).map(it=>({...it,term:"Unassigned"})); planSave(); renderPlan();
});
