"""The independent oracle: npm's own resolver.

For each artifact, ``npm ls <package>`` is run against the pinned lockfile in a scratch directory, offline, with
``--package-lock-only``. Its answer does not pass through this project's lockfile parser or its graph, so it can
grade all three systems fairly.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT_FIELDS = ("name", "version", "dependencies", "devDependencies", "optionalDependencies", "peerDependencies")


def npm_available() -> bool:
    return shutil.which("npm") is not None


def npm_version() -> str:
    out = subprocess.run([shutil.which("npm"), "--version"], capture_output=True, text=True, check=False)
    return out.stdout.strip()


def unsupported_reason(lock_bytes: bytes) -> str | None:
    """Why npm ls cannot be used on this lockfile, or None if it can (workspaces need member package.json files)."""
    root = (json.loads(lock_bytes).get("packages") or {}).get("")
    if root is None:
        return "not an npm v2/v3 lockfile"
    if root.get("workspaces"):
        return "uses workspaces"
    return None


def _walk(deps: dict | None, name: str, top: str | None, out: dict[str, set[str]]) -> None:
    for dep_name, meta in (deps or {}).items():
        branch = top or dep_name
        if dep_name == name and meta.get("version"):
            out.setdefault(meta["version"], set()).add(branch)
        _walk(meta.get("dependencies"), name, branch, out)


def npm_ls(lock_bytes: bytes, name: str) -> dict[str, set[str]]:
    """Versions of ``name`` that npm finds in this lockfile, each with the top-level dependencies that lead to it."""
    root = json.loads(lock_bytes)["packages"][""]
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        (scratch / "package.json").write_text(json.dumps({k: root[k] for k in ROOT_FIELDS if k in root}), encoding="utf-8")
        (scratch / "package-lock.json").write_bytes(lock_bytes)
        proc = subprocess.run(
            [shutil.which("npm"), "ls", name, "--package-lock-only", "--all", "--json", "--offline"],
            cwd=scratch, capture_output=True, text=True, timeout=300, check=False)
    tree = json.loads(proc.stdout or "{}")
    found: dict[str, set[str]] = {}
    _walk(tree.get("dependencies"), name, None, found)
    return found
