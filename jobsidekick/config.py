from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

# JOBSIDEKICK_HOME lets the tool keep your config, CV and data in one folder when installed as a plugin or package
ROOT = Path(os.environ.get("JOBSIDEKICK_HOME") or Path(__file__).resolve().parent.parent).expanduser()
DB_PATH = ROOT / "data" / "jobs.db"


class LLM(BaseModel):
    provider: str = "anthropic"  # anthropic | openai | gemini | ollama | custom (OpenAI-compatible)
    base_url: str = ""
    api_key_env: str = ""  # name of the env var holding the key, if not the default for the provider


class Models(BaseModel):
    match: str = "claude-haiku-5-5"
    write: str = "claude-sonnet-5-5"
    browser: str = "claude-sonnet-5-5"


class Search(BaseModel):
    titles: list[str] = Field(default_factory=list)
    exclude_title_words: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    remote_only: bool = True
    locations_ok: list[str] = Field(default_factory=lambda: ["worldwide", "anywhere", "global"])
    min_salary_usd: int | None = None
    min_score: int = 4
    blacklist_companies: list[str] = Field(default_factory=list)
    max_years_gap: int = 2  # skip jobs asking for more than (your years + this)


class Sources(BaseModel):
    hn: bool = True
    starter_companies: bool = True  # poll the verified starter list of company boards
    remoteok: bool = True
    remotive: bool = True
    wwr: bool = True
    himalayas: bool = True
    jobicy: bool = True
    arbeitnow: bool = True
    adzuna: bool = False      # needs ADZUNA_APP_ID / ADZUNA_APP_KEY
    adzuna_country: str = "us"
    jsearch: bool = False     # needs RAPIDAPI_KEY; covers LinkedIn/Indeed/Glassdoor listings
    serpapi: bool = False     # needs SERPAPI_KEY; Google Jobs
    jobspy: bool = False      # OPT-IN scraping of Indeed/LinkedIn/Glassdoor/ZipRecruiter/BDJobs via python-jobspy; against those sites' terms, your risk
    jobspy_sites: list[str] = Field(default_factory=lambda: ["indeed"])
    jobspy_country: str = "usa"
    greenhouse: list[str] = Field(default_factory=list)
    lever: list[str] = Field(default_factory=list)
    ashby: list[str] = Field(default_factory=list)


class Apply(BaseModel):
    mode: str = "review"  # review = fill form, ask you before Submit; auto = submit on its own
    max_per_run: int = 10
    headless: bool = False
    skip_domains: list[str] = Field(default_factory=lambda: ["linkedin.com"])


class Email(BaseModel):
    via: str = "auto"  # auto = Gmail drafts if credentials.json exists, else a mailto link; or gmail | mailto


class Resume(BaseModel):
    enabled: bool = True  # make a tailored one-job PDF resume (facts from your CV only)


class Notify(BaseModel):
    desktop: bool = True  # macOS banner; Telegram/Slack turn on when TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID / SLACK_WEBHOOK_URL are set
    followup_days: int = 7


class Config(BaseModel):
    cv_path: str = "profile/cv.pdf"
    profile_path: str = "profile/profile.yaml"
    llm: LLM = LLM()
    models: Models = Models()
    search: Search = Search()
    sources: Sources = Sources()
    apply: Apply = Apply()
    email: Email = Email()
    resume: Resume = Resume()
    notify: Notify = Notify()

    @property
    def cv_file(self) -> Path:
        return ROOT / self.cv_path


def load(path: str | Path | None = None) -> Config:
    p = Path(path) if path else ROOT / "config.yaml"
    if not p.exists():
        raise SystemExit(f"Missing {p.name}. Copy config.example.yaml to config.yaml and edit it.")
    return Config(**(yaml.safe_load(p.read_text()) or {}))


def load_profile(cfg: Config) -> dict:
    p = ROOT / cfg.profile_path
    if not p.exists():
        raise SystemExit(f"Missing {cfg.profile_path}. Copy profile/profile.example.yaml and fill it in.")
    return _clean(yaml.safe_load(p.read_text()) or {})


def _clean(x):
    """Template placeholders like 'FILL IN: ...' count as empty, so they are never used as an answer."""
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    return "" if isinstance(x, str) and "FILL IN" in x else x


def cv_text(cfg: Config) -> str:
    f = cfg.cv_file
    if not f.exists():
        raise SystemExit(f"CV not found at {f}. Put your CV there (or change cv_path).")
    if f.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n".join(pg.extract_text() or "" for pg in PdfReader(str(f)).pages)
    return f.read_text()
