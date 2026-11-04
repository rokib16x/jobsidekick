"""Runs JobSidekick steps as background processes for the dashboard, one at a time, with a live log.
Only a fixed list of steps can be started. 'apply' is deliberately not here: it needs you to press Submit in a terminal."""
from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
import uuid

from .config import ROOT

ACTIONS = {
    "find": "Find jobs",       # scan (optionally for one query) then score what is new
    "score": "Score new jobs",
    "draft": "Write cover letters",
    "prepare": "Prepare picked jobs",  # resume + email drafts for the jobs you ticked
    "sync": "Sync Gmail",
    "daily": "Daily routine",
    "add": "Add job from link",
    "funded": "Find funded startups",
    "reach": "Draft outreach",
}


def steps(action: str, query: str = "", url: str = "") -> list[list[str]]:
    if action == "find":
        return [["scan", *(["--query", query] if query else [])], ["match", "--limit", "150"]]
    if action == "score":
        return [["match", "--limit", "300"]]
    if action == "draft":
        return [["draft"]]
    if action == "prepare":
        return [["resume"], ["email"]]
    if action == "sync":
        return [["sync"]]
    if action == "daily":
        return [["daily"]]
    if action == "funded":
        return [["funded"]]
    if action == "reach":
        if not re.fullmatch(r"[A-Za-z0-9 _.&-]{1,60}", query or ""):
            raise ValueError("pick a startup first")
        return [["reach", query]]
    if action == "add":
        if not url.startswith(("http://", "https://")):
            raise ValueError("that does not look like a link")
        return [["add", url]]
    raise ValueError("unknown action")


class Runner:
    def __init__(self):
        self.lock, self.current, self.history = threading.Lock(), None, []

    def start(self, action: str, query: str = "", url: str = "") -> dict:
        plan = steps(action, query, url)
        with self.lock:
            if self.current and self.current["status"] == "running":
                raise RuntimeError("something is already running")
            run = {"id": uuid.uuid4().hex[:8], "action": action, "label": ACTIONS[action] + (f": {query}" if query else ""),
                   "status": "running", "log": [], "started": time.time(), "step": 0, "steps": len(plan)}
            self.current = run
            self.history = ([run] + self.history)[:10]
        threading.Thread(target=self._go, args=(run, plan), daemon=True).start()
        return run

    def _go(self, run: dict, plan: list[list[str]]) -> None:
        code = 0
        for i, args in enumerate(plan, 1):
            run["step"] = i
            run["log"].append(f"$ sidekick {' '.join(args)}")
            p = subprocess.Popen([sys.executable, "-m", "jobsidekick", *args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL)
            for line in p.stdout:  # type: ignore[union-attr]
                run["log"] = (run["log"] + [line.rstrip()])[-300:]
            code = p.wait()
            if code:
                break
        run["status"] = "done" if code == 0 else "failed"
        run["ended"] = time.time()

    def get(self, run_id: str | None = None) -> dict | None:
        return next((r for r in self.history if r["id"] == run_id), None) if run_id else self.current


RUNNER = Runner()
