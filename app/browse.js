// ---- column definitions -------------------------------------------------
const HAS_RATINGS = COURSES.some(c=>c.rating!=null);
const COLS = [
  {key:'flag',  label:'★', sort:false, fixed:true,
     get:c=>flags.has(c.id)?1:0, render:renderStar},
  {key:'number',label:'Course', get:c=>c.number, render:c=>{
     const planned=typeof planItems!=='undefined' && planItems.some(it=>it.course===c.id);
     return `<span class="cnum">${c.url?`<a href="${esc(c.url)}" target="_blank">${esc(c.number)}</a>`:esc(c.number)}</span> `+
       (planned?`<span class="addplan added" title="Already in your plan">✓</span>`
               :`<span class="addplan" data-addplan="${esc(c.id)}" title="Add to plan (Unassigned)">＋</span>`);}},
  {key:'department',label:'Dept', get:c=>c.department||'', render:c=>{
     const d=c.department||'';
     const short=d.startsWith('Course 6')?'6 EECS':d.startsWith('Course 15')?'15 Mgmt':d.startsWith('Course 2')?'2 MechE':d.startsWith('Common Ground')?'CG':d;
     return `<span class="chip" title="${esc(d)}">${esc(short)}</span>`;}},
  {key:'title', label:'Title', get:c=>c.title, render:c=>esc(c.title)+
     (c.action_learning?` <span class="albadge" title="Action Learning lab · ${esc(c.al_term||'')}">🧪 ${esc(c.action_learning)}</span>`:'')+
     (c.design_approved?` <span class="dz dz-${c.design_approved}" title="${c.design_approved==='approved'?'LGO pre-approved design class: fulfills the Design requirement':'LGO conditionally approved design class: check the LGO handbook'}">🎨</span>`:'')+
     (c.half_term?` <span class="chip half" title="Half-term course (${c.half_term==='H1'?'first':'second'} half)">${c.half_term}</span>`:'')+
     (c.kind==='special'?` <span class="hint" title="Special subjects reuse their number for a different topic each term">· topic changes each term</span>`:'')},
  {key:'category',label:'Research area', get:c=>c.category||'', render:c=>esc(c.category||'')},
  {key:'terms', label:'Your terms', num:true, get:c=>firstOffered(c), render:renderTermChips},
  {key:'offering',label:'Offering', get:c=>c.available.now?'':c.available.reason, render:renderOffering},
  {key:'aags', label:'AAGS', get:c=>c.aags||'', render:renderAags},
  {key:'units_raw',label:'Units', get:c=>c.units_raw||'', render:c=>esc(c.units_raw||'—')},
  {key:'units_total',label:'Total', num:true, get:c=>c.units_total, render:c=>
     c.units_total==null?'<span class="empty">—</span>':`<span class="num">${c.units_total}</span>`},
  {key:'schedule_summary',label:'Schedule', get:c=>c.schedule_summary||'',
     render:c=>esc(c.schedule_summary||'')||'<span class="empty">—</span>'},
  {key:'prereqs',label:'Prerequisites', get:c=>c.prereq_raw||'', render:renderPrereqs},
  {key:'eval_hours_in', label:'Hrs in', num:true, get:c=>c.eval_hours_in, render:c=>hoursCell(c,c.eval_hours_in)},
  {key:'eval_hours_out',label:'Hrs out', num:true, get:c=>c.eval_hours_out, render:c=>hoursCell(c,c.eval_hours_out)},
  {key:'difficulty',label:'Difficulty', num:true, get:c=>diffTotal(c), render:c=>diffBadge(c)},
  {key:'eval_instructor_match',label:'Eval match', get:c=>String(c.eval_instructor_match??''), render:renderMatch},
  {key:'rating',label:'Rating', num:true, get:c=>c.rating, render:renderRating},
  {key:'rating_rationale',label:'Why', get:c=>c.rating_rationale||'',
     render:c=>c.rating_rationale?`<span class="desc">${esc(c.rating_rationale)}</span>`:'<span class="empty">—</span>'},
  {key:'instructor',label:'Instructor', get:c=>c.instructor||'',
     render:c=>c.instructor?`<i>${esc(c.instructor)}</i>`:'<span class="empty">—</span>'},
  {key:'description',label:'Description', sort:false, get:c=>c.description||'', render:renderDesc},
];
// No ratings in the data (public build) -> drop the Rating/Why columns entirely.
if(!HAS_RATINGS){ for(let i=COLS.length-1;i>=0;i--) if(COLS[i].key==='rating'||COLS[i].key==='rating_rationale') COLS.splice(i,1); }
const DEFAULT_HIDDEN = []; // all visible by default

