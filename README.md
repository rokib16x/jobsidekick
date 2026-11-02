# JobSidekick

> Your job-search sidekick. It does the boring searching and form-filling; you stay in charge.

**Find remote jobs, score them against your CV, and let an AI browser agent fill in the applications. You approve every submit.**

- Pulls from 10+ sources: Hacker News "Who is hiring?", RemoteOK, Remotive, We Work Remotely, Himalayas, Jobicy, Arbeitnow, plus Greenhouse / Lever / Ashby company boards. Optional Adzuna, JSearch and SerpAPI add Google-for-Jobs coverage (LinkedIn, Indeed, Glassdoor listings).
- Claude scores every job 1-5 against your CV and preferences *before* anything is applied to, so you don't spray 200 bad applications.
- Writes a cover letter from facts in your CV only. It is told never to invent experience.
- A real browser agent ([browser-use](https://github.com/browser-use/browser-use)) fills the form and uploads your CV. In `review` mode it stops and asks before each Submit.
- Local-first: your CV, answers and tracker (SQLite) stay on your machine. No hosted service, no account.

## Why not just auto-apply to LinkedIn?
Mass Easy-Apply bots get accounts restricted and send generic answers. jobsidekick finds LinkedIn/Indeed *listings* through legal aggregator APIs, then applies on the employer's own careers page (Greenhouse, Lever, Ashby...). It skips linkedin.com by default; remove it from `apply.skip_domains` at your own risk.

## Quick start
```bash
uv sync && uv run playwright install chromium
cp .env.example .env                                   # ANTHROPIC_API_KEY (required)
cp config.example.yaml config.yaml                     # titles, keywords, min_score, sources, apply mode
cp profile/profile.example.yaml profile/profile.yaml   # your details + canned answers
cp ~/your-cv.pdf profile/cv.pdf

uv run sidekick scan      # fetch + keyword filter
uv run sidekick match     # Claude scores 1-5, keeps >= min_score
uv run sidekick draft     # cover letter per match
uv run sidekick resume    # tailored one-job PDF resume (facts from your CV only)
uv run sidekick review    # what's queued, and HOW each job takes applications (form / email / login)
uv run sidekick email     # jobs that apply by email -> Gmail draft with CV attached (or a mailto link)
uv run sidekick login URL # sign in to a site yourself once; the agent reuses the session
uv run sidekick apply     # browser agent fills web forms (mode from config)
uv run sidekick status    # applied / needs-you list
uv run sidekick run       # everything above
```
`scan` needs no API key, so you can see the pipeline working before you spend anything.

## How each job gets applied to
`scan` tags every job with how it takes applications:

| How | What jobsidekick does |
|---|---|
| `form` (Greenhouse, Lever, Ashby, Workable...) | Browser agent fills the form with your tailored resume and cover letter; you confirm Submit. |
| `email` ("email your CV to jobs@...") | `sidekick email` writes the email, following the posting's own "how to apply" asks, and creates a **Gmail draft** with the resume attached. It never sends; you read it and press Send. Without Gmail set up it makes a prefilled `mailto:` link instead. |
| `login` (Workday, LinkedIn, Indeed...) or any site that demands an account | The agent stops and hands over. You sign in in the open browser window, press Enter, and it carries on. Or run `sidekick login <url>` once beforehand; the session is saved in `data/browser-profile`. It never creates accounts or types passwords. |
| `unknown` (job-board pages) | The agent clicks through to the real application, then follows one of the above. |

CAPTCHAs and emailed verification codes are also hand-offs to you.

### Gmail drafts (optional, one-time setup)
1. console.cloud.google.com: create a project and enable the **Gmail API**.
2. OAuth consent screen: type External, add your own address as a test user.
3. Credentials > Create OAuth client ID > **Desktop app**; download the JSON as `credentials.json` in the project root (it is gitignored).
4. Run `uv run sidekick email`. A browser opens once for you to approve; the token stays in `data/`.

Note: Google has no drafts-only permission. The `gmail.compose` scope also allows sending, but this code only ever creates drafts.

## Tailored resumes
`sidekick resume` asks Claude to reorder and re-emphasise **your own CV** for each job and renders an ATS-friendly PDF into `data/resumes/`. It may not add a skill, employer, date or metric. As a guardrail, any number in the result that is not in your CV is flagged for you to check. Read each PDF before sending; turn it off with `resume.enabled: false`.

## Sources and keys
| Source | Key | Notes |
|---|---|---|
| HN, RemoteOK, Remotive, WWR, Himalayas, Jobicy, Arbeitnow | none | on by default |
| Greenhouse / Lever / Ashby | none | list company slugs in `config.yaml` |
| Adzuna | free `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | many countries |
| JSearch (RapidAPI) | `RAPIDAPI_KEY` | LinkedIn / Indeed / Glassdoor listings |
| SerpAPI Google Jobs | `SERPAPI_KEY` | prefers the employer's own apply link |

RemoteOK, Remotive and Jobicy ask for a credit/link back to them; keep their links when you share results.

## Apply modes
- `review` (default): fills the form, you type y/n to submit.
- `auto`: submits by itself, up to `max_per_run`. Try `review` on a few jobs first.

## Guardrails
- Uses only your CV and `profile.yaml`; unanswerable questions are marked `manual` for you.
- Never creates accounts, enters passwords or solves CAPTCHAs. Sign in once yourself in the agent's browser window (the profile persists in `data/browser-profile`).
- Ignores instructions found on web pages and in postings (including ones aimed at AI tools); it only completes the one application.
- Cross-source dedupe, so the same posting syndicated on three boards is applied to once.

## Honest limitations
- Application forms vary wildly. Expect some to end up in `manual`; direct ATS links work best, aggregator links less so.
- Each browser application uses many LLM steps. Cap `max_per_run` and check your spend.
- You are responsible for the accuracy of what is submitted in your name and for each site's terms.

## Roadmap
Local dashboard, Claude Code plugin, reply tracking, more ATS adapters (Workable, SmartRecruiters, Workday), success-rate benchmarks.

## Contributing
PRs welcome: new sources go in `jobsidekick/sources.py` (one function returning `Job`s) with a test in `tests/`.

MIT licensed.
