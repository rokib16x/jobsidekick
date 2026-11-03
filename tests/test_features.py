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


def test_liveness_closed_and_open():
    import httpx

    from jobsidekick import liveness

    def handler(req):
        if "gone" in str(req.url):
            return httpx.Response(404)
        if "filled" in str(req.url):
            return httpx.Response(200, text="<p>Sorry, this position has been filled.</p>")
        return httpx.Response(200, text="<p>Apply now</p>")

    c = httpx.Client(transport=httpx.MockTransport(handler))
    assert liveness.check("https://x.com/gone", c) == "closed"
    assert liveness.check("https://x.com/filled", c) == "closed"
    assert liveness.check("https://x.com/job", c) == "open"
    assert liveness.check("mailto:a@b.c") == "unknown"


def test_experience_limit_caps_score(monkeypatch):
    from jobsidekick import matcher
    from jobsidekick.config import Config

    monkeypatch.setattr(matcher, "complete", lambda *a, **k: '{"score":5,"reasons":"great","required_years":8,"gaps":["kubernetes"]}')
    job = {"title": "t", "company": "c", "location": "", "salary": "", "description": "d"}
    r = matcher.score(job, Config(), "cv", {"work": {"years_experience": 2}})
    assert r["score"] == 2 and r["req_years"] == 8 and "kubernetes" in r["gaps"]
    r = matcher.score(job, Config(), "cv", {"work": {"years_experience": 7}})
    assert r["score"] == 5


def test_blacklist_and_gaps(tmp_path, monkeypatch):
    from jobsidekick import sources, stats
    from jobsidekick.config import Config

    cfg = Config(search={"titles": ["engineer"], "blacklist_companies": ["EvilCorp"]})
    kept = sources.prefilter([Job(id="a", source="wwr", title="Engineer", company="EvilCorp Inc", location="", url="", apply_url="", description="")], cfg)
    assert kept == []
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.add_new([Job(id="a:1", source="wwr", title="Eng", company="A", location="", url="", apply_url="", description="")])
    db.update("a:1", score=3, gaps='["Kubernetes", "go"]')
    assert stats.top_gaps()[0] == ("kubernetes", 1)


def test_company_detect_from_url_and_name():
    import httpx

    from jobsidekick import companies

    def handler(req):
        u = str(req.url)
        if "boards-api.greenhouse.io/v1/boards/acme/" in u:
            return httpx.Response(200, json={"jobs": [{"id": 1, "title": "Eng", "absolute_url": "http://x", "location": {"name": "Remote"}, "content": ""}]})
        return httpx.Response(404)

    c = httpx.Client(transport=httpx.MockTransport(handler))
    assert companies.detect("https://job-boards.greenhouse.io/acme", c) == [("greenhouse", "acme", 1)]
    assert companies.detect("Acme", c) == [("greenhouse", "acme", 1)]
    assert companies.detect("https://jobs.lever.co/nothing", c) == []


def test_watchlist_merges_starter_and_user(tmp_path, monkeypatch):
    from jobsidekick import companies

    monkeypatch.setattr(companies, "WATCHLIST", tmp_path / "c.yaml")
    assert companies.add("ashby", "mycorp") and not companies.add("ashby", "mycorp")
    wl = companies.watchlist()
    assert "mycorp" in wl["ashby"] and "gitlab" in wl["greenhouse"]
    assert "gitlab" not in companies.watchlist(include_starter=False)["greenhouse"]


def test_intake_reads_page_with_model(monkeypatch):
    import httpx

    from jobsidekick import intake
    from jobsidekick.config import Config

    monkeypatch.setattr(intake, "complete", lambda *a, **k: '{"title":"Dev","company":"Acme","location":"Remote","description":"build","apply_email":"jobs@acme.com"}')
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html><script>x()</script><p>We hire</p></html>")))
    job = intake.from_url("https://acme.com/careers/dev", Config(), c)
    assert job.title == "Dev" and job.apply_url == "mailto:jobs@acme.com" and job.id.startswith("manual:")


