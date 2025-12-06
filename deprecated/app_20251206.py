# app_openalex_v3_abstract_ui_fixed.py
import os, re, html
from typing import List, Dict, Any
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
UA = f"PaperDigest/0.3 (+mailto:{CONTACT})"
HEADERS = {"User-Agent": UA, "Accept": "application/json"}

# Venue → ISSNs (helps OpenAlex match precisely; fallback when needed)
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

# Some venues often have missing/short abstracts on OpenAlex even for research items
ABSTRACT_LEN_WHITELIST = {
    "Nature", "Science", "Cell", "Immunity", "Nature Immunology", "Nature Medicine",
    "PNAS", "Science Immunology", "Science Translational Medicine",
    "Nature Biotechnology", "Nature Aging", "Journal of Clinical Investigation",
}

# Title patterns to exclude commentary/non-research
NON_RESEARCH_TITLE_RE = re.compile(
    r"(?i)(news|news & views|world view|editorial|comment(ary)?|perspective|opinion|careers|podcast|interview|q.?a|toolbox|technology feature|research briefing|outlook|correspondence|matters arising|briefing)"
)

# Strict research-only filters
STRICT_RESEARCH = (
    ",is_paratext:false,"
    "type:article,"  # OpenAlex-native type; less brittle than type_crossref
    # keep out common non-research via crossref-type negation when present
    "type_crossref:!editorial|news-item|comment|letter|book-review|retraction|correction|erratum|addendum"
)

