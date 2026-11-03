"""Form plans: for Greenhouse we read the real application questions from its public API, answer them up front, and hand
the browser agent exact values to type. Cheaper and more accurate than letting the agent improvise every field."""
from __future__ import annotations

import re

import httpx

from . import answers, sources
from .config import Config

SKIP_FILE = ("resume", "resume_text", "cover_letter")  # uploads / pasted resume are handled by the agent


def greenhouse_questions(url: str, client: httpx.Client | None = None) -> list[dict] | None:
    m = re.search(r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)/jobs/(\d+)", url) or re.search(r"greenhouse\.io/([\w-]+)\?.*gh_jid=(\d+)", url)
    if not m:
        return None
    c = client or httpx.Client(headers=sources.UA, timeout=30)
    r = c.get(f"https://boards-api.greenhouse.io/v1/boards/{m[1]}/jobs/{m[2]}", params={"questions": "true"})
    return r.json().get("questions", []) if r.status_code == 200 else None


def plan(job: dict, cfg: Config, profile: dict, cv: str, client: httpx.Client | None = None, use_model: bool = True) -> dict | None:
    """{"ats", "fields": [{label, required, type, options, value, source}]} or None for forms we can't read ahead."""
    qs = greenhouse_questions(job.get("apply_url") or job.get("url") or "", client)
    if qs is None:
        return None
    fields = []
    for q in qs:
        for f in q["fields"]:
            if f["name"] in SKIP_FILE or f["type"] == "input_file":
                continue
            label, required = re.sub(r"<[^>]+>", "", q["label"]).strip(), bool(q["required"])
            opts = [v["label"] for v in f.get("values", [])]
            if f["name"] == "cover_letter_text":
                value, src = job.get("cover_letter") or None, "cover letter"
            elif required or answers.rule(label, profile) or answers.recall(label):  # optional unknowns stay blank
                value, src = answers.answer_for(label, opts, cfg, profile, cv, job, use_model and required)
            else:
                continue
            fields.append({"label": label, "required": required, "type": f["type"], "options": opts[:12], "value": value, "source": src})
    return {"ats": "greenhouse", "fields": fields}


def missing(p: dict) -> list[dict]:
    """Required fields we have no honest value for (the human must answer these)."""
    return [f for f in p["fields"] if f["required"] and f["value"] in (None, "") and f["source"] != "blocked"]


def blocked(p: dict) -> list[dict]:
    return [f for f in p["fields"] if f["source"] == "blocked"]


def to_task_text(p: dict) -> str:
    lines = []
    for f in p["fields"]:
        if f["value"] in (None, ""):
            continue
        lines.append(f'- "{f["label"]}" ({f["type"]}{", required" if f["required"] else ""}): {f["value"]}')
    return "\n".join(lines)
