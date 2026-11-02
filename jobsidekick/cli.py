from __future__ import annotations

import asyncio
from pathlib import Path

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
def resume(job_id: str = typer.Option(None, help="Only this job id"), limit: int = 50) -> None:
    """Make a tailored one-job PDF resume for each ready job (facts from your CV only)."""
    cfg = C.load()
    if not cfg.resume.enabled:
        return console.print("resume.enabled is false in config.yaml")
    from . import resume as R

    profile, cv = C.load_profile(cfg), C.cv_text(cfg)
    for row in db.by_status("ready", limit):
        job = dict(row)
        if (job_id and job["id"] != job_id) or (job["resume_path"] and Path(job["resume_path"]).exists()):
            continue
        try:
            path, warn = R.make(job, cfg, cv, profile)
        except Exception as e:
            console.print(f"[red]{job['title']}: {e}")
            continue
        db.update(job["id"], resume_path=path)
        console.print(f"resume: {job['title']} @ {job['company']} -> {path}")
        if warn:
            console.print(f"  [yellow]check these numbers, they are not in your CV: {', '.join(warn)}[/yellow]")


@app.command()
def email(via: str = typer.Option(None, help="gmail | mailto (default from config)")) -> None:
    """For jobs that apply by email: write the email and make a Gmail draft (CV attached) or a mailto link. Never sends."""
    from . import emailer

    cfg = C.load()
    profile, cv = C.load_profile(cfg), C.cv_text(cfg)
    via = via or cfg.email.via
    if via == "auto":
        via = "gmail" if emailer.gmail_ready() else "mailto"
    if via == "gmail" and not emailer.gmail_ready():
        raise SystemExit("credentials.json not found. See 'Gmail drafts' in the README, or use --via mailto.")
    links = []
    for row in db.by_status("ready"):
        job = dict(row)
        if job["method"] != "email" or not job["email"]:
            continue
        body = matcher.email_body(job, cfg, cv, profile)
        attach = job["resume_path"] if job["resume_path"] and Path(job["resume_path"]).exists() else str(cfg.cv_file)
        if via == "gmail":
            did = emailer.gmail_draft(emailer.build_message(job, body, profile, attach))
            db.update(job["id"], status="drafted", notes=f"gmail draft {did} to {job['email']}")
            console.print(f"[green]draft created[/green] -> {job['email']}  ({job['title']} @ {job['company']}). Open Gmail > Drafts, check, Send.")
        else:
            link = emailer.mailto(job, body, profile)
            links.append(f"{job['title']} @ {job['company']}\n{link}\n")
            db.update(job["id"], status="drafted", notes=f"mailto {job['email']}; attach {Path(attach).name} yourself")
            console.print(f"mailto ready -> {job['email']}  ({job['title']}). Attach {Path(attach).name} yourself.")
    if links:
        out = C.ROOT / "data" / "mailto-links.txt"
        out.write_text("\n".join(links))
        console.print(f"Links saved to {out}. Open one in your browser to start the email in your mail app.")


@app.command()
def login(url: str = typer.Argument(..., help="Site's login page, e.g. https://boards.greenhouse.io")) -> None:
    """Open the agent's browser so you can sign in yourself once; the session is saved for later runs."""
    from . import applier

    asyncio.run(applier.login(url))


@app.command()
def review() -> None:
    """List jobs that are ready, best first, with how each one takes applications."""
    t = Table("score", "title", "company", "how", "source", "why")
    for r in db.by_status("ready"):
        how = r["method"] + (f" ({r['email']})" if r["email"] else "") + (" +resume" if r["resume_path"] else "")
        t.add_row(str(r["score"]), r["title"][:42], r["company"][:22], how, r["source"], (r["reasons"] or "")[:60])
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
    scan(); match(); draft(); resume(None, 50); email(None); apply(None)


@app.command()
def status() -> None:
    """Counts per stage, plus what has been applied to."""
    console.print(db.counts())
    for r in db.by_status("applied"):
        console.print(f"[green]applied[/green] {r['title']} @ {r['company']}  {r['url']}")
    for r in db.by_status("drafted"):
        console.print(f"[cyan]drafted[/cyan] {r['title']} @ {r['company']}  ({r['notes']})")
    for r in db.by_status("manual"):
        console.print(f"[yellow]needs you[/yellow] {r['title']} @ {r['company']}  {r['url']}  ({r['notes']})")


if __name__ == "__main__":
    app()
