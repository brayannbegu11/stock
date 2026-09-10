"""Publica el sitio (docs/index.html + docs/site + docs/.nojekyll) en la rama `gh-pages` del remoto.

GitHub Pages sirve esa rama en https://brayannbegu11.github.io/stock/. La fuente del sitio vive en
`docs/` de `main`; esta rama es sólo el artefacto desplegado y se reescribe entera en cada publicación.

Uso: python scripts/deploy_pages.py [--no-push]
Requiere `git` con acceso de escritura al remoto `origin`.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ["docs/index.html", "docs/.nojekyll"]
DIRS = ["docs/site"]
BRANCH = "gh-pages"


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()
    head = git("rev-parse", "--short", "HEAD").stdout.strip()
    with tempfile.TemporaryDirectory(prefix="twlab-pages-") as tmp:
        wt = Path(tmp) / "wt"
        # rama huérfana nueva en cada despliegue: el historial del sitio vive en main
        git("worktree", "add", "--detach", str(wt))
        try:
            git("checkout", "--orphan", BRANCH, cwd=wt)
            git("rm", "-rf", "-q", ".", cwd=wt, check=False)
            for rel in FILES:
                src = ROOT / rel
                if src.exists():
                    dst = wt / Path(rel).name
                    shutil.copy2(src, dst)
            for rel in DIRS:
                src = ROOT / rel
                if src.exists():
                    shutil.copytree(src, wt / Path(rel).name, dirs_exist_ok=True)
            git("add", "-A", cwd=wt)
            git("-c", "user.name=Brayann Benavides", "-c", "user.email=brayannbegu11@gmail.com",
                "commit", "-q", "-m", f"Publicar sitio desde main@{head}", cwd=wt)
            if not args.no_push:
                r = git("push", "--force", "origin", f"HEAD:{BRANCH}", cwd=wt)
                print(r.stderr.strip() or r.stdout.strip())
            print(f"gh-pages actualizado desde main@{head}")
        finally:
            git("worktree", "remove", "--force", str(wt), check=False)
            git("branch", "-D", BRANCH, check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