def test_wizard_writes_files_without_overwriting(tmp_path):
    import yaml

    from jobsidekick import wizard

    (tmp_path / "config.example.yaml").write_text(yaml.safe_dump({"search": {"titles": [], "min_score": 3}}))
    d = {"basics": {"full_name": "Ada"}, "location": {"city": "X"}, "work": {"years_experience": 3}, "search": {"titles": ["engineer"], "keywords": []}}
    assert wizard.write_files(d, tmp_path) == ["profile/profile.yaml", "config.yaml"]
    assert wizard.write_files(d, tmp_path) == []  # second run does not overwrite
    cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert cfg["search"]["titles"] == ["engineer"] and cfg["search"]["min_score"] == 3


def test_answer_rules_sensitive_and_options(tmp_path, monkeypatch):
    from jobsidekick import answers
    from jobsidekick.config import Config

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    prof = {"basics": {"full_name": "Ada King Lovelace", "email": "a@b.c"}, "location": {"country": "Bangladesh"},
            "work": {"years_experience": 3}, "answers": {"gender": "Decline to self-identify"}}
    f = lambda label, opts=(): answers.answer_for(label, list(opts), Config(), prof, "cv", {}, use_model=False)
    assert f("First Name") == ("Ada", "rule") and f("Last Name") == ("Lovelace", "rule")
    assert f("What is your current country of residence?", ["India", "Bangladesh"]) == ("Bangladesh", "rule")
    assert f("Social Security Number")[1] == "blocked" and f("Date of birth")[1] == "blocked"
    assert f("Gender", ["Male", "Female", "I don't wish to answer"]) == ("I don't wish to answer", "eeo")
    assert f("Why do you want to work here?") == (None, "none")
    answers.remember("Why do you want to work here?", "Because remote-first.")
    assert f("why do you want to work here") == ("Because remote-first.", "bank")  # near-identical question recalled


def test_greenhouse_plan_from_api():
    import httpx

    from jobsidekick import ats
    from jobsidekick.config import Config

    qs = {"questions": [
        {"label": "First Name", "required": True, "fields": [{"name": "first_name", "type": "input_text"}]},
        {"label": "Resume/CV", "required": True, "fields": [{"name": "resume", "type": "input_file"}]},
        {"label": "Will you require visa sponsorship?", "required": True, "fields": [{"name": "q1", "type": "multi_value_single_select", "values": [{"label": "Yes"}, {"label": "No"}]}]},
        {"label": "Optional random thing", "required": False, "fields": [{"name": "q2", "type": "input_text"}]}]}
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=qs)))
    prof = {"basics": {"full_name": "Ada Lovelace"}}
    p = ats.plan({"apply_url": "https://job-boards.greenhouse.io/acme/jobs/123"}, Config(), prof, "cv", c, use_model=False)
    labels = [f["label"] for f in p["fields"]]
    assert labels == ["First Name", "Will you require visa sponsorship?"]  # file + optional unknown skipped
    assert [f["label"] for f in ats.missing(p)] == ["Will you require visa sponsorship?"]
    assert "First Name" in ats.to_task_text(p)
    assert ats.plan({"apply_url": "https://example.com/job"}, Config(), prof, "cv", c) is None


def test_high_stakes_questions_never_guessed_by_model(monkeypatch, tmp_path):
    from jobsidekick import answers
    from jobsidekick.config import Config

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(answers, "draft", lambda *a, **k: "No")  # a model that would happily guess
    f = lambda label, prof: answers.answer_for(label, ["Yes", "No"], Config(), prof, "cv", {})
    assert f("Will you require visa sponsorship?", {}) == (None, "none")
    assert f("Will you require visa sponsorship?", {"location": {"needs_sponsorship": "no"}}) == ("No", "rule")
    assert f("Have you worked here before?", {}) == ("No", "model")  # ordinary factual question may be drafted


def test_profile_placeholders_count_as_empty():
    from jobsidekick import config

    assert config._clean({"a": {"b": "Based in X. FILL IN: visa"}, "c": "ok"}) == {"a": {"b": ""}, "c": "ok"}