// ---- persisted state ----------------------------------------------------
// Storage keys are namespaced 'lgo-dp.' so this public build never shares saved state with
// the personal build (both run from file://, which browsers treat as one origin).
const LS = {flags:'lgo-dp.flags', hidden:'lgo-dp.hidden', sort:'lgo-dp.sort'};
// Starred courses, by course id (older saves hold numbers: a number stars all its topics).
const flags = new Set(load(LS.flags, []).flatMap(k=>CAT.get(k)?[k]:CAT.byNumber(k).map(c=>c.id)));
let hidden = new Set(load(LS.hidden, DEFAULT_HIDDEN));
let sort = load(LS.sort, {key:'number', dir:1});
const expanded = new Set();


// ---- renderers ----------------------------------------------------------
function renderStar(c){return `<span class="star ${flags.has(c.id)?'on':''}" data-star="${esc(c.id)}">★</span>`;}
// The student's terms (from the Plan's grad year) where the course has a catalog record, e.g.
// "F26 ✓  S27 ✓  F27 ~  S28 ?". Same badges and tooltips as the plan.
const SEASON_SHORT={Fall:"F",IAP:"I",Spring:"S",Summer:"Su"};
const QUIET=new Set(["not_listed","no_record","not_projected"]);
const OFFERED=new Set(["listed","expected","unverified","ran"]);
function renderTermChips(c){
  const chips=PLAN_TERMS.map(t=>({t,b:CAT.status(c.id,t)})).filter(x=>!QUIET.has(x.b.code));
  return chips.length?'<span class="tchips">'+chips.map(({t,b})=>{const [s,y]=t.split(" ");
    return `<span class="tchip tb-${b.code}" title="${esc(t)}: ${esc(b.label)}. ${esc(b.tip)}">${SEASON_SHORT[s]||s}${y.slice(2)} ${b.symbol}</span>`;}).join('')+'</span>'
    :'<span class="empty">—</span>';
}
// Sorts by the first of the student's terms the course is offered in.
function firstOffered(c){const t=PLAN_TERMS.find(t=>OFFERED.has(CAT.status(c.id,t).code));return t?CAT.termKey(t):null;}
function numCell(v){return v==null?'<span class="empty">—</span>':`<span class="num">${v}</span>`;}
function diffTotal(c){return (c.eval_hours_in!=null||c.eval_hours_out!=null)?((c.eval_hours_in||0)+(c.eval_hours_out||0)):null;}
function diffInfo(t){if(t==null)return null; if(t<8)return{l:'Light',c:'d-l'}; if(t<11)return{l:'Moderate',c:'d-m'}; if(t<15)return{l:'Heavy',c:'d-h'}; return{l:'Very Heavy',c:'d-x'};}
function diffBadge(c){const t=diffTotal(c); const d=diffInfo(t); return d?`<span class="dbadge ${d.c}" title="${t} hrs/week total (eval)">${d.l}</span>`:'<span class="empty">—</span>';}
function hoursCell(c,v){
  if(v==null) return c.eval_status==='none'?'<span class="empty" title="No evaluation on record">n/a</span>':'<span class="empty">—</span>';
  const bits=[]; if(c.eval_term)bits.push(c.eval_term); if(c.eval_responses!=null)bits.push('n='+c.eval_responses);
  const lowN=c.eval_responses!=null&&c.eval_responses<5;
  return `<span class="num${lowN?' lown':''}" title="${esc(bits.join(' · '))}">${v}${lowN?'*':''}</span>`;
}
function renderOffering(c){
  return c.available.now?'<span class="badge b-ok">Offered</span>':`<span class="badge b-grey">${esc(c.available.reason)}</span>`;
}
function renderAags(c){
  const a=c.aags||'Not approved';
  const map={'Approved-Offered':['b-blue','AAGS ✓ offered'],'Approved-NotThisYear':['b-grey','AAGS ✓ (not this yr)'],
             'Approved-NotInCatalog':['b-grey','AAGS ✓ (not in catalog)'],'Not approved':['b-none','— not approved'],
             'N/A':['b-none','—']};
  const [cls,txt]=map[a]||['b-none',a];
  return `<span class="badge ${cls}">${esc(txt)}</span>`;
}
function renderPrereqs(c){
  if(!c.prereqs || !c.prereqs.length){
    return c.prereq_raw?`<span class="prq">${esc(c.prereq_raw)}</span>`:'<span class="empty">None</span>';
  }
  const parts=c.prereqs.map(p=>p.name?`${p.number} ${p.name}`:p.number);
  return `<span class="prq" title="${esc(c.prereq_raw)}">${esc(parts.join('; '))}</span>`;
}
function renderMatch(c){
  const m=c.eval_instructor_match;
  if(m===true) return '<span class="matchY">✓ same</span>';
  if(m===false){
    const who=c.eval_instructor?` (${esc(c.eval_instructor)})`:'';
    return `<span class="matchN" title="Evaluation reflects a different instructor than the catalog: ${esc(c.eval_instructor||'')}">✗ diff${who}</span>`;
  }
  if(c.eval_status==='none') return '<span class="matchNA" title="No evaluation on record">n/a</span>';
  return '<span class="matchNA" title="Catalog instructor unknown — cannot compare">—</span>';
}
function renderRating(c){
  if(c.rating==null) return '<span class="empty">—</span>';
  return `<span class="rate"><span class="r${c.rating}">${c.rating}/5</span></span>`;
}
function renderDesc(c){
  const d=c.description||''; if(!d) return '<span class="empty">—</span>';
  const open=expanded.has(c.id);
  const clip=d.length>160?d.slice(0,160)+'… ':d;
  if(d.length<=160) return `<span class="desc">${esc(d)}</span>`;
  return `<span class="desc ${open?'open':''}"><span class="clip">${esc(clip)}</span>`+
         `<span class="full">${esc(d)} </span>`+
         `<span class="more" data-more="${esc(c.id)}">${open?'less':'more'}</span></span>`;
}

