# Phone-width overflow check, 390 px

Viewport 390x844. `scripts/check_phone_width.py` measures `document.documentElement.scrollWidth` against 390. A page passes when scrollWidth is no greater than the viewport width.

| Page | Viewport | scrollWidth | Result |
|---|---|---|---|
| public home | 390x844 | 390 | pass |
| admin dashboard | 390x844 | 390 | pass |
| admin recaps list | 390x844 | 390 | pass |
| admin accounts list | 390x844 | 390 | pass |

Tables sit inside a scroll container (`.table-scroll`), so the measurement is page-level: a wide table scrolls inside its own container and does not widen the document. This check does not measure the width of the tables themselves.

Pages measured:

- public home: https://andrew-vera26.github.io/iphs400-mp2-cms/
- admin dashboard: http://localhost:8000/admin
- admin recaps list: http://localhost:8000/admin/recaps
- admin accounts list: http://localhost:8000/admin/accounts
