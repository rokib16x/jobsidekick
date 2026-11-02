from pathlib import Path

from jobsidekick import db, emailer, methods, resume
from jobsidekick.db import Job

PROFILE = {"basics": {"full_name": "Ada Lovelace", "email": "ada@example.com", "website": "https://ada.dev",
                      "github": "https://github.com/ada", "linkedin": "https://linkedin.com/in/ada", "phone": "1"}}


def test_classify_email_form_login():
    assert methods.classify("", "How to apply\nEmail your CV to jobs@acme.com")[0] == "email"
    assert methods.classify("", "Contact legal@acme.com for contracts")[0] == "unknown"  # not an apply email
    assert methods.classify("https://boards.greenhouse.io/acme/jobs/1", "")[0] == "form"
    assert methods.classify("https://acme.wd1.myworkdayjobs.com/x", "")[0] == "login"
    assert methods.classify("mailto:hr@acme.com?subject=hi", "") == ("email", "hr@acme.com")


def test_best_url_skips_videos():
    urls = ["https://www.youtube.com/watch?v=1", "https://acme.com/careers/engineer"]
    assert methods.best_url(urls) == "https://acme.com/careers/engineer"


def test_fix_text_repairs_mojibake_and_norm_dedupes():
    assert db.fix_text("Sothebyâ\u0080\u0099s") == "Sotheby’s"
    assert db.norm("Software Engineer, AI Coding Tasks") == db.norm("software engineer AI coding tasks")


def test_linkify_shows_short_names_with_real_links():
    h = emailer.linkify("Portfolio: ada.dev\nGitHub: github.com/ada", PROFILE)
    assert '<a href="https://ada.dev">ada.dev</a>' in h
    assert '<a href="https://github.com/ada">github.com/ada</a>' in h
    assert "google.com/url" not in h


def test_build_message_has_pdf_and_html(tmp_path):
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    m = emailer.build_message({"title": "Dev", "email": "hr@acme.com"}, "Hi\nada.dev", PROFILE, pdf)
    assert m["To"] == "hr@acme.com" and "Ada Lovelace" in m["Subject"]
    kinds = [p.get_content_type() for p in m.walk()]
    assert "text/html" in kinds and "application/pdf" in kinds


def test_mailto_encodes_subject_and_body():
    link = emailer.mailto({"title": "Dev", "email": "hr@acme.com"}, "Hello there", PROFILE)
    assert link.startswith("mailto:hr@acme.com?subject=Application%3A%20Dev") and "Hello%20there" in link


def test_resume_flags_numbers_not_in_cv():
    cv = "Managed 18+ domains, GPA 3.47"
    assert resume._check_numbers({"x": "18+ domains — 3.47"}, cv) == []
    assert resume._check_numbers({"x": "grew revenue 250%"}, cv) == ["250"]


def test_resume_html_escapes_and_renders():
    d = {"headline": "Dev", "summary": "<b>x</b>", "experience": [{"company": "A&B", "role": "Eng", "dates": "2024", "bullets": ["did it"]}]}
    h = resume.render_html(d, PROFILE)
    assert "&lt;b&gt;x" in h and "A&amp;B" in h and "ada.dev" in h
