from __future__ import annotations

import asyncio

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from . import config as C
from . import db, matcher, sources

load_dotenv(C.ROOT / ".env")
app = typer.Typer(add_completion=False, help="Find remote jobs, score them against your CV, apply with an AI browser agent.")
console = Console()


@app.command()
def scan() -> None:
    """Fetch postings from all sources, prefilter by your keywords, store new ones."""
    cfg = C.load()
    jobs = sources.fetch_all(cfg, console.print)
    kept = sources.prefilter(jobs, cfg)
    n = db.add_new(kept)
    console.print(f"{len(jobs)} fetched, {len(kept)} passed keyword filter, [green]{n} new[/green]")


@app.command()
def match(limit: int = 100) -> None:
    """Score new jobs 1-5 against your CV with Claude; keep those at or above min_score."""
    cfg, profile, cv = C.load(), None, None
    profile, cv = C.load_profile(cfg), C.cv_text(cfg)
    for row in db.by_status("new", limit):
        job = dict(row)
        try:
            r = matcher.score(job, cfg, cv, profile)
        except Exception as e:
            console.print(f"[red]{job['title']}: {e}")
            continue
        keep = r["score"] >= cfg.search.min_score
        db.update(job["id"], score=r["score"], reasons=r["reasons"], status="matched" if keep else "skipped")
        console.print(f"{'[green]✓' if keep else '[dim]✗'} {r['score']} {job['title'][:60]} @ {job['company'][:30]}[/]")


@app.command()
def draft() -> None:
    """Write a tailored cover letter for each matched job so you can review it before applying."""
    cfg = C.load()
    profile, cv = C.load_profile(cfg), C.cv_text(cfg)
    for row in db.by_status("matched"):
        job = dict(row)
        db.update(job["id"], cover_letter=matcher.cover_letter(job, cfg, cv, profile), status="ready")
        console.print(f"drafted: {job['title']} @ {job['company']}")


@app.command()
def review() -> None:
    """List jobs that are ready to apply, best first."""
    t = Table("score", "title", "company", "source", "why")
    for r in db.by_status("ready"):
        t.add_row(str(r["score"]), r["title"][:50], r["company"][:25], r["source"], (r["reasons"] or "")[:70])
    console.print(t)


@app.command()
def apply(limit: int = typer.Option(None, help="Max applications this run (default from config)")) -> None:
    """Open a browser and apply to ready jobs. Mode (review|auto) comes from config.yaml."""
    cfg = C.load()
    profile = C.load_profile(cfg)
    console.print(f"mode: [bold]{cfg.apply.mode}[/bold]")
    asyncio.run(applier_run(cfg, profile, limit or cfg.apply.max_per_run))


def applier_run(cfg, profile, limit):
    from . import applier

    return applier.apply_all(db.by_status("ready"), cfg, profile, limit)


@app.command()
def run() -> None:
    """scan -> match -> draft -> apply, in one go."""
    scan(); match(); draft(); apply(None)


@app.command()
def status() -> None:
    """Counts per stage, plus what has been applied to."""
    console.print(db.counts())
    for r in db.by_status("applied"):
        console.print(f"[green]applied[/green] {r['title']} @ {r['company']}  {r['url']}")
    for r in db.by_status("manual"):
        console.print(f"[yellow]needs you[/yellow] {r['title']} @ {r['company']}  {r['url']}  ({r['notes']})")


if __name__ == "__main__":
    app()
