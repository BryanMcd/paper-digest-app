
import os
from typing import List
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONTACT = os.getenv("PD_MAILTO", "your@email.here")
UA = f"PaperDigest/0.1 (+mailto:{CONTACT})"
HEADERS = {"User-Agent": UA, "Accept": "application/json"}

JOURNAL_ISSNS = {
    "Nature": ["0028-0836", "1476-4687"],
    "Immunity": ["1074-7613", "1097-4180"],
    "Nature Immunology": ["1529-2908", "1529-2916"],
    "Science": ["0036-8075", "1095-9203"],
    "Cell": ["0092-8674", "1097-4172"],
    "Nature Medicine": ["1078-8956", "1546-170X"],
    "PNAS": ["0027-8424", "1091-6490"],
    "Science Immunology": ["2470-9468"],
    "Journal of Clinical Investigation": ["0021-9738", "1558-8238"],
    "Nature Biotechnology": ["1087-0156", "1546-1696"],
    "Science Translational Medicine": ["1946-6234"],
    "Nature Aging": ["2662-8465"],
}

INDEX_HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Paper Digest — Strict Research UI</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#fff;color:#111}
    header{position:sticky;top:0;background:rgba(255,255,255,.9);backdrop-filter:saturate(180%) blur(6px);border-bottom:1px solid #eee}
    .wrap{max-width:1100px;margin:0 auto;padding:16px}
    h1{font-size:22px;margin:0 0 4px}
    .controls{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px}
    input,button,textarea{padding:8px 10px;border:1px solid #ddd;border-radius:12px}
    button{background:#111;color:#fff;border-color:#111;cursor:pointer}
    main{display:grid;grid-template-columns:3fr 2fr;gap:24px}
    @media (max-width: 900px){main{grid-template-columns:1fr} .controls{grid-template-columns:repeat(2,minmax(0,1fr))}}
    ul{list-style:none;padding:0;margin:0}
    .card{border:1px solid #e5e5e5;border-radius:16px;padding:14px;margin:12px 0}
    .muted{color:#666;font-size:13px}
    .row{display:flex;gap:8px;align-items:center;color:#555;font-size:14px}
    a{color:#0b57d0;text-decoration:none} a:hover{text-decoration:underline}
    .error{background:#fff5f5;color:#b00020;border:1px solid #f2c9c9;padding:10px;border-radius:12px;margin-bottom:12px;font-size:13px;white-space:pre-wrap}
    .pill{display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid #ddd;font-size:12px;margin-right:6px}
    textarea{width:100%;height:120px}
    .selected{box-shadow:0 0 0 2px #111}
    .status{margin:10px 0;padding:8px 12px;border:1px solid #eee;border-radius:10px;background:#fafafa;font-size:13px}
  </style>
</head>
<body>
<header>
  <div class="wrap">
    <h1>Paper Digest — Strict Research UI</h1>
    <div class="muted">Excludes news/editorials/podcasts; research articles only.</div>
    <div class="controls" style="margin-top:10px">
      <label class="muted">Days back<br><input id="days" type="number" value="120"></label>
      <label class="muted">Per journal<br><input id="per" type="number" value="20"></label>
      <label class="muted"><input id="demo" type="checkbox"> Demo</label>
      <label class="muted"><input id="useUnp" type="checkbox"> Unpaywall</label>
      <label class="muted" style="grid-column:span 2">Unpaywall email<br><input id="email" placeholder="you@lab.org"></label>
      <button id="fetchBtn">Fetch Papers</button>
    </div>
  </div>
</header>
<div class="wrap">
  <div id="status" class="status">Idle</div>
  <main style="margin-top:8px">
    <section>
      <h3>Latest</h3>
      <div id="error"></div>
      <div id="latest"></div>
    </section>
    <aside>
      <h3>Related</h3>
      <div id="relatedNote" class="muted">Click any paper on the left to see suggestions.</div>
      <div id="related"></div>
    </aside>
  </main>
  <section style="margin-top:20px">
    <h4>Journals</h4>
    <div class="muted">Edit this list. bioRxiv (immunology) is automatically included.</div>
    <textarea id="journals"></textarea>
  </section>
  <footer class="muted" style="margin:20px 0">
    Data from <a href="https://docs.openalex.org/" target="_blank">OpenAlex</a>. OA links via <a href="https://unpaywall.org/products/api" target="_blank">Unpaywall</a>.
  </footer>
</div>
<script>
const DEFAULT_JOURNALS = [
  "Nature Immunology","Immunity","Science","Cell","Nature Medicine","PNAS",
  "Science Immunology","Journal of Clinical Investigation","Nature Biotechnology",
  "Science Translational Medicine","Nature Aging","Nature"
];
const IMMUNOLOGY_KEYWORDS = ["immunolog","t cell","b cell","antigen","antibody","cytokine","innate","adaptive","treg","th1","th2","th17","il-2","il-6","ifn","mhc","hla","tlr","nk cell","dendritic","apc","vaccin"];
const STOP = new Set(("a,an,and,are,as,at,be,by,for,from,has,he,in,is,it,its,of,on,that,the,to,was,were,will,with,not,or,if,into,than,then,they,them,these,those,which,who,whom,what,when,where,why,how,also,can,may,using,used,use,based,between,within,across,via,per,over,under,more,less,most").split(","));

function isoSince(daysBack){
  const d=new Date(); d.setDate(d.getDate()-Number(daysBack||30)); return d.toISOString().slice(0,10);
}
function tokenize(t){return (t||"").toLowerCase().replace(/[^a-z0-9\\s]/g," ").split(/\\s+/).filter(x=>x && !STOP.has(x) && x.length>2)}
function buildTfidf(records){
  const docs=records.map(r=>tokenize(r.title+" "+r.abstract));
  const df=new Map();
  const tfs=docs.map(tokens=>{const m=new Map(); for(const t of tokens){m.set(t,(m.get(t)||0)+1)} for(const t of new Set(tokens)){df.set(t,(df.get(t)||0)+1)} return m});
  const N=docs.length, idf=new Map(); for(const [t,d] of df.entries()){idf.set(t, Math.log((N+1)/(d+1))+1)}
  const vecs=tfs.map(m=>{const v=new Map(); let n2=0; for(const [t,f] of m.entries()){const w=(f/Math.sqrt(m.size||1))*(idf.get(t)||0); v.set(t,w); n2+=w*w} return {v,norm:Math.sqrt(n2)}});
  return {vecs};
}
function cos(a,b){ if(!a?.norm||!b?.norm) return 0; let dot=0; const [sm,lg]=a.v.size<b.v.size?[a.v,b.v]:[b.v,a.v]; for(const [t,w] of sm.entries()){const w2=lg.get(t); if(w2) dot+=w*w2} return dot/(a.norm*b.norm) }
function relIdx(idx,k,records,vecs){
  if(!vecs?.length) return [];
  const base=vecs[idx];
  const sims=vecs.map((v,i)=>({i,s:i===idx?-1:cos(base,v)})).sort((a,b)=>b.s-a.s);
  const same=(records[idx]?.journal||"").toLowerCase();
  const cross=sims.filter(x=>(records[x.i]?.journal||"").toLowerCase()!==same).slice(0,k);
  if(cross.length<k){ const fill=sims.filter(x=>!cross.find(y=>y.i===x.i)).slice(0,k-cross.length); return cross.concat(fill).map(x=>x.i) }
  return cross.map(x=>x.i);
}

function absText(w){
  const t=w?.abstract;
  if(typeof t==="string") return t;
  const inv=w?.abstract_inverted_index;
  if(inv && typeof inv==="object"){const pos=[]; for(const [word,idxs] of Object.entries(inv)){for(const i of idxs) pos.push([i,word])} pos.sort((a,b)=>a[0]-b[0]); return pos.map(p=>p[1]).join(" ")}
  return "";
}
function toRec(w,fb){
  const doi=(w?.doi||"").replace("https://doi.org/","");
  return { id:w?.id, title:w?.title||"", abstract:absText(w), doi, url: doi?`https://doi.org/${doi}`:(w?.primary_location?.landing_page_url||w?.id), published:w?.publication_date||"", journal:w?.host_venue?.display_name||fb||"", oa_pdf:null };
}

async function api(path, params){
  const q = new URLSearchParams(params||{}).toString();
  const r = await fetch(`/api/${path}?${q}`);
  if(!r.ok) throw new Error(`API /${path} failed (${r.status})`);
  return await r.json();
}

const elStatus=document.getElementById('status');
const elLatest=document.getElementById('latest');
const elRelated=document.getElementById('related');
const elRelNote=document.getElementById('relatedNote');
const elError=document.getElementById('error');
const elDays=document.getElementById('days');
const elPer=document.getElementById('per');
const elDemo=document.getElementById('demo');
const elUseUnp=document.getElementById('useUnp');
const elEmail=document.getElementById('email');
const elJournals=document.getElementById('journals');

elJournals.value = DEFAULT_JOURNALS.join("\\n");

let records=[], vecs=[], selected=null;

function setStatus(t){ elStatus.textContent = t }

function renderLatest(){
  elLatest.innerHTML = records.map((p,i)=>`
    <div class="card ${selected===i?'selected':''}" data-idx="${i}">
      <div class="row"><span class="pill">${p.journal||""}</span> <span class="muted">${p.published||""}</span></div>
      <div style="margin-top:6px"><a href="${p.url}" target="_blank"><strong>${p.title}</strong></a></div>
      <div class="row" style="margin-top:6px">
        ${p.doi?`<a href="https://doi.org/${p.doi}" target="_blank">DOI</a>`:""}
      </div>
    </div>`).join("");
  for(const card of elLatest.querySelectorAll('.card')){
    card.onclick = ()=>{ selected = Number(card.getAttribute('data-idx')); renderLatest(); renderRelated(); }
  }
  setStatus(`Fetched ${records.length} items across journals`);
}
function renderRelated(){
  if(selected==null){ elRelated.innerHTML=""; elRelNote.style.display='block'; return; }
  elRelNote.style.display='none';
  const idxs = relIdx(selected,6,records,vecs);
  elRelated.innerHTML = idxs.map(i=>{
    const p=records[i];
    return `<div class="card">
      <div class="row"><span class="pill">${p.journal||""}</span> <span class="muted">${p.published||""}</span></div>
      <div style="margin-top:6px"><a href="${p.url}" target="_blank"><strong>${p.title}</strong></a></div>
      <div class="row" style="margin-top:6px">
        ${p.doi?`<a href="https://doi.org/${p.doi}" target="_blank">DOI</a>`:""}
      </div>
    </div>`;
  }).join("");
}

function showError(msg){ elError.innerHTML = `<div class="error">${msg}</div>` }

async function fetchAll(){
  try{
    elError.innerHTML=""; selected=null; renderRelated();
    setStatus("Fetching…");
    if(elDemo.checked){
      records = [
        {id:'d1', title:'IL-2 signaling dynamics in human Tregs', abstract:'We map IL2RA-driven STAT5 responses…', doi:'10.1000/demo.il2', url:'https://doi.org/10.1000/demo.il2', published:'2025-10-20', journal:'Immunity'},
        {id:'d2', title:'Engineered CAR-Tregs suppress alloimmunity in humanized mice', abstract:'FOXP3-stabilized CAR-Tregs targeting HLA-A2…', doi:'10.1000/demo.cartreg', url:'https://doi.org/10.1000/demo.cartreg', published:'2025-10-19', journal:'Nature Medicine'},
        {id:'d3', title:'TLR7 agonism reshapes GC B cell selection', abstract:'Adjuvanting with R848 enhances affinity maturation…', doi:'10.1000/demo.tlr7', url:'https://doi.org/10.1000/demo.tlr7', published:'2025-10-18', journal:'Science Immunology'}
      ];
      vecs = buildTfidf(records).vecs; renderLatest(); return;
    }
    const since = isoSince(elDays.value);
    const per = Number(elPer.value||20);
    const list = elJournals.value.split(/\\n+/).map(s=>s.trim()).filter(Boolean);
    const all=[];
    for(const j of list){
      if(j.toLowerCase().includes("biorxiv")) continue;
      const jres = await api("openalex_journal",{name:j, since:since, per:per});
      if(jres.status !== 200){ throw new Error(`OpenAlex query failed for ${j} (status ${jres.status})\\n${jres.error || ''}`) }
      for(const w of jres.results){ all.push(toRec(w,j)) }
    }
    try{
      const bxres = await api("openalex_biorxiv",{since:since, per:per});
      if(bxres.status === 200){
        const items = bxres.results.filter(w=>{
          const t = (w?.title||"") + " " + (w?.abstract || "");
          const low = t.toLowerCase();
          return IMMUNOLOGY_KEYWORDS.some(k=>low.includes(k));
        });
        for(const w of items){ all.push(toRec(w,"bioRxiv")) }
      }
    }catch(e){ console.warn("bioRxiv fail", e) }
    all.sort((a,b)=>String(b.published).localeCompare(String(a.published)));
    records = all;
    vecs = buildTfidf(records).vecs;
    renderLatest();
  }catch(e){
    console.error(e);
    showError(e.message||String(e));
    setStatus("Error");
  }
}

document.getElementById('fetchBtn').onclick = fetchAll;
</script>
</body>
</html>'''

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(INDEX_HTML)

async def _openalex_query(params: dict):
    q = dict(params)
    q["mailto"] = CONTACT
    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        r = await client.get("https://api.openalex.org/works", params=q)
    return r

def _issns_for(name: str) -> List[str]:
    return JOURNAL_ISSNS.get(name, [])

# Strict research-only clause used for all journal queries
STRICT_RESEARCH = (
    ",is_paratext:false,"
    "type_crossref:journal-article,"
    "type_crossref:!editorial|news-item|comment|letter|book-review|retraction|correction|erratum|addendum"
)

@app.get("/api/openalex_journal")
async def api_openalex_journal(name: str, since: str, per: int = 20):
    base_filter = f"locations.source.display_name.search:{name},from_publication_date:{since}"
    filters_try = [base_filter + STRICT_RESEARCH]
    issns = _issns_for(name)
    if issns:
        issn_base = f"locations.source.issn:{'|'.join(issns)},from_publication_date:{since}"
        filters_try.append(issn_base + STRICT_RESEARCH)

    last_error = None
    for flt in filters_try:
        params = {"filter": flt, "sort": "publication_date:desc", "per_page": per}
        r = await _openalex_query(params)
        if r.status_code == 200:
            j = r.json()
            return JSONResponse({"status": 200, "results": j.get("results", []), "applied_filter": flt})
        else:
            last_error = (r.status_code, r.text, flt)

    st, txt, flt = last_error or (500, "Unknown error", "")
    return JSONResponse({"status": st, "error": txt, "attempted_filter": flt}, status_code=200)

@app.get("/api/openalex_biorxiv")
async def api_openalex_biorxiv(since: str, per: int = 20):
    base = {
        "filter": f"locations.source.display_name.search:bioRxiv,from_publication_date:{since},is_paratext:false",
        "sort": "publication_date:desc",
        "per_page": per,
    }
    r = await _openalex_query(base)
    if r.status_code != 200:
        return JSONResponse({"status": r.status_code, "error": r.text}, status_code=200)
    j = r.json()
    return JSONResponse({"status": 200, "results": j.get("results", [])})
