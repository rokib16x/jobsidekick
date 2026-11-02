"""Work out HOW a job takes applications: web form, email, or a site that needs a login."""
from __future__ import annotations

import re
from urllib.parse import urlparse

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
BAD_LOCAL = ("noreply", "no-reply", "donotreply", "privacy", "legal", "abuse", "unsubscribe", "support@", "press@")
APPLY_WORDS = ("apply", "application", "send", "email", "e-mail", "cv", "resume", "résumé", "portfolio", "contact", "reach out", "submit")

FORM_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "smartrecruiters.com", "bamboohr.com",
              "recruitee.com", "teamtailor.com", "personio.", "breezy.hr", "jobs.gem.com", "rippling.com", "comeet.com",
              "pinpointhq.com", "jobvite.com", "dover.com", "wellfound.com")
LOGIN_HOSTS = ("myworkdayjobs.com", "linkedin.com", "indeed.com", "icims.com", "taleo.net", "successfactors.", "glassdoor.com",
               "remote.com", "ziprecruiter.com")
NOT_APPLY_URLS = ("youtube.com", "youtu.be", "twitter.com", "x.com", "github.com", "medium.com", "crunchbase.com")


def apply_emails(text: str) -> list[str]:
    """Emails that the posting asks you to apply to (an apply-ish word within ~160 chars before them)."""
    out = []
    for m in EMAIL_RE.finditer(text):
        addr = m.group(0).rstrip(".")
        if any(b in addr.lower() for b in BAD_LOCAL):
            continue
        ctx = text[max(0, m.start() - 160): m.start()].lower()
        if any(w in ctx for w in APPLY_WORDS) and addr not in out:
            out.append(addr)
    return out


def best_url(urls: list[str]) -> str:
    """Pick the likeliest application link out of the URLs in a free-text post."""
    good = [u.rstrip(".,;") for u in urls if not any(b in u for b in NOT_APPLY_URLS)]
    for u in good:
        if any(h in u for h in FORM_HOSTS) or re.search(r"/(jobs?|careers?|apply|positions?|hiring)\b", u):
            return u
    return good[0] if good else ""


def classify(apply_url: str, description: str) -> tuple[str, str]:
    """Return (method, email). method is form | email | login | unknown."""
    url = (apply_url or "").lower()
    if url.startswith("mailto:"):
        return "email", url[7:].split("?")[0]
    host = urlparse(url).netloc
    if any(h in host for h in FORM_HOSTS):
        return "form", ""
    if any(h in host for h in LOGIN_HOSTS):
        return "login", ""
    emails = apply_emails(description)
    if emails:
        return "email", emails[0]
    return "unknown", ""
