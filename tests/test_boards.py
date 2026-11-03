import httpx

from jobsidekick import boards, companies, feeds


def client(routes):
    def handler(req):
        for frag, resp in routes.items():
            if frag in str(req.url):
                return httpx.Response(200, **resp) if not isinstance(resp, httpx.Response) else resp
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_recruitee_and_breezy():
    c = client({"acme.recruitee.com": {"json": {"offers": [{"id": 1, "title": "Dev", "company_name": "Acme", "location": "Berlin", "remote": True,
                                                            "careers_url": "https://careers.acme.com/o/dev", "description": "<p>Build</p>", "requirements": "Python"}]}},
                "acme.breezy.hr": {"json": [{"id": "x1", "name": "Ops", "url": "https://acme.breezy.hr/p/x1", "company": {"name": "Acme"},
                                             "location": {"is_remote": True, "city": "", "country": {"name": "France"}}, "description": "<b>do</b>", "salary": "$5"}]}})
    (r,) = boards.recruitee(c, "acme")
    assert r.source == "recruitee" and r.location.startswith("Remote") and "Python" in r.description
    (b,) = boards.breezy(c, "acme")
    assert b.title == "Ops" and "Remote" in b.location and b.salary == "$5"


def test_personio_xml():
    xml = """<workzag-jobs><position><id>7</id><name>Backend Dev</name><office>Berlin</office>
    <jobDescriptions><jobDescription><name>Tasks</name><value>&lt;p&gt;Write APIs&lt;/p&gt;</value></jobDescription></jobDescriptions></position></workzag-jobs>"""
    (j,) = boards.personio(client({"acme.jobs.personio.de": {"text": xml}}), "acme")
    assert j.title == "Backend Dev" and "Write APIs" in j.description and j.url.endswith("/job/7")


def test_smartrecruiters_fetches_details_only_when_wanted():
    calls = []
    c = client({"/postings/1": {"json": {"jobAd": {"sections": {"jobDescription": {"text": "<p>Python</p>"}}}, "postingUrl": "https://jobs.sr.com/x/1"}},
                "/postings?": {"json": {"content": [{"id": "1", "name": "Python Dev", "company": {"name": "X"}, "location": {"city": "Remote", "region": "Remote", "country": "pl"}},
                                                    {"id": "2", "name": "Chef", "company": {"name": "X"}, "location": {}}]}}})
    orig = c.get
    c.get = lambda url, **k: (calls.append(url), orig(url, **k))[1]
    jobs = boards.smartrecruiters(c, "x", want=lambda t: "python" in t.lower())
    assert [j.title for j in jobs] == ["Python Dev", "Chef"] and "Python" in jobs[0].description and jobs[1].description == "Chef"
    assert sum("/postings/" in u for u in calls) == 1  # one detail request, not two


def test_workable_and_workday():
    c = client({"/api/v3/accounts/acme/jobs": {"json": {"results": [{"shortcode": "AB1", "title": "Eng", "remote": True, "location": {"city": "", "country": "France"}}]}},
                "/api/v2/accounts/acme/jobs/AB1": {"json": {"description": "<p>Python things</p>"}},
                "/wday/cxs/t/Site/jobs": {"json": {"jobPostings": [{"title": "SWE", "externalPath": "/job/US/SWE_JR1", "locationsText": "Remote US"}]}},
                "/wday/cxs/t/Site/job/US/SWE_JR1": {"json": {"jobPostingInfo": {"jobDescription": "<p>Go</p>"}}}})
    (w,) = boards.workable(c, "acme")
    assert w.url == "https://apply.workable.com/acme/j/AB1/" and "Python" in w.description and "Remote" in w.location
    r = c.post
    c.post = lambda url, json=None, **k: r(url, json=json, **k)
    (d,) = boards.workday(c, "x.wd1.myworkdayjobs.com|t|Site", None, ["engineer"])
    assert d.title == "SWE" and d.description == "Go" and d.url == "https://x.wd1.myworkdayjobs.com/en-US/Site/job/US/SWE_JR1"


def test_workday_spec_and_detect_new_ats():
    assert boards.workday_spec("https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/x") == "nvidia.wd5.myworkdayjobs.com|nvidia|NVIDIAExternalCareerSite"
    c = client({"acme.recruitee.com/api/offers": {"json": {"offers": [{"id": 1, "title": "Dev", "careers_url": "https://x"}]}}})
    assert companies.detect("https://acme.recruitee.com/", c) == [("recruitee", "acme", 1)]


def test_linkedin_card_parser_and_feeds():
    html = """<ul><li><div class="base-card base-search-card" data-entity-urn="urn:li:jobPosting:12345">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/dev-at-foo-12345?trk=x">x</a>
      <h3 class="base-search-card__title">React Developer</h3><h4 class="base-search-card__subtitle"><a>Foo Inc</a></h4>
      <span class="job-search-card__location">Remote, Worldwide</span></div></li></ul>"""
    p = feeds._Cards()
    p.feed(html)
    assert p.jobs == [{"id": "12345", "title": "React Developer", "company": "Foo Inc", "location": "Remote, Worldwide", "link": "https://www.linkedin.com/jobs/view/dev-at-foo-12345"}]
    c = client({"workingnomads.com": {"json": [{"url": "https://wn/1", "title": "Dev", "company_name": "C", "description": "<p>x</p>", "tags": "py"}]}})
    assert feeds.workingnomads(c)[0].company == "C"
