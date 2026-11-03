"""Answers to application questions. Order: sensitive gate -> profile rules -> your saved answers -> model draft (needs your OK)."""
from __future__ import annotations

import difflib
import json
import re
import time

from . import db
from .config import Config
from .llm import complete

# Never auto-filled, whatever the form asks (FormFilla-style gating)
SENSITIVE = re.compile(r"\b(ssn|social security|national id|identity (card|number)|passport|date of birth|birth ?date|dob|"
                       r"bank|routing number|iban|tax id|driver'?s licen[cs]e|credit card)\b", re.I)
# Legal / eligibility questions: only YOUR profile or saved answers may answer these, never a model guess
HIGH_STAKES = re.compile(r"sponsor|visa|work permit|authori[sz]ed to work|right to work|legally|non-?compete|employment agreement|"
                         r"criminal|convict|background check|security clearance|relocat|currently employed by|conflict of interest", re.I)
EEO = re.compile(r"gender|race|ethnic|veteran|disabilit|sexual orientation|hispanic|transgender", re.I)
DECLINE = re.compile(r"don'?t wish|decline|prefer not|do not wish|not to (say|answer|disclose)", re.I)


def norm(q: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", q.lower()).strip()


def rule(label: str, profile: dict) -> str | None:
    """Plain facts we already know from your profile."""
    b, loc, w, a = (profile.get(k) or {} for k in ("basics", "location", "work", "answers"))
    name = (b.get("full_name") or "").split()
    l = label.lower()
    if re.search(r"sponsor|visa", label, re.I) and loc.get("needs_sponsorship") not in (None, ""):
        return "Yes" if str(loc["needs_sponsorship"]).lower() in ("yes", "true", "y") else "No"
    table = [
        (r"first name|given name|prefer.*name|name.*prefer", name[0] if name else ""),
        (r"last name|surname|family name", name[-1] if len(name) > 1 else ""),
        (r"^(full |legal )?name\b|your name", b.get("full_name")),
        (r"e-?mail", b.get("email")),
        (r"phone|mobile|telephone", b.get("phone")),
        (r"linkedin", b.get("linkedin")),
        (r"github", b.get("github")),
        (r"website|portfolio|personal site|url", b.get("website") or b.get("github")),
        (r"country.*(reside|located|residence|live)|(reside|located|residence|live).*country|^country", loc.get("country")),
        (r"\bcity\b", loc.get("city")),
        (r"years.*experience|experience.*years", w.get("years_experience")),
        (r"salary|compensation|pay expectation", w.get("desired_salary_usd")),
        (r"notice period", w.get("notice_period")),
        (r"start date|earliest|available to start", w.get("earliest_start")),
        (r"hear about|how did you find", a.get("how_did_you_hear")),
    ]
    for pat, val in table:
        if re.search(pat, l) and val not in (None, ""):
            return str(val)
    return None


def pick_option(value: str, options: list[str]) -> str | None:
    """Match a value to the closest dropdown option (exact, contains, then fuzzy)."""
    v = norm(value)
    for o in options:
        if norm(o) == v:
            return o
    for o in options:
        if v and (v in norm(o) or norm(o) in v) and len(norm(o)) > 1:
            return o
    best = difflib.get_close_matches(v, [norm(o) for o in options], n=1, cutoff=0.75)
    return next((o for o in options if norm(o) == best[0]), None) if best else None


def recall(question: str) -> str | None:
    """Your saved answer to this (or a nearly identical) question."""
    key, c = norm(question), db.conn()
    row = c.execute("SELECT answer FROM answers WHERE key=?", (key,)).fetchone()
    if row:
        return row[0]
    keys = {r[0]: r[1] for r in c.execute("SELECT key, answer FROM answers")}
    near = difflib.get_close_matches(key, list(keys), n=1, cutoff=0.88)
    return keys[near[0]] if near else None


def remember(question: str, answer: str, source: str = "you") -> None:
    c = db.conn()
    c.execute("INSERT OR REPLACE INTO answers VALUES (?,?,?,?,?)", (norm(question), question, answer, source, time.time()))
    c.commit()


def all_saved() -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in db.conn().execute("SELECT question, answer FROM answers ORDER BY created DESC")]


def draft(question: str, options: list[str], cfg: Config, profile: dict, cv: str, job: dict) -> str | None:
    """Model draft from your CV/profile only. None when it can't answer honestly (then a human decides)."""
    opts = f"\nChoose EXACTLY one of these options: {json.dumps(options)}" if options else "\nAnswer in 1-3 plain sentences."
    prompt = f"""Answer one job application question for the candidate, using ONLY facts in the CV and profile.
If the facts do not support an honest answer, reply exactly: NEEDS_HUMAN
Reply with the answer only.{opts}

QUESTION: {question}
JOB: {job.get('title')} at {job.get('company')}
PROFILE: {json.dumps(profile)}
CV:
{cv[:7000]}"""
    out = complete(cfg, "match", prompt, max_tokens=800).strip()
    if not out or "NEEDS_HUMAN" in out:
        return None
    return pick_option(out, options) if options else out


def answer_for(label: str, options: list[str], cfg: Config, profile: dict, cv: str, job: dict, use_model: bool = True) -> tuple[str | None, str]:
    """Return (value, source). source: blocked | eeo | rule | bank | model | none."""
    if SENSITIVE.search(label):
        return None, "blocked"
    if EEO.search(label):
        a = (profile.get("answers") or {})
        want = next((a[k] for k in ("gender", "veteran", "disability") if k in a and k in label.lower()), "Decline to self-identify")
        return (pick_option(want, options) or next((o for o in options if DECLINE.search(o)), None) or want), "eeo"
    v = rule(label, profile)
    if v is None:
        v = recall(label)
        src = "bank"
    else:
        src = "rule"
    if v is not None:
        return (pick_option(v, options) if options else v), src
    if use_model and not HIGH_STAKES.search(label):
        v = draft(label, options, cfg, profile, cv, job)
        if v:
            return v, "model"
    return None, "none"
