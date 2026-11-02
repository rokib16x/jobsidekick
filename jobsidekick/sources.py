"""Fetch remote job postings from free public APIs. No scraping of logged-in sites."""
from __future__ import annotations

import html
import os
import re
import xml.etree.ElementTree as ET

import httpx

from .config import Config
from .db import Job
from .methods import best_url

UA = {"User-Agent": "jobsidekick/0.1 (personal job search)"}
URL_RE = re.compile(r"https?://[^\s<>\"')]+")


def _text(s: str) -> str:
    s = re.sub(r"<(br|p|/p|li)\s*/?>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def hn(client: httpx.Client) -> list[Job]:
    """Latest 'Ask HN: Who is hiring?' thread (top-level comments only)."""
    r = client.get(
        "https://hn.algolia.com/api/v1/search_by_date",
        params={"query": "Ask HN: Who is hiring", "tags": "story,author_whoishiring", "hitsPerPage": 5},
    )
    stories = [h for h in r.json()["hits"] if "who is hiring" in (h.get("title") or "").lower()]
    if not stories:
        return []
    sid = stories[0]["objectID"]
    jobs, page = [], 0
    while page < 10:
        r = client.get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={"tags": f"comment,story_{sid}", "hitsPerPage": 1000, "page": page},
        )
        data = r.json()
        for h in data["hits"]:
            if str(h.get("parent_id")) != sid or not h.get("comment_text"):
                continue
            body = _text(h["comment_text"])
            head = body.split("\n", 1)[0]
            urls = URL_RE.findall(body)
            parts = [p.strip() for p in head.split("|")]
            jobs.append(Job(
                id=f"hn:{h['objectID']}", source="hn",
                title=" | ".join(parts[1:3]) if len(parts) > 2 else head[:120],
                company=parts[0][:80], location=head[:200],
                url=f"https://news.ycombinator.com/item?id={h['objectID']}",
                apply_url=best_url(urls), description=body,
            ))
        page += 1
        if page >= data["nbPages"]:
            break
    return jobs


def remoteok(client: httpx.Client) -> list[Job]:
    data = client.get("https://remoteok.com/api").json()[1:]  # first item is legal notice
    return [Job(
        id=f"remoteok:{d['id']}", source="remoteok", title=d.get("position", ""), company=d.get("company", ""),
        location=d.get("location") or "Remote", url=d.get("url", ""), apply_url=d.get("apply_url") or d.get("url", ""),
        description=_text(d.get("description", "")) + "\nTags: " + ", ".join(d.get("tags", [])),
        salary=f"{d.get('salary_min', '')}-{d.get('salary_max', '')}" if d.get("salary_min") else "",
    ) for d in data if d.get("id")]


def remotive(client: httpx.Client, cfg: Config) -> list[Job]:
    out: dict[str, Job] = {}
    for q in cfg.search.titles[:5] or [""]:
        for d in client.get("https://remotive.com/api/remote-jobs", params={"search": q, "limit": 100}).json().get("jobs", []):
            out[f"remotive:{d['id']}"] = Job(
                id=f"remotive:{d['id']}", source="remotive", title=d["title"], company=d["company_name"],
                location=d.get("candidate_required_location", ""), url=d["url"], apply_url=d["url"],
                description=_text(d.get("description", "")), salary=d.get("salary", ""),
            )
    return list(out.values())


def greenhouse(client: httpx.Client, token: str) -> list[Job]:
    r = client.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", params={"content": "true"})
    return [Job(
        id=f"greenhouse:{token}:{d['id']}", source="greenhouse", title=d["title"], company=token,
        location=(d.get("location") or {}).get("name", ""), url=d["absolute_url"], apply_url=d["absolute_url"],
        description=_text(html.unescape(d.get("content", ""))),
    ) for d in r.json().get("jobs", [])] if r.status_code == 200 else []


def lever(client: httpx.Client, slug: str) -> list[Job]:
    r = client.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    return [Job(
        id=f"lever:{slug}:{d['id']}", source="lever", title=d["text"], company=slug,
        location=(d.get("categories") or {}).get("location", ""), url=d["hostedUrl"], apply_url=d.get("applyUrl", d["hostedUrl"]),
        description=d.get("descriptionPlain", ""),
    ) for d in r.json()] if r.status_code == 200 else []


