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
def init(cv: str = typer.Argument(..., help="Path to your CV (PDF)"), force: bool = typer.Option(False, help="Overwrite existing files")) -> None:
    """Set up from your CV: copies it to profile/cv.pdf, then writes profile.yaml and config.yaml for you to check."""
    import sys

    from . import wizard

    dst = wizard.copy_cv(cv)
    cfg = C.load() if (C.ROOT / "config.yaml").exists() else C.Config()
    console.print("Reading your CV...")
    d = wizard.extract(C.cv_text(C.Config(cv_path=str(dst))), cfg)
    extra = {}
    if sys.stdin.isatty():  # things a CV cannot tell us
        extra["work_authorization"] = typer.prompt("Work authorization / visa (e.g. 'Based in Bangladesh, no sponsorship needed')", default="")
        extra["needs_sponsorship"] = typer.prompt("Will you need visa sponsorship for the jobs you apply to? (yes/no, blank = always ask me)", default="")
        extra["desired_salary_usd"] = typer.prompt("Desired salary in USD per year (blank to skip)", default="")
        extra["notice_period"] = typer.prompt("Notice period (blank to skip)", default="")
    wrote = wizard.write_files(d, force=force, extra=extra)
    console.print(f"[green]wrote[/green] {', '.join(wrote) or 'nothing (files exist, use --force)'}")
    s = d.get("search", {})
    console.print(f"Searching for: {', '.join(s.get('titles', [])[:6])} ...\nCheck profile/profile.yaml and config.yaml, then run: sidekick run")


@app.command()
def add(urls: list[str] = typer.Argument(..., help="Job posting link(s)"), score_now: bool = typer.Option(True, "--score/--no-score")) -> None:
    """Add a job you found yourself by pasting its link; it is scored and queued like any other."""
    from . import intake

    cfg = C.load()
    for url in urls:
        try:
            job = intake.from_url(url, cfg)
        except Exception as e:
            console.print(f"[red]{url}: {e}")
            continue
        if not db.add_new([job]):
            console.print(f"already tracked: {job.title} @ {job.company}")
            continue
        console.print(f"added: {job.title} @ {job.company} (apply by {db.methods.classify(job.apply_url, job.description)[0]})")
    if score_now:
        match(limit=len(urls) + 100)


@app.command("add-company")
def add_company(target: str = typer.Argument(..., help="Careers page URL or company name")) -> None:
    """Watch a company's job board (Greenhouse, Lever or Ashby), found automatically from its URL or name."""
    from . import companies

    found = companies.detect(target)
    if not found:
        return console.print("No public Greenhouse/Lever/Ashby board found for that. Paste a specific job link with `sidekick add` instead.")
    for ats, slug, n in found:
        new = companies.add(ats, slug)
        console.print(f"{'added' if new else 'already watching'} {slug} on {ats} ({n} open jobs)")


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
        if job["source"] == "linkedin-guest" and len(job["description"]) < 400:
            from . import feeds

            full = feeds.linkedin_detail(job["url"])
            if full:
                job["description"] = full
                db.update(job["id"], description=full)
        try:
            r = matcher.score(job, cfg, cv, profile)
        except Exception as e:
            console.print(f"[red]{job['title']}: {e}")
            continue
        keep = r["score"] >= cfg.search.min_score
        db.update(job["id"], score=r["score"], reasons=r["reasons"], gaps=r["gaps"], req_years=r["req_years"],
                  status="matched" if keep else "skipped")
        console.print(f"{'[green]✓' if keep else '[dim]✗'} {r['score']} {job['title'][:60]} @ {job['company'][:30]}[/]")


