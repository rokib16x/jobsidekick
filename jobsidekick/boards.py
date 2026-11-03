"""More public ATS job boards. Every one is an official public endpoint the company's own careers page uses; no login, no scraping of
protected pages. `want(title)` decides which postings are worth fetching full details for (saves requests on huge boards)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import httpx

from .db import Job
from .sources import _text

Want = "callable[[str], bool] | None"


def _w(want, title: str) -> bool:
    return want is None or want(title)


def workable(c: httpx.Client, slug: str, want=None) -> list[Job]:
    r = c.post(f"https://apply.workable.com/api/v3/accounts/{slug}/jobs", json={"query": "", "location": [], "department": [], "worktype": [], "remote": []})
    if r.status_code != 200:
        return []
    out = []
    for j in r.json().get("results", []):
        loc = j.get("location") or {}
        desc = ""
        if _w(want, j["title"]):
            d = c.get(f"https://apply.workable.com/api/v2/accounts/{slug}/jobs/{j['shortcode']}")
            if d.status_code == 200:
                x = d.json()
                desc = _text(" ".join(str(x.get(k) or "") for k in ("description", "requirements", "benefits")))
        url = f"https://apply.workable.com/{slug}/j/{j['shortcode']}/"
        out.append(Job(id=f"workable:{slug}:{j['shortcode']}", source="workable", title=j["title"], company=slug,
                       location=("Remote, " if j.get("remote") else "") + ", ".join(x for x in (loc.get("city"), loc.get("country")) if x),
                       url=url, apply_url=url, description=desc or j["title"]))
    return out


def smartrecruiters(c: httpx.Client, slug: str, want=None) -> list[Job]:
    out, offset = [], 0
    while offset < 300:
        r = c.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", params={"limit": 100, "offset": offset})
        if r.status_code != 200:
            break
        items = r.json().get("content", [])
        for j in items:
            loc = j.get("location") or {}
            desc, url = "", f"https://jobs.smartrecruiters.com/{slug}/{j['id']}"
            if _w(want, j["name"]):
                d = c.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{j['id']}")
                if d.status_code == 200:
                    x = d.json()
                    secs = (x.get("jobAd") or {}).get("sections") or {}
                    desc = _text(" ".join((s or {}).get("text", "") for s in secs.values()))
                    url = x.get("postingUrl") or url
            where = ", ".join(v for v in (loc.get("city"), loc.get("country")) if v)
            out.append(Job(id=f"smartrecruiters:{slug}:{j['id']}", source="smartrecruiters", title=j["name"], company=(j.get("company") or {}).get("name", slug),
                           location=("Remote, " if loc.get("remote") or loc.get("region") == "Remote" else "") + where, url=url, apply_url=url, description=desc or j["name"]))
        if len(items) < 100:
            break
        offset += 100
    return out


def recruitee(c: httpx.Client, slug: str, want=None) -> list[Job]:
    r = c.get(f"https://{slug}.recruitee.com/api/offers/")
    if r.status_code != 200:
        return []
    return [Job(id=f"recruitee:{slug}:{o['id']}", source="recruitee", title=o["title"], company=o.get("company_name", slug),
                location=("Remote, " if o.get("remote") else "") + (o.get("location") or ""), url=o["careers_url"], apply_url=o.get("careers_apply_url") or o["careers_url"],
                description=_text((o.get("description") or "") + " " + (o.get("requirements") or ""))) for o in r.json().get("offers", [])]


def personio(c: httpx.Client, slug: str, want=None) -> list[Job]:
    r = c.get(f"https://{slug}.jobs.personio.de/xml")
    if r.status_code != 200 or "<workzag-jobs" not in r.text:
        return []
    out = []
    for p in ET.fromstring(r.text).iter("position"):
        pid, name = p.findtext("id"), p.findtext("name") or ""
        desc = _text(" ".join((d.findtext("value") or "") for d in p.iter("jobDescription")))
        url = f"https://{slug}.jobs.personio.de/job/{pid}"
        out.append(Job(id=f"personio:{slug}:{pid}", source="personio", title=name, company=slug, location=p.findtext("office") or "", url=url, apply_url=url, description=desc or name))
    return out


def breezy(c: httpx.Client, slug: str, want=None) -> list[Job]:
    r = c.get(f"https://{slug}.breezy.hr/json")
    if r.status_code != 200:
        return []
    out = []
    for j in r.json():
        loc = j.get("location") or {}
        out.append(Job(id=f"breezy:{slug}:{j['id']}", source="breezy", title=j["name"], company=(j.get("company") or {}).get("name", slug),
                       location=("Remote, " if loc.get("is_remote") else "") + ", ".join(x for x in (loc.get("city"), (loc.get("country") or {}).get("name")) if x),
                       url=j["url"], apply_url=j["url"], description=_text(j.get("description") or "") or j["name"], salary=j.get("salary") or ""))
    return out


def workday(c: httpx.Client, spec: str, want=None, terms: list[str] | None = None) -> list[Job]:
    """spec = 'host|tenant|site', e.g. 'nvidia.wd5.myworkdayjobs.com|nvidia|NVIDIAExternalCareerSite'. Searches your job titles."""
    host, tenant, site = spec.split("|")
    base = f"https://{host}/wday/cxs/{tenant}/{site}"
    seen: dict[str, dict] = {}
    for term in (terms or [""])[:4]:
        r = c.post(f"{base}/jobs", json={"limit": 20, "offset": 0, "searchText": term})
        if r.status_code != 200:
            continue
        for p in r.json().get("jobPostings", []):
            seen.setdefault(p["externalPath"], p)
    out = []
    for path, p in seen.items():
        desc, title = "", p["title"]
        if _w(want, title):
            d = c.get(base + path)
            if d.status_code == 200:
                desc = _text((d.json().get("jobPostingInfo") or {}).get("jobDescription", ""))
        url = f"https://{host}/en-US/{site}{path}"
        out.append(Job(id=f"workday:{tenant}:{path.rsplit('_', 1)[-1]}", source="workday", title=title, company=tenant, location=p.get("locationsText", ""),
                       url=url, apply_url=url, description=desc or title))
    return out


FETCHERS = {"workable": workable, "smartrecruiters": smartrecruiters, "recruitee": recruitee, "personio": personio, "breezy": breezy, "workday": workday}


def workday_spec(url: str) -> str | None:
    """Turn a Workday careers URL into 'host|tenant|site'."""
    m = re.match(r"https?://([\w.-]+\.myworkdayjobs\.com)/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)", url)
    return f"{m[1]}|{m[1].split('.')[0]}|{m[2]}" if m else None