// ---- build sidebar filters ----------------------------------------------
function uniq(arr){return [...new Set(arr)].filter(x=>x!=null&&x!=='');}
const AAGS=['Approved-Offered','Approved-NotThisYear','Approved-NotInCatalog','Not approved'];
const CATS=uniq(COURSES.map(c=>c.category)).sort();
const DEPTS=uniq(COURSES.map(c=>c.department)).sort();

function checkList(host,items,name){
  document.getElementById(host).innerHTML=items.map(v=>
    `<label><input type="checkbox" data-${name}="${esc(v)}">${esc(v)}</label>`).join('');
}
checkList('f_dept',DEPTS,'dept');
checkList('f_aags',AAGS,'aags');
checkList('f_cat',CATS,'cat');

// column toggles
document.getElementById('coltoggle').innerHTML=COLS.filter(c=>!c.fixed).map(c=>
  `<label style="display:block"><input type="checkbox" data-col="${c.key}" ${hidden.has(c.key)?'':'checked'}> ${esc(c.label)}</label>`).join('');

// ---- filtering / sorting -------------------------------------------------
function checkedVals(name){return [...document.querySelectorAll(`[data-${name}]`)].filter(x=>x.checked).map(x=>x.getAttribute('data-'+name));}

function getFilters(){
  return {
    q:document.getElementById('search').value.trim().toLowerCase(),
    flagged:document.getElementById('f_flagged').checked,
    term:document.getElementById('f_term').value, notNow:document.getElementById('f_notnow').checked,
    aags:checkedVals('aags'), cat:checkedVals('cat'), dept:checkedVals('dept'),
    design:document.getElementById('f_design').checked,
    al:document.getElementById('f_al').checked,
    umin:numOrNull('u_min'), umax:numOrNull('u_max'),
    hmax:numOrNull('h_max'), rmin:+document.getElementById('r_min').value,
  };
}
function numOrNull(id){const v=document.getElementById(id).value;return v===''?null:+v;}

