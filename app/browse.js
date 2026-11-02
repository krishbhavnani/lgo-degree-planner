// ---- column definitions -------------------------------------------------
const HAS_RATINGS = COURSES.some(c=>c.rating!=null);
const COLS = [
  {key:'flag',  label:'★', sort:false, fixed:true,
     get:c=>flags.has(c.number)?1:0, render:renderStar},
  {key:'number',label:'Course', get:c=>c.number, render:c=>{
     const planned=typeof planItems!=='undefined' && planItems.some(it=>it.number===c.number);
     return `<span class="cnum"><a href="${c.url}" target="_blank">${c.number}</a></span> `+
       (planned?`<span class="addplan added" title="Already in your plan">✓</span>`
               :`<span class="addplan" data-addplan="${c.number}" title="Add to plan (Unassigned)">＋</span>`);}},
  {key:'department',label:'Dept', get:c=>c.department||'', render:c=>{
     const d=c.department||'';
     const short=d.startsWith('Course 6')?'6 EECS':d.startsWith('Course 15')?'15 Mgmt':d.startsWith('Course 2')?'2 MechE':d.startsWith('Common Ground')?'CG':d;
     return `<span class="chip" title="${esc(d)}">${esc(short)}</span>`;}},
  {key:'title', label:'Title', get:c=>c.title, render:c=>esc(c.title)+
     (c.action_learning?` <span class="albadge" title="Action Learning lab · ${esc(c.al_term||'')}">🧪 ${esc(c.action_learning)}</span>`:'')+
     (c.design_approved?` <span class="dz dz-${c.design_approved}" title="LGO ${c.design_approved} design class — fulfills the Design requirement">🎨</span>`:'')},
  {key:'category',label:'Category', get:c=>c.category||'', render:c=>esc(c.category||'')},
  {key:'terms', label:'Terms', get:c=>(c.terms||[]).join(','),
     render:c=>(c.terms||[]).map(t=>`<span class="chip">${t}</span>`).join('')||'<span class="empty">—</span>'},
  {key:'offering_status',label:'Offering', get:c=>c.offering_status||'', render:renderOffering},
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
const flags = new Set(load(LS.flags, []));
let hidden = new Set(load(LS.hidden, DEFAULT_HIDDEN));
let sort = load(LS.sort, {key:'number', dir:1});
const expanded = new Set();


// ---- renderers ----------------------------------------------------------
function renderStar(c){return `<span class="star ${flags.has(c.number)?'on':''}" data-star="${c.number}">★</span>`;}
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
  const s=c.offering_status||'';
  let cls='b-ok'; if(/this year/.test(s))cls='b-bad'; else if(/next year/.test(s))cls='b-warn';
  else if(/not currently/i.test(s))cls='b-grey';
  let h=`<span class="badge ${cls}">${esc(s)}</span>`;
  if((c.offering_notes||[]).length) h+=`<div class="hint">${esc(c.offering_notes.join('; '))}</div>`;
  return h;
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
  const open=expanded.has(c.number);
  const clip=d.length>160?d.slice(0,160)+'… ':d;
  if(d.length<=160) return `<span class="desc">${esc(d)}</span>`;
  return `<span class="desc ${open?'open':''}"><span class="clip">${esc(clip)}</span>`+
         `<span class="full">${esc(d)} </span>`+
         `<span class="more" data-more="${c.number}">${open?'less':'more'}</span></span>`;
}

// ---- build sidebar filters ----------------------------------------------
function uniq(arr){return [...new Set(arr)].filter(x=>x!=null&&x!=='');}
const TERMS=['Fall','IAP','Spring','Summer'];
const OFFER=uniq(COURSES.map(c=>c.offering_status)).sort();
const AAGS=['Approved-Offered','Approved-NotThisYear','Approved-NotInCatalog','Not approved'];
const CATS=uniq(COURSES.map(c=>c.category)).sort();
const DEPTS=uniq(COURSES.map(c=>c.department)).sort();

function checkList(host,items,name){
  document.getElementById(host).innerHTML=items.map(v=>
    `<label><input type="checkbox" data-${name}="${esc(v)}">${esc(v)}</label>`).join('');
}
checkList('f_dept',DEPTS,'dept');
checkList('f_terms',TERMS,'term');
checkList('f_offering',OFFER,'offer');
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
    terms:checkedVals('term'), offer:checkedVals('offer'),
    aags:checkedVals('aags'), cat:checkedVals('cat'), dept:checkedVals('dept'),
    design:document.getElementById('f_design').checked,
    al:document.getElementById('f_al').checked,
    umin:numOrNull('u_min'), umax:numOrNull('u_max'),
    hmax:numOrNull('h_max'), rmin:+document.getElementById('r_min').value,
  };
}
function numOrNull(id){const v=document.getElementById(id).value;return v===''?null:+v;}

function passes(c,f){
  if(f.flagged && !flags.has(c.number)) return false;
  if(f.dept.length && !f.dept.includes(c.department)) return false;
  if(f.design && !c.design_approved) return false;
  if(f.al && !c.action_learning) return false;
  if(f.q){
    const hay=(c.number+' '+c.title+' '+(c.instructor||'')+' '+(c.description||'')+' '+(c.category||'')+' '+(c.department||'')).toLowerCase();
    if(!hay.includes(f.q)) return false;
  }
  if(f.terms.length && !(c.terms||[]).some(t=>f.terms.includes(t))) return false;
  if(f.offer.length && !f.offer.includes(c.offering_status)) return false;
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
function renderRows(){
  const f=getFilters();
  const list=sorted(COURSES.filter(c=>passes(c,f)));
  document.getElementById('rows').innerHTML=list.map(c=>
    '<tr>'+COLS.map(col=>{
      const hc=hidden.has(col.key)?'hcol':'';
      return `<td class="${hc} ${col.key==='number'?'cnum':''}">${col.render(c)}</td>`;
    }).join('')+'</tr>').join('');
  document.getElementById('shown').textContent=list.length;
  document.getElementById('total').textContent=COURSES.length;
  document.getElementById('flagcount').textContent=flags.size;
}
function renderAll(){renderHead();renderRows();}

// ---- events --------------------------------------------------------------
document.addEventListener('input',e=>{
  if(e.target.matches('#search,[data-dept],[data-term],[data-offer],[data-aags],[data-cat],#u_min,#u_max,#h_max,#r_min,#f_flagged,#f_design,#f_al'))
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
  document.querySelectorAll('[data-dept],[data-term],[data-offer],[data-aags],[data-cat]').forEach(x=>x.checked=false);
  ['u_min','u_max','h_max'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('r_min').value='0';
  document.getElementById('f_flagged').checked=false;
  document.getElementById('f_design').checked=false;
  document.getElementById('f_al').checked=false;
  renderRows();
});
document.getElementById('export').addEventListener('click',()=>{
  const cols=['number','title','department','category','terms','offering_status','aags','units_raw','units_total',
              'schedule_summary','prereq_raw','eval_hours_in','eval_hours_out','eval_instructor_match',
              ...(HAS_RATINGS?['rating','rating_rationale']:[]),'instructor','url'];
  const rows=COURSES.filter(c=>flags.has(c.number));
  const csv=[cols.join(',')].concat(rows.map(c=>cols.map(k=>{
    let v=c[k]; if(Array.isArray(v))v=v.join('; '); v=v==null?'':String(v);
    return '"'+v.replace(/"/g,'""')+'"';
  }).join(','))).join('\n');
  const blob=new Blob([csv],{type:'text/csv'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='flagged_courses.csv'; a.click();
});
