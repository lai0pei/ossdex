# ossdex

Collect notable **open-source GitHub repos** into a SQLite database, then browse and search them with a
web UI, a JSON API and an MCP server. The data comes from the GitHub API and nothing else.

For each repo it stores the URL, description, topics, language, license, homepage, stars, forks, open
issues, created/pushed dates and the **README**, plus a **daily star snapshot** so the UI can show which
repos are rising.

ossdex is a uv workspace with two programs that you run separately and that share one file, `data/ossdex.db`:

| package | command | job |
|---|---|---|
| `ossdex-collector` | `ossdex-collector` | the only part that talks to GitHub: finds repos, fetches READMEs, takes star snapshots, builds the keyword index. Writes the database. |
| `ossdex-server` | `ossdex-server` | web UI, JSON API (`/api`) and MCP server (`/mcp`) in one process. Only reads the database; never calls GitHub, never needs a token. |
| `ossdex-core` | – | shared code: settings, the schema, README chunking, license rules. |

Use it on your own machine, or put both on a VPS and let anyone use the MCP server from the Claude app
with no login (see [Hosting it publicly](#hosting-it-publicly)).

## Setup
```sh
uv sync --all-packages
cp .env.example .env            # set GITHUB_TOKEN (collector only)
(cd web && npm install && npm run build)

uv run --package ossdex-collector ossdex-collector discover --dry-run   # how many repos would the threshold collect?
uv run --package ossdex-collector ossdex-collector update               # fetch everything (the first run is long)
uv run --package ossdex-server ossdex-server serve                      # http://127.0.0.1:8200
```
**GitHub token.** A classic personal access token with **no scopes** is enough (public data). Put it in
`.env` as `GITHUB_TOKEN`. If it is empty, `gh auth token` is tried. The token is only sent to
`api.github.com` and is never printed or logged. Only the collector uses it.

The server serves the UI from `web/dist`, the API under `/api` and the MCP endpoint at `/mcp`, all on
port 8200. It can run while the collector writes (SQLite WAL), and it drops its response cache by itself
when the collector commits.

## The star threshold
`OSSDEX_MIN_STARS` (default `1000`) or `--min-stars N` on any run.
- `ossdex-collector discover --dry-run --min-stars 500` prints how many repos that would mean, and an estimate of
  the requests, before anything is downloaded.
- **Lowering** it adds the repos in the new range (READMEs are only fetched for those).
  **Raising** it hides repos below it (they are kept, so lowering it again brings them back);
  `ossdex-collector prune` deletes them for good, after asking.
- Every run of `discover` reads **all** repos at or above the threshold again, because that is how the
  daily star snapshot is taken. Only READMEs are incremental. Rough cost of a daily run:
  one search page per 100 repos, about 2 GraphQL points each (an estimate from GitHub's cost formula,
  not a measurement), so roughly 1,200 points of the 5,000 hourly allowance for 60,000 repos.

## Commands
| command | what it does |
|---|---|
| `ossdex-collector discover [--min-stars N] [--dry-run] [--budget P]` | search GitHub for qualifying repos and store them; resumable |
| `ossdex-collector refresh` | look up repos the last discover run did not return: deleted, now a fork/archived/unlicensed, renamed |
| `ossdex-collector readmes [--limit N] [--days D]` | fetch READMEs (biggest repos first); refetch ones older than D days (30) |
| `ossdex-collector index [--full]` | rebuild the keyword-search chunks (`update` already does this) |
| `ossdex-collector enrich [--offline]` | tag repos with the Awesome lists they are in and the arXiv papers their README links to |
| `ossdex-collector demand [owner/repo ...] [--topic T --top N] [--days D]` | fetch what users of some projects ask for: most-upvoted open issues, help-wanted and bounty counts (a GitHub search per repo, so on chosen repos only; not part of `update`) |
| `ossdex-collector update` | discover, refresh, READMEs, enrich, keyword-search chunks in order. Safe to stop and run again |
| `ossdex-collector prune` | delete hidden repos (gone, no longer qualifying, below the threshold) |
| `ossdex-collector status` | what is in the database |
| `ossdex-collector schedule install` / `remove` | run `update` daily with launchd (macOS); on Linux `install` prints a crontab line to add yourself |
| `ossdex-server serve [--workers N]` | the UI, API and MCP over HTTP (port 8200) |
| `ossdex-server mcp [--transport stdio\|sse\|streamable-http]` | the MCP server alone; stdio by default, for local clients |

`--budget P` stops a run after P GraphQL points (the hourly allowance is 5,000), so one run never uses
all of your token's quota.

## Star growth needs history
GitHub only reports today's star count, so ossdex takes a **snapshot every day it runs** and computes
"gained in 7 / 30 days" from them. Growth shows up after a week (7-day) or a month (30-day) of daily
runs; until then those columns are empty and the UI says how many days of history exist. Run
`ossdex-collector schedule install` so it happens every day. Days the collector did not run are fine: a gain uses
the closest older snapshot. The daily job only fetches: run `ossdex-collector index` where you browse.

## Finding paid work (freelancing, plugins, hosting)
ossdex can point at where the demand and the money are; finding the clients is up to you.
- **Growing niches**: the `find_niches` tool ranks topics by stars gained,
  stars per repo and how many repos are still maintained. Fast growth with few repos is room to
  specialise (`momentum` sorts small, fast topics first). Needs a few days of star history.
- **Business-model hints**: `ossdex-collector update` reads each README for `hosted_cloud`, `enterprise`,
  `pricing` and `support_consulting` (words like "managed cloud", "enterprise edition", "paid
  support"), and `discover` records funding links (`sponsors`). They are hints that companies already
  pay for services around the project, so those projects have buyers. Filter with `money`.
- **Demand**: `ossdex-collector demand --topic n8n --top 10` stores each repo's most-upvoted open issues
  (feature requests nobody has built) and its help-wanted / bounty counts; the repo drawer and the
  `get_demand` tool show them, and `has_bounties` filters for paid issues.
- **`opportunity_report`** (MCP) combines the above: the fastest-growing niches, their top
  rising repos with business hints and, when fetched, demand.

## Where to run what
- **One machine**: run both on your laptop. Simple, and the data stays with you.
- **One VPS** (public MCP, 300-ish users): collector by cron, server under systemd, same `data/ossdex.db`.
  See [Hosting it publicly](#hosting-it-publicly).
- **Fetch on a server, browse locally**: take a consistent snapshot and copy it:
  ```sh
  # on the server
  sqlite3 data/ossdex.db "VACUUM INTO 'data/ossdex-snapshot.db'"   # one consistent file, safe while running
  # locally
  scp server:/path/to/ossdex/data/ossdex-snapshot.db data/ossdex.db   # remove ossdex.db-wal/-shm first
  ```
  Never copy the live `ossdex.db`: in WAL mode recent writes are still in `ossdex.db-wal`, and a copy
  without them (or taken mid-write) is a corrupt database ("database disk image is malformed").

## Hosting it publicly
`deploy/` has everything: `README.md` (step by step), a `Caddyfile`, a systemd unit, a cron file for the
collector, an env file template and a script that limits the firewall to Cloudflare.

Once it is up, add it in the Claude app (claude.ai → Settings → Connectors → Add custom connector) with
the URL `https://ossdex.<your-domain>/mcp` and no authentication. It then works in the Claude mobile app.

**What the public server does and does not do**
- It answers from the database only. It makes no GitHub calls and uses no token; data is as fresh as the
  last collector run.
- It never inspects the machine it runs on. Tools such as `find_oss_alternatives` take the OS and habits
  from the caller.
- Repo details carry a README excerpt (about 1,500 characters) and a link to GitHub, not the whole file.
- No accounts. Abuse is limited per client: a token bucket per IP for `/api` and for `/mcp`, a cap on requests
  in flight (503 when full), a cap on query-string size (414), and a 5 s limit per query. A client
  that goes over gets 429 with `Retry-After`.
- Capacity: each worker process answers one request at a time, so `OSSDEX_WORKERS` (set it to your
  CPU cores) is how many requests run in parallel. Repeated questions are answered from a per-process cache.
  Measure your own machine with `scripts/loadtest.py`.

## What gets collected
Public repos with at least the threshold of stars that are **not** forks, mirrors, templates or
archived, that have a **license** GitHub recognises (including "other"), and that do not carry one of the
excluded topics (`OSSDEX_EXCLUDE_TOPICS`, by default `awesome-list`, `awesome`, `books`, `tutorial`,
`interview`: lists and tutorials rather than software). A repo that later stops qualifying is hidden,
not deleted.

**Repos without a license** are skipped by default: without one, the code is "all rights reserved"
and not open source. Set `OSSDEX_REQUIRE_LICENSE=false` to keep them too. Search finds them anyway, so
this costs no extra search requests, only more READMEs and index work. The next `update` (then
`index`) brings them in; the UI then marks them "no license" and offers a **Licensed only** filter.
Setting it back to `true` hides them again (`ossdex-collector prune` deletes
them). Keep the setting the same on every run, as each run applies it.

## Limits and drawbacks
- **GitHub search returns at most 1,000 results per query**, so discovery splits the star range (and,
  for a star count that is very common, the creation date) until each slice fits. A single star
  count created on one single day with more than 1,000 repos would still be cut at 1,000; the run
  reports it.
- **Rate limits**: GraphQL gives 5,000 points an hour. The client waits out a close reset and stops
  cleanly on a far one (re-run to resume), backs off on secondary limits and 5xx errors, retries a
  200 reply that is not JSON, asks for smaller search pages (100, then 50, then 25) when GitHub keeps
  timing out, and sends one request at a time. A slice that still fails is left for the next run. The first full run covers about 60,000 repos at 1,000+ stars before filtering (a
  count measured on GitHub in October 2026). Fetching their READMEs is on the order of 2,500 requests of
  20 repos each, which should take well under an hour at one request per 0.4 s plus GitHub's response
  time. These are estimates: send the first run's output back if it is far off.
- **`--dry-run` is an upper bound**: licenses and some filters are applied after reading, so fewer repos
  are stored than counted.
- **Stars are not quality.** Fast-rising young projects and quiet infrastructure libraries under the
  threshold are missed; stars can be faked.
- **No past star history**: it starts the day you first run it.
- READMEs belong to their authors. The public server therefore shows only an excerpt and links to GitHub.

## MCP Desktop Setup

ossdex exposes a FastMCP server with 27 tools and 15 prompts over **Streamable HTTP** at `/mcp`. It makes
no LLM or GitHub calls. Every client connects to one URL:

- **Local**: `http://127.0.0.1:8200/mcp`, while `uv run --package ossdex-server ossdex-server serve` is running.
- **Hosted**: `https://ossdex.<your-domain>/mcp` (see [Hosting it publicly](#hosting-it-publicly)).

The examples below use the local URL; swap in the hosted one if you use that. Cloud connectors (claude.ai,
ChatGPT) run on their vendor's servers and cannot reach `127.0.0.1`, so they need the hosted URL.
The web UI's **Guide & MCP** dialog shows these commands with the URL of the server you opened it on.

### 1. Claude (Desktop & CLI)
- **Claude Code CLI**:
  ```sh
  claude mcp add --transport http ossdex http://127.0.0.1:8200/mcp
  ```
- **Claude Desktop / claude.ai (hosted URL)**: **Settings → Connectors → Add custom connector**, name it
  `ossdex`, URL `https://ossdex.<your-domain>/mcp`, no authentication.
- **Claude Desktop (local server)**: the config file only starts local processes, so bridge to the HTTP
  endpoint with `mcp-remote` (needs Node.js). Add to `~/Library/Application Support/Claude/claude_desktop_config.json`
  on macOS or `%APPDATA%\Claude\claude_desktop_config.json` on Windows:
  ```json
  {
    "mcpServers": {
      "ossdex": { "command": "npx", "args": ["-y", "mcp-remote", "http://127.0.0.1:8200/mcp"] }
    }
  }
  ```
  Restart Claude Desktop. The hammer (🔨) icon shows connected ossdex tools. Type `/` to invoke prompts.

### 2. Gemini (CLI & Antigravity)
- **Gemini CLI**:
  ```sh
  gemini mcp add --transport http ossdex http://127.0.0.1:8200/mcp
  ```
  or by hand in `~/.gemini/settings.json` (`httpUrl` selects Streamable HTTP):
  ```json
  { "mcpServers": { "ossdex": { "httpUrl": "http://127.0.0.1:8200/mcp" } } }
  ```
- **Antigravity**: **Manage MCP servers → View raw config**, then add to `mcp_config.json` (remote servers
  use `serverUrl`):
  ```json
  { "mcpServers": { "ossdex": { "serverUrl": "http://127.0.0.1:8200/mcp" } } }
  ```

### 3. ChatGPT (Desktop, Codex & Web)
- **Option A: Zero-Setup Prompt Library Workflow (Instant)**:
  Open any repo card in the ossdex web app, pick a prompt template (e.g. *Managed Cloud SaaS Wrapper*), click **Copy**, and paste directly into ChatGPT Desktop or web.
- **Option B: ChatGPT Connector (hosted URL)**: with developer mode on, **Settings → Connectors → Create**,
  name it `ossdex`, MCP Server URL `https://ossdex.<your-domain>/mcp`, no authentication.
- **Option C: OpenAI Codex CLI**:
  ```sh
  codex mcp add ossdex --url http://127.0.0.1:8200/mcp
  ```

### Test & Verify
```sh
npx @modelcontextprotocol/inspector
```
Choose the **Streamable HTTP** transport and connect to `http://127.0.0.1:8200/mcp`.

### Tools Reference (27 Tools)
- `search_repos`: keyword search (FTS5, bm25) over README sections plus names, topics and descriptions.
- `list_repos`: structured filtering & sorting (stars, forks, gain_7d, money hints, bounties).
- `get_repo`: repo record, license posture, star history, and a README excerpt with a GitHub link.
- `find_similar`: closest alternatives and competitors by shared keywords, topics and language.
- `compare_repos`: side-by-side comparison of 2–6 repos: velocity, licenses, age, issues.
- `count_repos`: size a niche: grouped counts by language, license kind, topic, or year.
- `get_demand`: inspect top upvoted community issues, user reactions, and bounties.
- `opportunity_report`: fastest-growing niches + rising repos with business hints.
- `find_niches`: rank topics by star growth rate and momentum per repo.
- `get_readme_section`: keyword search inside a repo's README, returning matching sections.
- `get_rising`: repos gaining the most stars over the last 7 or 30 days.
- `facets`: database-wide facet counts for languages, licenses, and topics.
- `find_oss_alternatives`: open-source alternative finder for paid products, using the OS, habits and installed software you pass in; fit scores and install commands.
- More tools: `classify_artifact`, `get_runtime_dependencies`, `classify_growth`, `get_package_adoption`, `analyze_forks`, `get_maintainer_health`, `classify_issues`, `get_commercial_landscape`, `get_company_events`, `check_name_collision`, `license_audit`, `platform_compat`, `saas_base`, `evaluate_brief`.

### Prompts Reference (15 Prompts)
1. `find_oss_alternative(paid_product, habits?, workflow_notes?)`: evaluate and articulate tailored open-source alternatives for a paid product with OS-native install commands and a 15-minute migration plan.
2. `saas_base(idea, language?)`: find a permissively licensed, maintained project to build a product or SaaS on.
3. `vertical_saas_idea(repo_or_niche, target_industry)`: tailor an open-source project to a regulated vertical (Health, Legal, FinTech).
4. `compose_product_stack(idea, core_repos?, language?)`: architect a multi-project product with role assignments and license audit.
5. `monetize_demand_gaps(full_name)`: analyze upvoted issues and bounties to design paid plugins or extensions.
6. `fork_and_rebrand_audit(full_name, product_goal?)`: checklist for trademark stripping, white-labeling, and git upstream tracking.
7. `competitive_moat_analysis(full_name)`: benchmark against closest alternatives to find an underserved wedge.
8. `breakout_opportunity_scan(language?, topic?, days?)`: scan fast-rising topics with few competitors to spot new bets.
9. `freelance_niches(skill_or_stack)`: find platforms businesses deploy and pay consultants to customize.
10. `oss_solution(problem, constraints?)`: evaluate the best open-source solution for a problem with trade-offs.
11. `evaluate_product_brief(full_name, angles?, claims?)`: audit a product idea brief against 10 failure modes (F1-F10).
12. `articulate_repo_ideas(full_name, target_audience?)`: brainstorm 5 concrete product/startup ideas based on an open-source repo.
13. `articulate_stack_ideas(repos, domain_hint?)`: brainstorm 4 '1+1=3' mashup product concepts combining 2 to 6 repos.
14. `learn_repo_80_20(full_name, background?, goal?)`: Pareto 80/20 learning guide: prerequisites, 20% high-value core, 80% noise to skip, 60-min lab.
15. `learn_stack_80_20(repos, background?)`: Pareto 80/20 multi-repo integration surface and weekend prototype project.

**Resource:** `ossdex://repo/{owner}/{name}` is the repo's README excerpt; `ossdex://status` is the database status.

## How to Maximize Benefit (Product & SaaS Ideation Playbook)

Follow the 4-stage workflow to move from a filtered shortlist down to validated commercial products:

### Stage 1: Opportunity Filtering (`Cards` Filter Bar)
- **Fast-Track Filter**: Use the `SaaS-Safe` filter combined with `Business` hints to eliminate restrictive licenses upfront.

### Stage 2: Single-Project Signal Auditing (`Cards` → Modal Popup)
Click any repo card to open the large popup dialog:
- **Fork-to-Star Ratio (≥ 12%)**: High fork ratios prove that companies are actively cloning, self-hosting, and maintaining customized deployments in production.
- **License Posture**:
  - *Permissive (MIT, Apache 2.0, BSD)*: Free for closed-source proprietary SaaS with zero source code disclosure.
  - *Weak Copyleft (LGPL, MPL)*: Safe if kept as an external dependency; library modifications must remain open.
  - *Network Copyleft (AGPL)*: Triggers source code disclosure over network; requires a clean-room API microservice boundary.
- **Community Demand & Bounties**: Click the top issue links to see what users complain about and what features maintainers haven't built yet.
- **MCP Prompt Library**: Choose from 10 single-repo lenses (*Managed Cloud*, *Vertical SaaS*, *Open-Core Gate*, *Paid Extension*, *White-Label Audit*, *Moat Analysis*) and click **Copy**.

### Stage 3: Deepening Data with the CLI
- Fetch issue demand for your shortlisted repos:
  ```sh
  uv run --package ossdex-collector ossdex-collector demand owner/repo
  uv run --package ossdex-collector ossdex-collector demand --topic agent --top 10
  ```
- Keep star growth and rankings fresh with the daily collector:
  ```sh
  uv run --package ossdex-collector ossdex-collector update
  uv run --package ossdex-collector ossdex-collector schedule install    # macOS launchd automated daily run
  ```

### Stage 4: Personalized Alternative Discovery (`Alternatives` Tab)
- Switch to the **Alternatives** tab to find drop-in open-source replacements for paid products (Notion, Postman, TablePlus, Docker Desktop, Raycast, Zapier, 1Password, etc.).
- **Your setup**: pick your OS (guessed from the browser) and tick the habits and tools you use. Nothing is read from your machine.
- **Habit & Workflow Fit Scoring**: Scores fit (0–100%) against the habits you chose (CLI-first, keyboard-driven, native GUI, local-first, self-hosted Docker).
- **Tailored 1-Click Install**: Extracts exact copy-paste installation commands for your OS.
- **LLM Articulation Prompt Library**: Generates grounded prompts for Claude, Gemini, or ChatGPT to get 15-minute step-by-step migration plans and feature gap analyses.

## How it works
```
GitHub API ─► ossdex-collector ─► data/ossdex.db (SQLite, WAL) ─► chunks (FTS5)
                                      │ read-only
                                      ▼
                         ossdex-server (one process)
                           ├─ /api  FastAPI ─► web/ (React, served from web/dist)
                           └─ /mcp  FastMCP (streamable HTTP), same tool code as the stdio server
```
- Server code: `repo_query.py` (SQL filters, sorts, facets, detail, star growth), `search.py` (keywords,
  FTS5 + names/topics), `tools.py` (the tool implementations), `cache.py` (response cache),
  `limits.py` (rate limits), `db.py` (read-only connections, query time limit).
- `repos.enrich_status` is `ok` (visible), `gone`, `filtered` (no longer qualifies) or `below` (under
  the threshold); the last three are hidden everywhere.
- Discovery state (the planned slices and each page cursor) is saved in the database, so a stopped run
  resumes without re-reading.

## Configuration
Collector (in `.env` in the project directory):

| variable | default | |
|---|---|---|
| `GITHUB_TOKEN` (or `OSSDEX_GITHUB_TOKEN`) | – (falls back to `gh auth token`) | collector only |
| `OSSDEX_MIN_STARS` | `1000` | star threshold |
| `OSSDEX_EXCLUDE_TOPICS` | `awesome-list,awesome,books,tutorial,interview` | |
| `OSSDEX_REQUIRE_LICENSE` | `true` | `false` also keeps repos without a license |
| `OSSDEX_DATA`, `OSSDEX_DB` | `data`, `data/ossdex.db` | where everything is stored |
| `OSSDEX_HOME` | nearest workspace root | project directory holding `.env`, `data/`, `web/` |

Server:

| variable | default | |
|---|---|---|
| `OSSDEX_PUBLIC_HOST` | – | public hostname the MCP endpoint accepts; setting it also turns the rate limits on |
| `OSSDEX_WORKERS` | `1` | worker processes; set to the CPU core count |
| `OSSDEX_MAX_QUERIES` | `1` | queries running at once inside a worker |
| `OSSDEX_QUERY_TIMEOUT` | `5` | seconds per request, queue time included |
| `OSSDEX_RATE_LIMIT` | on when `OSSDEX_PUBLIC_HOST` is set | `on` / `off` |
| `OSSDEX_RATE_WEB`, `OSSDEX_RATE_MCP` | `120`, `600` | requests per minute per client IP for `/api` and `/mcp`, all workers together |
| `OSSDEX_MAX_INFLIGHT_API`, `OSSDEX_MAX_INFLIGHT_MCP` | `64`, `32` | requests handled at once per process |
| `OSSDEX_TRUSTED_PROXIES` | – | extra proxy addresses (besides 127.0.0.1) whose `CF-Connecting-IP` is believed |
| `OSSDEX_WEB_DIST` | `web/dist` | where the built UI is |

## Origin
ossdex started as a copy of `trenshift-web` (the UI and MCP code) with its own collector and
database. The two projects share no files at run time; a later fix to the shared parts may have to be
made in both.

## Tests
`uv run pytest` (offline: a fake GitHub that emulates search paging and the 1,000-result cap, a fixture
database). `cd web && npm run build` type-checks and builds the UI.