function passes(c,f){
  if(f.flagged && !flags.has(c.id)) return false;
  if(!f.notNow && !c.available.now) return false;   // default: offered now or later
  if(f.dept.length && !f.dept.includes(c.department)) return false;
  if(f.design && !c.design_approved) return false;
  if(f.al && !c.action_learning) return false;
  if(f.q){
    const hay=(c.number+' '+c.title+' '+(c.instructor||'')+' '+(c.description||'')+' '+(c.category||'')+' '+(c.department||'')).toLowerCase();
    if(!hay.includes(f.q)) return false;
  }
  if(f.term && !OFFERED.has(CAT.status(c.id,f.term).code)) return false;
  if(f.aags.length && !f.aags.includes(c.aags||'Not approved')) return false;
  if(f.cat.length && !f.cat.includes(c.category)) return false;
  if(f.umin!=null && (c.units_total==null || c.units_total<f.umin)) return false;
  if(f.umax!=null && (c.units_total==null || c.units_total>f.umax)) return false;
  if(f.hmax!=null){
    const h=(c.eval_hours_in||0)+(c.eval_hours_out||0);
    const hasEval=c.eval_hours_in!=null||c.eval_hours_out!=null;
    if(hasEval && h>f.hmax) return false; // null eval always passes
  }
  if(f.rmin && (c.rating==null || c.rating<f.rmin)) return false;
  return true;
}

function sorted(list){
  const col=COLS.find(c=>c.key===sort.key)||COLS[1];
  const dir=sort.dir;
  return list.slice().sort((a,b)=>{
    let va=col.get(a), vb=col.get(b);
    if(col.num){
      const na=va==null?null:+va, nb=vb==null?null:+vb;
      if(na==null&&nb==null)return 0; if(na==null)return 1; if(nb==null)return -1; // nulls last
      return (na-nb)*dir;
    }
    va=(va==null?'':String(va)).toLowerCase(); vb=(vb==null?'':String(vb)).toLowerCase();
    return va<vb?-dir:va>vb?dir:0;
  });
}

// ---- render --------------------------------------------------------------
function renderHead(){
  document.getElementById('headrow').innerHTML=COLS.map(c=>{
    const arr=sort.key===c.key?`<span class="arrow">${sort.dir>0?'▲':'▼'}</span>`:'';
    const hc=hidden.has(c.key)?'hcol':'';
    return `<th class="${hc}" data-col="${c.key}">${esc(c.label)} ${arr}</th>`;
  }).join('');
}
// "Offered in" lists the student's own terms that the catalog covers, so it follows the grad year.
function syncTermFilter(){
  const sel=document.getElementById('f_term'), cur=sel.value;
  sel.innerHTML='<option value="">any term</option>'+PLAN_TERMS.filter(CAT.tracked).map(t=>`<option ${t===cur?'selected':''}>${esc(t)}</option>`).join('');
}
function renderRows(){
  syncTermFilter();
  const f=getFilters();
  const list=sorted(COURSES.filter(c=>passes(c,f)));
  document.getElementById('rows').innerHTML=list.map(c=>
    '<tr>'+COLS.map(col=>{
      const hc=hidden.has(col.key)?'hcol':'';
      return `<td class="${hc} ${col.key==='number'?'cnum':''}">${col.render(c)}</td>`;
    }).join('')+'</tr>').join('');
  // Not offered now or later (shown only with the toggle): dimmed, with the reason.
  document.querySelectorAll('#rows tr').forEach((tr,i)=>{const c=list[i]; if(!c.available.now){tr.classList.add('dim'); tr.title=c.available.reason;}});
  document.getElementById('shown').textContent=list.length;
  document.getElementById('total').textContent=COURSES.length;
  document.getElementById('flagcount').textContent=flags.size;
}
function renderAll(){renderHead();renderRows();}