# ---------------- UI (right column shows Abstract) ----------------
INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Paper Digest</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#fff;color:#111}
    header{position:sticky;top:0;background:rgba(255,255,255,.9);border-bottom:1px solid #eee}
    .wrap{max-width:1100px;margin:0 auto;padding:16px}
    h1{font-size:22px;margin:0 0 4px}
    .controls{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px}
    input,button,textarea{padding:8px 10px;border:1px solid #ddd;border-radius:12px}
    button{background:#111;color:#fff;border-color:#111;cursor:pointer}
    main{display:grid;grid-template-columns:3fr 2fr;gap:24px}
    aside {
      position: fixed;
      right: 0;
      top: 300px;                   /* adjust so it sits just below your header */
      width: 35%;                   /* matches your original 3fr/2fr split roughly */
      height: calc(100vh - 120px);  /* fill the viewport minus header/footer */
      overflow-y: auto;
      background: #fff;
      box-shadow: -4px 0 12px rgba(0,0,0,0.05);
      border-left: 1px solid #eee;
      padding: 16px;
      border-radius: 0 0 0 12px;    /* subtle rounding */
      z-index: 50;
    }
    @media (max-width: 900px){main{grid-template-columns:1fr} .controls{grid-template-columns:repeat(2,minmax(0,1fr))}}
    ul{list-style:none;padding:0;margin:0}
    .card{border:1px solid #e5e5e5;border-radius:16px;padding:14px;margin:12px 0}
    .muted{color:#666;font-size:13px}
    .row{display:flex;gap:8px;align-items:center;color:#555;font-size:14px}
    a{color:#0b57d0;text-decoration:none} a:hover{text-decoration:underline}
    .error{background:#fff5f5;color:#b00020;border:1px solid #f2c9c9;padding:10px;border-radius:12px;margin-bottom:12px;font-size:13px;white-space:pre-wrap}
    .pill{display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid #ddd;font-size:12px}
    textarea{width:100%;height:120px}
    .selected{box-shadow:0 0 0 2px #111}
    .status{margin:10px 0;padding:8px 12px;border:1px solid #eee;border-radius:10px;background:#fafafa;font-size:13px}
  </style>
</head>
<body>
<header>
  <div class="wrap">
    <h1>Paper Digest</h1>
    <div class="muted">Research-only; right column shows the selected paper's abstract.</div>
    <div class="controls" style="margin-top:10px">
      <label class="muted">Days back<br><input id="days" type="number" value="120"></label>
      <label class="muted">Per journal<br><input id="per" type="number" value="20"></label>
      <label class="muted"><input id="demo" type="checkbox"> Demo</label>
      <label class="muted" style="grid-column:span 3">Journals (one per line)<br><textarea id="journals"></textarea></label>
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

function absText(w){
  const t=w?.abstract;
  if(typeof t==="string") return t;
  const inv=w?.abstract_inverted_index;
  if(inv && typeof inv==="object"){const pos=[]; for(const [word,idxs] of Object.entries(inv)){for(const i of idxs) pos.push([i,word])} pos.sort((a,b)=>a[0]-b[0]); return pos.map(p=>p[1]).join(" ")}
  return "";
}
async function api(path, params){
  const q = new URLSearchParams(params||{}).toString();
  const r = await fetch(`/api/${path}?${q}`);
  if(!r.ok) throw new Error(`API /${path} failed (${r.status})`);
  return await r.json();
}

const elStatus=document.getElementById('status');
const elLatest=document.getElementById('latest');
const elAbstract=document.getElementById('abstract');
const elAbsNote=document.getElementById('abstractNote');
const elError=document.getElementById('error');
const elDays=document.getElementById('days');
const elPer=document.getElementById('per');
const elDemo=document.getElementById('demo');
const elJournals=document.getElementById('journals');

// show each default journal on its own line
elJournals.value = DEFAULT_JOURNALS.join("\\n").split("\\\\n").join("\\n");

let records=[], selected=null;
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
    card.onclick = ()=>{ selected = Number(card.getAttribute('data-idx')); renderLatest(); renderAbstract(); }
  }
  setStatus(`Fetched ${records.length} items across journals`);
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
    <div class="card">
      <div class="row"><span class="pill">${p.journal||""}</span> <span class="muted">${p.published||""}</span></div>
      <div style="margin-top:6px"><a href="${p.url}" target="_blank"><strong>${p.title}</strong></a></div>
      <div class="muted" style="margin-top:10px; font-size:14px; line-height:1.5">${safeAbs}</div>
      <div class="row" style="margin-top:10px">
        ${p.doi?`<a href="https://doi.org/${p.doi}" target="_blank">DOI</a>`:""}
      </div>
    </div>`;
}

function showError(msg){ elError.innerHTML = `<div class="error">${msg}</div>` }

async function fetchAll(){
  try{
    elError.innerHTML=""; selected=null; renderAbstract();
    setStatus("Fetching...");
    if(elDemo.checked){
      records = [
        {id:'d1', title:'IL-2 signaling dynamics in human Tregs', abstract:'Demo abstract...', doi:'10.1000/demo.il2', url:'https://doi.org/10.1000/demo.il2', published:'2025-10-20', journal:'Immunity'},
        {id:'d2', title:'Engineered CAR-Tregs suppress alloimmunity in mice', abstract:'Demo abstract...', doi:'10.1000/demo.cartreg', url:'https://doi.org/10.1000/demo.cartreg', published:'2025-10-19', journal:'Nature Medicine'},
        {id:'d3', title:'TLR7 agonism reshapes GC B cell selection', abstract:'Demo abstract...', doi:'10.1000/demo.tlr7', url:'https://doi.org/10.1000/demo.tlr7', published:'2025-10-18', journal:'Science Immunology'}
      ];
      renderLatest(); return;
    }
    const since = isoSince(elDays.value);
    const per = Number(elPer.value||20);
    const list = elJournals.value.split(/\\n+/).map(s=>s.trim()).filter(Boolean);
    const all=[];
    for(const j of list){
      if(j.toLowerCase().includes("biorxiv")) continue;
      const jres = await api("openalex_journal",{name:j, since:since, per:per});
      if(jres.status !== 200){ throw new Error(`OpenAlex query failed for ${j} (status ${jres.status})\\n${jres.error || ''}`) }
      for(const w of jres.results){ all.push({
        id: w?.id,
        title: w?.title || "",
        abstract: (function(){
          const t=w?.abstract;
          if(typeof t==="string") return t;
          const inv=w?.abstract_inverted_index;
          if(inv && typeof inv==="object"){const pos=[]; for(const [word,idxs] of Object.entries(inv)){for(const i of idxs) pos.push([i,word])} pos.sort((a,b)=>a[0]-b[0]); return pos.map(p=>p[1]).join(" ")}
          return "";
        })(),
        doi: (w?.doi||"").replace("https://doi.org/",""),
        url: (w?.doi ? `https://doi.org/${(w?.doi||"").replace("https://doi.org/","")}` : (w?.primary_location?.landing_page_url||w?.id)),
        published: w?.publication_date || "",
        journal: w?.host_venue?.display_name || j
      }) }
    }
    all.sort((a, b) => {
      const da = new Date(a.published || 0);
      const db = new Date(b.published || 0);
      return db - da;  // newest first
    });
    records = all;
    renderLatest();
    renderAbstract();
  }catch(e){
    console.error(e);
    showError(e.message||String(e));
    setStatus("Error");
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

# ------------ Crossref helpers (for freshest items) ------------
JATS_TAG_RE = re.compile(r"<[^>]+>")

def _jats_to_text(jats: str) -> str:
    if not isinstance(jats, str):
        return ""
    txt = JATS_TAG_RE.sub("", jats)
    return html.unescape(txt).strip()

async def _crossref_recent_by_issn(issns: List[str], since_iso: str, want: int = 20, max_pages: int = 3) -> List[Dict[str, Any]]:
    if not issns:
        return []
    rows = min(200, max(50, want * 2))
    cr_items: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": UA, "Accept": "application/json"}) as client:
        cursor = "*"
        pages = 0
        while len(cr_items) < want and pages < max_pages:
            url = f"https://api.crossref.org/journals/{issns[0]}/works"
            params = {
                "filter": f"from-pub-date:{since_iso},type:journal-article",
                "sort": "published",
                "order": "desc",
                "rows": rows,
                "cursor": cursor,
                "mailto": CONTACT,
            }
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
    return results[:want]

def _pubdate_key(w: dict) -> str:
    return str(w.get("publication_date") or w.get("from_publication_date") or w.get("publication_year") or "")

def _issns_for(name: str) -> List[str]:
    return JOURNAL_ISSNS.get(name, [])

def is_probably_research(work: dict) -> bool:
    title = (work.get("title") or "").lower()
    if NON_RESEARCH_TITLE_RE.search(title):
        return False
    genre = (work.get("type_crossref") or work.get("type") or "").lower()
    if any(k in genre for k in ["editorial", "news", "comment", "retraction", "correction", "erratum", "addendum", "book-review"]):
        return False
    venue = (work.get("host_venue") or {}).get("display_name") or ""
    if venue in ABSTRACT_LEN_WHITELIST:
        return True
    abstract = work.get("abstract_inverted_index") or work.get("abstract")
    if isinstance(abstract, str):
        return len(abstract) >= 50
    if isinstance(abstract, dict):
        return len(abstract) >= 10
    return False

# ------------ API route ------------
@app.get("/api/openalex_journal")
async def api_openalex_journal(name: str, since: str, per: int = 20):
    issns = JOURNAL_ISSNS.get(name, [])

    ox_filters = [
        {"filter": f"locations.source.issn:{'|'.join(issns)},from_publication_date:{since}{STRICT_RESEARCH}", "sort": "publication_date:desc"} if issns else None,
        {"filter": f"locations.source.display_name.search:{name},from_publication_date:{since}{STRICT_RESEARCH}", "sort": "publication_date:desc"},
        {"filter": f"locations.source.issn:{'|'.join(issns)},from_created_date:{since}{STRICT_RESEARCH}", "sort": "publication_date:desc"} if issns else None,
        {"filter": f"locations.source.display_name.search:{name},from_created_date:{since}{STRICT_RESEARCH}", "sort": "publication_date:desc"},
    ]
    ox_results: List[Dict[str, Any]] = []

    for q in [p for p in ox_filters if p]:
        if len(ox_results) >= per:
            break
        need = per - len(ox_results)
        ox_results += await _collect_research(q, need, is_probably_research, max_pages=8)

    if len(ox_results) < per and issns:
        need = per - len(ox_results)
        cr = await _crossref_recent_by_issn(issns, since_iso=since, want=need, max_pages=2)
        ox_results += cr

    merged = _dedupe_on_ids_and_doi(ox_results)
    merged.sort(key=lambda w: str(w.get("publication_date") or ""), reverse=True)
    merged = merged[:per]

    return JSONResponse({
        "status": 200,
        "results": merged,
        "requested_per_journal": per,
        "delivered": len(merged),
        "note": "OpenAlex (pubdate + created_date) with Crossref fallback by ISSN; deduped by id/DOI.",
    })
