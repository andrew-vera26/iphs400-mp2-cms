"""Measure horizontal overflow at a 390x844 phone viewport.

Run from the repository root, installing nothing into the repo:

    uv run --no-project --env-file .env --with playwright==1.58.0 \
        python scripts/check_phone_width.py

Checks document.documentElement.scrollWidth against the viewport width on the
public home page and three admin screens, then writes
docs/screenshots/overflow-390.md. The admin login reads CMS_ADMIN_PASSWORD from
the environment and never prints it. If nothing answers on the local port, the
script starts the app itself and stops it afterwards.
"""
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots" / "overflow-390.md"
WIDTH, HEIGHT = 390, 844
PORT = 8000
LOCAL = f"http://localhost:{PORT}"
PUBLIC = "https://andrew-vera26.github.io/iphs400-mp2-cms/"
ADMIN_EMAIL = re.search(r'ADMIN_EMAIL = "([^"]+)"',
                        (ROOT / "app" / "seed.py").read_text()).group(1)
ADMIN_SCREENS = [("admin dashboard", "/admin"),
                 ("admin recaps list", "/admin/recaps"),
                 ("admin accounts list", "/admin/accounts")]


def listening() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def start_app() -> subprocess.Popen:
    proc = subprocess.Popen(
        ["uv", "run", "--env-file", ".env", "python", "-m", "uvicorn",
         "app.main:app", "--port", str(PORT)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if listening():
            return proc
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    proc.terminate()
    sys.exit("could not start the app on port %d" % PORT)


def measure(page, url: str) -> int:
    page.goto(url, wait_until="networkidle")
    return page.evaluate("document.documentElement.scrollWidth")


def main() -> int:
    password = os.environ.get("CMS_ADMIN_PASSWORD")
    if not password:
        sys.exit("CMS_ADMIN_PASSWORD is not set (run with --env-file .env)")
    started = None if listening() else start_app()
    rows = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_context(
                viewport={"width": WIDTH, "height": HEIGHT}).new_page()
            rows.append(("public home", PUBLIC, measure(page, PUBLIC)))

            page.goto(LOCAL + "/login")
            page.fill('input[name="email"]', ADMIN_EMAIL)
            page.fill('input[name="password"]', password)
            page.click('form[action="/login"] button[type="submit"], '
                       'form button[type="submit"]')
            page.wait_for_load_state("networkidle")
            if page.url.rstrip("/").endswith("/login"):
                sys.exit("admin login failed (is the database seeded?)")
            for name, path in ADMIN_SCREENS:
                rows.append((name, LOCAL + path, measure(page, LOCAL + path)))
            browser.close()
    finally:
        if started:
            started.terminate()
            started.wait(timeout=10)

    lines = [
        "# Phone-width overflow check, 390 px", "",
        f"Viewport {WIDTH}x{HEIGHT}. `scripts/check_phone_width.py` measures "
        f"`document.documentElement.scrollWidth` against {WIDTH}. A page "
        "passes when scrollWidth is no greater than the viewport width.", "",
        "| Page | Viewport | scrollWidth | Result |", "|---|---|---|---|",
    ]
    for name, _url, sw in rows:
        lines.append(f"| {name} | {WIDTH}x{HEIGHT} | {sw} | "
                     f"{'pass' if sw <= WIDTH else 'fail'} |")
    lines += [
        "", "Tables sit inside a scroll container (`.table-scroll`), so the "
        "measurement is page-level: a wide table scrolls inside its own "
        "container and does not widen the document. This check does not "
        "measure the width of the tables themselves.", "",
        "Pages measured:", ""]
    lines += [f"- {name}: {url}" for name, url, _ in rows]
    OUT.write_text("\n".join(lines) + "\n")
    print(OUT.read_text())
    return 0 if all(sw <= WIDTH for *_, sw in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