def test_dashboard_api_and_csrf_guard(tmp_path, monkeypatch):
    import json
    import threading
    import urllib.error
    import urllib.request

    from jobsidekick import dashboard

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.add_new([Job(id="a:1", source="wwr", title="Eng", company="A", location="", url="u", apply_url="u", description="d")])
    srv = dashboard.serve(0, open_browser=False)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        assert json.load(urllib.request.urlopen(base + "/api/jobs"))[0]["title"] == "Eng"
        assert b"JobSidekick" in urllib.request.urlopen(base + "/").read()
        post = lambda hdr: urllib.request.urlopen(urllib.request.Request(base + "/api/job/a:1/status", json.dumps({"status": "applied"}).encode(), hdr, method="POST"))
        try:
            post({"Origin": "https://evil.example", "X-Sidekick": "1"})
            raise AssertionError("foreign origin accepted")
        except urllib.error.HTTPError as e:
            assert e.code == 403
        try:
            post({})
            raise AssertionError("missing header accepted")
        except urllib.error.HTTPError as e:
            assert e.code == 403
        post({"X-Sidekick": "1"})
        assert db.counts() == {"applied": 1}
    finally:
        srv.shutdown()


def _gmsg(text, frm="hr@acme.com", subj="Re: your application"):
    import base64

    enc = base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")
    return {"payload": {"headers": [{"name": "From", "value": frm}, {"name": "Subject", "value": subj}],
                        "parts": [{"mimeType": "text/plain", "body": {"data": enc}}]}}


class _FakeGmail:
    def __init__(self, msgs):
        self.msgs = msgs

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, **kw):
        return self._r({"messages": [{"id": k} for k in self.msgs]})

    def get(self, id, **kw):
        return self._r(self.msgs[id])

    def _r(self, v):
        class R:
            def execute(_):
                return v
        return R()


def test_gmail_reply_sync_updates_status(tmp_path, monkeypatch):
    from jobsidekick import gmailsync
    from jobsidekick.config import Config

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.add_new([Job(id="a:1", source="wwr", title="Dev", company="Acme", location="", url="u", apply_url="u", description="d")])
    db.update("a:1", status="applied")
    monkeypatch.setattr(gmailsync, "complete", lambda *a, **k: '{"relevant": true, "kind": "interview", "summary": "call on Tuesday"}')
    svc = _FakeGmail({"m1": _gmsg("We'd love to schedule a call. Tuesday?")})
    assert gmailsync.sync_replies(Config(), svc, lambda *_: None) == 1
    assert db.counts() == {"interview": 1}
    assert gmailsync.sync_replies(Config(), svc, lambda *_: None) == 0  # same email is never processed twice


def test_gmail_alerts_become_jobs(tmp_path, monkeypatch):
    from jobsidekick import gmailsync
    from jobsidekick.config import Config

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(gmailsync, "complete", lambda *a, **k: '{"jobs":[{"title":"Backend Dev","company":"Foo","location":"Remote","link":"https://www.linkedin.com/comm/jobs/view/1"}]}')
    svc = _FakeGmail({"m1": _gmsg("Backend Dev at Foo", frm="jobalerts-noreply@linkedin.com")})
    assert gmailsync.sync_alerts(Config(), svc, lambda *_: None) == 1
    row = db.by_status("new")[0]
    assert row["source"] == "linkedin-alert" and row["method"] == "login"


def test_voice_lint_and_enforce(monkeypatch):
    from jobsidekick import voice
    from jobsidekick.config import Config

    assert sorted(voice.lint("I'm passionate about X \u2014 truly")) == sorted(["passionate", "\u2014"])
    assert voice.lint("I build APIs in Node.") == []
    monkeypatch.setattr(voice, "complete", lambda *a, **k: "I build APIs.")
    assert voice.enforce("I'm passionate about APIs.", Config()) == "I build APIs."
    monkeypatch.setattr(voice, "complete", lambda *a, **k: "I'm passionate and thrilled.")  # rewrite made it worse: keep original
    assert voice.enforce("I'm passionate.", Config()) == "I'm passionate."


