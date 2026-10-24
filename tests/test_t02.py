"""T02: Account management (Admin only)."""
import pytest
from fastapi.testclient import TestClient

from app import accounts, db
from app.main import create_app
from tests.conftest import DEMO_USERS, csrf_from, log_in

GENERIC = "email or password is incorrect"
LIST = "/admin/accounts"
NEW_FORM = "/admin/accounts/new"

NEW_ACCOUNT = {"email": "new.editor@example.test", "name": "New Editor",
               "class_year": "2029", "role": "editor",
               "password": "new-editor-pw"}


# ---- helpers --------------------------------------------------------------

def account_id(email):
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM account WHERE email = ?",
                           (email,)).fetchone()
    return row["id"] if row else None


def account_count():
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM account").fetchone()[0]


def post(c, path, **data):
    """POST a form with a valid CSRF token taken from the Accounts list."""
    token = csrf_from(c.get(LIST))
    return c.post(path, data={"csrf_token": token, **data},
                  follow_redirects=False)


def create(c, **overrides):
    return post(c, LIST, **{**NEW_ACCOUNT, **overrides})


def signed_in(email, password):
    """A fresh client signed in as this Account; its login response too."""
    c = TestClient(create_app())
    return c, log_in(c, email, password)


def make_second_admin():
    accounts.create_account("second.admin@example.test", "Second Admin", 2026,
                            "admin", "second-admin-pw")
    return account_id("second.admin@example.test")


# ---- list and create ------------------------------------------------------

def test_admin_lists_accounts(client_as):
    page = client_as("admin").get(LIST)
    assert page.status_code == 200
    for user in DEMO_USERS.values():
        assert user["email"] in page.text


def test_admin_creates_an_account_that_can_log_in(client_as):
    admin = client_as("admin")
    r = create(admin)
    assert r.status_code == 303 and r.headers["location"] == LIST
    assert NEW_ACCOUNT["email"] in admin.get(LIST).text

    with db.connect() as conn:
        row = conn.execute("SELECT * FROM account WHERE email = ?",
                           (NEW_ACCOUNT["email"],)).fetchone()
    assert row["name"] == "New Editor" and row["class_year"] == 2029
    assert row["role"] == "editor" and row["active"] == 1
    assert row["password_hash"].startswith("$argon2")
    assert NEW_ACCOUNT["password"] not in row["password_hash"]

    c, login = signed_in(NEW_ACCOUNT["email"], NEW_ACCOUNT["password"])
    assert login.status_code == 303
    assert c.get("/admin").status_code == 200


@pytest.mark.parametrize("email", [
    DEMO_USERS["editor"]["email"],
    DEMO_USERS["editor"]["email"].upper(),
    f"  {DEMO_USERS['editor']['email']}  ",
])
def test_duplicate_email_is_refused_with_a_clear_error(client_as, email):
    admin = client_as("admin")
    before = account_count()
    r = create(admin, email=email, password="attacker-chosen-pw")
    assert r.status_code == 400
    assert "already in use" in r.text.lower()
    assert account_count() == before
    # the existing Account is untouched: its own password still works
    _, login = signed_in(DEMO_USERS["editor"]["email"],
                         DEMO_USERS["editor"]["password"])
    assert login.status_code == 303


@pytest.mark.parametrize("overrides", [
    {"role": "superuser"},
    {"class_year": "not-a-year"},
    {"name": "   "},
    {"password": ""},
    {"email": ""},
])
def test_invalid_account_input_is_refused(client_as, overrides):
    admin = client_as("admin")
    before = account_count()
    assert create(admin, **overrides).status_code == 400
    assert account_count() == before


# ---- role changes ---------------------------------------------------------

def test_promotion_takes_effect_on_the_next_request(client_as):
    editor, admin = client_as("editor"), client_as("admin")
    assert editor.get(LIST, follow_redirects=False).status_code == 403
    r = post(admin, f"{LIST}/{account_id(DEMO_USERS['editor']['email'])}/role",
             role="admin")
    assert r.status_code == 303
    # same session, no new login
    assert editor.get(LIST).status_code == 200


