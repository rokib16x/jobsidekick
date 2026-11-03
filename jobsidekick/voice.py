"""Keep drafts sounding like a person: your own voice notes (profile/voice.md) plus a filter for stock AI phrases."""
from __future__ import annotations

import re

from .config import ROOT, Config
from .llm import complete

BANNED = [r"—", r"i hope this (email )?finds you well", r"\bpassionate\b", r"\bexcited to\b", r"\bthrilled\b", r"\bdelve\b",
          r"\bleverag(e|ing)\b", r"\bsynerg", r"fast-paced", r"\brockstar\b", r"\bninja\b", r"results-driven", r"team player",
          r"i am writing to express", r"\bspearhead", r"\btapestry\b", r"\bunwavering\b"]


def voice_notes() -> str:
    """Optional profile/voice.md: a few lines or sample paragraphs of how you write."""
    p = ROOT / "profile" / "voice.md"
    return p.read_text()[:2000] if p.exists() else ""


def prompt_block() -> str:
    v = voice_notes()
    return f"\nWrite in the candidate's own voice, described here:\n{v}\n" if v else ""


def lint(text: str) -> list[str]:
    return [m.group(0) for pat in BANNED if (m := re.search(pat, text, re.I))]


def enforce(text: str, cfg: Config) -> str:
    """If the draft contains stock phrases, ask once for a rewrite that keeps every fact. Returns the better text."""
    bad = lint(text)
    if not bad:
        return text
    fixed = complete(cfg, "write", f"""Rewrite this text so it contains none of these: {bad}. Keep every fact and the same length and structure.
Use plain, direct wording a real person would write; no em dashes. Output ONLY the rewritten text.{prompt_block()}

{text}""").strip()
    return fixed if len(lint(fixed)) < len(bad) else text
