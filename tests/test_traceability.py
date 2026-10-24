"""Direct tests for three acceptance criteria that were only covered indirectly.

- #2 criterion 1: the Account schema has every listed field.
- #2 criterion 8: no ad-hoc role checks outside the permission-policy module.
- #10 criterion 8: the Editor table covers every admin-only or state-changing
  console route, or the route is in the documented Editor-allowed list below.
"""
import ast
import re
import sqlite3
from pathlib import Path

import pytest

from app import db, policy
from app.main import create_app
from app.routes import accounts, auth, console, pages, recaps, trips
from tests.test_t01 import ADMIN_ONLY_ROUTES

ROOT = Path(__file__).resolve().parents[1]


# ---- #2 criterion 1: the Account schema -----------------------------------

def test_account_schema_has_every_listed_field(database):
    with db.connect() as conn:
        columns = {r["name"]: r for r in conn.execute("PRAGMA table_info(account)")}
        unique = [r["name"] for r in conn.execute("PRAGMA index_list(account)")
                  if r["unique"]]
        unique_cols = {c["name"] for idx in unique
                       for c in conn.execute(f"PRAGMA index_info({idx})")}
        seeded = conn.execute("SELECT * FROM account").fetchall()

    for name in ("email", "name", "class_year", "role", "password_hash",
                 "active", "created_at"):
        assert name in columns, f"account has no {name} column"
    assert "email" in unique_cols                       # email (unique)
    assert seeded and all(r["password_hash"].startswith("$argon2") for r in seeded)
    assert all(r["active"] == 1 for r in seeded)        # an active flag
    # the created timestamp is filled in on insert, as an ISO-8601 UTC time
    assert all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", r["created_at"])
               for r in seeded)

    # role is `admin` or `editor` and nothing else
    with db.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO account (email, name, class_year, role, "
                     "password_hash) VALUES ('x@example.test', 'X', 2027, "
                     "'owner', 'h')")


# ---- #2 criterion 8: no ad-hoc role checks outside app/policy.py ----------

# a test on the role column (not `SET role = ?`, which assigns it)
SQL_ROLE_TEST = re.compile(r"\b(WHERE|AND|OR|CHECK)\s*\(?\s*role\s*(=|!=|<>|IN\b)",
                           re.IGNORECASE)

# Role comparisons outside the policy that are not permission checks, as
# (file, enclosing function). Each one is about the Account being changed or a
# submitted value, never about what the signed-in Account may do.
ROLE_COMPARISONS_ALLOWED: dict[tuple[str, str], str] = {
    ("app/db.py", "<module>"):
        "the CHECK constraint on account.role: the schema's set of valid roles",
    ("app/accounts.py", "_is_last_active_admin"):
        "the last-active-Admin rule (#3 criterion 5), about the target Account",
    ("app/accounts.py", "set_role"):
        "is the new role a demotion; feeds the last-active-Admin rule",
    ("app/routes/accounts.py", "create_account"):
        "validates the submitted role form field against the known roles",
    ("app/routes/accounts.py", "change_role"):
        "validates the submitted role form field against the known roles",
}


def _is_role(n: ast.AST) -> bool:
    """`x.role`, `role` or `x["role"]`: an operand that is itself a role."""
    return ((isinstance(n, ast.Attribute) and n.attr == "role")
            or (isinstance(n, ast.Name) and n.id == "role")
            or (isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)
                and n.slice.value == "role"))


def _compares_a_role(node: ast.Compare) -> bool:
    return any(_is_role(n) for n in [node.left, *node.comparators])


def role_comparisons(path: Path) -> list[tuple[str, int, str]]:
    """(enclosing function, line, source) for each Python comparison that
    involves a role, and each SQL string that compares the role column."""
    tree = ast.parse(path.read_text())
    source = path.read_text().splitlines()
    found = []

    def visit(node, func):
        for child in ast.iter_child_nodes(node):
            inner = (child.name if isinstance(child, (ast.FunctionDef,
                                                      ast.AsyncFunctionDef))
                     else func)
            if isinstance(child, ast.Compare) and _compares_a_role(child):
                found.append((func, child.lineno, source[child.lineno - 1].strip()))
            elif (isinstance(child, ast.Constant) and isinstance(child.value, str)
                  and SQL_ROLE_TEST.search(child.value)):
                found.append((func, child.lineno, source[child.lineno - 1].strip()))
            visit(child, inner)

    visit(tree, "<module>")
    return found


