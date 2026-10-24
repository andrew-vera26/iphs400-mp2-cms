"""The `cms` command: serve, publish, deploy, backup.

    uv run cms serve      # admin console + public preview at http://localhost:8000
    uv run cms publish    # render site/ from published content
    uv run cms deploy     # push site/ to the gh-pages branch (Pages serves it)
    uv run cms backup DIR # zip the database and uploads into DIR (outside the repo)
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from app import settings, site_state
from app.publish import PublishRefused, render_site


def _inside_repository(folder: Path) -> bool:
    """True if `folder`, or the nearest part of it that exists, is the
    repository or inside it. Compared by file identity, so a case-insensitive
    filesystem and symlinks cannot disguise it, even for a folder that does
    not exist yet."""
    nearest = folder.resolve()
    while not nearest.exists():
        nearest = nearest.parent
    return any(os.path.samefile(p, settings.ROOT)
               for p in (nearest, *nearest.parents))


def backup(folder: Path) -> Path:
    """Write cms-backup-<YYYYMMDD-HHMM>.zip into `folder`: an online-backup
    copy of the database, and the uploads folder under uploads/. Raises
    ValueError, creating nothing, if the database does not exist, `folder` is
    inside the repository (symlinks are followed) or the archive already
    exists. Symlinks inside uploads/ are skipped with a warning."""
    if not settings.DATABASE_PATH.is_file():
        raise ValueError(f"the database {settings.DATABASE_PATH} does not "
                         "exist; there is nothing to back up.")
    if _inside_repository(folder):
        raise ValueError(f"{folder} is inside the repository; choose a "
                         "private folder outside it.")
    target = folder.resolve()
    target.mkdir(parents=True, exist_ok=True)
    archive = target / f"cms-backup-{datetime.now():%Y%m%d-%H%M}.zip"
    if archive.exists():
        raise ValueError(f"{archive} already exists; it was not overwritten.")
    partial = None
    try:
        with tempfile.TemporaryDirectory() as scratch:
            copy = Path(scratch) / settings.DATABASE_PATH.name
            source = sqlite3.connect(settings.DATABASE_PATH)
            dest = sqlite3.connect(copy)
            try:
                source.backup(dest)
            finally:
                dest.close()
                source.close()
            with tempfile.NamedTemporaryFile(
                    dir=target, prefix=".cms-backup-", suffix=".part",
                    delete=False) as handle:
                partial = Path(handle.name)
            with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(copy, copy.name)
                if settings.UPLOADS.is_dir():
                    for path in sorted(settings.UPLOADS.rglob("*")):
                        if path.is_symlink():
                            print(f"cms backup: skipped symlink {path}",
                                  file=sys.stderr)
                        elif path.is_file():
                            z.write(path, "uploads/" + path.relative_to(
                                settings.UPLOADS).as_posix())
        try:
            os.link(partial, archive)       # fails rather than overwrites
        except FileExistsError:
            raise ValueError(f"{archive} already exists; it was not "
                             "overwritten.") from None
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cms")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the admin console locally")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true", default=True)
    sub.add_parser("publish", help="render site/ from published content")
    deploy = sub.add_parser("deploy", help="push site/ to gh-pages")
    deploy.add_argument("--message", default="Publish site")
    backup_cmd = sub.add_parser("backup", help="zip the database and uploads")
    backup_cmd.add_argument("folder", type=Path,
                            help="output folder, outside the repository")
    args = parser.parse_args(argv)

    if args.command == "serve":
        import uvicorn

        uvicorn.run("app.main:app", port=args.port, reload=args.reload)
        return 0

    if args.command == "publish":
        try:
            out = render_site()
        except PublishRefused as refused:
            print(f"cms publish refused: {refused}")
            return 1
        site_state.record_render()
        print(f"Wrote {out}. Preview it with:  python3 -m http.server -d {out} 8001")
        return 0

    if args.command == "backup":
        try:
            archive = backup(args.folder)
        except ValueError as refused:
            print(f"cms backup refused: {refused}")
            return 1
        print(f"Wrote {archive}")
        return 0

    if args.command == "deploy":
        if not settings.SITE.exists():
            print("site/ does not exist yet — run `uv run cms publish` first.")
            return 1
        result = subprocess.run(
            [sys.executable, "-m", "ghp_import", "-n", "-p", "-m", args.message,
             str(settings.SITE)],
        )
        if result.returncode == 0:
            print("Pushed to gh-pages. Settings -> Pages -> Deploy from a branch -> "
                  "gh-pages / root, then wait up to 10 minutes.")
        return result.returncode
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