def test_resume_ats_check_on_real_pdf(tmp_path):
    from jobsidekick import resume

    d = {"headline": "Dev", "summary": "I build web apps " * 30, "skills": [{"group": "Lang", "items": ["Python"]}],
         "experience": [{"company": "A", "role": "Eng", "dates": "2024", "bullets": ["shipped things " * 8] * 3}], "education": [{"school": "U", "degree": "BSc", "dates": "2020"}]}
    prof = {"basics": {"full_name": "Ada Lovelace", "email": "ada@example.com", "phone": "+1 555 123"}}
    pdf = tmp_path / "r.pdf"
    resume.to_pdf(resume.render_html(d, prof), pdf)
    assert resume.ats_check(pdf, prof) == []
    assert "email not readable as text" in resume.ats_check(pdf, {"basics": {"full_name": "Ada Lovelace", "email": "zz@nowhere.org"}})


def test_digest_followups_and_notify(tmp_path, monkeypatch):
    import time

    import httpx

    from jobsidekick import notify
    from jobsidekick.config import Config

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.add_new([Job(id="a:1", source="wwr", title="Dev", company="Acme", location="", url="http://a", apply_url="u", description="d"),
                Job(id="a:2", source="wwr", title="Ops", company="Beta", location="", url="http://b", apply_url="u", description="d")])
    db.update("a:1", status="ready", score=4)
    db.update("a:2", status="applied")
    c = db.conn()
    c.execute("UPDATE jobs SET updated=? WHERE id='a:2'", (time.time() - 10 * 86400,))
    c.commit()
    text = notify.digest(0, Config())
    assert "2 new jobs" in text and "4/5" in text and "Follow up" in text and "Beta" in text
    calls = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    cfg = Config(notify={"desktop": False})
    client = httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(str(r.url)) or httpx.Response(200)))
    assert notify.send(text, cfg, client) == ["telegram", "slack"] and len(calls) == 2


def test_schedule_plist_and_cron():
    import plistlib

    from jobsidekick import schedule

    p = plistlib.loads(schedule.plist(9, 30))
    assert p["StartCalendarInterval"] == {"Hour": 9, "Minute": 30} and p["ProgramArguments"][-1] == "daily"
    assert schedule.cron_line(7, 5).startswith("5 7 * * * cd ")


def test_mcp_tools_registered_and_work(tmp_path, monkeypatch):
    import asyncio

    from jobsidekick import mcp_server

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert names == {"list_jobs", "get_job", "set_status", "add_job_from_url", "scan_for_jobs", "funnel_and_gaps"}
    assert not any("apply" in n or "send" in n or "submit" in n for n in names - {"add_job_from_url"})  # nothing that sends
    db.add_new([Job(id="a:1", source="wwr", title="Dev", company="A", location="", url="u", apply_url="u", description="d")])
    assert mcp_server.set_status("a:1", "ready") == {"ok": True}
    assert mcp_server.list_jobs("ready")[0]["title"] == "Dev"
    assert "error" in mcp_server.set_status("a:1", "hacked")


def test_outreach_writes_draft_with_checklist(tmp_path, monkeypatch):
    from jobsidekick import coach
    from jobsidekick.config import Config

    monkeypatch.setattr(coach, "OUT", tmp_path)
    monkeypatch.setattr(coach, "complete", lambda *a, **k: '{"linkedin_note":"Hi [first name], saw the Rust role.","email_subject":"Quick question","email_body":"Hi [first name], I build APIs.","fact_from_posting":"uses Rust","fact_from_cv":"built APIs","look_for_titles":["Engineering Manager"]}')
    monkeypatch.setattr(coach.voice, "complete", lambda *a, **k: "x")
    path = coach.outreach({"title": "Dev", "company": "Acme", "description": "d"}, Config(), "cv", {})
    text = open(path).read()
    assert "Nothing here has been sent" in text and "Engineering Manager" in text and "Hi [first name]" in text


def test_jobspy_source_maps_rows(monkeypatch):
    import sys
    import types

    from jobsidekick import sources
    from jobsidekick.config import Config

    class DF:
        def to_dict(self, _):
            return [{"id": "in-1", "title": "Py Dev", "company": "Foo", "location": "Remote", "job_url": "https://indeed.com/v", "job_url_direct": "https://foo.com/apply",
                     "description": "build", "min_amount": 80000.0, "max_amount": 100000.0, "currency": "USD"}]

    monkeypatch.setitem(sys.modules, "jobspy", types.SimpleNamespace(scrape_jobs=lambda **k: DF()))
    (job,) = sources.jobspy(Config(search={"titles": ["python"]}))[:1]
    assert job.source == "jobspy" and job.apply_url == "https://foo.com/apply" and job.salary.startswith("80000")


