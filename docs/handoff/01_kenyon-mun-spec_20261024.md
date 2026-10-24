# Handoff: kenyon-mun-spec
- **Written:** 2026-10-24 10:42  **Session:** 3c83bfcc-3eab-41bd-893a-8b0e0abb030e
- **Agent:** claude  **Stream:** main  **Continues:** none
- **Status:** Grill and spec stages done; spec is issue #1. Next: break the spec into tickets (`tickets` stage).
- **Branch:** main  **HEAD:** 06d4fd9 Fix Deploy in CONTEXT.md: cms publish renders, cms deploy pushes  **Working tree:** 6 uncommitted (listed below, all intentionally left)
- **Model/effort used:** Opus 5.5, medium  **Context at handoff:** 34%

## Goal (1–3 sentences)
Build the Kenyon Model UN Recaps CMS for IPHS 400 MP2: a local admin console plus a static Public site that covers all seven required capabilities. The next session turns spec issue #1 into vertical-slice ticket issues (T01, T02, …) ready for implementation.

## Done (this session)
- Ran `/grill-with-docs`. `CONTEXT.md` now holds the full glossary (54dfbfe, plus the Deploy wording fix in 06d4fd9).
- Wrote `docs/adr/ADR-003-editors-at-sunday-meetings.md`: Editors exist, only Admins Publish, Editors use the Console laptop at the Sunday meetings, and remote editing is out of scope.
- Published the spec as https://github.com/andrew-vera26/iphs400-mp2-cms/issues/1, labelled `spec` (deliberately not `ready-for-agent`). It covers 67 user stories, a table mapping stories to the seven capabilities, the test seams, and the required tests.
- Edited issue #1 so the Instagram footer URL is a committed constant, not an environment variable. The placeholder is `https://www.instagram.com/REPLACE-ME/`.
- Pushed `main` to origin. No feature branches remain.

## In progress (state on disk right now)
- Nothing is half-built, and no app code has changed since T00.
- The user said to leave these uncommitted until they decide: `notes/usage-ledger.csv` (modified), `notes/cms-content-model-research.md`, and `docs/transcripts/*session_06..09*.md` (untracked).
- `.claude/state/phase` currently says `spec`.

## Next steps (ordered, concrete, each startable in <1 min)
1. Write `tickets` into `.claude/state/phase`.
2. Read issue #1 (`gh issue view 1`), `CONTEXT.md`, and the ADRs in `docs/adr/`.
3. Split #1 into vertical-slice ticket issues labelled `ticket`, each with acceptance tests drawn from #1's Testing Decisions. A sensible order: login, sessions and CSRF; Accounts and roles policy; Trips; Recaps and the status machine; Images; Pages and the Navigation bar; console dashboard, list and Preview; `render_site` for the Public site; `cms backup`; seed script. Confirm the breakdown with the user before creating issues.
4. Later, per ticket: write the ticket id into the phase file. Before the closing commit, post the `/code-review` findings on the issue. Commit message starts `T0N:` and ends `Closes #N`.

## Decisions and why (things a fresh session must not re-litigate)
- Editors exist with their own Accounts, but only Admins Publish. The assignment requires two roles, and the officers want to review every Recap first. ADR-003 records this. An earlier "admins only, no editor accounts" version was rejected.
- Deploy and Backup run from the terminal only, with no console buttons. The President owns the terminal, and pushing git from a web request adds failure modes.
- Tests use only the existing seams: the HTTP app with `client`/`client_as`, `render_site(out)`, and the CLI `main(argv)`. The user asked for no new seams.
- The Instagram URL is a committed constant so that `cms publish` is reproducible on any machine. The user will replace the placeholder before the final publish.
- The ban on external links applies to every Body, Pages included.
- Images belong to Recaps only. Pages are text-only, to keep the upload code to one kind of owner.

## Gotchas / traps discovered
- `cms publish` only renders `site/`, and `cms deploy` pushes it (see `app/cli.py`). The first glossary draft wrongly said `cms publish` pushes. That is now fixed.
- The project `CLAUDE.md` says transcripts live in `transcripts/`, but this assignment keeps them in `docs/transcripts/`. Don't move them, and leave any stray files in `transcripts/` alone.
- The user wants feature branches fast-forwarded into `main` and pushed, with the branch deleted afterwards.
- `tests/conftest.py` `client_as` logs in at `/login` with email and password. The login route must match that.

## Verification state
- Tests: the T00 suite was not run this session. No code changed.

## Pointers (read these before anything else)
- https://github.com/andrew-vera26/iphs400-mp2-cms/issues/1 — the spec, the source of truth for tickets
- `CONTEXT.md` — the glossary. Use its terms, such as Recap rather than "post".
- `docs/adr/ADR-001…003` — local console with a static site, the stack, and the Editors decision
- `docs/manual_iphs400_mp2-web-cms_20260922.md` §3.3 — the seven required capabilities
- `tests/conftest.py`, `tests/test_t00.py` — existing fixtures and prior art for tests

## Open questions / risks
- Issue #1 contains choices the user hasn't confirmed: no reactivating Accounts, no password reset by email, Editors see only their own Recaps, the Byline is copied onto a Recap when it is created, and reserved Page Slugs include `admin` and `login`. Raise them with the user before ticketing.
- An "Officers and contact" Page can't include outside links because of the Body ban. Ask if contact emails are needed.

## Suggested skills
- `to-tickets`, if installed, to split issue #1 into tickets. Otherwise create them by hand following `docs/agents/issue-tracker.md`.
- `domain-modeling`, if ticketing surfaces new or conflicting terms.
- `tdd` when implementing each ticket.
- `code-review` before each ticket-closing commit, as `CLAUDE.md` requires.

## How to recover detail if needed
- Previous session: `claude --resume 3c83bfcc-3eab-41bd-893a-8b0e0abb030e`
- Ask it without loading it: `claude -p --resume 3c83bfcc-3eab-41bd-893a-8b0e0abb030e --fork-session --output-format json "<question>"`
- Compaction snapshots: `~/.claude/handoffs/<project-slug>/auto/*_precompact.md`
