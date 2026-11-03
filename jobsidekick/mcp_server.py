"""MCP server: lets Claude Desktop / Claude Code / any MCP client browse and manage your tracker.
Deliberately has NO tool that submits an application or sends an email."""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import config as C
from . import db, stats

mcp = MCPServer("jobsidekick")
SLIM = ("id", "title", "company", "source", "location", "salary", "score", "status", "method", "email", "url", "reasons", "notes")
STATUSES = {"new", "matched", "ready", "drafted", "applied", "interview", "offer", "rejected", "manual", "skipped", "closed"}


@mcp.tool()
def list_jobs(status: str = "ready", limit: int = 20) -> list[dict]:
    """List tracked jobs with a given status (new, matched, ready, drafted, applied, interview, offer, rejected, manual, skipped, closed), best score first."""
    return [{k: r[k] for k in SLIM} for r in db.by_status(status, min(limit, 100))]


@mcp.tool()
def get_job(job_id: str) -> dict:
    """Everything about one job: description, score reasons, skill gaps, cover letter, resume path."""
    r = db.conn().execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(r) if r else {"error": "no such job"}


@mcp.tool()
def set_status(job_id: str, status: str) -> dict:
    """Move a job to a status, e.g. mark it applied, interview, rejected or skipped."""
    if status not in STATUSES:
        return {"error": f"status must be one of {sorted(STATUSES)}"}
    db.update(job_id, status=status)
    return {"ok": True}


@mcp.tool()
def add_job_from_url(url: str) -> dict:
    """Add a job you found by its link. It is read, stored and queued for scoring."""
    from . import intake

    job = intake.from_url(url, C.load())
    return {"added": bool(db.add_new([job])), "title": job.title, "company": job.company, "method": db.methods.classify(job.apply_url, job.description)[0]}


@mcp.tool()
def scan_for_jobs() -> dict:
    """Fetch new postings from all configured sources (free, no AI cost) and store the ones matching your keywords."""
    from . import sources

    cfg = C.load()
    jobs = sources.fetch_all(cfg, lambda *_: None)
    kept = sources.prefilter(jobs, cfg)
    return {"fetched": len(jobs), "matched_keywords": len(kept), "new": db.add_new(kept)}


@mcp.tool()
def funnel_and_gaps() -> dict:
    """Funnel counts (found, matched, applied, interviews, offers) and the skills jobs ask for that your CV lacks."""
    f = stats.funnel()
    return {**{k: v for k, v in f.items() if k != "by_status"}, "by_status": f["by_status"], "top_gaps": stats.top_gaps(10)}


def run() -> None:
    mcp.run()
