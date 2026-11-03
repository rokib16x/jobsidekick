# JobSidekick

> Your job-search sidekick. It does the boring searching and form-filling; you stay in charge.

**Find remote jobs, score them against your CV, tailor your resume, draft the emails, fill the forms, and track the replies. You approve every submit and every send.**

- **Finds jobs everywhere that is publicly reachable**: 13 free job boards, ~65 verified company boards across 9 hiring systems (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee, Personio, Breezy, Workday) and any link you paste. Optional: Adzuna, JSearch, SerpAPI, LinkedIn alert emails, and opt-in LinkedIn/Indeed/Glassdoor/BDJobs search.
- **Scores honestly**: Claude (or OpenAI, Gemini, or a free local Ollama model) rates each job 1-5 against your CV, lists the skills you lack, enforces an experience limit, and checks the posting is still open.
- **Writes only true things**: cover letters, application emails and a tailored one-job PDF resume use facts from your CV only. Any number not in your CV is flagged; stock AI phrases are filtered out.
- **Applies safely**: a browser agent fills web forms (Greenhouse questions are read from the API and pre-answered), emails become Gmail drafts with the resume attached, and logins / CAPTCHAs / verification codes are handed to you.
- **Tracks everything**: local web dashboard, funnel stats, Gmail reply tracking, follow-up reminders, daily digest to Telegram/Slack/desktop.
- **Local-first**: your CV, answers and tracker (SQLite) stay on your machine. No hosted service, no telemetry, no account.

## Why not just auto-apply to LinkedIn?
Mass Easy-Apply bots get accounts restricted and send generic answers. JobSidekick finds LinkedIn/Indeed *listings* through aggregator APIs and your own LinkedIn alert emails, then applies on the employer's own careers page. It skips linkedin.com by default; remove it from `apply.skip_domains` at your own risk. It sends nothing by itself: no auto-submit by default, no auto-sent emails, no cold messages.

## Quick start
```bash
uv sync && uv run playwright install chromium
cp .env.example .env                      # add your ANTHROPIC_API_KEY (or another provider)
uv run sidekick init ~/your-cv.pdf        # reads your CV, writes profile.yaml + config.yaml for you to check

uv run sidekick scan       # fetch + keyword filter (free, no API key needed)
uv run sidekick match      # AI scores 1-5, lists gaps, checks experience limit
uv run sidekick draft      # cover letter per match (skips postings that closed)
uv run sidekick resume     # tailored PDF resume per job, with an ATS-readability check
uv run sidekick review     # the queue, and HOW each job takes applications
uv run sidekick dashboard  # local web dashboard
```
Or everything unattended except applying: `uv run sidekick daily`, and `uv run sidekick schedule install --time 09:00`.

## Commands
| Command | What it does |
|---|---|
| `init CV.pdf` | Setup wizard: profile.yaml and config.yaml from your CV |
| `scan` / `match` / `draft` / `resume` | The pipeline |
| `add URL...` | Add a job you found by its link; scored like any other |
| `add-company NAME-OR-URL` | Watch a company's Greenhouse/Lever/Ashby board (found automatically) |
| `review` | Ready jobs, with apply method (form / email / login) |
| `plan [JOB]` | Preview exactly what would be typed into a Greenhouse form; answer what it can't |
| `answers [Q A]` | List / save answers to screening questions, reused on every future form |
| `email` | Applications by email: Gmail draft with resume attached (or a mailto link). Never sends |
| `login URL` | Sign in yourself once in the agent's browser; session is kept |
| `apply` | Browser agent fills web forms; you confirm each Submit |
| `sync` | Read Gmail (read-only): update statuses from replies, import LinkedIn alert emails |
| `outreach [JOB]` | Draft a LinkedIn note and email to a hiring manager (two-fact rule). You find the person and send |
| `prep JOB` / `stories` | Interview prep pack; STAR story bank from your CV |
| `stats` / `gaps` | Funnel by source and method; skills jobs want that your CV lacks |
| `dashboard` / `export` | Local web UI (127.0.0.1 only); CSV export |
| `daily` / `schedule install\|remove` | The unattended routine + digest; run it every day |
| `mcp` | MCP server for Claude Desktop/Code (no tool can submit or send) |

## How each job gets applied to
`scan` tags every job with how it takes applications:

| How | What JobSidekick does |
|---|---|
| `form` (Greenhouse, Lever, Ashby, Workable...) | Agent fills the form with your tailored resume and cover letter. For Greenhouse the real questions are read from the API, answered up front from your profile, saved answers, or a CV-only model draft, and shown in `plan`. Legal/eligibility questions (visa, work permit, non-compete...) are never guessed by a model. SSN / date of birth / bank / ID questions are never auto-filled. |
| `email` ("email your CV to jobs@...") | `sidekick email` writes the email following the posting's own "how to apply" asks and creates a Gmail draft with the resume attached. You read it and press Send. |
| `login` (Workday, LinkedIn, Indeed...) or any account wall | The agent stops and hands over. You sign in in the open window, press Enter, and it carries on. It never creates accounts or types passwords. |
| `unknown` (job-board pages) | The agent clicks through to the real application, then follows one of the above. |

CAPTCHAs and emailed verification codes are also hand-offs to you.

