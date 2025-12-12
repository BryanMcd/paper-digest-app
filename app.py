# app.py
import os, re, html, asyncio
from typing import List, Dict, Any, Set
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
UA = f"PaperDigest/0.6 (+mailto:{CONTACT})"
HEADERS = {"User-Agent": UA, "Accept": "application/json"}

# Hardcoded cache for speed, but we will now also look up unknowns dynamically
JOURNAL_ISSNS: Dict[str, List[str]] = {
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

# Normalized set for safer checking
ABSTRACT_LEN_WHITELIST = {
    "nature", "science", "cell", "immunity", "nature immunology", "nature medicine",
    "pnas", "science immunology", "science translational medicine",
    "nature biotechnology", "nature aging", "journal of clinical investigation",
}

NON_RESEARCH_TITLE_RE = re.compile(
    r"(?i)(news|news & views|world view|editorial|comment(ary)?|perspective|opinion|careers|podcast|interview|q.?a|toolbox|technology feature|research briefing|outlook|correspondence|matters arising|briefing)"
)

STRICT_RESEARCH = (
    ",is_paratext:false,"
    "type:article," 
    "type_crossref:!editorial|news-item|comment|letter|book-review|retraction|correction|erratum|addendum"
)

# ---------------- UI (Master-Detail with Parallel Fetch) ----------------
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
    .controls{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px}
    input,button,textarea{padding:8px 10px;border:1px solid #ddd;border-radius:12px;font-family:inherit}
    button{background:#111;color:#fff;border-color:#111;cursor:pointer}
    button:disabled{opacity:0.5;cursor:not-allowed}
    
    main{display:grid;grid-template-columns:3fr 2fr;gap:24px; position: relative;}
    
    /* Desktop Sidebar */
    aside {
      position: fixed;
      right: 0;
      top: 240px; /* approximates header height */
      width: 35%; 
      height: calc(100vh - 240px);
      overflow-y: auto;
      background: #fff;
      box-shadow: -4px 0 12px rgba(0,0,0,0.05);
      border-left: 1px solid #eee;
      padding: 20px;
      z-index: 50;
    }
    
    /* Mobile Responsive Styles */
    @media (max-width: 900px){
      main{grid-template-columns:1fr} 
      .controls{grid-template-columns:repeat(2,minmax(0,1fr))}
      aside {
        display: none; /* Hidden by default on mobile */
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        width: 100%; height: 100%;
        background: #fff;
        z-index: 200;
        padding: 20px;
        box-shadow: none;
      }
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
    textarea{
        width:100%;
        height:120px; 
        box-sizing:border-box; /* Includes padding in height calc */
        display:block;         /* Removes invisible space at the bottom */
        }
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
      <label class="muted">Days back<br><input id="days" type="number" value="120"></label>
      <label class="muted">Per journal<br><input id="per" type="number" value="20"></label>
      <div></div>
      <label class="muted" style="grid-column:span 2">Journals (one per line)<br><textarea id="journals"></textarea></label>
      <button id="fetchBtn" style="height:120px; align-self:end;">Fetch Papers</button>
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
    Data from <a href="https://docs.openalex.org/" target="_blank">OpenAlex</a>.
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
const elJournals=document.getElementById('journals');
const elBtn=document.getElementById('fetchBtn');

elJournals.value = DEFAULT_JOURNALS.join("\\n");

let records=[], selected=null;
function setStatus(t){ elStatus.textContent = t }

function closeAbstract() {
    elAside.classList.remove('active');
}

function renderLatest(){
  elLatest.innerHTML = records.map((p,i)=>`
    <div class="card ${selected===i?'selected':''}" data-idx="${i}">
      <div class="row"><span class="pill">${p.journal||""}</span> <span class="muted">${p.published||""}</span></div>
      <div style="margin-top:6px"><a href="${p.url}" target="_blank" onclick="event.stopPropagation()"><strong>${p.title}</strong></a></div>
      <div class="row" style="margin-top:6px">
        ${p.doi?`<span class="muted">DOI: ${p.doi}</span>`:""}
      </div>
    </div>`).join("");
  
  for(const card of elLatest.querySelectorAll('.card')){
    card.onclick = ()=>{ 
        selected = Number(card.getAttribute('data-idx')); 
        renderLatest(); 
        renderAbstract();
        elAside.classList.add('active'); // Show mobile modal
    }
  }
}

function renderAbstract(){
  if(selected==null){ elAbstract.innerHTML=""; elAbsNote.style.display='block'; return; }
  elAbsNote.style.display='none';
  const p = records[selected];
  const abs = (p.abstract || "").trim();
  const safeAbs = abs
    ? abs.replace(/</g,"&lt;").replace(/>/g,"&gt;")
    : "<span class='muted'>No abstract found for this item.</span>";
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
    elBtn.disabled = true;
    elError.innerHTML=""; selected=null; renderAbstract();
    records = []; renderLatest();
    setStatus("Fetching...");

    const since = isoSince(elDays.value);
    const per = Number(elPer.value||20);
    const list = elJournals.value.split(/\\n+/).map(s=>s.trim()).filter(Boolean);
    
    // Parallel Fetching
    const promises = list.map(j => {
        if(j.toLowerCase().includes("biorxiv")) return null;
        return defFetch("openalex_journal", {name:j, since:since, per:per})
            .then(data => ({ status: 'fulfilled', value: data, journal: j }))
            .catch(err => ({ status: 'rejected', reason: err, journal: j }));
    }).filter(Boolean);

    const results = await Promise.all(promises);
    
    const all = [];
    const errors = [];

    for(const r of results){
        if(r.status === 'fulfilled'){
            if(r.value.results) all.push(...r.value.results);
        } else {
            console.error(r.reason);
            errors.push(r.journal);
        }
    }

    // Deduping across journals (just in case)
    const seen = new Set();
    const unique = [];
    for(const item of all){
        if(!item.id) continue;
        if(seen.has(item.id)) continue;
        seen.add(item.id);
        
        // Post-processing abstract structure (reconstruct from inverted index if needed)
        if(!item.abstract && item.abstract_inverted_index){
             const inv=item.abstract_inverted_index;
             if(typeof inv==="object"){
                 const pos=[]; 
                 for(const [word,idxs] of Object.entries(inv)){
                     for(const i of idxs) pos.push([i,word])
                 } 
                 pos.sort((a,b)=>a[0]-b[0]); 
                 item.abstract = pos.map(p=>p[1]).join(" ");
             }
        }
        unique.push(item);
    }

    unique.sort((a, b) => {
      const da = new Date(a.published || 0);
      const db = new Date(b.published || 0);
      return db - da;
    });

    records = unique;
    renderLatest();
    
    if(errors.length > 0){
        showError(`Failed to fetch: ${errors.join(", ")}`);
        setStatus(`Fetched ${records.length} items (partial errors)`);
    } else {
        setStatus(`Fetched ${records.length} items successfully`);
    }

  }catch(e){
    console.error(e);
    showError(e.message||String(e));
    setStatus("Error");
  } finally {
      elBtn.disabled = false;
  }
}
document.getElementById('fetchBtn').onclick = fetchAll;
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(INDEX_HTML)

async def _openalex_query(params: dict):
    q = dict(params)
    q["mailto"] = CONTACT
    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        r = await client.get("https://api.openalex.org/works", params=q)
    return r

# ------------ Helpers: Dynamic ISSN Lookup ------------
async def _get_issns_dynamic(journal_name: str) -> List[str]:
    if journal_name in JOURNAL_ISSNS:
        return JOURNAL_ISSNS[journal_name]
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as client:
            r = await client.get("https://api.openalex.org/sources", params={"search": journal_name, "mailto": CONTACT})
            if r.status_code == 200:
                data = r.json()
                results = data.get("results", [])
                if results:
                    top = results[0]
                    if journal_name.lower() in (top.get("display_name") or "").lower():
                        return top.get("issn") or []
    except Exception as e:
        print(f"Error fetching ISSNs for {journal_name}: {e}")
        return []
    return []

# ------------ Crossref helpers ------------
JATS_TAG_RE = re.compile(r"<[^>]+>")

def _jats_to_text(jats: str) -> str:
    if not isinstance(jats, str):
        return ""
    txt = JATS_TAG_RE.sub("", jats)
    return html.unescape(txt).strip()

async def _crossref_recent_by_issn(issns: List[str], since_iso: str, want: int = 20, max_pages: int = 3) -> List[Dict[str, Any]]:
    if not issns:
        return []
    target_issn = issns[0]
    rows = min(200, max(50, want * 2))
    cr_items: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": UA, "Accept": "application/json"}) as client:
        cursor = "*"
        pages = 0
        while len(cr_items) < want and pages < max_pages:
            url = f"https://api.crossref.org/journals/{target_issn}/works"
            params = {
                "filter": f"from-pub-date:{since_iso},type:journal-article",
                "sort": "published",
                "order": "desc",
                "rows": rows,
                "cursor": cursor,
                "mailto": CONTACT,
            }
            try:
                r = await client.get(url, params=params)
                if r.status_code != 200:
                    break
                j = r.json()
                msg = j.get("message", {})
                items = msg.get("items", []) or []
                if not items:
                    break
                for it in items:
                    doi = (it.get("DOI") or "").lower().strip()
                    title = " ".join(it.get("title") or [])[:500]
                    # Date extraction
                    date_parts = (
                        (it.get("published-online") or {}).get("date-parts")
                        or (it.get("published-print") or {}).get("date-parts")
                        or (it.get("issued") or {}).get("date-parts")
                        or []
                    )
                    pubdate = ""
                    if date_parts and isinstance(date_parts[0], list):
                        parts = date_parts[0] + [1, 1, 1]
                        y, m, d = parts[0], parts[1], parts[2]
                        pubdate = f"{y:04d}-{m:02d}-{d:02d}"

                    abstract = _jats_to_text(it.get("abstract", ""))
                    journal = " ".join(it.get("container-title") or [])

                    cr_items.append({
                        "id": f"crossref:{doi}" if doi else None,
                        "title": title,
                        "abstract": abstract,
                        "doi": f"https://doi.org/{doi}" if doi else None,
                        "publication_date": pubdate,
                        "host_venue": {"display_name": journal},
                        "primary_location": {"landing_page_url": f"https://doi.org/{doi}" if doi else None},
                        "type": "article",
                        "type_crossref": "journal-article",
                    })

                cursor = msg.get("next-cursor") or None
                if not cursor:
                    break
                pages += 1
            except Exception:
                break

    return cr_items[:want]

def _dedupe_on_ids_and_doi(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen_ids, seen_doi, out = set(), set(), []
    for w in items:
        wid = w.get("id")
        doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
        if wid and wid in seen_ids:
            continue
        if doi and doi in seen_doi:
            continue
        if wid:
            seen_ids.add(wid)
        if doi:
            seen_doi.add(doi)
        out.append(w)
    return out

# ------------ OpenAlex helpers ------------
async def _collect_research(params: dict, want: int, is_research_fn, max_pages: int = 8) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    cursor, pages = "*", 0
    while len(results) < want and pages < max_pages:
        q = dict(params)
        q["cursor"] = cursor
        q["per_page"] = min(200, max(50, want * 2))
        try:
            r = await _openalex_query(q)
            if r.status_code != 200:
                break
            j = r.json()
            raw = j.get("results", []) or []
            if not raw:
                break
            filtered = [w for w in raw if is_research_fn(w)]
            results.extend(filtered)
            cursor = (j.get("meta") or {}).get("next_cursor")
            if not cursor:
                break
            pages += 1
        except Exception:
            break
    return results[:want]

def is_probably_research(work: dict) -> bool:
    title = (work.get("title") or "").lower()
    if NON_RESEARCH_TITLE_RE.search(title):
        return False
    genre = (work.get("type_crossref") or work.get("type") or "").lower()
    if any(k in genre for k in ["editorial", "news", "comment", "retraction", "correction", "erratum", "addendum", "book-review"]):
        return False
    
    venue = (work.get("host_venue") or {}).get("display_name") or ""
    # Try primary_location if host_venue is empty (OpenAlex)
    if not venue:
        venue = ((work.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
        
    if venue.lower().strip() in ABSTRACT_LEN_WHITELIST:
        return True
        
    abstract = work.get("abstract_inverted_index") or work.get("abstract")
    if isinstance(abstract, str):
        return len(abstract) >= 50
    if isinstance(abstract, dict):
        return len(abstract) >= 10
    return False

# ------------ Data Normalization for Frontend ------------
def _normalize_work(w: Dict[str, Any], fallback_journal: str = "") -> Dict[str, Any]:
    """
    Convert raw OpenAlex/Crossref data into the clean, flattened format
    the frontend expects (published, journal, url, clean DOI, etc).
    """
    # 1. Title
    title = w.get("title") or "[No Title]"
    
    # 2. DOI (Strip prefix for clean display/id, keep full for fallback)
    raw_doi = w.get("doi") or ""
    clean_doi = raw_doi.replace("https://doi.org/", "")
    
    # 3. URL (Use DOI link if possible, else landing page)
    url = raw_doi if raw_doi.startswith("http") else (w.get("primary_location") or {}).get("landing_page_url")
    if not url:
        url = w.get("id") # Fallback to OpenAlex ID
        
    # 4. Date
    published = w.get("publication_date") or w.get("created_date") or ""
    
    # 5. Journal Name - Robust Lookup
    # Try primary_location (standard OpenAlex)
    journal = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
    
    # Try host_venue (old OpenAlex / Crossref helper)
    if not journal:
        journal = (w.get("host_venue") or {}).get("display_name")
        
    # Fallback to the search term (restores original app behavior)
    if not journal:
        journal = fallback_journal or "Unknown Journal"
    
    # 6. Abstract (Pass through inverted or text; frontend handles inverted)
    abstract = w.get("abstract")
    abstract_inverted_index = w.get("abstract_inverted_index")
    
    return {
        "id": w.get("id"),
        "title": title,
        "published": published,
        "journal": journal,
        "doi": clean_doi,
        "url": url,
        "abstract": abstract,
        "abstract_inverted_index": abstract_inverted_index
    }

# ------------ API route ------------
@app.get("/api/openalex_journal")
async def api_openalex_journal(name: str, since: str, per: int = 20):
    # 1. Resolve ISSNs (Static Cache OR Dynamic Fetch)
    issns = await _get_issns_dynamic(name)

    ox_filters = [
        {"filter": f"locations.source.issn:{'|'.join(issns)},from_publication_date:{since}{STRICT_RESEARCH}", "sort": "publication_date:desc"} if issns else None,
        {"filter": f"locations.source.display_name.search:{name},from_publication_date:{since}{STRICT_RESEARCH}", "sort": "publication_date:desc"},
        {"filter": f"locations.source.issn:{'|'.join(issns)},from_created_date:{since}{STRICT_RESEARCH}", "sort": "publication_date:desc"} if issns else None,
        {"filter": f"locations.source.display_name.search:{name},from_created_date:{since}{STRICT_RESEARCH}", "sort": "publication_date:desc"},
    ]
    ox_results: List[Dict[str, Any]] = []

    # 2. OpenAlex Collection
    for q in [p for p in ox_filters if p]:
        if len(ox_results) >= per:
            break
        need = per - len(ox_results)
        ox_results += await _collect_research(q, need, is_probably_research, max_pages=6)

    # 3. Crossref Fallback (requires ISSNs)
    if len(ox_results) < per and issns:
        need = per - len(ox_results)
        cr = await _crossref_recent_by_issn(issns, since_iso=since, want=need, max_pages=2)
        ox_results += cr

    merged = _dedupe_on_ids_and_doi(ox_results)
    
    # 4. NORMALIZE BEFORE SENDING TO FRONTEND
    # Pass 'name' as fallback_journal so "Unknown Journal" becomes "The Lancet" (or whatever was searched)
    normalized = [_normalize_work(w, fallback_journal=name) for w in merged]
    
    normalized.sort(key=lambda w: str(w.get("published") or ""), reverse=True)
    normalized = normalized[:per]

    return JSONResponse({
        "status": 200,
        "results": normalized,
        "requested_per_journal": per,
        "delivered": len(normalized),
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)