@app.command()
def draft() -> None:
    """Write a tailored cover letter for each matched job so you can review it before applying."""
    cfg = C.load()
    profile, cv = C.load_profile(cfg), C.cv_text(cfg)
    from . import liveness

    for row in db.by_status("matched"):
        job = dict(row)
        if liveness.check(job["apply_url"] or job["url"]) == "closed":
            db.update(job["id"], status="closed", liveness="closed", notes="posting is no longer open")
            console.print(f"[dim]closed, skipped: {job['title']} @ {job['company']}[/dim]")
            continue
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
            console.print(f"  [yellow]check: {'; '.join(warn)}[/yellow]")


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
def plan(job_id: str = typer.Argument(None, help="Job id (see `sidekick review`); default: every ready Greenhouse job")) -> None:
    """Preview exactly what would be typed into a form (Greenhouse), and answer the questions it can't."""
    from . import ats, answers

    cfg = C.load()
    profile, cv = C.load_profile(cfg), C.cv_text(cfg)
    rows = [r for r in db.by_status("ready") if not job_id or r["id"] == job_id]
    for row in rows:
        job = dict(row)
        p = ats.plan(job, cfg, profile, cv)
        if not p:
            continue
        t = Table("field", "req", "value", "from", title=f"{job['title']} @ {job['company']}")
        for f in p["fields"]:
            t.add_row(f["label"][:48], "yes" if f["required"] else "", str(f["value"] or "[red]?[/red]")[:60], f["source"])
        console.print(t)
        for f in ats.missing(p):
            v = typer.prompt(f"Answer for '{f['label']}'" + (f" {f['options']}" if f["options"] else "") + " (blank to skip)", default="")
            if v:
                answers.remember(f["label"], v)
        if ats.blocked(p):
            console.print("[yellow]Sensitive fields are never auto-filled; you fill these yourself:[/yellow] " + ", ".join(f["label"] for f in ats.blocked(p)))


@app.command("answers")
def answers_cmd(question: str = typer.Argument(None), answer: str = typer.Argument(None)) -> None:
    """No arguments: list your saved answers. With a question and answer: save it for every future form."""
    from . import answers as A

    if question and answer:
        A.remember(question, answer)
        return console.print("saved")
    for q, a in A.all_saved():
        console.print(f"[bold]{q}[/bold]\n  {a}")