def ashby(client: httpx.Client, name: str) -> list[Job]:
    r = client.get(f"https://api.ashbyhq.com/posting-api/job-board/{name}")
    return [Job(
        id=f"ashby:{name}:{d['id']}", source="ashby", title=d["title"], company=name, location=d.get("location", ""),
        url=d["jobUrl"], apply_url=d.get("applyUrl", d["jobUrl"]), description=d.get("descriptionPlain", ""),
    ) for d in r.json().get("jobs", [])] if r.status_code == 200 else []


REMOTE_ONLY_SOURCES = {"remoteok", "remotive", "wwr", "himalayas", "jobicy", "arbeitnow", "jsearch", "serpapi"}


def wwr(client: httpx.Client) -> list[Job]:
    root = ET.fromstring(client.get("https://weworkremotely.com/remote-jobs.rss").text)
    jobs = []
    for it in root.iter("item"):
        g = lambda t: (it.findtext(t) or "").strip()
        company, _, title = g("title").partition(": ")
        jobs.append(Job(
            id=f"wwr:{g('guid')}", source="wwr", title=title or company, company=company if title else "",
            location=g("region") or "Remote", url=g("link"), apply_url=g("link"),
            description=_text(g("description")) + f"\nSkills: {g('skills')}",
        ))
    return jobs


def himalayas(client: httpx.Client) -> list[Job]:
    jobs, cursor = [], None
    for _ in range(3):
        d = client.get("https://himalayas.app/jobs/api", params={"limit": 100, **({"cursor": cursor} if cursor else {})}).json()
        for j in d.get("jobs", []):
            sal = f"{j.get('minSalary')}-{j.get('maxSalary')} {j.get('currency')}" if j.get("minSalary") else ""
            jobs.append(Job(
                id=f"himalayas:{j['guid']}", source="himalayas", title=j["title"], company=j.get("companyName", ""),
                location=", ".join(j.get("locationRestrictions") or []) or "Worldwide", url=j["guid"],
                apply_url=j.get("applicationLink") or j["guid"], description=_text(j.get("description", "")), salary=sal,
            ))
        cursor = d.get("nextCursor")
        if not cursor:
            break
    return jobs


def jobicy(client: httpx.Client) -> list[Job]:
    d = client.get("https://jobicy.com/api/v2/remote-jobs", params={"count": 100}).json()
    return [Job(
        id=f"jobicy:{j['id']}", source="jobicy", title=j["jobTitle"], company=j.get("companyName", ""),
        location=j.get("jobGeo", ""), url=j["url"], apply_url=j["url"], description=_text(j.get("jobDescription", "")),
        salary=f"{j.get('salaryMin')}-{j.get('salaryMax')} {j.get('salaryCurrency')}" if j.get("salaryMin") else "",
    ) for j in d.get("jobs", [])]


def arbeitnow(client: httpx.Client) -> list[Job]:
    d = client.get("https://www.arbeitnow.com/api/job-board-api").json().get("data", [])
    return [Job(
        id=f"arbeitnow:{j['slug']}", source="arbeitnow", title=j["title"], company=j["company_name"],
        location=j.get("location", ""), url=j["url"], apply_url=j["url"], description=_text(j.get("description", "")),
    ) for j in d if j.get("remote")]


def adzuna(client: httpx.Client, cfg: Config) -> list[Job]:
    app_id, app_key = os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        raise RuntimeError("set ADZUNA_APP_ID and ADZUNA_APP_KEY (free at developer.adzuna.com)")
    out = []
    for q in cfg.search.titles[:5]:
        r = client.get(f"https://api.adzuna.com/v1/api/jobs/{cfg.sources.adzuna_country}/search/1", params={
            "app_id": app_id, "app_key": app_key, "what": f"{q} remote", "results_per_page": 50, "content-type": "application/json"})
        for j in r.json().get("results", []):
            out.append(Job(
                id=f"adzuna:{j['id']}", source="adzuna", title=j["title"], company=(j.get("company") or {}).get("display_name", ""),
                location=(j.get("location") or {}).get("display_name", ""), url=j["redirect_url"], apply_url=j["redirect_url"],
                description=_text(j.get("description", "")), salary=str(j.get("salary_min") or ""),
            ))
    return out