### Gmail drafts and sync (optional, one-time setup)
1. console.cloud.google.com: create a project and enable the **Gmail API**.
2. OAuth consent screen: type External, add your own address as a test user.
3. Credentials > Create OAuth client ID > **Desktop app**; download the JSON as `credentials.json` in the project root (gitignored).
4. Run `uv run sidekick email` or `sync`. A browser opens once for you to approve; the token stays in `data/`.

Google has no drafts-only permission: the `gmail.compose` scope also allows sending, but this code only ever creates drafts. `sync` uses `gmail.readonly`.

## Models
`llm.provider` in `config.yaml`: `anthropic` (default), `openai`, `gemini`, `ollama` (free, runs on your machine) or `custom` (any OpenAI-compatible URL). Set `models.match` / `models.write` / `models.browser` to model names for that provider. The browser agent needs a vision-capable model; small local models struggle with it, but scoring, letters and resumes work fine locally.

## Use it from Claude
- **MCP**: add to Claude Desktop's config: `{"mcpServers": {"jobsidekick": {"command": "uv", "args": ["run", "--project", "/path/to/jobsidekick", "sidekick", "mcp"]}}}`
- **Claude Code plugin**: this repo is also a plugin (`.claude-plugin/`, `skills/`, `.mcp.json`); it keeps your data in `~/.jobsidekick` (`JOBSIDEKICK_HOME`).

## What is covered, and what isn't
| Where | How | Status |
|---|---|---|
| Hacker News "Who is hiring?", RemoteOK, Remotive, We Work Remotely, Himalayas, Jobicy, Arbeitnow, Working Nomads, The Muse, NoDesk | public APIs / RSS, no key | on by default |
| Company career pages on Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee, Personio, Breezy, Workday | official public job-board endpoints | ~65 starter companies; add any with `sidekick add-company <careers url>` |
| Google-for-Jobs aggregate (LinkedIn, Indeed, Glassdoor, ZipRecruiter listings) | JSearch / SerpAPI (free tiers), Adzuna | needs a key |
| LinkedIn | alert emails via `sync` (safe), or opt-in public search `sources.linkedin_guest` | see below |
| Indeed, Glassdoor, ZipRecruiter, BDJobs | opt-in JobSpy | against their terms, your risk |
| Jobspresso, Remote.co, CryptoJobsList | not covered: they sit behind Cloudflare bot checks and we don't bypass those | use a link with `sidekick add` |

Anything that needs a login to apply is still *found and scored*; it is tagged `login` and waits in `sidekick manual`, which opens each posting, copies your cover letter to the clipboard, and lets you mark it applied.

### LinkedIn: better options than a LinkedIn bot
Bots like Easy-Apply auto-appliers log in as you, which is what gets accounts restricted. In order of safety:
1. **LinkedIn job-alert emails** (`sidekick sync`): set up alerts on LinkedIn, and the postings arrive in your Gmail and are imported and scored. Nothing touches LinkedIn.
2. **Same job on the employer's site**: Google-for-Jobs sources (JSearch / SerpAPI) usually carry the employer's own apply link, so you apply there with no LinkedIn login.
3. **`sources.linkedin_guest: true`**: reads LinkedIn's public logged-out search pages. No login or account involved, but automated access is against LinkedIn's terms and it rate-limits, so it is slow, polite and opt-in. Results are tagged `login`: you apply by hand with `sidekick manual`.
4. **Easy Apply bots**: not included, on purpose.

## Sources and keys
| Source | Key | Notes |
|---|---|---|
| HN, RemoteOK, Remotive, WWR, Himalayas, Jobicy, Arbeitnow | none | on by default |
| Starter company boards + `add-company` | none | official public APIs |
| Adzuna | free `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | many countries |
| JSearch (RapidAPI) | `RAPIDAPI_KEY` | LinkedIn / Indeed / Glassdoor listings |
| SerpAPI Google Jobs | `SERPAPI_KEY` | prefers the employer's own apply link |
| LinkedIn alert emails | Gmail setup | `sidekick sync`; no LinkedIn scraping or login |
| JobSpy (opt-in) | none | scrapes Indeed/LinkedIn/Glassdoor/BDJobs; **against their terms, can block your IP; your risk**. `uv sync --extra scrape` |

RemoteOK, Remotive and Jobicy ask for a credit/link back; keep their links when you share results.

## Guardrails
- Uses only your CV and `profile.yaml`; unanswerable questions are marked `manual` for you. Template "FILL IN" text in your profile counts as empty.
- Never creates accounts, enters passwords or solves CAPTCHAs.
- Ignores instructions found on web pages, in postings and in emails (including ones aimed at AI tools).
- The dashboard binds to 127.0.0.1 and rejects cross-site requests; the MCP server has no submit or send tool.
- Cross-source dedupe, so a posting syndicated on three boards is handled once.

## Honest limitations
- Application forms vary wildly. Expect some to end up in `manual`; direct ATS links work best, aggregator links less so. Form filling, Gmail sign-in and the Claude plugin install are the least battle-tested parts; please report problems.
- Each browser application uses many LLM steps. Cap `max_per_run` and watch your spend.
- Tailored resumes are rewordings of your own CV. Read each one before sending.
- You are responsible for the accuracy of what is submitted in your name and for each site's terms.

## Roadmap
Browser extension that fills forms in your own Chrome, deterministic fillers for Lever/Ashby/Workable forms, more regional boards, success-rate benchmarks.

## Contributing
PRs welcome: new sources go in `jobsidekick/sources.py` (one function returning `Job`s) with a test in `tests/`.

MIT licensed.
