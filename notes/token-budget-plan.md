# Token budget plan

| Stage | Model | Effort | Estimate (% of a 5-hour window) |
|---|---|---|---|
| Quick lookups | Haiku 5.5 | low | 1% |
| /grill-with-docs | Opus 5.5 | high | 8% |
| /to-spec | Opus 5.5 | high | 5% |
| /to-tickets | Opus 5.5 | high | 5% |
| /implement + /tdd (per ticket) | Sonnet 5.5 | medium | 5% |
| /code-review (per ticket) | Sonnet 5.5 | high | 3% |

**How many 5-hour windows will the 9 tickets take?** Planning is about 18%. The tickets are 9 x 8% = 72%. That's about 90% of one window, so I'm planning on two to leave room for rework.

**How much of one week is that?** My status line showed 24% of a 5-hour window and 6% of the week, so one full window is roughly 25% of a week. Two windows is about half a week.

**Which stage will I cut first if I'm wrong?** The stretch features (comments, uploads), then I'd drop /code-review from high to medium effort.
(Part 5.4 of the manual. Fill this in before your first /implement.)
