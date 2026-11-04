import json
import time

import httpx

from jobsidekick import db, funded, runner
from jobsidekick.config import Config

RSS = """<rss><channel><item><title>Acme raises $12M Series A to build robots</title><link>https://news.example/acme</link>
<description>&lt;p&gt;Acme, led by Ada.&lt;/p&gt;</description><pubDate>{d}</pubDate></item>
<item><title>Ten tips for remote work</title><link>https://news.example/tips</link><description>advice</description><pubDate>{d}</pubDate></item></channel></rss>"""


def mock(routes):
    def h(req):
        for frag, resp in routes.items():
            if frag in str(req.url):
                return resp if isinstance(resp, httpx.Response) else httpx.Response(200, text=resp, headers={"content-type": "text/html"})
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(h))


def test_parse_feed_and_funding_filter():
    d = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
    items = funded.parse_feed(RSS.format(d=d), "Test")
    assert [i["title"] for i in items][0].startswith("Acme raises") and abs(items[0]["ts"] - time.time()) < 90
    c = mock({"techcrunch.com/category/venture": RSS.format(d=d)})
    got = funded.fetch_news(3, c, log=lambda *_: None)
    assert [g["title"] for g in got] == ["Acme raises $12M Series A to build robots"]  # the tips story is not funding news


def test_extract_leads_uses_model_and_ignores_bad_rows(monkeypatch):
    items = [{"title": "Acme raises $12M", "summary": "robots", "source": "T", "link": "u", "ts": 1.0}, {"title": "Fund closes", "summary": "x", "source": "T", "link": "u2", "ts": 1.0}]
    monkeypatch.setattr(funded, "complete", lambda *a, **k: json.dumps({"leads": [{"i": 0, "company": "Acme", "round": "Series A", "amount": "$12M", "investors": "X", "does": "builds robots", "relevant": True}, {"i": 9, "company": "Ghost"}]}))
    (lead,) = funded.extract_leads(items, Config())
    assert lead["company"] == "Acme" and lead["relevant"] == 1 and lead["link"] == "u"


def test_find_website_prefers_company_links_and_skips_news_sites():
    html = '<a href="https://twitter.com/acme">Acme on X</a><a href="https://techcrunch.com/x">more</a><a href="https://www.acme.io/careers">Acme</a>'
    assert funded.find_website(html, "Acme", "news.example") == "https://acme.io"
    assert funded.find_website('<a href="https://other.com">read</a>', "Acme") == ""


def test_public_contacts_only_own_domain_and_respects_robots():
    pages = {"robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /team"),
             "acme.io/careers": "<p>Write to careers@acme.io or noreply@acme.io or press@acme.io or someone@gmail.com or bob@acme.io</p>",
             "acme.io/team": "<p>secret@acme.io</p>", "acme.io": "<p>hello@acme.io</p>"}
    got = funded.public_contacts("https://acme.io", mock(pages))
    emails = [g["email"] for g in got]
    assert "careers@acme.io" in emails and "hello@acme.io" in emails and "bob@acme.io" in emails
    assert not any(x in emails for x in ("noreply@acme.io", "press@acme.io", "someone@gmail.com", "secret@acme.io"))
    assert emails.index("careers@acme.io") < emails.index("bob@acme.io")  # role addresses first


def test_save_dedupes_by_company(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    base = {"company": "Fal", "source": "A", "link": "l", "ts": 1.0, "relevant": 1}
    assert funded.save([base, {**base, "round": "Series B", "source": "B"}]) == 1
    assert funded.save([{**base, "company": "FAL"}]) == 0


def test_runner_funded_and_reach_validation():
    assert runner.steps("funded") == [["funded"]]
    assert runner.steps("reach", query="Kalshi") == [["reach", "Kalshi"]]
    for bad in ("", "x; rm -rf /", "$(id)"):
        try:
            runner.steps("reach", query=bad)
            raise AssertionError(f"accepted {bad!r}")
        except ValueError:
            pass


def test_lead_outreach_writes_draft_without_sending(tmp_path, monkeypatch):
    from jobsidekick import coach

    monkeypatch.setattr(coach, "OUT", tmp_path)
    monkeypatch.setattr(coach, "complete", lambda *a, **k: json.dumps({"linkedin_note": "Hi [first name], saw the raise.", "email_subject": "Quick question", "email_body": "Hi [first name], I build APIs.",
                                                                       "fact_from_news": "raised $12M", "fact_from_cv": "built APIs", "roles_to_ask_about": ["Full-stack"]}))
    monkeypatch.setattr(coach.voice, "complete", lambda *a, **k: "x")
    lead = {"company": "Acme", "round": "Series A", "amount": "$12M", "source": "T", "link": "http://n", "does": "robots", "ats": "ashby:acme", "open_jobs": 4,
            "website": "https://acme.io", "contacts": json.dumps([{"email": "careers@acme.io", "page": "https://acme.io/careers"}])}
    text = open(coach.lead_outreach(lead, Config(), "cv", {})).read()
    assert "Nothing here has been sent" in text and "careers@acme.io (published on https://acme.io/careers)" in text and "4 open jobs" in text
