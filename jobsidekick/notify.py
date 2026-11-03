"""Daily digest and notifications. Channels turn on by themselves when their env vars exist (Telegram, Slack) plus a desktop banner."""
from __future__ import annotations

import os
import platform
import subprocess
import time

import httpx

from . import db
from .config import Config


def due_followups(days: int) -> list[dict]:
    """Applications with no news for `days` days: worth a polite follow-up."""
    cut = time.time() - days * 86400
    rows = db.conn().execute("SELECT * FROM jobs WHERE status IN ('applied','drafted') AND updated < ? ORDER BY updated", (cut,)).fetchall()
    return [dict(r) for r in rows]


def digest(since: float, cfg: Config) -> str:
    c = db.conn()
    new = c.execute("SELECT * FROM jobs WHERE created >= ? AND status IN ('ready','drafted','matched') ORDER BY score DESC LIMIT 5", (since,)).fetchall()
    total_new = c.execute("SELECT COUNT(*) FROM jobs WHERE created >= ?", (since,)).fetchone()[0]
    ready = len(db.by_status("ready"))
    lines = [f"JobSidekick: {total_new} new jobs found, {ready} ready to review."]
    for r in new:
        lines.append(f"  {r['score']}/5  {r['title'][:50]} @ {r['company'][:25]}  [{r['method']}]  {r['url']}")
    fu = due_followups(cfg.notify.followup_days)
    if fu:
        lines.append(f"Follow up ({cfg.notify.followup_days}+ days, no news): " + ", ".join(f"{r['company']}" for r in fu[:6]))
    drafts = len(db.by_status("drafted"))
    if drafts:
        lines.append(f"{drafts} email draft(s) waiting in Gmail Drafts for you to review and send.")
    return "\n".join(lines)


def send(text: str, cfg: Config, client: httpx.Client | None = None) -> list[str]:
    """Send to every configured channel. Returns the channels used."""
    c, used = client or httpx.Client(timeout=20), []
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if tok and chat:
        c.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True})
        used.append("telegram")
    if os.getenv("SLACK_WEBHOOK_URL"):
        c.post(os.environ["SLACK_WEBHOOK_URL"], json={"text": text})
        used.append("slack")
    if cfg.notify.desktop and platform.system() == "Darwin":
        first = text.splitlines()[0].replace('"', "'")
        subprocess.run(["osascript", "-e", f'display notification "{first}" with title "JobSidekick"'], check=False, capture_output=True)
        used.append("desktop")
    return used
