# UK Graduate Energy & Materials Job Agent

A local job-search agent for a **current Imperial College London MSc Advanced Materials Science and Engineering student (2026-2027)** with a **completed First-Class Honours BSc Chemistry from Warwick**, based in **London, United Kingdom**. The MSc is in progress, expected in 2027; full-time availability begins **1 October 2027**. Academic research/projects/internships do not count as professional industry employment. It searches LinkedIn and supported company career sites for graduate energy, renewables, sustainability, battery/electrochemistry, materials and R&D roles. Jobs are stored in SQLite, scored against your CV, shown in a React dashboard and optionally emailed when they score **70+** and were posted today or within the previous two calendar days.

The workflow is **search → filter → score → display/email**. It does not submit applications. LinkedIn's existing request budgets and 15-minute default polling interval are unchanged.

### Graduate filtering and scoring

- Keep graduate/new-graduate, junior, entry-level, trainee and internship roles; scoring favours permanent graduate jobs over internships.
- Reject degree placement/sandwich years and return-to-university requirements even while the candidate is an MSc student. Current postgraduate/graduate-open internships can qualify; undergraduate-only or penultimate-year roles still do not.
- Reject senior/lead/principal/staff/manager/director/head/VP/chief titles. Ordinary Research Engineer titles are accepted.
- Reject explicit mandatory industry/professional/commercial/consultancy experience, including positive minimum years. Keep preferences, zero-minimum ranges, upper bounds such as "up to two years", and academic/research/internship alternatives. Graduate/training programme duration is not prior experience. Ambiguous experience is retained for scoring.
- `HIGHEST_COMPLETED_EDUCATION=bachelors` describes awarded qualifications. `CURRENT_EDUCATION=masters` and `CURRENT_EDUCATION_STATUS=in_progress` describe current study. A relevant Master's required by an October 2027 or later start is eligible; a Master's explicitly already required at application or an incompatible discipline is rejected. With no stated start, keep the role and flag completion timing for confirmation. Master's preferences and bachelor's alternatives remain open; an ongoing MSc never satisfies a PhD requirement.
- `CANDIDATE_GRADUATION_YEAR=2027` accepts 2027 and overlapping cohorts, rejecting exclusive 2026/2028 cohorts. A programme start year does not specify the applicant's graduation year.
- `CANDIDATE_AVAILABLE_FROM=2027-10-01` rejects explicit fixed starts before October 2027. A missing start date stays eligible; a seasonal or flexible date overlapping availability (such as Autumn 2027) produces `eligibility_warnings` for confirmation in job records and scoring context. Start, graduation and application/posting dates are assessed separately.
- With `REJECT_12_MONTH_CONTRACT=true`, reject explicit 12-month/one-year contracts, fixed-term contracts, FTCs, temporary terms and placements. Unrelated training durations are accepted.
- With `FILTER_BY_LOCATION=true`, keep UK locations and explicitly UK-eligible remote roles. London/hybrid is prioritised by scoring; other UK roles score lower for practical fit. Known overseas locations and unspecified remote eligibility are rejected. Missing location/description is uncertain, not proof of eligibility.
- Score with weights: graduate suitability 25%, energy/sustainability 25%, academic/technical fit 25%, transferable/analytical skills 15%, location/practical fit 10%. Deterministic hard-filter mismatches are rejected before AI scoring, including direct/cached-job scoring (score 0); missing descriptions are capped at 60/100, below the default email threshold.
- Lever descriptions include every structured list, requirement and additional text block. Scoring selects complete facts from the whole JD, prioritising eligibility, qualifications, experience and contract type before duties/preferences. Excerpts are bounded to 2,400 characters per job; requests (including the system prompt) are bounded to 48,000 characters and split into smaller batches when necessary. If critical facts alone exceed the excerpt budget, scoring fails before the API request instead of omitting eligibility evidence.
- CV research/project/internship headings are recognised without renaming. Tailoring preserves evidenced skills and never increases years of experience to satisfy a job description. ATS targets are diagnostics, not guarantees.
- Scoring profiles reserve at least 300 characters within the unchanged 4,800-character ceiling. Leadership is reduced to role/institution identity and languages to names; full detail remains in the local CV. Academic eligibility, relevant modules, technical skills and all three research entries take priority.
- Broad searches still rotate four queries per cycle. The first two groups prioritise 2027 energy and materials searches; the remaining queries continue afterwards within the same LinkedIn limits.