def test_demotion_takes_effect_on_the_next_request(client_as):
    admin = client_as("admin")
    second_id = make_second_admin()
    second, login = signed_in("second.admin@example.test", "second-admin-pw")
    assert login.status_code == 303 and second.get(LIST).status_code == 200

    assert post(admin, f"{LIST}/{second_id}/role", role="editor"
                ).status_code == 303
    assert second.get(LIST, follow_redirects=False).status_code == 403
    assert second.get("/admin").status_code == 200  # still signed in


def test_invalid_role_is_refused_and_changes_nothing(client_as):
    admin = client_as("admin")
    editor_id = account_id(DEMO_USERS["editor"]["email"])
    assert post(admin, f"{LIST}/{editor_id}/role", role="superuser"
                ).status_code == 400
    assert accounts.get(editor_id).role == "editor"


# ---- deactivation ---------------------------------------------------------

def test_deactivated_account_cannot_log_in(client_as):
    admin = client_as("admin")
    editor_id = account_id(DEMO_USERS["editor"]["email"])
    assert post(admin, f"{LIST}/{editor_id}/deactivate").status_code == 303
    c, login = signed_in(DEMO_USERS["editor"]["email"],
                         DEMO_USERS["editor"]["password"])
    assert login.status_code == 401 and GENERIC in login.text.lower()
    assert c.get("/admin", follow_redirects=False).status_code == 303


