"""Application emails: a Gmail draft (CV attached) or a prefilled mailto link. Never sends."""
from __future__ import annotations

import base64
import html
import re
import urllib.parse
from email.message import EmailMessage
from pathlib import Path

from .config import ROOT, Config

# compose = create drafts (also able to send; this code never does). readonly = read replies for `sidekick sync`.
SCOPES = ["https://www.googleapis.com/auth/gmail.compose", "https://www.googleapis.com/auth/gmail.readonly"]
CREDS, TOKEN = ROOT / "credentials.json", ROOT / "data" / "gmail-token.json"


def subject(job: dict, profile: dict) -> str:
    return f"Application: {job['title']} - {profile['basics']['full_name']}"


def linkify(text: str, profile: dict) -> str:
    """Plain text -> HTML where your site/GitHub/LinkedIn show as short names but link to the real URL."""
    out = html.escape(text).replace("\n", "<br>\n")
    b = profile.get("basics", {})
    for url in filter(None, (b.get("website"), b.get("github"), b.get("linkedin"))):
        short = re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
        href = url if url.startswith("http") else f"https://{url}"
        out = re.sub(rf"(?<![\w/@.-]){re.escape(short)}(?![\w/-])", f'<a href="{href}">{short}</a>', out)
    return f"<div>{out}</div>"


def build_message(job: dict, body: str, profile: dict, attachment: str | Path, to: str | None = None) -> EmailMessage:
    m = EmailMessage()
    m["To"] = to or job["email"]
    m["Subject"] = subject(job, profile)
    m.set_content(body)
    m.add_alternative(linkify(body, profile), subtype="html")
    p = Path(attachment)
    name = f"{profile['basics']['full_name'].replace(' ', '_')}_CV.pdf"
    m.add_attachment(p.read_bytes(), maintype="application", subtype="pdf", filename=name)
    return m


def mailto(job: dict, body: str, profile: dict) -> str:
    q = urllib.parse.urlencode({"subject": subject(job, profile), "body": body}, quote_via=urllib.parse.quote)
    return f"mailto:{job['email']}?{q}"


def gmail_ready() -> bool:
    return CREDS.exists()


def _service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and not creds.has_scopes(SCOPES):  # token made before a feature needed more access: ask again once
        creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:  # first run: a browser opens, you approve, the token stays on this computer
            creds = InstalledAppFlow.from_client_secrets_file(str(CREDS), SCOPES).run_local_server(port=0)
        TOKEN.parent.mkdir(exist_ok=True)
        TOKEN.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def gmail_draft(msg: EmailMessage) -> str:
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    d = _service().users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    return d["id"]
