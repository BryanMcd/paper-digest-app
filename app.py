# app.py
import os, re, asyncio
from typing import List, Dict, Any
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CONTACT = os.getenv("PD_MAILTO", "your@email.here")
UA = f"PaperDigest/0.8 (+mailto:{CONTACT})"
HEADERS = {"User-Agent": UA, "Accept": "application/json"}

# 1. PERFORMANCE: In-memory cache prevents repeated API lookups
ISSN_CACHE: Dict[str, List[str]] = {
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

# Regex to clean up non-research titles locally
NON_RESEARCH_TITLE_RE = re.compile(
    r"(?i)(news|news & views|world view|editorial|comment(ary)?|perspective|opinion|careers|podcast|interview|q.?a|toolbox|technology feature|research briefing|outlook|correspondence|matters arising|briefing)"
)

# ---------------- UI (Unchanged) ----------------
INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Paper Digest</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#fff;color:#111}
    header{position:sticky;top:0;background:rgba(255,255,255,.95);border-bottom:1px solid #eee; z-index: 100;}
    .wrap{max-width:1100px;margin:0 auto;padding:16px}
    h1{font-size:22px;margin:0 0 4px}
    .controls { display: grid; grid-template-columns: auto auto 1fr 300px auto; gap: 12px; align-items: end; }
    input,button,textarea{padding:8px 10px;border:1px solid #ddd;border-radius:12px;font-family:inherit}
    button{background:#111;color:#fff;border-color:#111;cursor:pointer}
    button:disabled{opacity:0.5;cursor:not-allowed}
    main{display:grid;grid-template-columns:3fr 2fr;gap:24px; position: relative;}
    aside { position: fixed; right: 0; top: 230px; bottom: 0; width: 35%; overflow-y: auto; background: #fff; box-shadow: -4px 0 12px rgba(0,0,0,0.05); border-left: 1px solid #eee; padding: 20px; padding-bottom: 40px; z-index: 50; }
    @media (max-width: 900px){
      main{grid-template-columns:1fr} 
      .controls{grid-template-columns:repeat(2,minmax(0,1fr))}
      aside { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; width: 100%; height: 100%; background: #fff; z-index: 200; padding: 20px; box-shadow: none; }
      aside.active { display: block; }
      .mobile-close { display: block !important; margin-bottom: 20px;}
    }
    ul{list-style:none;padding:0;margin:0}
    .card{border:1px solid #e5e5e5;border-radius:16px;padding:14px;margin:12px 0; transition: border-color 0.2s}
    .card:hover { border-color: #bbb; cursor: pointer; }
    .muted{color:#666;font-size:13px}
    .row{display:flex;gap:8px;align-items:center;color:#555;font-size:14px}
    a{color:#0b57d0;text-decoration:none} a:hover{text-decoration:underline}
    .error{background:#fff5f5;color:#b00020;border:1px solid #f2c9c9;padding:10px;border-radius:12px;margin-bottom:12px;font-size:13px;white-space:pre-wrap}
    .pill{display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid #ddd;font-size:12px; background:#f4f4f4}
    textarea{ width:100%; height:120px; box-sizing:border-box; display:block; }
    .selected{box-shadow:0 0 0 2px #111; border-color:#111}
    .status{margin:10px 0;padding:8px 12px;border:1px solid #eee;border-radius:10px;background:#fafafa;font-size:13px}
    .mobile-close { display: none; width: 100%; background: #eee; color: #333; border: none; font-weight: bold;}
  </style>
</head>
<body>
<header>
  <div class="wrap">
    <h1>Paper Digest</h1>
    <div class="muted">Select a paper to view abstract.</div>
    <div class="controls" style="margin-top:10px">
      <div style="display:flex; flex-direction:column; justify-content:space-between; height:110px">
        <label class="muted">Days back<br><input id="days" type="number" value="120" style="width:70px"></label>
        <label class="muted">Per journal<br><input id="per" type="number" value="20" style="width:70px"></label>
      </div>
      <div style="display:flex; flex-direction:column; justify-content:space-between; height:90px">
        <label class="muted" style="cursor:pointer; display:block; padding-top:4px">
            <input id="news" type="checkbox" style="margin-right:4px; vertical-align:middle"> Include News
        </label>
        <label class="muted">Keywords<br>
            <div style="display:flex; gap:4px">
                <input id="keywords" type="text" placeholder="e.g. ARID1A" style="width:125px">
                <button onclick="document.getElementById('keywords').value=''" style="padding:0; width:25px; background:#f4f4f4; color:#333; border:1px solid #ddd; font-size:16px; line-height:1" title="Clear">×</button>
            </div>
        </label>
      </div>
      <div></div>
      <label class="muted">Journals<br><textarea id="journals" style="width:100%"></textarea></label>
      <button id="fetchBtn" style="height:120px;">Fetch Papers</button>
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
    <aside id="abstractAside">
      <button class="mobile-close" onclick="closeAbstract()">Close Abstract</button>
      <h3>Abstract</h3>
      <div id="abstractNote" class="muted">Click any paper on the left to see its abstract.</div>
      <div id="abstract"></div>
    </aside>
  </main>
  <footer class="muted" style="margin:20px 0">
    Data from <a href="https://docs.openalex.org/" target="_blank">OpenAlex</a>
    <br>
    Github repo: <a href="https://github.com/BryanMcd/paper-digest-app" target="_blank">paperdigest</a>
  </footer>
</div>
<script>
const DEFAULT_JOURNALS = [
  "Nature Immunology","Immunity","Science","Cell","Nature Medicine","PNAS",
  "Science Immunology","Journal of Clinical Investigation","Nature Biotechnology",
  "Science Translational Medicine","Nature Aging","Nature"
];
function isoSince(daysBack){ const d=new Date(); d.setDate(d.getDate()-Number(daysBack||30)); return d.toISOString().slice(0,10); }
async function defFetch(path, params){
  const q = new URLSearchParams(params||{}).toString();
  const r = await fetch(`/api/${path}?${q}`);
  if(!r.ok) throw new Error(`API failed`);
  return await r.json();
}
const elStatus=document.getElementById('status');
const elLatest=document.getElementById('latest');
const elAbstract=document.getElementById('abstract');
const elAbsNote=document.getElementById('abstractNote');
const elAside=document.getElementById('abstractAside');
const elError=document.getElementById('error');
const elDays=document.getElementById('days');
const elPer=document.getElementById('per');
const elNews=document.getElementById('news');
const elKw=document.getElementById('keywords');
const elJournals=document.getElementById('journals');
const elBtn=document.getElementById('fetchBtn');
elJournals.value = DEFAULT_JOURNALS.join("\\n");
let records=[], selected=null;
function setStatus(t){ elStatus.textContent = t }
function closeAbstract() { elAside.classList.remove('active'); }
function renderLatest(){
  elLatest.innerHTML = records.map((p,i)=>`
    <div class="card ${selected===i?'selected':''}" data-idx="${i}">
      <div class="row"><span class="pill">${p.journal||""}</span> <span class="muted">${p.published||""}</span></div>
      <div style="margin-top:6px"><a href="${p.url}" target="_blank" onclick="event.stopPropagation()"><strong>${p.title}</strong></a></div>
      <div class="row" style="margin-top:6px">${p.doi?`<span class="muted">DOI: ${p.doi}</span>`:""}</div>
    </div>`).join("");
  for(const card of elLatest.querySelectorAll('.card')){
    card.onclick = ()=>{ 
        selected = Number(card.getAttribute('data-idx')); 
        renderLatest(); renderAbstract();
        elAside.classList.add('active');
    }
  }
}
function renderAbstract(){
  if(selected==null){ elAbstract.innerHTML=""; elAbsNote.style.display='block'; return; }
  elAbsNote.style.display='none';
  const p = records[selected];
  const abs = (p.abstract || "").trim();
  const safeAbs = abs ? abs.replace(/</g,"&lt;").replace(/>/g,"&gt;") : "<span class='muted'>No abstract found.</span>";
  elAbstract.innerHTML = `
    <div class="card" style="border:none; padding:0; margin:0">
      <div class="row"><span class="pill">${p.journal||""}</span> <span class="muted">${p.published||""}</span></div>
      <div style="margin-top:10px; font-weight:600; font-size:18px"><a href="${p.url}" target="_blank">${p.title}</a></div>
      <hr style="border:0; border-top:1px solid #eee; margin:15px 0">
      <div style="font-size:16px; line-height:1.6; color:#222">${safeAbs}</div>
      <div class="row" style="margin-top:20px">
        ${p.doi?`<a href="https://doi.org/${p.doi}" target="_blank" style="background:#111; color:#fff; padding:6px 12px; border-radius:8px">View Full Text</a>`:""}
      </div>
    </div>`;
}
function showError(msg){ elError.innerHTML = `<div class="error">${msg}</div>` }
async function fetchAll(){
  try{
    elBtn.disabled = true; elError.innerHTML=""; selected=null; renderAbstract(); records = []; renderLatest(); setStatus("Fetching...");
    const since = isoSince(elDays.value); const per = Number(elPer.value||20); const kw = elKw.value.trim();
    const list = elJournals.value.split(/\\n+/).map(s=>s.trim()).filter(Boolean);
    const promises = list.map(j => {
        if(j.toLowerCase().includes("biorxiv")) return null;
        return defFetch("openalex_journal", {name:j, since:since, per:per, news:elNews.checked, keywords:kw})
            .then(data => ({ status: 'fulfilled', value: data, journal: j })).catch(err => ({ status: 'rejected', reason: err, journal: j }));
    }).filter(Boolean);
    const results = await Promise.all(promises);
    const all = [], errors = [];
    const seen = new Set();
    for(const r of results){
        if(r.status === 'fulfilled'){
            if(r.value.results) all.push(...r.value.results);
        } else { console.error(r.reason); errors.push(r.journal); }
    }
    for(const item of all){
        if(!item.id || seen.has(item.id)) continue;
        seen.add(item.id);
        if(!item.abstract && item.abstract_inverted_index){
             const inv=item.abstract_inverted_index;
             if(typeof inv==="object"){
                 const pos=[]; for(const [word,idxs] of Object.entries(inv)) for(const i of idxs) pos.push([i,word]);
                 pos.sort((a,b)=>a[0]-b[0]); item.abstract = pos.map(p=>p[1]).join(" ");
             }
        }
        records.push(item);
    }
    records.sort((a, b) => new Date(b.published||0) - new Date(a.published||0));
    renderLatest();
    if(errors.length > 0) { showError(`Failed to fetch: ${errors.join(", ")}`); setStatus(`Fetched ${records.length} items (partial errors)`); }
    else setStatus(`Fetched ${records.length} items successfully`);
  }catch(e){ console.error(e); showError(e.message||String(e)); setStatus("Error"); } 
  finally { elBtn.disabled = false; }
}
[elDays, elPer, elKw, elJournals].forEach(el => {
  el.addEventListener('keydown', (e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); elBtn.click(); } });
});
document.getElementById('fetchBtn').onclick = fetchAll;
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(INDEX_HTML)

# ------------ Helpers: Dynamic ISSN Lookup (Cached) ------------
async def _get_issns(journal_name: str) -> List[str]:
    # Check cache first
    if journal_name in ISSN_CACHE:
        return ISSN_CACHE[journal_name]
    
    # Fetch from OpenAlex Sources if not known
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
            r = await client.get("https://api.openalex.org/sources", params={"search": journal_name, "mailto": CONTACT})
            if r.status_code == 200:
                data = r.json()
                results = data.get("results", [])
                if results:
                    top = results[0]
                    # Simple fuzzy check
                    if journal_name.lower() in (top.get("display_name") or "").lower():
                        issns = top.get("issn") or []
                        ISSN_CACHE[journal_name] = issns # Update Cache
                        return issns
    except Exception as e:
        print(f"Error fetching ISSNs for {journal_name}: {e}")
    
    # Cache failure as empty list to prevent re-fetching invalid names
    ISSN_CACHE[journal_name] = []
    return []

# ------------ Robust Verification Logic ------------
def is_valid_article(work: dict, allow_news: bool) -> bool:
    """
    Strictly filters out non-research items.
    """
    # 1. Check Explicit Types (Crossref/OpenAlex)
    genre = (work.get("type_crossref") or work.get("type") or "").lower()
    if any(k in genre for k in ["retraction", "correction", "erratum", "addendum"]):
        return False
    
    if allow_news:
        return True

    # 2. Check Title against "News" patterns
    title = (work.get("title") or "").lower()
    if NON_RESEARCH_TITLE_RE.search(title):
        return False

    if any(k in genre for k in ["editorial", "news", "comment", "book-review"]):
        return False

    # 3. Check Abstract Length (CRITICAL for catching News snippets)
    # News items often have 0 or very short abstracts (< 50 chars).
    abstract = work.get("abstract_inverted_index") or work.get("abstract")
    length = 0
    if isinstance(abstract, str):
        length = len(abstract)
    elif isinstance(abstract, dict):
        length = len(abstract) # rough proxy for word count in inverted index
    
    # Require at least some abstract content for "Research" papers
    return length >= 40 

# ------------ OpenAlex logic (Simplified) ------------
async def _collect_openalex(params: dict, want: int, allow_news: bool) -> List[Dict[str, Any]]:
    results = []
    cursor = "*"
    
    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        # Max 5 pages of fetching per journal
        for _ in range(5):
            if len(results) >= want:
                break
                
            q = dict(params)
            q["cursor"] = cursor
            q["per_page"] = min(200, max(50, want * 2))
            
            try:
                r = await client.get("https://api.openalex.org/works", params=q)
                if r.status_code != 200:
                    break
                
                data = r.json()
                items = data.get("results", [])
                if not items:
                    break
                
                # Apply Robust Filter locally
                for w in items:
                    if is_valid_article(w, allow_news):
                        results.append(w)
                    
                cursor = data.get("meta", {}).get("next_cursor")
                if not cursor:
                    break
            except Exception:
                break
                
    return results[:want]

def _normalize_work(w: Dict[str, Any], fallback_journal: str) -> Dict[str, Any]:
    raw_doi = w.get("doi") or ""
    return {
        "id": w.get("id"),
        "title": w.get("title") or "[No Title]",
        "published": w.get("publication_date") or w.get("created_date") or "",
        "journal": ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or fallback_journal,
        "doi": raw_doi.replace("https://doi.org/", ""),
        "url": raw_doi if raw_doi.startswith("http") else (w.get("primary_location") or {}).get("landing_page_url"),
        "abstract": w.get("abstract"),
        "abstract_inverted_index": w.get("abstract_inverted_index")
    }

# ------------ API route ------------
@app.get("/api/openalex_journal")
async def api_openalex_journal(name: str, since: str, per: int = 20, news: bool = False, keywords: str = ""):
    issns = await _get_issns(name)
    
    # 3. PERFORMANCE: Build filter string strictly.
    type_filter = "type:article|review,is_paratext:false" 
    if not news:
        type_filter += ",type_crossref:!editorial|news-item|comment|letter|book-review|retraction|correction"
    
    # Base filter
    filters = [
        f"from_publication_date:{since}",
        type_filter
    ]
    
    if keywords:
        filters.append(f"title_and_abstract.search:{keywords}")

    # OPTIMIZATION: If we have ISSNs, use them. If not, use Display Name.
    if issns:
        filters.append(f"locations.source.issn:{'|'.join(issns)}")
    else:
        filters.append(f"locations.source.display_name.search:{name}")

    query_params = {
        "filter": ",".join(filters),
        "sort": "publication_date:desc",
        "mailto": CONTACT
    }

    # Fetch slightly more than needed to account for duplicates we might drop
    raw_results = await _collect_openalex(query_params, want=per + 5, allow_news=news)
    
    # Normalize first so we have clean DOIs
    normalized = [_normalize_work(w, name) for w in raw_results]

    # 4. FIX: Dedupe by DOI (Restore deduplication logic)
    seen_dois = set()
    unique_results = []
    for w in normalized:
        # Use DOI if available, otherwise fallback to ID
        identifier = w.get("doi") or w.get("id")
        if identifier in seen_dois:
            continue
        seen_dois.add(identifier)
        unique_results.append(w)
    
    # Trim back down to the requested amount
    final_results = unique_results[:per]
    
    return JSONResponse({
        "status": 200,
        "results": final_results,
        "requested_per_journal": per,
        "delivered": len(final_results),
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)