def test_deactivated_accounts_existing_session_stops_working(client_as):
    admin, editor = client_as("admin"), client_as("editor")
    assert editor.get("/admin").status_code == 200
    post(admin, f"{LIST}/{account_id(DEMO_USERS['editor']['email'])}/deactivate")
    r = editor.get("/admin", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_deactivating_keeps_the_account_row(client_as):
    admin = client_as("admin")
    editor_id = account_id(DEMO_USERS["editor"]["email"])
    post(admin, f"{LIST}/{editor_id}/deactivate")
    kept = accounts.get(editor_id)
    assert kept is not None and not kept.active
    assert (kept.name, kept.class_year) == ("Demo Editor", 2028)
    assert DEMO_USERS["editor"]["email"] in admin.get(LIST).text


# ---- the last active Admin ------------------------------------------------

def test_last_active_admin_cannot_be_deactivated(client_as):
    admin = client_as("admin")
    admin_id = account_id(DEMO_USERS["admin"]["email"])
    r = post(admin, f"{LIST}/{admin_id}/deactivate")
    assert r.status_code == 400 and "last active admin" in r.text.lower()
    kept = accounts.get(admin_id)
    assert kept.active and kept.role == "admin"
    assert admin.get(LIST).status_code == 200


def test_last_active_admin_cannot_be_demoted(client_as):
    admin = client_as("admin")
    admin_id = account_id(DEMO_USERS["admin"]["email"])
    r = post(admin, f"{LIST}/{admin_id}/role", role="editor")
    assert r.status_code == 400 and "last active admin" in r.text.lower()
    kept = accounts.get(admin_id)
    assert kept.active and kept.role == "admin"
    assert admin.get(LIST).status_code == 200


def test_a_deactivated_admin_does_not_count_as_active(client_as):
    admin = client_as("admin")
    admin_id = account_id(DEMO_USERS["admin"]["email"])
    second_id = make_second_admin()
    # two active Admins: one may be deactivated ...
    assert post(admin, f"{LIST}/{second_id}/deactivate").status_code == 303
    # ... which leaves the first as the last active Admin
    assert post(admin, f"{LIST}/{admin_id}/deactivate").status_code == 400
    assert accounts.get(admin_id).active


def test_an_admin_may_be_deactivated_while_another_is_active(client_as):
    """Handover: the incoming Admin deactivates the outgoing one."""
    outgoing = client_as("admin")
    outgoing_id = account_id(DEMO_USERS["admin"]["email"])
    make_second_admin()
    incoming, _ = signed_in("second.admin@example.test", "second-admin-pw")
    assert post(incoming, f"{LIST}/{outgoing_id}/deactivate").status_code == 303
    assert not accounts.get(outgoing_id).active
    assert outgoing.get("/admin", follow_redirects=False).status_code == 303


# ---- passwords ------------------------------------------------------------

def test_admin_sets_a_new_password(client_as):
    admin = client_as("admin")
    editor_id = account_id(DEMO_USERS["editor"]["email"])
    r = post(admin, f"{LIST}/{editor_id}/password", password="reset-by-admin")
    assert r.status_code == 303

    _, old = signed_in(DEMO_USERS["editor"]["email"],
                       DEMO_USERS["editor"]["password"])
    assert old.status_code == 401
    c, new = signed_in(DEMO_USERS["editor"]["email"], "reset-by-admin")
    assert new.status_code == 303 and c.get("/admin").status_code == 200
    with db.connect() as conn:
        stored = conn.execute("SELECT password_hash FROM account WHERE id = ?",
                              (editor_id,)).fetchone()[0]
    assert stored.startswith("$argon2") and "reset-by-admin" not in stored


def test_blank_new_password_is_refused(client_as):
    admin = client_as("admin")
    editor_id = account_id(DEMO_USERS["editor"]["email"])
    assert post(admin, f"{LIST}/{editor_id}/password", password=""
                ).status_code == 400
    _, login = signed_in(DEMO_USERS["editor"]["email"],
                         DEMO_USERS["editor"]["password"])
    assert login.status_code == 303


# ---- no Reactivate --------------------------------------------------------

@pytest.mark.parametrize("action", ["reactivate", "activate"])
def test_there_is_no_reactivate_action(client_as, action):
    admin = client_as("admin")
    editor_id = account_id(DEMO_USERS["editor"]["email"])
    post(admin, f"{LIST}/{editor_id}/deactivate")
    assert post(admin, f"{LIST}/{editor_id}/{action}").status_code in (404, 405)
    assert not accounts.get(editor_id).active
    assert "reactivate" not in admin.get(LIST).text.lower()


def test_changing_role_or_password_does_not_reactivate(client_as):
    admin = client_as("admin")
    editor_id = account_id(DEMO_USERS["editor"]["email"])
    post(admin, f"{LIST}/{editor_id}/deactivate")
    post(admin, f"{LIST}/{editor_id}/role", role="admin")
    post(admin, f"{LIST}/{editor_id}/password", password="sneaky-new-pw")
    assert not accounts.get(editor_id).active
    _, login = signed_in(DEMO_USERS["editor"]["email"], "sneaky-new-pw")
    assert login.status_code == 401


# ---- CSRF -----------------------------------------------------------------

def test_every_account_form_carries_a_token(client_as):
    admin = client_as("admin")
    for path in (LIST, NEW_FORM):
        page = admin.get(path)
        assert page.status_code == 200
        assert page.text.count("<form") >= 1, path
        assert page.text.count("<form") == page.text.count('name="csrf_token"'), path
    # the list offers a form per action on each Account
    listing = admin.get(LIST).text
    for action in ("role", "deactivate", "password"):
        assert f"/{action}" in listing


def _state_changing_posts():
    # (path template, form data); {admin} / {editor} are filled with real ids
    return [
        (LIST, dict(NEW_ACCOUNT, email="csrf.probe@example.test")),
        ("/admin/accounts/{editor}/role", {"role": "admin"}),
        ("/admin/accounts/{editor}/deactivate", {}),
        ("/admin/accounts/{editor}/password", {"password": "csrf-probe-pw"}),
    ]


@pytest.mark.parametrize("path,data", _state_changing_posts())
@pytest.mark.parametrize("token", [None, "bad"])
def test_account_posts_without_a_valid_token_are_403(client_as, path, data, token):
    admin = client_as("admin")
    editor_id = account_id(DEMO_USERS["editor"]["email"])
    before = account_count()
    form = dict(data) if token is None else {**data, "csrf_token": token}
    r = admin.post(path.format(editor=editor_id), data=form,
                   follow_redirects=False)
    assert r.status_code == 403
    after = accounts.get(editor_id)
    assert (after.role, after.active) == ("editor", True)
    assert account_count() == before
    assert signed_in(DEMO_USERS["editor"]["email"],
                     DEMO_USERS["editor"]["password"])[1].status_code == 303


# ---- unknown ids and anonymous visitors -----------------------------------

@pytest.mark.parametrize("action,data", [
    ("role", {"role": "admin"}),
    ("deactivate", {}),
    ("password", {"password": "whatever-pw"}),
])
def test_unknown_account_id_is_404(client_as, action, data):
    admin = client_as("admin")
    assert post(admin, f"{LIST}/99999/{action}", **data).status_code == 404


@pytest.mark.parametrize("path", [LIST, NEW_FORM])
def test_anonymous_visitors_are_sent_to_login(client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


# ---- review follow-ups ----------------------------------------------------

@pytest.mark.parametrize("class_year", [
    "²",                        # superscript two: isdigit() but not int()
    "٢٠٢٧",      # Arabic-Indic 2027: not ASCII digits
    "99999999999999999999",          # overflows SQLite
    "0", "1999", "2101", "20277", "-2027", "202.7", " ",
])
def test_class_year_must_be_a_four_digit_year_2000_to_2100(client_as, class_year):
    admin = client_as("admin")
    before = account_count()
    r = create(admin, class_year=class_year)
    assert r.status_code == 400
    assert "class year" in r.text.lower() and "2000" in r.text
    assert account_count() == before


@pytest.mark.parametrize("class_year", ["2000", "2027", "2100"])
def test_class_year_boundaries_are_accepted(client_as, class_year):
    admin = client_as("admin")
    assert create(admin, class_year=class_year).status_code == 303
    assert accounts.get(account_id(NEW_ACCOUNT["email"])).class_year == int(class_year)


def test_roles_are_shown_capitalized(client_as):
    admin = client_as("admin")
    listing = admin.get(LIST).text
    assert "<td>Admin</td>" in listing and "<td>Editor</td>" in listing
    assert "<td>admin</td>" not in listing and "<td>editor</td>" not in listing
    for page in (listing, admin.get(NEW_FORM).text):
        assert ">Admin</option>" in page and ">Editor</option>" in page
        assert ">admin</option>" not in page and ">editor</option>" not in page
        assert 'value="admin"' in page and 'value="editor"' in page  # wire values


def test_an_admin_deactivating_themselves_loses_their_own_session(client_as):
    """Allowed while another Admin is active; the redirect is their last page."""
    me = client_as("admin")
    my_id = account_id(DEMO_USERS["admin"]["email"])
    second_id = make_second_admin()
    assert post(me, f"{LIST}/{my_id}/deactivate").status_code == 303
    assert not accounts.get(my_id).active
    assert accounts.get(second_id).active
    after = me.get(LIST, follow_redirects=False)
    assert after.status_code == 303 and after.headers["location"] == "/login"
    _, login = signed_in(DEMO_USERS["admin"]["email"],
                         DEMO_USERS["admin"]["password"])
    assert login.status_code == 401


def test_an_admin_demoting_themselves_loses_admin_pages_but_stays_signed_in(client_as):
    me = client_as("admin")
    my_id = account_id(DEMO_USERS["admin"]["email"])
    make_second_admin()
    assert post(me, f"{LIST}/{my_id}/role", role="editor").status_code == 303
    assert me.get("/admin").status_code == 200
    assert me.get(LIST, follow_redirects=False).status_code == 403
