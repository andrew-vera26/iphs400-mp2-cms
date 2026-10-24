# IPHS 400 Mini-Project #2: Kenyon Model UN Recaps CMS

Andrew Vera · 24 October 2026 · Repo: https://github.com/andrew-vera26/iphs400-mp2-cms · Live site: https://andrew-vera26.github.io/iphs400-mp2-cms/

## 1. What I built, and which grill decisions were mine

I built a content management system for the Kenyon Model UN club. Members write trip recaps in a FastAPI and SQLite console, officers publish them, and `cms publish` followed by `cms deploy` renders a static site to GitHub Pages. Recaps move from Draft to Submitted to Published, and the suite has 531 tests. The full feature list is in the README.

Three grill decisions were mine. The model's first design let only Admins log in, which would have meant chasing the President across campus to enter every recap. I reversed it. Editors now log in on the President's laptop at Sunday meetings, and I recorded that in ADR-003. I also set the permission rule that Editors see and change only their own Recaps while Admins alone publish, and I ruled out Account reactivation and email password reset.

## 2. Where the AI drifted, and what caught it

The clearest drift was on T04, the Markdown sanitizer. The spec says it strips all raw HTML. The model's first version escaped it instead, so `<script>` and `onerror=` survived as visible text, and three of my tests failed. It proposed loosening them to fit. I caught it by reading the failing tests against the spec instead of against the model's explanation. I made it restore the original assertions and fix the code, and the final version drops every raw-HTML token.

Two other things surfaced. On T01 the model wrote implementation before showing a failing test, and I only found out by asking it directly. Later, `/code-review`, which compares the diff to the spec, found that an Editor's save could land after an Admin had Published the Recap (fixed with a status-guarded UPDATE), and that `cms backup` of a missing database wrote an empty archive.

The bug I remember best is a small one. `.env.example` had an unquoted `CMS_SITE_TITLE` containing spaces. `uv run --env-file` couldn't parse that line and silently dropped every variable after it, so the seed script exited asking for `CMS_ADMIN_PASSWORD`. My tests had passed the values through the environment and never ran the documented command, so they never saw it. Running that command against a fresh clone did.

## 3. Skills, prompts, and resources

I followed the course workflow: `/grill-with-docs`, `/to-spec`, and `/to-tickets` on Opus 5.5, then nine tickets on Sonnet 5.5 at medium effort. Each ticket ran the same loop: `/clear`, `/implement` with `/tdd` (tests red before any code), `/code-review` in a fresh subagent, the findings posted on the GitHub issue, then a closing commit that names every file. I also used research subagents for the WordPress field notes, `/clear` between tickets, one manual `/compact`, and one handoff. I kept tickets small enough for one fresh session, which cost me some setup time per ticket but meant the model never worked from a stale, crowded context.

## 4. What I would add next, and what the budget showed

| Stage | Plan | Actual (% of a 5-hour window) |
|---|---|---|
| Planning (grill, spec, tickets) | 18% | 16% |
| Tickets T01–T09 (implement, test, review) | 72% | 69% |
| Final polish (admin stylesheet, 403 page, screenshots, README, deploy) | not planned | 12% |

The plan held: tickets averaged 7.7% against 8% planned, with T03 the most expensive at 13% and T05 the cheapest at 3%. What I missed was work outside the tickets. The final polish cost 12%, more than any ticket except T03, and 59 points of the meter, about a third of everything logged, sit under "unlabelled" because I started labelling phases late. The earliest of those rows list models I did not select, and I don't know why the status line reported them. A line for polish and an earlier habit of labelling would have made the plan honest.

The thing I'd change is how I wrote the ground rules. On T02 through T05 I asked the model to "show me them failing before any implementation." It treated that as a report, not a gate. On T05 it showed a real red run (14 failed, 2 passed), implemented, and reached `/code-review` before I'd had a chance to look. The work was fine, but I could only check it after the fact. From T06 on, every prompt named stops: after the red run, after green, and before review. Next time the stops go in the first prompt.

Next I would add a Deploy button in the console (it is terminal-only now), account reactivation, and a styled 404 for the public site. At about 8% per ticket, three tickets fit in one window. Debt I left: status transitions wired in five places, test files that import each other's helpers, and an image check that reads magic bytes without decoding.

## Note on the submission check

`check_submission.py` reports a failure for root-absolute paths in eleven console templates (`templates/admin/` and the console's base template). Those links (`/admin/...`) are correct because the console is served from the root and never published. The rubric rules (S1.7, F2, T6) concern the published site, where the tests and a grep over the rendered `site/` find none. I left the script unchanged and explain the failure here instead.
