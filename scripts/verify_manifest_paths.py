#!/usr/bin/env python3
"""Verify manifest-referenced dashboard signal files exist locally and/or in a git ref."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REQUIRED_REPORT_FILES = [
    "manifest.json",
    "sports-facts.json",
    "sports-events.json",
    "contextual-notes-candidates.json",
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def git_path_exists(ref: str, rel_path: str) -> bool:
    proc = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}:{rel_path}"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return proc.returncode == 0


def required_paths(manifest: dict, require_report_dates: set[str]) -> list[str]:
    paths: set[str] = set()
    for file_info in manifest.get("files", {}).values():
        path = file_info.get("path")
        if path:
            paths.add(path)

    dated = manifest.get("dated_snapshot", {}).get("path")
    if dated:
        paths.add(dated)

    for report in manifest.get("available_reports", []):
        path = report.get("path")
        report_date = report.get("report_date")
        if path:
            paths.add(path)
        if report_date in require_report_dates:
            for name in REQUIRED_REPORT_FILES:
                paths.add(f"data/reports/{report_date}/{name}")

    latest = manifest.get("latest_report_date") or manifest.get("report_date")
    if latest:
        for name in REQUIRED_REPORT_FILES:
            paths.add(f"data/reports/{latest}/{name}")

    for report_date in require_report_dates:
        for name in REQUIRED_REPORT_FILES:
            paths.add(f"data/reports/{report_date}/{name}")

    return sorted(paths)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(DATA / "manifest.json"))
    parser.add_argument("--git-ref", help="Also verify paths exist in this git ref, e.g. HEAD or origin/main")
    parser.add_argument("--require-report", action="append", default=[], help="Require complete data/reports/YYYY-MM-DD bundle; repeatable")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = load_json(manifest_path)
    require_reports = set(args.require_report)
    paths = required_paths(manifest, require_reports)
    missing_local = [p for p in paths if not (ROOT / p).exists()]
    missing_git = [p for p in paths if args.git_ref and not git_path_exists(args.git_ref, p)]

    result = {
        "status": "ok" if not missing_local and not missing_git else "error",
        "manifest": str(manifest_path.relative_to(ROOT) if manifest_path.is_relative_to(ROOT) else manifest_path),
        "checked_paths": len(paths),
        "git_ref": args.git_ref,
        "missing_local": missing_local,
        "missing_git": missing_git,
    }
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
