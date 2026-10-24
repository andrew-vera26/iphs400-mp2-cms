# Kenyon Model UN Recaps CMS

A content management system where club members write trip recaps and officers publish them to a static GitHub Pages site. It is IPHS 400 Mini-Project #2.

## Features

- Login with argon2 password hashes and CSRF protection on every form
- Two roles, Admin and Editor, with Editors limited to their own Recaps
- Trips and Recaps, with Draft, Submitted and Published states
- Pages that appear in the public navigation
- A dashboard with counts and a filterable content list
- A Markdown editor with a sanitized Preview
- Image uploads with required alt text
- Account management, including Deactivate
- `cms publish`, `cms deploy` and `cms backup` commands

## Live URL

- Site: <https://andrew-vera26.github.io/iphs400-mp2-cms/>
- Repository: <https://github.com/andrew-vera26/iphs400-mp2-cms>

## Run locally

Every command runs from the repository root, because `CMS_DATABASE` and
`CMS_UPLOADS` are relative paths, and goes through `uv run --env-file .env` so
the settings in `.env` are loaded.

1. Clone and install:

   ```bash
   git clone https://github.com/andrew-vera26/iphs400-mp2-cms.git
   cd iphs400-mp2-cms
   uv sync
   ```

2. Create `.env` from the template, then edit it and set `CMS_ADMIN_PASSWORD`
   and `CMS_EDITOR_PASSWORD` (and a long random `CMS_SECRET_KEY`). Keep values
   with spaces in double quotes. `.env` is gitignored.

   ```bash
   cp .env.example .env
   ```

3. Seed the demo Admin and Editor accounts, a Trip, Recaps in every status and
   two Pages. It is safe to run again.

   ```bash
   uv run --env-file .env python scripts/seed_demo.py
   ```

4. Start the admin console and open <http://localhost:8000/login>. Log in as
   `admin@example.test` or `editor@example.test` with the passwords from `.env`.

   ```bash
   uv run --env-file .env cms serve
   ```

5. Render the published content into `site/` (generated; never edit it by hand).
   Preview it with `python3 -m http.server -d site 8001`.

   ```bash
   uv run --env-file .env cms publish
   ```

6. Back up the database and uploaded images into a folder **outside** the
   repository (the command refuses a folder inside it):

   ```bash
   uv run --env-file .env cms backup ~/cms-backups
   ```

7. Push `site/` to the `gh-pages` branch, then in the repository's Settings ->
   Pages choose **Deploy from a branch**, `gh-pages`, `/ (root)`:

   ```bash
   uv run --env-file .env cms deploy
   ```

## What is here

```text
app/               the FastAPI admin console and the publisher
  routes/          login, console, trips, recaps, pages and accounts routes
  static/          admin.css, the admin stylesheet
templates/         Jinja templates: admin/ (console) and public/ (published site)
tests/             one test file per ticket (T00-T09), plus the admin style and 403 page tests
scripts/           seed_demo.py, usage_report.py, check_submission.py
docs/              screenshots, handoffs, process notes and the project report
docs/adr/          three decision records (ADR-001 to ADR-003)
.claude/hooks/     the context meter and usage ledger
CONTEXT.md         the project glossary
```

The CMS is complete (tickets T00-T09), both exercise functions, `decide()` and `spend()`, are implemented, the test suite passes, and the demo site is published to GitHub Pages from the `gh-pages` branch.

Run `uv run python scripts/check_submission.py --stage 2` before you submit.

## Backends used

| Backend | Models | Phases | Swaps |
| --- | --- | --- | --- |
| Anthropic API | Claude Opus 5.5 and Sonnet 5.5 | All phases | None |

## Generative AI Use Statement

I built this project with Claude Code, following the grill, spec, tickets, and per-ticket workflow from the course manual. I used Claude Opus 5.5 for the grilling, spec, and ticket breakdown, and Claude Sonnet 5.5 at medium effort for implementing and reviewing each ticket. The skills I ran were grill-with-docs, to-spec, to-tickets, implement, tdd, code-review, and handoff. I also ran research subagents to look up WordPress functions for my field notes, and used /clear and /compact to manage context. The grill decisions were mine, including reversing the model's admins-only account design so Editors can log in at club meetings, and the rule that Editors see only their own Recaps.

Two prompts I used:
1. "Write the new tests first and run them. Show me the red run, then STOP and wait for me to say go before you write any implementation code."
2. "Stop. Answer these before doing anything else, with no changes to files. (1) Did you write tests/test_t05.py before any implementation code? (2) Did you run them and see them fail before implementing, and where in this session can I see that?"

One real failure: on the first ticket the model implemented before showing a failing test, even though the workflow requires it. I caught it by asking directly whether it had run the tests red first, and it admitted it had not. After that I asked for the red run explicitly on every ticket. On T05 my prompt asked to show the red run but did not say to stop, so the model showed it and kept going, and I added an explicit stop to every later prompt.
