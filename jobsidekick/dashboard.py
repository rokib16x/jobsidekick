"""Local web app over the tracker: browse, pick, run steps, see the funnel. Binds to 127.0.0.1 only; nothing leaves your machine."""
from __future__ import annotations

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import answers, db, stats
from . import config as C
from .runner import ACTIONS, RUNNER

STATUSES = ["new", "matched", "ready", "drafted", "applied", "interview", "offer", "rejected", "manual", "skipped", "closed", "failed"]
LIST_COLS = "id,source,title,company,location,salary,score,status,method,email,url,apply_url,reasons,gaps,notes,created,updated,resume_path,picked,cover_letter IS NOT NULL AS has_cover"
UI = Path(__file__).parent / "ui"
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml"}


def _rows(sql: str, args=()) -> list[dict]:
    return [dict(r) for r in db.conn().execute(sql, args).fetchall()]


def activity(span: str) -> dict:
    """Counts per time bucket for the timeline: found, scored, applied, replies."""
    now = time.time()
    n, step = {"day": (24, 3600), "week": (7, 86400), "month": (30, 86400), "year": (12, 30 * 86400)}.get(span, (7, 86400))
    start = now - n * step
    rows = {
        "Found": _rows("SELECT created t FROM jobs WHERE created >= ?", (start,)),
        "Scored": _rows("SELECT updated t FROM jobs WHERE score IS NOT NULL AND updated >= ?", (start,)),
        "Prepared": _rows("SELECT updated t FROM jobs WHERE status IN ('ready','drafted') AND updated >= ?", (start,)),
        "Applied": _rows("SELECT updated t FROM jobs WHERE status IN ('applied','drafted') AND updated >= ?", (start,)),
        "Replies": _rows("SELECT updated t FROM jobs WHERE status IN ('interview','offer','rejected') AND updated >= ?", (start,)),
    }
    out = {}
    for name, rs in rows.items():
        buckets = [0] * n
        for r in rs:
            buckets[min(n - 1, int((r["t"] - start) // step))] += 1
        out[name] = buckets
    return {"start": start, "step": step, "n": n, "rows": out}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
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

    def _body(self) -> dict:
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")

    @staticmethod
    def _jid(s: str) -> str:
        return s.replace("%3A", ":")

    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)
        if path == "/":
            return self._send((UI / "index.html").read_bytes(), TYPES[".html"])
        m = re.fullmatch(r"/ui/([\w.-]+)", path)
        if m and (UI / m[1]).is_file() and (UI / m[1]).suffix in TYPES:
            return self._send((UI / m[1]).read_bytes(), TYPES[(UI / m[1]).suffix])
        if path == "/api/jobs":
            st = q.get("status", [""])[0]
            sql = f"SELECT {LIST_COLS} FROM jobs" + (" WHERE status=?" if st else "") + " ORDER BY COALESCE(score,0) DESC, updated DESC LIMIT 3000"
            return self._json(_rows(sql, (st,) if st else ()))
        if path == "/api/stats":
            f = stats.funnel()
            return self._json({**f, "gaps": stats.top_gaps(12), "statuses": STATUSES, "by_source": stats.by_group("source"), "by_method": stats.by_group("method")})
        if path == "/api/profile":
            try:
                prof = C.load_profile(C.load())
            except SystemExit:
                prof = {}
            b, w, loc = prof.get("basics", {}), prof.get("work", {}), prof.get("location", {})
            return self._json({"name": b.get("full_name", "You"), "title": w.get("current_title", ""), "place": ", ".join(x for x in (loc.get("city"), loc.get("country")) if x)})
        if path == "/api/settings":
            try:
                cfg = C.load()
            except SystemExit:
                return self._json({})
            return self._json({"mode": cfg.apply.mode, "provider": cfg.llm.provider, "models": cfg.models.model_dump(), "min_score": cfg.search.min_score, "email_via": cfg.email.via,
                               "titles": cfg.search.titles, "resume": cfg.resume.enabled, "max_per_run": cfg.apply.max_per_run, "sources_on": [k for k, v in cfg.sources.model_dump().items() if v is True]})
        if path == "/api/activity":
            return self._json(activity(q.get("span", ["week"])[0]))
        if path == "/api/answers":
            return self._json([{"question": a, "answer": b} for a, b in answers.all_saved()])
        if path == "/api/run":
            return self._json(RUNNER.get(q.get("id", [None])[0]) or {})
        m = re.fullmatch(r"/api/job/([^/]+)", path)
        if m:
            rows = _rows("SELECT * FROM jobs WHERE id=?", (self._jid(m[1]),))
            return self._json(rows[0] if rows else {}, 200 if rows else 404)
        m = re.fullmatch(r"/resume/([^/]+)", path)
        if m:
            r = _rows("SELECT resume_path FROM jobs WHERE id=?", (self._jid(m[1]),))
            p = Path(r[0]["resume_path"]) if r and r[0]["resume_path"] else None
            if p and p.exists():
                return self._send(p.read_bytes(), "application/pdf")
        self._send(b"{}", code=404)

    def do_POST(self):
        # A web page on another site must not be able to change your tracker or start jobs: require our header and a local Origin.
        origin = self.headers.get("Origin", "")
        if self.headers.get("X-Sidekick") != "1" or (origin and not re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$", origin)):
            return self._json({"error": "forbidden"}, 403)
        path, body = urlparse(self.path).path, self._body()
        if path == "/api/run":
            if body.get("action") not in ACTIONS:
                return self._json({"error": "unknown action"}, 400)
            try:
                return self._json(RUNNER.start(body["action"], str(body.get("query", ""))[:200], str(body.get("url", ""))[:1000]))
            except RuntimeError as e:
                return self._json({"error": str(e)}, 409)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
        if path == "/api/answers":
            if body.get("question") and body.get("answer"):
                answers.remember(str(body["question"])[:300], str(body["answer"])[:2000])
            return self._json({"ok": True})
        m = re.fullmatch(r"/api/job/([^/]+)/pick", path)
        if m:
            db.update(self._jid(m[1]), picked=1 if body.get("picked") else 0)
            return self._json({"ok": True})
        m = re.fullmatch(r"/api/job/([^/]+)/status", path)
        if m:
            if body.get("status") not in STATUSES:
                return self._json({"error": "bad status"}, 400)
            db.update(self._jid(m[1]), status=body["status"])
            return self._json({"ok": True})
        self._json({}, 404)


def serve(port: int = 8765, open_browser: bool = True) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    if open_browser:
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{srv.server_port}")
    return srv
