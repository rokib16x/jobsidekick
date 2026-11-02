"""Score jobs against the CV + preferences, and draft a cover letter. Uses Claude."""
from __future__ import annotations

import json
import re

import anthropic

from . import db
from .config import Config

_client = None


def client() -> anthropic.Anthropic:
    global _client
    _client = _client or anthropic.Anthropic()  # built lazily so .env is loaded first
    return _client


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


def score(job: db.Job | dict, cfg: Config, cv: str, profile: dict) -> dict:
    prefs = cfg.search.model_dump()
    prompt = f"""You screen job postings for a candidate. Be strict and honest.

CANDIDATE CV:
{cv[:8000]}

CANDIDATE PREFERENCES (hard requirements marked):
{json.dumps(prefs)}
Work authorization / location: {json.dumps(profile.get('location', {}))}

JOB:
Title: {job['title']}
Company: {job['company']}
Location: {job['location']}
Salary: {job['salary']}
Description:
{job['description'][:6000]}

Score 1-5: 5 = strong fit on role, seniority, skills, remote and location eligibility;
3 = partial; 1 = wrong role or ineligible (e.g. region-locked to somewhere the candidate cannot work).
Reply with JSON only: {{"score": int, "reasons": "one or two sentences", "red_flags": "or empty"}}"""
    r = client().messages.create(model=cfg.models.match, max_tokens=400, messages=[{"role": "user", "content": prompt}])
    d = _json(r.content[0].text)
    return {"score": int(d.get("score", 1)), "reasons": f"{d.get('reasons', '')} {d.get('red_flags', '')}".strip()}


def cover_letter(job: dict, cfg: Config, cv: str, profile: dict) -> str:
    prompt = f"""Write a short cover letter (120-170 words) for this job, in the first person.
Rules: use ONLY facts in the CV or profile below. Never invent employers, numbers, degrees or skills.
Concrete, no clichés ("passionate", "excited to apply"), no placeholders, no subject line. Sign off with the candidate's name.

CV:
{cv[:8000]}

PROFILE:
{json.dumps(profile.get('basics', {}))}

JOB: {job['title']} at {job['company']}
{job['description'][:5000]}"""
    r = client().messages.create(model=cfg.models.write, max_tokens=700, messages=[{"role": "user", "content": prompt}])
    return r.content[0].text.strip()
