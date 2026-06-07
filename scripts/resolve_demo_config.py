"""Resolve MIS demo runtime config (DB URL + AMap keys + interpreter) safely.

Windows PowerShell 5.1 mojibakes CJK string literals embedded in a BOM-less
.ps1, which makes hardcoded CJK paths/globs unreliable. Python reads the
filesystem with correct Unicode, so we centralise secret/interpreter resolution
here and emit shell-safe ``KEY=VALUE`` lines for the launcher to consume.

Security: prints secret VALUES only as ``OKRA_*`` env assignments meant to be
captured by the launching shell, never to a log file. The caller is responsible
for not echoing them. Keys are read first-line-only from the Desktop secrets
folder. Nothing is written to disk.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

HEX32 = re.compile(r"^[0-9a-fA-F]{32}$")


def _first_line(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if s:
                return s
    except Exception:
        pass
    return ""


def find_key_dir() -> Path | None:
    desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    if not desktop.exists():
        return None
    for d in desktop.iterdir():
        if d.is_dir() and ("API" in d.name) and ("密钥" in d.name or "密钥" in d.name or "API" in d.name):
            # prefer a folder that actually contains a PostgreSQL secret
            if any("PostgreSQL" in f.name for f in d.iterdir() if f.is_file()):
                return d
    # fallback: any desktop dir with API in the name
    for d in desktop.iterdir():
        if d.is_dir() and "API" in d.name:
            return d
    return None


def find_unified_python() -> str:
    # The solver/ML venv: has gurobipy + pyomo + torch_geometric + (now) psycopg.
    for base in (Path("D:/"), Path("C:/")):
        if not base.exists():
            continue
        for d in base.iterdir():
            if not d.is_dir():
                continue
            py = d / "backend" / "venv" / "Scripts" / "python.exe"
            if py.exists():
                # confirm it is the analysis platform venv (has pyomo), not logistics
                try:
                    import subprocess

                    r = subprocess.run(
                        [str(py), "-c", "import pyomo, gurobipy"],
                        capture_output=True, timeout=30,
                    )
                    if r.returncode == 0:
                        return str(py)
                except Exception:
                    continue
    return "python"


def main() -> int:
    key_dir = find_key_dir()
    out: list[str] = []

    # Database URL (only if not already set by caller).
    if not os.environ.get("OKRA_DATABASE_URL") and key_dir:
        pg = next((f for f in key_dir.iterdir() if f.is_file() and "PostgreSQL" in f.name), None)
        if pg:
            pw = _first_line(pg)
            if pw:
                out.append(f"OKRA_DATABASE_URL=postgresql+psycopg://okra:{pw}@localhost:5432/okra_cold_storage")

    # AMap keys: 前端 (frontend/browser JS) vs 后端 (backend/web-service).
    if key_dir:
        js_file = next((f for f in key_dir.iterdir() if f.is_file() and "前端" in f.name and "API" in f.name), None)
        web_file = next((f for f in key_dir.iterdir() if f.is_file() and "后端" in f.name and "API" in f.name), None)
        if js_file:
            js = _first_line(js_file)
            if HEX32.match(js):
                out.append("OKRA_MAP_PROVIDER=amap")
                out.append(f"OKRA_AMAP_JS_KEY={js}")
                out.append("OKRA_MAP_PUBLIC_KEY_ALLOWED=true")
        if web_file:
            web = _first_line(web_file)
            if HEX32.match(web):
                out.append(f"OKRA_AMAP_WEB_SERVICE_KEY={web}")

    out.append(f"UNIFIED_PYTHON={find_unified_python()}")
    # Emit KEY=VALUE lines (no secret labels, no logging).
    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
