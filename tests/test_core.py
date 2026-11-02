import httpx

from jobsidekick import db, sources
from jobsidekick.config import Config
from jobsidekick.db import Job


def J(**kw):
    base = dict(id="x:1", source="wwr", title="Backend Engineer", company="Acme", location="Remote", url="u", apply_url="u", description="python remote role")
    return Job(**{**base, **kw})


def cfg(**search):
    return Config(search={"titles": ["engineer"], "exclude_title_words": ["intern"], **search})


def test_prefilter_keeps_matching_remote():
    assert sources.prefilter([J()], cfg()) == [J()]


def test_prefilter_drops_excluded_and_offtopic():
    jobs = [J(title="Engineering Intern"), J(id="x:2", title="Chef", description="cook remote")]
    assert sources.prefilter(jobs, cfg()) == []


def test_prefilter_drops_onsite_when_remote_only():
    assert sources.prefilter([J(source="greenhouse", location="Berlin onsite", description="engineer in office")], cfg()) == []


def test_db_dedupes_across_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    assert db.add_new([J(id="a:1", source="remoteok"), J(id="b:2", source="wwr")]) == 1  # same company+title
    assert db.add_new([J(id="a:1", source="remoteok", company="Other")]) == 0  # same id
    db.update("a:1", status="matched", score=5)
    assert db.counts() == {"matched": 1}


def test_wwr_parser():
    rss = """<rss><channel><item><title>Acme: Python Dev</title><guid>g1</guid><link>http://l</link>
    <region>Worldwide</region><skills>Python</skills><description>&lt;p&gt;Hi&lt;/p&gt;</description></item></channel></rss>"""
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=rss)))
    (job,) = sources.wwr(client)
    assert (job.company, job.title, job.location) == ("Acme", "Python Dev", "Worldwide")
