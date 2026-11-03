"""Funnel numbers and skill gaps, straight from the tracker."""
from __future__ import annotations

import json
from collections import Counter

from . import db


def funnel() -> dict:
    c = db.counts()
    scored = sum(v for k, v in c.items() if k not in ("new",))
    return {"found": sum(c.values()), "scored": scored, "matched": sum(c.get(k, 0) for k in ("matched", "ready", "drafted", "applied", "interview", "offer", "rejected")),
            "applied_or_drafted": sum(c.get(k, 0) for k in ("applied", "drafted", "interview", "offer", "rejected")),
            "interviews": c.get("interview", 0) + c.get("offer", 0), "offers": c.get("offer", 0), "rejected": c.get("rejected", 0), "by_status": c}


def by_group(col: str) -> list[tuple[str, int, int]]:
    """(value, jobs, reached interview/offer) for a column such as source or method."""
    rows = db.conn().execute(f"SELECT {col} v, COUNT(*) n, SUM(status IN ('interview','offer')) w FROM jobs GROUP BY {col} ORDER BY n DESC").fetchall()
    return [(r["v"] or "-", r["n"], r["w"] or 0) for r in rows]


def top_gaps(limit: int = 15) -> list[tuple[str, int]]:
    """Skills the postings want and your CV lacks, most frequent first (what to learn or add to your CV)."""
    cnt: Counter = Counter()
    for r in db.conn().execute("SELECT gaps FROM jobs WHERE gaps IS NOT NULL AND score IS NOT NULL"):
        try:
            cnt.update(g.strip().lower() for g in json.loads(r["gaps"]) if g)
        except (ValueError, TypeError):
            pass
    return cnt.most_common(limit)