Filters operate on available listing text and cannot infer missing requirements. Workday and SmartRecruiters list responses may omit descriptions; such listings need a full JD before reliable scoring and are not allowed to reach the default email threshold without one. Career-page discovery only supports known ATS platforms; some employers will be found through LinkedIn instead.

### Automated checks

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
cd ui && npm run build
```

Tests use temporary databases, mocked network/AI calls and sample CVs. They cover graduate filters, independent preferences vs requirements, UK locations, stored-job/email selection, AI score caps, research CV parsing/PDF output, and LinkedIn rate limits. They never send emails or apply for jobs.

---

## Table of contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Clone and install](#clone-and-install)
- [Configure](#configure)
- [Run the application](#run-the-application)
- [First-time usage](#first-time-usage)
- [Dashboard (UI)](#dashboard-ui)
- [CLI mode](#cli-mode)
- [Configuration reference](#configuration-reference)
- [Email setup](#email-setup)
- [Optional: AI scoring](#optional-ai-scoring)
- [API reference](#api-reference)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)

---

## Features

- Fetches jobs from **career-site APIs** and **LinkedIn** guest search
- **React dashboard** with card and table views, search, filters, and sort
- **Email alerts** when new jobs score **70+** and were posted within two calendar days (Gmail, SMTP, or Maileroo)
- **Background polling** — the API server fetches on a schedule while the UI stays open
- **New-job celebration** — confetti animation when new listings appear (great for a desk display)
- **Graduate profile filtering** — checks mandatory professional experience, education, contract duration and UK location
- **Deduplication** — same role from LinkedIn and a career site is stored once
- **Optional AI mode** — Gemini scores jobs and tailors one-page resumes and cover letters from the dashboard or `--with-ai` (OpenAI if Gemini fails, then Claude)

---

## Prerequisites

Install these before you start:

| Tool | Version | Check |
|------|---------|-------|
| **Python** | 3.11 or newer | `python3 --version` |
| **Node.js** | 18 or newer | `node --version` |
| **npm** | 9+ (bundled with Node) | `npm --version` |
| **Git** | any recent version | `git --version` |

Email alerts are optional but recommended. For AI scoring, tailored resumes, and cover letters, add a [Gemini API key](https://aistudio.google.com/apikey). If Gemini fails, the app retries with an [OpenAI](https://platform.openai.com/api-keys) key, then [Anthropic](https://console.anthropic.com/) if set.

---

## Clone and install

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/job-agent.git
cd job-agent

# 2. Create a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install UI dependencies
cd ui && npm install && cd ..
```

