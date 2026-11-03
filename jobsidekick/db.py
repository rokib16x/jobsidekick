from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass, field

from . import methods
from .config import DB_PATH

# status flow: new -> (skipped | matched) -> ready -> (applied | drafted | manual | failed)
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, source TEXT, title TEXT, company TEXT, location TEXT,
  url TEXT, apply_url TEXT, description TEXT, salary TEXT,
  score INTEGER, reasons TEXT, cover_letter TEXT, method TEXT, email TEXT, resume_path TEXT,
  status TEXT DEFAULT 'new', notes TEXT, created REAL, updated REAL
)
"""


@dataclass
class Job:
    id: str
    source: str
    title: str
    company: str
    location: str
    url: str
    apply_url: str
    description: str
    salary: str = ""
    extra: dict = field(default_factory=dict)


def conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute(SCHEMA)
    c.execute("CREATE TABLE IF NOT EXISTS answers (key TEXT PRIMARY KEY, question TEXT, answer TEXT, source TEXT, created REAL)")
    have = {r[1] for r in c.execute("PRAGMA table_info(jobs)")}
    for col in ("method", "email", "resume_path", "gaps", "req_years", "liveness", "picked"):  # migrate databases from older versions
        if col not in have:
            c.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT")
    for r in c.execute("SELECT id, apply_url, description FROM jobs WHERE method IS NULL").fetchall():
        m, e = methods.classify(r["apply_url"], r["description"])
        c.execute("UPDATE jobs SET method=?, email=? WHERE id=?", (m, e, r["id"]))
    c.commit()
    return c


def fix_text(s: str) -> str:
    """Repair UTF-8 that a feed double-encoded (e.g. 'Sothebyâ\x80\x99s')."""
    if s and re.search("[âÃ]", s):
        for enc in ("latin-1", "cp1252"):
            try:
                return s.encode(enc).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
    return s


def norm(s: str) -> str:
    """Normalised key so 'Software Engineer, AI Coding Tasks' == 'Software Engineer AI Coding Tasks'."""
    return re.sub(r"[^a-z0-9]+", " ", fix_text(s).lower()).strip()


def add_new(jobs: list[Job]) -> int:
    c, n = conn(), 0
    seen = {(norm(r[0]), norm(r[1])) for r in c.execute("SELECT company, title FROM jobs")}
    for j in jobs:
        j.title, j.company, j.description = fix_text(j.title), fix_text(j.company), fix_text(j.description)
        key = (norm(j.company), norm(j.title))
        if j.company and key in seen:  # same posting syndicated on several boards
            continue
        seen.add(key)
        cur = c.execute(
            "INSERT OR IGNORE INTO jobs (id,source,title,company,location,url,apply_url,description,salary,method,email,created,updated)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (j.id, j.source, j.title, j.company, j.location, j.url, j.apply_url, j.description, j.salary,
             *methods.classify(j.apply_url, j.description), time.time(), time.time()),
        )
        n += cur.rowcount
    c.commit()
    return n


def by_status(status: str, limit: int = 1000) -> list[sqlite3.Row]:
    return conn().execute(
        "SELECT * FROM jobs WHERE status=? ORDER BY COALESCE(score,0) DESC, created DESC LIMIT ?", (status, limit)
    ).fetchall()


def update(job_id: str, **fields) -> None:
    c = conn()
    fields["updated"] = time.time()
    cols = ", ".join(f"{k}=?" for k in fields)
    c.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))
    c.commit()


def only_picked(rows: list) -> list:
    """If you ticked jobs in the dashboard, work on those only; if you ticked none, work on everything in the queue."""
    any_picked = conn().execute("SELECT 1 FROM jobs WHERE picked=1 AND status IN ('ready','manual','drafted') LIMIT 1").fetchone()
    return [r for r in rows if r["picked"]] if any_picked else rows


def counts() -> dict[str, int]:
    return {r[0]: r[1] for r in conn().execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")}