@app.command()
def dashboard(port: int = 8765, open_browser: bool = typer.Option(True, "--open/--no-open")) -> None:
    """Open the local web dashboard (127.0.0.1 only) to browse, filter and update your jobs."""
    from . import dashboard as D

    srv = D.serve(port, open_browser)
    console.print(f"Dashboard: http://127.0.0.1:{srv.server_port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.server_close()


@app.command()
def export(path: str = "data/jobs.csv") -> None:
    """Export the whole tracker to CSV."""
    import csv

    rows = db.conn().execute("SELECT id,source,title,company,location,salary,score,status,method,email,url,apply_url,reasons,notes FROM jobs ORDER BY score DESC").fetchall()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(rows[0].keys() if rows else [])
        w.writerows([tuple(r) for r in rows])
    console.print(f"wrote {len(rows)} jobs to {path}")


@app.command()
def sync(replies: bool = True, alerts: bool = True) -> None:
    """Read your Gmail (read-only): update statuses from replies/rejections/interview invites, and import LinkedIn job-alert emails."""
    from . import emailer, gmailsync

    if not emailer.gmail_ready():
        raise SystemExit("credentials.json not found. See 'Gmail drafts' in the README (the same setup covers sync).")
    cfg, svc = C.load(), emailer._service()
    if alerts:
        gmailsync.sync_alerts(cfg, svc, console.print)
    if replies:
        n = gmailsync.sync_replies(cfg, svc, console.print)
        console.print(f"{n} application(s) updated from your inbox")


@app.command()
def daily() -> None:
    """The unattended routine: scan, score, check still-open, draft letters/resumes/emails, sync Gmail, then send a digest. Never applies."""
    import time

    from . import emailer, notify

    cfg, since = C.load(), time.time()
    scan()
    match(limit=100)
    draft()
    if cfg.resume.enabled:
        resume(None, 50)
    email(None)
    if emailer.gmail_ready():
        try:
            sync()
        except Exception as e:  # sync is a bonus; the digest must still go out
            console.print(f"[yellow]gmail sync skipped: {e}[/yellow]")
    text = notify.digest(since, cfg)
    console.print(text)
    console.print("sent via: " + (", ".join(notify.send(text, cfg)) or "no channel configured"))


schedule_app = typer.Typer(help="Run the daily routine automatically.", no_args_is_help=True)
app.add_typer(schedule_app, name="schedule")


@schedule_app.command("install")
def schedule_install(time: str = typer.Option("09:00", help="HH:MM, 24-hour, your local time")) -> None:
    """Schedule `sidekick daily` (macOS launchd; elsewhere prints a crontab line)."""
    from . import schedule

    console.print(schedule.install(time))


@schedule_app.command("remove")
def schedule_remove() -> None:
    """Remove the daily schedule."""
    from . import schedule

    console.print(schedule.uninstall())


def _pick(job_id: str | None, limit: int) -> list[dict]:
    rows = [r for st in ("ready", "drafted", "applied", "interview") for r in db.by_status(st)]
    return [dict(r) for r in rows if not job_id or r["id"] == job_id][: (1 if job_id else limit)]


@app.command()
def outreach(job_id: str = typer.Argument(None, help="Job id; default: your top ready jobs"), limit: int = 3) -> None:
    """Draft a LinkedIn note and email to a hiring manager (two-fact rule). Drafts only; you find the person and send."""
    from . import coach

    cfg = C.load()
    profile, cv = C.load_profile(cfg), C.cv_text(cfg)
    for job in _pick(job_id, limit):
        console.print(f"{job['title']} @ {job['company']} -> {coach.outreach(job, cfg, cv, profile)}")


@app.command()
def prep(job_id: str = typer.Argument(..., help="Job id (see `sidekick review`)")) -> None:
    """Interview prep pack for one job: likely questions with your real evidence, gaps, questions to ask, pay notes."""
    from . import coach

    cfg = C.load()
    job = _pick(job_id, 1) or [dict(r) for r in [db.conn().execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()] if r]
    if not job:
        raise SystemExit("no such job id")
    console.print(f"prep pack: {coach.prep(job[0], cfg, C.cv_text(cfg), C.load_profile(cfg))}")


@app.command()
def stories() -> None:
    """Build profile/stories.md: STAR interview stories from your CV for you to edit."""
    from . import coach

    cfg = C.load()
    console.print(f"wrote {coach.stories(cfg, C.cv_text(cfg))}  (add your real numbers, then `sidekick prep <job id>` uses it)")


@app.command()
def manual(open_links: bool = typer.Option(True, "--open/--list", help="Open each posting in your browser, one at a time")) -> None:
    """Jobs you apply to by hand (sites that need a login, LinkedIn, no apply link): opens each, copies your cover letter to the clipboard."""
    import platform
    import subprocess
    import webbrowser

    rows = [dict(r) for st in ("ready", "manual") for r in db.by_status(st) if r["method"] == "login" or st == "manual"]
    rows = [r for r in rows if r["method"] != "email" and (r["apply_url"] or r["url"])]
    if not rows:
        return console.print("Nothing waiting for a manual application.")
    for i, r in enumerate(rows, 1):
        console.print(f"[bold]{i}/{len(rows)}[/bold] {r['title']} @ {r['company']} (score {r['score']}, {r['method']})\n  {r['apply_url'] or r['url']}")
        if not open_links:
            continue
        if r.get("cover_letter"):
            clip = ["pbcopy"] if platform.system() == "Darwin" else ["xclip", "-selection", "clipboard"]
            try:
                subprocess.run(clip, input=r["cover_letter"].encode(), check=True)
                console.print("  cover letter copied to your clipboard")
            except (OSError, subprocess.CalledProcessError):
                pass
        webbrowser.open(r["apply_url"] or r["url"])
        ans = typer.prompt("  applied? [y = mark applied / s = skip job / Enter = later / q = quit]", default="").strip().lower()
        if ans == "q":
            break
        if ans in ("y", "s"):
            db.update(r["id"], status="applied" if ans == "y" else "skipped")


@app.command("mcp")
def mcp_cmd() -> None:
    """Run as an MCP server (stdio) so Claude Desktop/Code can browse and manage your jobs. It cannot submit or send anything."""
    from . import mcp_server

    mcp_server.run()


@app.command()
def gaps() -> None:
    """Skills that jobs ask for and your CV lacks, most frequent first."""
    from . import stats

    rows = stats.top_gaps()
    if not rows:
        return console.print("No gaps recorded yet. Run `sidekick match` first.")
    for g, n in rows:
        console.print(f"{n:>3}  {g}")


@app.command()
def stats() -> None:
    """Funnel and which sources / apply methods lead to interviews."""
    from . import stats as S

    f = S.funnel()
    console.print({k: v for k, v in f.items() if k != "by_status"}, f["by_status"])
    for col in ("source", "method"):
        t = Table(col, "jobs", "interviews+offers")
        for v, n, w in S.by_group(col):
            t.add_row(str(v), str(n), str(w))
        console.print(t)


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
