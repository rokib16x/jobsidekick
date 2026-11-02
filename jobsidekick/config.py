from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "jobs.db"


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


class Sources(BaseModel):
    hn: bool = True
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
    greenhouse: list[str] = Field(default_factory=list)
    lever: list[str] = Field(default_factory=list)
    ashby: list[str] = Field(default_factory=list)


class Apply(BaseModel):
    mode: str = "review"  # review = fill form, ask you before Submit; auto = submit on its own
    max_per_run: int = 10
    headless: bool = False
    skip_domains: list[str] = Field(default_factory=lambda: ["linkedin.com"])


class Config(BaseModel):
    cv_path: str = "profile/cv.pdf"
    profile_path: str = "profile/profile.yaml"
    models: Models = Models()
    search: Search = Search()
    sources: Sources = Sources()
    apply: Apply = Apply()

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
    return yaml.safe_load(p.read_text()) or {}


def cv_text(cfg: Config) -> str:
    f = cfg.cv_file
    if not f.exists():
        raise SystemExit(f"CV not found at {f}. Put your CV there (or change cv_path).")
    if f.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n".join(pg.extract_text() or "" for pg in PdfReader(str(f)).pages)
    return f.read_text()