// ---- events --------------------------------------------------------------
document.addEventListener('input',e=>{
  if(e.target.matches('#search,[data-dept],#f_term,#f_notnow,[data-aags],[data-cat],#u_min,#u_max,#h_max,#r_min,#f_flagged,#f_design,#f_al'))
    renderRows();
});
document.getElementById('headrow').addEventListener('click',e=>{
  const th=e.target.closest('th'); if(!th)return;
  const key=th.getAttribute('data-col'); const col=COLS.find(c=>c.key===key);
  if(!col||col.sort===false)return;
  if(sort.key===key) sort.dir=-sort.dir; else {sort.key=key;sort.dir=1;}
  save(LS.sort,sort); renderAll();
});
document.getElementById('rows').addEventListener('click',e=>{
  const s=e.target.closest('[data-star]');
  if(s){const n=s.getAttribute('data-star'); flags.has(n)?flags.delete(n):flags.add(n);
        save(LS.flags,[...flags]); renderRows(); return;}
  const ap=e.target.closest('[data-addplan]');
  if(ap){addPlanItem(ap.getAttribute('data-addplan'),null,null,"Unassigned"); renderRows(); return;}
  const m=e.target.closest('[data-more]');
  if(m){const n=m.getAttribute('data-more'); expanded.has(n)?expanded.delete(n):expanded.add(n); renderRows();}
});
document.getElementById('coltoggle').addEventListener('change',e=>{
  const k=e.target.getAttribute('data-col'); if(!k)return;
  e.target.checked?hidden.delete(k):hidden.add(k);
  save(LS.hidden,[...hidden]); renderAll();
});
document.getElementById('resetf').addEventListener('click',()=>{
  document.getElementById('search').value='';
  document.querySelectorAll('[data-dept],[data-aags],[data-cat]').forEach(x=>x.checked=false);
  document.getElementById('f_term').value=''; document.getElementById('f_notnow').checked=false;
  ['u_min','u_max','h_max'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('r_min').value='0';
  document.getElementById('f_flagged').checked=false;
  document.getElementById('f_design').checked=false;
  document.getElementById('f_al').checked=false;
  renderRows();
});
document.getElementById('export').addEventListener('click',()=>{
  const cols=['number','title','department','category','terms','offering','aags','units_raw','units_total',
              'schedule_summary','prereq_raw','eval_hours_in','eval_hours_out','eval_instructor_match',
              ...(HAS_RATINGS?['rating','rating_rationale']:[]),'instructor','url'];
  const rows=COURSES.filter(c=>flags.has(c.id));
  const field=(c,k)=>k==='terms'?PLAN_TERMS.map(t=>[t,CAT.status(c.id,t)]).filter(([,b])=>!QUIET.has(b.code)).map(([t,b])=>`${t} ${b.label}`)
    :k==='offering'?(c.available.now?'Offered':c.available.reason):c[k];
  const csv=[cols.join(',')].concat(rows.map(c=>cols.map(k=>{
    let v=field(c,k); if(Array.isArray(v))v=v.join('; '); v=v==null?'':String(v);
    return '"'+v.replace(/"/g,'""')+'"';
  }).join(','))).join('\n');
  const blob=new Blob([csv],{type:'text/csv'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='flagged_courses.csv'; a.click();
});
