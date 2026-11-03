"""Local web dashboard over the tracker. Binds to 127.0.0.1 only; nothing leaves your machine."""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import db, stats

STATUSES = ["new", "matched", "ready", "drafted", "applied", "interview", "offer", "rejected", "manual", "skipped", "closed", "failed"]
LIST_COLS = "id,source,title,company,location,salary,score,status,method,email,url,apply_url,reasons,gaps,notes,updated,resume_path,cover_letter IS NOT NULL AS has_cover"


def _rows(sql: str, args=()) -> list[dict]:
    return [dict(r) for r in db.conn().execute(sql, args).fetchall()]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, body: bytes, ctype="application/json", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj, default=str).encode(), code=code)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(PAGE.encode(), "text/html; charset=utf-8")
        if u.path == "/api/jobs":
            st = parse_qs(u.query).get("status", [""])[0]
            sql = f"SELECT {LIST_COLS} FROM jobs" + (" WHERE status=?" if st else "") + " ORDER BY COALESCE(score,0) DESC, updated DESC LIMIT 2000"
            return self._json(_rows(sql, (st,) if st else ()))
        if u.path == "/api/stats":
            f = stats.funnel()
            return self._json({**f, "gaps": stats.top_gaps(10), "statuses": STATUSES})
        m = re.fullmatch(r"/api/job/([^/]+)", u.path)
        if m:
            rows = _rows("SELECT * FROM jobs WHERE id=?", (m[1].replace("%3A", ":"),))
            return self._json(rows[0] if rows else {}, 200 if rows else 404)
        m = re.fullmatch(r"/resume/([^/]+)", u.path)
        if m:
            r = _rows("SELECT resume_path FROM jobs WHERE id=?", (m[1].replace("%3A", ":"),))
            p = Path(r[0]["resume_path"]) if r and r[0]["resume_path"] else None
            if p and p.exists():
                return self._send(p.read_bytes(), "application/pdf")
        self._send(b"{}", code=404)

    def do_POST(self):
        # A web page on another site must not be able to change your tracker: require our header and a local Origin.
        origin = self.headers.get("Origin", "")
        if self.headers.get("X-Sidekick") != "1" or (origin and not re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$", origin)):
            return self._json({"error": "forbidden"}, 403)
        m = re.fullmatch(r"/api/job/([^/]+)/status", urlparse(self.path).path)
        if not m:
            return self._json({}, 404)
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        if body.get("status") not in STATUSES:
            return self._json({"error": "bad status"}, 400)
        db.update(m[1].replace("%3A", ":"), status=body["status"])
        self._json({"ok": True})


def serve(port: int = 8765, open_browser: bool = True) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    if open_browser:
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{srv.server_port}")
    return srv


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JobSidekick</title><style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1b1f27;--dim:#667085;--line:#e4e7ec;--brand:#2a4a8a;--good:#1a7f4b;--warn:#b54708;--bad:#b42318}
@media(prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1d2128;--ink:#e8eaee;--dim:#98a2b3;--line:#2c313a;--brand:#8aa8ee;--good:#5bd08f;--warn:#f5a54a;--bad:#f1827a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
header{padding:20px 24px 8px}h1{margin:0;font-size:20px}h1 span{color:var(--dim);font-weight:400;font-size:14px;margin-left:8px}
.cards{display:flex;gap:12px;flex-wrap:wrap;padding:8px 24px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 16px;min-width:110px}
.card b{display:block;font-size:22px}.card small{color:var(--dim)}
.bar{display:flex;gap:8px;flex-wrap:wrap;padding:10px 24px;align-items:center}
.chip{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:99px;padding:4px 12px;cursor:pointer;font-size:13px}
.chip.on{background:var(--brand);color:#fff;border-color:var(--brand)}input[type=search]{flex:1;min-width:180px;max-width:320px;padding:6px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
main{padding:0 24px 40px}table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;color:var(--dim);text-transform:uppercase;letter-spacing:.5px}
tr.row{cursor:pointer}tr.row:hover td{background:color-mix(in srgb,var(--brand) 6%,transparent)}
.score{display:inline-block;min-width:26px;text-align:center;border-radius:6px;padding:1px 6px;font-weight:700;color:#fff}.s5,.s4{background:var(--good)}.s3{background:var(--warn)}.s2,.s1{background:var(--bad)}.s0{background:var(--dim)}
.tag{font-size:12px;color:var(--dim)}select{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:2px 4px}
.detail td{background:color-mix(in srgb,var(--brand) 4%,var(--card));white-space:pre-wrap}.detail a{color:var(--brand)}
@media(max-width:700px){.hide-m{display:none}}
</style></head><body>
<header><h1>JobSidekick<span id="sub"></span></h1></header>
<div class="cards" id="cards"></div>
<div class="bar" id="chips"></div>
<div class="bar"><input type="search" id="q" placeholder="Search title or company"></div>
<main><table><thead><tr><th>Score</th><th>Job</th><th class="hide-m">How</th><th class="hide-m">Source</th><th>Status</th></tr></thead><tbody id="rows"></tbody></table>
<p id="gaps" class="tag" style="margin-top:14px"></p></main>
<script>
let jobs=[],status='',st={statuses:[]};const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function load(){st=await (await fetch('/api/stats')).json();jobs=await (await fetch('/api/jobs'+(status?'?status='+status:''))).json();draw()}
function draw(){
 $('#sub').textContent=` ${st.found} jobs tracked`;
 $('#cards').innerHTML=[['found','Found'],['matched','Matched'],['applied_or_drafted','Applied / drafted'],['interviews','Interviews'],['offers','Offers']].map(([k,l])=>`<div class="card"><b>${st[k]??0}</b><small>${l}</small></div>`).join('');
 const counts=st.by_status||{};
 $('#chips').innerHTML=['',...st.statuses.filter(s=>counts[s])].map(s=>`<button class="chip ${s===status?'on':''}" data-s="${s}">${s||'all'}${s?' '+counts[s]:''}</button>`).join('');
 const q=$('#q').value.toLowerCase();
 $('#rows').innerHTML=jobs.filter(j=>!q||(j.title+' '+j.company).toLowerCase().includes(q)).map(j=>`
 <tr class="row" data-id="${esc(j.id)}"><td><span class="score s${j.score||0}">${j.score??'–'}</span></td>
 <td><b>${esc(j.title)}</b><br><span class="tag">${esc(j.company)} · ${esc((j.location||'').slice(0,50))} ${esc(j.salary||'')}</span></td>
 <td class="hide-m">${esc(j.method||'')}${j.email?'<br><span class="tag">'+esc(j.email)+'</span>':''}</td><td class="hide-m tag">${esc(j.source)}</td>
 <td><select data-id="${esc(j.id)}">${st.statuses.map(s=>`<option ${s===j.status?'selected':''}>${s}</option>`).join('')}</select></td></tr>`).join('');
 $('#gaps').textContent=st.gaps&&st.gaps.length?'Skills jobs ask for that your CV lacks: '+st.gaps.map(g=>g[0]+' ('+g[1]+')').join(', '):'';
}
document.addEventListener('click',async e=>{
 const c=e.target.closest('.chip');if(c){status=c.dataset.s;return load()}
 if(e.target.tagName==='SELECT'||e.target.closest('.detail'))return;
 const r=e.target.closest('tr.row');if(!r)return;
 const nx=r.nextElementSibling;if(nx&&nx.classList.contains('detail')){nx.remove();return}
 const j=await (await fetch('/api/job/'+encodeURIComponent(r.dataset.id))).json();
 const t=document.createElement('tr');t.className='detail';
 t.innerHTML=`<td></td><td colspan="4"><b>Why this score:</b> ${esc(j.reasons)}\n${j.gaps&&j.gaps!='[]'?'<b>Gaps:</b> '+esc(JSON.parse(j.gaps).join(', '))+'\n':''}${j.notes?'<b>Notes:</b> '+esc(j.notes)+'\n':''}<a href="${esc(j.url)}" target="_blank" rel="noopener">Open posting</a>${j.resume_path?' · <a href="/resume/'+encodeURIComponent(j.id)+'" target="_blank">Tailored resume (PDF)</a>':''}${j.cover_letter?'\n\n<b>Cover letter</b>\n'+esc(j.cover_letter):''}</td>`;
 r.after(t)});
document.addEventListener('change',async e=>{if(e.target.tagName!=='SELECT')return;
 await fetch('/api/job/'+encodeURIComponent(e.target.dataset.id)+'/status',{method:'POST',headers:{'X-Sidekick':'1','Content-Type':'application/json'},body:JSON.stringify({status:e.target.value})});load()});
$('#q').addEventListener('input',draw);load();
</script></body></html>"""