def test_picked_jobs_narrow_the_queue(tmp_path, monkeypatch):
    import json
    import threading
    import urllib.request

    from jobsidekick import dashboard

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.add_new([Job(id=f"a:{i}", source="wwr", title=f"Eng {i}", company=f"C{i}", location="", url="u", apply_url="u", description="d") for i in (1, 2)])
    for i in (1, 2):
        db.update(f"a:{i}", status="ready")
    assert len(db.only_picked(db.by_status("ready"))) == 2  # nothing ticked: everything is in the queue
    srv = dashboard.serve(0, open_browser=False)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_port}/api/job/a:2/pick", json.dumps({"picked": True}).encode(), {"X-Sidekick": "1"}, method="POST")
        urllib.request.urlopen(req)
        assert [r["id"] for r in db.only_picked(db.by_status("ready"))] == ["a:2"]
    finally:
        srv.shutdown()


def test_runner_steps_and_single_flight(monkeypatch):
    import io
    import time

    from jobsidekick import runner

    assert runner.steps("find", "react") == [["scan", "--query", "react"], ["match", "--limit", "150"]]
    assert runner.steps("add", url="https://x.com/j") == [["add", "https://x.com/j"]]
    for bad in (lambda: runner.steps("apply"), lambda: runner.steps("add", url="javascript:alert(1)")):
        try:
            bad()
            raise AssertionError("accepted")
        except ValueError:
            pass

    class P:
        def __init__(self, cmd, **k):
            self.stdout = io.StringIO("scanned 5\nok\n")
            time.sleep(0.3)

        def wait(self):
            return 0

    monkeypatch.setattr(runner.subprocess, "Popen", P)
    r = runner.Runner()
    run = r.start("score")
    try:
        r.start("draft")
        raise AssertionError("second run allowed")
    except RuntimeError:
        pass
    for _ in range(40):
        if run["status"] != "running":
            break
        time.sleep(0.1)
    assert run["status"] == "done" and "scanned 5" in run["log"]
    assert r.get(run["id"]) is run


def test_activity_buckets_and_ui_routes(tmp_path, monkeypatch):
    import json
    import threading
    import time
    import urllib.error
    import urllib.request

    from jobsidekick import dashboard

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.add_new([Job(id="a:1", source="wwr", title="Eng", company="A", location="", url="u", apply_url="u", description="d")])
    a = dashboard.activity("week")
    assert a["n"] == 7 and a["rows"]["Found"][-1] == 1 and sum(a["rows"]["Applied"]) == 0
    db.update("a:1", status="applied")
    assert sum(dashboard.activity("day")["rows"]["Applied"]) == 1
    srv = dashboard.serve(0, open_browser=False)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        assert b"Satoshi" in urllib.request.urlopen(base + "/").read()
        assert urllib.request.urlopen(base + "/ui/app.js").status == 200
        for bad in ("/ui/..", "/ui/secret.txt", "/ui/%2e%2e/x"):
            try:
                urllib.request.urlopen(base + bad)
                raise AssertionError("served " + bad)
            except urllib.error.HTTPError as e:
                assert e.code == 404
        post = lambda body, hdr: urllib.request.urlopen(urllib.request.Request(base + "/api/run", json.dumps(body).encode(), hdr, method="POST"))
        for body, hdr, code in (({"action": "find"}, {}, 403), ({"action": "find"}, {"X-Sidekick": "1", "Origin": "https://evil.example"}, 403),
                                ({"action": "apply"}, {"X-Sidekick": "1"}, 400), ({"action": "add", "url": "file:///etc/passwd"}, {"X-Sidekick": "1"}, 400)):
            try:
                post(body, hdr)
                raise AssertionError(f"accepted {body}")
            except urllib.error.HTTPError as e:
                assert e.code == code
    finally:
        srv.shutdown()
