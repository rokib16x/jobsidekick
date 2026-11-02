from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field

from .config import DB_PATH

# status flow: new -> (skipped | matched) -> ready -> (applied | manual | failed)
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, source TEXT, title TEXT, company TEXT, location TEXT,
  url TEXT, apply_url TEXT, description TEXT, salary TEXT,
  score INTEGER, reasons TEXT, cover_letter TEXT,
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
    return c


def add_new(jobs: list[Job]) -> int:
    c, n = conn(), 0
    seen = {(r[0].lower().strip(), r[1].lower().strip()) for r in c.execute("SELECT company, title FROM jobs")}
    for j in jobs:
        key = (j.company.lower().strip(), j.title.lower().strip())
        if j.company and key in seen:  # same posting syndicated on several boards
            continue
        seen.add(key)
        cur = c.execute(
            "INSERT OR IGNORE INTO jobs (id,source,title,company,location,url,apply_url,description,salary,created,updated)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (j.id, j.source, j.title, j.company, j.location, j.url, j.apply_url, j.description, j.salary, time.time(), time.time()),
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


def counts() -> dict[str, int]:
    return {r[0]: r[1] for r in conn().execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")}