def test_no_role_comparison_outside_the_policy_module():
    hits = {}
    for path in sorted((ROOT / "app").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel == "app/policy.py":
            continue
        for func, line, text in role_comparisons(path):
            hits.setdefault((rel, func), []).append(f"{rel}:{line} {text}")

    ad_hoc = [h for key, lines in hits.items()
              if key not in ROLE_COMPARISONS_ALLOWED for h in lines]
    assert not ad_hoc, "role checks outside app/policy.py:\n" + "\n".join(ad_hoc)
    # an allowlist entry that no longer matches anything is removed, not kept
    stale = set(ROLE_COMPARISONS_ALLOWED) - set(hits)
    assert not stale, stale


def test_the_role_scan_sees_a_role_check(tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text("def f(account):\n    return account.role == 'admin'\n"
                     "Q = \"SELECT 1 FROM account WHERE role = 'admin'\"\n")
    assert [(f, n) for f, n, _ in role_comparisons(probe)] == [("f", 2),
                                                               ("<module>", 3)]


# ---- #10 criterion 8: the Editor table covers every console route --------

# Console routes an Editor may use, each on a Recap they Own while it is a
# Draft. They change state, so they need an entry here or in ADMIN_ONLY_ROUTES;
# the per-Recap refusals for other people's Recaps are tested in T03, T04, T06.
EDITOR_ALLOWED_ROUTES: dict[tuple[str, str], str] = {
    ("POST", "/admin/recaps"): "create a Recap Draft (#4 criterion 4)",
    ("POST", "/admin/recaps/preview"): "Preview a Recap before its first save",
    ("POST", "/admin/recaps/{recap_id}"): "edit their own Draft (#4 criterion 10)",
    ("POST", "/admin/recaps/{recap_id}/delete"): "delete their own Draft (#4 criterion 10)",
    ("POST", "/admin/recaps/{recap_id}/submit"): "Submit their own Draft (#5 criterion 1)",
    ("POST", "/admin/recaps/{recap_id}/preview"): "Preview their own Draft",
    ("POST", "/admin/recaps/{recap_id}/images"): "upload to their own Draft (#7 criterion 1)",
    ("POST", "/admin/recaps/{recap_id}/images/{image_id}/delete"):
        "delete an Image from their own Draft",
}

ROUTERS = (auth, console, accounts, trips, recaps, pages)
STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}


def _action(route) -> str:
    """The policy action named by the route's `require(...)` guard."""
    actions = [cell.cell_contents
               for dep in route.dependant.dependencies
               for name, cell in zip(dep.call.__code__.co_freevars,
                                     dep.call.__closure__ or ())
               if name == "action"]
    assert len(actions) == 1, (route.path, actions)
    return actions[0]


def console_routes() -> list[tuple[str, str, str]]:
    """(method, path template, policy action) for every /admin route."""
    return sorted((method, route.path, _action(route))
                  for router in ROUTERS for route in router.router.routes
                  if route.path.startswith("/admin")
                  for method in route.methods)


def _template_for(method: str, concrete: str, templates) -> tuple[str, str] | None:
    """The route a concrete table row reaches. A literal segment beats a path
    parameter, as it does when the app dispatches (preview before {page_id})."""
    matches = [(m, t) for m, t in templates if m == method
               and re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", t), concrete)]
    return min(matches, key=lambda mt: mt[1].count("{"), default=None)


def test_routers_seen_here_are_the_whole_console():
    from tests.test_t09 import swept_routes
    templates = {(m, re.sub(r"\{[^}]+\}", "1", re.sub(r"\{filename\}", "x.png", p)))
                 for m, p, _ in console_routes()}
    assert templates == set(swept_routes(create_app(), "/admin"))


def test_every_admin_only_or_state_changing_route_is_in_a_table():
    routes = console_routes()
    templates = [(m, p) for m, p, _ in routes]
    in_editor_table = {_template_for(m, p.replace("{other}", "1"), templates)
                       for m, p in ADMIN_ONLY_ROUTES}
    assert None not in in_editor_table, "an ADMIN_ONLY_ROUTES row matches no route"

    admin_only = {(m, p) for m, p, a in routes
                  if policy.ROLE_RULES.get(a) == frozenset({policy.ADMIN})}
    must_be_listed = admin_only | {(m, p) for m, p, _ in routes
                                   if m in STATE_CHANGING}
    missing = sorted(must_be_listed - in_editor_table - set(EDITOR_ALLOWED_ROUTES))
    assert not missing, missing

    # every admin-only route is in the Editor table, never in the allowed list
    assert admin_only <= in_editor_table
    assert not admin_only & set(EDITOR_ALLOWED_ROUTES)
    assert set(EDITOR_ALLOWED_ROUTES) <= set(templates), "stale allowed entry"


# ---- no root-absolute paths in any template --------------------------------

def test_no_template_has_a_root_absolute_href_or_src():
    """The same two patterns as scripts/check_submission.py, on every tracked
    template, so the submission check cannot fail on a console template."""
    import subprocess
    tracked = subprocess.run(["git", "ls-files", "templates/*.html",
                              "templates/**/*.html"], cwd=ROOT,
                             capture_output=True, text=True, check=True)
    paths = sorted(set(tracked.stdout.split()))
    assert paths, "no tracked templates found"
    bad = [f"{p}:{n}" for p in paths
           for n, line in enumerate((ROOT / p).read_text().splitlines(), 1)
           if 'href="/' in line or 'src="/' in line]
    assert not bad, "root-absolute href/src:\n" + "\n".join(bad)