> **Windows note:** Use two terminals to run the API and UI separately (see [Run the application](#run-the-application)). The `start-ui.sh` script is macOS/Linux only.

---

## Configure

Three files hold your personal settings. None of them are committed to git — you create them locally from the examples.

```bash
cp env.template .env
cp config/companies.example.json config/companies.json
cp resume/master_resume.example.txt resume/master_resume.txt
```

### 1. Edit `.env`

Open `.env` and set at minimum:

```env
USER_NAME=Your Name
TARGET_ROLES=Graduate Energy Analyst,Graduate Materials Scientist,Energy Consultant,Research Engineer
JOB_LOCATION=London, United Kingdom
EXPERIENCE_YEARS=0
EXPERIENCE_MIN=0
EXPERIENCE_MAX=0
HIGHEST_COMPLETED_EDUCATION=bachelors
CURRENT_EDUCATION=masters
CURRENT_EDUCATION_STATUS=in_progress
CANDIDATE_GRADUATION_YEAR=2027
CANDIDATE_AVAILABLE_FROM=2027-10-01
REJECT_12_MONTH_CONTRACT=true
```

See [Configuration reference](#configuration-reference) for every variable.

### 2. Edit `config/companies.json`

Add the companies you want to watch:

```json
{
  "target_companies": [
    "Octopus Energy",
    "EDF",
    "National Grid",
    "Johnson Matthey",
    "Arup"
  ]
}
```

You can list as many companies as you like. Career-site URLs and ATS board mappings are already curated in `jobs/career_registry.py` for common tech companies.

**Alternative:** set companies directly in `.env` instead of a JSON file:

```env
TARGET_COMPANIES=Octopus Energy,EDF,National Grid,Johnson Matthey,Arup
```

### 3. Edit `resume/master_resume.txt` (optional)

Required for AI scoring or tailored files, including dashboard scoring. Replace the placeholder with your real CV text. `PROJECT & RESEARCH EXPERIENCE`, `RESEARCH EXPERIENCE`, `PROJECT EXPERIENCE` and `INTERNSHIP EXPERIENCE` are recognised. Describe university work as academic experience and list only techniques you actually used.

Keep API keys/passwords only in the ignored `.env`; never put secrets in `env.template`, committed files or chat. Edit an existing `.env` rather than overwriting it. Old local values override the new defaults, so replace any software roles, India location, four-year experience or Master's ceiling. Leave `NOTIFY_EMAIL` blank until you want email delivery: starting the API sends a test email when email is fully configured.

For a restricted cloud environment, allow the configured job-source domains. The default shortlist uses `www.linkedin.com`, `api.lever.co` (Octopus Energy), `careers.edfenergy.com`, `jobs.nationalgrid.com`, `matthey.com` and `www.arup.com`; discovery redirects/ATS boards may require additional exact hosts. No live source availability is guaranteed by the tests. Review the company shortlist and add employers relevant to your interests.

### 4. Set up email (optional but recommended)

Add one of the email options to `.env` for new-job alerts scoring **70+** within the last two calendar days. The easiest path is Gmail — see [Email setup](#email-setup). Keep `EMAIL_ATTACH_MATERIALS=false` to leave file generation click-only.

---

## Run the application

You need **two processes**: the FastAPI backend (port 8000) and the React frontend (port 5173). The UI proxies API calls to the backend automatically.

### Option A — one command (macOS / Linux)

```bash
source .venv/bin/activate
chmod +x start-ui.sh    # only needed once
./start-ui.sh
```

### Option B — two terminals (all platforms)

**Terminal 1 — API server:**

```bash
cd job-agent
source .venv/bin/activate
python -m uvicorn api.server:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — React UI:**

```bash
cd job-agent/ui
npm run dev
```

### Open the dashboard

Go to **http://localhost:5173**

The API is also available directly at **http://127.0.0.1:8000** (e.g. `GET /api/jobs`).

### Production UI build (optional)

```bash
cd ui && npm run build
```

Serve the `ui/dist/` folder with any static file server. You still need the API running on port 8000 (or update the proxy in your server config).

---

## First-time usage

1. Start the API and UI (see above).
2. Open **http://localhost:5173**.
3. Click **Fetch jobs** in the top-right corner.
4. Wait for the fetch to complete (can take a few minutes depending on how many companies you watch).
5. Jobs appear in the dashboard. New ones show a **New** badge.
6. Click **Open ↗** on any job to view the listing.
7. Wait for scores to fill in (highest match first). Click **Generate resume** or **Generate cover letter** when you want a tailored file.
8. Click **Mark all read** to clear new badges after you've reviewed them.

The server fetches on an interval (`CHECK_INTERVAL_MINUTES`, default 15) and scores any remaining unscored jobs afterward. The UI checks for changes every 30 seconds (every 5 seconds while scoring) and shows a countdown to the next fetch.

---

## Dashboard (UI)

| Feature | Description |
|---------|-------------|
| **Card / Table view** | Toggle between card grid and sortable table |
| **Search** | Filter by job title or company name |
| **Company filter** | Show jobs from one company |
| **Source filter** | Filter by LinkedIn, Greenhouse, Lever, etc. |
| **Location filter** | Show jobs in one city (Bengaluru matches Bangalore, and so on) |
| **Posted filter** | Show jobs posted in the last 1, 3, 7, 14, or 30 days |
| **Sort** | Highest match score by default; newest or oldest as alternatives |
| **Match score** | Gemini/OpenAI/Claude 0–100 fit vs your master resume |
| **Generate resume** | One-page tailored PDF on click |
| **Generate cover letter** | One-page JD-tailored PDF on click |
| **Remove** | Hide a listing so it does not come back on later fetches |
| **Fetch jobs** | Trigger a manual fetch (rate-limited to the poll interval) |
| **Mark all read** | Clear all "new" badges |
| **Next fetch countdown** | Live timer showing when the next automatic fetch runs |
| **New-job animation** | Confetti burst when new jobs appear |
| **Auto-refresh** | Polls for changes every 30 seconds while the tab is visible |

---

## CLI mode

You can run the fetcher without the UI — useful for servers or cron jobs.

```bash
source .venv/bin/activate

# Fetch once and exit
python main.py --once

# Fetch every N minutes (same interval as CHECK_INTERVAL_MINUTES)
python main.py

# Send a test email to verify email config
python main.py --test-email

# AI scoring mode (requires GEMINI_API_KEY, OPENAI_API_KEY, or CLAUDE_API_KEY and master_resume.txt)
python main.py --once --with-ai
```

Logs are written to `logs/job_agent.log`.

---

## Configuration reference

All settings are loaded from `.env` and `config/companies.json` by `config.py`. Copy `env.template` to get started.

### Profile

| Variable | Default | Description |
|----------|---------|-------------|
| `USER_NAME` | *(empty)* | Your name (shown in CLI and API meta) |
| `TARGET_ROLES` | Energy/graduate/scientific role variants | Comma-separated titles with flexible matching for related graduate STEM roles |
| `JOB_LOCATION` | `London, United Kingdom` | Location passed to LinkedIn searches |
| `FILTER_BY_ROLE` | `true` | Keep matching roles and related scientific/graduate variants for scoring |
| `FILTER_BY_DOMAIN` | `true` | Generic STEM titles need energy/materials/chemistry/sustainability evidence when a description is available; unknown descriptions remain eligible with an uncertainty indicator |
| `FILTER_BY_LOCATION` | `true` | Reject known overseas roles; accept explicitly UK-eligible remote roles |
| `MIN_MATCH_SCORE` | `65` | Minimum AI score to act on a job (`--with-ai` only) |
| `EMAIL_MIN_SCORE` | `70` | Minimum AI score for new-job email alerts |
| `EMAIL_MAX_POSTED_DAYS` | `2` | Only email 70+ jobs posted today or within the previous two calendar days. `0` disables the age filter |
| `EMAIL_ATTACH_MATERIALS` | `false` | Attach tailored resume and cover letter PDFs to 70+ job alerts. Keep `false` on the first fetch to avoid generating files (and spending tokens) for every matching job |
| `JOB_LOOKBACK` | `r604800` | LinkedIn time filter (604800 s = last 7 days) |
| `COMPANIES_CONFIG_PATH` | `config/companies.json` | Path to your company shortlist JSON |
| `TARGET_COMPANIES` | *(none)* | Alternative: comma-separated companies in `.env` |
| `RESUME_PATH` | `resume/master_resume.txt` | Path to master resume for AI mode |
| `RESUME_MIN_ATS_SCORE` | `80` | Legacy diagnostic target; missing skills are reported, never inserted |
| `RESUME_TARGET_ATS_SCORE` | `90` | Legacy diagnostic target; truthful CV content takes priority |

### Experience filter

| Variable | Default | Description |
|----------|---------|-------------|
| `EXPERIENCE_YEARS` | `0` | Full-time professional experience; academic projects/internships do not count as industry employment |
| `EXPERIENCE_MIN` | `0` | Displayed profile minimum; no lower-bound rejection of graduate jobs |
| `EXPERIENCE_MAX` | `0` | Reject unmet mandatory professional requirements above this ceiling |
| `FILTER_BY_EXPERIENCE` | `true` | Enable/disable seniority and mandatory experience filtering |
| `HIGHEST_COMPLETED_EDUCATION` | `bachelors` | Awarded education level; legacy `MAX_EDUCATION` is only a fallback when this is unset |
| `CURRENT_EDUCATION` | `masters` | Current study level; does not change the highest completed qualification |
| `CURRENT_EDUCATION_STATUS` | `in_progress` | Current study status; application-time completed-Master's requirements remain unmet |
| `CURRENT_EDUCATION_DISCIPLINE` | `Advanced Materials Science and Engineering` | Discipline used to assess relevant Master's requirements |
| `CANDIDATE_GRADUATION_YEAR` | `2027` | Expected graduation cohort; programme start years are assessed separately |
| `CANDIDATE_AVAILABLE_FROM` | `2027-10-01` | Earliest full-time start (ISO date); missing dates are kept, overlapping seasonal/flexible dates need confirmation |
| `FILTER_BY_EDUCATION` | `true` | Enable/disable education filtering |
| `REJECT_12_MONTH_CONTRACT` | `true` | Reject explicit 12-month/one-year contracts independently of other filters |

### Fetch settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CHECK_INTERVAL_MINUTES` | `15` | How often the background poller fetches new jobs |
| `FETCH_CONCURRENCY` | `8` | Parallel threads for **career-site** fetches (LinkedIn is always sequential) |
| `WORKDAY_SEARCH_TERMS` | `graduate,energy,sustainability,materials,scientist,analyst,engineer` | One rotating term per board per cycle; empty fetches all roles within the existing 400-result cap. Explicit legacy `WORKDAY_SEARCH_TEXT` overrides other than `graduate` remain supported when this setting is absent |
| `ENABLE_BROAD_LINKEDIN_SEARCH` | `true` | Add company-independent role/domain searches alongside the shortlist |
| `BROAD_SEARCH_QUERIES` | 21 graduate/energy/materials queries in `env.template` | Existing 14 searches plus seven 2027 graduate searches, using `JOB_LOCATION` |
| `BROAD_SEARCH_QUERIES_PER_CYCLE` | `4` | Rotating broad queries per cycle, sharing the existing total search cap with company queries |
| `ATS_DETAIL_REQUESTS_PER_BOARD` | `10` | Maximum official SmartRecruiters/Workday detail attempts per board fetch; reuse cached descriptions and rotate pending attempts. `0` disables detail requests |
| `LINKEDIN_MIN_DELAY_SECONDS` | `6` | Minimum pause between LinkedIn requests (~10/min) |
| `LINKEDIN_MAX_REQUESTS_PER_MINUTE` | `10` | Hard cap on LinkedIn requests per rolling minute |
| `LINKEDIN_MAX_REQUESTS_PER_HOUR` | `80` | Hard cap on LinkedIn requests per rolling hour |
| `LINKEDIN_MAX_SEARCHES_PER_CYCLE` | `20` | Combined company and broad searches per fetch; reserve company capacity and rotate remaining queries |
| `SCORE_BATCH_SIZE` | `80` | Jobs scored per Gemini call after fetch |

### API keys

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key (preferred for scoring and resume rewrite) |
| `GOOGLE_CLOUD_PROJECT` | Optional Cloud project id bound to the key |
| `AI_PROVIDER` | `auto` (Gemini if set, else OpenAI, else Claude), `gemini`, `openai`, or `claude` |
| `GEMINI_SCORE_MODEL` | Model for match scores (default `gemini-3.5-flash-lite`) |
| `GEMINI_MODEL` | Model for resume rewrite (default `gemini-3.6-flash`) |
| `SCORE_BATCH_SIZE` | Jobs per scoring request (default `80`) |
| `OPENAI_API_KEY` | OpenAI key — used if Gemini is unset or a Gemini call fails |
| `OPENAI_MODEL` | OpenAI Chat Completions model (default `gpt-4o-mini`) |
| `CLAUDE_API_KEY` | Anthropic last-resort fallback if Gemini and OpenAI are not set |

---

## Email setup

Set `NOTIFY_EMAIL` to the address that should receive alerts, then configure **one** transport below. Alerts go out after AI scoring and only include **new**, eligible jobs with a match score of **70** or higher (`EMAIL_MIN_SCORE`) posted today or within the previous two calendar days (`EMAIL_MAX_POSTED_DAYS=2`). Each listing in the email shows its score. A job is emailed **once**; after a successful send it is not included in later alerts.

Set `EMAIL_ATTACH_MATERIALS=true` to generate (or reuse) a tailored resume and cover letter PDF for each 70+ job and attach them to the alert. Leave this **false** until after the initial fetch, or the first run can create a large number of files and spend many LLM tokens.

### Option 1 — Gmail (easiest)

1. Enable 2FA on your Google account.
2. Create an [App Password](https://myaccount.google.com/apppasswords).
3. Add to `.env`:

```env
NOTIFY_EMAIL=your.email@gmail.com
GMAIL_APP_PASSWORD=your_16_char_app_password
```

### Option 2 — Custom SMTP

```env
NOTIFY_EMAIL=your.email@gmail.com
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your_smtp_user
SMTP_PASSWORD=your_smtp_password
SMTP_FROM=alerts@example.com
SMTP_FROM_NAME=Job Agent
SMTP_USE_TLS=true
```

### Option 3 — Maileroo API

```env
NOTIFY_EMAIL=your.email@gmail.com
MAILEROO_API_KEY=your_sending_key
```

### Test your email config

```bash
python main.py --test-email
```

Or via the API:

```bash
curl -X POST http://127.0.0.1:8000/api/email/test
```

---

## Optional: AI scoring and resumes

If Gemini returns **401**, the key is the wrong type. Create a Developer API key at [Google AI Studio](https://aistudio.google.com/apikey) (usually starts with `AIza`) and put it in `GEMINI_API_KEY`. A Gemini Pro *app* subscription and a Cloud Console key named “GeminiKey” are not always the same thing. If Gemini still fails, set `OPENAI_API_KEY` from [platform.openai.com/api-keys](https://platform.openai.com/api-keys) and the app will retry with ChatGPT automatically.

```env
GEMINI_API_KEY=your_key
GOOGLE_CLOUD_PROJECT=your_project_number
OPENAI_API_KEY=your_openai_key
AI_PROVIDER=auto
```

Also copy your resume to `resume/master_resume.txt`.

**Dashboard:** listings are sorted by **Highest match** by default. After each fetch the API scores unscored jobs in the background (one integer 0–100, no match writeup). A compact “Scoring N / total” line appears while that runs. Email alerts include eligible new jobs scoring **70+** posted today or within the previous two calendar days. **Generate resume** and **Generate cover letter** stay click-only with `EMAIL_ATTACH_MATERIALS=false`. Resume generation rewrites existing research/experience bullets and an existing summary; Python preserves headers, evidenced skills, projects, education and certifications, then writes a one-page PDF. Missing skills remain ATS diagnostics. Cover letters use a fact pack extracted from your CV. Unscored jobs sort last. Per-card **Re-score** still works.

**CLI:**

```bash
python main.py --once --with-ai
```

CLI fetch then scores all remaining unscored jobs with the same batch helper. Resume and cover letter files are not auto-generated.

Match score is a single 0–100 fit rating against a short profile extracted from your resume. Use it to apply from the top of the list.

---

## API reference

Base URL: `http://127.0.0.1:8000`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/jobs` | All jobs + metadata. Query params: `company`, `search`, `sort` (`newest`/`oldest`), `source`, `applied` |
| `GET` | `/api/jobs/status` | Lightweight status: counts, scoring progress |
| `GET` | `/api/companies` | Distinct company names in the database |
| `GET` | `/api/meta` | Full metadata: profile, fetch status, email config, poll interval, AI provider |
| `POST` | `/api/fetch` | Start a background fetch |
| `POST` | `/api/fetch/sync` | Fetch jobs now and wait for result |
| `POST` | `/api/jobs/mark-read` | Mark all jobs as read (clear "new" badges) |
| `POST` | `/api/jobs/{job_id}/applied` | Mark or unmark a job as applied |
| `DELETE` | `/api/jobs/{job_id}` | Remove/dismiss a job |
| `POST` | `/api/jobs/{job_id}/score` | Score one job against the master resume |
| `POST` | `/api/jobs/{job_id}/resume` | Generate a one-page tailored resume |
| `GET` | `/api/jobs/{job_id}/resume` | Download the tailored PDF |
| `POST` | `/api/jobs/{job_id}/cover-letter` | Generate a one-page tailored cover letter |
| `GET` | `/api/jobs/{job_id}/cover-letter` | Download the tailored cover letter PDF |
| `POST` | `/api/email/test` | Send a test email |

### Example

```bash
# Get all jobs
curl http://127.0.0.1:8000/api/jobs

# Fetch jobs now
curl -X POST http://127.0.0.1:8000/api/fetch/sync

# Check if anything changed (used by the UI for smart polling)
curl http://127.0.0.1:8000/api/jobs/status
```

---

## Project structure

```
job-agent/
├── api/
│   └── server.py              # FastAPI backend + background poller
├── ai/
│   ├── llm.py                 # Gemini / OpenAI / Claude wrapper
│   ├── job_scorer.py          # Job match scoring
│   ├── resume_builder.py      # One-page tailored resume (PDF)
│   └── cover_letter.py        # One-page tailored cover letter (PDF)
├── config/
│   ├── companies.example.json # Example company list (committed)
│   └── companies.json         # Your company list (gitignored — create locally)
├── jobs/
│   ├── job_fetcher.py         # LinkedIn + orchestration
│   ├── career_fetcher.py      # Career-site fetching
│   ├── career_registry.py     # ATS URLs and board mappings
│   ├── job_store.py           # SQLite read/write
│   ├── database.py            # Schema and migrations
│   └── ats/                   # Greenhouse, Lever, Ashby, SmartRecruiters
├── notifications/
│   ├── email_notifier.py      # SMTP email sender
│   ├── dispatch.py            # Eligible high-score job alerts
│   └── maileroo_api.py        # Maileroo transport
├── resume/
│   ├── master_resume.example.txt  # Resume template (committed)
│   ├── master_resume.txt          # Your resume text (gitignored)
│   └── master_resume.pdf          # Your resume PDF with hyperlinks (gitignored)
├── resumes/                   # Generated tailored resumes (gitignored)
├── cover_letters/             # Generated tailored cover letters (gitignored)
├── ui/                        # React dashboard (Vite)
├── data/                      # SQLite database (gitignored, auto-created)
├── logs/                      # Application logs (gitignored)
├── config.py                  # Loads .env + companies.json
├── env.template               # Environment variable template (committed)
├── main.py                    # CLI entry point
├── start-ui.sh                # Start API + UI together (macOS/Linux)
└── requirements.txt           # Python dependencies
```

### Job sources and deduplication

Each fetch pulls from:

1. **Career-site APIs** — Greenhouse, Lever, Ashby, SmartRecruiters and Workday, for shortlisted companies, with supported ATS discovery. SmartRecruiters and Workday use bounded official JSON detail enrichment. Workday rotates one search term per board without increasing its pagination budget.
2. **LinkedIn** — company searches **and** company-independent graduate/domain searches. Results from unlisted employers are eligible. With the default five companies and four broad queries, each cycle plans nine searches; all still use the existing serialized rate limiter and shared search/description budget. Search requests precede description requests, so enrichment does not consume the quota before broad discovery starts. Description candidates then take turns across queries to share the remaining quota.

Broad query cursors advance only for attempted searches. The 14 default phrases rotate four at a time, wrapping around; larger company shortlists rotate within the remaining search slots. Workday terms rotate independently for each board. Rotation cursors are in memory and reset when the process restarts; use the continuous CLI or API poller to cover subsequent cycles.

Discovery uses a broad STEM title prefilter, then full-description eligibility/domain checks, then optional AI scoring. Generic graduate programmes, consultants, scientists and research assistants need relevant domain evidence when their descriptions are known. Missing descriptions remain visible as **Description unavailable**, with an incomplete-evaluation tooltip and a maximum AI score of 60, below the email threshold. London and London-hybrid preference, followed by UK-remote preference, remains in the scoring rubric; UK eligibility filtering does not make all UK locations equally preferred.

Jobs are deduplicated by:

- **`job_id`** — unique per source (e.g. `li_123456`, `gh_postman_456`)
- **`dedup_hash`** — cross-source dedup from company + title + location

---

## Troubleshooting

### "No jobs yet" after fetching

- Check that `config/companies.json` has companies listed.
- Verify `JOB_LOCATION` matches where you want to work.
- Try setting `FILTER_BY_ROLE=false` temporarily to see all jobs at each company.
- Check API logs in the terminal running uvicorn.

### Fetch button says "runs every 5 minutes"

Manual fetches are rate-limited to the same interval as background polling (`CHECK_INTERVAL_MINUTES`). Wait for the countdown or increase the interval in `.env`.

### Email not working

- Run `python main.py --test-email` and read the error message.
- For Gmail: make sure you're using an **App Password**, not your regular password.
- The UI shows a warning banner if email is misconfigured — check `/api/meta` → `email_status`.

### UI shows "Failed to load jobs"

- Make sure the API server is running on port 8000.
- The UI dev server proxies `/api` to `http://127.0.0.1:8000` — both must be running.

### `ModuleNotFoundError` or import errors

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Port already in use

```bash
# Find and kill the process on port 8000 or 5173
lsof -ti:8000 | xargs kill
lsof -ti:5173 | xargs kill
```

### LinkedIn "too many requests" / HTTP 429

LinkedIn's guest job endpoints throttle bursts. The fetcher stays under a conservative cap (about **10 requests per minute** and **80 per hour**), searches companies sequentially with a 6s gap, and skips the rest of the LinkedIn cycle if it still gets a 429. Career-site fetches are unaffected. If 429s continue, raise `LINKEDIN_MIN_DELAY_SECONDS` or lower `LINKEDIN_MAX_SEARCHES_PER_CYCLE` in `.env`.

### Slow first fetch

Career-site fetching is network-bound. With many companies, the first cycle can take several minutes. Increase `FETCH_CONCURRENCY` in `.env` (default `8`) to speed **career sites** up. Do not raise LinkedIn rate-limit settings to go faster — that is what triggers HTTP 429.
