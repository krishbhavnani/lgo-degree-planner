// Course facts: db.js (courses x term offerings), read through app/catalog.js. Browse shows one
// row per course; a special subject gets one row per topic.
const CAT = Catalog.load(window.COURSE_DB);
const COURSES = CAT.courses.map(c=>CAT.row(c));
// Personal overlay: personal/ratings.js (gitignored) sets window.PERSONAL_RATINGS = {number: {rating, rating_rationale}}.
// Present only on Krish's machine, so the public site never shows Rating/Why columns.
if(window.PERSONAL_RATINGS) COURSES.forEach(c=>{const r=window.PERSONAL_RATINGS[c.number];
  if(r){c.rating=r.rating??null; c.rating_rationale=r.rating_rationale??null;}});

// ---- analytics: counts only ----------------------------------------------
// GoatCounter counts visits and a few named events, on the public site only (never file://, a
// local server or the personal build). No cookies, and nothing about a plan is ever sent.
// The script is pinned to v5 and checked against its hash, so a changed file won't run.
const ANALYTICS=location.hostname==="krishbhavnani.github.io";
const gcQueue=[];
if(ANALYTICS){
  const s=document.createElement("script");
  s.async=true; s.src="https://gc.zgo.at/count.v5.js"; s.crossOrigin="anonymous";
  s.integrity="sha384-atnOLvQb9t+jTSipvd75X2yginT4PjVbqDdlJAmxMm+wYElFmeR6EmLP5bYeoRVQ";
  s.dataset.goatcounter="https://lgo-degree-planner.goatcounter.com/count";
  s.onload=()=>gcQueue.splice(0).forEach(gcSend);
  document.head.appendChild(s);
}
function gcSend(name){window.goatcounter.count({path:name,title:name,event:true});}
// Count an event at most once per browser-tab session (reloads don't count again).
const tracked=new Set();
function track(name){
  if(!ANALYTICS||tracked.has(name)) return;
  tracked.add(name);
  const key="lgo-dp.ev."+name;
  try{ if(sessionStorage.getItem(key)) return; sessionStorage.setItem(key,"1"); }catch(e){}
  if(window.goatcounter?.count) gcSend(name); else gcQueue.push(name);
}

// ---- badge key (Browse and Plan) -----------------------------------------
// A small "Key" button that opens a popover listing only the badges that page can show. Each
// badge's own tooltip carries the specifics; the key is for a first look and for touch screens,
// where tooltips don't work. Open/closed is remembered per page.
const KEY_ITEMS={
  browse:[["listed","Offered","on MIT's schedule"],["expected","Likely offered","usually offered; not posted yet"],
          ["unverified","Check with dept.","offered irregularly"]],
  plan:  [["listed","Offered","on MIT's schedule"],["expected","Likely offered","usually offered; not posted yet"],
          ["unverified","Check with dept.","offered irregularly"],["not_offered","Not offered","not offered that term"]],
};
function renderKeys(){
  const terms=CAT.meta.terms||[], span=terms.length?`${terms[0]} to ${terms[terms.length-1]}`:"";
  const notes={
    browse:"Terms a course isn't offered don't appear; with none of your remaining terms, the row is dimmed and says why. Hover a chip for details.",
    plan:`No mark: no schedule data for that term${span?` (MIT data covers ${esc(span)})`:""}. Hover a badge for details.`,
  };
  document.querySelectorAll("details.key").forEach(el=>{
    const page=el.dataset.page, stored="lgo-dp.key."+page;
    el.querySelector(".key-pop").innerHTML=KEY_ITEMS[page].map(([code,label,desc])=>
      `<div class="key-row"><span class="tb tb-${code}">${Catalog.LEGEND[code].symbol}</span><b>${esc(label)}</b>${desc?`<span>${esc(desc)}</span>`:""}</div>`).join("")+
      `<div class="key-note">${notes[page]}</div>`;
    el.open=!!load(stored,false);
    el.addEventListener("toggle",()=>{try{save(stored,el.open);}catch(e){}});
  });
}

// ---- view switching ----
function setView(v){
  const plan=v==="plan";
  document.getElementById("view-browse").hidden=plan;
  document.getElementById("view-plan").hidden=!plan;
  document.getElementById("tab-browse").classList.toggle("on",!plan);
  document.getElementById("tab-plan").classList.toggle("on",plan);
  document.getElementById("search").style.display=plan?"none":"";
  document.getElementById("export").style.display=plan?"none":"";
  save(PLS.view,v);
  if(plan){ renderPlan(); track("plan-opened"); askGradYearOnce(); } else renderRows();
}
document.getElementById("tab-browse").addEventListener("click",()=>setView("browse"));
document.getElementById("tab-plan").addEventListener("click",()=>setView("plan"));

// ---- init ----------------------------------------------------------------
// The weekly refresh normally keeps the data under a week old. Older than this means the job has
// stopped (e.g. GitHub disabled the schedule), so say so instead of letting people trust it.
const STALE_DAYS=21;
// `updated` is the date of the last refresh that changed the course database (YYYY-MM-DD).
function renderFreshness(updated,now){
  const raw=updated||'';
  const d=raw?new Date(raw+'T12:00:00'):null;
  const ok=d&&!isNaN(d);
  const label=ok?d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}):'unknown';
  document.getElementById('lastpull').innerHTML=
    `<span title="Course data was fetched from MIT on ${esc(raw||'an unknown date')}">Data updated <b>${esc(label)}</b> · ${COURSES.length} courses</span>`;
  const stale=document.getElementById('stale');
  const age=ok?Math.round((now-d)/864e5):Infinity;   // whole days (ignores clock changes)
  stale.hidden=age<=STALE_DAYS;
  stale.textContent=`⚠ Course data may be out of date (last updated ${label}). Check the MIT catalog for the latest offerings and schedules.`;
}
function init(){
  renderFreshness(CAT.meta.updated,new Date());
  renderKeys();
  const haveEval=COURSES.filter(c=>c.eval_hours_in!=null).length;
  const haveRate=COURSES.filter(c=>c.rating!=null).length;
  document.getElementById('evalnote').textContent=
    `workload data: ${haveEval}/${COURSES.length} courses`+(HAS_RATINGS?` · ratings: ${haveRate}/${COURSES.length}`:'');
  if(!HAS_RATINGS) document.querySelectorAll('.rating-only').forEach(el=>el.hidden=true);
  renderAll();
  setView(load(PLS.view,"browse"));
}
// Every app/*.js file has loaded by the time the DOM is ready.
document.addEventListener('DOMContentLoaded',init);
