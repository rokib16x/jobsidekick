"""More public job feeds (no key): Working Nomads, The Muse, NoDesk, and an OPT-IN LinkedIn guest search (no login, against LinkedIn's terms)."""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import httpx

from .config import Config
from .db import Job
from .sources import _text


def workingnomads(c: httpx.Client) -> list[Job]:
    return [Job(id=f"workingnomads:{j['url']}", source="workingnomads", title=j["title"], company=j.get("company_name", ""),
                location=j.get("location") or "Remote", url=j["url"], apply_url=j["url"],
                description=_text(j.get("description", "")) + "\nTags: " + str(j.get("tags", ""))) for j in c.get("https://www.workingnomads.com/api/exposed_jobs/").json()]


def themuse(c: httpx.Client) -> list[Job]:
    out = []
    for cat in ("Software Engineering", "Data and Analytics", "Data Science", "Computer and IT"):
        for page in (1, 2):
            r = c.get("https://www.themuse.com/api/public/jobs", params={"page": page, "category": cat, "location": "Flexible / Remote"})
            for j in r.json().get("results", []):
                url = (j.get("refs") or {}).get("landing_page", "")
                out.append(Job(id=f"themuse:{j['id']}", source="themuse", title=j["name"], company=(j.get("company") or {}).get("name", ""),
                               location="Remote (Flexible / Remote)", url=url, apply_url=url, description=_text(j.get("contents", ""))))
    return out


def nodesk(c: httpx.Client) -> list[Job]:
    out = []
    for it in ET.fromstring(c.get("https://nodesk.co/remote-jobs/index.xml").text).iter("item"):
        g = lambda t: (it.findtext(t) or "").strip()
        out.append(Job(id=f"nodesk:{g('guid') or g('link')}", source="nodesk", title=g("title"), company="", location="Remote", url=g("link"), apply_url=g("link"),
                       description=_text(g("description"))))
    return out


class _Cards(HTMLParser):
    """Pull job cards out of LinkedIn's public guest-search HTML."""

    def __init__(self):
        super().__init__()
        self.jobs, self.cur, self.field = [], None, None

    def handle_starttag(self, tag, attrs):
        a, cls = dict(attrs), dict(attrs).get("class", "")
        if tag == "div" and "base-card" in cls.split() and "data-entity-urn" in a:
            self.cur = {"id": a["data-entity-urn"].rsplit(":", 1)[-1], "title": "", "company": "", "location": "", "link": ""}
            self.jobs.append(self.cur)
        elif self.cur is not None:
            if tag == "a" and "base-card__full-link" in cls:
                self.cur["link"] = a.get("href", "").split("?")[0]
            self.field = ("title" if "base-search-card__title" in cls else "company" if "base-search-card__subtitle" in cls
                          else "location" if "job-search-card__location" in cls else self.field if tag in ("a", "span") else None)

    def handle_data(self, d):
        if self.cur is not None and self.field and d.strip():
            self.cur[self.field] += (" " if self.cur[self.field] else "") + d.strip()

    def handle_endtag(self, tag):
        if tag in ("h3", "h4") or (tag == "span" and self.field == "location"):
            self.field = None


def linkedin_guest(cfg: Config) -> list[Job]:
    """OPT-IN. LinkedIn's public (logged-out) job search pages. No login and no account touched, but automated access is against
    LinkedIn's terms and it rate-limits hard, so this is slow and polite. Jobs are tagged login: you apply by hand."""
    out, hdr = [], {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
    with httpx.Client(headers=hdr, timeout=25, follow_redirects=True) as c:
        for q in cfg.search.titles[:4]:
            for start in (0, 25):
                r = c.get("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                          params={"keywords": q, "location": cfg.sources.linkedin_location, "f_WT": "2", "f_TPR": "r604800", "start": start})
                if r.status_code == 429:
                    return out  # rate limited: stop, don't hammer
                p = _Cards()
                p.feed(r.text)
                for j in p.jobs:
                    if j["title"] and j["link"]:
                        out.append(Job(id=f"linkedin-guest:{j['id']}", source="linkedin-guest", title=j["title"], company=j["company"], location=j["location"] or "Remote",
                                       url=j["link"], apply_url=j["link"], description=f"{j['title']} at {j['company']}. {j['location']}. (LinkedIn public listing; full text is fetched when scoring.)"))
                time.sleep(2.5)
    return out


def linkedin_detail(url: str) -> str:
    """Full public text of one LinkedIn posting (logged-out page)."""
    m = re.search(r"(\d{6,})", url)
    if not m:
        return ""
    r = httpx.get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m[1]}", headers={"User-Agent": "Mozilla/5.0 Chrome/124"}, timeout=25)
    if r.status_code != 200:
        return ""
    m2 = re.search(r'class="[^"]*show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>', r.text, re.S)
    return _text(m2.group(1)) if m2 else ""
