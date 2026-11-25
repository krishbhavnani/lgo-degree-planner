// ---- column definitions -------------------------------------------------
const HAS_RATINGS = COURSES.some(c=>c.rating!=null);
const COLS = [
  {key:'flag',  label:'★', sort:false, fixed:true,
     get:c=>flags.has(c.id)?1:0, render:renderStar},
  {key:'number',label:'Course', mit:true, get:c=>c.number, render:c=>{
     const planned=typeof planItems!=='undefined' && planItems.some(it=>it.course===c.id);
     return `<span class="cnum">${c.url?`<a href="${esc(c.url)}" target="_blank">${esc(c.number)}</a>`:esc(c.number)}</span> `+
       (planned?`<span class="addplan added" title="Already in your plan">✓</span>`
               :`<span class="addplan" data-addplan="${esc(c.id)}" title="Add to plan (Unassigned)">＋</span>`);}},
  {key:'department',label:'Dept', mit:true, get:c=>c.department||'', render:c=>{
     const d=c.department||'';
     const short=d.startsWith('Course 6')?'6 EECS':d.startsWith('Course 15')?'15 Mgmt':d.startsWith('Course 2')?'2 MechE':d.startsWith('Common Ground')?'CG':d;
     return `<span class="chip" title="${esc(d)}">${esc(short)}</span>`;}},
  {key:'title', label:'Title', get:c=>c.title, render:c=>esc(c.title)+
     (c.action_learning?` <span class="albadge" title="Action Learning lab · ${esc(c.al_term||'')}">🧪 ${esc(c.action_learning)}</span>`:'')+
     (c.design_approved?` <span class="dz dz-${c.design_approved}" title="${c.design_approved==='approved'?'LGO pre-approved design class: fulfills the Design requirement':'LGO conditionally approved design class: check the LGO handbook'}">🎨</span>`:'')+
     (c.half_term?` <span class="chip half" title="Half-term course (${c.half_term==='H1'?'first':'second'} half)">${c.half_term}</span>`:'')+
     (c.kind==='special'?` <span class="hint" title="Special subjects reuse their number for a different topic each term">· topic changes each term</span>`:'')},
  {key:'category',label:'Research area', get:c=>c.category||'', render:c=>esc(c.category||'')},
  {key:'terms', label:'Your terms', num:true, get:c=>{const f=summary(c).first;return f?CAT.termKey(f):null;}, render:renderTermChips},
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
// "Your terms": the student's remaining terms (from the Plan's grad year) in which the course is or
// may be offered, e.g. "S27 ✓  F27 ~  S28 ?", with the plan's badges and tooltips. With none, the
// cell says why instead ("Next offered Fall 2027"). CAT.termsSummary() is the rule; the column,
// its sort, the row dimming and the CSV export all read it.
const SEASON_SHORT={Fall:"F",IAP:"I",Spring:"S",Summer:"Su"};
const summary=c=>CAT.termsSummary(c,PLAN_TERMS);
function renderTermChips(c){
  const {chips,reason}=summary(c);
  return chips.length?'<span class="tchips">'+chips.map(({term,badge:b})=>{const [s,y]=term.split(" ");
    return `<span class="tchip tb-${b.code}" title="${esc(term)}: ${esc(b.label)}. ${esc(b.tip)}">${SEASON_SHORT[s]||s}${y.slice(2)} ${b.symbol}</span>`;}).join('')+'</span>'
    :`<span class="empty">${esc(reason)}</span>`;
}
function diffTotal(c){return (c.eval_hours_in!=null||c.eval_hours_out!=null)?((c.eval_hours_in||0)+(c.eval_hours_out||0)):null;}
function diffInfo(t){if(t==null)return null; if(t<8)return{l:'Light',c:'d-l'}; if(t<11)return{l:'Moderate',c:'d-m'}; if(t<15)return{l:'Heavy',c:'d-h'}; return{l:'Very Heavy',c:'d-x'};}
function diffBadge(c){const t=diffTotal(c); const d=diffInfo(t); return d?`<span class="dbadge ${d.c}" title="${t} hrs/week total (eval)">${d.l}</span>`:'<span class="empty">—</span>';}
function hoursCell(c,v){
  if(v==null) return c.eval_status==='none'?'<span class="empty" title="No evaluation on record">n/a</span>':'<span class="empty">—</span>';
  const bits=[]; if(c.eval_term)bits.push(c.eval_term); if(c.eval_responses!=null)bits.push('n='+c.eval_responses);
  const lowN=c.eval_responses!=null&&c.eval_responses<5;
  return `<span class="num${lowN?' lown':''}" title="${esc(bits.join(' · '))}">${v}${lowN?'*':''}</span>`;
}
function renderAags(c){
  const a=c.aags||'Not approved';
  const map={'Approved-Offered':['b-blue','AAGS ✓ offered'],'Approved-NotThisYear':['b-grey','AAGS ✓ (not this yr)'],
             'Approved-NotInCatalog':['b-grey','AAGS ✓ (not in catalog)'],'Not approved':['b-none','— not approved'],
             'N/A':['b-none','—'],'Needs approval':['b-warn','AAGS ? needs approval']};
  const [cls,txt]=map[a]||['b-none',a];
  const tip=c.aags_note?`EECS lists it as: "${c.aags_note}". Not on the AAGS list: you can count it in your plan, but get it approved first.`:'';
  return `<span class="badge ${cls}" ${tip?`title="${esc(tip)}"`:''}>${esc(txt)}</span>`;
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
const AAGS=['Approved-Offered','Approved-NotThisYear','Approved-NotInCatalog','Needs approval','Not approved'];
const CATS=uniq(COURSES.map(c=>c.category)).sort();
const DEPTS=uniq(COURSES.map(c=>c.department)).sort(Catalog.mitCompare);

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
    term:document.getElementById('f_term').value,
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
  if(f.dept.length && !f.dept.includes(c.department)) return false;
  if(f.design && !c.design_approved) return false;
  if(f.al && !c.action_learning) return false;
  if(f.q){
    const hay=(c.number+' '+c.title+' '+(c.instructor||'')+' '+(c.description||'')+' '+(c.category||'')+' '+(c.department||'')).toLowerCase();
    if(!hay.includes(f.q)) return false;
  }
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
    if(col.mit) return Catalog.mitCompare(va,vb)*dir;   // MIT course order, not text
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
// The Term filter: the student's remaining terms (default), all terms, or one of their tracked
// terms (past ones included). Labels come from the plan's terms, so they follow the grad year.
// CAT.inScope() is the rule. A plan with no terms left (graduated) says so instead of "()".
function syncTermFilter(){
  const sel=document.getElementById('f_term'), cur=sel.value, left=CAT.remaining(PLAN_TERMS);
  const span=left.length?[...new Set([left[0],left[left.length-1]])].join(' – '):'none left';
  const opt=(v,label)=>`<option value="${esc(v)}" ${v===cur?'selected':''}>${esc(label)}</option>`;
  sel.innerHTML=opt('',`Your remaining terms (${span})`)+opt('all','All terms, including past')+
    '<optgroup label="One term">'+PLAN_TERMS.filter(CAT.tracked).map(t=>opt(t,CAT.isPastTracked(t)?`${t} (past)`:t)).join('')+'</optgroup>';
}
function renderRows(){
  syncTermFilter();
  const f=getFilters();
  // One pass: rows in the Term scope, and (for the default scope) matches hidden only by it.
  const inScope=[]; let outside=0;
  for(const c of COURSES){ if(!passes(c,f)) continue; if(CAT.inScope(c,f.term,PLAN_TERMS)) inScope.push(c); else if(!f.term) outside++; }
  const list=sorted(inScope);
  document.getElementById('rows').innerHTML=list.map(c=>
    '<tr>'+COLS.map(col=>{
      const hc=hidden.has(col.key)?'hcol':'';
      return `<td class="${hc} ${col.key==='number'?'cnum':''}">${col.render(c)}</td>`;
    }).join('')+'</tr>').join('');
  // None of the student's remaining terms: dimmed (the Your terms cell says why).
  document.querySelectorAll('#rows tr').forEach((tr,i)=>{ if(!summary(list[i]).chips.length) tr.classList.add('dim'); });
  document.getElementById('shown').textContent=list.length;
  const more=document.getElementById('scope-more');
  more.hidden=!outside;
  more.innerHTML=`${outside} more match outside your remaining terms. <a href="#" id="show-all-terms">Show all terms</a>`;
  document.getElementById('total').textContent=COURSES.length;
  document.getElementById('flagcount').textContent=flags.size;
}
function renderAll(){renderHead();renderRows();}

// ---- events --------------------------------------------------------------
document.addEventListener('input',e=>{
  if(e.target.matches('#search,[data-dept],#f_term,[data-aags],[data-cat],#u_min,#u_max,#h_max,#r_min,#f_flagged,#f_design,#f_al'))
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
document.getElementById('scope-more').addEventListener('click',e=>{
  if(!e.target.closest('#show-all-terms')) return;
  e.preventDefault(); document.getElementById('f_term').value='all'; renderRows();
});
document.getElementById('resetf').addEventListener('click',()=>{
  document.getElementById('search').value='';
  document.querySelectorAll('[data-dept],[data-aags],[data-cat]').forEach(x=>x.checked=false);
  document.getElementById('f_term').value='';
  ['u_min','u_max','h_max'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('r_min').value='0';
  document.getElementById('f_flagged').checked=false;
  document.getElementById('f_design').checked=false;
  document.getElementById('f_al').checked=false;
  renderRows();
});
document.getElementById('export').addEventListener('click',()=>{
  const cols=['number','title','department','category','terms','aags','units_raw','units_total',
              'schedule_summary','prereq_raw','eval_hours_in','eval_hours_out','eval_instructor_match',
              ...(HAS_RATINGS?['rating','rating_rationale']:[]),'instructor','url'];
  const rows=COURSES.filter(c=>flags.has(c.id));
  const terms=c=>{const {chips,reason}=summary(c); return chips.length?chips.map(({term,badge})=>`${term} ${badge.label}`):reason;};
  const field=(c,k)=>k==='terms'?terms(c):c[k];
  const csv=[cols.join(',')].concat(rows.map(c=>cols.map(k=>{
    let v=field(c,k); if(Array.isArray(v))v=v.join('; '); v=v==null?'':String(v);
    return '"'+v.replace(/"/g,'""')+'"';
  }).join(','))).join('\n');
  const blob=new Blob([csv],{type:'text/csv'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='flagged_courses.csv'; a.click();
});
