"""Run `sidekick daily` on a schedule: launchd on macOS, a crontab line elsewhere. Installs only when you ask."""
from __future__ import annotations

import plistlib
import shutil
import subprocess
from pathlib import Path

from .config import ROOT

LABEL = "com.jobsidekick.daily"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def command() -> list[str]:
    uv = shutil.which("uv") or "uv"
    return [uv, "run", "--project", str(ROOT), "sidekick", "daily"]


def plist(hour: int, minute: int) -> bytes:
    (ROOT / "data").mkdir(exist_ok=True)
    return plistlib.dumps({
        "Label": LABEL, "ProgramArguments": command(), "WorkingDirectory": str(ROOT),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(ROOT / "data" / "daily.log"), "StandardErrorPath": str(ROOT / "data" / "daily.log"),
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"},
    })


def cron_line(hour: int, minute: int) -> str:
    return f"{minute} {hour} * * * cd {ROOT} && {' '.join(command())} >> {ROOT}/data/daily.log 2>&1"


def install(hhmm: str) -> str:
    hour, minute = (int(x) for x in hhmm.split(":"))
    import platform

    if platform.system() == "Darwin":
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        PLIST.write_bytes(plist(hour, minute))
        subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
        subprocess.run(["launchctl", "load", str(PLIST)], check=True)
        return f"Scheduled daily at {hhmm} (launchd: {PLIST}). Log: data/daily.log"
    return f"Add this line with `crontab -e`:\n{cron_line(hour, minute)}"


def uninstall() -> str:
    if PLIST.exists():
        subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
        PLIST.unlink()
        return "Schedule removed."
    return "No schedule installed."