def jsearch(client: httpx.Client, cfg: Config) -> list[Job]:
    """RapidAPI JSearch: aggregates Google for Jobs, i.e. LinkedIn, Indeed, Glassdoor, ZipRecruiter listings."""
    key = os.getenv("RAPIDAPI_KEY")
    if not key:
        raise RuntimeError("set RAPIDAPI_KEY (JSearch on rapidapi.com)")
    out = []
    for q in cfg.search.titles[:5]:
        r = client.get("https://jsearch.p.rapidapi.com/search", headers={"X-RapidAPI-Key": key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"},
                       params={"query": f"{q} remote", "remote_jobs_only": "true", "num_pages": 1, "date_posted": "month"})
        for j in r.json().get("data", []):
            out.append(Job(
                id=f"jsearch:{j['job_id']}", source="jsearch", title=j["job_title"], company=j.get("employer_name", ""),
                location=f"{j.get('job_city') or ''} {j.get('job_country') or ''}".strip() or "Remote",
                url=j.get("job_google_link") or j["job_apply_link"], apply_url=j["job_apply_link"],
                description=j.get("job_description", ""), salary=str(j.get("job_min_salary") or ""),
            ))
    return out


def serpapi(client: httpx.Client, cfg: Config) -> list[Job]:
    """SerpAPI Google Jobs. Prefers an apply link on the employer's own site over LinkedIn."""
    key = os.getenv("SERPAPI_KEY")
    if not key:
        raise RuntimeError("set SERPAPI_KEY (serpapi.com)")
    out = []
    for q in cfg.search.titles[:5]:
        r = client.get("https://serpapi.com/search.json", params={"engine": "google_jobs", "q": f"{q} remote", "api_key": key})
        for j in r.json().get("jobs_results", []):
            opts = [o["link"] for o in j.get("apply_options", [])]
            best = next((o for o in opts if "linkedin.com" not in o and "indeed.com" not in o), opts[0] if opts else j.get("share_link", ""))
            out.append(Job(
                id=f"serpapi:{j['job_id'][:60]}", source="serpapi", title=j["title"], company=j.get("company_name", ""),
                location=j.get("location", ""), url=j.get("share_link", best), apply_url=best, description=j.get("description", ""),
            ))
    return out


def fetch_all(cfg: Config, log=print) -> list[Job]:
    s, jobs = cfg.sources, []
    with httpx.Client(headers=UA, timeout=30, follow_redirects=True) as c:
        tasks = []
        if s.hn: tasks.append(("hn", lambda: hn(c)))
        if s.remoteok: tasks.append(("remoteok", lambda: remoteok(c)))
        if s.remotive: tasks.append(("remotive", lambda: remotive(c, cfg)))
        if s.wwr: tasks.append(("wwr", lambda: wwr(c)))
        if s.himalayas: tasks.append(("himalayas", lambda: himalayas(c)))
        if s.jobicy: tasks.append(("jobicy", lambda: jobicy(c)))
        if s.arbeitnow: tasks.append(("arbeitnow", lambda: arbeitnow(c)))
        if s.adzuna: tasks.append(("adzuna", lambda: adzuna(c, cfg)))
        if s.jsearch: tasks.append(("jsearch", lambda: jsearch(c, cfg)))
        if s.serpapi: tasks.append(("serpapi", lambda: serpapi(c, cfg)))
        tasks += [(f"greenhouse:{t}", lambda t=t: greenhouse(c, t)) for t in s.greenhouse]
        tasks += [(f"lever:{t}", lambda t=t: lever(c, t)) for t in s.lever]
        tasks += [(f"ashby:{t}", lambda t=t: ashby(c, t)) for t in s.ashby]
        for name, fn in tasks:
            try:
                got = fn()
                log(f"  {name}: {len(got)} postings")
                jobs += got
            except Exception as e:  # one bad source shouldn't kill the scan
                log(f"  {name}: failed ({e})")
    return jobs


def prefilter(jobs: list[Job], cfg: Config) -> list[Job]:
    """Cheap keyword gate so we only pay for LLM scoring on plausible jobs."""
    s, out = cfg.search, []
    for j in jobs:
        hay = f"{j.title} {j.description}".lower()
        if any(w.lower() in j.title.lower() for w in s.exclude_title_words):
            continue
        if s.remote_only and "remote" not in f"{j.location} {hay[:600]}".lower() and j.source not in REMOTE_ONLY_SOURCES:
            continue
        # the role itself must match: title only (HN posts have no clean title, so use the opening of the post)
        head = (j.description[:300] if j.source == "hn" else j.title).lower()
        terms = [t.lower() for t in s.titles + s.keywords]
        if terms and not any(t in head for t in terms):
            continue
        out.append(j)
    return out
