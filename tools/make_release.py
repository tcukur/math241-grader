"""Build the release ZIP that graders download.

    python tools/make_release.py

Writes, for the version in grader_app/__init__.py:
    dist/MATH241_Grader_<version>.zip   the app as graders get it (one folder, "MATH241 Grader")
    dist/WHATS_NEW_<version>.md         that version's entry from docs/CHANGELOG.md, to post with it

The ZIP holds only the program, its two starters and the user guide. Never any assignment, workspace, key or
student file: those are not in this repository at all (see .gitignore)."""
from __future__ import annotations

import re
import stat
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = "MATH241 Grader"
FILES = ["Start MATH241 Grader.command", "Start MATH241 Grader (Windows).bat", "run_grader.py",
         "requirements-run.txt", "docs/USER_GUIDE.md", "docs/CHANGELOG.md"]
NEVER = (".m241access", ".db", ".db-wal", ".db-shm", ".pyc")


def version() -> str:
    m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', (ROOT / "grader_app/__init__.py").read_text(encoding="utf-8"))
    if not m:
        sys.exit("APP_VERSION not found in grader_app/__init__.py")
    return m.group(1)


def whats_new(v: str) -> str:
    log = (ROOT / "docs/CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(rf"^## {re.escape(v)}\b.*?(?=^## |\Z)", log, re.M | re.S)
    if not m:
        sys.exit(f"docs/CHANGELOG.md has no entry for {v}. Add one before releasing.")
    return m.group(0).strip() + "\n"


def add(z: zipfile.ZipFile, src: Path, arc: str) -> None:
    info = zipfile.ZipInfo(f"{TOP}/{arc}", date_time=(2026, 1, 1, 0, 0, 0))
    executable = src.suffix == ".command"
    info.external_attr = ((0o755 if executable else 0o644) | stat.S_IFREG) << 16   # the Mac starter stays runnable
    info.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(info, src.read_bytes())


def main() -> None:
    v = version()
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    target = out / f"MATH241_Grader_{v}.zip"
    with zipfile.ZipFile(target, "w") as z:
        for f in FILES:
            add(z, ROOT / f, f)
        for p in sorted((ROOT / "grader_app").rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(NEVER):
                add(z, p, str(p.relative_to(ROOT)).replace("\\", "/"))
    (out / f"WHATS_NEW_{v}.md").write_text(whats_new(v), encoding="utf-8")
    print(f"Built {target.relative_to(ROOT)} and dist/WHATS_NEW_{v}.md")


if __name__ == "__main__":
    main()
