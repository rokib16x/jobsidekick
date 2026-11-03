"""Is the posting still open? Checked before we spend money drafting for it."""
from __future__ import annotations

import re

import httpx

CLOSED_MARKERS = ("no longer accepting", "no longer available", "position has been filled", "job is closed", "job has expired",
                  "this job has expired", "posting has expired", "position is closed", "no longer open", "role has been filled",
                  "this position is no longer", "page not found", "job not found")
UA = {"User-Agent": "Mozilla/5.0 (jobsidekick liveness check)"}


def check(url: str, client: httpx.Client | None = None) -> str:
    """Return 'open', 'closed' or 'unknown'. Only says 'closed' on clear evidence (404/410 or a closed-page phrase)."""
    if not url or url.startswith("mailto:"):
        return "unknown"
    c = client or httpx.Client(headers=UA, timeout=20, follow_redirects=True)
    try:
        # Greenhouse / Lever / Ashby expose the job through an API: a missing job is a definite 'closed'
        m = re.search(r"greenhouse\.io/([\w-]+)/jobs/(\d+)", url)
        if m:
            r = c.get(f"https://boards-api.greenhouse.io/v1/boards/{m[1]}/jobs/{m[2]}")
            return "closed" if r.status_code == 404 else "open" if r.status_code == 200 else "unknown"
        m = re.search(r"jobs\.lever\.co/([\w-]+)/([\w-]+)", url)
        if m:
            r = c.get(f"https://api.lever.co/v0/postings/{m[1]}/{m[2]}")
            return "closed" if r.status_code == 404 else "open" if r.status_code == 200 else "unknown"
        r = c.get(url)
    except httpx.HTTPError:
        return "unknown"
    if r.status_code in (404, 410):
        return "closed"
    if r.status_code >= 400:
        return "unknown"
    text = re.sub(r"<[^>]+>", " ", r.text[:200_000]).lower()
    return "closed" if any(mk in text for mk in CLOSED_MARKERS) else "open"
