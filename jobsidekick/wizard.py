"""`sidekick init`: read your CV and write profile.yaml and config.yaml for you."""
from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from .config import ROOT, Config
from .llm import complete, extract_json

PROMPT = """Read this CV and reply with JSON only, to set up a job-search tool for this person:
{{"basics": {{"full_name": str, "email": str, "phone": str, "linkedin": str, "github": str, "website": str}},
  "location": {{"city": str, "country": str, "timezone": str}},
  "work": {{"years_experience": number (professional years, count part-time as real time but do not double count), "current_title": str}},
  "search": {{"titles": [8-12 job titles to search for, lowercase], "keywords": [6-10 core skills, lowercase],
             "exclude_title_words": [words for seniority levels or fields clearly above or outside this CV, e.g. "director", "intern"]}}}}
Use only what the CV says; use "" when unknown. Full URLs for links.

CV:
{cv}"""


def extract(cv: str, cfg: Config) -> dict:
    d = extract_json(complete(cfg, "write", PROMPT.format(cv=cv[:9000]), max_tokens=3000))
    if not d.get("basics"):
        raise RuntimeError("could not read the CV (is it a scanned image?)")
    return d


def write_files(d: dict, root: Path = ROOT, force: bool = False, extra: dict | None = None) -> list[str]:
    """Write profile/profile.yaml and config.yaml. Never overwrites without force. Returns what it wrote."""
    wrote = []
    extra = extra or {}
    profile = {
        "basics": d["basics"],
        "location": {**d.get("location", {}), "work_authorization": extra.get("work_authorization", ""),
                     "needs_sponsorship": extra.get("needs_sponsorship", ""), "open_to_relocate": False},
        "work": {**d.get("work", {}), "notice_period": extra.get("notice_period", ""), "desired_salary_usd": extra.get("desired_salary_usd", ""),
                 "earliest_start": extra.get("earliest_start", "")},
        "answers": {"how_did_you_hear": "Job board / company careers page", "why_remote": "", "gender": "Decline to self-identify",
                    "veteran": "Decline to self-identify", "disability": "Decline to self-identify"},
    }
    p = root / "profile" / "profile.yaml"
    if force or not p.exists():
        p.parent.mkdir(exist_ok=True)
        p.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True))
        wrote.append(str(p.relative_to(root)))
    c = root / "config.yaml"
    if force or not c.exists():
        cfg = yaml.safe_load((root / "config.example.yaml").read_text())
        cfg["search"].update({k: v for k, v in d.get("search", {}).items() if v})
        c.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
        wrote.append("config.yaml")
    return wrote


def copy_cv(src: str, root: Path = ROOT) -> Path:
    dst = root / "profile" / "cv.pdf"
    dst.parent.mkdir(exist_ok=True)
    if Path(src).resolve() != dst.resolve():
        shutil.copy(src, dst)
    return dst
