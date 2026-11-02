// Saved state in the browser: shared load/save helpers and old-format migrations.
function load(k,def){try{const v=JSON.parse(localStorage.getItem(k));return v??def;}catch(e){return def;}}
function save(k,v){localStorage.setItem(k,JSON.stringify(v));}
function esc(s){return (s==null?'':String(s)).replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));}

// migrate older "1st/2nd" term labels (and saved plans) to calendar years
const TERM_MIG={"1st Summer":"Summer 2026","1st Fall":"Fall 2026","1st IAP":"IAP 2027","1st Spring":"Spring 2027","2nd Summer":"Summer 2027","2nd Fall":"Fall 2027","2nd IAP":"IAP 2028","2nd Spring":"Spring 2028"};
const migTerm=t=>TERM_MIG[t]||t;
