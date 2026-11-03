"""One place that talks to a model. Providers: anthropic, openai, gemini, ollama (local, free), or any OpenAI-compatible URL."""
from __future__ import annotations

import json
import os
import re

import httpx

from .config import ROOT, Config

# provider -> (base url for OpenAI-compatible chat, env var holding the key)
OPENAI_LIKE = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "ollama": ("http://localhost:11434/v1", ""),
    "custom": ("", ""),
}
_anthropic = None


def _env() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")  # lazy, so it works from scripts as well as the CLI


def extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


def _anthropic_client():
    global _anthropic
    if _anthropic is None:
        import anthropic

        _env()
        _anthropic = anthropic.Anthropic()
    return _anthropic


def complete(cfg: Config, role: str, prompt: str, max_tokens: int = 3000) -> str:
    """role is 'match' (cheap, many calls) or 'write' (better writing). Returns the reply text."""
    model = getattr(cfg.models, role)
    prov = cfg.llm.provider
    if prov == "anthropic":
        r = _anthropic_client().messages.create(model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}])
        # newer models may lead with a thinking block, so join only the text blocks
        text = "".join(b.text for b in r.content if b.type == "text")
        if not text:
            raise RuntimeError(f"empty model reply (stop_reason={r.stop_reason})")
        return text
    _env()
    base, key_env = OPENAI_LIKE[prov]
    base = cfg.llm.base_url or base
    key = os.getenv(cfg.llm.api_key_env or key_env, "")
    r = httpx.post(f"{base.rstrip('/')}/chat/completions", timeout=300,
                   headers={"Authorization": f"Bearer {key}"} if key else {},
                   json={"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


def browser_llm(cfg: Config):
    """The model that drives the browser agent (needs vision + tool use; small local models struggle)."""
    import browser_use as bu

    _env()
    model, prov = cfg.models.browser, cfg.llm.provider
    if prov == "anthropic":
        return bu.ChatAnthropic(model=model)
    if prov == "gemini":
        return bu.ChatGoogle(model=model)
    if prov == "ollama":
        return bu.ChatOllama(model=model)
    return bu.ChatOpenAI(model=model, base_url=cfg.llm.base_url or OPENAI_LIKE[prov][0] or None,
                         api_key=os.getenv(cfg.llm.api_key_env or OPENAI_LIKE[prov][1] or "OPENAI_API_KEY"))
