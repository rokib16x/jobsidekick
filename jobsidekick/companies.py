"""Company watchlist: boards on Greenhouse / Lever / Ashby that we poll directly (no scraping, official public APIs)."""
from __future__ import annotations

import re
from pathlib import Path

import httpx
import yaml

from . import sources
from .config import ROOT

WATCHLIST = ROOT / "data" / "companies.yaml"
STARTER = Path(__file__).parent / "starter_companies.yaml"
ATS = ("greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee", "personio", "breezy", "workday")
URL_PATTERNS = [
    ("greenhouse", r"(?:job-)?boards(?:-api)?\.greenhouse\.io/(?:v1/boards/)?([\w-]+)"),
    ("lever", r"jobs\.lever\.co/([\w-]+)"),
    ("ashby", r"jobs\.ashbyhq\.com/([\w%.-]+)"),
    ("workable", r"apply\.workable\.com/([\w-]+)"),
    ("smartrecruiters", r"(?:jobs|careers)\.smartrecruiters\.com/([\w-]+)"),
    ("recruitee", r"([\w-]+)\.recruitee\.com"),
    ("personio", r"([\w-]+)\.jobs\.personio\.(?:de|com)"),
    ("breezy", r"([\w-]+)\.breezy\.hr"),
]


def _load(path: Path) -> dict[str, list[str]]:
    d = yaml.safe_load(path.read_text()) if path.exists() else {}
    return {k: list((d or {}).get(k) or []) for k in ATS}


def watchlist(include_starter: bool = True) -> dict[str, list[str]]:
    """Starter list + your own additions, deduplicated."""
    out = {k: [] for k in ATS}
    for src in ([STARTER] if include_starter else []) + [WATCHLIST]:
        for k, v in _load(src).items():
            out[k] += [x for x in v if x not in out[k]]
    return out


def detect(target: str, client: httpx.Client | None = None) -> list[tuple[str, str, int]]:
    """Return [(ats, slug, open_jobs)] for a careers URL or a company name. Empty if nothing public was found."""
    c = client or httpx.Client(headers=sources.UA, timeout=20, follow_redirects=True)
    from . import boards

    no_details = lambda title: False  # just count postings, don't fetch every description
    fetch = {"greenhouse": sources.greenhouse, "lever": sources.lever, "ashby": sources.ashby,
             **{k: (lambda c, s, f=f: f(c, s, no_details)) for k, f in boards.FETCHERS.items()}}
    cands: list[tuple[str, str]] = []
    wd = boards.workday_spec(target)
    if wd:
        cands.append(("workday", wd))
    for ats, pat in URL_PATTERNS:
        m = re.search(pat, target)
        if m:
            cands.append((ats, m.group(1)))
    if not cands:  # a plain name: try the likely slugs on every ATS (Workday needs a URL)
        base = re.sub(r"[^a-z0-9]+", "", target.lower())
        hyph = re.sub(r"[^a-z0-9]+", "-", target.lower()).strip("-")
        cands = [(a, s) for s in dict.fromkeys([base, hyph]) for a in ATS if a != "workday"]
    found = []
    for ats, slug in cands:
        try:
            n = len(fetch[ats](c, slug))
        except Exception:
            n = 0
        if n:
            found.append((ats, slug, n))
    return found


def add(ats: str, slug: str) -> bool:
    data = _load(WATCHLIST)
    if slug in data[ats]:
        return False
    data[ats].append(slug)
    WATCHLIST.parent.mkdir(exist_ok=True)
    WATCHLIST.write_text(yaml.safe_dump(data))
    return True
