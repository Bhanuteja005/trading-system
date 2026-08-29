#!/usr/bin/env python3
"""Fail the build if anything outside packages/config reads the environment.

Config has exactly one entry point. Scattered os.environ lookups are how a
service ends up live when someone believed it was in dry-run.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {ROOT / "packages" / "config" / "src" / "tsys" / "config"}
SKIP_PARTS = {
    "packages/openalgo", "monorepo", "node_modules", ".venv",
    "__pycache__", "scripts/check_env_boundary.py",
}


def _skip(p: Path) -> bool:
    rel = p.relative_to(ROOT).as_posix()
    return any(s in rel for s in SKIP_PARTS)


def _allowed(p: Path) -> bool:
    return any(a in p.parents for a in ALLOWED)


def violations() -> list[str]:
    found = []
    for path in ROOT.rglob("*.py"):
        if _skip(path) or _allowed(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            # os.environ / os.getenv / os.environ.get
            if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
                if isinstance(node.value, ast.Name) and node.value.id == "os":
                    rel = path.relative_to(ROOT).as_posix()
                    found.append(f"{rel}:{node.lineno}: os.{node.attr} outside packages/config")
    return found


if __name__ == "__main__":
    found = violations()
    if found:
        print("Environment boundary violations:\n", file=sys.stderr)
        for v in found:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nRead config through `from tsys.config import settings` instead.",
            file=sys.stderr,
        )
        sys.exit(1)
    print("env boundary: clean")
